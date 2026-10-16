"""M4: MCP server, in-process client on the test graph."""
import json

import anyio
from mcp import Client

from backend.mcp_server import build_server
from backend.tools.memory_tools import MEMORY_TOOLS
from backend.tools.registry import TOOLS


def run(coro_fn, tenant):
    async def go():
        async with Client(build_server(tenant)) as c:
            return await coro_fn(c)
    return anyio.run(go)


def test_lists_every_read_tool_from_the_registry(ctx):
    tools = run(lambda c: c.list_tools(), ctx.tenant).tools
    assert len(tools) == len(TOOLS) and {t.name for t in tools} == set(TOOLS)
    assert not {t.name for t in tools} & set(MEMORY_TOOLS)  # no write tools over MCP
    t = next(t for t in tools if t.name == "recent_changes_downstream")
    assert t.description == TOOLS[t.name]["description"] and t.input_schema == TOOLS[t.name]["input_schema"]


def test_call_recent_changes_downstream(ctx):
    r = run(lambda c: c.call_tool("recent_changes_downstream", {"service_id": "svc:payments-api", "since_minutes": 120}), ctx.tenant)
    assert not r.is_error and len(r.content) == 2
    result = json.loads(r.content[0].text)
    assert result["hits"][0]["service"] == "svc:risk-rules" and result["hits"][0]["deploy"]["id"] == "dep:risk-rules-v2.8.0"
    assert r.content[1].text.startswith("Cypher receipt") and "DEPENDS_ON" in r.content[1].text and "$since" in r.content[1].text


def test_errors_are_tool_errors(ctx):
    r = run(lambda c: c.call_tool("blast_radius", {"service_id": "svc:nope"}), ctx.tenant)
    assert r.is_error and "unknown service id" in r.content[0].text


def test_tools_via_mcp_parity(ctx):
    """Our own Firefighter, with its tool list and every call coming through an MCP session: same run as direct."""
    from backend.agents.firefighter import run_firefighter
    from backend.llm import LLMClient
    alert = {"service_id": "svc:payments-api", "symptom": "5xx rate 12%"}
    direct = run_firefighter(alert, ctx, LLMClient(mode="mock"), save=False)
    via = run_firefighter(alert, ctx, LLMClient(mode="mock"), save=False, tools_via="mcp")
    assert via["tools_via"]["transport"] == "mcp" and via["tools_via"]["mcp_calls"] == direct["totals"]["tool_calls"]
    assert [s["tool"] for s in via["steps"]] == [s["tool"] for s in direct["steps"]]
    strip = lambda r: {k: v for k, v in r.items() if k not in ("deploy",)}  # minutes_ago may tick between runs
    assert [strip(s["result"]) for s in via["steps"][:3]] == [strip(s["result"]) for s in direct["steps"][:3]]
    assert via["report"]["likely_cause"] == direct["report"]["likely_cause"]
    cy = lambda s: [q["cypher"] for q in s["receipt"]["queries"]]  # params hold `since`: the server uses its own clock
    assert all(cy(a) == cy(b) for a, b in zip(via["steps"], direct["steps"]))


def test_prompts_resources_and_structured_receipts(ctx):
    async def go(c):
        p = await c.get_prompt("alert_storm", {"services": "svc:a, svc:b"})
        r = await c.read_resource("incident-brain://schema")
        t = await c.call_tool("recent_changes", {"since_minutes": 120})
        return p, r, t
    p, r, t = run(go, ctx.tenant)
    assert "correlate_alerts" in p.messages[0].content.text and "Graph Schema" in r.contents[0].text
    assert set(t.structured_content) == {"result", "receipt"} and t.structured_content["receipt"]["queries"]


def test_streamable_http_endpoint_per_tenant(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.api import main
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1000")
    h = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with TestClient(main.app) as c:
        tenant = next(iter(main.MCP))
        r = c.post(f"/mcp/{tenant}/", headers=h, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                                         "params": {"name": "find_service", "arguments": {"query": "payments"}}})
        body = r.json()
        assert r.status_code == 200 and body["result"]["structuredContent"]["result"]["matches"]
        bad = c.post(f"/mcp/{tenant}/", headers={**h, "Host": "evil.example"}, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert bad.status_code in (400, 403, 421)  # DNS-rebinding protection: unknown Host refused
