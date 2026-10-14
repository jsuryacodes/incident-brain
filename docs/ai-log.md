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
