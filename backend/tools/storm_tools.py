"""Alert-storm tools: several alerts at once, read through FalkorDB's graph algorithms.  fn(ctx, **args) -> ToolOutput.

correlate_alerts  algo.BFS from every alerting service (what it depends on, up to 6 hops) -> the dependencies most
                  alerts share, ranked; algo.SPpaths gives each alert's path to the top candidates
connected_impact  algo.WCC on a projection: the alerting services plus everything they call, copied into a scratch
                  graph (same labels, deleted at once). Alerts in different components share no dependency at all, so
                  they cannot have a common cause
blast_tiers       algo.SSpaths (incoming) from a service: who calls it at 1, 2, 3... hops, split into alerting and
                  silent (silent callers are the next to feel it: notify them, don't page them)
failure_domains   algo.labelPropagation (CDLP) over DEPENDS_ON: which community each service falls in (context only)

Same rules as graph_tools: parameterised Cypher, read-only on the tenant graph, narrow aggregation rows (FalkorDB 6.0.2
crashed on wide ones). connected_impact writes ONLY to its own scratch graph `<tenant>__proj_<hex>`, never to the tenant.
"""
import secrets

from backend.db import client
from backend.tools.graph_tools import MAX_HOPS, _sp
from backend.tools.receipt import Recorder, clamp

MAX_ALERTS = 12


def _alerts(rec, service_ids):
    if isinstance(service_ids, str):
        service_ids = [service_ids]
    if not isinstance(service_ids, list) or not service_ids or not all(isinstance(s, str) for s in service_ids):
        return None, "service_ids must be a non-empty list of service ids; try find_service"
    ids = list(dict.fromkeys(service_ids))[:MAX_ALERTS]
    for s in ids:
        if err := rec.check(s, "Service"):
            return None, err
    return ids, None


def _algos_on(rec):
    return None if rec.ctx.algorithms else "graph algorithms are switched off in this run"


# ───────────── correlate_alerts ─────────────
Q_REACH = """UNWIND $ids AS sid
MATCH (s:Service {id:sid})
CALL algo.BFS(s, $depth, 'DEPENDS_ON') YIELD nodes
UNWIND nodes AS d
RETURN d.id, collect(DISTINCT sid)"""
Q_CALLER_COUNT = """MATCH (c:Service)-[:DEPENDS_ON*1..6]->(s:Service) WHERE s.id IN $ids RETURN s.id, count(DISTINCT c)"""


def correlate_alerts(ctx, service_ids, max_hops=6):
    rec = Recorder(ctx, "correlate_alerts", {"service_ids": service_ids, "max_hops": max_hops})
    if err := _algos_on(rec):
        return rec.error(err)
    ids, err = _alerts(rec, service_ids)
    if err:
        return rec.error(err)
    depth = clamp(max_hops, 1, MAX_HOPS, 6)
    cover = {s: {s} for s in ids}  # every alerting service "reaches" itself (it may be the shared root)
    for d, who in rec.q(Q_REACH, {"ids": ids, "depth": depth}):
        cover.setdefault(d, set()).update(who)
    shared = {d: who for d, who in cover.items() if len(who) >= 2}
    if not shared:
        rec.hl(*ids)
        return rec.done({"alerts": ids, "roots": [], "note": "no two alerting services share any dependency"})
    top = sorted(shared, key=lambda d: (-len(shared[d]), d not in ids, d))
    best = len(shared[top[0]])
    consider = [d for d in top if len(shared[d]) >= best - 1][:6]  # paths only for the leading candidates
    callers = dict(rec.q(Q_CALLER_COUNT, {"ids": consider}))
    roots = []
    for d in consider:
        paths, hops = {}, 0
        for a in sorted(shared[d]):
            sp = _sp(rec, a, d, "outgoing", depth)
            paths[a] = sp["ids"] if sp else [a, d]
            hops += len(paths[a]) - 1
        roots.append({"id": d, "covers": sorted(shared[d]), "coverage": len(shared[d]), "alerting": d in ids,
                      "total_hops": hops, "callers": callers.get(d, 0), "paths": paths})
    roots.sort(key=lambda r: (-r["coverage"], not r["alerting"], r["total_hops"], r["id"]))
    for r in roots[:3]:
        for p in r["paths"].values():
            rec.hl_path(p)
    rec.hl(*ids)
    res = {"alerts": ids, "max_hops": depth, "roots": roots[:5],
           "uncovered_by_top": sorted(set(ids) - set(roots[0]["covers"])),
           "ranking": "alerts covered (desc), alerting before silent, total hops (asc)"}
    if len(shared) > len(consider):
        res["other_shared"] = len(shared) - len(consider)
    return rec.done(res, limit=4500)


# ───────────── connected_impact ─────────────
Q_CLOSURE = """UNWIND $ids AS sid
MATCH (s:Service {id:sid})
CALL algo.BFS(s, 6, 'DEPENDS_ON') YIELD nodes
UNWIND nodes AS d
RETURN DISTINCT d.id"""
Q_EDGES_AMONG = "MATCH (a:Service)-[:DEPENDS_ON]->(b:Service) WHERE a.id IN $ids AND b.id IN $ids RETURN a.id, b.id"
Q_PROJ_NODES = "UNWIND $ids AS i CREATE (:Service {id: i})"
Q_PROJ_EDGES = "UNWIND $pairs AS p MATCH (a:Service {id: p[0]}), (b:Service {id: p[1]}) CREATE (a)-[:DEPENDS_ON]->(b)"
Q_WCC = """CALL algo.WCC({nodeLabels: ['Service'], relationshipTypes: ['DEPENDS_ON']}) YIELD node, componentId
RETURN node.id, componentId"""


def connected_impact(ctx, service_ids):
    rec = Recorder(ctx, "connected_impact", {"service_ids": service_ids})
    if err := _algos_on(rec):
        return rec.error(err)
    ids, err = _alerts(rec, service_ids)
    if err:
        return rec.error(err)
    nodes = sorted(set(ids) | {r[0] for r in rec.q(Q_CLOSURE, {"ids": ids})})
    pairs = [[a, b] for a, b in rec.q(Q_EDGES_AMONG, {"ids": nodes})]
    name = f"{ctx.tenant}__proj_{secrets.token_hex(4)}"
    g = client().select_graph(name)
    try:  # the projection lives in its own scratch graph: the tenant graph is never written
        for q, p in ((Q_PROJ_NODES, {"ids": nodes}), (Q_PROJ_EDGES, {"pairs": pairs})):
            rec.queries.append({"cypher": " ".join(q.split()), "params": {k: f"<{len(v)} items>" for k, v in p.items()},
                                "write": True, "graph": "scratch projection"})
            g.query(q, p)
        rec.queries.append({"cypher": " ".join(Q_WCC.split()), "params": {}, "graph": "scratch projection"})
        comp = dict(g.ro_query(Q_WCC).result_set)
    finally:
        try:
            g.delete()
        except Exception:
            pass
    groups = {}
    for a in ids:
        groups.setdefault(comp.get(a), []).append(a)
    components = [{"alerts": sorted(v), "size": sum(1 for x in comp.values() if x == k)}
                  for k, v in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[1]))]
    rec.hl(*ids)
    return rec.done({"alerts": ids, "projection": {"services": len(nodes), "edges": len(pairs)},
                     "components": components, "incidents_at_least": len(components),
                     "meaning": "alerts in different components share no dependency at all, so no single cause can "
                                "explain them together"})


# ───────────── blast_tiers ─────────────
Q_TIERS = """MATCH (s:Service {id:$id})
CALL algo.SSpaths({sourceNode: s, relTypes: ['DEPENDS_ON'], relDirection: 'incoming', maxLen: $depth, pathCount: 1000}) YIELD path, pathWeight
RETURN last(nodes(path)).id, min(pathWeight)"""


def blast_tiers(ctx, service_id, alerting=None, max_hops=4):
    rec = Recorder(ctx, "blast_tiers", {"service_id": service_id, "alerting": alerting, "max_hops": max_hops})
    if err := _algos_on(rec):
        return rec.error(err)
    if err := rec.check(service_id, "Service"):
        return rec.error(err)
    alerting = set(alerting or []) if isinstance(alerting, (list, type(None))) else None
    if alerting is None:
        return rec.error("alerting must be a list of service ids (or omitted)")
    depth = clamp(max_hops, 1, MAX_HOPS, 4)
    tiers = {}
    for sid, hops in rec.q(Q_TIERS, {"id": service_id, "depth": depth}):
        tiers.setdefault(int(hops), []).append(sid)
    out = [{"hops": h, "alerting": sorted(s for s in tiers[h] if s in alerting),
            "silent": sorted(s for s in tiers[h] if s not in alerting)} for h in sorted(tiers)]
    rec.hl(service_id, *[s for t in tiers.values() for s in t])
    return rec.done({"service": service_id, "max_hops": depth, "tiers": out,
                     "callers": sum(len(t) for t in tiers.values()),
                     "silent_callers": sorted(s for t in out for s in t["silent"]),
                     "meaning": "tier n = services that call this one at n hops (shortest); silent ones have not alerted yet"})


# ───────────── failure_domains ─────────────
Q_CDLP = """CALL algo.labelPropagation({nodeLabels: ['Service'], relationshipTypes: ['DEPENDS_ON'], maxIterations: 20}) YIELD node, communityId
RETURN node.id, communityId"""


def failure_domains(ctx, service_ids=None):
    rec = Recorder(ctx, "failure_domains", {"service_ids": service_ids})
    if err := _algos_on(rec):
        return rec.error(err)
    ids = None
    if service_ids is not None:
        ids, err = _alerts(rec, service_ids)
        if err:
            return rec.error(err)
    comm = dict(rec.q(Q_CDLP))
    sizes = {}
    for c in comm.values():
        sizes[c] = sizes.get(c, 0) + 1
    res = {"algorithm": "algo.labelPropagation (CDLP) over DEPENDS_ON", "communities": len(sizes),
           "sizes": sorted(sizes.values(), reverse=True)}
    if ids:
        res["services"] = [{"id": s, "community": comm.get(s), "community_size": sizes.get(comm.get(s))} for s in ids]
        res["same_community"] = len({comm.get(s) for s in ids}) == 1
        rec.hl(*ids)
    res["caveat"] = ("communities come from link density; in a hub-heavy graph they are coarse, so treat them as "
                     "context, not as proof that alerts are related")
    return rec.done(res)
