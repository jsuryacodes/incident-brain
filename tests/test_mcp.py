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
