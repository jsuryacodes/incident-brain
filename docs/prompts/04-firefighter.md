# Claude Code task — Build step 4: the Firefighter agent, end to end in the terminal

Read `CLAUDE.md`, `docs/schema.md` and `backend/tools/registry.py` first. Steps 2–3 are done and green.

## Step 0 — housekeeping (its own commit, first)
1. In `backend/tools/registry.py` replace the placeholder tracks with the official names (also in CLAUDE.md):
   - Firefighter → "Track 1: Agents That Act on Connected Data"
   - Team memory → "Track 2: Agent Memory and Coordination"
   - Brain → "Track 3: Company Brain"

   Then re-check each tool's track list:
   - `shared_dependency_changes` and `past_incidents` also serve Track 2: they are how memory gets used.
   - `search_knowledge`, `decisions_about`, `who_to_call` and `stale_knowledge` serve Track 3.
   - The traversal and algorithm tools serve Track 1.
2. Regenerate `docs/cypher.md`.
3. Commit with `CLAUDE.md` and this prompt file: "Official track names; CLAUDE.md quirks; step 4 spec". Push.

## Goal
One agent, the **Firefighter**, takes an alert and investigates using ONLY the step-3 graph tools. It finishes by submitting a structured, **grounded** incident report: every id it cites must have come back from a tool. Every step is recorded with its receipt (Cypher plus highlight).

This is the "ugly end-to-end slice". Everything else builds on it:
- step 5 adds memory write-back, Session/Step nodes and the three-agent handoff
- later steps wrap it in an API and a UI

No graph writes in this step.

## Files
```
backend/
  llm.py                    # THE ONLY place that talks to an LLM provider
  agents/
    __init__.py
    prompts/firefighter.md  # system prompt (kept in a file so it's easy to review and tune)
    report_schema.py        # submit_report tool schema + grounding checker
    firefighter.py          # run_firefighter(...) + CLI: python -m backend.agents.firefighter
    mock_policy.py          # deterministic stand-in for the LLM (no API, no cost)
    check_run.py            # python -m backend.agents.check_run runs/<file>.json -> PASS/FAIL story assertions
tests/test_firefighter.py
runs/                       # run records (JSON). Git-ignore runs/* but keep runs/golden/ tracked (empty .gitkeep for now)
```
Add `anthropic` to requirements.txt.

## 1. `backend/llm.py` — one wrapper
- `LLMClient(mode=None, model=None)`:
  - `mode` comes from env `LLM_MODE`. **Default `mock`.**
  - `model` comes from env `LLM_MODEL`, default `claude-haiku-5-5`.
  - `ANTHROPIC_API_KEY` is read only from `.env` and the environment. Never print or log it.
- `complete(system: str, tools: list[dict], messages: list, max_tokens: int = 1024) -> LLMResponse` with:
  - `content` (list of blocks: text / tool_use, provider-neutral dicts)
  - `stop_reason`
  - `usage` (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`)
  - `cost_usd`
- Live mode uses the official `anthropic` SDK Messages API with tool use.
- **Prompt caching:** add `cache_control: {"type": "ephemeral"}` to the LAST tool definition and send `system` as one text block that also has `cache_control`. Haiku 5.5 / Sonnet 5.5 cache prompts ≥ 512 tokens; our system prompt plus tools exceed that.
- `PRICES` table, USD per million tokens:
  - `claude-haiku-5-5`: input 0.10, output 0.50, cache write 0.125, cache read 0.01
  - `claude-sonnet-5-5`: input 2.00, output 10.00, cache write 2.50, cache read 0.10

  Compute `cost_usd` per call. Unknown model → cost None plus a warning.
- **Budget guard:** the run tracks cumulative cost. If it exceeds `MAX_RUN_COST_USD` (env, default 0.05), abort the run cleanly and record why.
- Mock mode does not use the SDK. It delegates to `mock_policy.py` and returns the same `LLMResponse` shape, with zero cost.

## 2. The agent loop (`firefighter.py`)
`run_firefighter(alert: dict, ctx: ToolContext, llm: LLMClient, max_steps: int = 10) -> dict` (the run record).
- `alert` = `{"service_id": "svc:payments-api", "symptom": "5xx rate 12% and p99 4.1s on payments-api for the last 15 minutes"}`. Also accept `service_query` (free text) instead of `service_id`; the agent then uses `find_service`.
- Tools offered = all 12 registry tools (name, description, input_schema) + `submit_report`.
- Loop:
  1. call the LLM
  2. execute EVERY `tool_use` block in the response (the model may request several at once)
  3. send all results back in one user message as `tool_result` blocks: `json.dumps(result)`, or `{"error": ...}` with `is_error: true`
  4. repeat until `submit_report` is called or `max_steps` LLM calls are used. If the cap is hit, return a record with `status: "step_limit"`.
- Tool exceptions must never crash the loop. Return them as error results.
- **Grounding check** on `submit_report`:
  - collect every id-shaped string in the report (prefixes from `seed/schema.py`)
  - every one must have appeared in some earlier tool result
  - if not, return a `tool_result` error listing the ungrounded ids and ask the model to resubmit. This is allowed **once**.
  - the record keeps `grounding: {ok, ungrounded_ids}`.
- `submit_report` input schema (strict):
  - `summary`: ≤ 3 sentences
  - `likely_cause`: `{service_id, deploy_id, ticket_key, path: [service ids], explanation}`
  - `blast_radius`: [service ids]
  - `contact`: `{person_id, name, reason}`
  - `bus_factor_warning`: string or null
  - `conflicting_decision`: `{decision_id, source_id, excerpt, how_it_conflicts}` or null
  - `similar_past_incidents`: `[{incident_id, what_fixed_it, resolved_by}]`
  - `evidence`: `[{node_id, claim}]`, min 3
  - `recommended_actions`: [strings], ≤ 4. Proposals only; paging and ticketing come in step 5.
  - `confidence`: low | medium | high

### Run record
JSON saved to `runs/firefighter-<UTC timestamp>.json`.
- Top level: `run_id`, `agent: "firefighter"`, `tenant`, `alert`, `mode`, `model`, `started_at`, `status` (`ok` | `step_limit` | `budget_abort` | `error`), `report`, `grounding`, `totals` (input/output/cache tokens, `cost_usd`, `llm_calls`, `tool_calls`, `duration_ms`).
- `steps`: a list. Shape each entry like the schema's `Step` node so step 5 can persist it directly:
  - `seq`, `agent`, `action` (`tool_call` | `answer`), `tool`
  - `args`, `result` (what the LLM saw), `receipt` (cypher, params, highlight)
  - `summary` (one line, e.g. "recent_changes_downstream → 1 hit: risk-rules (deployed 40 min ago)")
  - `ts`, `ms`

## 3. System prompt (`prompts/firefighter.md`)
Write it for a small model: short, concrete, numbered. It must tell the agent:
- **Role:** on-call incident investigator for Kestrel Pay. It can only know what the graph tools return.
- **Method, in order:**
  1. Resolve the service (if needed).
  2. `recent_changes_downstream` with `since_minutes: 120`.
  3. Only if that finds nothing, `shared_dependency_changes` with `since_minutes: 120`.
  4. `blast_radius` of the alerting service.
  5. `who_to_call` for the **culprit** service, not the alerting one.
  6. `decisions_about` the culprit. Explicitly check whether the recent change contradicts a past decision.
  7. `past_incidents` for [alerting service, culprit, and any shared dependency].
  8. `submit_report`.

  Batch independent calls in one turn when possible (e.g. 5, 6 and 7 together) to save round-trips.
- **Rules:**
  - Cite ids exactly as tools return them.
  - Never invent ids, people or numbers.
  - If the maintainer has left, say so in `bus_factor_warning` and recommend the top active candidate.
  - Keep the report terse.
- Keep it under ~600 words.

## 4. Mock policy (`mock_policy.py`)
A deterministic, rule-based stand-in for the LLM. It reads the previous tool results in `messages` and emits the same sequence a good model would:
- `recent_changes_downstream`
- then (`blast_radius`, `who_to_call`(culprit), `decisions_about`(culprit), `past_incidents`) in ONE turn
- then `submit_report` built only from values found in those results

It must work for any alerting service that has a downstream culprit, not just payments-api: derive the culprit from the tool result, don't hard-code it. Purpose: free development, tests, and later a no-API "public mode".

## 5. CLI
`python -m backend.agents.firefighter --service svc:payments-api --symptom "..." [--live] [--model claude-sonnet-5-5] [--max-steps 10]`
- Default is mock. `--live` sets live mode.
- Print a readable trace:
  - each step: `[3] who_to_call {"service_id":"svc:risk-rules"} → top: Priya Nair (score 48); maintainer Arjun Mehta LEFT`
  - the Cypher, dimmed and indented, with `--show-cypher`
- Then a nicely formatted report, then totals (tokens, cache read tokens, cost in USD and ≈ INR at 84 INR/USD, duration), then the record path.

## 6. `check_run.py` — story assertions on any run record
For the payments-api scenario, each line is PASS/FAIL:
1. `likely_cause.service_id == svc:risk-rules`
2. `deploy_id == dep:risk-rules-v2.8.0`
3. `ticket_key == RISK-412`
4. path is payments-api → fraud-scoring → risk-rules
5. `contact.person_id == per:priya-nair`
6. `bus_factor_warning` mentions Arjun
7. `conflicting_decision.decision_id == dec:rules-cache-ttl` with `source_id == chat:risk-eng-config-load`
8. `similar_past_incidents` includes inc:2025-031
9. `blast_radius` includes web-checkout
10. `grounding.ok`
11. `status == ok`
12. ≤ 6 LLM calls

Exit non-zero on failure. This is how we compare Haiku vs Sonnet and catch prompt regressions.

## Tests (`tests/test_firefighter.py`) — mock only, never live
1. Mock run on payments-api passes every `check_run` assertion, with cost 0.
2. Grounding: feed a report containing `per:made-up` → ungrounded and rejected. After one failed resubmit, the record shows `grounding.ok == false`.
3. Step cap: a policy that never submits stops at `max_steps` with `status: step_limit`.
4. Budget guard: fake usage that exceeds `MAX_RUN_COST_USD` → `status: budget_abort`.
5. Request building (no network): the live request payload puts `cache_control` on the last tool and on the system block, and sets `max_tokens`.
6. A tool raising an exception becomes an error `tool_result`; the run continues.
7. Every step in the record has a receipt with ≥1 query, except `submit_report`.

## Live check (manual, once, at the end)
1. If `ANTHROPIC_API_KEY` is not in `.env`, stop and ask me to add it. Don't skip the live check silently.
2. Run once live with Haiku:
   `python -m backend.agents.firefighter --service svc:payments-api --symptom "5xx rate 12% and p99 4.1s on payments-api for the last 15 minutes" --live`
3. Run `check_run` on its record.
4. If assertions fail, improve **only the system prompt or tool descriptions**. Max 3 attempts. Log each change and result in `docs/ai-log.md`. Do not change what the tools return just to make Haiku pass.
5. Report: tokens per call, whether calls 2+ show `cache_read_input_tokens > 0`, total cost, check_run results.
6. Do NOT run Sonnet. I'll decide when.

## Done when
- `pytest -q` is green, and `python -m seed.verify --graph kestrel_pay` still passes.
- The mock CLI run prints the trace and the report.
- One live Haiku run has been made and checked.
- `.gitignore` covers `runs/*` but not `runs/golden/`.
- Finish per CLAUDE.md: ai-log, commit "Step 4: Firefighter agent (mock + live)", push.

  In the plain-language explanation, cover:
  - the agent loop
  - why `submit_report` is a tool (structured output)
  - what grounding prevents
  - how caching and the budget guard protect the ₹500
  - how mock mode lets us build the UI for free
  - what the live Haiku run cost
