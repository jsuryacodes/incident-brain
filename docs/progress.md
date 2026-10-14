# Progress — mega task M1–M6

Resume point for `docs/prompts/05-mega.md`. Continue from the first milestone not marked DONE.

**Run constraint (from Jaya, 15 Oct 2026):** build all LLM code, but make **no live API calls** and use **no API key**. Every "Live check" is therefore `SKIPPED (no key)`; all runs are mock mode.

**Live API spend so far: $0.00**

| Milestone | Status | Commit |
|---|---|---|
| M1 Firefighter agent | DONE (live check SKIPPED, no key) | 5f54e03 |
| M2 Memory write-back + team + Session 2 | IN PROGRESS | — |
| M3 Ask the Brain | TODO | — |
| M4 MCP server | TODO | — |
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
