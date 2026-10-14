"""Read models for the web UI: graph elements, normalised step events, run graphs, compare numbers, Brain suggestions,
Explorer. Generic: nothing here knows the demo story (that lives in backend/demo.py).

Element shapes (what the UI renders):
  node = {id, label, name, origin, props}          edge = {source, target, type, origin, props}
Step event (replays and fresh runs alike):
  {seq, agent, action, tool, summary, args, cypher, params, queries, result_preview, ms, llm_call, mode,
   highlight {nodes[], edges[]}, cited[], writes {nodes[], edges[]}, elements {nodes[], edges[]}}
"""
import json

from backend.db import get_graph
from backend.tools.receipt import clip
from seed.schema import PREFIX_TO_LABEL

HIDDEN = {"ses", "step"}  # Session/Step nodes are the run's own bookkeeping: shown as the timeline, not as graph nodes
SOURCE_PREFIXES = {"doc", "tkt", "chat", "dec", "inc", "res", "rb", "fact", "pm"}
LONG = {"text", "rationale", "steps", "summary", "statement", "description", "symptom"}
Q_NODES = "MATCH (n) WHERE n.id IN $ids RETURN n.id, labels(n)[0], n"
Q_EDGES = "MATCH (a)-[r]->(b) WHERE a.id IN $ids AND b.id IN $ids RETURN a.id, type(r), b.id, properties(r)"
Q_NEIGHBOURS = "MATCH (a {id:$id})-[:DEPENDS_ON]-(b:Service) RETURN DISTINCT b.id"
Q_HOPS = "MATCH (a)-[r]-(b) WHERE a.id IN $ids AND NOT b:Step AND NOT b:Session RETURN DISTINCT b.id LIMIT $cap"


def visible(nid):
    return isinstance(nid, str) and ":" in nid and nid.split(":", 1)[0] in PREFIX_TO_LABEL and nid.split(":", 1)[0] not in HIDDEN


def edge_key(e):
    return f"{e['source']}|{e['type']}|{e['target']}"


def _props(p):
    out = {}
    for k, v in p.items():
        if k in ("id", "created_at"):
            continue
        out[k] = clip(v, 400 if k in LONG else 160) if isinstance(v, str) else v
    return out


def node_name(label, p):
    if label == "Deploy":
        return p.get("version") or p.get("id")
    return p.get("name") or p.get("key") or p.get("title") or clip(p.get("statement") or p.get("summary"), 60) or p.get("id")


def edge_origin(props):
    return props.get("origin") or ("agent" if props.get("source") == "learned" else "seed")


def elements(graph, ids):
    """Nodes for these ids and every edge among them, from the live graph."""
    ids = sorted({i for i in ids if visible(i)})
    if not ids:
        return {"nodes": [], "edges": []}
    nodes = []
    for nid, label, n in graph.ro_query(Q_NODES, {"ids": ids}).result_set:
        p = n.properties
        nodes.append({"id": nid, "label": label, "name": node_name(label, p), "origin": p.get("origin") or "seed",
                      "props": _props(p)})
    edges = [{"source": a, "type": t, "target": b, "origin": edge_origin(dict(pr)), "props": _props(dict(pr))}
             for a, t, b, pr in graph.ro_query(Q_EDGES, {"ids": ids}).result_set]
    return {"nodes": nodes, "edges": edges}


def hops_out(graph, ids, hops, cap=200):
    """ids plus everything within `hops` hops (Step/Session excluded)."""
    seen = {i for i in ids if visible(i)}
    frontier = set(seen)
    for _ in range(max(0, min(hops, 2))):
        if not frontier or len(seen) >= cap:
            break
        nxt = {r[0] for r in graph.ro_query(Q_HOPS, {"ids": sorted(frontier), "cap": cap}).result_set if visible(r[0])}
        frontier = nxt - seen
        seen |= frontier
    return sorted(seen)[:cap]


def subgraph(tenant, ids, hops=1):
    g = get_graph(tenant)
    return elements(g, hops_out(g, ids, hops))


# ───────────── steps → events ─────────────
def step_highlight(step):
    hl = step.get("receipt", {}).get("highlight", {})
    nodes = [n for n in hl.get("nodes", []) if visible(n)]
    edges = [{"source": e["from"], "type": e["type"], "target": e["to"]} for e in hl.get("edges", [])
             if visible(e["from"]) and visible(e["to"])]
    return nodes, edges


def _walk(obj, out):
    if isinstance(obj, dict):
        sid = obj.get("source_id") or obj.get("node_id") or obj.get("id")
        ex = obj.get("excerpt")
        if isinstance(ex, str) and isinstance(sid, str) and visible(sid):
            out.append((sid, ex))
        for v in obj.values():
            _walk(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, out)


def sources(step, names):
    """Source cards for a step: every (id, verbatim excerpt) in its args/result, plus read_source's text."""
    found = []
    _walk(step.get("args"), found)
    _walk(step.get("result"), found)
    res = step.get("result") or {}
    if step.get("tool") == "read_source" and res.get("id") and res.get("text"):
        found.append((res["id"], clip(res["text"], 320)))
    out, seen = [], set()
    for sid, ex in found:
        if sid.split(":", 1)[0] not in SOURCE_PREFIXES or (sid, ex) in seen:
            continue
        seen.add((sid, ex))
        out.append({"id": sid, "label": PREFIX_TO_LABEL[sid.split(":", 1)[0]], "title": names.get(sid) or sid, "excerpt": ex})
    return out[:8]


def step_event(step, index, written, mode):
    """index: {"nodes": {id: node}, "edges": {key: edge}} with element data. written: set of element ids/keys already
    written earlier in this run (updated here)."""
    nodes, edges = step_highlight(step)
    edges = [index["edges"].get(edge_key(e)) or {**e, "origin": "seed", "props": {}} for e in edges]
    els = {"nodes": [index["nodes"][n] for n in nodes if n in index["nodes"]], "edges": edges}
    writes = {"nodes": [], "edges": []}
    if step.get("action") == "write":
        for n in els["nodes"]:
            if n["origin"] == "agent" and n["id"] not in written:
                written.add(n["id"])
                writes["nodes"].append(n)
        for e in edges:
            if e["origin"] == "agent" and edge_key(e) not in written:
                written.add(edge_key(e))
                writes["edges"].append(e)
    queries = step.get("receipt", {}).get("queries", [])
    names = {n["id"]: n["name"] for n in index["nodes"].values()}
    result = step.get("result")
    return {k: step.get(k) for k in ("seq", "agent", "action", "tool", "summary", "args", "ms", "llm_call")} | {
        "mode": mode,
        "cypher": ";\n\n".join(q["cypher"] for q in queries),
        "params": [q["params"] for q in queries],
        "queries": queries,
        "result_preview": clip(json.dumps(result, ensure_ascii=False, default=str), 1500) if result is not None else None,
        "highlight": {"nodes": nodes, "edges": [{k: e[k] for k in ("source", "target", "type", "props")} for e in edges]},
        "cited": sources(step, names),
        "writes": writes,
        "elements": els,
    }


def index_of(els):
    return {"nodes": {n["id"]: n for n in els["nodes"]}, "edges": {edge_key(e): e for e in els["edges"]}}


# ───────────── run graphs ─────────────
def run_ids(rec):
    """Every visible node a run touches, plus the alerting service and its direct dependencies/callers."""
    ids = set()
    for s in rec.get("steps", []):
        ids |= set(step_highlight(s)[0])
    return ids


def run_graph(tenant, rec):
    """Snapshot of every node/edge any step of the run highlights or writes, plus the alert's neighbourhood. Taken
    right after the run (golden runs embed it, so replays never depend on the live graph's state)."""
    g = get_graph(tenant)
    alert = (rec.get("alert") or {}).get("service_id") or rec.get("incident_id")
    base = {alert} | {r[0] for r in g.ro_query(Q_NEIGHBOURS, {"id": alert}).result_set} if alert else set()
    ids = run_ids(rec) | base
    els = elements(g, ids)
    keep = {f"{alert}|DEPENDS_ON|{b}" for b in base} | {f"{b}|DEPENDS_ON|{alert}" for b in base}
    for s in rec.get("steps", []):
        keep |= {edge_key(e) for e in step_highlight(s)[1]}
    have = {edge_key(e) for e in els["edges"]}
    edges = [e for e in els["edges"] if edge_key(e) in keep]
    for s in rec.get("steps", []):  # highlighted but not stored (e.g. a path read the other way): keep as drawn
        for e in step_highlight(s)[1]:
            if edge_key(e) not in have and e["source"] in ids and e["target"] in ids:
                have.add(edge_key(e))
                edges.append({**e, "origin": "seed", "props": {}})
    return {"nodes": els["nodes"], "edges": edges, "base": sorted(i for i in base if visible(i)), "alert": alert}


def replay_events(rec):
    """(event, data) pairs for a recorded run, using its embedded graph snapshot."""
    graph = rec.get("graph") or {"nodes": [], "edges": []}
    index, written, agent, out = index_of(graph), set(), None, []
    for step in rec["steps"]:
        if step["agent"] != agent:
            agent = step["agent"]
            out.append(("agent", {"agent": agent}))
        out.append(("step", step_event(step, index, written, "replay")))
        if step["action"] == "handoff":
            out.append(("handoff", {"agent": step["agent"], "note": step["summary"], "seq": step["seq"]}))
    return out


class LiveIndex:
    """Element data for a fresh run, fetched from the graph as each step lands (the run is writing it)."""

    def __init__(self, tenant):
        self.graph, self.written = get_graph(tenant), set()

    def event(self, step, mode):
        nodes, edges = step_highlight(step)
        return step_event(step, index_of(elements(self.graph, nodes + [x for e in edges for x in (e["source"], e["target"])])),
                          self.written, mode)


# ───────────── compare ─────────────
def recalled(rec):
    """The first incident memory_recall brought back in this run, if any."""
    for s in rec.get("steps", []):
        if s["tool"] == "memory_recall":
            inc = next(iter((s.get("result") or {}).get("incidents") or []), None)
            if inc:
                return {"id": inc["id"], "key": inc.get("key"),
                        "fixed_by": [p["name"] for p in inc.get("resolved_by", [])],
                        "fix": (inc.get("resolution") or {}).get("summary")}
    return None


def compare_column(key, title, rec, source):
    t, rep = rec.get("time_to_cause"), rec.get("report") or {}
    cause = (rep.get("likely_cause") or {})
    found = bool(t) and bool(cause.get("deploy_id") or cause.get("service_id"))
    return {"key": key, "title": title, "source": source, "alert_service": (rec.get("alert") or {}).get("service_id"),
            "incident": rec.get("incident_key"), "cause_found": found,
            "cause": cause.get("deploy_id") or cause.get("service_id") if found else None,
            "investigator_tool_calls_until_cause": t["agent_tool_calls"] if found else None,
            "tool_calls_until_cause": t["tool_calls"] if found else None,
            "llm_calls_until_cause": t["llm_calls"] if found else None,
            "llm_calls_total": (rec.get("totals") or {}).get("llm_calls"),
            "recalled_incident": recalled(rec), "contact": (rep.get("contact") or {}).get("name"),
            "industry_match": rep.get("industry_pattern"), "confidence": rep.get("confidence")}


# ───────────── Brain suggestions ─────────────
Q_TOP_PR = """CALL algo.pageRank('Service', 'DEPENDS_ON') YIELD node, score
RETURN node.name, score ORDER BY score DESC, node.name LIMIT 1"""
Q_DECISION = """MATCH (dep:Deploy)-[:CHANGED]->(:Service)<-[:ABOUT]-(d:Decision)
RETURN d.title, dep.ts ORDER BY dep.ts DESC, d.title LIMIT 1"""
Q_DEPARTED = """MATCH (p:Person {status:'left'})-[:MAINTAINS]->(s:Service)
OPTIONAL MATCH (i:Incident)-[:AFFECTED]->(s)
RETURN p.name, s.name, count(i) AS n ORDER BY n DESC, s.name LIMIT 1"""
Q_STALE_DOC = """MATCH (d:Doc)-[:DESCRIBES]->(s:Service), (a:Person {status:'left'})-[:AUTHORED]->(d)
RETURN s.name, d.updated_at ORDER BY d.updated_at, s.name LIMIT 1"""
Q_TEAM = """MATCH (t:Team), (d:Doc) WHERE d.title CONTAINS t.name
RETURN t.name, count(d) AS n ORDER BY n DESC, t.name LIMIT 1"""
Q_RC = """MATCH (i:Incident)-[:HAS_ROOT_CAUSE]->(rc:RootCause)<-[:HAS_ROOT_CAUSE]-(:PublicPostmortem)
RETURN rc.name, count(DISTINCT i) AS n ORDER BY n DESC, rc.name LIMIT 1"""


def _one(g, q):
    rows = g.ro_query(q).result_set
    return rows[0] if rows else None


def pattern_words(name):
    """'Cache TTL too low → thundering herd on a shared config store' -> 'thundering herd'; 'Retry storm' -> 'retry storm'."""
    words = name.split("→")[-1].split()
    return " ".join(words[:2] if "→" in name or len(words) > 3 else words).lower()


def suggestions(tenant):
    """Six questions built from templates; every value comes from a Cypher query on this tenant's graph."""
    g, out, extra = get_graph(tenant), [], []
    if r := _one(g, Q_DECISION):  # the decision behind the most recently changed service
        out.append({"kind": "why", "question": f"Why did we decide that {r[0]}?"})
    if r := _one(g, Q_DEPARTED):
        out.append({"kind": "who", "question": f"{r[0].split()[0]} left. Who knows {r[1]} best now?"})
    if r := _one(g, Q_TOP_PR):
        out.append({"kind": "blast", "question": f"What breaks if {r[0]} fails?"})
        extra.append({"kind": "owner", "question": f"Who owns {r[0]}?"})
    if r := _one(g, Q_STALE_DOC):
        out.append({"kind": "stale", "question": f"Which docs about {r[0]} are out of date, and why?"})
    if r := _one(g, Q_RC):
        out.append({"kind": "industry", "question": f"Has any other company had a {pattern_words(r[0])} outage like ours?"})
    if r := _one(g, Q_TEAM):
        out.append({"kind": "onboarding", "question": f"I'm new on {r[0]}. What should I read first?"})
    out += extra
    return out[:6]


# ───────────── Explorer ─────────────
EXPLORER_DEFAULT = ["Service", "Team", "Person"]
EXPLORER_CAP, EXPLORER_EDGE_CAP = 400, 2000
Q_EXPLORER_NODES = """MATCH (n) WHERE labels(n)[0] IN $labels AND ($origin IS NULL OR n.origin = $origin)
RETURN n.id, labels(n)[0], n ORDER BY n.id LIMIT $cap"""
Q_EXPLORER_AGENT_EDGES = """MATCH (a)-[r]->(b) WHERE (r.origin = 'agent' OR r.source = 'learned') AND NOT a:Step AND NOT a:Session
AND NOT b:Step AND NOT b:Session RETURN a.id, b.id LIMIT $cap"""
Q_PAGERANK_ALL = "CALL algo.pageRank('Service', 'DEPENDS_ON') YIELD node, score RETURN node.id, score"
Q_COUNTS = "MATCH (n) WHERE NOT n:Step AND NOT n:Session RETURN labels(n)[0], n.origin, count(n)"


def explorer(tenant, labels=None, origin=None):
    """Tenant graph for the Explorer: chosen labels (default services, teams, people), optionally agent memory only
    (then every agent-written node and the endpoints of agent-written edges), PageRank on services for sizing."""
    g = get_graph(tenant)
    labels = [l for l in (labels or EXPLORER_DEFAULT) if l in PREFIX_TO_LABEL.values() and l not in ("Step", "Session")]
    if origin == "agent":
        ids = {r[0] for r in g.ro_query(Q_EXPLORER_NODES, {"labels": [l for l in PREFIX_TO_LABEL.values() if l not in ("Step", "Session")],
                                                          "origin": "agent", "cap": EXPLORER_CAP}).result_set}
        for a, b in g.ro_query(Q_EXPLORER_AGENT_EDGES, {"cap": EXPLORER_EDGE_CAP}).result_set:
            ids |= {a, b}
    else:
        ids = {r[0] for r in g.ro_query(Q_EXPLORER_NODES, {"labels": labels, "origin": None, "cap": EXPLORER_CAP}).result_set}
    els = elements(g, list(ids)[:EXPLORER_CAP])
    if origin == "agent":  # only the memory: agent-written edges, nodes that touch them
        els["edges"] = [e for e in els["edges"] if e["origin"] == "agent"]
    pr = {nid: round(score, 5) for nid, score in g.ro_query(Q_PAGERANK_ALL).result_set}
    for n in els["nodes"]:
        if n["id"] in pr:
            n["pagerank"] = pr[n["id"]]
    counts = {}
    for label, org, n in g.ro_query(Q_COUNTS).result_set:
        counts.setdefault(label, {"seed": 0, "agent": 0})[org or "seed"] = n
    agent_total = sum(c["agent"] for c in counts.values())
    return {"tenant": tenant, "labels": labels, "origin": origin, **els, "counts": counts, "agent_nodes": agent_total,
            "agent_edges": g.ro_query("MATCH ()-[r]->() WHERE r.origin = 'agent' OR r.source = 'learned' RETURN count(r)").result_set[0][0],
            "truncated": len(ids) > EXPLORER_CAP, "pagerank": "algo.pageRank('Service', 'DEPENDS_ON')"}
