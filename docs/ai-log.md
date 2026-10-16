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

## 2026-10-15 — 06B: memory-first recall
- Claude Code (Opus 5.5, unattended) added read tool `memory_recall` (5 parameterised read queries; registry/MCP/docs generated), made the Investigator and Firefighter recall first and verify memory's suspect with one tool (mock policy + live prompts), added the "Seen before … see Runbook vN step K" line, `time_to_cause.agent_tool_calls`, a three-column before/after box (`--compare-no-memory` now runs the no-memory contrast and then the full story), removed "Kestrel Pay" from all agent prompts, regenerated golden runs and docs, 6 new tests.
- Double-check: (1) recall only returns **agent-written** memory (`origin:'agent'` incidents); seeded incidents are deliberately excluded so Session 1 recalls nothing (do you agree?). (2) "within 3 tool calls" is the Investigator's count (3); from session start it is 9 because Triage runs first. (3) Session 1 now makes one extra (empty) call: 14 tool / 8 LLM calls vs 13 / 7 before. (4) `Q_RECALL_RUNBOOKS` uses `SUPERSEDES*0..5` and `WHERE NOT ()-[:SUPERSEDES]->(latest)`; both work on this FalkorDB.

## 2026-10-15 — 06C: public postmortems layer
- Claude Code (Opus 5.5, unattended) fetched and read ~25 candidate public postmortems, kept the 21 whose facts it could check on the page itself, wrote its own ≤ 60-word summary for each and tagged root causes (`seed/data/public_postmortems.json`, generated `docs/postmortems.md`). Loader adds them to every tenant; verify checks them; new read tool `industry_matches`; resolve writes `SIMILAR_TO` to the best 1–2; reports gain `industry_pattern`. Renamed Northwind's `rc:nw-retry-storm` → `rc:retry-storm`.
- Double-check: (1) **read the 21 summaries yourself** (`docs/postmortems.md`); they are about real companies. (2) No certificate-expiry postmortem made it in (no primary page could be verified). (3) The root-cause tags are judgement calls, especially Datadog 2023 and the two cache-stampede tags.

## 2026-10-15 — 06D: Brain eval 5 → 15 (+3 Northwind)
- Claude Code (Opus 5.5, unattended) grew `brain_eval.py` to 15 Kestrel + 3 Northwind questions (new grading: citations_any, answer_has, quote_has, dont_know, refused other user, subprocess follow-up), added Brain intents (blast, seen, session, industry), fixed the weak-hit fallback that answered unanswerable questions, schema v1.2 (two full-text indexes), prompt updated. Result 15/15 + 3/3.
- Double-check: (1) the eval expects Omar Haddad as config-service owner (maintainer, 95 commits) and Maya Okoro for Northwind notifications: read from the seed, not assumed. (2) Schema v1.2 is index-only; I bumped the version per the overnight rules rather than asking. (3) The industry question relies on the root cause's *name* containing the words ("thundering herd", "retry storm").

## 2026-10-15 — 06E: README draft
- Claude Code (Opus 5.5, unattended) wrote the README draft, `docs/live-mode.md`, refreshed `docs/demo-checklist.md`, and let `brain_eval --live` run the restart case in-process.
- Double-check: (1) paste the official track focus bullets into the three `TODO:` lines; I didn't have them. (2) The quickstart's `git clone` URL assumes the repo is public. (3) Every number in the README is from mock mode, and it says so.

## 2026-10-15 — 06F: hardening pass
- Claude Code (Opus 5.5, unattended) ran one independent reviewer subagent (read-only, no network) over the 8 areas in the spec, then fixed: `record_resolution` overwriting seed history (high), `link_similar` from seed incidents, agents quoting their own incident text, ungrounded second submits being accepted, nested schema/excerpt checks, story ids in tool descriptions and the Brain prompt, `package_for` silently defaulting to Kestrel, plus 6 low items. Remaining low items are listed in progress.md 06F. Final: fresh venv `pytest -q` 105 passed ×3, verify 14/14 + 8/8, demo box pasted into progress.md.
- Double-check: (1) an ungrounded run now has `status: ungrounded` and `report: None`; the API/UI should show that state rather than an empty answer. (2) An agent-written incident is quotable only after "Resolution (operator): "; the resolve pass writes exactly that prefix. (3) FalkorDB is now bound to 127.0.0.1 by `scripts/setup.sh` and compose; an existing container keeps its old port binding.

## 2026-10-15 — 07-0: preflight + demo script
- Claude Code (Opus 5.5, unattended) ran the 07 preflight (Node v22.23.2 → Vite path; Docker + FalkorDB up; setup.sh clean; pytest 105 passed) and wrote `docs/demo-script.md`, a 2:45 shot list in 7 beats.
- Double-check: (1) the narrator lines are mine; read them aloud once for timing. (2) The script assumes replay mode at 1× and a 1920×1080 window.

## 2026-10-15 — 07A: API additions for the UI
- Claude Code (Opus 5.5, unattended) added `backend/api/views.py` (elements, step events, run graphs, compare, suggestions, Explorer), story beats in `backend/demo.py`, 11 endpoints, the access-code gate on every write (incl. the existing team-run and resolve endpoints), Brain answers without persistence, a single-use stream token for EventSource, `seed/conn.py`, golden runs with embedded graph snapshots (+ the no-memory recording), 11 new tests.
- Double-check: (1) **behaviour change:** `/api/team/run` and `/api/incidents/{id}/resolve` now return 403 without the code. (2) The fresh "compare" beat runs on an internal twin graph `<tenant>__nomem` that is deleted afterwards; `get_graph` allows that suffix. (3) Brain mock stop words gained "decide"/"decided".

## 2026-10-15 — 07B: frontend
- Claude Code (Opus 5.5, unattended) built `frontend/` (React 19, Vite 8, TS 7, Tailwind 4, zustand, Cytoscape + fcose): theme system, app shell, Story view (timeline, growing graph with the learned-edge draw-in, receipt drawer, report card, controls, before/after), Ask the Brain, Explorer; 17 vitest tests (theme store, replay reducer). `scripts/ui.sh`; FastAPI serves `frontend/dist` with an index.html fallback. Rate limit now only on `/api/*`, default 60/min (also changed in `.env` and `.env.example`).
- Double-check: (1) **your local `.env` was edited:** `RATE_LIMIT_PER_MIN` 20 → 60 (20/min was too low for the UI's page loads). (2) The bundle is ~850 KB (262 KB gzip), mostly Cytoscape. (3) The About dialog links to github.com/jsuryacodes/incident-brain.

## 2026-10-15 — 07D: headless-browser self-check
- Claude Code (Opus 5.5, unattended) wrote 10 Playwright tests + `scripts/e2e.sh`, generated `docs/screenshots/` (light + dark, 1920 hero, phone), looked at every screenshot and ran 3 polish rounds (fixes listed in progress.md 07D). Found and fixed a mock-Brain bug (history used for unrelated questions).
- Double-check: (1) open `docs/screenshots/story-learned-edge-1920.png` and the two `story-before-after-*.png`. (2) `scripts/e2e.sh` re-seeds the real `kestrel_pay` and `northwind_health` graphs (then replays the story into them).

## 2026-10-15 — 07C: deploy-ready container
- Claude Code (Opus 5.5, unattended) wrote the multi-stage Dockerfile, `SEED_ON_START` (seed + verify + mock story, only for empty graphs), `docker-compose.yml` (app + FalkorDB) and `docker-compose.prod.yml` (app only, FalkorDB from env), `docs/deploy.md`; verified `docker build`, `docker compose up` and Playwright 10/10 against the container; removed the test stack afterwards. Nothing deployed.
- Double-check: (1) compose's app port is now bound to 127.0.0.1 (was 0.0.0.0). (2) The compose service was renamed `api` → `app`. (3) `docker-compose.prod.yml` publishes `${PORT}` on all interfaces, as a host would.

## 2026-10-15 — 07E: docs
- Claude Code (Opus 5.5, unattended) updated README (screenshots, run-the-UI, three views ↔ tracks), `docs/explain.md` (UI data flow, stable layout, gate, judge Q&A), `docs/demo-script.md` (measured replay lengths), `docs/progress.md` (final status, morning list, decisions, gaps).
- Double-check: (1) the README still says "Draft" and keeps the video / live URL / official-track-bullet `TODO:`s. (2) Commit `c4a4a1b`'s message says "pytest 119"; the real count is 118 (history not rewritten).

## 2026-10-16 — 08A1: eval scenario library + oracle
- Claude Code (Opus 5.5, unattended) added `seed/eval_scenarios.py` (12 scenarios as fixtures), `seed.load.build()` + `load(transform=)`, internal twin graphs `<tenant>__eval_<id>` in `backend/db.py`, and `tests/test_eval_scenarios.py` (an oracle that re-derives every expectation without Cypher). A held-out set's hash is recorded in progress.md.
- Double-check: (1) read the "why" line of each scenario in `seed/eval_scenarios.py`: is each a fair test? (2) The departed-owner scenarios drop one WORKED_ON edge in the twin only.

## 2026-10-16 — 08A2: tools for the eval
- Claude Code (Opus 5.5, unattended) added `recent_changes`, self-change hits (hops 0) in `recent_changes_downstream`, `critical_services(downstream_of)`, the no-algorithms mode, and real tool output in docs/cypher.md. Found a FalkorDB 6.0.2 server crash on a NULL-heavy aggregation and worked around it.
- Double-check: (1) `dependency_path` from a service to itself now answers found, length 0. (2) docs/cypher.md's "Verified" blocks change on every regeneration (times are relative to the seed).

## 2026-10-16 — 08A3: generalised Firefighter planner
- Claude Code (Opus 5.5, unattended) wrote `backend/agents/ff_policy.py` (mock planner: leads from the change log, judged by the graph; multi-alert; team escalation; look_first; tool-aware), optional report fields, the matching live prompt, `shared_callers` in shared_dependency_changes, 10 new tests. Four adversarial verifier rounds; every finding fixed.
- Double-check: (1) the neighbour rule's threshold (fewer than 4 services reach the shared dependency = "narrow") in `ff_policy.py`; (2) read one report's `rejected_leads` (e.g. `python -m backend.agents.firefighter --service svc:payments-api --symptom "5xx"`): are the reasons convincing?

## 2026-10-16 — 08A4/08A5: oracle, generator, eval runner
- Claude Code (Opus 5.5, unattended) moved the oracle to `seed/eval_oracle.py`, added the seeded generator, the eval runner (`backend/agents/firefighter_eval.py`), `GET /api/eval/latest`, `docs/eval.md`, scorer loophole tests.
- Double-check: `docs/eval.md` (is the table readable?), and that `python -m backend.agents.firefighter_eval` takes ~10 s on your machine.

## 2026-10-16 — 08A6: "graph, no algorithms" baseline
- Claude Code (Opus 5.5, unattended) added `backend/agents/baseline_noalgo.py`, a plain-Cypher `fan_in` mode for critical_services, a PageRank→fan_in fallback in the planner, a deterministic tie-break in search_knowledge, eval table/wording fixes.
- Double-check: the baseline ties the full profile on single alerts; that is the honest result and docs/eval.md says so.

## 2026-10-16 — 08A7: "no graph" baseline
- Claude Code (Opus 5.5, unattended) added `backend/agents/baseline_text.py`, team ids in `find_service`, snippet matching and team escalation for the no-graph path, deterministic full-text ordering.
- Double-check: docs/eval.md's fairness note under the table (why "scenarios passed" is 0 for this profile by construction).

## 2026-10-16 — 08A8: held-out eval set
- Claude Code (Opus 5.5, unattended) ran the held-out scenarios once (6/6 full), then committed them as `seed/eval_holdout.py` (now a permanent eval set) with the hash and a caveat about the author's brief.
- Double-check: the caveat in the file header.

## 2026-10-16 — 08C: alert storm
- Claude Code (Opus 5.5, unattended) added four algorithm tools (storm_tools.py), storm correlation in the Firefighter planner, 3 storm scenarios, the storm story beat backend (golden replay, /api/storm/latest), tests.
- Double-check: (1) `connected_impact` writes a temporary projection graph (not the tenant graph) — the MCP "read-only" wording should mention it; (2) `python -m backend.demo storm` prints the naive-vs-agent numbers.

## 2026-10-16 — 08B: hypotheses and why-this-tool
- Claude Code (Opus 5.5, unattended) added `why` lines to every turn (mock + prompts), the Firefighter's hypothesis board and confidence breakdown, the Investigator's board in its handoff, Step.why / Step.hypotheses_json (schema v1.3), tests incl. a fake live client.
- Double-check: docs/schema.md v1.3 changelog (two optional Step properties; you asked to approve schema changes).

## 2026-10-16 — 08D: action plan, safety check, approval
- Claude Code (Opus 5.5, unattended) added `rollback_safety`, the Firefighter `action_plan`, `backend/agents/actions.py` (simulated, idempotent execution on twins + verification), `POST /api/actions/execute`, tests; re-recorded the storm replay with an approved execution.
- Double-check: the "hard to undo" word list in `graph_tools.rollback_safety` (IRREVERSIBLE).

## 2026-10-16 — 08G: UI for A-D
- Claude Code (Opus 5.5, unattended) built the Firefighter view, the Eval view, Story hooks (storm, why a graph, why lines, hypotheses tab), playground API + 15 recordings, a Playwright spec with screenshots.
- Double-check: open `docs/screenshots/ff-storm-1920.png`, `ff-hypotheses-*.png`, `ff-safety-hold-*.png`, `eval-why-a-graph-*.png`.
