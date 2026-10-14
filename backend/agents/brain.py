"""Ask the Brain: company-knowledge Q&A with sources, and conversation memory kept in the graph.

python -m backend.agents.brain ask "Why must RULES_CACHE_TTL stay at 300 seconds?" [--session ses:...] [--user jaya] [--live]
python -m backend.agents.brain sessions [--user jaya]

Each turn is persisted as an 'answer' Step (question + answer + citations in params_json) in a Session (mode 'brain').
Given session_id, earlier turns are loaded FROM THE GRAPH and replayed as conversation history, so a follow-up like
"who should I talk to about that?" works after a process restart. Sessions belong to one user.
"""
import argparse
import json
import time

from backend.agents.firefighter import PROMPTS, payload_message, print_totals, read_tools
from backend.agents.loop import BOLD, RST, fmt_step, new_totals, run_agent
from backend.agents.report_schema import _obj, grounding_problems, schema_errors
from backend.agents.team import memory_tools
from backend.db import get_graph
from backend.llm import LLMClient
from backend.memory.sessions import StepLog, end_session, start_session, step_id
from backend.tools.receipt import ToolContext, ToolOutput

READ = ["search_knowledge", "decisions_about", "who_to_call", "read_source", "node_details", "stale_knowledge",
        "find_service", "past_incidents", "blast_radius", "industry_matches"]
_S = {"type": "string"}
ANSWER_SCHEMA = _obj({
    "answer": {"type": "string", "description": "At most 150 words. Say plainly if the graph doesn't know."},
    "citations": {"type": "array", "items": _obj({"node_id": _S, "excerpt": {"type": "string", "description": "Verbatim quote."}}),
                  "description": "At least 1 unless you don't know. Each excerpt copied verbatim from read_source."},
    "people": {"type": "array", "items": _S, "description": "Person ids to talk to."},
    "stale_warnings": {"type": "array", "items": _obj({"node_id": _S, "reason": _S})},
})
SUBMIT_ANSWER = {"action": "answer", "input_schema": ANSWER_SCHEMA,
                 "description": "Submit your answer with grounded citations. Call exactly once, at the end."}
DONT_KNOW = ("don't know", "do not know", "no information", "nothing in")


def check_answer(args, seen, graph):
    p = grounding_problems(args, seen, graph)
    errs = schema_errors(args, ANSWER_SCHEMA)
    if len(str(args.get("answer", "")).split()) > 150:
        errs.append("answer must be at most 150 words")
    if not args.get("citations") and not any(d in str(args.get("answer", "")).lower() for d in DONT_KNOW):
        errs.append("cite at least one source (node_id + verbatim excerpt), or say you don't know")
    if errs:
        p = {"errors": p.get("errors", []) + errs, "ungrounded_ids": p.get("ungrounded_ids", [])}
    return p


Q_OWNER = "MATCH (s:Session {id:$id}) RETURN s.user, s.mode"
Q_TURNS = """MATCH (st:Step)-[:IN_SESSION]->(:Session {id:$id})
RETURN st.seq, st.action, st.params_json ORDER BY st.seq"""
Q_LIST = """MATCH (s:Session {user:$user})
OPTIONAL MATCH (st:Step {action:'answer'})-[:IN_SESSION]->(s)
RETURN s.id, s.mode, s.status, s.started_at, count(st) ORDER BY s.started_at DESC"""


def load_turns(tenant, session_id, user):
    """Earlier Q&A turns of a session, from the graph. Raises PermissionError if it isn't this user's brain session."""
    g = get_graph(tenant)
    owner = g.ro_query(Q_OWNER, {"id": session_id}).result_set
    if not owner or owner[0][0] != user or owner[0][1] != "brain":
        raise PermissionError(f"no brain session {session_id!r} for user {user!r}")
    rows = g.ro_query(Q_TURNS, {"id": session_id}).result_set
    turns = [json.loads(pj) for _, action, pj in rows if action == "answer"]
    return turns, (rows[-1][0] if rows else 0)


def history_messages(turns):
    msgs = []
    for t in turns:
        msgs.append({"role": "user", "content": f"Earlier question: {t.get('question')}"})
        msgs.append({"role": "assistant", "content": f"Earlier answer: {t.get('answer')}\nCited: "
                     + ", ".join(c["node_id"] for c in t.get("citations", [])) + "\nPeople: " + ", ".join(t.get("people", []))})
    return msgs


def list_sessions(tenant, user):
    return [{"id": i, "mode": m, "status": st, "started_at": at, "turns": n}
            for i, m, st, at, n in get_graph(tenant).ro_query(Q_LIST, {"user": user}).result_set]


def not_persisted(ctx, args):
    return ToolOutput({"skipped": "not saved: this answer is not persisted (no access code)"},
                      {"tool": "flag_stale", "args": args, "queries": [], "highlight": {"nodes": [], "edges": []}})


def ask(tenant, user, question, session_id=None, llm=None, on_step=None, max_steps=8, persist=True, turns=None):
    """persist=False: nothing is written (no Session/Step, flag_stale is a no-op); follow-ups then use `turns`, the
    earlier [{question, answer, citations, people}] the caller kept."""
    llm, t0 = llm or LLMClient(), time.time()
    if persist:
        turns, last_seq = load_turns(tenant, session_id, user) if session_id else ([], 0)
        session_id = session_id or start_session(tenant, user, "brain")
        log = StepLog(tenant, session_id)
        log.prev = step_id(session_id, last_seq) if last_seq else None
    else:
        turns, last_seq, session_id, log = list(turns or []), 0, None, (lambda step: None)
    ctx = ToolContext(tenant=tenant, session_id=session_id)
    steps = []

    def record(step):
        if step["action"] == "answer":  # the turn record: question + answer + citations
            step = {**step, "args": {**step["args"], "question": question}}
        log(step)
        steps.append(step)
        if on_step:
            on_step(step)
    graph, totals = get_graph(tenant), new_totals()
    tools = {**read_tools(READ), **memory_tools(["flag_stale"]), "submit_answer": SUBMIT_ANSWER}
    if not persist:
        tools["flag_stale"] = {**tools["flag_stale"], "fn": not_persisted}
    rec = run_agent("brain", (PROMPTS / "brain.md").read_text(), tools,
                    payload_message("Answer this question about the company using the graph tools.", {"question": question}),
                    ctx, llm, max_steps=max_steps, validate=lambda n, a, seen: check_answer(a, seen, graph),
                    history=history_messages(turns), on_step=record, totals=totals, seq_start=last_seq)
    if persist:
        end_session(tenant, session_id, "open" if rec["status"] == "ok" else rec["status"])
    out = rec["report"] or {"answer": None, "citations": [], "people": [], "stale_warnings": []}
    return {"session_id": session_id, "question": question, "status": rec["status"], **out,
            "grounding": rec["grounding"], "turn": len(turns) + 1, "mode": llm.mode, "steps": steps, "persisted": persist,
            "totals": {**totals, "duration_ms": int((time.time() - t0) * 1000)}}


def main():
    ap = argparse.ArgumentParser(prog="python -m backend.agents.brain")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask")
    a.add_argument("question")
    a.add_argument("--session")
    a.add_argument("--live", action="store_true")
    a.add_argument("--model")
    a.add_argument("--show-cypher", action="store_true")
    ls = sub.add_parser("sessions")
    for p in (a, ls):
        p.add_argument("--user", default="jaya")
        p.add_argument("--tenant", default="kestrel_pay")
    x = ap.parse_args()
    if x.cmd == "sessions":
        for s in list_sessions(x.tenant, x.user):
            print(f"{s['id']}  {s['mode']:6s} {s['status']:8s} turns={s['turns']}")
        return
    llm = LLMClient(mode="live" if x.live else None, model=x.model)
    try:
        r = ask(x.tenant, x.user, x.question, x.session, llm, on_step=lambda s: print(fmt_step(s, x.show_cypher)))
    except PermissionError as e:
        raise SystemExit(f"error: {e}")
    print(f"\n{BOLD}ANSWER{RST} (turn {r['turn']}, {r['status']}, grounding ok: {r['grounding']['ok']})\n  {r['answer']}")
    for c in r["citations"]:
        print(f"  [{c['node_id']}] \"{c['excerpt']}\"")
    if r["people"]:
        print("  people: " + ", ".join(r["people"]))
    for w in r["stale_warnings"]:
        print(f"  STALE {w['node_id']}: {w['reason']}")
    print_totals(r["totals"])
    print(f"session: {r['session_id']}   (follow up with --session {r['session_id']})")


if __name__ == "__main__":
    main()
