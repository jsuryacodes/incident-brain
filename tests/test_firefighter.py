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
    assert rec["status"] == "ungrounded" and rec["report"] is None  # never served or handed off


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


def test_2c_nested_fields_and_excerpts_are_required(ctx):
    def strip(agent, system, tools, messages):
        out = mock_policy.respond(agent, system, tools, messages)
        for b in out:
            if b["name"] == "submit_report" and b["input"]["conflicting_decision"]:
                b["input"] = copy.deepcopy(b["input"])
                del b["input"]["conflicting_decision"]["source_id"]  # would have skipped the excerpt check
        return out
    rec = run(ctx, LLMClient(mode="mock", policy=strip))
    assert rec["status"] == "ungrounded"
    assert any("conflicting_decision.'source_id'" in e for e in rec["grounding"]["errors"])


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


# ───────────── the generalised planner (08A3) ─────────────
from contextlib import contextmanager  # noqa: E402
from dataclasses import replace  # noqa: E402

import pytest  # noqa: E402

from backend.db import eval_twin, get_graph  # noqa: E402
from backend.tools.receipt import ToolContext  # noqa: E402
from seed.eval_scenarios import BY_ID, fixture  # noqa: E402
from seed.load import load  # noqa: E402


@contextmanager
def twin(scenario_id):
    sc = BY_ID[scenario_id]
    name = eval_twin("northwind_test" if sc["tenant"] == "northwind_health" else "kestrel_pay_test", "t_" + scenario_id.replace("-", "_"))
    s = load(name, reset=True, data_package=sc["tenant"], quiet=True, transform=fixture(sc))
    try:
        yield sc, ToolContext(tenant=name, now=s["now"])
    finally:
        get_graph(name).delete()


def ff(sc, ctx, **kw):
    alert = sc["alerts"][0] if len(sc["alerts"]) == 1 else sc["alerts"]
    return run_firefighter(alert, ctx, LLMClient(mode="mock"), save=False, **kw)


def test_8_every_recent_change_is_a_lead_and_the_decoy_is_rejected(ctx):
    r = run(ctx, LLMClient(mode="mock"))["report"]
    assert [x["deploy_id"] for x in r["rejected_leads"]] == ["dep:email-sender-v1.14.2"]
    assert "not on the call path" in r["rejected_leads"][0]["reason"]


def test_9_nobody_active_escalates_to_the_team():
    with twin("k-departed") as (sc, c):
        r = ff(sc, c)["report"]
    assert r["contact"]["person_id"] is None and r["contact"]["team_id"] == "team:merchant-exp"
    assert "Carlos Mendes" in r["bus_factor_warning"] and not any("per:carlos-mendes" in a for a in r["recommended_actions"])


def test_10_nothing_changed_means_no_cause_and_a_pagerank_pointer():
    with twin("k-nochange") as (sc, c):
        rec = ff(sc, c)
    r = rec["report"]
    assert r["likely_cause"]["deploy_id"] is None and r["confidence"] == "low"
    assert r["look_first"]["algorithm"] == "pagerank" and r["look_first"]["service_ids"][0] in sc["expect"]["look_first"]
    assert not any(a.startswith("Roll back") for a in r["recommended_actions"])
    assert not any(s["tool"] == "recent_changes_downstream" for s in rec["steps"])  # an empty change log needs no scan


def test_11_one_change_explaining_two_alerts_beats_a_fresher_one():
    with twin("n-chokepoint") as (sc, c):
        r = ff(sc, c)["report"]
    assert "incidents" in r and len(r["incidents"]) == 1
    assert r["likely_cause"]["deploy_id"] == "dep:notifications-v3.3.0"
    assert "explains 2 alerts" in next(x["reason"] for x in r["rejected_leads"] if x["deploy_id"] == "dep:records-db-v15.2.0")


def test_12_uncorroborated_neighbour_is_not_a_cause(ctx):
    """In a company where everything calls the same hubs, a neighbour through a shared hub alone is noise."""
    with twin("k-hubsat") as (sc, c):
        corroborated = ff(sc, c)["report"]
        bare = ff({"alerts": [{"service_id": sc["alerts"][0]["service_id"], "symptom": "webhook delivery lag 14 min"}]}, c)["report"]
    assert corroborated["likely_cause"]["deploy_id"] == "dep:reconciliation-job-v1.8.0"
    assert bare["likely_cause"]["deploy_id"] is None
    assert "nothing corroborates it" in bare["rejected_leads"][0]["reason"]


def test_13_restricted_tools_degrade_honestly(ctx):
    rec = run(ctx, LLMClient(mode="mock"), tool_names=["find_service", "recent_changes", "search_knowledge", "read_source"])
    r = rec["report"]
    assert {s["tool"] for s in rec["steps"]} <= {"recent_changes", "search_knowledge", "submit_report"}
    assert r["likely_cause"]["path"] == [] and r["confidence"] == "low" and rec["grounding"]["ok"] is True


def test_14_narrow_shared_dependency_is_a_candidate_a_hub_is_not():
    """bank-connector has 2 callers (narrow): a change to its other caller is a real suspect. config-service has many."""
    sc = {"tenant": "kestrel_pay", "id": "narrow", "fixture": {"quiet": True, "deploys": [
        ("reconciliation-job", "9.0.0", 20, "tomasz-kowalski", "Replay every bank statement line on each run", None)]},
        "alerts": [{"service_id": "svc:payouts-service", "symptom": "payout batch API 5xx 6%"}]}
    BY_ID["narrow"] = sc
    try:
        with twin("narrow") as (sc_, c):
            r = ff(sc_, c)["report"]
    finally:
        BY_ID.pop("narrow")
    assert r["likely_cause"]["deploy_id"] == "dep:reconciliation-job-v9.0.0"
    assert "narrow dependency" in r["likely_cause"]["explanation"]


def test_15_rejection_reasons_and_an_unresolved_alert_is_reported(ctx):
    with twin("k-falselead") as (sc, c):
        r = ff({"alerts": [sc["alerts"][0], {"service_query": "zzzqqq", "symptom": "x"}]}, c)["report"]
    assert "Could not resolve" in r["summary"] and "zzzqqq" in r["summary"]
    reasons = {x["deploy_id"]: x["reason"] for x in r["rejected_leads"]}
    assert "a hub" in reasons["dep:merchant-dashboard-v7.10.0"] or "own call path" in reasons["dep:merchant-dashboard-v7.10.0"]
    assert "shares no dependency" in reasons["dep:email-sender-v1.15.0"]


def test_16_every_tool_subset_stays_grounded():
    """Whatever tools the planner is given (the baselines and sparser), every report is grounded: it states only what
    it checked, and says what it could not check."""
    from seed.eval_scenarios import SCENARIOS
    from backend.tools.registry import TOOLS
    NOALGO = sorted(set(TOOLS) - {"critical_services", "dependency_path"})
    TEXT = ["find_service", "recent_changes", "search_knowledge", "read_source"]
    sets = {"full": None, "noalgo": NOALGO, "text": TEXT, "log": ["recent_changes"], "down": ["recent_changes_downstream"],
            "scans": ["recent_changes_downstream", "shared_dependency_changes"], "none": []}
    bad = []
    for sc in SCENARIOS:
        with twin(sc["id"]) as (_, c):
            for name, tools in sets.items():
                rec = ff(sc, replace(c, algorithms=name != "noalgo"), tool_names=tools)
                if rec["status"] != "ok":
                    bad.append((sc["id"], name, rec["grounding"]["errors"][:1]))
    assert not bad, bad


def test_17_reason_follows_the_multi_alert_comparison():
    """Two alerts: audit-trail is on both alerts' paths; lab-results' own change only covers identity as a neighbour."""
    sc = {"tenant": "northwind_health", "id": "why", "fixture": {"quiet": True, "deploys": [
        ("lab-results", "9.0.0", 30, "maya-okoro", "Rewrite the result renderer", None),
        ("audit-trail", "9.0.0", 30, "maya-okoro", "fsync every audit write", None)]},
        "alerts": [{"service_id": "svc:lab-results", "symptom": "slow"}, {"service_id": "svc:identity", "symptom": "slow"}]}
    BY_ID["why"] = sc
    try:
        with twin("why") as (sc_, c):
            r = ff(sc_, c)["report"]
    finally:
        BY_ID.pop("why")
    assert r["likely_cause"]["deploy_id"] == "dep:audit-trail-v9.0.0"
    reason = next(x["reason"] for x in r["rejected_leads"] if x["deploy_id"] == "dep:lab-results-v9.0.0")
    assert "is nearer" not in reason and ("only shares a dependency" in reason or "explains 2 alerts" in reason), reason
