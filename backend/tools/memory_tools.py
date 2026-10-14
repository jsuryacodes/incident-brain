"""Memory / action write tools. fn(ctx, **args) -> ToolOutput, same result + receipt shape as the read tools.

Every write is validated first (ids exist with the right label, excerpts are literal quotes of their source, no
duplicate learned edges), uses MERGE on id, puts origin='agent' + created_at on every node AND edge it creates, hangs
WRITTEN_IN -> current Session on Fact/Resolution/Runbook/Ticket/Incident, and is parameterised. Only schema labels
(looked up from the id prefix) are interpolated.

Concurrency: incident and ticket keys are allocated and created in ONE query, and the learned edge is checked and
created in ONE query. FalkorDB executes write queries one at a time per graph, so parallel agents can't take the same
key or create the same learned edge twice.
"""
import hashlib
import re
import time

from backend.tools.receipt import Recorder, clip, excerpt_error
from seed.schema import PREFIX_TO_LABEL

SOURCE_LABELS = ("Doc", "Ticket", "ChatThread", "Incident")
NEW = "origin = 'agent', {0}.created_at = $now"  # used as ON CREATE SET x.<NEW>


def _new(var):
    return f"ON CREATE SET {var}." + NEW.format(var)


def _label(node_id):
    return PREFIX_TO_LABEL.get(node_id.split(":", 1)[0]) if isinstance(node_id, str) and ":" in node_id else None


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")[:60]


def _steps_text(steps):
    if isinstance(steps, list):
        return "\n".join(f"{i}. {re.sub(r'^[0-9]+[.)] *', '', str(s).strip())}" for i, s in enumerate(steps, 1))
    return str(steps or "").strip()


def _num(v, lo, hi, kind=float):
    try:
        v = kind(v)
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


def _session(rec, ctx):
    if not ctx.session_id:
        return "write tools need an active agent session"
    return rec.check(ctx.session_id, "Session")


def _sources(rec, sources):
    if not isinstance(sources, list) or not sources:
        return "sources must be a non-empty list of {node_id, excerpt}"
    for s in sources:
        nid = s.get("node_id") if isinstance(s, dict) else None
        lab = _label(nid)
        if lab not in SOURCE_LABELS:
            return f"source {nid!r} must be a doc:, tkt:, chat: or inc: id"
        if err := rec.check(nid, lab) or excerpt_error(rec.graph, nid, s.get("excerpt")):
            return err
    return None


def _write_sources(rec, label, node_id, sources, now):
    for s in sources:
        rec.w(f"MATCH (n:{label} {{id:$id}}), (s:{_label(s['node_id'])} {{id:$sid}}) "
              f"MERGE (n)-[r:SOURCED_FROM]->(s) {_new('r')}, r.excerpt = $excerpt",
              {"id": node_id, "sid": s["node_id"], "excerpt": s["excerpt"], "now": now})
        rec.hl_edge(node_id, "SOURCED_FROM", s["node_id"])


def _written_in(rec, label, node_id, ctx, now):
    rec.w(f"MATCH (n:{label} {{id:$id}}), (ses:Session {{id:$ses}}) MERGE (n)-[r:WRITTEN_IN]->(ses) {_new('r')}",
          {"id": node_id, "ses": ctx.session_id, "now": now})
    rec.hl_edge(node_id, "WRITTEN_IN", ctx.session_id)


def _agent_incident(rec, incident_id):
    if err := rec.check(incident_id, "Incident"):
        return err, None
    origin, key, sev = rec.graph.ro_query("MATCH (i:Incident {id:$id}) RETURN i.origin, i.key, i.severity",
                                          {"id": incident_id}).result_set[0]
    return None, {"origin": origin, "key": key, "severity": sev}


# ───────────── open_incident ─────────────
Q_OPEN = """OPTIONAL MATCH (i:Incident) WHERE i.key STARTS WITH $prefix
WITH coalesce(max(toInteger(substring(i.key, size($prefix)))), 0) + 1 AS n
WITH $prefix + right('00' + toString(n), 3) AS key
CREATE (x:Incident {id: 'inc:' + substring(key, 4), key: key, title: $title, severity: $severity, status: 'open',
        symptom: $symptom, summary: $symptom, started_at: $now, origin: 'agent', created_at: $now})
RETURN x.id, x.key"""
Q_OPEN_LINK = """MATCH (x:Incident {id:$id}), (s:Service {id:$svc}), (ses:Session {id:$ses})
MERGE (x)-[a:AFFECTED]->(s) ON CREATE SET a.origin = 'agent', a.created_at = $now
MERGE (ses)-[f:FOR_INCIDENT]->(x) ON CREATE SET f.origin = 'agent', f.created_at = $now
MERGE (x)-[w:WRITTEN_IN]->(ses) ON CREATE SET w.origin = 'agent', w.created_at = $now"""


def open_incident(ctx, service_id, symptom, severity):
    rec = Recorder(ctx, "open_incident", {"service_id": service_id, "symptom": symptom, "severity": severity})
    sev = _num(severity, 1, 4, int)
    if err := _session(rec, ctx) or rec.check(service_id, "Service"):
        return rec.error(err)
    if sev is None or not str(symptom or "").strip():
        return rec.error("severity must be 1-4 (1 = worst) and symptom must be non-empty")
    now = int(time.time())
    year = time.strftime("%Y", time.gmtime(ctx.now))
    iid, key = rec.w(Q_OPEN, {"prefix": f"INC-{year}-", "title": clip(f"{service_id.split(':', 1)[1]}: {symptom}", 100),
                              "severity": sev, "symptom": str(symptom).strip(), "now": now})[0]
    rec.w(Q_OPEN_LINK, {"id": iid, "svc": service_id, "ses": ctx.session_id, "now": now})
    rec.hl_edge(iid, "AFFECTED", service_id)
    rec.hl_edge(ctx.session_id, "FOR_INCIDENT", iid)
    return rec.done({"id": iid, "key": key, "status": "open", "severity": sev,
                     "summary": f"opened {key} ({iid}), severity {sev}, on {service_id}"})


# ───────────── update_incident ─────────────
def update_incident(ctx, incident_id, status=None, severity=None, affected_ids=None, cause_deploy_id=None,
                    cause_service_id=None, root_cause_id=None, summary=None):
    loc = dict(locals())
    args = {k: v for k, v in loc.items() if k != "ctx" and v is not None}
    rec = Recorder(ctx, "update_incident", args)
    err, inc = _agent_incident(rec, incident_id)
    if err:
        return rec.error(err)
    if inc["origin"] != "agent":
        return rec.error(f"{incident_id} is a historical (seed) incident; only incidents opened by agents can be updated")
    if status is not None and status not in ("open", "mitigated", "resolved"):
        return rec.error("status must be open, mitigated or resolved")
    if severity is not None and _num(severity, 1, 4, int) is None:
        return rec.error("severity must be 1-4")
    affected_ids = affected_ids or []
    if not isinstance(affected_ids, list):
        return rec.error("affected_ids must be a list of service ids")
    for i, lab in [(a, "Service") for a in affected_ids] + [(cause_deploy_id, "Deploy"), (cause_service_id, "Service"),
                                                            (root_cause_id, "RootCause")]:
        if i is not None and (err := rec.check(i, lab)):
            return rec.error(err)
    if len(args) == 1:
        return rec.error("nothing to update")
    now, p, done = int(time.time()), {"id": incident_id}, []
    props = {k: v for k, v in (("status", status), ("severity", _num(severity, 1, 4, int) if severity else None),
                               ("summary", summary)) if v is not None}
    if status == "resolved":
        props["resolved_at"] = now
    if props:
        rec.w("MATCH (i:Incident {id:$id}) SET i += $props", {**p, "props": props})
        done.append(", ".join(f"{k}={clip(v, 40)}" for k, v in props.items() if k != "resolved_at"))
    if affected_ids:
        rec.w("UNWIND $ids AS sid MATCH (i:Incident {id:$id}), (s:Service {id:sid}) "
              f"MERGE (i)-[r:AFFECTED]->(s) {_new('r')}", {**p, "ids": affected_ids, "now": now})
        for a in affected_ids:
            rec.hl_edge(incident_id, "AFFECTED", a)
        done.append(f"affected +{len(affected_ids)}")
    for target, lab, typ in ((cause_deploy_id, "Deploy", "CAUSED_BY"), (cause_service_id, "Service", "CAUSED_BY"),
                             (root_cause_id, "RootCause", "HAS_ROOT_CAUSE")):
        if target:
            rec.w(f"MATCH (i:Incident {{id:$id}}), (t:{lab} {{id:$t}}) MERGE (i)-[r:{typ}]->(t) {_new('r')}",
                  {**p, "t": target, "now": now})
            rec.hl_edge(incident_id, typ, target)
            done.append(f"{'cause' if typ == 'CAUSED_BY' else 'root cause'} {target}")
    rec.hl(incident_id)
    return rec.done({"id": incident_id, "key": inc["key"], "updated": done,
                     "summary": f"{inc['key']}: " + "; ".join(done)})


# ───────────── record_learned_dependency / record_fact ─────────────
Q_LEARN = """MATCH (a:Service {id:$a}), (b:Service {id:$b})
WHERE NOT (a)-[:DEPENDS_ON]-(b)
MERGE (f:Fact {id:$fid}) ON CREATE SET f.statement = $statement, f.confidence = $confidence, f.origin = 'agent', f.created_at = $now
CREATE (a)-[r:DEPENDS_ON {kind: $kind, source: 'learned', learned_at: $now, learned_from: $fid, origin: 'agent', created_at: $now}]->(b)
RETURN f.id"""


def _fact_links(rec, fid, about, sources, ctx, now):
    for a in about:
        rec.w(f"MATCH (f:Fact {{id:$id}}), (x:{_label(a)} {{id:$x}}) MERGE (f)-[r:ABOUT]->(x) {_new('r')}",
              {"id": fid, "x": a, "now": now})
        rec.hl_edge(fid, "ABOUT", a)
    _write_sources(rec, "Fact", fid, sources, now)
    _written_in(rec, "Fact", fid, ctx, now)


def record_learned_dependency(ctx, from_service_id, to_service_id, kind, statement, confidence, sources):
    rec = Recorder(ctx, "record_learned_dependency",
                   {"from_service_id": from_service_id, "to_service_id": to_service_id, "kind": kind,
                    "statement": statement, "confidence": confidence, "sources": sources})
    conf = _num(confidence, 0, 1)
    if err := (_session(rec, ctx) or rec.check(from_service_id, "Service") or rec.check(to_service_id, "Service")
               or _sources(rec, sources)):
        return rec.error(err)
    if from_service_id == to_service_id:
        return rec.error("a service cannot depend on itself")
    if kind not in ("sync", "async", "db", "cache") or conf is None or not str(statement or "").strip():
        return rec.error("kind must be sync|async|db|cache, confidence 0..1, statement non-empty")
    now = int(time.time())
    fid = f"fact:learned-{from_service_id.split(':', 1)[1]}-{to_service_id.split(':', 1)[1]}"
    rows = rec.w(Q_LEARN, {"a": from_service_id, "b": to_service_id, "fid": fid, "statement": statement,
                           "confidence": conf, "kind": kind, "now": now})
    if not rows:
        return rec.error(f"a DEPENDS_ON edge already exists between {from_service_id} and {to_service_id} "
                         "(declared or learned); nothing written")
    _fact_links(rec, fid, [from_service_id, to_service_id], sources, ctx, now)
    rec.hl_edge(from_service_id, "DEPENDS_ON", to_service_id)
    return rec.done({"fact_id": fid, "edge": {"from": from_service_id, "to": to_service_id, "source": "learned",
                                              "kind": kind, "learned_from": fid},
                     "summary": f"LEARNED {from_service_id} -[DEPENDS_ON]-> {to_service_id} ({fid})"})


def record_fact(ctx, statement, about_ids, confidence, sources):
    rec = Recorder(ctx, "record_fact", {"statement": statement, "about_ids": about_ids, "confidence": confidence,
                                        "sources": sources})
    conf = _num(confidence, 0, 1)
    if not isinstance(about_ids, list) or not about_ids:
        return rec.error("about_ids must be a non-empty list of service or incident ids")
    for a in about_ids:
        if _label(a) not in ("Service", "Incident"):
            return rec.error(f"about id {a!r} must be a svc: or inc: id")
        if err := rec.check(a, _label(a)):
            return rec.error(err)
    if err := _session(rec, ctx) or _sources(rec, sources):
        return rec.error(err)
    if conf is None or not str(statement or "").strip():
        return rec.error("confidence must be 0..1 and statement non-empty")
    now = int(time.time())
    fid = "fact:" + hashlib.sha1(statement.encode()).hexdigest()[:10]
    rec.w(f"MERGE (f:Fact {{id:$id}}) {_new('f')}, f.statement = $statement, f.confidence = $confidence",
          {"id": fid, "statement": statement, "confidence": conf, "now": now})
    _fact_links(rec, fid, about_ids, sources, ctx, now)
    return rec.done({"fact_id": fid, "summary": f"fact {fid}: {clip(statement, 100)}"})


# ───────────── page_person / open_ticket / flag_stale ─────────────
Q_PAGE = """MATCH (p:Person {id:$p}), (i:Incident {id:$i})
RETURN p.name, p.status, p.left_at, i.key"""


def page_person(ctx, person_id, incident_id, message):
    """Simulated: no external call. The page IS the Step (action 'page') the session log writes, CITED person+incident."""
    rec = Recorder(ctx, "page_person", {"person_id": person_id, "incident_id": incident_id, "message": message})
    if err := _session(rec, ctx) or rec.check(person_id, "Person") or rec.check(incident_id, "Incident"):
        return rec.error(err)
    name, status, left_at, key = rec.q(Q_PAGE, {"p": person_id, "i": incident_id})[0]
    if status == "left":
        days = (ctx.now - left_at) // 86400 if left_at else "?"
        return rec.error(f"{name} ({person_id}) left the company {days} days ago and cannot be paged; "
                         "page an active person from who_to_call instead")
    rec.hl(person_id, incident_id)
    return rec.done({"paged": person_id, "name": name, "incident": incident_id, "simulated": True,
                     "message": clip(message, 300), "summary": f"paged {name} for {key} (simulated): {clip(message, 90)}"})


Q_TICKET = """OPTIONAL MATCH (t:Ticket) WHERE t.key STARTS WITH 'OPS-'
WITH coalesce(max(toInteger(substring(t.key, 4))), 0) + 1 AS n
CREATE (x:Ticket {id: 'tkt:OPS-' + toString(n), key: 'OPS-' + toString(n), title: $title, text: $text,
        kind: 'incident-followup', status: 'open', priority: $priority, origin: 'agent', created_at: $now})
RETURN x.id, x.key"""


def open_ticket(ctx, title, text, service_id, incident_id):
    rec = Recorder(ctx, "open_ticket", {"title": title, "text": text, "service_id": service_id, "incident_id": incident_id})
    if err := _session(rec, ctx) or rec.check(service_id, "Service"):
        return rec.error(err)
    err, inc = _agent_incident(rec, incident_id)
    if err:
        return rec.error(err)
    if not str(title or "").strip() or not str(text or "").strip():
        return rec.error("title and text must be non-empty")
    now = int(time.time())
    tid, key = rec.w(Q_TICKET, {"title": clip(title, 120), "text": str(text).strip(), "now": now,
                                "priority": "P1" if inc["severity"] == 1 else "P2"})[0]
    for target, lab in ((service_id, "Service"), (incident_id, "Incident")):
        rec.w(f"MATCH (t:Ticket {{id:$id}}), (x:{lab} {{id:$x}}) MERGE (t)-[r:ABOUT]->(x) {_new('r')}",
              {"id": tid, "x": target, "now": now})
        rec.hl_edge(tid, "ABOUT", target)
    _written_in(rec, "Ticket", tid, ctx, now)
    return rec.done({"id": tid, "key": key, "status": "open", "summary": f"opened {key} ({tid}): {clip(title, 80)}"})


def flag_stale(ctx, node_id, reason):
    rec = Recorder(ctx, "flag_stale", {"node_id": node_id, "reason": reason})
    lab = _label(node_id)
    if lab not in ("Doc", "Runbook"):
        return rec.error(f"only doc: and rb: ids can be flagged stale; got {node_id!r}")
    if err := rec.check(node_id, lab):
        return rec.error(err)
    if not str(reason or "").strip():
        return rec.error("reason must be non-empty")
    rec.w(f"MATCH (n:{lab} {{id:$id}}) SET n.flagged_stale = true, n.flagged_reason = $reason, n.flagged_at = $now",
          {"id": node_id, "reason": clip(reason, 300), "now": int(time.time())})
    rec.hl(node_id)
    return rec.done({"id": node_id, "flagged_stale": True, "summary": f"flagged {node_id} stale: {clip(reason, 100)}"})


# ───────────── record_resolution / link_similar / write_runbook ─────────────
def record_resolution(ctx, incident_id, summary, steps, performed_by_ids, sources):
    rec = Recorder(ctx, "record_resolution", {"incident_id": incident_id, "summary": summary, "steps": steps,
                                              "performed_by_ids": performed_by_ids, "sources": sources})
    err, inc = _agent_incident(rec, incident_id)
    if err or (err := _session(rec, ctx)):
        return rec.error(err)
    if not isinstance(performed_by_ids, list) or not performed_by_ids:
        return rec.error("performed_by_ids must be a non-empty list of person ids")
    for pid in performed_by_ids:
        if err := rec.check(pid, "Person"):
            return rec.error(err)
    if err := _sources(rec, sources):
        return rec.error(err)
    if not str(summary or "").strip():
        return rec.error("summary must be non-empty")
    now, rid = int(time.time()), "res:" + incident_id.split(":", 1)[1]
    rec.w(f"MERGE (r:Resolution {{id:$id}}) {_new('r')} SET r.summary = $summary, r.steps = $steps",
          {"id": rid, "summary": summary, "steps": _steps_text(steps), "now": now})
    rec.w(f"MATCH (i:Incident {{id:$iid}}), (r:Resolution {{id:$id}}) MERGE (i)-[e:RESOLVED_BY]->(r) {_new('e')} "
          "SET i.status = 'resolved', i.resolved_at = $now", {"iid": incident_id, "id": rid, "now": now})
    rec.w(f"UNWIND $pids AS pid MATCH (r:Resolution {{id:$id}}), (p:Person {{id:pid}}) MERGE (r)-[e:PERFORMED_BY]->(p) {_new('e')}",
          {"id": rid, "pids": performed_by_ids, "now": now})
    rec.hl_edge(incident_id, "RESOLVED_BY", rid)
    for pid in performed_by_ids:
        rec.hl_edge(rid, "PERFORMED_BY", pid)
    _write_sources(rec, "Resolution", rid, sources, now)
    _written_in(rec, "Resolution", rid, ctx, now)
    return rec.done({"id": rid, "incident": incident_id, "status": "resolved",
                     "summary": f"resolution {rid} for {inc['key']}: {clip(summary, 90)}"})


def link_similar(ctx, incident_id, other_id, score, reason):
    rec = Recorder(ctx, "link_similar", {"incident_id": incident_id, "other_id": other_id, "score": score, "reason": reason})
    lab = _label(other_id)
    sc = _num(score, 0, 1)
    if err := rec.check(incident_id, "Incident"):
        return rec.error(err)
    if lab not in ("Incident", "PublicPostmortem"):
        return rec.error(f"other_id must be an inc: or pm: id; got {other_id!r}")
    if err := rec.check(other_id, lab):
        return rec.error(err)
    if other_id == incident_id or sc is None or not str(reason or "").strip():
        return rec.error("link two different incidents with score 0..1 and a non-empty reason")
    rec.w(f"MATCH (i:Incident {{id:$id}}), (o:{lab} {{id:$o}}) MERGE (i)-[r:SIMILAR_TO]->(o) {_new('r')} "
          "SET r.score = $score, r.reason = $reason",
          {"id": incident_id, "o": other_id, "score": sc, "reason": clip(reason, 200), "now": int(time.time())})
    rec.hl_edge(incident_id, "SIMILAR_TO", other_id)
    return rec.done({"from": incident_id, "to": other_id, "score": sc,
                     "summary": f"{incident_id} SIMILAR_TO {other_id} ({sc}): {clip(reason, 80)}"})


def write_runbook(ctx, service_id, title, steps, sources, supersedes_id=None):
    rec = Recorder(ctx, "write_runbook", {"service_id": service_id, "title": title, "steps": steps, "sources": sources,
                                          "supersedes_id": supersedes_id})
    if err := _session(rec, ctx) or rec.check(service_id, "Service") or _sources(rec, sources):
        return rec.error(err)
    if not str(title or "").strip() or not _steps_text(steps):
        return rec.error("title and steps must be non-empty")
    version, rid = 1, f"rb:{_slug(title)}"
    if supersedes_id:
        if err := rec.check(supersedes_id, "Runbook"):
            return rec.error(err)
        old_v, newer = rec.graph.ro_query("MATCH (o:Runbook {id:$id}) OPTIONAL MATCH (n:Runbook)-[:SUPERSEDES]->(o) "
                                          "RETURN o.version, collect(n.id)", {"id": supersedes_id}).result_set[0]
        if newer:
            return rec.error(f"{supersedes_id} is already superseded by {newer[0]}; supersede that one instead")
        version = (old_v or 1) + 1
        rid = f"rb:{re.sub(r'-v[0-9]+$', '', supersedes_id.split(':', 1)[1])}-v{version}"
    if not rec.check(rid, "Runbook"):
        return rec.error(f"{rid} already exists; pass supersedes_id to write a new version")
    now = int(time.time())
    rec.w(f"MERGE (rb:Runbook {{id:$id}}) {_new('rb')} SET rb.title = $title, rb.steps = $steps, rb.version = $v, "
          "rb.updated_at = $now", {"id": rid, "title": title, "steps": _steps_text(steps), "v": version, "now": now})
    rec.w(f"MATCH (rb:Runbook {{id:$id}}), (s:Service {{id:$s}}) MERGE (rb)-[r:DESCRIBES]->(s) {_new('r')}",
          {"id": rid, "s": service_id, "now": now})
    rec.hl_edge(rid, "DESCRIBES", service_id)
    if supersedes_id:
        rec.w(f"MATCH (rb:Runbook {{id:$id}}), (o:Runbook {{id:$o}}) MERGE (rb)-[r:SUPERSEDES]->(o) {_new('r')}",
              {"id": rid, "o": supersedes_id, "now": now})
        rec.hl_edge(rid, "SUPERSEDES", supersedes_id)
    _write_sources(rec, "Runbook", rid, sources, now)
    _written_in(rec, "Runbook", rid, ctx, now)
    return rec.done({"id": rid, "version": version, "supersedes": supersedes_id,
                     "summary": f"runbook {rid} v{version}" + (f" supersedes {supersedes_id}" if supersedes_id else "")})


# ───────────── registry entries (LLM-facing) ─────────────
def _obj(props, required=()):
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


_S = {"type": "string"}
_SOURCES = {"type": "array", "minItems": 1, "description": "Where this came from. excerpt must be copied VERBATIM from the source text (use read_source).",
            "items": _obj({"node_id": {"type": "string", "description": "doc:, tkt:, chat: or inc: id"}, "excerpt": _S}, ["node_id", "excerpt"])}
_CONF = {"type": "number", "minimum": 0, "maximum": 1}

MEMORY_TOOLS = {
    "open_incident": dict(fn=open_incident, action="write",
        description="Open a new incident for the alerting service. Allocates the next INC-<year>-<nnn> key, links it to this session and marks the service AFFECTED. Call once per alert.",
        input_schema=_obj({"service_id": _S, "symptom": _S, "severity": {"type": "integer", "minimum": 1, "maximum": 4, "description": "1 = worst."}},
                          ["service_id", "symptom", "severity"])),
    "update_incident": dict(fn=update_incident, action="write",
        description="Update an open incident: status, severity, more AFFECTED services, the cause (CAUSED_BY a deploy and/or service), the root cause pattern, or the summary. Edges are additive.",
        input_schema=_obj({"incident_id": _S, "status": {"enum": ["open", "mitigated", "resolved"]},
                           "severity": {"type": "integer", "minimum": 1, "maximum": 4},
                           "affected_ids": {"type": "array", "items": _S}, "cause_deploy_id": _S, "cause_service_id": _S,
                           "root_cause_id": {"type": "string", "description": "rc: id from a past incident with the same pattern."},
                           "summary": _S}, ["incident_id"])),
    "record_learned_dependency": dict(fn=record_learned_dependency, action="write",
        description="Record a service dependency that a source reveals but the graph lacks: writes a Fact (with the verbatim quote) and a DEPENDS_ON {source:'learned'} edge from caller to callee. Refused if any DEPENDS_ON already exists between the two.",
        input_schema=_obj({"from_service_id": {"type": "string", "description": "The caller."},
                           "to_service_id": {"type": "string", "description": "The service it calls."},
                           "kind": {"enum": ["sync", "async", "db", "cache"]}, "statement": _S, "confidence": _CONF,
                           "sources": _SOURCES}, ["from_service_id", "to_service_id", "kind", "statement", "confidence", "sources"])),
    "record_fact": dict(fn=record_fact, action="write",
        description="Remember a fact about services or incidents (semantic memory), with verbatim sources.",
        input_schema=_obj({"statement": _S, "about_ids": {"type": "array", "items": _S, "minItems": 1}, "confidence": _CONF,
                           "sources": _SOURCES}, ["statement", "about_ids", "confidence", "sources"])),
    "page_person": dict(fn=page_person, action="page",
        description="Page a person about an incident (simulated: recorded in the graph, nothing is sent). Refused if the person has left.",
        input_schema=_obj({"person_id": _S, "incident_id": _S, "message": _S}, ["person_id", "incident_id", "message"])),
    "open_ticket": dict(fn=open_ticket, action="write",
        description="Open an incident follow-up ticket (OPS-<n>) about a service and the incident.",
        input_schema=_obj({"title": _S, "text": _S, "service_id": _S, "incident_id": _S}, ["title", "text", "service_id", "incident_id"])),
    "flag_stale": dict(fn=flag_stale, action="write",
        description="Flag a doc or runbook as stale, with the reason (e.g. names a person who left, misses a learned dependency).",
        input_schema=_obj({"node_id": _S, "reason": _S}, ["node_id", "reason"])),
    "record_resolution": dict(fn=record_resolution, action="write",
        description="Record how an incident was resolved and by whom; sets the incident to resolved. Sources may include the incident itself.",
        input_schema=_obj({"incident_id": _S, "summary": _S, "steps": {"type": "array", "items": _S},
                           "performed_by_ids": {"type": "array", "items": _S, "minItems": 1}, "sources": _SOURCES},
                          ["incident_id", "summary", "steps", "performed_by_ids", "sources"])),
    "link_similar": dict(fn=link_similar, action="write",
        description="Link this incident to a similar past incident (or public postmortem) with a score 0..1 and a reason.",
        input_schema=_obj({"incident_id": _S, "other_id": _S, "score": _CONF, "reason": _S}, ["incident_id", "other_id", "score", "reason"])),
    "write_runbook": dict(fn=write_runbook, action="write",
        description="Write a runbook for a service. Pass supersedes_id to write the next version of an existing runbook (v2 SUPERSEDES v1).",
        input_schema=_obj({"service_id": _S, "title": _S, "steps": {"type": "array", "items": _S, "minItems": 1},
                           "sources": _SOURCES, "supersedes_id": _S}, ["service_id", "title", "steps", "sources"])),
}
