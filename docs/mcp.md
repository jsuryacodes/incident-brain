# Incident Brain over MCP

`backend/mcp_server.py` exposes the company graph's **read-only** tools over the Model Context Protocol (stdio).
Any MCP client (Claude Desktop, Claude Code, …) then picks tools itself, the Track 1 "tool selection via MCP" story.

- **Tools:** every tool in `backend/tools/registry.py` (15 today: `find_service`, `blast_radius`,
  `recent_changes_downstream`, `shared_dependency_changes`, `dependency_path`, `who_to_call`, `decisions_about`,
  `past_incidents`, `search_knowledge`, `critical_services`, `stale_knowledge`, `node_details`, `read_source`,
  `get_incident_state`, `memory_recall`). Names, descriptions and JSON schemas are generated from the registry, so they never drift
  from what our own agents use.
- **Output:** the tool's `result` JSON, plus a second text block **"Cypher receipt"** with the exact parameterised
  queries that produced it.
- **Not exposed:** write/memory tools and agent runs. MCP clients can look but not change the graph or spend API budget.
- One server process serves one tenant (`--tenant`, must be in `TENANTS`).
- Built on the official `mcp` Python SDK 2.x low-level `Server` (FastMCP is called `MCPServer` in 2.x; its
  decorators would re-derive schemas from Python signatures instead of using the registry's).

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
