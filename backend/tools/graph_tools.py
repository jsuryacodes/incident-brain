"""The fixed, parameterised, read-only graph tools.  fn(ctx, **args) -> ToolOutput.

Every query goes through Recorder.q -> graph.ro_query. Variable-length bounds cannot be parameters, so the only
interpolation is `__N__`, replaced by an int clamped to 1..6. Query text lives in module constants (Q_*) so that
registry.py / export_docs.py can print exactly what runs.

FalkorDB quirk: a MATCH placed *after* `WITH ... aggregate` can silently return no rows. So every aggregation
(min(length(p)), collect, count) is the last step in its query (in RETURN), and all MATCHes come before it.
"""
import json
import re

from backend.tools.receipt import Recorder, clamp, clip, days_ago, iso, minutes_ago
from seed.schema import PREFIX_TO_LABEL

MAX_HOPS = 6


def _n(q, hops):
    return q.replace("__N__", str(hops))


def _deploy(now, did, version, ts, summary, by):
    return {"id": did, "version": version, "ts": ts, "minutes_ago": minutes_ago(now, ts),
            "summary": clip(summary, 160), "by": by}


# ───────────── 1. find_service ─────────────
Q_FIND = """MATCH (s:Service)<-[:OWNS]-(t:Team)
WHERE toLower(s.name) CONTAINS $q OR toLower(s.id) CONTAINS $q
RETURN s.id, s.name, s.tier, t.name"""
Q_FIND_TOKENS = """MATCH (s:Service)<-[:OWNS]-(t:Team)
WHERE all(tok IN $tokens WHERE toLower(s.name) CONTAINS tok OR toLower(s.description) CONTAINS tok)
RETURN s.id, s.name, s.tier, t.name"""


def find_service(ctx, query=""):
    rec = Recorder(ctx, "find_service", {"query": query})
    q = re.sub(r"[\s_]+", "-", str(query).strip().lower())
    if not q:
        return rec.error("query is empty; pass a service name such as 'payments api'")
    rows = rec.q(Q_FIND, {"q": q})
    if not rows:
        tokens = re.findall(r"[a-z0-9]+", q)
        rows = rec.q(Q_FIND_TOKENS, {"tokens": tokens}) if tokens else []
    rows.sort(key=lambda r: (0 if r[1] == q else 1 if r[1].startswith(q) else 2, r[1]))
    matches = [{"id": r[0], "name": r[1], "tier": r[2], "team": r[3]} for r in rows[:5]]
    rec.hl(*[m["id"] for m in matches])
    res = {"query": query, "matches": matches}
    if not matches:
        res["note"] = "no service matched; try fewer or different words"
    return rec.done(res)


# ───────────── 2. blast_radius ─────────────
Q_BLAST = """MATCH p=(s:Service {id:$id})<-[:DEPENDS_ON*1..__N__]-(up:Service)
MATCH (t:Team)-[:OWNS]->(up)
RETURN up.id, up.tier, t.name, min(length(p)) AS hops
ORDER BY up.tier, hops, up.id"""
Q_BLAST_EDGES = """MATCH p=(s:Service {id:$id})<-[:DEPENDS_ON*1..__N__]-(up:Service)
UNWIND relationships(p) AS r
RETURN DISTINCT startNode(r).id, endNode(r).id, r.source"""


def blast_radius(ctx, service_id, max_hops=4):
    rec = Recorder(ctx, "blast_radius", {"service_id": service_id, "max_hops": max_hops})
    if err := rec.check(service_id, "Service"):
        return rec.error(err)
    n = clamp(max_hops, 1, MAX_HOPS, 4)
    rows = rec.q(_n(Q_BLAST, n), {"id": service_id})
    edges = rec.q(_n(Q_BLAST_EDGES, n), {"id": service_id})
    for a, b, _ in edges:
        rec.hl_edge(a, "DEPENDS_ON", b)
    rec.hl(service_id, *[r[0] for r in rows])
    res = {"service": service_id, "max_hops": n, "upstream_count": len(rows),
           "tier1_count": sum(1 for r in rows if r[1] == 1),
           "upstream": [{"id": r[0], "tier": r[1], "team": r[2], "hops": r[3]} for r in rows[:22]]}
    if len(rows) > 22:
        res["truncated"] = True
    learned = [{"from": a, "to": b} for a, b, src in edges if src == "learned"]
    if learned:
        res["learned_edges_in_paths"] = learned
    return rec.done(res)


# ───────────── 3. recent_changes_downstream ─────────────
Q_RECENT = """MATCH p=(s:Service {id:$id})-[:DEPENDS_ON*1..__N__]->(d:Service)
MATCH (d)<-[:CHANGED]-(dep:Deploy) WHERE dep.ts > $since
OPTIONAL MATCH (who:Person)-[:DEPLOYED]->(dep)
OPTIONAL MATCH (dep)-[:FOR_TICKET]->(t:Ticket)
RETURN d.id, min(length(p)) AS hops, dep.id, dep.version, dep.ts, dep.summary, who.id, who.name, t.id, t.key, t.title
ORDER BY hops, dep.ts DESC"""
# algo.SPpaths: shortest DEPENDS_ON path; $dir is one of outgoing / incoming / both
Q_SP = """MATCH (a:Service {id:$from}), (b:Service {id:$to})
CALL algo.SPpaths({sourceNode: a, targetNode: b, relTypes: ['DEPENDS_ON'], relDirection: $dir, maxLen: $maxlen}) YIELD path
RETURN [x IN nodes(path) | x.id], [r IN relationships(path) | r.source], [r IN relationships(path) | startNode(r).id], [r IN relationships(path) | r.kind]"""


def _sp(rec, a, b, direction, maxlen):
    rows = rec.q(Q_SP, {"from": a, "to": b, "dir": direction, "maxlen": maxlen})
    if not rows:
        return None
    ids, sources, starts, kinds = rows[0]
    return {"ids": ids, "sources": sources, "starts": starts, "kinds": kinds}


def recent_changes_downstream(ctx, service_id, since_minutes=120, max_hops=4):
    rec = Recorder(ctx, "recent_changes_downstream",
                   {"service_id": service_id, "since_minutes": since_minutes, "max_hops": max_hops})
    if err := rec.check(service_id, "Service"):
        return rec.error(err)
    n = clamp(max_hops, 1, MAX_HOPS, 4)
    mins = clamp(since_minutes, 1, 60 * 24 * 365, 120)
    rows = rec.q(_n(Q_RECENT, n), {"id": service_id, "since": ctx.now - mins * 60})
    hits = []
    for svc, hops, did, ver, ts, summ, wid, wname, tid, tkey, ttitle in rows[:6]:
        sp = _sp(rec, service_id, svc, "outgoing", n)
        ids, sources = (sp["ids"], sp["sources"]) if sp else ([service_id, svc], [])
        rec.hl_path(ids)
        rec.hl_edge(did, "CHANGED", svc)
        if wid:
            rec.hl_edge(wid, "DEPLOYED", did)
        if tid:
            rec.hl_edge(did, "FOR_TICKET", tid)
        hits.append({"service": svc, "hops": hops, "path": ids, "edge_sources": sources,
                     "deploy": _deploy(ctx.now, did, ver, ts, summ, wname),
                     "ticket": {"key": tkey, "title": clip(ttitle, 100)} if tkey else None})
    res = {"service": service_id, "since_minutes": mins, "hit_count": len(rows), "hits": hits}
    if len(rows) > 6:
        res["truncated"] = True
    if not rows:
        res["note"] = "no downstream service was deployed in this window"
    return rec.done(res)


# ───────────── 4. shared_dependency_changes ─────────────
Q_DOWNSTREAM = """MATCH (s:Service {id:$id})-[:DEPENDS_ON*1..6]->(x:Service) RETURN DISTINCT x.id"""
Q_SHARED = """MATCH p1=(s:Service {id:$id})-[:DEPENDS_ON*1..__N__]->(shared:Service),
      p2=(shared)<-[:DEPENDS_ON*1..__N__]-(n:Service)
MATCH (n)<-[:CHANGED]-(d:Deploy)
WHERE d.ts > $since AND n.id <> $id AND NOT n.id IN $downstream
OPTIONAL MATCH (who:Person)-[:DEPLOYED]->(d)
OPTIONAL MATCH (d)-[:FOR_TICKET]->(t:Ticket)
RETURN n.id, shared.id, d.id, d.version, d.ts, d.summary, who.id, who.name, t.id, t.key, t.title,
       [x IN nodes(p1) | x.id], [r IN relationships(p1) | r.source],
       [x IN nodes(p2) | x.id], [r IN relationships(p2) | r.source],
       [r IN relationships(p1) + relationships(p2) WHERE r.learned_from IS NOT NULL | r.learned_from]
ORDER BY length(p1) + length(p2), d.ts DESC
LIMIT 60"""


def shared_dependency_changes(ctx, service_id, since_minutes=1440, max_hops=3):
    rec = Recorder(ctx, "shared_dependency_changes",
                   {"service_id": service_id, "since_minutes": since_minutes, "max_hops": max_hops})
    if err := rec.check(service_id, "Service"):
        return rec.error(err)
    n = clamp(max_hops, 1, MAX_HOPS, 3)
    mins = clamp(since_minutes, 1, 60 * 24 * 365, 1440)
    down = [r[0] for r in rec.q(Q_DOWNSTREAM, {"id": service_id})]
    rows = rec.q(_n(Q_SHARED, n), {"id": service_id, "since": ctx.now - mins * 60, "downstream": down})
    best = {}  # (neighbour, deploy) -> best row; also collect the other shared services
    for r in rows:
        key = (r[0], r[2])
        total = len(r[12]) + len(r[14])
        if key not in best:
            best[key] = {"row": r, "total": total, "others": []}
        elif r[1] != best[key]["row"][1] and r[1] not in best[key]["others"]:
            best[key]["others"].append(r[1])
    hits = []
    for (nb, did), b in sorted(best.items(), key=lambda kv: (kv[1]["total"], -kv[1]["row"][4]))[:5]:
        (_, shared, _, ver, ts, summ, wid, wname, tid, tkey, ttitle, p1, s1, p2, s2, facts) = b["row"]
        p2, s2 = p2[::-1], s2[::-1]  # neighbour -> shared
        rec.hl_path(p1)
        rec.hl_path(p2)
        rec.hl_edge(did, "CHANGED", nb)
        if wid:
            rec.hl_edge(wid, "DEPLOYED", did)
        if tid:
            rec.hl_edge(did, "FOR_TICKET", tid)
        hit = {"neighbour": nb, "shared": shared, "deploy": _deploy(ctx.now, did, ver, ts, summ, wname),
               "ticket": {"key": tkey, "title": clip(ttitle, 100)} if tkey else None,
               "path_to_shared": p1, "path_to_shared_sources": s1,
               "neighbour_path": p2, "neighbour_path_sources": s2,
               "uses_learned_edge": "learned" in s1 + s2}
        if facts:
            hit["learned_facts"] = sorted(set(facts))
        if b["others"]:
            hit["also_shares"] = b["others"][:3]
        hits.append(hit)
    res = {"service": service_id, "since_minutes": mins, "hit_count": len(best), "hits": hits}
    if len(best) > 5:
        res["truncated"] = True
    if not hits:
        res["note"] = "no recently changed service shares a downstream dependency with this one"
    return rec.done(res)


# ───────────── 5. dependency_path ─────────────
def dependency_path(ctx, from_id, to_id):
    rec = Recorder(ctx, "dependency_path", {"from_id": from_id, "to_id": to_id})
    for i in (from_id, to_id):
        if err := rec.check(i, "Service"):
            return rec.error(err)
    for direction in ("outgoing", "incoming", "both"):
        sp = _sp(rec, from_id, to_id, direction, MAX_HOPS)
        if sp:
            break
    else:
        return rec.done({"from": from_id, "to": to_id, "found": False, "tried": ["outgoing", "incoming", "both"],
                         "note": f"no DEPENDS_ON path within {MAX_HOPS} hops in any direction"})
    ids, hops = sp["ids"], []
    for i, (src, start) in enumerate(zip(sp["sources"], sp["starts"])):
        a, b = ids[i], ids[i + 1]
        caller, callee = (a, b) if start == a else (b, a)
        rec.hl_edge(caller, "DEPENDS_ON", callee)
        hops.append({"caller": caller, "callee": callee, "source": src, "kind": sp["kinds"][i]})
    rec.hl(*ids)
    return rec.done({"from": from_id, "to": to_id, "found": True, "direction_matched": direction,
                     "length": len(hops), "nodes": ids, "hops": hops})


# ───────────── 6. who_to_call ─────────────
Q_MAINT = "MATCH (p:Person)-[:MAINTAINS]->(s:Service {id:$id}) RETURN p.id, p.name, p.status, p.left_at"
Q_WORKERS = """MATCH (p:Person {status:'active'})-[w:WORKED_ON]->(s:Service {id:$id})
RETURN p.id, p.name, p.role, w.commits, w.last_at"""
Q_RES_AFFECTED = """MATCH (s:Service {id:$id})<-[:AFFECTED]-(i:Incident)-[:RESOLVED_BY]->(r:Resolution)-[:PERFORMED_BY]->(p:Person {status:'active'})
RETURN p.id, p.name, p.role, collect(DISTINCT r.id)"""
Q_RES_DEPLOY = """MATCH (s:Service {id:$id})<-[:CHANGED]-(:Deploy)<-[:CAUSED_BY]-(i:Incident)-[:RESOLVED_BY]->(r:Resolution)-[:PERFORMED_BY]->(p:Person {status:'active'})
RETURN p.id, p.name, p.role, collect(DISTINCT r.id)"""
Q_TEAM = """MATCH (t:Team)-[:OWNS]->(s:Service {id:$id})
OPTIONAL MATCH (m:Person {status:'active'})-[:MEMBER_OF]->(t)
RETURN t.id, t.name, collect(m.name)"""


def who_to_call(ctx, service_id):
    rec = Recorder(ctx, "who_to_call", {"service_id": service_id})
    if err := rec.check(service_id, "Service"):
        return rec.error(err)
    p = {"id": service_id}
    maint = rec.q(Q_MAINT, p)
    workers = rec.q(Q_WORKERS, p)
    cand = {}  # person id -> dict
    for pid, name, role, commits, last_at in workers:
        cand[pid] = {"id": pid, "name": name, "role": role, "commits": commits,
                     "last_commit_days_ago": days_ago(ctx.now, last_at), "_res": set()}
        rec.hl_edge(pid, "WORKED_ON", service_id)
    for q in (Q_RES_AFFECTED, Q_RES_DEPLOY):
        for pid, name, role, rids in rec.q(q, p):
            c = cand.setdefault(pid, {"id": pid, "name": name, "role": role, "commits": 0,
                                      "last_commit_days_ago": None, "_res": set()})
            c["_res"].update(rids)
    for c in cand.values():
        c["resolutions"] = len(c.pop("_res"))
        c["score"] = c["commits"] + 25 * c["resolutions"]
    ranked = sorted(cand.values(), key=lambda c: (-c["score"], c["last_commit_days_ago"] or 9999))
    maintainers = [{"id": i, "name": nm, "status": st, "left_days_ago": days_ago(ctx.now, left)} for i, nm, st, left in maint]
    for m in maintainers:
        rec.hl_edge(m["id"], "MAINTAINS", service_id)
    active_workers = len(workers)
    reasons = [f"maintainer {m['name']} has left" for m in maintainers if m["status"] == "left"]
    if active_workers <= 1:
        reasons.append(f"only {active_workers} active person has worked on this service")
    team = rec.q(Q_TEAM, p)
    team_out = None
    if team:
        tid, tname, members = team[0]
        rec.hl_edge(tid, "OWNS", service_id)
        team_out = {"id": tid, "name": tname, "active_members": members[:6]}
    res = {"service": service_id, "maintainers": maintainers, "bus_factor_risk": bool(reasons),
           "bus_factor_reasons": reasons, "score_formula": "commits + 25 * resolutions",
           "candidates": ranked[:5], "owning_team_fallback": team_out}
    rec.hl(*[c["id"] for c in ranked[:5]])
    return rec.done(res)


# ───────────── 7. decisions_about ─────────────
Q_DECISIONS = """MATCH (d:Decision)-[:ABOUT]->(s:Service {id:$id})
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(d)
OPTIONAL MATCH (d)-[r:SOURCED_FROM]->(src)
RETURN d.id, d.title, d.rationale, d.decided_at, a.id, a.name, a.status,
       src.id, labels(src)[0], coalesce(src.title, src.key), src.channel,
       coalesce(src.ts, src.updated_at, src.created_at, src.started_at), r.excerpt
ORDER BY d.decided_at DESC"""


def decisions_about(ctx, service_id):
    rec = Recorder(ctx, "decisions_about", {"service_id": service_id})
    if err := rec.check(service_id, "Service"):
        return rec.error(err)
    out = {}
    for did, title, why, at, aid, aname, astat, sid, slabel, stitle, chan, sdate, exc in rec.q(Q_DECISIONS, {"id": service_id}):
        d = out.setdefault(did, {"id": did, "title": title, "rationale": clip(why, 200), "decided": iso(at),
                                 "decided_days_ago": days_ago(ctx.now, at), "author": aname, "author_status": astat,
                                 "sources": []})
        rec.hl_edge(did, "ABOUT", service_id)
        if aid:
            rec.hl_edge(aid, "AUTHORED", did)
        if sid:
            rec.hl_edge(did, "SOURCED_FROM", sid)
            d["sources"].append({"id": sid, "label": slabel, "title": clip(stitle, 80), "channel": chan,
                                 "date": iso(sdate), "excerpt": clip(exc, 220)})
    res = {"service": service_id, "decisions": list(out.values())}
    if not out:
        res["note"] = "no recorded decisions about this service"
    return rec.done(res)


# ───────────── 8. past_incidents ─────────────
Q_INC_AFFECTED = """MATCH (i:Incident)-[:AFFECTED]->(s:Service) WHERE s.id IN $ids
RETURN DISTINCT i.id, s.id"""
Q_INC_DEPLOY = """MATCH (i:Incident)-[:CAUSED_BY]->(dep:Deploy)-[:CHANGED]->(s:Service) WHERE s.id IN $ids
RETURN DISTINCT i.id, s.id, dep.id"""
Q_INC_DETAIL = """MATCH (i:Incident) WHERE i.id IN $iids
OPTIONAL MATCH (i)-[:HAS_ROOT_CAUSE]->(rc:RootCause)
OPTIONAL MATCH (i)-[:RESOLVED_BY]->(r:Resolution)
OPTIONAL MATCH (r)-[:PERFORMED_BY]->(p:Person)
OPTIONAL MATCH (r)-[:SOURCED_FROM]->(src)
OPTIONAL MATCH (i)-[sim:SIMILAR_TO]-(o)
OPTIONAL MATCH (rb:Runbook)-[:SOURCED_FROM]->(i)
RETURN i.id, i.key, i.title, i.severity, i.started_at, i.origin, i.status,
       collect(DISTINCT rc.id), collect(DISTINCT r.id), collect(DISTINCT r.summary), collect(DISTINCT p.id),
       collect(DISTINCT p.name), collect(DISTINCT src.id), collect(DISTINCT {id: o.id, score: sim.score}),
       collect(DISTINCT rb.id)"""


def past_incidents(ctx, service_ids, limit=5):
    rec = Recorder(ctx, "past_incidents", {"service_ids": service_ids, "limit": limit})
    if isinstance(service_ids, str):
        service_ids = [service_ids]
    if not isinstance(service_ids, list) or not service_ids or not all(isinstance(s, str) for s in service_ids):
        return rec.error("service_ids must be a non-empty list of service ids; try find_service")
    service_ids = service_ids[:10]
    for s in service_ids:
        if err := rec.check(s, "Service"):
            return rec.error(err)
    limit = clamp(limit, 1, 10, 5)
    found = {}  # incident id -> {services, via, edges to highlight}
    for q, via in ((Q_INC_AFFECTED, "affected"), (Q_INC_DEPLOY, "caused_by_deploy")):
        for iid, sid, *dep in rec.q(q, {"ids": service_ids}):
            f = found.setdefault(iid, {"services": set(), "via": set(), "edges": [], "caused": set()})
            f["services"].add(sid)
            f["via"].add(via)
            if dep:
                f["caused"].add(sid)
            f["edges"] += [(iid, "AFFECTED", sid)] if not dep else [(iid, "CAUSED_BY", dep[0]), (dep[0], "CHANGED", sid)]
    details = {r[0]: r for r in rec.q(Q_INC_DETAIL, {"iids": list(found)})} if found else {}
    ranked = sorted(details.values(), key=lambda r: (-len(found[r[0]]["services"]), -(r[4] or 0)))[:limit]
    out = []
    for iid, key, title, sev, started, origin, status, rcs, rids, rsums, pids, pnames, srcs, sims, rbs in ranked:
        f = found[iid]
        rec.hl(iid, *rcs)
        for e in f["edges"]:
            rec.hl_edge(*e)
        for rc in rcs:
            rec.hl_edge(iid, "HAS_ROOT_CAUSE", rc)
        for r in rids:
            rec.hl_edge(iid, "RESOLVED_BY", r)
            for pid in pids:
                rec.hl_edge(r, "PERFORMED_BY", pid)
            for src in srcs:
                rec.hl_edge(r, "SOURCED_FROM", src)
        similar = [{"id": s["id"], "score": s["score"]} for s in sims if s["id"]]
        for s in similar:
            rec.hl_edge(iid, "SIMILAR_TO", s["id"])
        out.append({"id": iid, "key": key, "title": clip(title, 90), "severity": sev, "started": iso(started),
                    "origin": origin, "status": status, "overlap": len(f["services"]), "via": sorted(f["via"]),
                    "caused_by_change_to": sorted(f["caused"]),
                    "root_causes": rcs, "resolution": clip(rsums[0], 120) if rsums else None,
                    "resolved_by": pnames, "resolution_sources": srcs, "similar_to": similar,
                    **({"runbooks": sorted(rbs)} if rbs else {})})
        for rb in rbs:
            rec.hl_edge(rb, "SOURCED_FROM", iid)
    res = {"service_ids": service_ids, "incident_count": len(found), "incidents": out}
    if len(found) > len(out):
        res["truncated"] = True
    if not found:
        res["note"] = "no past incidents touched these services"
    return rec.done(res)


# ───────────── 9. search_knowledge ─────────────
DEFAULT_SEARCH = ["Doc", "Ticket", "ChatThread", "Decision", "Incident", "Runbook"]
SEARCH_LABELS = DEFAULT_SEARCH + ["RootCause", "PublicPostmortem"]  # the last two only when asked for (labels)
_SOURCE_PREF = ["ChatThread", "Doc", "Ticket", "Runbook", "Decision", "Incident", "RootCause", "PublicPostmortem"]
Q_SEARCH = """CALL db.idx.fulltext.queryNodes($label, $q) YIELD node, score
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(node)
RETURN node.id, score, coalesce(node.title, node.key, node.name), coalesce(node.text, node.rationale, node.summary, node.steps, node.description),
       coalesce(node.ts, node.updated_at, node.decided_at, node.started_at, node.created_at), a.name, a.status
ORDER BY score DESC LIMIT $limit"""
_STOP = {"the", "a", "an", "of", "to", "in", "on", "and", "or", "is", "are", "was", "we", "why", "did", "do", "how", "what", "for", "it"}


def _snippet(text, tokens, n=200):
    text = " ".join((text or "").split())
    low = text.lower()
    pos = min((p for p in (low.find(t) for t in tokens) if p >= 0), default=0)
    start = max(0, pos - 60)
    return ("…" if start else "") + clip(text[start:], n)


def search_knowledge(ctx, query="", labels=None, limit=8):
    rec = Recorder(ctx, "search_knowledge", {"query": query, "labels": labels, "limit": limit})
    labels = labels or DEFAULT_SEARCH
    bad = [l for l in labels if l not in SEARCH_LABELS] if isinstance(labels, list) else labels
    if bad:
        return rec.error(f"labels must be a subset of {SEARCH_LABELS}")
    tokens = [t for t in re.findall(r"[A-Za-z0-9_]+", str(query).lower()) if len(t) > 1 and t not in _STOP][:8]
    if not tokens:
        return rec.error("query has no searchable words")
    limit = clamp(limit, 1, 20, 8)
    hits = {}
    for label in labels:
        # all words first (precise); if that leaves room, any word (recall) ranked below.
        # Scores from different indexes are not comparable, so each index is normalised to its own best hit.
        for q, weight in ((" ".join(tokens), 1.0), ("|".join(tokens), 0.1)):
            rows = rec.q(Q_SEARCH, {"label": label, "q": q, "limit": limit})
            top = max((r[1] for r in rows), default=1) or 1
            for nid, score, title, text, date, aname, astat in rows:
                if nid not in hits:
                    hits[nid] = {"id": nid, "label": label, "title": clip(title, 90), "snippet": _snippet(text, tokens),
                                 "date": iso(date), "author": aname, "author_status": astat,
                                 "score": round(weight * score / top, 3)}
            if sum(1 for h in hits.values() if h["label"] == label) >= limit:
                break
    # ties (every index's best hit scores 1.0): raw sources before derived summaries
    ranked = sorted(hits.values(), key=lambda h: (-h["score"], _SOURCE_PREF.index(h["label"])))[:limit]
    rec.hl(*[h["id"] for h in ranked])
    return rec.done({"query": query, "terms": tokens, "hit_count": len(hits), "hits": ranked,
                     **({"truncated": True} if len(hits) > limit else {})})


# ───────────── 10. critical_services ─────────────
Q_PAGERANK = """CALL algo.pageRank('Service', 'DEPENDS_ON') YIELD node, score
MATCH (t:Team)-[:OWNS]->(node)
RETURN node.id, node.name, node.tier, t.name, score ORDER BY score DESC LIMIT $limit"""
Q_BETWEENNESS = """CALL algo.betweenness({nodeLabels: ['Service'], relationshipTypes: ['DEPENDS_ON'], samplingSize: 64, samplingSeed: 42}) YIELD node, score
MATCH (t:Team)-[:OWNS]->(node)
RETURN node.id, node.name, node.tier, t.name, score ORDER BY score DESC LIMIT $limit"""


def critical_services(ctx, algorithm="pagerank", limit=8):
    rec = Recorder(ctx, "critical_services", {"algorithm": algorithm, "limit": limit})
    if algorithm not in ("pagerank", "betweenness"):
        return rec.error("algorithm must be 'pagerank' or 'betweenness'")
    limit = clamp(limit, 1, 27, 8)
    q = Q_PAGERANK if algorithm == "pagerank" else Q_BETWEENNESS
    rows = rec.q(q, {"limit": limit})
    rec.hl(*[r[0] for r in rows])
    meaning = ("shared dependencies: services many others call, directly or indirectly" if algorithm == "pagerank"
               else "chokepoints: services that sit on many shortest call paths")
    return rec.done({"algorithm": algorithm, "meaning": meaning,
                     "services": [{"id": r[0], "name": r[1], "tier": r[2], "team": r[3], "score": round(r[4], 4)} for r in rows]})


# ───────────── 11. stale_knowledge ─────────────
Q_STALE = """MATCH (x)-[:DESCRIBES]->(s:Service)
WHERE (x:Doc OR x:Runbook) AND ($sid IS NULL OR s.id = $sid)
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(x)
OPTIONAL MATCH (x)-[:MENTIONS]->(gone:Person {status: 'left'})
OPTIONAL MATCH (dp:Deploy)-[:CHANGED]->(s) WHERE dp.ts > x.updated_at
OPTIONAL MATCH (s)-[l:DEPENDS_ON {source: 'learned'}]->(t:Service) WHERE l.learned_at > x.updated_at
RETURN x.id, labels(x)[0], x.title, x.updated_at, s.id, a.id, a.name, a.status, coalesce(x.flagged_stale, false),
       collect(DISTINCT gone.name), collect(DISTINCT gone.id), count(DISTINCT dp), collect(DISTINCT t.id)
ORDER BY x.updated_at"""


def stale_knowledge(ctx, service_id=None):
    rec = Recorder(ctx, "stale_knowledge", {"service_id": service_id})
    if service_id is not None and (err := rec.check(service_id, "Service")):
        return rec.error(err)
    items = []
    for xid, label, title, upd, sid, aid, aname, astat, flagged, gone, gone_ids, deploys, learned in rec.q(Q_STALE, {"sid": service_id}):
        reasons, detail = [], {}
        if astat == "left":
            reasons.append("author_left")
            detail["author"] = aname
        if gone:
            reasons.append("names_departed_person")
            detail["departed_people"] = gone
        if days_ago(ctx.now, upd) > 365 and deploys > 0:
            reasons.append("old_vs_changes")
            detail["deploys_since_update"] = deploys
        if learned:
            reasons.append("missing_learned_dependency")
            detail["learned_dependencies"] = learned
        if not reasons:
            continue
        rec.hl_edge(xid, "DESCRIBES", sid)
        if aid and astat == "left":
            rec.hl_edge(aid, "AUTHORED", xid)
        for g in gone_ids:
            rec.hl_edge(xid, "MENTIONS", g)
        for t in learned:
            rec.hl_edge(sid, "DEPENDS_ON", t)
        items.append({"id": xid, "kind": label, "title": clip(title, 80), "describes": sid,
                      "updated": iso(upd), "updated_days_ago": days_ago(ctx.now, upd), "flagged": flagged,
                      "reasons": reasons, **detail})
    res = {"service": service_id, "stale_count": len(items), "items": items[:10]}
    if len(items) > 10:
        res["truncated"] = True
    return rec.done(res)


# ───────────── 12. node_details ─────────────
Q_NODE = "MATCH (n:__LABEL__ {id: $id}) RETURN n"
Q_NEIGHBOURS = """MATCH (n:__LABEL__ {id: $id})-[r]-(m)
RETURN type(r), startNode(r).id = n.id, m.id, coalesce(m.name, m.title, m.key, m.summary, m.statement)
LIMIT 300"""
_SKIP_PROPS = {"id", "created_at"}


def node_details(ctx, node_id):
    rec = Recorder(ctx, "node_details", {"node_id": node_id})
    prefix = node_id.split(":", 1)[0] if isinstance(node_id, str) and ":" in node_id else None
    if prefix not in PREFIX_TO_LABEL:
        return rec.error(f"invalid node id {node_id!r}; ids look like 'svc:payments-api' (prefixes: {sorted(PREFIX_TO_LABEL)})")
    label = PREFIX_TO_LABEL[prefix]  # whitelisted -> safe to interpolate
    rows = rec.q(Q_NODE.replace("__LABEL__", label), {"id": node_id})
    if not rows:
        return rec.error(f"unknown node id {node_id!r}")
    props, dates = {}, {}
    for k, v in rows[0][0].properties.items():
        if k in _SKIP_PROPS:
            continue
        props[k] = clip(v, 200) if isinstance(v, str) else v
        if (k == "ts" or k.endswith("_at")) and isinstance(v, int):
            dates[k] = iso(v)
    groups = {}
    for etype, outgoing, mid, name in rec.q(Q_NEIGHBOURS.replace("__LABEL__", label), {"id": node_id}):
        groups.setdefault((etype, "out" if outgoing else "in"), []).append({"edge": etype, "dir": "out" if outgoing else "in",
                                                                             "id": mid, "name": clip(name, 40)})
    counts = {f"{e} ({d})": len(v) for (e, d), v in groups.items()}
    neighbours = []
    while len(neighbours) < 25 and any(groups.values()):  # round-robin so rare edge types are not crowded out
        for v in groups.values():
            if v and len(neighbours) < 25:
                neighbours.append(v.pop(0))
    for nb in neighbours:
        a, b = (node_id, nb["id"]) if nb["dir"] == "out" else (nb["id"], node_id)
        rec.hl_edge(a, nb["edge"], b)
    rec.hl(node_id)
    res = {"id": node_id, "label": label, "props": props, "dates": dates, "neighbour_counts": counts, "neighbours": neighbours}
    if sum(counts.values()) > len(neighbours):
        res["truncated"] = True
    return rec.done(res)


# ───────────── 13. read_source ─────────────
READABLE = {"Doc": "text", "Ticket": "text", "ChatThread": "text", "Decision": "rationale", "Runbook": "steps", "Incident": "summary"}
SOURCE_CHARS = 1800
Q_SOURCE = """MATCH (n:__LABEL__ {id:$id})
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(n)
RETURN n, a.id, a.name, a.status"""
Q_SOURCE_LINKS = """MATCH (n:__LABEL__ {id:$id})-[r:MENTIONS|DESCRIBES|ABOUT|SUPERSEDES|SOURCED_FROM]->(m)
RETURN type(r), m.id"""
Q_SUPERSEDED_BY = "MATCH (o:Runbook)-[:SUPERSEDES]->(n:Runbook {id:$id}) RETURN o.id"


def read_source(ctx, node_id):
    rec = Recorder(ctx, "read_source", {"node_id": node_id})
    prefix = node_id.split(":", 1)[0] if isinstance(node_id, str) and ":" in node_id else None
    label = PREFIX_TO_LABEL.get(prefix)
    if label not in READABLE:
        return rec.error(f"read_source reads {sorted(READABLE)} ids (doc:, tkt:, chat:, dec:, rb:, inc:); got {node_id!r}")
    rows = rec.q(Q_SOURCE.replace("__LABEL__", label), {"id": node_id})
    if not rows:
        return rec.error(f"unknown {label.lower()} id {node_id!r}")
    p = rows[0][0].properties
    text = "\n".join(x for x in ([p.get("symptom")] if label == "Incident" else []) + [p.get(READABLE[label])] if x)
    links = {}
    for typ, mid in rec.q(Q_SOURCE_LINKS.replace("__LABEL__", label), {"id": node_id}):
        links.setdefault(typ.lower(), []).append(mid)
        rec.hl_edge(node_id, typ, mid)
    date = next((p[k] for k in ("ts", "updated_at", "decided_at", "started_at", "created_at") if p.get(k)), None)
    res = {"id": node_id, "label": label, "title": p.get("title") or p.get("key"), "author": rows[0][2],
           "author_status": rows[0][3], "date": iso(date), "days_ago": days_ago(ctx.now, date),
           "text": text[:SOURCE_CHARS], "truncated": len(text) > SOURCE_CHARS, **links}
    for k in ("channel", "key", "status", "version", "flagged_stale", "origin"):
        if p.get(k) is not None:
            res[k] = p[k]
    if label == "Runbook":
        res["superseded_by"] = [r[0] for r in rec.q(Q_SUPERSEDED_BY, {"id": node_id})]
    if rows[0][1]:
        rec.hl_edge(rows[0][1], "AUTHORED", node_id)
    rec.hl(node_id)
    return rec.done(res, limit=SOURCE_CHARS + 1200)


# ───────────── 14. get_incident_state ─────────────
Q_STATE = "MATCH (i:Incident {id:$id}) RETURN i"
Q_STATE_AFFECTED = "MATCH (i:Incident {id:$id})-[:AFFECTED]->(s:Service) RETURN s.id ORDER BY s.id"
Q_STATE_CAUSE = """MATCH (i:Incident {id:$id})-[:CAUSED_BY]->(c)
OPTIONAL MATCH (c)-[:CHANGED]->(s:Service)
OPTIONAL MATCH (c)-[:FOR_TICKET]->(t:Ticket)
OPTIONAL MATCH (who:Person)-[:DEPLOYED]->(c)
RETURN c.id, labels(c)[0], c.summary, c.ts, s.id, t.key, t.title, who.name"""
Q_STATE_RC = "MATCH (i:Incident {id:$id})-[:HAS_ROOT_CAUSE]->(rc:RootCause) RETURN rc.id, rc.name"
Q_STATE_FACTS = """MATCH (:Incident {id:$id})<-[:FOR_INCIDENT]-(:Session)<-[:WRITTEN_IN]-(f:Fact)
OPTIONAL MATCH (f)-[:ABOUT]->(x)
OPTIONAL MATCH (f)-[r:SOURCED_FROM]->(src)
RETURN f.id, f.statement, f.confidence, collect(DISTINCT x.id), collect(DISTINCT [src.id, r.excerpt])"""
Q_STATE_STEPS = """MATCH (:Incident {id:$id})<-[:FOR_INCIDENT]-(ses:Session)<-[:IN_SESSION]-(st:Step)
WHERE st.action IN ['handoff', 'write', 'page']
RETURN ses.id, ses.started_at, st.seq, st.agent, st.action, st.tool, st.summary, st.params_json
ORDER BY ses.started_at, st.seq"""
Q_STATE_TICKETS = "MATCH (t:Ticket)-[:ABOUT]->(:Incident {id:$id}) RETURN t.id, t.key, t.title, t.status"
Q_STATE_SIMILAR = """MATCH (i:Incident {id:$id})-[s:SIMILAR_TO]-(o)
OPTIONAL MATCH (o)-[:RESOLVED_BY]->(r:Resolution)
OPTIONAL MATCH (r)-[:PERFORMED_BY]->(p:Person)
OPTIONAL MATCH (rb:Runbook)-[:SOURCED_FROM]->(o)
RETURN o.id, o.key, s.score, s.reason, r.summary, collect(DISTINCT p.name), collect(DISTINCT rb.id)"""
Q_STATE_RESOLUTION = """MATCH (i:Incident {id:$id})-[:RESOLVED_BY]->(r:Resolution)
OPTIONAL MATCH (r)-[:PERFORMED_BY]->(p:Person)
RETURN r.id, r.summary, collect(p.id), collect(p.name)"""
STATE_CHARS = 10000  # ponytail: ~2.5k tokens; the handoffs must never be trimmed. Summarise old handoffs if states grow past this.


def get_incident_state(ctx, incident_id):
    rec = Recorder(ctx, "get_incident_state", {"incident_id": incident_id})
    if err := rec.check(incident_id, "Incident"):
        return rec.error(err)
    p = {"id": incident_id}
    i = rec.q(Q_STATE, p)[0][0].properties
    res = {"id": incident_id, **{k: i.get(k) for k in ("key", "title", "severity", "status", "symptom", "summary", "origin")},
           "started_minutes_ago": minutes_ago(ctx.now, i["started_at"]) if i.get("started_at") else None,
           "affected": [r[0] for r in rec.q(Q_STATE_AFFECTED, p)]}
    for s in res["affected"]:
        rec.hl_edge(incident_id, "AFFECTED", s)
    res["caused_by"] = []
    for cid, clabel, summ, ts, sid, tkey, ttitle, who in rec.q(Q_STATE_CAUSE, p):
        rec.hl_edge(incident_id, "CAUSED_BY", cid)
        c = {"id": cid, "label": clabel}
        if clabel == "Deploy":
            c.update(service=sid, summary=clip(summ, 160), minutes_ago=minutes_ago(ctx.now, ts), by=who,
                     ticket={"key": tkey, "title": clip(ttitle, 100)} if tkey else None)
            rec.hl_edge(cid, "CHANGED", sid)
        res["caused_by"].append(c)
    res["root_causes"] = [{"id": a, "name": b} for a, b in rec.q(Q_STATE_RC, p)]
    for rc in res["root_causes"]:
        rec.hl_edge(incident_id, "HAS_ROOT_CAUSE", rc["id"])
    res["facts"] = []
    for fid, stmt, conf, about, srcs in rec.q(Q_STATE_FACTS, p):
        rec.hl(fid)
        res["facts"].append({"id": fid, "statement": stmt, "confidence": conf, "about": about,
                             "sources": [{"id": s, "excerpt": clip(e, 220)} for s, e in srcs if s]})
    res["handoffs"], res["actions"] = [], []
    for sid, _, seq, agent, action, tool, summ, pj in rec.q(Q_STATE_STEPS, p):
        if action == "handoff":
            try:
                details = json.loads(pj or "{}").get("details")
            except ValueError:
                details = None
            res["handoffs"].append({"agent": agent, "session": sid, "seq": seq, "note": summ, "details": details})
        else:
            res["actions"].append({"agent": agent, "action": action, "tool": tool, "summary": clip(summ, 160)})
    res["tickets"] = [{"id": a, "key": b, "title": clip(c, 90), "status": d} for a, b, c, d in rec.q(Q_STATE_TICKETS, p)]
    res["similar"] = []
    for oid, key, score, reason, rsum, people, rbs in rec.q(Q_STATE_SIMILAR, p):
        rec.hl_edge(incident_id, "SIMILAR_TO", oid)
        res["similar"].append({"id": oid, "key": key, "score": score, "reason": clip(reason, 120),
                               "resolution": clip(rsum, 120) if rsum else None, "resolved_by": people, "runbooks": rbs})
    r = rec.q(Q_STATE_RESOLUTION, p)
    res["resolution"] = {"id": r[0][0], "summary": r[0][1], "performed_by": r[0][2], "names": r[0][3]} if r else None
    rec.hl(incident_id)
    return rec.done(res, limit=STATE_CHARS)


# ───────────── 15. memory_recall ─────────────
Q_RECALL_SCOPE = "MATCH (s:Service {id:$id})-[:DEPENDS_ON*1..__N__]->(d:Service) RETURN DISTINCT d.id"
Q_RECALL_LEARNED = """MATCH (a:Service)-[r:DEPENDS_ON {source:'learned'}]->(b:Service)
WHERE a.id IN $ids OR b.id IN $ids
OPTIONAL MATCH (f:Fact) WHERE f.id = r.learned_from
OPTIONAL MATCH (f)-[sf:SOURCED_FROM]->(src)
OPTIONAL MATCH (f)-[:WRITTEN_IN]->(ses:Session)
RETURN a.id, b.id, r.kind, r.learned_at, f.id, f.statement, src.id, sf.excerpt, ses.id"""
Q_RECALL_FACTS = """MATCH (f:Fact)-[:ABOUT]->(s:Service)
WHERE s.id IN $ids AND NOT f.id IN $skip
OPTIONAL MATCH (f)-[sf:SOURCED_FROM]->(src)
OPTIONAL MATCH (f)-[:WRITTEN_IN]->(ses:Session)
RETURN f.id, f.statement, f.confidence, collect(DISTINCT s.id), collect(DISTINCT [src.id, sf.excerpt]), collect(DISTINCT ses.id)"""
Q_RECALL_INCIDENTS = """MATCH (i:Incident {origin:'agent', status:'resolved'})-[:AFFECTED]->(s:Service)
WHERE s.id IN $ids
OPTIONAL MATCH (i)-[:CAUSED_BY]->(c)
OPTIONAL MATCH (c)-[:CHANGED]->(cs:Service)
OPTIONAL MATCH (i)-[:HAS_ROOT_CAUSE]->(rc:RootCause)
OPTIONAL MATCH (i)-[:RESOLVED_BY]->(r:Resolution)
OPTIONAL MATCH (r)-[:PERFORMED_BY]->(p:Person)
OPTIONAL MATCH (i)-[:WRITTEN_IN]->(ses:Session)
RETURN i.id, i.key, i.title, i.resolved_at, collect(DISTINCT s.id), collect(DISTINCT [c.id, labels(c)[0], cs.id]),
       collect(DISTINCT rc.id), r.id, r.summary, collect(DISTINCT [p.id, p.name]), collect(DISTINCT ses.id)
ORDER BY i.resolved_at DESC"""
# latest version of each runbook written from those incidents: follow SUPERSEDES up to a runbook nothing supersedes
Q_RECALL_RUNBOOKS = """MATCH (rb:Runbook)-[:SOURCED_FROM]->(i:Incident)
WHERE i.id IN $iids
MATCH (latest:Runbook)-[:SUPERSEDES*0..5]->(rb)
WHERE NOT ()-[:SUPERSEDES]->(latest)
RETURN DISTINCT i.id, latest.id, latest.title, latest.version, latest.steps"""


def _suspect(sus, svc, relation, via, shared=None):
    s = sus.setdefault(svc, {"service": svc, "relation": relation, "via": []})
    s["via"].append(via)
    if shared and "shared" not in s:
        s["shared"] = shared


def memory_recall(ctx, service_id, max_hops=3):
    rec = Recorder(ctx, "memory_recall", {"service_id": service_id, "max_hops": max_hops})
    if err := rec.check(service_id, "Service"):
        return rec.error(err)
    n = clamp(max_hops, 1, MAX_HOPS, 3)
    down = [r[0] for r in rec.q(_n(Q_RECALL_SCOPE, n), {"id": service_id})]
    scope = [service_id] + down
    sus = {}  # service -> why earlier sessions point at it
    learned = {}
    for a, b, kind, at, fid, stmt, src, exc, ses in rec.q(Q_RECALL_LEARNED, {"ids": scope}):
        e = learned.setdefault((a, b), {"from": a, "to": b, "kind": kind, "learned": iso(at),
                                         "fact": {"id": fid, "statement": clip(stmt, 200), "sources": []}, "session": ses})
        if src and src not in [s["id"] for s in e["fact"]["sources"]]:
            e["fact"]["sources"].append({"id": src, "excerpt": clip(exc, 220)})
        rec.hl_edge(a, "DEPENDS_ON", b)
        if fid and src:
            rec.hl_edge(fid, "SOURCED_FROM", src)
        if a in scope:  # on my own call path: the callee is downstream
            _suspect(sus, b, "downstream", f"learned edge {a} -> {b}" + (f" ({fid})" if fid else ""))
        else:  # someone else calls one of my dependencies: a noisy-neighbour candidate
            _suspect(sus, a, "shares_dependency", f"learned edge {a} -> {b}" + (f" ({fid})" if fid else ""), shared=b)
    skip = [e["fact"]["id"] for e in learned.values() if e["fact"]["id"]]
    facts = []
    for fid, stmt, conf, about, srcs, sess in rec.q(Q_RECALL_FACTS, {"ids": scope, "skip": skip}):
        rec.hl(fid)
        facts.append({"id": fid, "statement": clip(stmt, 200), "confidence": conf, "about": about,
                      "sources": [{"id": s, "excerpt": clip(x, 220)} for s, x in srcs if s], "session": (sess or [None])[0]})
    incidents = []
    for iid, key, title, resolved, aff, causes, rcs, rid, rsum, people, sess in rec.q(Q_RECALL_INCIDENTS, {"ids": scope}):
        cause = next(({"deploy": c, "service": cs} for c, lab, cs in causes if lab == "Deploy"), None) or next(
            ({"deploy": None, "service": c} for c, lab, _ in causes if lab == "Service"), None)
        for s in aff:
            rec.hl_edge(iid, "AFFECTED", s)
        if rid:
            rec.hl_edge(iid, "RESOLVED_BY", rid)
        for pid, _ in people:
            if pid and rid:
                rec.hl_edge(rid, "PERFORMED_BY", pid)
        incidents.append({"id": iid, "key": key, "title": clip(title, 90), "resolved": iso(resolved),
                          "affected_in_scope": aff, "cause": cause, "root_causes": rcs,
                          "resolution": {"id": rid, "summary": clip(rsum, 160)} if rid else None,
                          "resolved_by": [{"id": p, "name": nm} for p, nm in people if p], "session": (sess or [None])[0]})
        if cause and cause["service"] and cause["service"] != service_id:
            _suspect(sus, cause["service"], "downstream" if cause["service"] in scope else "shares_dependency",
                     f"caused {key}")
    if incidents:
        for iid, rb, title, version, steps in rec.q(Q_RECALL_RUNBOOKS, {"iids": [i["id"] for i in incidents]}):
            rec.hl_edge(rb, "SOURCED_FROM", iid)
            inc = next(i for i in incidents if i["id"] == iid)
            inc["runbook"] = {"id": rb, "title": clip(title, 80), "version": version,
                              "steps": [clip(l, 180) for l in (steps or "").split("\n") if l.strip()][:8]}
    rec.hl(service_id)
    res = {"service": service_id, "scope": scope, "learned_edges": list(learned.values()), "facts": facts[:5],
           "incidents": incidents[:3], "suspects": sorted(sus.values(), key=lambda s: -len(s["via"]))[:5]}
    if not (learned or facts or incidents):
        res["note"] = "no memory yet: earlier agent sessions learned nothing about this service or its dependencies"
    return rec.done(res, limit=4500)


# ───────────── 16. industry_matches ─────────────
Q_IND_INCIDENT = """MATCH (i:Incident {id:$id})
OPTIONAL MATCH (i)-[:HAS_ROOT_CAUSE]->(rc:RootCause)
RETURN i.title, i.symptom, i.summary, collect(rc.id)"""
Q_IND_MATCHES = """MATCH (pm:PublicPostmortem)-[:HAS_ROOT_CAUSE]->(rc:RootCause)
WHERE rc.id IN $rcs
RETURN pm.id, pm.company, pm.title, pm.url, pm.published_at, pm.summary, collect(DISTINCT rc.id)"""
Q_IND_LINKED = "MATCH (:Incident {id:$id})-[s:SIMILAR_TO]->(pm:PublicPostmortem) RETURN pm.id, s.score"
_IND_STOP = {"with", "that", "this", "from", "into", "were", "when", "then", "they", "their", "every", "after", "before",
             "about", "which", "while", "would", "could", "because", "service", "services", "minutes", "last"}


def _terms(text):
    return {w for w in re.findall(r"[a-z][a-z0-9]+", (text or "").lower()) if len(w) >= 4 and w not in _IND_STOP}


def industry_matches(ctx, root_cause_id=None, incident_id=None, limit=5):
    rec = Recorder(ctx, "industry_matches", {"root_cause_id": root_cause_id, "incident_id": incident_id, "limit": limit})
    if (root_cause_id is None) == (incident_id is None):
        return rec.error("pass exactly one of root_cause_id (rc:...) or incident_id (inc:...)")
    text, linked = "", {}
    if incident_id is not None:
        if err := rec.check(incident_id, "Incident"):
            return rec.error(err)
        title, symptom, summary, rcs = rec.q(Q_IND_INCIDENT, {"id": incident_id})[0]
        text = " ".join(x for x in (title, symptom, summary) if x)
        linked = dict(rec.q(Q_IND_LINKED, {"id": incident_id}))
        if not rcs:
            return rec.done({"incident": incident_id, "root_causes": [], "matches": [],
                             "note": "this incident has no root cause yet; set one (update_incident root_cause_id) first"})
    else:
        if err := rec.check(root_cause_id, "RootCause"):
            return rec.error(err)
        rcs = [root_cause_id]
    mine = _terms(text)
    rows = rec.q(Q_IND_MATCHES, {"rcs": rcs})
    # rank: more shared root causes, then more words shared with the incident, then newest
    scored = sorted(((r, sorted(mine & _terms(f"{r[2]} {r[5]}"))) for r in rows),
                    key=lambda x: (-len(x[0][6]), -len(x[1]), -(x[0][4] or 0)))
    limit = clamp(limit, 1, 10, 5)
    out = []
    for (pid, company, title, url, pub, summ, shared), overlap in scored[:limit]:
        for rc in shared:
            rec.hl_edge(pid, "HAS_ROOT_CAUSE", rc)
        if pid in linked:
            rec.hl_edge(incident_id, "SIMILAR_TO", pid)
        out.append({"id": pid, "company": company, "title": clip(title, 120), "url": url, "published": iso(pub),
                    "summary": clip(summ, 420), "shared_root_causes": shared, "overlap_terms": overlap[:6],
                    **({"already_linked": linked[pid]} if pid in linked else {})})
    res = {**({"incident": incident_id} if incident_id else {}), "root_causes": rcs, "match_count": len(rows), "matches": out}
    if not rows:
        res["note"] = "no public postmortem shares these root causes"
    return rec.done(res, limit=4000)
