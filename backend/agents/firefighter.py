"""The Firefighter: one agent, read-only graph tools, grounded structured report.

python -m backend.agents.firefighter --service svc:payments-api --symptom "..." [--live] [--model M] [--max-steps 10]
"""
import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.agents.loop import BOLD, RST, fmt_step, new_totals, run_agent
from backend.agents.report_schema import SUBMIT_REPORT, check_report
from backend.db import get_graph
from backend.llm import LLMClient
from backend.tools.receipt import ToolContext
from backend.tools.registry import TOOLS, call

PROMPTS = Path(__file__).parent / "prompts"
RUNS = Path(__file__).resolve().parents[2] / "runs"
INR_PER_USD = 84


def read_tools(names=None):
    """Registry read tools in the loop's format."""
    return {n: {"description": t["description"], "input_schema": t["input_schema"], "action": "tool_call",
                "fn": (lambda ctx, a, n=n: call(n, a, ctx))}
            for n, t in TOOLS.items() if names is None or n in names}


def payload_message(text, payload):
    """Initial user message: instructions + one fenced JSON payload (what the mock policy parses)."""
    return f"{text}\n\n```json\n{json.dumps(payload, ensure_ascii=False, default=str)}\n```"


def utc_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def save_record(record, prefix):
    RUNS.mkdir(exist_ok=True)
    path = RUNS / f"{prefix}-{utc_stamp()}-{uuid.uuid4().hex[:4]}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str))
    return path


def run_firefighter(alert, ctx, llm, max_steps=10, on_step=None, save=True):
    t0 = time.time()
    graph = get_graph(ctx.tenant)
    tools = {**read_tools(), "submit_report": SUBMIT_REPORT}
    totals = new_totals()
    msg = payload_message("An alert fired. Investigate it with the tools and finish with submit_report.", {"alert": alert})
    rec = run_agent("firefighter", (PROMPTS / "firefighter.md").read_text(), tools, msg, ctx, llm, max_steps=max_steps,
                    validate=lambda name, report, seen: check_report(report, seen, graph), on_step=on_step,
                    totals=totals)
    record = {"run_id": f"run-{uuid.uuid4().hex[:12]}", "agent": "firefighter", "tenant": ctx.tenant, "alert": alert,
              "mode": llm.mode, "model": llm.model if llm.mode == "live" else "mock",
              "started_at": int(t0), "status": rec["status"], "report": rec["report"], "grounding": rec["grounding"],
              "totals": {**totals, "duration_ms": int((time.time() - t0) * 1000)}, "steps": rec["steps"]}
    if "abort_reason" in rec:
        record["abort_reason"] = rec["abort_reason"]
    if save:
        record["path"] = str(save_record(record, "firefighter"))
    return record


def print_report(r):
    if not r:
        print("(no report)")
        return
    lc = r.get("likely_cause") or {}
    print(f"\n{BOLD}REPORT{RST}  confidence: {r.get('confidence')}")
    print(f"  {r.get('summary')}")
    print(f"  cause:    {lc.get('service_id')}  deploy {lc.get('deploy_id')}  ticket {lc.get('ticket_key')}")
    print(f"  path:     {' -> '.join(lc.get('path') or [])}")
    print(f"  why:      {lc.get('explanation')}")
    c = r.get("contact") or {}
    print(f"  contact:  {c.get('name')} ({c.get('person_id')}): {c.get('reason')}")
    if r.get("bus_factor_warning"):
        print(f"  BUS FACTOR: {r['bus_factor_warning']}")
    if cd := r.get("conflicting_decision"):
        print(f"  conflicts with {cd['decision_id']} (source {cd['source_id']}):\n      \"{cd['excerpt']}\"\n      {cd['how_it_conflicts']}")
    for s in r.get("similar_past_incidents") or []:
        print(f"  seen before: {s['incident_id']}: {s['what_fixed_it']} (by {s['resolved_by']})")
    print(f"  blast radius: {', '.join(r.get('blast_radius') or [])}")
    for e in r.get("evidence") or []:
        print(f"  evidence: {e['node_id']}: {e['claim']}")
    for a in r.get("recommended_actions") or []:
        print(f"  -> {a}")
    for k in ("actions_taken", "learned"):
        for a in r.get(k) or []:
            print(f"  {k}: {a}")
    if r.get("status_update"):
        print(f"  status update: {r['status_update']}")


def print_totals(t):
    print(f"\ntotals: {t['llm_calls']} LLM calls, {t['tool_calls']} tool calls, tokens in {t['input_tokens']} / "
          f"out {t['output_tokens']} / cache write {t['cache_creation_input_tokens']} / cache read "
          f"{t['cache_read_input_tokens']}, cost ${t['cost_usd']:.4f} (≈ ₹{t['cost_usd'] * INR_PER_USD:.2f})"
          + (f", {t['duration_ms']} ms" if "duration_ms" in t else ""))


def main():
    ap = argparse.ArgumentParser(prog="python -m backend.agents.firefighter")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--service", help="service id, e.g. svc:payments-api")
    g.add_argument("--service-query", help="free-text service name")
    ap.add_argument("--symptom", required=True)
    ap.add_argument("--tenant", default="kestrel_pay")
    ap.add_argument("--live", action="store_true", help="use the real LLM (default: mock)")
    ap.add_argument("--model")
    ap.add_argument("--max-steps", type=int, default=10)
    ap.add_argument("--show-cypher", action="store_true")
    a = ap.parse_args()
    alert = {"service_id": a.service, "symptom": a.symptom} if a.service else {"service_query": a.service_query, "symptom": a.symptom}
    llm = LLMClient(mode="live" if a.live else None, model=a.model)
    print(f"{BOLD}Firefighter{RST} on {a.tenant} ({llm.mode}{', ' + llm.model if llm.mode == 'live' else ''}): {alert}\n")
    rec = run_firefighter(alert, ToolContext(tenant=a.tenant), llm, a.max_steps,
                          on_step=lambda s: print(fmt_step(s, a.show_cypher)))
    print_report(rec["report"])
    print(f"\nstatus: {rec['status']}" + (f" ({rec['abort_reason']})" if rec.get("abort_reason") else "")
          + f"   grounding ok: {rec['grounding']['ok']}" + (f" ungrounded: {rec['grounding']['ungrounded_ids']}" if rec['grounding']['ungrounded_ids'] else ""))
    print_totals(rec["totals"])
    print(f"record: {rec['path']}")


if __name__ == "__main__":
    main()
