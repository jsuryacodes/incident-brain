"""Canned Ask-the-Brain eval. python -m backend.agents.brain_eval [--tenant kestrel_pay] [--live]

Q5 is a follow-up asked in Q1's session: its subject ("that") must be resolved from the history stored in the graph.
Q4 also expects the 'missing_learned_dependency' reason once the M2 story has taught the graph risk-rules -> config-service.
"""
import argparse
import sys

from backend.agents.brain import ask
from backend.db import get_graph
from backend.llm import LLMClient

EVAL = [
    {"q": "Why must RULES_CACHE_TTL stay at 300 seconds?", "citations": {"dec:rules-cache-ttl", "chat:risk-eng-config-load"}},
    {"q": "Arjun left. Who knows risk-rules best now?", "people": {"per:priya-nair"}},
    {"q": "I'm new on Payments Core. What should I read first?", "citations": {"doc:payments-core-onboarding"},
     "decision_of_team": "team:payments-core"},
    {"q": "Which docs about risk-rules are out of date, and why?", "stale": {"doc:risk-rules-readme"}},
    {"q": "Who should I talk to about that?", "followup_of": 0, "people": {"per:priya-nair"}},
]
Q_TEAM_DECISION = """MATCH (d:Decision)-[:ABOUT]->(:Service)<-[:OWNS]-(:Team {id:$team}) WHERE d.id IN $ids RETURN count(d)"""
Q_LEARNED = "MATCH (:Service {id:'svc:risk-rules'})-[:DEPENDS_ON {source:'learned'}]->() RETURN count(*)"


def grade(case, r, graph):
    cited = {c["node_id"] for c in r.get("citations") or []}
    problems = []
    if r["status"] != "ok" or not r["grounding"]["ok"]:
        problems.append(f"status {r['status']}, grounding {r['grounding']}")
    if missing := case.get("citations", set()) - cited:
        problems.append(f"missing citations {sorted(missing)}")
    if missing := case.get("people", set()) - set(r.get("people") or []):
        problems.append(f"missing people {sorted(missing)}")
    if team := case.get("decision_of_team"):
        if not graph.ro_query(Q_TEAM_DECISION, {"team": team, "ids": sorted(cited)}).result_set[0][0]:
            problems.append(f"no cited decision about a {team} service")
    if stale := case.get("stale"):
        warned = {w["node_id"]: w["reason"] for w in r.get("stale_warnings") or []}
        if missing := stale - set(warned):
            problems.append(f"missing stale warnings {sorted(missing)}")
        elif graph.ro_query(Q_LEARNED).result_set[0][0] and not all("missing_learned_dependency" in warned[s] for s in stale):
            problems.append("graph has a learned dependency but the reason omits missing_learned_dependency")
    return problems


def run_eval(tenant="kestrel_pay", llm=None, user="eval", quiet=False):
    llm, graph, results = llm or LLMClient(), get_graph(tenant), []
    for i, case in enumerate(EVAL):
        session = results[case["followup_of"]]["session_id"] if "followup_of" in case else None
        r = ask(tenant, user, case["q"], session, llm)
        problems = grade(case, r, graph)
        results.append({"q": case["q"], "ok": not problems, "problems": problems, "session_id": r["session_id"],
                        "answer": r["answer"], "cost_usd": r["totals"]["cost_usd"], "llm_calls": r["totals"]["llm_calls"]})
        if not quiet:
            print(f"{i + 1}. {'PASS' if not problems else 'FAIL'}  {case['q']}" + "".join(f"\n      - {p}" for p in problems))
    return results


def main():
    ap = argparse.ArgumentParser(prog="python -m backend.agents.brain_eval")
    ap.add_argument("--tenant", default="kestrel_pay")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--model")
    a = ap.parse_args()
    res = run_eval(a.tenant, LLMClient(mode="live" if a.live else None, model=a.model))
    cost = sum(r["cost_usd"] for r in res)
    print(f"\n{sum(r['ok'] for r in res)}/{len(res)} passed, {sum(r['llm_calls'] for r in res)} LLM calls, ${cost:.4f}")
    sys.exit(0 if all(r["ok"] for r in res) else 1)


if __name__ == "__main__":
    main()
