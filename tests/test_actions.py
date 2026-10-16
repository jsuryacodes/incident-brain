"""Part D: action plan, rollback safety, approval-gated simulated execution, verification. Mock only."""
import pytest
from fastapi.testclient import TestClient

from backend.agents.actions import execute
from backend.agents.firefighter import run_firefighter
from backend.api import main
from backend.db import eval_twin, get_graph
from backend.llm import LLMClient
from backend.tools.receipt import ToolContext
from seed.eval_scenarios import BY_ID, fixture
from seed.load import load


def run(scenario_id):
    sc = BY_ID[scenario_id]
    name = eval_twin("northwind_test" if sc["tenant"] == "northwind_health" else "kestrel_pay_test", "act_" + scenario_id.replace("-", "_"))
    s = load(name, reset=True, data_package=sc["tenant"], quiet=True, transform=fixture(sc))
    rec = run_firefighter(sc["alerts"][0] if len(sc["alerts"]) == 1 else sc["alerts"],
                          ToolContext(tenant=name, now=s["now"]), LLMClient(mode="mock"), save=False)
    return name, rec


def test_safe_rollback_executes_once_and_verifies():
    name, rec = run("k-falselead")
    try:
        plan = rec["report"]["action_plan"]
        rb = next(a for a in plan if a["kind"] == "rollback")
        assert rb["safety"]["verdict"] == "safe" and rb["justification"]["path"] == ["svc:payouts-service", "svc:bank-connector"]
        out = execute(name, rec, None, "test")
        assert all(r["ok"] for r in out["results"]) and out["verification"]["all_cleared"] is True
        g = get_graph(name)
        assert g.ro_query("MATCH (d:Deploy {id:'dep:bank-connector-v1.20.0-rollback', origin:'agent'}) RETURN count(d)").result_set[0][0] == 1
        again = execute(name, rec, None, "test")
        assert again["already_executed"] and g.ro_query("MATCH (i:Incident {origin:'agent'}) RETURN count(i)").result_set[0][0] == 1
    finally:
        get_graph(name).delete()


def test_risky_rollback_becomes_hold_and_does_not_clear():
    name, rec = run("n-falselead")
    try:
        hold = next(a for a in rec["report"]["action_plan"] if a["kind"] in ("hold", "rollback"))
        assert hold["kind"] == "hold" and "hard to undo" in hold["safety"]["reasons"][0]
        assert any(a.startswith("Hold the rollback") for a in rec["report"]["recommended_actions"])
        out = execute(name, rec, None, "test")
        assert out["verification"]["all_cleared"] is False
    finally:
        get_graph(name).delete()


def test_never_executes_on_a_hero_graph(ctx):
    rec = run_firefighter({"service_id": "svc:payments-api", "symptom": "5xx"}, ctx, LLMClient(mode="mock"), save=False)
    with pytest.raises(PermissionError):
        execute(ctx.tenant, {**rec, "run_id": "x"}, None, "test")


def test_execute_endpoint_needs_the_code(monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "c0de")
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1000")
    c = TestClient(main.app)
    assert c.post("/api/actions/execute", json={"run_id": "nope"}).status_code == 403
    assert c.post("/api/actions/execute", json={"run_id": "nope"}, headers={"X-Access-Code": "c0de"}).status_code == 404
