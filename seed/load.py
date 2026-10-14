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
        for p in sorted(set(props) - req - opt - schema.EDGE_COMMON_OPTIONAL):
            errs.append(f"{tag}: edge prop '{p}' not in schema")
        for k, v in props.items():
            if schema.is_time_prop(k) and type(v) is not int:
                errs.append(f"{tag}: time prop '{k}' must be int, got {v!r}")
            if (t, k) in schema.EDGE_ENUMS and v not in schema.EDGE_ENUMS[(t, k)]:
                errs.append(f"{tag}: {k}={v!r} not allowed")
        if t == "SOURCED_FROM" and not props.get("excerpt"):
            errs.append(f"{tag}: excerpt must be non-empty")
    return errs


def create_indexes(g, quiet=False):
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
    if not quiet:
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


def package_for(graph_name):
    """Seed package for a graph: its own name if seed/data/<name> exists, else the package sharing its first word
    (kestrel_pay_test -> kestrel_pay, northwind_test -> northwind_health), else kestrel_pay."""
    data = os.path.join(os.path.dirname(__file__), "data")
    pkgs = sorted(d for d in os.listdir(data) if os.path.isdir(os.path.join(data, d)) and not d.startswith("_"))
    return graph_name if graph_name in pkgs else next((p for p in pkgs if p.split("_")[0] == graph_name.split("_")[0]), "kestrel_pay")


def load(graph_name, reset=True, now=None, data_package=None, quiet=False):
    """Validate + load a tenant seed into `graph_name`. data_package defaults to graph_name (seed/data/<pkg>).
    Returns {"nodes": Counter, "edges": Counter, "now": int}. Raises ValueError listing every validation problem."""
    load_dotenv()
    t0 = time.time()
    pkg = data_package or package_for(graph_name)
    timeutil.set_now(now)  # BEFORE the data import: data computes times at import time
    for name in [m for m in sys.modules if m == f"seed.data.{pkg}" or m.startswith(f"seed.data.{pkg}.")]:
        del sys.modules[name]  # force re-evaluation so a new NOW takes effect when called twice in one process
    data = importlib.import_module(f"seed.data.{pkg}")
    nodes = [dict(n) for n in data.NODES]
    for n in nodes:
        n.setdefault("origin", "seed")
        n.setdefault("created_at", timeutil.NOW)
    errs = validate(nodes, data.EDGES)
    if errs:
        raise ValueError(f"VALIDATION FAILED ({len(errs)} problems), nothing written:\n" + "\n".join("  - " + e for e in errs))

    db = FalkorDB(host=os.getenv("FALKORDB_HOST", "localhost"), port=int(os.getenv("FALKORDB_PORT", "6379")))
    if reset:
        try:
            db.select_graph(graph_name).delete()
        except Exception:
            pass
    g = db.select_graph(graph_name)
    create_indexes(g, quiet)
    write(g, nodes, data.EDGES)

    summary = {"nodes": Counter(n["label"] for n in nodes), "edges": Counter(e[1] for e in data.EDGES), "now": timeutil.NOW}
    if not quiet:
        print(f"\ngraph '{graph_name}' loaded (NOW={timeutil.NOW}):")
        print("  nodes:", ", ".join(f"{k}={v}" for k, v in sorted(summary["nodes"].items())))
        print("  edges:", ", ".join(f"{k}={v}" for k, v in sorted(summary["edges"].items())))
        print(f"  {len(nodes)} nodes, {len(data.EDGES)} edges in {time.time() - t0:.1f}s")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True)
    ap.add_argument("--reset", action="store_true", help="delete the graph first")
    ap.add_argument("--now", type=int, help="override NOW (epoch seconds)")
    args = ap.parse_args()
    try:
        load(args.graph, reset=args.reset, now=args.now)
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
