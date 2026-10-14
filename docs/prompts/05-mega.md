# Claude Code MEGA TASK — milestones M1–M6 (run with Opus 5.5, high effort)

You are building most of **Incident Brain**, a FalkorDB hackathon entry. Deadline: 18 Oct 2026, 23:59 IST.
The developer (Jaya) is asleep or away while you work. Work autonomously and keep everything recoverable.

## Read first, in this order
1. `CLAUDE.md`: standing rules, finishing steps, FalkorDB quirks, track names, API budget.
2. `docs/schema.md`: LOCKED graph model, v1.0.2.
3. `docs/demo-checklist.md` and `docs/cypher.md`.
4. `docs/prompts/04-firefighter.md`: this is milestone M1, verbatim.
5. `docs/progress.md` if it exists. **If it exists you are resuming: continue from the first milestone not marked DONE.**

## The demo we are building towards (every milestone serves this)
1. An alert fires: payments-api 5xx.
2. A **team of three agents** (Triage → Investigator → Communicator) investigates by handing off through shared incident state **in the graph**. The Investigator then:
   - finds the risk-rules deploy from 40 minutes ago (RISK-412)
   - sees it contradicts a decision buried in a chat thread
   - notices the maintainer Arjun has left, so the person to call is Priya
   - **learns an undocumented dependency** (risk-rules → config-service) from that chat and writes it to the graph with sources

   The Communicator pages Priya (simulated), opens a follow-up ticket and flags the stale README.
3. An operator marks the incident resolved: "Priya rolled back the TTL". The agents write:
   - a Resolution
   - an improved Runbook v2 that SUPERSEDES v1
   - SIMILAR_TO links to past incidents
4. **Session 2:** a different service (payouts-service) alerts. The noisy-neighbour traversal finds risk-rules **only because of the learned edge**. The agents recall: "seen this before, Priya fixed it by rolling back the TTL. Runbook v2, step N."
5. Ask the Brain answers company-knowledge questions with sources, and remembers the conversation.
6. A second company's graph knows none of this (tenant isolation).

## Global rules for this task
- **Milestones run in order.** For each milestone:
  1. Implement it.
  2. Run tests. `pytest -q` must be fully green, and `python -m seed.verify --graph kestrel_pay` must pass.
  3. Do the CLAUDE.md finishing steps (ai-log, commit, `git push origin main`).
  4. Update `docs/progress.md`.

  Never start a milestone while tests are red.
- **`docs/progress.md` is the resume point.** Create it at the start. Keep a section per milestone with:
  - status (TODO / IN PROGRESS / DONE / BLOCKED)
  - commit hash
  - what was built
  - how to run it
  - decisions made and why (in plain language, since Jaya must defend them to judges)
  - open issues
  - live API spend so far

  Update it at the end of every milestone, and whenever you make a significant decision.
- **If blocked:** if a milestone stays stuck after serious effort (about 30–40 minutes of attempts), mark it BLOCKED in progress.md with the exact error and what you tried. Then continue with the next milestone that doesn't depend on it.
- **Schema:**
  - Labels and edge types are frozen.
  - You MAY add optional properties if truly needed. Record them in `docs/schema.md` §3/§4 and the changelog as v1.1, and in `seed/schema.py`.
  - Never rename or remove anything.
- **All graph writes go through the memory tools (M2):**
  - MERGE on id
  - `origin:'agent'` and `created_at` on everything agents create
  - `WRITTEN_IN` → Session for agent-written Fact/Resolution/Runbook/Ticket/Incident
  - parameterised Cypher
  - a receipt for every write, same shape as the read tools
- **LLM:**
  - Every call goes through `backend/llm.py` (built in M1).
  - Mock mode is the default everywhere, and tests are always mock.
  - Live calls are allowed ONLY at the "Live check" points below, with `claude-haiku-5-5`.
  - **Hard total budget for live calls in this whole task: $0.50.** Keep the running total in progress.md, and stop live checks if the next one could exceed it. Never use Sonnet.
- **Every agent has a mock policy.** It is deterministic, rule-based, derives its choices from tool results, and has no hard-coded answers beyond what the tools return. This keeps the whole product runnable for free, including in the later public mode.
- **Grounding everywhere:**
  - Any id an agent cites must have appeared in a tool result in that run.
  - Any `excerpt` an agent writes must be a literal substring of the source node's text.
  - Reject ungrounded writes and reports with an error result, allowing one retry.
- **Overrides for unattended running:**
  - If `ANTHROPIC_API_KEY` is missing from `.env`, do NOT stop and wait (this overrides 04-firefighter.md). Skip every live check, mark it "SKIPPED (no key)" in progress.md, and continue in mock mode.
  - In M1's Step 0 commit, also include `docs/prompts/05-mega.md`.
- **Out of scope:** web UI, deployment, public postmortems, README rewrite, demo video. Leave them for later.

---

## M1 — Firefighter agent (single agent, terminal)
Do `docs/prompts/04-firefighter.md` exactly, including its Step 0 and its single live Haiku check. That is this milestone's live check.

---

## M2 — Memory write-back, the three-agent team, Session 2 recall  ← the most important milestone

### M2.1 New read tools
Add these to the registry. Update the tests and regenerate `docs/cypher.md`.
- `read_source(node_id)`: full `text`/`rationale`/`steps` of a Doc, Ticket, ChatThread, Decision, Runbook or Incident, up to 1,800 characters (`truncated` flag if cut), plus title, author and date.

  Needed because `node_details` clips text to 200 characters and the key chat lines are further in.
- `get_incident_state(incident_id)`: the incident's props, AFFECTED services, CAUSED_BY, root causes, Facts written in its sessions, handoff notes (Step nodes with `action:'handoff'` in sessions FOR_INCIDENT it, in order), and actions taken (pages, tickets).

  **This is how agents hand off: each agent starts with an empty conversation and reads shared state from the graph.**

### M2.2 Memory/action write tools (`backend/tools/memory_tools.py`)
Same ToolOutput/receipt pattern as the read tools. Writes use `graph.query`.

Validate everything before writing:
- ids exist and have the right labels
- excerpts are literal substrings of the source text
- no duplicate learned edges

| tool | writes |
|---|---|
| `open_incident(service_id, symptom, severity)` | `Incident` {key `INC-<year>-<3-digit seq>` (next free), status 'open', started_at=now} + AFFECTED + the current Session FOR_INCIDENT it + WRITTEN_IN. |
| `update_incident(incident_id, status?, severity?, affected_ids?, cause_deploy_id?, cause_service_id?, root_cause_id?)` | Props + AFFECTED / CAUSED_BY / HAS_ROOT_CAUSE edges (additive). |
| `record_learned_dependency(from_service_id, to_service_id, kind, statement, confidence, sources:[{node_id, excerpt}])` | `Fact` (+ABOUT both services, SOURCED_FROM each source with excerpt, WRITTEN_IN) + `DEPENDS_ON {source:'learned', kind, learned_at, learned_from: fact_id}`. Refuse if any DEPENDS_ON already exists between them. |
| `record_fact(statement, about_ids, confidence, sources)` | Generic semantic memory. |
| `page_person(person_id, incident_id, message)` | Simulated page: no external call, only a Step with action 'page' that CITED the person and the incident. Refuse if the person has status 'left' (error says so: a nice demo beat). |
| `open_ticket(title, text, service_id, incident_id)` | `Ticket` {key `OPS-<n>`, kind 'incident-followup', status 'open'} + ABOUT service and incident + WRITTEN_IN. |
| `flag_stale(node_id, reason)` | Doc/Runbook `flagged_stale=true`, plus `flagged_reason` and `flagged_at` (new optional props → schema v1.1). |
| `record_resolution(incident_id, summary, steps, performed_by_ids, sources)` | `Resolution` + RESOLVED_BY + PERFORMED_BY + SOURCED_FROM (the incident itself is a valid source) + WRITTEN_IN; incident → status 'resolved', resolved_at. |
| `link_similar(incident_id, other_id, score, reason)` | SIMILAR_TO {score, reason}. |
| `write_runbook(service_id, title, steps, sources, supersedes_id?)` | New `Runbook` (version = old+1 if superseding), DESCRIBES, SOURCED_FROM, SUPERSEDES old, WRITTEN_IN. Ids like `rb:<slug>-v2`. |

### M2.3 Sessions and steps persisted live (`backend/memory/sessions.py`)
- `start_session(tenant, user, mode)` → `Session` node.
- Every agent step from the run loop is written as a `Step` node **as it happens**:
  - `IN_SESSION`, and `NEXT` from the previous step
  - `CITED` → every highlight node id from the step's receipt
  - `cypher` and `params_json` from the receipt
  - a one-line `summary`
- Handoffs are Steps with `action:'handoff'`, whose `summary` is the handoff note.
- Refactor the M1 loop into a reusable `run_agent(agent_name, system_prompt, tools, initial_message, ...)`. The Firefighter keeps working on top of it, and its tests stay green.

### M2.4 The team (`backend/agents/team.py`)
`run_team(alert, tenant, user, llm) -> record`:
- The orchestrator starts a Session (mode 'team') and runs three agents **sequentially**. Each starts with a fresh conversation that contains only the alert plus `get_incident_state` output.
- Each agent ends by calling its own submit tool (`submit_handoff` / `submit_report`), which writes a handoff Step.

The three agents:
- **Triage**
  - Read tools: find_service, blast_radius, critical_services, past_incidents, get_incident_state.
  - Write tools: open_incident, update_incident (severity / affected).
  - Handoff: severity + reasoning (tier, PageRank), blast radius, "seen before?" hints.
- **Investigator**
  - Read tools: recent_changes_downstream, shared_dependency_changes, dependency_path, decisions_about, read_source, past_incidents, who_to_call, node_details, get_incident_state.
  - Write tools: update_incident (cause, root cause, affected), record_learned_dependency, record_fact, link_similar.
  - Prompt rule: when a source reveals a dependency that the graph lacks, record it with the exact quote. It must find the risk-rules → config-service dependency by reading `chat:risk-eng-config-load` through `decisions_about` → `read_source`.
  - Handoff: cause, path, evidence, learned facts, contact candidates.
- **Communicator**
  - Read tools: who_to_call, stale_knowledge, get_incident_state.
  - Write tools: page_person, open_ticket, flag_stale.
  - Output: the final report (extend M1's `submit_report` with `actions_taken` and `learned`) and a short status-update message for humans.

**Operator action:** `resolve_incident(incident_id, resolved_by_ids, what_fixed_it, tenant, llm)` runs a short Communicator pass in "postmortem" mode. It must:
- write a Resolution sourced from the incident
- write Runbook v2 superseding the runbook for the most relevant service (`rb:fraud-scoring-latency` → v2, adding concrete steps about the risk-rules RULES_CACHE_TTL and config-service load)
- link_similar to past incidents with the same root cause (inc:2025-031, inc:2026-012)
- set the root cause on the incident if it isn't set

**Scenario helper** (`seed/scenario.py`): `python -m seed.scenario session2 --graph kestrel_pay` adds `dep:risk-rules-v2.8.1` (now − 5 min, by Leo, "RISK-412 follow-up: re-enable 5s TTL for EU ruleset", CHANGED risk-rules, FOR_TICKET RISK-412). It has `origin:'seed'` because it is a world event, not agent memory. This makes Session 2 a fresh, realistic regression.

**CLI:** `python -m backend.agents.team run --service svc:payments-api --symptom "..."`, `... resolve INC-... --by per:priya-nair --summary "..."`, `... state INC-...`.
- It prints a readable trace grouped by agent, with handoff notes and writes highlighted. `[WRITE]` lines show the Cypher.
- `--live` switches to the real LLM.

**Metrics in the record:** time to cause (LLM calls and tool calls until `update_incident` sets the cause). Print it so we can show that "Session 2 found the cause in N calls vs M in Session 1".

### M2.5 `python -m backend.demo story` — the whole demo storyline, mock by default
1. Re-seed `kestrel_pay`.
2. Run the Session 1 team on payments-api.
3. Resolve it as Priya.
4. Run the `session2` scenario.
5. Run the Session 2 team on payouts-service.
6. Print a side-by-side summary:
   - S1 vs S2 time-to-cause
   - which learned edge made S2 possible
   - the agent-written nodes, by label
   - the Cypher to paste into the FalkorDB Browser to SEE the memory: `MATCH (n {origin:'agent'})-[r]-(m) RETURN n,r,m`

Also add `--compare-no-memory`. It runs Session 2 on a fresh seed **without** Session 1. The agents should NOT find risk-rules, and the report must honestly say the cause is unknown or low-confidence. This proves memory is what made the difference.

### M2 tests (mock)
- Each write tool:
  - happy path
  - validation failures: bad id, non-literal excerpt, duplicate learned edge, paging a person who left
  - `origin:'agent'`, WRITTEN_IN and the receipt are present
- Session 1 team run, all of these:
  - incident opened
  - cause = dep:risk-rules-v2.8.0
  - learned edge risk-rules→config-service exists with a Fact SOURCED_FROM chat:risk-eng-config-load
  - Priya paged
  - OPS ticket open
  - doc:risk-rules-readme flagged
  - Step chain unbroken (NEXT from first to last)
  - 3 handoff steps
- Resolve:
  - Resolution PERFORMED_BY Priya
  - `rb:fraud-scoring-latency-v2` SUPERSEDES v1
  - SIMILAR_TO inc:2025-031
- Session 2 (after scenario): shared_dependency_changes finds risk-rules via a learned hop; the report recalls the Session 1 incident and Priya's fix; time-to-cause < Session 1.
- No-memory compare: Session 2 does NOT name risk-rules as the cause.
- **Concurrency:** 5 team runs in parallel threads (mock) on the test graph give 5 incidents with distinct keys, unbroken step chains, no duplicate ids, and no lost writes. If FalkorDB/MERGE races cause key collisions, fix them (e.g. allocate keys in a single query, or retry on conflict) and explain in progress.md. This covers the "high-concurrency reads/writes" bullet in Track 2.
- Steps CITED only existing nodes.

### M2 live check
One live Haiku run of the full `backend.demo story` (S1 + resolve + S2). Then:
- Record cost and pass/fail of the same assertions in progress.md.
- If Haiku fails specific assertions, you may tune prompts and tool descriptions (max 2 more live attempts, within budget). Do not weaken the assertions or make the tools "cheat".

---

## M3 — Ask the Brain (Track 3) + persistent conversation history
- Agent `brain`.
  - Read tools: search_knowledge, decisions_about, who_to_call, read_source, node_details, stale_knowledge, find_service, past_incidents.
  - Write tool: flag_stale.
  - Ends with `submit_answer {answer (≤ 150 words), citations:[{node_id, excerpt}] (≥1, grounded and literal), people:[person ids], stale_warnings:[{node_id, reason}]}`.
- `ask(tenant, user, question, session_id=None)`:
  - Persists a Session (mode 'brain') and Steps. Each Q&A turn is stored as an `answer` Step with the question and answer in its summary or params.
  - When `session_id` is given, the prior turns of that session are loaded **from the graph** and given to the agent as conversation history. So "and who should I ask about it?" works as a follow-up across process restarts.
  - Sessions are per `user`. `list_sessions(user)` returns only that user's sessions.
- CLI: `python -m backend.agents.brain ask "..." [--session ses:...] [--user jaya] [--live]`.
- Canned eval set (`backend/agents/brain_eval.py`, mock + optional live). Each question has expected citations/people:
  1. "Why must RULES_CACHE_TTL stay at 300 seconds?" → dec:rules-cache-ttl + chat:risk-eng-config-load.
  2. "Arjun left. Who knows risk-rules best now?" → per:priya-nair.
  3. "I'm new on Payments Core. What should I read first?" → the Payments Core onboarding doc + ≥1 decision about a Payments Core service.
  4. "Which docs about risk-rules are out of date, and why?" → doc:risk-rules-readme. After the M2 story, also expect the `missing_learned_dependency` reason.
  5. Follow-up in the same session as Q1: "Who should I talk to about that?" → per:priya-nair, resolved from the history.
- Tests (mock):
  - eval passes
  - follow-up works after a new Python process (load from graph)
  - user A can't list user B's sessions
  - grounding rejects a fake citation
- Live check: one Haiku pass of the 5 eval questions. Record cost and results.

---

## M4 — MCP server (Track 1: "tool selection via MCP")
- Use the official `mcp` Python SDK (FastMCP), stdio transport. `python -m backend.mcp_server --tenant kestrel_pay`.
- Expose all **read** tools from the registry. Generate this from the registry, don't duplicate code: descriptions and JSON schemas come straight from it.
- Tool output = the `result` JSON, plus the receipt's Cypher as a second text block labelled "Cypher receipt".
- No write tools and no agent-running tools over MCP (safety + cost).
- Tests: an in-process MCP client lists the tools (count matches the registry) and calls `recent_changes_downstream` on the test graph.
- Docs: `docs/mcp.md` with exact config snippets to use it from Claude Desktop and Claude Code (`claude mcp add ...`). Check current syntax in the docs. Include 3 example prompts.

---

## M5 — Backend API (local; deployment comes later)
FastAPI app `backend/api/` (`uvicorn backend.api.main:app`).

**Endpoints:**
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/tenants` | List tenants |
| GET | `/api/graph?tenant=&mode=overview\|incident&id=` | Nodes and edges for a graph panel, capped at ~300. Each node has id, label, name/title, origin; each edge has from, type, to, source. |
| GET | `/api/node/{id}` | Node details |
| POST | `/api/team/run` | Body: `{tenant, service_id, symptom}`. **Streams Server-Sent Events**: `step` (agent, tool, args, summary, receipt), `handoff`, `write`, `report`, `done`, `error`. |
| POST | `/api/incidents/{id}/resolve` | Resolve an incident |
| POST | `/api/brain/ask` | Body: `{tenant, user, question, session_id?}` |
| GET | `/api/sessions?tenant=&user=` | List sessions |
| GET | `/api/sessions/{id}` | Full session with steps; used for replay |
| POST | `/api/replay/{run_file}` | Streams a recorded run from `runs/golden/` with realistic delays. No LLM. |
| POST | `/api/admin/reseed` | Re-seed |

**Protection (all from env):**
- **Live mode needs the access code.** Requests with a correct `X-Access-Code` header (`ACCESS_CODE`, compared in constant time) may use the live LLM. Without it, agents run in **mock mode** and the response says so. The product is fully explorable for free; the live model is gated.
- **Daily cap** on live runs (`DAILY_LIVE_RUNS`, default 30): a counter in FalkorDB's Redis, key `ib:live_runs:<YYYY-MM-DD>` via INCR with a TTL.
- **Per-IP rate limit:** in-memory token bucket, `RATE_LIMIT_PER_MIN` (default 20).
- **Admin endpoints and writes outside agent runs** require the access code.
- **CORS** allowlist from env.

**Packaging and tests:**
- `Dockerfile` for the API plus `docker-compose.yml` (falkordb + api, healthcheck, env file) so deployment day is quick. Verify `docker compose config` parses. Don't deploy.
- Tests (FastAPI TestClient, mock mode):
  - every endpoint
  - an SSE stream yields `step`/`handoff`/`report`/`done` in order
  - with no access code the run is forced to mock
  - a wrong code is rejected for admin
  - the daily cap blocks run N+1 (test with cap=1)
  - the rate limit triggers

---

## M6 — Second tenant: tenant isolation (stretch; Track 2 "separate memory per tenant")
- A small second company `northwind_health` (`seed/data/northwind_health/`, ~40 nodes):
  - different domain (appointments, patient-portal, lab-results, notifications…), 2 teams, ~8 people, a few docs, decisions and 2 past incidents
  - its own small planted story is fine
  - fully synthetic; no real patient data of any kind
- `TENANTS=kestrel_pay,northwind_health`. Loader, verify (a minimal check set for this tenant), API and MCP all accept it.
- Tests:
  - After the M2 story on kestrel_pay, northwind_health has zero `origin:'agent'` nodes.
  - A Brain question about "RULES_CACHE_TTL" on northwind returns no citations, and the answer says it doesn't know.
  - Memory/session tools can't reference ids from the other tenant (the validation fails cleanly).
- Add it to `backend.demo` as a final "switch tenant" beat.

---

## When everything is done (or you must stop)
- `docs/progress.md` must contain:
  - a status table for M1–M6 with commit hashes
  - total live spend
  - "How to run the demo story" in 5 commands
  - "Things Jaya must understand before judging": the 8–10 most important design decisions, each in 2–3 plain sentences
  - known issues
  - suggested next steps: UI, deployment, public postmortems, README/video
- Update `docs/demo-checklist.md` with anything new (e.g. run `seed.scenario session2` before Session 2).
- Final commit + push per CLAUDE.md.
- Final message: a short summary pointing to progress.md.
