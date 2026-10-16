"""Our own agents, choosing and calling tools THROUGH MCP (`--tools-via mcp`).

McpToolbox(tenant) opens an MCP client session to our MCP server (the same server Claude Desktop / Claude Code use)
and exposes, in the agent loop's format, exactly the tools the server lists: names, descriptions and schemas come from
`tools/list`, every call is a `tools/call`, and the result + receipt come back as MCP structuredContent. The agent
loop is synchronous, so the async session runs in an anyio blocking portal (a background event loop).
Transport: in-process memory streams by default; pass url= to talk to a running server over streamable HTTP.
"""
import json

import anyio.from_thread
from mcp import Client

from backend.tools.receipt import ToolOutput


class McpToolbox:
    def __init__(self, tenant, url=None, names=None):
        from backend.mcp_server import build_server
        self.tenant, self.calls = tenant, 0
        self._portal_cm = anyio.from_thread.start_blocking_portal()
        self.portal = self._portal_cm.__enter__()
        self._client_cm = self.portal.wrap_async_context_manager(Client(url or build_server(tenant, internal=True)))
        self.client = self._client_cm.__enter__()
        listed = self.portal.call(self.client.list_tools).tools
        self.listed = [t.name for t in listed]
        self.tools = {t.name: {"description": t.description, "input_schema": t.input_schema, "action": "tool_call",
                               "fn": self._caller(t.name)}
                      for t in listed if names is None or t.name in names}

    def _caller(self, name):
        def fn(ctx, args):
            self.calls += 1
            r = self.portal.call(self.client.call_tool, name, args)
            sc = r.structured_content or {}
            if "result" in sc:
                return ToolOutput(sc["result"], sc["receipt"])
            return ToolOutput(json.loads(r.content[0].text), {"tool": name, "args": args, "queries": [],
                                                              "highlight": {"nodes": [], "edges": []}})
        return fn

    def close(self):
        self._client_cm.__exit__(None, None, None)
        self._portal_cm.__exit__(None, None, None)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
