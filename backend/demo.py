"""The whole demo storyline, mock by default.

python -m backend.demo story [--graph kestrel_pay] [--live] [--quiet]
python -m backend.demo story --compare-no-memory      # Session 2 on a fresh seed, WITHOUT Session 1
"""
import argparse
import json
from pathlib import Path

from backend.agents.loop import BOLD, CYAN, RST
from backend.agents.firefighter import print_report
from backend.agents.team import resolve_incident, run_team, tracer
from backend.agents.brain import ask
from backend.db import allowed_tenants, get_graph
from backend.llm import LLMClient
from seed import scenario
from seed.load import load

S1_ALERT = {"service_id": "svc:payments-api", "symptom": "5xx rate 12% and p99 4.1s on payments-api for the last 15 minutes"}
S2_ALERT = {"service_id": "svc:payouts-service", "symptom": "payout batch API 5xx 9% and p99 3.2s for the last 10 minutes"}
FIX = "Priya rolled back RULES_CACHE_TTL to 300s; config-service load recovered"
BROWSER_CYPHER = "MATCH (n {origin:'agent'})-[r]-(m) RETURN n,r,m"
GOLDEN = Path(__file__).resolve().parents[1] / "runs" / "golden"


def save_golden(out):
    """Recorded runs for /api/replay (no LLM needed to show the demo)."""
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for key, name in (("s1", "team-session1.json"), ("resolve", "resolve-session1.json"), ("s2", "team-session2.json")):
        if key in out:
            rec = {k: v for k, v in out[key].items() if k != "path"}
            (GOLDEN / name).write_text(json.dumps(rec, indent=1, ensure_ascii=False, default=str))


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
    """quiet: print only session headers, handoffs and the summary box (verbose prints every step)."""
    llm = llm or LLMClient()
    ev = handoffs_only if quiet else tracer(False)
    say = (lambda *a: None) if quiet else print
    other = other if other in allowed_tenants() and other != graph else None
    if not quiet:
        banner(f"1. Re-seed {graph}" + (f" and {other}" if other else ""))
    load(graph, reset=True, data_package="kestrel_pay", quiet=True)
    if other:
        load(other, reset=True, data_package="northwind_health", quiet=True)
    out = {}
    if not compare_no_memory:
        banner("2. Session 1: payments-api alert, the team investigates")
        out["s1"] = run_team(S1_ALERT, graph, "jaya", llm, ev)
        if not quiet:
            print_report(out["s1"]["report"])
        banner("3. Operator: resolved by Priya")
        out["resolve"] = resolve_incident(out["s1"]["incident_id"], ["per:priya-nair"], FIX, graph, llm, "jaya", ev)
    if not quiet:
        banner("4. World event: risk-rules v2.8.1 ships (scenario session2)")
    say(f"added {scenario.apply('session2', graph)}")
    banner("5. Session 2: payouts-service alert" + (" (NO memory: fresh seed)" if compare_no_memory else ""))
    out["s2"] = run_team(S2_ALERT, graph, "jaya", llm, ev)
    if not quiet:
        print_report(out["s2"]["report"])
    out.update(memory_summary(graph))
    out["s2_learned_hit"] = s2_learned_hit(out["s2"])
    if other:
        out["switch_tenant"] = switch_tenant(other, llm)
    print_summary(out, compare_no_memory)
    return out


def _ttc(rec):
    t = rec and rec.get("time_to_cause")
    return f"{t['llm_calls']} LLM calls / {t['tool_calls']} tool calls" if t else "cause NOT found"


def print_summary(out, compare_no_memory):
    banner("6. Summary")
    s2 = out["s2"]
    lc2 = (s2["report"] or {}).get("likely_cause") or {}
    rows = [("", "Session 1 (payments-api)", "Session 2 (payouts-service)")]
    if "s1" in out:
        lc1 = (out["s1"]["report"] or {}).get("likely_cause") or {}
        rows.append(("incident", out["s1"]["incident_key"], s2["incident_key"]))
        rows.append(("cause", str(lc1.get("deploy_id")), str(lc2.get("deploy_id"))))
        rows.append(("time to cause", _ttc(out["s1"]), _ttc(s2)))
        rows.append(("LLM calls total", str(out["s1"]["totals"]["llm_calls"]), str(s2["totals"]["llm_calls"])))
    else:
        rows.append(("incident", "(skipped: no memory)", s2["incident_key"]))
        rows.append(("cause", "-", str(lc2.get("deploy_id"))))
        rows.append(("time to cause", "-", _ttc(s2)))
        rows.append(("confidence", "-", str((s2["report"] or {}).get("confidence"))))
    w = max(len(r[1]) for r in rows) + 2
    for a, b, c in rows:
        print(f"  {a:16s} {b:{w}s} {c}")
    hit = out["s2_learned_hit"]
    if hit:
        print(f"\n  Session 2 found {hit['neighbour']} only through the LEARNED edge "
              + " -> ".join(hit["neighbour_path"]) + f" (written by Session 1, {', '.join(hit.get('learned_facts', []))}).")
    elif compare_no_memory:
        print("\n  Without Session 1's memory there is no risk-rules -> config-service edge, so the noisy-neighbour"
              "\n  traversal finds nothing and the team honestly reports the cause as unknown.")
    print("\n  learned edges: " + (", ".join(f"{e['from']} -> {e['to']} ({e['fact']})" for e in out["learned_edges"]) or "none"))
    print("  agent-written nodes: " + (", ".join(f"{k}={v}" for k, v in out["agent_nodes"].items()) or "none"))
    print(f"\n  See the memory in the FalkorDB Browser (http://localhost:3000, graph '{s2['tenant']}'):\n    {BROWSER_CYPHER}")
    if sw := out.get("switch_tenant"):
        banner(f"7. Switch tenant: {sw['tenant']}")
        print(f"  agent-written nodes in {sw['tenant']}: {sw['agent_nodes_before']}; learned edges: {sw['learned_edges']}")
        print(f"  Brain on {sw['tenant']}: \"{sw['question']}\"\n    -> {sw['answer']}  (citations: {len(sw['citations'])})")
        print("  Each company is its own FalkorDB graph, so memory learned at Kestrel Pay cannot leak into Northwind Health.")


def main():
    ap = argparse.ArgumentParser(prog="python -m backend.demo")
    ap.add_argument("cmd", choices=["story"])
    ap.add_argument("--graph", default="kestrel_pay")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--model")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--compare-no-memory", action="store_true")
    ap.add_argument("--save-golden", action="store_true", help="write the runs to runs/golden/ for /api/replay")
    a = ap.parse_args()
    out = story(a.graph, LLMClient(mode="live" if a.live else None, model=a.model), a.quiet, a.compare_no_memory)
    if a.save_golden:
        save_golden(out)
        print(f"golden runs written to {GOLDEN}")


if __name__ == "__main__":
    main()
