"""run_agent: the one agent loop every agent (Firefighter, Triage, Investigator, Communicator, Brain) runs on.

LLM call -> execute EVERY tool_use in the response -> send all results back in one user message -> repeat until a
submit tool is accepted or max_steps LLM calls are used. Tool exceptions become error results, never crashes.

Grounding: `seen` holds every id that appeared in the initial message, the history or a tool result. Write tools may
only touch seen ids, and a submit is checked by `validate` (ungrounded ids, non-literal excerpts). A rejected submit
gets ONE retry; a second failure ends the run with grounding.ok = False.
"""
import json
import time

from backend.llm import USAGE_KEYS, max_run_cost
from backend.tools.receipt import clip, ids_in

DIM, BOLD, YEL, RED, CYAN, RST = "\033[2m", "\033[1m", "\033[33m", "\033[31m", "\033[36m", "\033[0m"


def new_totals():
    return {**dict.fromkeys(USAGE_KEYS, 0), "cost_usd": 0.0, "llm_calls": 0, "tool_calls": 0}


def tool_specs(tools):
    return [{"name": n, "description": t["description"], "input_schema": t["input_schema"]} for n, t in tools.items()]


def run_agent(agent, system, tools, initial_message, ctx, llm, *, max_steps=10, validate=None, history=None,
              on_step=None, totals=None, max_tokens=1024, seq_start=0, persona=None):
    """tools: name -> {description, input_schema, fn(ctx, args) -> ToolOutput, action}. action is 'tool_call',
    'write', 'page', or 'handoff'/'answer' for a submit tool (which has no fn). persona: which mock policy plays
    this agent (default: agent). Returns the agent record."""
    totals = totals if totals is not None else new_totals()
    messages = list(history or []) + [{"role": "user", "content": initial_message}]
    seen = ids_in(initial_message) | ids_in(history or [])
    specs = tool_specs(tools)
    rec = {"agent": agent, "status": "ok", "report": None, "submit_tool": None,
           "grounding": {"ok": None, "ungrounded_ids": [], "errors": []}, "steps": []}
    rejected = 0
    for _ in range(max_steps):
        resp = llm.complete(system, specs, messages, max_tokens=max_tokens, agent=persona or agent)
        totals["llm_calls"] += 1
        for k in USAGE_KEYS:
            totals[k] += resp.usage.get(k, 0)
        totals["cost_usd"] += resp.cost_usd or 0
        messages.append({"role": "assistant", "content": resp.content})
        if totals["cost_usd"] > max_run_cost():
            rec["status"], rec["abort_reason"] = "budget_abort", (
                f"cumulative cost ${totals['cost_usd']:.4f} exceeded MAX_RUN_COST_USD ${max_run_cost():.2f}")
            break
        uses = [b for b in resp.content if b["type"] == "tool_use"]
        if not uses:
            submit = [n for n, t in tools.items() if t["action"] in ("handoff", "answer")]
            messages.append({"role": "user", "content": f"Finish by calling {' or '.join(submit)}."})
            continue
        results, done = [], False
        for u in uses:
            name, args, t0 = u["name"], u.get("input") or {}, time.time()
            spec = tools.get(name)
            receipt = {"tool": name, "args": args, "queries": [], "highlight": {"nodes": [], "edges": []}}
            if spec is None:
                result = {"error": f"unknown tool {name!r}; available: {sorted(tools)}"}
            elif spec["action"] in ("handoff", "answer"):
                problems = validate(name, args, seen) if validate else {}
                if problems and not rejected:
                    rejected = 1
                    result = {"error": "rejected, not grounded: " + "; ".join(problems["errors"])
                              + ". Only cite ids that appeared in tool results and quote sources verbatim. Resubmit once."}
                else:
                    done = True
                    rec["report"], rec["submit_tool"] = args, name
                    rec["grounding"] = {"ok": not problems, "ungrounded_ids": (problems or {}).get("ungrounded_ids", []),
                                        "errors": (problems or {}).get("errors", [])}
                    result = {"ok": True, "accepted": name}
                    receipt["highlight"]["nodes"] = sorted(ids_in(args) & seen)
            else:
                bad = sorted(ids_in(args) - seen) if spec["action"] != "tool_call" else []
                if bad:
                    result = {"error": f"ungrounded ids {bad}: look them up with a read tool before writing"}
                else:
                    try:
                        out = spec["fn"](ctx, args)
                        result, receipt = out.result, out.receipt
                    except Exception as e:  # a crashing tool is an error result, never a crashed run
                        result = {"error": f"{name} failed: {type(e).__name__}: {e}"}
                totals["tool_calls"] += 1
            is_err = "error" in result
            if not is_err:
                seen |= ids_in(result)
            step = {"seq": seq_start + len(rec["steps"]) + 1, "agent": agent,
                    "action": spec["action"] if spec and not is_err else "tool_call",
                    "tool": name, "args": args, "result": result, "receipt": receipt,
                    "summary": (clip(args.get("note") or args.get("summary") or args.get("answer") or name, 900)
                                if result.get("accepted") else summarize(name, args, result)), "ts": int(time.time()),
                    "ms": int((time.time() - t0) * 1000), "llm_call": totals["llm_calls"]}
            rec["steps"].append(step)
            if on_step:
                on_step(step)
            results.append({"type": "tool_result", "tool_use_id": u["id"], "content": json.dumps(result, default=str),
                            **({"is_error": True} if is_err else {})})
        messages.append({"role": "user", "content": results})
        if done:
            break
    else:
        rec["status"] = "step_limit"
    if rec["status"] == "ok" and rec["report"] is None:
        rec["status"] = "step_limit"
    rec["messages"] = messages
    return rec


# ───────────── one-line step summaries (trace + Step.summary) ─────────────
def _name(i):
    return str(i).split(":", 1)[-1]


def _recent(a, r):
    hs = r.get("hits", [])
    if not hs:
        return "no recent downstream deploys"
    h = hs[0]
    t = f", {h['ticket']['key']}" if h.get("ticket") else ""
    return f"{r['hit_count']} hit(s): {_name(h['service'])} (deployed {h['deploy']['minutes_ago']} min ago by {h['deploy']['by']}{t})"


def _shared(a, r):
    hs = r.get("hits", [])
    if not hs:
        return "no noisy neighbours"
    h = hs[0]
    return (f"{r['hit_count']} hit(s): {_name(h['neighbour'])} via shared {_name(h['shared'])}"
            + (" (LEARNED edge)" if h.get("uses_learned_edge") else "") + f", deployed {h['deploy']['minutes_ago']} min ago")


def _who(a, r):
    c = r.get("candidates") or [{}]
    left = [m["name"] for m in r.get("maintainers", []) if m["status"] == "left"]
    return (f"top: {c[0].get('name')} (score {c[0].get('score')})"
            + (f"; maintainer {', '.join(left)} LEFT" if left else ""))


def _decisions(a, r):
    d = r.get("decisions", [])
    return f"{len(d)} decision(s)" + (f": {d[0]['title']}" if d else "")


def _past(a, r):
    inc = r.get("incidents", [])
    return f"{r.get('incident_count', 0)} incident(s)" + (": " + ", ".join(
        f"{i['key']}" + (f" (fixed by {', '.join(i['resolved_by'])})" if i.get("resolved_by") else "") for i in inc[:3]) if inc else "")


def _recall(a, r):
    if r.get("note"):
        return "nothing recalled (no memory yet)"
    sus = ", ".join(_name(x["service"]) for x in r.get("suspects", [])[:2])
    return (f"{len(r['learned_edges'])} learned edge(s), {len(r['facts'])} fact(s), {len(r['incidents'])} resolved incident(s)"
            + (f"; suspect: {sus}" if sus else ""))


_SUM = {
    "memory_recall": _recall,
    "industry_matches": lambda a, r: f"{r['match_count']} public postmortem(s)" + (
        f": {r['matches'][0]['company']} — {r['matches'][0]['title']}" if r.get("matches") else ""),
    "find_service": lambda a, r: "matches: " + (", ".join(m["id"] for m in r.get("matches", [])) or "none"),
    "blast_radius": lambda a, r: f"{r['upstream_count']} upstream ({r['tier1_count']} tier-1)",
    "recent_changes_downstream": _recent,
    "shared_dependency_changes": _shared,
    "dependency_path": lambda a, r: " -> ".join(map(_name, r["nodes"])) if r.get("found") else "no path",
    "who_to_call": _who,
    "decisions_about": _decisions,
    "past_incidents": _past,
    "search_knowledge": lambda a, r: f"{r['hit_count']} hit(s)" + (f": {r['hits'][0]['id']}" if r.get("hits") else ""),
    "critical_services": lambda a, r: f"{r['algorithm']}: " + ", ".join(_name(s["id"]) for s in r["services"][:4]),
    "stale_knowledge": lambda a, r: f"{r['stale_count']} stale: " + ", ".join(i["id"] for i in r["items"][:3]),
    "node_details": lambda a, r: f"{r['label']} {r['id']}",
}


def summarize(tool, args, result):
    if "error" in result:
        return f"{tool} → ERROR: {clip(result['error'], 140)}"
    if "summary" in result and isinstance(result["summary"], str):
        return f"{tool} → {clip(result['summary'], 160)}"
    try:
        return f"{tool} → {_SUM[tool](args, result)}" if tool in _SUM else f"{tool} → ok"
    except (KeyError, IndexError, TypeError):
        return f"{tool} → ok"


def fmt_step(step, show_cypher=False):
    color = {"write": YEL, "page": YEL, "handoff": CYAN, "answer": CYAN}.get(step["action"], "")
    tag = {"write": "[WRITE] ", "page": "[PAGE] ", "handoff": "[HANDOFF] "}.get(step["action"], "")
    head = step["summary"].split(" → ", 1)
    lines = [f"{color}[{step['seq']}] {tag}{step['tool']} {json.dumps(step['args'], ensure_ascii=False, default=str)[:160]}"
             + (f" → {head[1]}" if len(head) > 1 else "") + RST]
    if show_cypher or step["action"] in ("write", "page"):
        for q in step["receipt"].get("queries", []):
            lines.append(f"{DIM}      {q['cypher'][:300]}{RST}")
    return "\n".join(lines)
