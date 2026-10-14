"""Sessions and Steps, persisted live.

start_session(...) writes a Session node. StepLog(tenant, session_id) is the run loop's on_step hook: every step is
written as a Step node AS IT HAPPENS, IN_SESSION the session, NEXT from the previous step, CITED -> every highlighted
node of its receipt that exists, with the receipt's cypher and params. Handoff steps carry the note as summary and the
full submit input (note + structured details) in params_json, which is how get_incident_state hands them on.
"""
import json
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone

from backend.db import get_graph
from backend.tools.receipt import clip
from seed.schema import PREFIX_TO_LABEL

Q_SESSION = """MERGE (s:Session {id:$id}) ON CREATE SET s.user = $user, s.mode = $mode, s.status = 'running',
  s.started_at = $now, s.origin = 'agent', s.created_at = $now"""
Q_SESSION_INC = """MATCH (s:Session {id:$id}), (i:Incident {id:$inc})
MERGE (s)-[r:FOR_INCIDENT]->(i) ON CREATE SET r.origin = 'agent', r.created_at = $now"""
Q_STEP = """MATCH (ses:Session {id:$ses})
MERGE (st:Step {id:$id}) ON CREATE SET st += $props
MERGE (st)-[r:IN_SESSION]->(ses) ON CREATE SET r.origin = 'agent', r.created_at = $now"""
Q_NEXT = """MATCH (a:Step {id:$prev}), (b:Step {id:$id})
MERGE (a)-[r:NEXT]->(b) ON CREATE SET r.origin = 'agent', r.created_at = $now"""
Q_CITED = """UNWIND $ids AS cid
MATCH (st:Step {id:$id}), (n:__LABEL__ {id:cid})
MERGE (st)-[r:CITED]->(n) ON CREATE SET r.origin = 'agent', r.created_at = $now"""
Q_END = "MATCH (s:Session {id:$id}) SET s.status = $status, s.ended_at = $now"


def start_session(tenant, user, mode, incident_id=None):
    sid = f"ses:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(3)}"
    g, now = get_graph(tenant), int(time.time())
    g.query(Q_SESSION, {"id": sid, "user": user, "mode": mode, "now": now})
    if incident_id:
        g.query(Q_SESSION_INC, {"id": sid, "inc": incident_id, "now": now})
    return sid


def end_session(tenant, session_id, status="done"):
    get_graph(tenant).query(Q_END, {"id": session_id, "status": status, "now": int(time.time())})


def session_incident(tenant, session_id):
    rows = get_graph(tenant).ro_query("MATCH (:Session {id:$id})-[:FOR_INCIDENT]->(i:Incident) RETURN i.id ORDER BY i.started_at",
                                      {"id": session_id}).result_set
    return rows[0][0] if rows else None


def step_id(session_id, seq):
    return f"step:{session_id.split(':', 1)[1]}-{seq:03d}"


class StepLog:
    """on_step hook. Steps must arrive in seq order (the orchestrator passes seq_start to every agent)."""

    def __init__(self, tenant, session_id):
        self.graph, self.session_id, self.prev = get_graph(tenant), session_id, None

    def __call__(self, step):
        now = int(time.time())
        sid = step_id(self.session_id, step["seq"])
        queries = step["receipt"].get("queries", [])
        detail = step["args"] if step["action"] in ("handoff", "answer") or not queries else [q["params"] for q in queries]
        props = {"seq": step["seq"], "agent": step["agent"], "action": step["action"], "tool": step["tool"],
                 "cypher": ";\n".join(q["cypher"] for q in queries) or None,
                 "params_json": json.dumps(detail, ensure_ascii=False, default=str),
                 "summary": clip(step["summary"], 900), "ts": step["ts"], "origin": "agent", "created_at": now}
        self.graph.query(Q_STEP, {"ses": self.session_id, "id": sid, "now": now,
                                  "props": {k: v for k, v in props.items() if v is not None}})
        if self.prev:
            self.graph.query(Q_NEXT, {"prev": self.prev, "id": sid, "now": now})
        self.prev = sid
        by_label = defaultdict(list)
        for nid in step["receipt"].get("highlight", {}).get("nodes", []):
            label = PREFIX_TO_LABEL.get(str(nid).split(":", 1)[0])
            if label and nid != sid:
                by_label[label].append(nid)
        for label, ids in by_label.items():  # MATCH only existing nodes: CITED never dangles
            self.graph.query(Q_CITED.replace("__LABEL__", label), {"id": sid, "ids": ids, "now": now})
        step["step_id"] = sid
