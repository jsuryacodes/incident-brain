"""The whole demo storyline, mock by default.

python -m backend.demo story [--graph kestrel_pay] [--live] [--quiet]
python -m backend.demo story --compare-no-memory      # also Session 2 on a fresh seed WITHOUT Session 1, for contrast
"""
import argparse
import json
from pathlib import Path

from backend.agents.loop import BOLD, CYAN, RST
from backend.agents.firefighter import print_report
from backend.agents.team import resolve_incident, run_team, tracer
from backend.agents.actions import execute
from backend.agents.firefighter import run_firefighter
from backend.agents.brain import ask
from backend.api import views
from backend.api.views import run_graph
from backend.agents.loop import fmt_step
from backend.db import allowed_tenants, eval_twin, get_graph, nomem_twin
from backend.tools.receipt import ToolContext
from seed.eval_scenarios import BY_ID as SCENARIOS
from backend.llm import LLMClient
from seed import scenario
from seed.load import load, package_for

S1_ALERT = {"service_id": "svc:payments-api", "symptom": "5xx rate 12% and p99 4.1s on payments-api for the last 15 minutes"}
S2_ALERT = {"service_id": "svc:payouts-service", "symptom": "payout batch API 5xx 9% and p99 3.2s for the last 10 minutes"}
FIX = "Priya rolled back RULES_CACHE_TTL to 300s; config-service load recovered"
BROWSER_CYPHER = "MATCH (n {origin:'agent'})-[r]-(m) RETURN n,r,m"
GOLDEN = Path(__file__).resolve().parents[1] / "runs" / "golden"


GOLDEN_FILES = (("s1", "team-session1"), ("resolve", "resolve-session1"), ("s2", "team-session2"),
                ("s2_nomem", "team-session2-nomem"), ("storm", "firefighter-storm"))
STORM = SCENARIOS["k-storm"]  # the alert-storm beat replays this eval scenario (seed/eval_scenarios.py)


def save_golden(out):
    """Recorded runs for the UI's replays (no LLM needed to show the demo). Each embeds its graph snapshot."""
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for key, name in GOLDEN_FILES:
        if key in out:
            rec = {k: v for k, v in out[key].items() if k != "path"}
            (GOLDEN / f"{name}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False, default=str))


def snap(graph, rec):
    """Attach the run's graph snapshot right after it ran (later beats change the graph)."""
    rec["graph"] = run_graph(graph, rec)
    return rec


# ───────────── the story as the web UI plays it ─────────────
BEATS = [
    {"id": "session1", "label": "Fire alert", "kind": "team", "alert": S1_ALERT, "replay": "team-session1",
     "title": "Session 1", "caption": "The team investigates a payments-api alert with no memory yet."},
    {"id": "resolve", "label": "Resolve", "kind": "resolve", "continues": "session1", "replay": "resolve-session1",
     "title": "Resolve", "resolver": {"ids": ["per:priya-nair"], "name": "Priya Nair"}, "summary": FIX,
     "caption": "Priya fixes it. The resolution, Runbook v2 and industry matches are written to the graph."},
    {"id": "session2", "label": "Fire Session 2", "kind": "team", "alert": S2_ALERT, "replay": "team-session2",
     "title": "Session 2", "caption": "A different service alerts. The Investigator asks memory first."},
    {"id": "compare", "label": "Compare without memory", "kind": "team", "alert": S2_ALERT, "memory": False,
     "replay": "team-session2-nomem", "title": "Session 2, no memory",
     "caption": "The same alert on a fresh copy of the company without Session 1's memory."},
]
STORM_BEAT = {"id": "storm", "label": "Alert storm", "kind": "firefighter", "alerts": STORM["alerts"], "memory": False,
              "replay": "firefighter-storm", "title": "Alert storm",
              "caption": f"{len(STORM['alerts'])} alerts fire at once. The Firefighter asks the graph which ones share a cause "
                         "before anyone is paged."}


def tenant_name(tenant):
    return " ".join(w.capitalize() for w in tenant.split("_"))


def has_story(tenant):
    try:
        return package_for(tenant) == "kestrel_pay"
    except ValueError:
        return False


def story_meta(tenant):
    """What the UI's Story view renders: the beats, their button labels, alerts and the resolve step."""
    if not has_story(tenant):
        return {"tenant": tenant, "name": tenant_name(tenant), "has_story": False, "beats": []}
    return {"tenant": tenant, "name": tenant_name(tenant), "has_story": True, "beats": BEATS, "storm": STORM_BEAT,
            "intro": "An alert fires. Three agents (Triage, Investigator, Communicator) find the cause in the company "
                     "graph, show every query they ran, and write what they learned back into it."}


def golden(name):
    path = GOLDEN / f"{Path(name).stem}.json"
    return json.loads(path.read_text()) if path.parent == GOLDEN and path.is_file() else None


def storm_twin(tenant):
    return eval_twin(tenant, "story_storm")


def run_storm(tenant, llm=None, on_step=None, keep=False):
    """The alert-storm beat: the storm fixture on a fresh twin of the company (never the hero graph, whose memory would
    change the answer), one read-only Firefighter run, the graph snapshot. The twin is deleted unless keep."""
    twin = storm_twin(tenant)
    summary = load(twin, reset=True, data_package=package_for(tenant), quiet=True, transform=storm_fixture())
    try:
        rec = run_firefighter(STORM["alerts"], ToolContext(tenant=twin, now=summary["now"]), llm or LLMClient(),
                              on_step=on_step, save=False)
        rec["twin"] = twin  # where the plan can be approved and executed (kept only when keep=True)
        return snap(twin, rec)
    finally:
        if not keep:
            get_graph(twin).delete()


def storm_fixture():
    from seed.eval_scenarios import fixture
    return fixture(STORM)


def run_beat(tenant, beat_id, llm, on_event, latest):
    """A FRESH run of one beat (it writes to the graph; the API only allows it with an access code).
    latest: {beat_id: record} of this tenant's earlier fresh beats. Returns the record with its graph snapshot."""
    if beat_id == "storm":  # the twin stays until the next storm run, so the action plan can be approved
        rec = run_storm(tenant, llm, on_step=lambda st: on_event("step", st), keep=True)
        on_event("report", {"report": rec["report"], "incident_id": None, "time_to_cause": None})
        on_event("done", {"status": rec["status"], "session_id": None, "totals": rec["totals"]})
        return rec
    beat = next(b for b in BEATS if b["id"] == beat_id)
    if beat_id == "session1":
        load(tenant, reset=True, data_package=package_for(tenant), quiet=True)
        return snap(tenant, run_team(beat["alert"], tenant, "web", llm, on_event))
    if beat_id == "resolve":
        s1 = latest.get("session1")
        if not s1 or not s1.get("incident_id"):
            raise LookupError("run Session 1 first: there is no incident to resolve")
        return snap(tenant, resolve_incident(s1["incident_id"], beat["resolver"]["ids"], beat["summary"], tenant, llm,
                                             "web", on_event))
    if beat_id == "session2":
        scenario.apply("session2", tenant)
        return snap(tenant, run_team(beat["alert"], tenant, "web", llm, on_event))
    twin = nomem_twin(tenant)  # compare: the same alert on a fresh copy without Session 1's memory
    load(twin, reset=True, data_package=package_for(tenant), quiet=True)
    try:
        scenario.apply("session2", twin)
        return snap(twin, run_team(beat["alert"], twin, "web", llm, on_event))
    finally:
        get_graph(twin).delete()


def banner(t):
    print(f"\n{BOLD}{'=' * 8} {t} {'=' * 8}{RST}")


def memory_summary(graph):
    g = get_graph(graph)
    nodes = dict(g.ro_query("MATCH (n {origin:'agent'}) RETURN labels(n)[0], count(n) ORDER BY labels(n)[0]").result_set)
    learned = [{"from": a, "to": b, "fact": f} for a, b, f in g.ro_query(
        "MATCH (a:Service)-[r:DEPENDS_ON {source:'learned'}]->(b:Service) RETURN a.id, b.id, r.learned_from").result_set]
    return {"agent_nodes": nodes, "learned_edges": learned}


def s2_learned_hit(rec):
    """The shared_dependency_changes hit that found the culprit through a learned edge, if any."""
    for s in rec["steps"]:
        if s["tool"] == "shared_dependency_changes":
            return next((h for h in s["result"].get("hits", []) if h.get("uses_learned_edge")), None)
    return None


ISOLATION_Q = "Why must RULES_CACHE_TTL stay at 300 seconds?"


def switch_tenant(other, llm):
    """Tenant isolation: the other company's graph has none of this memory and doesn't know the answer."""
    g = get_graph(other)
    before = g.ro_query("MATCH (n {origin:'agent'}) RETURN count(n)").result_set[0][0]
    learned = g.ro_query("MATCH ()-[r:DEPENDS_ON {source:'learned'}]->() RETURN count(r)").result_set[0][0]
    r = ask(other, "jaya", ISOLATION_Q, llm=llm)
    return {"tenant": other, "agent_nodes_before": before, "learned_edges": learned, "question": ISOLATION_Q,
            "answer": r["answer"], "citations": r["citations"]}


def handoffs_only(typ, d):
    """--quiet tracer: only the notes agents leave each other."""
    if typ == "handoff":
        print(f"{CYAN}  {d['agent']}: {d['note']}{RST}")


def story(graph="kestrel_pay", llm=None, quiet=False, compare_no_memory=False, other="northwind_health"):
    """The whole story. compare_no_memory: first run Session 2 on a fresh seed WITHOUT Session 1 (the contrast),
    then the normal story, so the summary box shows all three. quiet: print only session headers, handoffs and the
    summary box (verbose prints every step)."""
    if package_for(graph) != "kestrel_pay":
        raise ValueError(f"the demo story is Kestrel Pay's; {graph!r} would be seeded with another company's data")
    llm = llm or LLMClient()
    ev = handoffs_only if quiet else tracer(False)
    say = (lambda *a: None) if quiet else print
    other = other if other in allowed_tenants() and other != graph else None
    out = {}
    if compare_no_memory:
        banner("0. Contrast: Session 2 on a fresh seed, WITHOUT Session 1's memory")
        load(graph, reset=True, data_package="kestrel_pay", quiet=True)
        say(f"added {scenario.apply('session2', graph)}")
        out["s2_nomem"] = snap(graph, run_team(S2_ALERT, graph, "jaya", llm, ev))
        if not quiet:
            print_report(out["s2_nomem"]["report"])
    if not quiet:
        banner(f"1. Re-seed {graph}" + (f" and {other}" if other else ""))
    load(graph, reset=True, data_package="kestrel_pay", quiet=True)
    if other:
        load(other, reset=True, data_package="northwind_health", quiet=True)
    banner("2. Session 1: payments-api alert, the team investigates")
    out["s1"] = snap(graph, run_team(S1_ALERT, graph, "jaya", llm, ev))
    if not quiet:
        print_report(out["s1"]["report"])
    banner("3. Operator: resolved by Priya")
    out["resolve"] = snap(graph, resolve_incident(out["s1"]["incident_id"], ["per:priya-nair"], FIX, graph, llm, "jaya", ev))
    if not quiet:
        banner("4. World event: risk-rules v2.8.1 ships (scenario session2)")
    say(f"added {scenario.apply('session2', graph)}")
    banner("5. Session 2: payouts-service alert, with memory")
    out["s2"] = snap(graph, run_team(S2_ALERT, graph, "jaya", llm, ev))
    if not quiet:
        print_report(out["s2"]["report"])
    out.update(memory_summary(graph))
    out["s2_learned_hit"] = s2_learned_hit(out["s2"])
    if other:
        out["switch_tenant"] = switch_tenant(other, llm)
    print_summary(out)
    return out


def _ttc(rec):
    t = rec.get("time_to_cause")
    return (f"{t['tool_calls']} total, {t['agent_tool_calls']} by {t['agent']}" if t else "cause NOT found",
            f"{t['llm_calls']}" if t else "-")


def print_summary(out):
    banner("6. Summary: before / after memory")
    runs = [("Session 1", out["s1"]), ("Session 2", out["s2"])] + (
        [("Session 2, no memory", out["s2_nomem"])] if "s2_nomem" in out else [])
    rows = [("",) + tuple(n for n, _ in runs),
            ("alert",) + tuple(svc_name(r["alert"]["service_id"]) for _, r in runs),
            ("incident",) + tuple(str(r["incident_key"]) for _, r in runs),
            ("cause",) + tuple(str(((r["report"] or {}).get("likely_cause") or {}).get("deploy_id") or "unknown") for _, r in runs),
            ("confidence",) + tuple(str((r["report"] or {}).get("confidence")) for _, r in runs),
            ("tool calls until cause",) + tuple(_ttc(r)[0] for _, r in runs),
            ("LLM calls until cause",) + tuple(_ttc(r)[1] for _, r in runs),
            ("LLM calls total",) + tuple(str(r["totals"]["llm_calls"]) for _, r in runs)]
    w = [max(len(r[i]) for r in rows) + 2 for i in range(len(rows[0]))]
    line = "  +" + "+".join("-" * x for x in w) + "+"
    print(line)
    for i, r in enumerate(rows):
        print("  |" + "|".join(f" {c:{w[j] - 1}s}" for j, c in enumerate(r)) + "|")
        if i == 0:
            print(line)
    print(line)
    seen = next((h["details"].get("seen_before") for h in _handoffs(out["s2"]) if (h.get("details") or {}).get("seen_before")), None)
    if seen:
        print(f"\n  Session 2, from memory: {seen}")
    hit = out["s2_learned_hit"]
    if hit:
        print(f"  Session 2 found {hit['neighbour']} only through the LEARNED edge "
              + " -> ".join(hit["neighbour_path"]) + f" (written by Session 1, {', '.join(hit.get('learned_facts', []))}).")
    if "s2_nomem" in out:
        print("  Without Session 1's memory there is no risk-rules -> config-service edge, so the noisy-neighbour"
              "\n  traversal finds nothing and the team honestly reports the cause as unknown.")
    print("\n  learned edges: " + (", ".join(f"{e['from']} -> {e['to']} ({e['fact']})" for e in out["learned_edges"]) or "none"))
    print("  agent-written nodes: " + (", ".join(f"{k}={v}" for k, v in out["agent_nodes"].items()) or "none"))
    print(f"\n  See the memory in the FalkorDB Browser (http://localhost:3000, graph '{out['s2']['tenant']}'):\n    {BROWSER_CYPHER}")
    if sw := out.get("switch_tenant"):
        banner(f"7. Switch tenant: {sw['tenant']}")
        print(f"  agent-written nodes in {sw['tenant']}: {sw['agent_nodes_before']}; learned edges: {sw['learned_edges']}")
        print(f"  Brain on {sw['tenant']}: \"{sw['question']}\"\n    -> {sw['answer']}  (citations: {len(sw['citations'])})")
        print("  Each company is its own FalkorDB graph, so memory learned at Kestrel Pay cannot leak into Northwind Health.")


def _handoffs(rec):
    return [s["args"] for s in rec["steps"] if s["action"] == "handoff" and s["agent"] == "investigator"]


def svc_name(sid):
    return str(sid).split(":", 1)[-1]


def main():
    ap = argparse.ArgumentParser(prog="python -m backend.demo")
    ap.add_argument("cmd", choices=["story", "storm"])
    ap.add_argument("--graph", default="kestrel_pay")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--model")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--compare-no-memory", action="store_true")
    ap.add_argument("--save-golden", action="store_true", help="write the runs to runs/golden/ for /api/replay")
    a = ap.parse_args()
    if a.cmd == "storm":
        rec = run_storm(a.graph, LLMClient(mode="live" if a.live else None, model=a.model),
                        on_step=None if a.quiet else lambda s: print(fmt_step(s)), keep=True)
        try:  # approve the whole plan (simulated) so the recording shows the execution and its verification
            rec["execution"] = {k: v for k, v in execute(rec["twin"], rec, None, "jaya").items() if k != "steps"}
        finally:
            get_graph(rec["twin"]).delete()
        print(json.dumps(views.storm_numbers(rec), indent=1, ensure_ascii=False)[:3000])
        print("execution:", json.dumps(rec["execution"]["verification"], ensure_ascii=False)[:600])
        if a.save_golden:
            save_golden({"storm": rec})
            print(f"golden run written to {GOLDEN / 'firefighter-storm.json'}")
        return
    out = story(a.graph, LLMClient(mode="live" if a.live else None, model=a.model), a.quiet, a.compare_no_memory)
    if a.save_golden:
        save_golden(out)
        print(f"golden runs written to {GOLDEN}")


if __name__ == "__main__":
    main()
