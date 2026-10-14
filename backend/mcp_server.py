"""MCP server: the read-only graph tools, generated from the registry. stdio transport.

python -m backend.mcp_server --tenant kestrel_pay

Every tool's name, description and JSON schema come straight from backend/tools/registry.py. A call returns the
tool's `result` JSON plus a second text block, "Cypher receipt", with the exact parameterised queries it ran.
No write tools and no agent-running tools are exposed (safety + cost): MCP clients get the same read-only view
of the company graph that our own agents get.

Built on the SDK's low-level `Server` (mcp 2.x; FastMCP was renamed MCPServer there). The high-level decorators
derive schemas from Python signatures, which would duplicate the registry; the low-level server takes them as data.
"""
import argparse
import json

import anyio
import mcp_types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from backend.db import allowed_tenants
from backend.tools.receipt import ToolContext
from backend.tools.registry import TOOLS, call


def receipt_text(receipt):
    lines = [f"Cypher receipt for {receipt['tool']} ({len(receipt['queries'])} quer{'y' if len(receipt['queries']) == 1 else 'ies'}):"]
    for q in receipt["queries"]:
        lines += [q["cypher"], f"  params: {json.dumps(q['params'], default=str)}"]
    return "\n".join(lines)


def build_server(tenant):
    if tenant not in allowed_tenants():
        raise ValueError(f"unknown tenant {tenant!r}; allowed: {allowed_tenants()}")

    async def list_tools(ctx, params):
        return types.ListToolsResult(tools=[types.Tool(name=n, description=t["description"], input_schema=t["input_schema"])
                                            for n, t in TOOLS.items()])

    async def call_tool(ctx, params):
        if params.name not in TOOLS:
            return types.CallToolResult(content=[types.TextContent(text=f"unknown tool {params.name!r}")], is_error=True)
        out = await anyio.to_thread.run_sync(lambda: call(params.name, params.arguments or {}, ToolContext(tenant=tenant)))
        return types.CallToolResult(
            content=[types.TextContent(text=json.dumps(out.result, ensure_ascii=False, default=str)),
                     types.TextContent(text=receipt_text(out.receipt))],
            is_error="error" in out.result)

    return Server(f"incident-brain-{tenant}", version="1.0",
                  instructions=f"Read-only tools over the {tenant} company graph (services, deploys, people, decisions, "
                               "incidents, docs). Start with find_service if you only have a name.",
                  get_tool_input_schema=lambda n: TOOLS[n]["input_schema"] if n in TOOLS else None,
                  on_list_tools=list_tools, on_call_tool=call_tool)


async def serve(tenant):
    server = build_server(tenant)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main():
    ap = argparse.ArgumentParser(prog="python -m backend.mcp_server")
    ap.add_argument("--tenant", default="kestrel_pay")
    a = ap.parse_args()
    anyio.run(serve, a.tenant)


if __name__ == "__main__":
    main()
