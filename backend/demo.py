"""The whole demo storyline, mock by default.

python -m backend.demo story [--graph kestrel_pay] [--live] [--quiet]
python -m backend.demo story --compare-no-memory      # Session 2 on a fresh seed, WITHOUT Session 1
"""
import argparse

from backend.agents.loop import BOLD, RST
from backend.agents.firefighter import print_report
from backend.agents.team import resolve_incident, run_team, tracer
from backend.db import get_graph
from backend.llm import LLMClient
from seed import scenario
from seed.load import load

S1_ALERT = {"service_id": "svc:payments-api", "symptom": "5xx rate 12% and p99 4.1s on payments-api for the last 15 minutes"}
S2_ALERT = {"service_id": "svc:payouts-service", "symptom": "payout batch API 5xx 9% and p99 3.2s for the last 10 minutes"}
FIX = "Priya rolled back RULES_CACHE_TTL to 300s; config-service load recovered"
BROWSER_CYPHER = "MATCH (n {origin:'agent'})-[r]-(m) RETURN n,r,m"


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


def story(graph="kestrel_pay", llm=None, quiet=False, compare_no_memory=False):
    llm = llm or LLMClient()
    ev = None if quiet else tracer(False)
    say = (lambda *a: None) if quiet else print
    if not quiet:
        banner(f"1. Re-seed {graph}")
    load(graph, reset=True, data_package="kestrel_pay", quiet=quiet)
    out = {}
    if not compare_no_memory:
        if not quiet:
            banner("2. Session 1: payments-api alert, the team investigates")
        out["s1"] = run_team(S1_ALERT, graph, "jaya", llm, ev)
        if not quiet:
            print_report(out["s1"]["report"])
            banner("3. Operator: resolved by Priya")
        out["resolve"] = resolve_incident(out["s1"]["incident_id"], ["per:priya-nair"], FIX, graph, llm, "jaya", ev)
    if not quiet:
        banner("4. World event: risk-rules v2.8.1 ships (scenario session2)")
    say(f"added {scenario.apply('session2', graph)}")
    if not quiet:
        banner("5. Session 2: payouts-service alert" + (" (NO memory: fresh seed)" if compare_no_memory else ""))
    out["s2"] = run_team(S2_ALERT, graph, "jaya", llm, ev)
    if not quiet:
        print_report(out["s2"]["report"])
    out.update(memory_summary(graph))
    out["s2_learned_hit"] = s2_learned_hit(out["s2"])
    if not quiet:
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


def main():
    ap = argparse.ArgumentParser(prog="python -m backend.demo")
    ap.add_argument("cmd", choices=["story"])
    ap.add_argument("--graph", default="kestrel_pay")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--model")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--compare-no-memory", action="store_true")
    a = ap.parse_args()
    story(a.graph, LLMClient(mode="live" if a.live else None, model=a.model), a.quiet, a.compare_no_memory)


if __name__ == "__main__":
    main()
