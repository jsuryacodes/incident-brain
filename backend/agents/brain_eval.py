"""Canned Ask-the-Brain eval: 15 Kestrel Pay questions (one per intent) + 3 Northwind Health questions.

python -m backend.agents.brain_eval [--tenant kestrel_pay] [--live]

Intents: why-decided (exact quote), who-knows-after-someone-left, onboarding, stale, follow-up ("that"), who-owns,
what-breaks-if, seen-before, follow-up pronoun ("it"), what-did-session-N-learn, industry pattern, another user's
session (must be refused), follow-up from a NEW process (restart persistence), a question with no answer ("I don't
know"). Follow-ups run in an earlier case's session; their subject must come from history stored in the graph.
Q4 also expects 'missing_learned_dependency' once the story has taught the graph risk-rules -> config-service.
The new-process case spawns a subprocess in mock mode only (a live run would bill it separately).
Q10 asks about the latest team session that wrote a Fact; on a fresh seed there is none, so it asks about a session
that doesn't exist and expects an honest "I don't know".
"""
import argparse
import json
import subprocess
import sys

from backend.agents.brain import ask
from backend.db import get_graph
from backend.llm import LLMClient

HERD_PMS = {"pm:slack-2022-02-22", "pm:facebook-2010-09-23"}
EVAL = {
    "kestrel_pay": [
        {"q": "Why must RULES_CACHE_TTL stay at 300 seconds?", "citations": {"dec:rules-cache-ttl", "chat:risk-eng-config-load"},
         "quote_has": "300s"},
        {"q": "Arjun left. Who knows risk-rules best now?", "people": {"per:priya-nair"}},
        {"q": "I'm new on Payments Core. What should I read first?", "citations": {"doc:payments-core-onboarding"},
         "decision_of_team": "team:payments-core"},
        {"q": "Which docs about risk-rules are out of date, and why?", "stale": {"doc:risk-rules-readme"}},
        {"q": "Who should I talk to about that?", "followup_of": 0, "people": {"per:priya-nair"}},
        {"q": "Who owns config-service?", "people": {"per:omar-haddad"}, "answer_has": ["Platform"]},
        {"q": "What breaks if config-service fails?", "answer_has": ["payments-api", "web-checkout"], "min_citations": 1},
        {"q": "Have we seen config-service overloaded before?", "citations_any": {"inc:2025-031", "inc:2026-012"},
         "answer_has": ["Priya Nair"]},
        {"q": "Who should I call about it?", "followup_of": 7, "people": {"per:omar-haddad"}},
        {"q": "What did session {session} learn?", "session_learn": True},
        {"q": "Has any other company had a thundering herd outage like ours?", "citations_any": HERD_PMS, "answer_has": ["https://"]},
        {"q": "Who should I talk to about that?", "followup_of": 0, "other_user": True},
        {"q": "Who should I talk to about that?", "followup_of": 0, "new_process": True, "people": {"per:priya-nair"}},
        {"q": "What is our policy for Kubernetes cluster upgrades?", "dont_know": True},
        {"q": "Why did we decide that?", "followup_of": 2, "min_citations": 1, "answer_has": ["dec:"]},
    ],
    "northwind_health": [
        {"q": "Why are SMS retries capped?", "citations": {"dec:sms-retry-cap"}},
        {"q": "Owen left. Who knows notifications best now?", "people": {"per:maya-okoro"}},
        {"q": "Has any other company had a retry storm like ours?", "answer_has": ["https://"], "min_citations": 1},
    ],
}
Q_TEAM_DECISION = """MATCH (d:Decision)-[:ABOUT]->(:Service)<-[:OWNS]-(:Team {id:$team}) WHERE d.id IN $ids RETURN count(d)"""
Q_LEARNED = "MATCH (:Service {id:'svc:risk-rules'})-[:DEPENDS_ON {source:'learned'}]->() RETURN count(*)"
Q_LEARNING_SESSION = """MATCH (f:Fact)-[:WRITTEN_IN]->(s:Session {mode:'team'})
RETURN s.id, collect(f.id) ORDER BY s.started_at DESC LIMIT 1"""
NO_SESSION = "ses:19700101T000000-000000"
DONT_KNOW = ("don't know", "do not know")


def grade(case, r, graph):
    if case.get("other_user"):
        return [] if r.get("refused") else ["another user's session was NOT refused"]
    cited = {c["node_id"] for c in r.get("citations") or []}
    answer = r.get("answer") or ""
    problems = []
    if r["status"] != "ok" or not r["grounding"]["ok"]:
        problems.append(f"status {r['status']}, grounding {r['grounding']}")
    if case.get("dont_know"):
        if cited or not any(d in answer.lower() for d in DONT_KNOW):
            problems.append(f"expected an honest 'I don't know' with no citations, got {answer[:80]!r} citing {sorted(cited)}")
        return problems
    if missing := case.get("citations", set()) - cited:
        problems.append(f"missing citations {sorted(missing)}")
    if (any_of := case.get("citations_any")) and not any_of & cited:
        problems.append(f"cites none of {sorted(any_of)}")
    if len(cited) < case.get("min_citations", 0):
        problems.append(f"needs at least {case['min_citations']} citation(s)")
    if missing := case.get("people", set()) - set(r.get("people") or []):
        problems.append(f"missing people {sorted(missing)}")
    for text in case.get("answer_has", []):
        if text.lower() not in answer.lower():
            problems.append(f"answer lacks {text!r}")
    if (q := case.get("quote_has")) and not any(q in c.get("excerpt", "") for c in r.get("citations") or []):
        problems.append(f"no cited excerpt contains {q!r}")
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


def ask_in_new_process(tenant, user, question, session):
    """Restart persistence: the follow-up runs in a fresh Python process, so history can only come from the graph."""
    code = ("import json, sys; from backend.agents.brain import ask; "
            "r = ask(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]); "
            "print(json.dumps({k: r[k] for k in ('session_id', 'status', 'answer', 'citations', 'people', 'stale_warnings', 'grounding', 'totals')}))")
    out = subprocess.run([sys.executable, "-c", code, tenant, user, question, session], capture_output=True, text=True, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def run_eval(tenant="kestrel_pay", llm=None, user="eval", quiet=False):
    llm, graph, results = llm or LLMClient(), get_graph(tenant), []
    cases = EVAL.get(tenant) or EVAL["northwind_health" if tenant.startswith("northwind") else "kestrel_pay"]
    for i, case in enumerate(cases):
        session = results[case["followup_of"]]["session_id"] if "followup_of" in case else None
        q, case = case["q"], dict(case)
        if case.get("session_learn"):
            row = graph.ro_query(Q_LEARNING_SESSION).result_set
            q = q.format(session=row[0][0] if row else NO_SESSION)
            case.update({"citations": set(row[0][1])} if row else {"dont_know": True})
        if case.get("other_user"):
            try:
                ask(tenant, user + "-other", q, session, llm)
                r = {"refused": False}
            except PermissionError:
                r = {"refused": True}
            r.update(session_id=session, answer="(refused)", totals={"cost_usd": 0, "llm_calls": 0})
        elif case.get("new_process") and llm.mode == "mock":  # live: same process (history still comes from the graph)
            r = ask_in_new_process(tenant, user, q, session)
        else:
            r = ask(tenant, user, q, session, llm)
        problems = grade(case, r, graph)
        results.append({"q": q, "ok": not problems, "problems": problems, "session_id": r["session_id"],
                        "answer": r["answer"], "cost_usd": r["totals"]["cost_usd"], "llm_calls": r["totals"]["llm_calls"]})
        if not quiet:
            print(f"{i + 1:2d}. {'PASS' if not problems else 'FAIL'}  {q}\n      -> {str(r['answer'])[:160]}"
                  + "".join(f"\n      - {p}" for p in problems))
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
