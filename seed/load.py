"""Load a tenant seed into FalkorDB.  python -m seed.load --graph kestrel_pay [--reset] [--now EPOCH]"""
import argparse
import importlib
import os
import sys
import time
from collections import Counter, defaultdict

from dotenv import load_dotenv
from falkordb import FalkorDB

from seed import schema, timeutil

BATCH = 100


def validate(nodes, edges):
    """Return a list of human-readable problems; empty list = data is clean."""
    errs, ids = [], {}
    for n in nodes:
        nid = n.get("id")
        if not isinstance(nid, str) or ":" not in nid:
            errs.append(f"node without a valid id: {n!r:.120}")
            continue
        prefix = nid.split(":", 1)[0]
        label = n.get("label")
        if prefix not in schema.PREFIX_TO_LABEL:
            errs.append(f"{nid}: unknown id prefix '{prefix}'")
            continue
        if label != schema.PREFIX_TO_LABEL[prefix]:
            errs.append(f"{nid}: label '{label}' does not match prefix '{prefix}' (expects {schema.PREFIX_TO_LABEL[prefix]})")
            continue
        if nid in ids:
            errs.append(f"duplicate id {nid}")
        ids[nid] = label
        props = {k for k in n if k != "label"}
        req, opt = schema.REQUIRED[label], schema.OPTIONAL.get(label, set())
        for p in sorted(req - props):
            errs.append(f"{nid}: missing required prop '{p}'")
        for p in sorted(props - req - opt - schema.COMMON):
            errs.append(f"{nid}: prop '{p}' is not in the schema for {label}")
        for k, v in n.items():
            if schema.is_time_prop(k) and (type(v) is not int):
                errs.append(f"{nid}: time prop '{k}' must be int epoch seconds, got {v!r}")
            if (label, k) in schema.ENUMS and v not in schema.ENUMS[(label, k)]:
                errs.append(f"{nid}: {k}={v!r} not in {sorted(schema.ENUMS[(label, k)], key=str)}")
    seen = set()
    for a, t, b, props in edges:
        tag = f"edge ({a})-[:{t}]->({b})"
        if t not in schema.EDGE_RULES:
            errs.append(f"{tag}: unknown edge type"); continue
        bad = [x for x in (a, b) if x not in ids]
        if bad:
            errs.append(f"{tag}: endpoint id does not exist: {bad}"); continue
        if (ids[a], ids[b]) not in schema.EDGE_RULES[t]:
            errs.append(f"{tag}: {ids[a]}->{ids[b]} not allowed for {t}")
        if (a, t, b) in seen:
            errs.append(f"{tag}: duplicate edge")
        seen.add((a, t, b))
        req, opt = schema.EDGE_PROPS.get(t, (set(), set()))
        for p in sorted(req - set(props)):
            errs.append(f"{tag}: missing edge prop '{p}'")
        for p in sorted(set(props) - req - opt):
            errs.append(f"{tag}: edge prop '{p}' not in schema")
        for k, v in props.items():
            if schema.is_time_prop(k) and type(v) is not int:
                errs.append(f"{tag}: time prop '{k}' must be int, got {v!r}")
            if (t, k) in schema.EDGE_ENUMS and v not in schema.EDGE_ENUMS[(t, k)]:
                errs.append(f"{tag}: {k}={v!r} not allowed")
        if t == "SOURCED_FROM" and not props.get("excerpt"):
            errs.append(f"{tag}: excerpt must be non-empty")
    return errs


def create_indexes(g):
    def run(q):
        try:
            g.query(q)
        except Exception as e:  # FalkorDB raises ResponseError("Index already exists ...")
            if "already" not in str(e).lower():
                raise
    for label, prop in schema.RANGE_INDEXES:
        run(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
    for label, props in schema.FULLTEXT_INDEXES:
        # FalkorDB 4.x rejects the multi-arg createNodeIndex procedure from schema.md; this DDL builds the same index.
        run(f"CREATE FULLTEXT INDEX FOR (n:{label}) ON ({', '.join('n.' + p for p in props)})")
    ok = 0
    for label in schema.LABELS:
        try:
            g.create_node_unique_constraint(label, "id")
            ok += 1
        except Exception as e:
            if "already" in str(e).lower():
                ok += 1
            else:
                print(f"  note: unique constraint on {label}.id skipped ({e})")
    print(f"indexes: {len(schema.RANGE_INDEXES)} range, {len(schema.FULLTEXT_INDEXES)} full-text; unique constraints: {ok}/{len(schema.LABELS)}")


def write(g, nodes, edges):
    by_label = defaultdict(list)
    for n in nodes:
        by_label[n["label"]].append({k: v for k, v in n.items() if k != "label"})
    for label, rows in by_label.items():
        assert label in schema.LABELS  # only checked names are ever interpolated
        for i in range(0, len(rows), BATCH):
            g.query(f"UNWIND $rows AS row MERGE (n:{label} {{id: row.id}}) SET n += row", {"rows": rows[i:i + BATCH]})
    groups = defaultdict(list)
    for a, t, b, props in edges:
        groups[(a.split(":", 1)[0], t, b.split(":", 1)[0])].append({"from": a, "to": b, "props": props})
    for (pa, t, pb), rows in groups.items():
        la, lb = schema.PREFIX_TO_LABEL[pa], schema.PREFIX_TO_LABEL[pb]
        assert t in schema.EDGE_RULES and (la, lb) in schema.EDGE_RULES[t]
        for i in range(0, len(rows), BATCH):
            g.query(f"UNWIND $rows AS row MATCH (a:{la} {{id: row.from}}), (b:{lb} {{id: row.to}}) "
                    f"MERGE (a)-[r:{t}]->(b) SET r += row.props", {"rows": rows[i:i + BATCH]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True)
    ap.add_argument("--reset", action="store_true", help="delete the graph first")
    ap.add_argument("--now", type=int, help="override NOW (epoch seconds)")
    args = ap.parse_args()
    load_dotenv()
    t0 = time.time()

    timeutil.set_now(args.now)  # BEFORE the data import: data computes times at import time
    data = importlib.import_module(f"seed.data.{args.graph}")
    nodes = [dict(n) for n in data.NODES]
    for n in nodes:
        n.setdefault("origin", "seed")
        n.setdefault("created_at", timeutil.NOW)
    errs = validate(nodes, data.EDGES)
    if errs:
        print(f"VALIDATION FAILED ({len(errs)} problems), nothing written:", file=sys.stderr)
        for e in errs:
            print("  -", e, file=sys.stderr)
        sys.exit(1)

    db = FalkorDB(host=os.getenv("FALKORDB_HOST", "localhost"), port=int(os.getenv("FALKORDB_PORT", "6379")))
    if args.reset:
        try:
            db.select_graph(args.graph).delete()
        except Exception:
            pass
    g = db.select_graph(args.graph)
    create_indexes(g)
    write(g, nodes, data.EDGES)

    print(f"\ngraph '{args.graph}' loaded (NOW={timeutil.NOW}):")
    print("  nodes:", ", ".join(f"{k}={v}" for k, v in sorted(Counter(n['label'] for n in nodes).items())))
    print("  edges:", ", ".join(f"{k}={v}" for k, v in sorted(Counter(e[1] for e in data.EDGES).items())))
    print(f"  {len(nodes)} nodes, {len(data.EDGES)} edges in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
