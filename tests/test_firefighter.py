"""Firefighter agent: mock only, never live."""
import copy

from backend.agents import mock_policy
from backend.agents.check_run import checks
from backend.agents.firefighter import run_firefighter
from backend.llm import LLMClient, LLMResponse

ALERT = {"service_id": "svc:payments-api", "symptom": "5xx rate 12% and p99 4.1s on payments-api for the last 15 minutes"}


def run(ctx, llm, **kw):
    return run_firefighter(ALERT, ctx, llm, save=False, **kw)


def test_1_mock_run_passes_story_checks(ctx):
    rec = run(ctx, LLMClient(mode="mock"))
    failed = [(n, got) for n, ok, got in checks(rec) if not ok]
    assert not failed, failed
    assert rec["totals"]["cost_usd"] == 0


def test_1b_service_query_resolves_name(ctx):
    rec = run_firefighter({"service_query": "payments api", "symptom": "5xx"}, ctx, LLMClient(mode="mock"), save=False)
    assert rec["steps"][0]["tool"] == "find_service"
    assert rec["report"]["likely_cause"]["service_id"] == "svc:risk-rules"


def _lying_policy(agent, system, tools, messages):
    out = mock_policy.respond(agent, system, tools, messages)
    for b in out:
        if b["name"] == "submit_report":
            b["input"] = copy.deepcopy(b["input"])
            b["input"]["contact"]["person_id"] = "per:made-up"
    return out


def test_2_grounding_rejects_invented_id(ctx):
    rec = run(ctx, LLMClient(mode="mock", policy=_lying_policy))
    submits = [s for s in rec["steps"] if s["tool"] == "submit_report"]
    assert len(submits) == 2  # rejected once, resubmitted once
    assert "per:made-up" in submits[0]["result"]["error"]
    assert rec["grounding"]["ok"] is False and rec["grounding"]["ungrounded_ids"] == ["per:made-up"]


def test_2b_grounding_rejects_non_literal_excerpt(ctx):
    def misquote(agent, system, tools, messages):
        out = mock_policy.respond(agent, system, tools, messages)
        for b in out:
            if b["name"] == "submit_report" and b["input"]["conflicting_decision"]:
                b["input"] = copy.deepcopy(b["input"])
                b["input"]["conflicting_decision"]["excerpt"] = "RULES_CACHE_TTL may be lowered freely."
        return out
    rec = run(ctx, LLMClient(mode="mock", policy=misquote))
    assert rec["grounding"]["ok"] is False
    assert any("literal quote" in e for e in rec["grounding"]["errors"])


def test_3_step_cap(ctx):
    never = lambda *a: [{"type": "tool_use", "id": "t1", "name": "blast_radius", "input": {"service_id": "svc:payments-api"}}]
    rec = run(ctx, LLMClient(mode="mock", policy=never), max_steps=3)
    assert rec["status"] == "step_limit" and rec["totals"]["llm_calls"] == 3 and rec["report"] is None


def test_4_budget_guard(ctx, monkeypatch):
    monkeypatch.setenv("MAX_RUN_COST_USD", "0.05")
    usage = {"input_tokens": 600_000, "output_tokens": 1000, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}

    def pricey(agent, system, tools, messages):
        return LLMResponse(mock_policy.respond(agent, system, tools, messages), "tool_use", usage, 0.061)
    rec = run(ctx, LLMClient(mode="mock", policy=pricey))
    assert rec["status"] == "budget_abort" and "MAX_RUN_COST_USD" in rec["abort_reason"]
    assert rec["totals"]["llm_calls"] == 1


def test_5_live_request_payload_without_network():
    llm = LLMClient(mode="live", model="claude-haiku-5-5")
    tools = [{"name": "a", "description": "x", "input_schema": {"type": "object"}},
             {"name": "b", "description": "y", "input_schema": {"type": "object"}}]
    p = llm.build_request("SYSTEM", tools, [{"role": "user", "content": "hi"}], max_tokens=777)
    assert p["max_tokens"] == 777 and p["model"] == "claude-haiku-5-5"
    assert p["tools"][-1]["cache_control"] == {"type": "ephemeral"} and "cache_control" not in p["tools"][0]
    assert p["system"] == [{"type": "text", "text": "SYSTEM", "cache_control": {"type": "ephemeral"}}]
    assert "cache_control" not in tools[-1]  # caller's list untouched


def test_6_tool_exception_becomes_error_result(ctx, monkeypatch):
    from backend.tools import registry

    def boom(ctx, **kw):
        raise RuntimeError("db on fire")
    monkeypatch.setitem(registry.TOOLS["blast_radius"], "fn", boom)
    rec = run(ctx, LLMClient(mode="mock"))
    step = next(s for s in rec["steps"] if s["tool"] == "blast_radius")
    assert "db on fire" in step["result"]["error"]
    assert rec["status"] == "ok" and rec["report"]["blast_radius"] == []


def test_7_every_tool_step_has_a_receipt(ctx):
    rec = run(ctx, LLMClient(mode="mock"))
    for s in rec["steps"]:
        if s["tool"] != "submit_report":
            assert len(s["receipt"]["queries"]) >= 1, s["tool"]
