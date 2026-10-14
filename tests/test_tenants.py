"""M6: second tenant (Northwind Health) and tenant isolation. Mock only."""
import json

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp import Client

from backend import demo
from backend.api import main
from backend.agents.brain import ask
from backend.db import get_graph
from backend.memory.sessions import start_session
from backend.tools.memory_tools import MEMORY_TOOLS
from backend.tools.receipt import ToolContext
from backend.tools.registry import call
from backend.mcp_server import build_server
from seed.load import package_for


@pytest.fixture(scope="module")
def tenants(fresh):
    kp, nw = fresh("kestrel_pay_iso"), fresh("northwind_test")
    out = demo.story(kp, quiet=True, other=nw)  # the whole M2 story on Kestrel Pay, then the switch-tenant beat
    return kp, nw, out


def test_story_memory_stays_in_its_tenant(tenants):
    kp, nw, out = tenants
    assert get_graph(kp).ro_query("MATCH (n {origin:'agent'}) RETURN count(n)").result_set[0][0] > 20
    assert out["switch_tenant"]["agent_nodes_before"] == 0 and out["switch_tenant"]["learned_edges"] == 0


def test_brain_on_other_tenant_does_not_know(tenants):
    _, nw, out = tenants
    sw = out["switch_tenant"]
    assert sw["citations"] == [] and "don't know" in sw["answer"].lower()
    r = ask(nw, "jaya", "Why must RULES_CACHE_TTL stay at 300 seconds?")
    assert r["citations"] == [] and "don't know" in r["answer"].lower() and r["grounding"]["ok"]


def test_other_tenant_answers_its_own_questions(tenants):
    _, nw, _ = tenants
    r = ask(nw, "jaya", "Why are SMS retries capped?")
    assert "dec:sms-retry-cap" in {c["node_id"] for c in r["citations"]}


def test_tools_cannot_reach_ids_of_the_other_tenant(tenants):
    kp, nw, out = tenants
    ctx = ToolContext(tenant=nw, session_id=start_session(nw, "jaya", "team"))
    w = lambda tool, **a: call(tool, a, ctx, MEMORY_TOOLS).result
    assert "unknown service" in w("open_incident", service_id="svc:payments-api", symptom="x", severity=2)["error"]
    assert "error" in w("record_learned_dependency", from_service_id="svc:notifications", to_service_id="svc:config-service",
                        kind="sync", statement="x", confidence=0.5,
                        sources=[{"node_id": "chat:risk-eng-config-load", "excerpt": "risk-rules polls config-service"}])
    assert "error" in w("record_fact", statement="x", about_ids=["svc:notifications"], confidence=0.5,
                        sources=[{"node_id": "chat:risk-eng-config-load", "excerpt": "risk-rules polls config-service"}])
    assert "error" in w("page_person", person_id="per:priya-nair", incident_id=out["s1"]["incident_id"], message="x")
    assert "error" in call("get_incident_state", {"incident_id": out["s1"]["incident_id"]}, ctx).result
    kp_session = out["s1"]["session_id"]
    with pytest.raises(PermissionError):  # a Kestrel Pay session id means nothing in Northwind's graph
        ask(nw, "jaya", "Who should I talk to about that?", kp_session)
    assert get_graph(nw).ro_query("MATCH (n:Incident {origin:'agent'}) RETURN count(n)").result_set[0][0] == 0


def test_api_and_mcp_accept_the_second_tenant(tenants, monkeypatch):
    _, nw, _ = tenants
    assert package_for("northwind_health") == package_for(nw) == "northwind_health" and package_for("kestrel_pay_iso") == "kestrel_pay"
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1000")
    c = TestClient(main.app)
    names = {n["id"] for n in c.get("/api/graph", params={"tenant": nw}).json()["nodes"]}
    assert "svc:patient-portal" in names and "svc:payments-api" not in names

    async def go():
        async with Client(build_server(nw)) as m:
            return await m.call_tool("recent_changes_downstream", {"service_id": "svc:patient-portal", "since_minutes": 120})
    r = anyio.run(go)
    assert json.loads(r.content[0].text)["hits"][0]["deploy"]["id"] == "dep:notifications-v3.2.0"
