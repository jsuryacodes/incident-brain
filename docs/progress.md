# Progress — mega task M1–M6

Resume point for `docs/prompts/05-mega.md`. Continue from the first milestone not marked DONE.

**Run constraint (from Jaya, 15 Oct 2026):** build all LLM code, but make **no live API calls** and use **no API key**. Every "Live check" is therefore `SKIPPED (no key)`; all runs are mock mode.

**Live API spend so far: $0.00**

| Milestone | Status | Commit |
|---|---|---|
| M1 Firefighter agent | DONE (live check SKIPPED, no key) | 5f54e03 |
| M2 Memory write-back + team + Session 2 | DONE (live check SKIPPED, no key) | 66db978 |
| M3 Ask the Brain | DONE (live check SKIPPED, no key) | bd91e13 |
| M4 MCP server | IN PROGRESS | — |
| M5 Backend API | TODO | — |
| M6 Second tenant | TODO | — |

## M1 — Firefighter agent
**Status:** DONE · commit `5f54e03` (step 0: `2f26e45`) · live check: **SKIPPED (no key)** · live spend $0.00

**What was built**
- `backend/llm.py`: the only LLM wrapper. `LLMClient(mode, model)`; mode defaults to `mock` (env `LLM_MODE`), model to `claude-haiku-5-5`. Live mode uses the anthropic SDK with `cache_control` on the system block and the last tool. `PRICES` table → `cost_usd` per call. Budget guard via `MAX_RUN_COST_USD` (default 0.05).
- `backend/agents/loop.py`: `run_agent(...)`, the reusable loop (LLM → run every tool_use → all results back in one message → repeat). Tool exceptions become error results. Grounding: ids must have appeared in a tool result; excerpts must be literal quotes; one retry. Also the one-line step summaries and the trace printer.
- `backend/agents/firefighter.py` (+ CLI), `prompts/firefighter.md`, `report_schema.py` (strict `submit_report` schema + grounding checker), `mock_policy.py` (deterministic stand-in), `check_run.py` (12 story assertions).
- `past_incidents` now also returns `caused_by_change_to`.

**How to run**
```
python -m backend.agents.firefighter --service svc:payments-api --symptom "5xx rate 12% and p99 4.1s on payments-api for the last 15 minutes"
python -m backend.agents.check_run runs/<file>.json      # 12/12 PASS in mock
```
Add `--live` (needs `ANTHROPIC_API_KEY` in `.env`) to use Haiku; `--show-cypher` prints receipts.

**Decisions (plain language)**
- *One loop for every agent.* The Firefighter is just `run_agent` with the 12 read tools plus `submit_report`. M2's three agents reuse the same loop, so grounding, budget and receipts are enforced in one place.
- *The report is a tool call.* Making the model call `submit_report` with a strict JSON schema gives structured output we can check by machine, instead of parsing prose.
- *Grounding.* The loop remembers every id that came back from a tool. A report citing an id it never saw (e.g. `per:made-up`) is rejected once with the list of bad ids; a second failure is recorded as `grounding.ok = false`. Quotes are checked against the source node's real text.
- *Mock policy.* A rule-based "fake model" reads the tool results and makes the same calls a good model would. It derives the culprit, contact, conflicting decision (shared words between the change and the decision title) and similar incidents from tool output, so it also works for other services. This keeps development, tests and the future public demo free.

**Open issues**
- The live Haiku check has never run (no key by instruction). Run it once when a key is added; see the commands above.

## M2 — Memory write-back, three-agent team, Session 2 recall
**Status:** DONE · commit `66db978` · live check: **SKIPPED (no key)** · live spend $0.00

**What was built**
- Read tools `read_source` (full text up to 1,800 chars + mentions/describes) and `get_incident_state` (the shared incident state: props, affected, cause, root causes, facts, handoff notes, actions, tickets, similar incidents, resolution).
- `backend/tools/memory_tools.py`: `open_incident`, `update_incident`, `record_learned_dependency`, `record_fact`, `page_person` (simulated), `open_ticket`, `flag_stale`, `record_resolution`, `link_similar`, `write_runbook`. Same result + receipt shape as the read tools; receipts mark write queries.
- `backend/memory/sessions.py`: `start_session`, and `StepLog`, which writes every step as a `Step` node as it happens (IN_SESSION, NEXT, CITED, cypher, params_json, summary).
- `backend/agents/team.py`: `run_team` (Triage → Investigator → Communicator), `resolve_incident` (postmortem pass), CLI. Run records go to `runs/team-*.json` / `runs/resolve-*.json` with `time_to_cause`.
- `seed/scenario.py session2`; `backend/demo.py story [--compare-no-memory]`.
- Schema v1.1: optional `flagged_reason`/`flagged_at` (Doc, Runbook), `flagged_stale` (Runbook), `origin`/`created_at` on agent-written edges.

**How to run**
```
python -m backend.demo story                       # re-seed, S1, resolve, session2 scenario, S2, summary
python -m backend.demo story --compare-no-memory   # S2 on a fresh seed: cause unknown
python -m backend.agents.team run --service svc:payments-api --symptom "5xx rate 12% ..."
python -m backend.agents.team resolve INC-2026-032 --by per:priya-nair --summary "Priya rolled back RULES_CACHE_TTL to 300s; config-service load recovered"
python -m seed.scenario session2 --graph kestrel_pay
python -m backend.agents.team run --service svc:payouts-service --symptom "payout batch API 5xx 9% ..."
python -m backend.agents.team state INC-2026-032
```
Mock result: S1 finds `dep:risk-rules-v2.8.0`, learns `risk-rules → config-service` from `chat:risk-eng-config-load`, pages Priya, opens OPS-1, flags the README. Resolve writes `res:2026-032` and `rb:fraud-scoring-latency-v2` (SUPERSEDES v1), links INC-2025-031 / INC-2026-012. S2 (payouts-service) finds risk-rules **only via the learned edge**, recalls "Priya rolled back RULES_CACHE_TTL…" and "rb:fraud-scoring-latency-v2 step 2". Time to cause: **S1 7 LLM / 13 tool calls, S2 6 / 12**. Without memory, S2 reports the cause as unknown (confidence low).

**Decisions (plain language)**
- *Handoff through the graph, not through chat.* Each agent starts with an empty conversation: just the alert plus `get_incident_state`. Everything one agent tells the next is a `Step` node in the graph (note + structured details in `params_json`). So the team is crash-safe, inspectable in the FalkorDB Browser, and the same mechanism works across processes.
- *Learning changes the structure.* When the Investigator reads the chat sentence "On every cache miss risk-rules polls config-service's internal /v1/rulesets endpoint." it writes a `Fact` (with that exact quote on `SOURCED_FROM`) and a `DEPENDS_ON {source:'learned'}` edge. Session 2's unchanged noisy-neighbour query then finds risk-rules because the graph changed, not because a prompt did.
- *Why S2 is cheaper.* With a learned edge on the path, the Investigator doesn't re-read the decision's source: the learned Fact already cites it. It also recalls the Session 1 incident (same culprit, resolved, with a runbook) through `past_incidents`. Honest framing: the saving is one LLM call and one tool call; the big difference is that S2 finds the cause at all (see `--compare-no-memory`).
- *Validation before every write.* Ids must exist with the right label; excerpts must be literal quotes of the source (whitespace-normalised); a learned edge is refused if any `DEPENDS_ON` already exists between the two services; paging someone who left is refused ("left the company 95 days ago"). Write tools may only use ids the agent has already seen in a tool result.
- *Concurrency.* Incident keys (`INC-2026-0NN`), ticket keys (`OPS-n`) and the learned edge are each allocated/checked and created in ONE Cypher query. FalkorDB runs write queries one at a time per graph, so that is atomic. No retry logic was needed: 5 parallel team runs (repeated 5×) gave 5 distinct incidents and tickets, 1 learned edge, no duplicate ids and unbroken step chains.
- *Seeded history is read-only.* `update_incident` refuses `origin:'seed'` incidents, so agents can add to the company's history but not rewrite it.
- *Operator words become a source.* The resolve pass first appends "Resolution (operator): …" to the incident summary, so the Resolution and Runbook v2 can quote the incident verbatim like any other source.

**Open issues**
- Live run of the story never done (no key). When a key exists: `python -m backend.demo story --live` (about 30 Haiku calls).
- `get_incident_state` may return up to 10,000 chars (≈2.5k tokens); fine for a few sessions per incident.
- Incident keys assume < 1,000 incidents per year (3-digit sequence).

## M3 — Ask the Brain + persistent conversation history
**Status:** DONE · commit `bd91e13` · live check: **SKIPPED (no key)** · live spend $0.00

**What was built**
- `backend/agents/brain.py`: `ask(tenant, user, question, session_id=None)` and `list_sessions(tenant, user)`, plus the CLI. Brain agent = 8 read tools + `flag_stale` + `submit_answer {answer ≤150 words, citations [{node_id, excerpt}], people, stale_warnings}`.
- Each turn is an `answer` Step in a `brain` Session; `params_json` holds question, answer, citations and people.
- `backend/agents/brain_eval.py`: the 5 canned questions with expected citations/people. Mock: 5/5 on a fresh seed and 5/5 after the M2 story (Q4 then also reports `missing_learned_dependency`).

**How to run**
```
python -m backend.agents.brain ask "Why must RULES_CACHE_TTL stay at 300 seconds?"
python -m backend.agents.brain ask "Who should I talk to about that?" --session ses:...   # works in a new process
python -m backend.agents.brain sessions --user jaya
python -m backend.agents.brain_eval            # add --live for one Haiku pass (~20 calls)
```

**Decisions (plain language)**
- *Conversation memory lives in the graph.* A follow-up loads the earlier turns from that session's `answer` Steps and replays them as history. Nothing is kept in process memory, so "who should I talk to about that?" works after a restart, and every turn is inspectable in the Browser.
- *"That" is resolved from what was cited.* The follow-up's subject comes from the sources cited in the earlier answer (e.g. `dec:rules-cache-ttl` is ABOUT `svc:risk-rules`), not from guessing.
- *Answers must quote.* At least one citation whose excerpt is a literal quote of the cited node, unless the Brain says it doesn't know. Fake ids, misquotes and missing citations are rejected (one retry), same rules as the incident agents.
- *Search with specific terms.* Full-text search on the whole question is weak, so the Brain searches for config keys, service names and Title Case names, then reads the best sources in full.
- *Sessions are per user.* `list_sessions` filters on the Session's `user`; continuing someone else's session is refused.

**Open issues**
- Live eval never run (no key).
- A "who" answer with no source mentioning the person falls back to "I don't know", because citations are mandatory. A softer fallback (cite the past incident's postmortem) could be added.
