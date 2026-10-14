# AI assistance log (for the hackathon disclosure)

Running log of where AI tools helped. Tools: Claude (claude.ai, Opus 5.5) for planning/design; Claude Code (Sonnet 5.5) for implementation.

## 2026-10-15 — Step 1: graph schema
- Designed with Claude in claude.ai: node labels, edges, provenance pattern (SOURCED_FROM), learned DEPENDS_ON edge for memory, indexes, planted-story fixtures.
- My decisions: hidden dependency absent from seed and learned at runtime; postmortems copied per tenant; no embeddings (full-text + traversal).
- Output: `docs/schema.md` (locked v1), `docs/prompts/02-seed.md` (task spec for Claude Code).

## 2026-10-15 — Step 2: Kestrel Pay seed + verify
- Claude Code (Sonnet 5.5) wrote `seed/` (loader, schema copy, verify) and all Kestrel Pay content (27 services, 20 people, 37 deploys, docs, chats, tickets, incidents) from `docs/prompts/02-seed.md`. No LLM/API calls at runtime.
- Loader validates everything before touching the DB (prefixes, required/unknown props, enums, time props are ints, edge endpoints and edge-type rules); writes with UNWIND + MERGE. `seed/verify.py` proves the 13 story checks.
- Double-check: (1) FalkorDB 4.x rejects the multi-arg `db.idx.fulltext.createNodeIndex` shown in schema.md §6; the loader uses `CREATE FULLTEXT INDEX FOR (n:Label) ON (n.a, n.b)` (same index) — consider updating §6 wording. (2) Fictional prose and chat transcripts: read `chat:risk-eng-config-load` yourself, it is the demo's key evidence. (3) Counts above the prompt's targets: Deploy 37 (33 in last 30 days + 4 older incident causes), Ticket 17 (11 + 6 postmortems). (4) Chat/doc dates are generated from the relative clock, so they shift on re-seed. (5) Extras beyond the prompt: runbooks also have SOURCED_FROM (design rule 2); Priya WORKED_ON merchant-onboarding (she fixed INC-2026-012).

## 2026-10-15 — Housekeeping: CLAUDE.md + schema §6 fix
- Added `CLAUDE.md` (standing rules) and corrected `docs/schema.md` §6 full-text syntax to `CREATE FULLTEXT INDEX` (v1.0.1, no model change). Both were written by Claude (claude.ai, Opus 5.5) at the user's request; Claude Code only committed and pushed them.
- Double-check: the loader's index DDL matches the corrected §6.

## 2026-10-15 — Docs: data model diagrams + demo checklist
- Claude (claude.ai, Opus 5.5) added three Mermaid diagrams to `docs/schema.md` ("Data model at a glance", v1.0.2; rendered and checked before committing) and `docs/demo-checklist.md`. No model change.

## 2026-10-15 — Step 3: core graph tools
- Claude Code (Sonnet 5.5) built `backend/` (tenant-checked `get_graph`, 12 read-only tools, registry, CLI, `docs/cypher.md` generator) and `tests/` (34 tests on a throwaway `kestrel_pay_test` graph). `seed/load.py` now exposes `load(graph, reset, now, data_package)`; CLI behaviour unchanged, verify still 13/13. No LLM calls.
- Double-check: (1) **Hackathon track names**: the prompt didn't define them, so `track` in `registry.py` uses the product modes (Firefighter / Brain / Team memory) as placeholders; give me the real names. (2) FalkorDB quirk: a MATCH after `WITH … aggregate` silently returns nothing, so aggregations are always last (see `graph_tools.py` header). (3) `shared_dependency_changes(payouts-service)` legitimately lists payments-api (deploy 7h ago) as a neighbour even before learning; risk-rules appears only once the learned edge exists (the test asserts this). (4) `search_knowledge` normalises each index's scores to its best hit and breaks ties raw-source-first, otherwise the incident summary outranked the chat thread. (5) Tool results are capped at 2,500 chars by per-tool caps plus a generic `fit()` that drops list tails and sets `truncated`.

## 2026-10-15 — Step 4 / M1: Firefighter agent
- Claude Code (Opus 5.5, unattended mega task `docs/prompts/05-mega.md`) built `backend/llm.py` (the one LLM wrapper: mock default, live via the anthropic SDK with prompt caching, price table, budget guard), `backend/agents/loop.py` (reusable `run_agent` loop with grounding), `report_schema.py`, `mock_policy.py`, `firefighter.py` + CLI, `check_run.py`, the system prompt, and 9 mock tests. Step 0 put the official track names in the registry.
- `past_incidents` now also returns `caused_by_change_to` (which of the given services had the deploy that caused the incident); the mock policy uses it to pick similar incidents.
- **Live Haiku check: SKIPPED (no key).** Per Jaya's instruction no API key was used and no live call was made. The live path (`--live`) is built and its request payload is unit-tested, but has never run against the API.
- Double-check: (1) run the live check yourself once: `python -m backend.agents.firefighter --service svc:payments-api --symptom "5xx rate 12% and p99 4.1s on payments-api for the last 15 minutes" --live`, then `python -m backend.agents.check_run runs/<file>.json`. (2) Excerpt checks compare whitespace-normalised text (chat lines wrap). (3) The grounding check also counts ids in the initial alert message as "seen".

## 2026-10-15 — Step 5 / M2: memory write-back, three-agent team, Session 2 recall
- Claude Code (Opus 5.5, unattended) built: `read_source` + `get_incident_state` read tools; `backend/tools/memory_tools.py` (10 validated write tools); `backend/memory/sessions.py` (Session + live Step persistence with NEXT/CITED); `backend/agents/team.py` (Triage → Investigator → Communicator, `resolve_incident` postmortem pass, CLI); mock policies + prompts for all four personas; `seed/scenario.py session2`; `backend/demo.py story [--compare-no-memory]`; 15 new tests incl. 5 parallel team runs. Schema v1.1 (optional props only).
- Small read-tool additions: `shared_dependency_changes` hits carry `learned_facts`; `past_incidents` returns `runbooks` sourced from each incident; `stale_knowledge` items carry `flagged`.
- **Live check: SKIPPED (no key)**, by instruction.
- Double-check: (1) time-to-cause in mock is S1 7 LLM / 13 tool calls vs S2 6 / 12. The saving is real but small: S2 skips re-reading the chat because the learned edge already records it. (2) The Investigator only re-reads a decision's source if the culprit was NOT reached through a learned edge; that rule is what makes S2 cheaper, so check you agree with it. (3) `get_incident_state` is allowed 10,000 chars (other tools 2,500) because trimming silently dropped the Investigator's handoff. (4) `update_incident` refuses seed incidents: agents can't rewrite history. (5) The resolve pass first appends the operator's words to the incident summary, so the Resolution can quote the incident verbatim.

## 2026-10-15 — M3: Ask the Brain + persistent conversation history
- Claude Code (Opus 5.5, unattended) built `backend/agents/brain.py` (`ask`, `list_sessions`, CLI), `prompts/brain.md`, the Brain mock policy, `backend/agents/brain_eval.py` (5 canned questions) and 7 tests (eval on a fresh seed and after the story, follow-up from a new Python process, per-user sessions, three grounding rejections).
- **Live check: SKIPPED (no key)**, by instruction.
- Double-check: (1) the Brain searches with *specific terms* (config keys, service names, Title Case names), because full-text search on a whole natural-language question ties every index's best hit; the live prompt says the same. (2) A follow-up's subject comes from the ids cited in earlier turns, which are reloaded from the graph (`answer` Steps) and replayed as history. (3) `citations` may be empty only when the answer says it doesn't know; that is what M6's tenant-isolation question relies on. (4) A session belongs to its user: asking with someone else's session id raises PermissionError.

## 2026-10-15 — M4: MCP server
- Claude Code (Opus 5.5, unattended) built `backend/mcp_server.py` (stdio; every registry read tool, schemas and descriptions generated from the registry; result JSON + "Cypher receipt" block; no write/agent tools), `tests/test_mcp.py` (in-process client) and `docs/mcp.md` (Claude Code + Claude Desktop config, 3 example prompts). Also checked a real stdio subprocess by hand.
- Double-check: (1) the installed SDK is **mcp 2.3**, where FastMCP was renamed `MCPServer`. I used the SDK's low-level `Server`, because the high-level decorators derive schemas from Python signatures and would duplicate the registry. (2) The `claude mcp add` syntax was taken from the local CLI's `--help`; I did not run `claude mcp add` (that changes your config).

## 2026-10-15 — M5: Backend API (local)
- Claude Code (Opus 5.5, unattended) built `backend/api/main.py` (FastAPI: health, tenants, graph overview/incident, node, SSE team run, resolve, brain ask, sessions, session replay from the graph, golden replay, admin reseed), `backend/api/guard.py` (access code with constant-time compare, daily live-run cap via Redis INCR + TTL, per-IP token bucket), `Dockerfile`, `.dockerignore`, `docker-compose.yml` (falkordb + api, healthchecks, optional .env), golden runs in `runs/golden/` (`python -m backend.demo story --quiet --save-golden`), 9 TestClient tests.
- Double-check: (1) live needs **all** of: `live: true` in the body, a correct `X-Access-Code`, `ANTHROPIC_API_KEY` on the server, and room under `DAILY_LIVE_RUNS`; anything else silently runs mock and the response says why. Over the cap returns 429. (2) Resolve counts as an agent run (no code needed, mock unless unlocked); only `/api/admin/reseed` needs the code. (3) With `ACCESS_CODE` unset, live and admin are disabled for everyone. (4) The cap test uses a separate Redis key and a mock client posing as live: no network.

## 2026-10-15 — M6: second tenant (Northwind Health) + tenant isolation
- Claude Code (Opus 5.5, unattended) wrote `seed/data/northwind_health/` (42 fully synthetic nodes: 2 teams, 8 people, 9 services, 6 deploys, 3 docs, 3 tickets, 2 chats, 2 decisions, 2 incidents, 1 runbook; systems only, no patient data), a 7-check verify set (`python -m seed.verify --graph northwind_health`), `seed.load.package_for`, the demo's "switch tenant" beat, `TENANTS` default `kestrel_pay,northwind_health`, and 5 tests.
- Double-check: (1) Northwind has its own planted story (notifications v3.2.0 / NW-88 contradicts `dec:sms-retry-cap`; the maintainer Owen Bryce has left), and the unchanged mock agents solve it. That shows the policies aren't hard-coded to Kestrel Pay. (2) Isolation is structural: one FalkorDB graph per tenant. A Kestrel id simply doesn't exist in Northwind's graph, so every write tool's validation fails cleanly. (3) Read the Northwind prose yourself; it's short.

## 2026-10-15 — 06A: setup scripts (overnight task `docs/prompts/06-overnight.md`)
- Claude Code (Opus 5.5, unattended) wrote `scripts/setup.sh` (Python ≥ 3.10 discovery, `.venv`, pinned install, `.env` from example, Docker/FalkorDB checks and start, seed + verify both tenants) and `scripts/demo.sh`; pinned `requirements.txt`; made `demo story --quiet` print headers + handoffs + summary; tests now block non-local network connections. Started `docs/explain.md`.
- Double-check: (1) setup.sh *creates* a `falkordb` container (`docker run -d --name falkordb -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest`) if none exists; it never deletes one. (2) Pins are the versions in my working venv; a fresh Python 3.12 venv installed them and passed the suite.
