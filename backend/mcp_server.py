"""MCP server: the read-only graph tools, generated from the registry. stdio, or streamable HTTP inside the API.

python -m backend.mcp_server --tenant kestrel_pay        # stdio
POST/GET http://localhost:8000/mcp/<tenant>/               # streamable HTTP, mounted by backend/api/main.py

Every tool's name, description and JSON schema come straight from backend/tools/registry.py. A call returns the
tool's `result` JSON plus a second text block, "Cypher receipt", with the exact parameterised queries it ran.
The result also travels as MCP structuredContent {"result", "receipt"} (the receipt with its highlight set), so a
client, including our own agents in `--tools-via mcp` mode, gets exactly what a direct call returns.
No write tools and no agent-running tools are exposed (safety + cost): MCP clients get the same read-only view
of the company graph that our own agents get. (connected_impact copies a projection into its own scratch graph for
algo.WCC and deletes it; the company graph itself is only read.)
Prompts: `investigate_alert` (service, symptom) and `alert_storm` (services). Resources: `incident-brain://schema`
(the graph model) and `incident-brain://tools` (the tool catalogue with each tool's Cypher).

Built on the SDK's low-level `Server` (mcp 2.x; FastMCP was renamed MCPServer there). The high-level decorators
derive schemas from Python signatures, which would duplicate the registry; the low-level server takes them as data.
"""
import argparse
import json
from pathlib import Path

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


ROOT = Path(__file__).resolve().parents[1]
PROMPTS = {
    "investigate_alert": dict(
        description="Investigate one alert with the graph tools: list recent changes as leads, check each against the "
                    "dependency graph, say who to page and why.",
        args=[("service", "the alerting service id or name", True), ("symptom", "what the alert says", True)],
        text="An alert fired on {service}: {symptom}. Use the tools: find_service if you only have a name, then "
             "recent_changes (every change is a lead), recent_changes_downstream and shared_dependency_changes to keep or "
             "reject each lead with the graph, then who_to_call, blast_radius, decisions_about and past_incidents for the "
             "culprit, and rollback_safety before suggesting a rollback. Cite node ids from the results; say why you "
             "rejected each other change."),
    "alert_storm": dict(
        description="Several alerts at once: decide which belong to one incident and who to page once.",
        args=[("services", "comma-separated alerting service ids", True)],
        text="These services are alerting at the same time: {services}. Call correlate_alerts and connected_impact with "
             "all of them, then recent_changes. If one shared dependency explains most alerts and no change explains "
             "more, treat them as ONE incident: who_to_call on that root, and list which per-alert pages you would "
             "suppress, with the dependency path as the reason. Keep alerts the root does not explain separate."),
}
RESOURCES = {
    "incident-brain://schema": ("Graph schema", "The locked graph model: labels, edges, properties.", ROOT / "docs" / "schema.md"),
    "incident-brain://tools": ("Tool catalogue", "Every tool's purpose, Cypher and real output.", ROOT / "docs" / "cypher.md"),
}


def build_server(tenant):
    if tenant not in allowed_tenants():
        raise ValueError(f"unknown tenant {tenant!r}; allowed: {allowed_tenants()}")

    async def list_prompts(ctx, params):
        return types.ListPromptsResult(prompts=[types.Prompt(name=n, description=p["description"], arguments=[
            types.PromptArgument(name=a, description=d, required=r) for a, d, r in p["args"]]) for n, p in PROMPTS.items()])

    async def get_prompt(ctx, params):
        p = PROMPTS.get(params.name)
        if not p:
            raise ValueError(f"unknown prompt {params.name!r}")
        args = {a: str((params.arguments or {}).get(a, ""))[:300] for a, _, _ in p["args"]}
        return types.GetPromptResult(description=p["description"], messages=[
            types.PromptMessage(role="user", content=types.TextContent(text=p["text"].format(**args)))])

    async def list_resources(ctx, params):
        return types.ListResourcesResult(resources=[types.Resource(uri=u, name=n, description=d, mime_type="text/markdown")
                                                    for u, (n, d, _) in RESOURCES.items()])

    async def read_resource(ctx, params):
        r = RESOURCES.get(str(params.uri))
        if not r:
            raise ValueError(f"unknown resource {params.uri!r}")
        return types.ReadResourceResult(contents=[types.TextResourceContents(uri=str(params.uri), mime_type="text/markdown",
                                                                             text=r[2].read_text())])

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
            structured_content=json.loads(json.dumps({"result": out.result, "receipt": out.receipt}, default=str)),
            is_error="error" in out.result)

    return Server(f"incident-brain-{tenant}", version="1.0",
                  instructions=f"Read-only tools over the {tenant} company graph (services, deploys, people, decisions, "
                               "incidents, docs). Start with find_service if you only have a name.",
                  get_tool_input_schema=lambda n: TOOLS[n]["input_schema"] if n in TOOLS else None,
                  on_list_tools=list_tools, on_call_tool=call_tool, on_list_prompts=list_prompts,
                  on_get_prompt=get_prompt, on_list_resources=list_resources, on_read_resource=read_resource)


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
