# Incident Brain over MCP

`backend/mcp_server.py` exposes the company graph's **read-only** tools over the Model Context Protocol, and our own
agents can pick and call their tools **through MCP** too (Track 1: "tool selection through MCP").

- **Tools:** every tool in `backend/tools/registry.py` (22 today, incl. the algorithm tools `critical_services`,
  `correlate_alerts`, `connected_impact`, `blast_tiers`, `failure_domains` and the safety check `rollback_safety`).
  Names, descriptions and JSON schemas are generated from the registry, so they never drift from what our agents use.
- **Output:** the tool's `result` JSON, a second text block **"Cypher receipt"** with the exact parameterised queries,
  and the same as MCP `structuredContent` `{result, receipt}` (receipt incl. the highlighted nodes/edges).
- **Prompts:** `investigate_alert(service, symptom)` and `alert_storm(services)`: the method our Firefighter follows.
- **Resources:** `incident-brain://schema` (the graph model) and `incident-brain://tools` (every tool's Cypher + real output).
- **Not exposed:** write/memory tools and agent runs. MCP clients can look but not change the graph or spend API budget.
  (`connected_impact` copies a projection into its own scratch graph for algo.WCC and deletes it; the company graph is only read.)
- **Transports:** stdio (`python -m backend.mcp_server --tenant <t>`, one tenant per process) and **streamable HTTP**
  inside the API: `http://localhost:8000/mcp/<tenant>/` (one server per company, so a connection serves one tenant;
  stateless JSON responses; rate-limited like `/api/*`; Host/Origin checked against DNS rebinding, configure with
  `MCP_ALLOWED_HOSTS` / `MCP_ALLOWED_ORIGINS`).
- **Our agents through MCP:** `python -m backend.agents.firefighter --service svc:payments-api --symptom "5xx" --tools-via mcp`:
  the tool list comes from `tools/list` and every call is a `tools/call` on an MCP client session
  (`backend/agents/mcp_tools.py`). `tests/test_mcp.py::test_tools_via_mcp_parity` proves the run is the same as direct.
- **Transcript:** `docs/mcp-transcript.md` (`python -m backend.agents.mcp_transcript`): a scripted client (no LLM)
  against the HTTP endpoint: discovery → prompt → tool selection → results and receipts.
- Built on the official `mcp` Python SDK 2.x low-level `Server`.

Prerequisites: FalkorDB running (`docker start falkordb`), the graph seeded, and the venv installed
(`pip install -r requirements.txt`). Replace `/ABS/PATH/incident-brain` below with your checkout path.

Check it by hand:
```bash
.venv/bin/python -m backend.mcp_server --tenant kestrel_pay   # waits for a client on stdin; Ctrl-C to stop
```

## Claude Code

```bash
cd /ABS/PATH/incident-brain
claude mcp add incident-brain -e PYTHONPATH=/ABS/PATH/incident-brain -- \
  /ABS/PATH/incident-brain/.venv/bin/python -m backend.mcp_server --tenant kestrel_pay
claude mcp list            # incident-brain should show as connected
```
Add `--scope project` to write it into `.mcp.json` for everyone on the repo, or `--scope user` for all your projects.
A second tenant is just a second server: `claude mcp add northwind -e PYTHONPATH=... -- ... --tenant northwind_health`.

## Claude Desktop

Settings → Developer → Edit Config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS),
then restart Claude Desktop:
```json
{
  "mcpServers": {
    "incident-brain": {
      "command": "/ABS/PATH/incident-brain/.venv/bin/python",
      "args": ["-m", "backend.mcp_server", "--tenant", "kestrel_pay"],
      "env": { "PYTHONPATH": "/ABS/PATH/incident-brain" }
    }
  }
}
```

## Example prompts

1. *"payments-api is throwing 5xx errors right now. Using the incident-brain tools, what changed recently that
   could cause it, and who should I page?"* → `recent_changes_downstream` → `who_to_call` (risk-rules deploy
   RISK-412, 40 min ago; Arjun has left, page Priya).
2. *"Why does RULES_CACHE_TTL have to stay at 300 seconds? Quote the original discussion."* → `search_knowledge`
   → `decisions_about` / `read_source` on `chat:risk-eng-config-load`.
3. *"Which services would be hurt if config-service went down, and which of our docs about risk-rules are out of
   date?"* → `blast_radius` + `stale_knowledge`.

Each answer can show its receipts: ask the client to "show the Cypher receipt" and it will quote the second text block.
