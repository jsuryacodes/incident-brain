"""Approve and execute a Firefighter action plan (simulated), then verify.

execute(graph, record, action_ids, user) runs the approved actions of a Firefighter run's `action_plan` on the graph
the run used (always an internal twin graph, never a hero company graph), then re-runs the graph checks to report
whether the signal cleared. Simulated: no pager, no CI system. What it writes uses existing labels with
origin 'agent': an Incident per incident (open_incident / update_incident), the pages (page_person), the follow-up
ticket (open_ticket), stale flags (flag_stale), a rollback Deploy that CHANGED the service, and one Step per action
(agent 'communicator', the acting role) in a Session (mode 'firefighter') whose id is derived from the run, so a second
approval of the same run does nothing (idempotent).
"""
import time

from backend.db import base_tenant, get_graph
from backend.memory.sessions import Q_END, Q_SESSION, StepLog
from backend.tools.memory_tools import MEMORY_TOOLS
from backend.tools.receipt import Recorder, ToolContext, clip
from backend.tools.registry import call

Q_ROLLBACK = """MATCH (d:Deploy {id:$dep})-[:CHANGED]->(s:Service)
MERGE (r:Deploy {id:$id}) ON CREATE SET r.version = $version, r.ts = $now, r.summary = $summary,
      r.origin = 'agent', r.created_at = $now
MERGE (r)-[c:CHANGED]->(s) ON CREATE SET c.origin = 'agent', c.created_at = $now
RETURN r.id, s.id"""
Q_EXISTS = "MATCH (s:Session {id:$id}) RETURN s.status"
Q_SESSION_STEPS = "MATCH (st:Step)-[:IN_SESSION]->(:Session {id:$id}) RETURN st.seq, st.tool, st.summary ORDER BY st.seq"


def session_id(run_id):
    return f"ses:exec-{run_id}"


def _incidents(report, alerts):
    if report.get("incidents"):
        return report["incidents"]
    return [{"alerts": [a["service_id"] for a in alerts], **{k: report.get(k) for k in ("likely_cause", "contact", "root")}}]


def execute(graph, record, action_ids=None, user="operator"):
    """-> {session_id, already_executed, results[], verification}. Raises PermissionError on a hero graph."""
    if base_tenant(graph) == graph:
        raise PermissionError("actions only execute on the run's own copy of the company (a twin graph), never on "
                              "the hero graph")
    report = record.get("report") or {}
    plan = report.get("action_plan") or []
    chosen = [a for a in plan if action_ids is None or a["id"] in action_ids]
    sid, g, now = session_id(record["run_id"]), get_graph(graph), int(time.time())
    if g.ro_query(Q_EXISTS, {"id": sid}).result_set:
        return {"session_id": sid, "already_executed": True,
                "results": [{"seq": a, "tool": b, "summary": c} for a, b, c in g.ro_query(Q_SESSION_STEPS, {"id": sid}).result_set],
                "verification": None}
    g.query(Q_SESSION, {"id": sid, "user": user, "mode": "firefighter", "now": now})
    ctx = ToolContext(tenant=graph, session_id=sid)
    log, steps, results = StepLog(graph, sid), [], []
    alerts = record["alert"] if isinstance(record.get("alert"), list) else [record.get("alert") or {}]
    symptoms = {a.get("service_id"): a.get("symptom") for a in alerts}

    def step(tool, args, out, action="write", summary=None):
        st = {"seq": len(steps) + 1, "agent": "communicator", "action": action if "error" not in out.result else "tool_call",
              "tool": tool, "args": args, "result": out.result, "receipt": out.receipt, "ts": int(time.time()),
              "summary": summary or out.result.get("summary") or out.result.get("error") or tool,
              "why": f"approved by {user}"}
        log(st)
        steps.append(st)
        return out.result

    # one Incident per incident of the report (pages and tickets hang on it)
    inc_ids = []
    for k, inc in enumerate(_incidents(report, alerts)):
        if not any(a["incident"] == k for a in chosen):
            inc_ids.append(None)
            continue
        first = inc["alerts"][0]
        r = step("open_incident", a := {"service_id": first, "symptom": symptoms.get(first) or "alert",
                                        "severity": 1 if len(inc["alerts"]) >= 3 else 2},
                 call("open_incident", a, ctx, MEMORY_TOOLS))
        iid = r.get("id")
        inc_ids.append(iid)
        lc, root = inc.get("likely_cause") or {}, inc.get("root") or {}
        upd = {"incident_id": iid, "affected_ids": inc["alerts"]}
        if lc.get("deploy_id"):
            upd.update(cause_deploy_id=lc["deploy_id"], cause_service_id=lc["service_id"])
        elif root.get("service_id"):
            upd.update(cause_service_id=root["service_id"])
        if iid:
            step("update_incident", upd, call("update_incident", upd, ctx, MEMORY_TOOLS))
    for a in chosen:
        iid = inc_ids[a["incident"]] if a["incident"] < len(inc_ids) else None
        kind = a["kind"]
        if kind == "page" and iid:
            args = {"person_id": a["target"], "incident_id": iid, "message": a["justification"]["why"][:280]}
            res = step("page_person", args, call("page_person", args, ctx, MEMORY_TOOLS), "page")
        elif kind == "open_ticket" and iid:
            args = {"service_id": a["target"], "incident_id": iid, "title": a["title"].replace("Open a follow-up ticket for ", "Follow-up: "),
                    "text": a["justification"]["why"]}
            res = step("open_ticket", args, call("open_ticket", args, ctx, MEMORY_TOOLS))
        elif kind == "flag_stale":
            args = {"node_id": a["target"], "reason": a["justification"]["why"]}
            res = step("flag_stale", args, call("flag_stale", args, ctx, MEMORY_TOOLS))
        elif kind == "rollback":
            rec = Recorder(ctx, "rollback", {"deploy_id": a["target"]})
            rid = a["target"] + "-rollback"
            rows = rec.w(Q_ROLLBACK, {"dep": a["target"], "id": rid, "version": "rollback of " + a["target"].split("-v")[-1],
                                      "summary": f"Rollback of {a['target']} (simulated, approved by {user})", "now": int(time.time())})
            if rows:
                rec.hl_edge(rid, "CHANGED", rows[0][1])
            out = rec.done({"rolled_back": a["target"], "rollback_deploy": rid, "simulated": True,
                            "summary": f"rolled back {a['target']} (simulated): wrote {rid}"}) if rows else rec.error("deploy not found")
            res = step("rollback", {"deploy_id": a["target"]}, out)
        else:  # hold / escalate / suppress_page / notify: a decision, recorded as a Step
            rec = Recorder(ctx, kind, {"target": a["target"]})
            rec.hl(*a["justification"]["node_ids"][:4])
            res = step(kind, {"target": a["target"]}, rec.done({"summary": f"{a['title']}: {clip(a['justification']['why'], 200)}"}),
                       "page" if kind in ("escalate", "suppress_page") else "write")
        results.append({"action": a["id"], "kind": kind, "title": a["title"], "ok": "error" not in res,
                        "summary": res.get("summary") or res.get("error")})
    g.query(Q_END, {"id": sid, "status": "done", "now": int(time.time())})
    return {"session_id": sid, "already_executed": False, "results": results, "incidents": [i for i in inc_ids if i],
            "verification": verify(graph, record, chosen), "steps": steps}


def verify(graph, record, chosen):
    """Re-run the checks: after a (simulated) rollback, is the bad change still the newest one on the call path? A page
    or a suppression can't clear a signal: say so instead of pretending."""
    ctx, checks, cleared = ToolContext(tenant=graph), [], []
    report = record.get("report") or {}
    alerts = record["alert"] if isinstance(record.get("alert"), list) else [record.get("alert") or {}]
    for k, inc in enumerate(_incidents(report, alerts)):
        rb = next((a for a in chosen if a["incident"] == k and a["kind"] == "rollback"), None)
        lc = inc.get("likely_cause") or {}
        if not rb:
            checks.append({"incident": k, "cleared": False, "summary": (
                f"no rollback approved for {lc['deploy_id']}: the signal stays until someone acts" if lc.get("deploy_id") else
                "no change to roll back (a shared root under load): paging its owner is the action; the signal stays "
                "until they relieve the load")})
            cleared.append(False)
            continue
        first = inc["alerts"][0]
        out = call("recent_changes_downstream", {"service_id": first, "since_minutes": 120, "max_hops": 6}, ctx)
        newest = next((h for h in out.result.get("hits", []) if h["service"] == lc["service_id"]), None)
        ok = bool(newest) and newest["deploy"]["id"] == rb["target"] + "-rollback"
        checks.append({"incident": k, "cleared": ok, "tool": "recent_changes_downstream", "queries": out.receipt["queries"],
                       "summary": (f"the newest change on {lc['service_id']} is now the rollback ({rb['target']}-rollback): "
                                   "the bad change is reverted (simulated), so the signal should clear" if ok else
                                   f"{rb['target']} is still the newest change on {lc['service_id']}: not cleared")})
        cleared.append(ok)
    return {"checks": checks, "all_cleared": all(cleared) if cleared else False, "simulated": True}
