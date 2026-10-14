"""The three-agent team: Triage -> Investigator -> Communicator, handing off through the graph.

Each agent starts with a FRESH conversation containing only the alert plus get_incident_state output, and ends with
its submit tool, which is persisted as a handoff Step. All steps are written to the graph as they happen.

python -m backend.agents.team run --service svc:payments-api --symptom "..." [--live] [--tenant T] [--user U]
python -m backend.agents.team resolve INC-2026-032 --by per:priya-nair --summary "..."
python -m backend.agents.team state INC-2026-032
"""
import argparse
import json
import time
import uuid

from backend.agents.firefighter import (PROMPTS, payload_message, print_report, print_totals, read_tools,
                                        save_record)
from backend.agents.loop import BOLD, CYAN, RST, fmt_step, new_totals, run_agent
from backend.agents.report_schema import REPORT_PROPS, _obj, check_report, grounding_problems
from backend.db import get_graph
from backend.llm import LLMClient
from backend.memory.sessions import StepLog, end_session, session_incident, start_session
from backend.tools.memory_tools import MEMORY_TOOLS
from backend.tools.receipt import ToolContext
from backend.tools.registry import call

SUBMIT_HANDOFF = {"action": "handoff",
                  "description": "Finish your part: hand off to the next agent. `note` is the human-readable handoff; "
                                 "`details` the structured findings. Every id must have come back from a tool.",
                  "input_schema": {"type": "object", "properties": {"note": {"type": "string"}, "details": {"type": "object"}},
                                   "required": ["note", "details"], "additionalProperties": False}}
TEAM_REPORT_SCHEMA = _obj({**REPORT_PROPS,
                           "actions_taken": {"type": "array", "items": {"type": "string"}},
                           "learned": {"type": "array", "items": {"type": "string"}},
                           "status_update": {"type": "string", "description": "2-3 sentences for the incident channel."}})
SUBMIT_TEAM_REPORT = {"action": "handoff", "input_schema": TEAM_REPORT_SCHEMA,
                      "description": "Submit the final incident report (with actions_taken, learned and a status_update). "
                                     "Call exactly once, at the end. Ids must come from tools; excerpts must be verbatim."}

AGENTS = {
    "triage": dict(read=["find_service", "blast_radius", "critical_services", "past_incidents", "get_incident_state"],
                   write=["open_incident", "update_incident"], submit=("submit_handoff", SUBMIT_HANDOFF)),
    "investigator": dict(read=["memory_recall", "recent_changes_downstream", "shared_dependency_changes", "dependency_path", "decisions_about",
                               "read_source", "past_incidents", "who_to_call", "node_details", "get_incident_state"],
                         write=["update_incident", "record_learned_dependency", "record_fact", "link_similar"],
                         submit=("submit_handoff", SUBMIT_HANDOFF)),
    "communicator": dict(read=["who_to_call", "stale_knowledge", "get_incident_state"],
                         write=["page_person", "open_ticket", "flag_stale"], submit=("submit_report", SUBMIT_TEAM_REPORT)),
    "postmortem": dict(read=["get_incident_state", "past_incidents", "search_knowledge", "read_source"],
                       write=["update_incident", "record_resolution", "link_similar", "write_runbook"],
                       submit=("submit_handoff", SUBMIT_HANDOFF)),
}
TASK = {
    "triage": "An alert fired. Assess it, open the incident and hand off to the Investigator.",
    "investigator": "Find the cause of this incident, record what you learn, and hand off to the Communicator.",
    "communicator": "Notify the right person, open the follow-up, flag stale knowledge and submit the final report.",
    "postmortem": "The operator resolved this incident. Record the resolution, link similar incidents and improve the runbook.",
}


def memory_tools(names):
    return {n: {**{k: MEMORY_TOOLS[n][k] for k in ("description", "input_schema", "action")},
                "fn": (lambda ctx, a, n=n: call(n, a, ctx, MEMORY_TOOLS))} for n in names}


def agent_tools(persona):
    cfg = AGENTS[persona]
    name, spec = cfg["submit"]
    return {**read_tools(cfg["read"]), **memory_tools(cfg["write"]), name: spec}


def validator(graph):
    def validate(name, args, seen):
        if name == "submit_report":
            return check_report(args, seen, graph, TEAM_REPORT_SCHEMA)
        p = grounding_problems(args, seen, graph)
        if not str(args.get("note") or "").strip():
            p = {"errors": p.get("errors", []) + ["note must be non-empty"], "ungrounded_ids": p.get("ungrounded_ids", [])}
        return p
    return validate


def incident_ref(x):
    """'INC-2026-032' or 'inc:2026-032' -> 'inc:2026-032'."""
    return x if x.startswith("inc:") else "inc:" + x[4:].lower() if x.upper().startswith("INC-") else x


def time_to_cause(steps):
    """LLM calls and tool calls until update_incident set a cause: from session start, and by the agent that set it
    (agent_tool_calls: the Investigator's own calls, i.e. how fast it named the culprit)."""
    for n, s in enumerate(steps, 1):
        if s["tool"] == "update_incident" and "error" not in s["result"] and (
                s["args"].get("cause_deploy_id") or s["args"].get("cause_service_id")):
            mine = sum(1 for x in steps[:n] if x["agent"] == s["agent"])
            return {"llm_calls": s["llm_call"], "tool_calls": n, "agent": s["agent"], "agent_tool_calls": mine}
    return None


def step_events(step):
    """The SSE events one step produces (shared by live runs and golden replays)."""
    out = [("step", {k: step.get(k) for k in ("seq", "agent", "action", "tool", "args", "summary", "receipt", "ts", "ms")})]
    if step["action"] in ("write", "page"):
        out.append(("write", {"agent": step["agent"], "tool": step["tool"], "summary": step["summary"],
                              "queries": step["receipt"]["queries"]}))
    elif step["action"] == "handoff":
        out.append(("handoff", {"agent": step["agent"], "note": step["summary"], "seq": step["seq"]}))
    return out


class Run:
    """Shared plumbing for a team run / resolve: session, live step log, events, totals."""

    def __init__(self, tenant, user, llm, on_event, incident_id=None):
        self.ctx = ToolContext(tenant=tenant)
        self.ctx.session_id = start_session(tenant, user, "team", incident_id)
        self.log, self.llm, self.on_event = StepLog(tenant, self.ctx.session_id), llm, on_event or (lambda t, d: None)
        self.graph, self.steps, self.totals, self.agents, self.t0 = get_graph(tenant), [], new_totals(), [], time.time()

    def emit(self, typ, data):
        self.on_event(typ, data)

    def on_step(self, step):
        self.log(step)
        self.steps.append(step)
        for typ, data in step_events(step):
            self.emit(typ, data)

    def agent(self, agent, persona, payload, max_steps):
        msg = payload_message(TASK[persona], payload)
        self.emit("agent", {"agent": agent, "persona": persona})
        rec = run_agent(agent, (PROMPTS / f"{persona}.md").read_text(), agent_tools(persona), msg, self.ctx, self.llm,
                        max_steps=max_steps, validate=validator(self.graph), on_step=self.on_step, totals=self.totals,
                        seq_start=len(self.steps), persona=persona)
        self.agents.append({k: rec.get(k) for k in ("agent", "status", "grounding", "report", "abort_reason")} | {"persona": persona})
        return rec

    def state(self, incident_id):
        return call("get_incident_state", {"incident_id": incident_id}, self.ctx).result if incident_id else None

    def record(self, kind, status, **extra):
        rec = {"run_id": f"run-{uuid.uuid4().hex[:12]}", "agent": kind, "tenant": self.ctx.tenant,
               "mode": self.llm.mode, "model": self.llm.model if self.llm.mode == "live" else "mock",
               "session_id": self.ctx.session_id, "started_at": int(self.t0), "status": status, **extra,
               "agents": self.agents, "time_to_cause": time_to_cause(self.steps),
               "totals": {**self.totals, "duration_ms": int((time.time() - self.t0) * 1000)}, "steps": self.steps}
        end_session(self.ctx.tenant, self.ctx.session_id, "done" if status == "ok" else status)
        return rec


def run_team(alert, tenant="kestrel_pay", user="jaya", llm=None, on_event=None, max_steps=8, save=True):
    """alert = {service_id, symptom}. Returns the team run record."""
    llm = llm or LLMClient()
    run, status, report = Run(tenant, user, llm, on_event), "ok", None
    try:
        for agent in ("triage", "investigator", "communicator"):
            inc = session_incident(tenant, run.ctx.session_id)
            rec = run.agent(agent, agent, {"alert": alert, "incident_state": run.state(inc) or
                                           "no incident open yet (Triage opens it)"}, max_steps)
            if rec["status"] != "ok":
                status = rec["status"]
                break
            report = rec["report"] if agent == "communicator" else report
    except Exception as e:  # never leave a session 'running'
        status = "error"
        run.emit("error", {"error": f"{type(e).__name__}: {e}"})
        if not save:
            raise
    inc = session_incident(tenant, run.ctx.session_id)
    out = run.record("team", status, alert=alert, user=user, incident_id=inc,
                     incident_key=(run.state(inc) or {}).get("key"), report=report)
    run.emit("report", {"report": report, "incident_id": inc, "time_to_cause": out["time_to_cause"]})
    run.emit("done", {"status": status, "session_id": out["session_id"], "totals": out["totals"]})
    if save:
        out["path"] = str(save_record(out, "team"))
    return out


def resolve_incident(incident_id, resolved_by_ids, what_fixed_it, tenant="kestrel_pay", llm=None, user="operator",
                     on_event=None, max_steps=8, save=True):
    """Operator action: a short Communicator pass in postmortem mode (Resolution, Runbook v2, SIMILAR_TO links)."""
    llm = llm or LLMClient()
    incident_id = incident_ref(incident_id)
    run = Run(tenant, user, llm, on_event, incident_id)
    payload = {"incident_state": run.state(incident_id),
               "operator": {"resolved_by_ids": list(resolved_by_ids), "what_fixed_it": what_fixed_it}}
    rec = run.agent("communicator", "postmortem", payload, max_steps)
    out = run.record("resolve", rec["status"], incident_id=incident_id, operator=payload["operator"], report=rec["report"])
    run.emit("done", {"status": rec["status"], "session_id": out["session_id"]})
    if save:
        out["path"] = str(save_record(out, "resolve"))
    return out


# ───────────── CLI ─────────────
def tracer(show_cypher):
    def on_event(typ, d):
        if typ == "agent":
            print(f"\n{BOLD}── {d['agent'].upper()}" + (f" ({d['persona']})" if d["persona"] != d["agent"] else "") + f" ──{RST}")
        elif typ == "step":
            print(fmt_step(d, show_cypher))
            if d["action"] == "handoff":
                print(f"{CYAN}    note: {d['summary']}{RST}")
        elif typ == "error":
            print(f"ERROR: {d['error']}")
    return on_event


def print_ttc(rec):
    t = rec.get("time_to_cause")
    print("time to cause: " + (f"{t['llm_calls']} LLM calls, {t['tool_calls']} tool calls (set by {t['agent']})" if t else "cause not set"))


def main():
    ap = argparse.ArgumentParser(prog="python -m backend.agents.team")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--service", required=True)
    r.add_argument("--symptom", required=True)
    s = sub.add_parser("resolve")
    s.add_argument("incident")
    s.add_argument("--by", required=True, nargs="+", help="person ids, e.g. per:priya-nair")
    s.add_argument("--summary", required=True, help="what fixed it, in the operator's words")
    st = sub.add_parser("state")
    st.add_argument("incident")
    for p in (r, s, st):
        p.add_argument("--tenant", default="kestrel_pay")
    for p in (r, s):
        p.add_argument("--user", default="jaya")
        p.add_argument("--live", action="store_true")
        p.add_argument("--model")
        p.add_argument("--show-cypher", action="store_true")
    a = ap.parse_args()
    if a.cmd == "state":
        print(json.dumps(call("get_incident_state", {"incident_id": incident_ref(a.incident)}, ToolContext(tenant=a.tenant)).result,
                         indent=2, ensure_ascii=False, default=str))
        return
    llm = LLMClient(mode="live" if a.live else None, model=a.model)
    if a.cmd == "run":
        rec = run_team({"service_id": a.service, "symptom": a.symptom}, a.tenant, a.user, llm, tracer(a.show_cypher))
        print_report(rec["report"])
        print(f"\nincident: {rec['incident_key']} ({rec['incident_id']})   status: {rec['status']}")
        print_ttc(rec)
    else:
        rec = resolve_incident(a.incident, a.by, a.summary, a.tenant, llm, a.user, tracer(a.show_cypher))
        print(f"\nstatus: {rec['status']}")
    print_totals(rec["totals"])
    print(f"session: {rec['session_id']}   record: {rec['path']}")


if __name__ == "__main__":
    main()
