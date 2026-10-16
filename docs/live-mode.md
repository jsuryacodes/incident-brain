# Mock mode vs live mode

**Status (15 Oct 2026): live mode is built but has never been run.** Every number in this repo comes from mock mode.
Expect one round of prompt tuning on the first live run.

## Mock mode (default, free)
`LLM_MODE=mock` (the default in `.env.example`). `backend/llm.py` never touches the Anthropic SDK; it asks
`backend/agents/mock_policy.py` for the next turn. The mock is a rule-based "fake model": it reads the tool results in
the conversation and picks the next tool calls and the final report from them. It sees the same tools, runs through
the same loop, and passes the same grounding and validation checks as the live model. Tests always run in mock mode
and block the network (`tests/conftest.py`).

## Live mode
`--live` on the CLIs (`backend.agents.firefighter`, `backend.agents.team`, `backend.agents.brain`, `backend.demo`,
`backend.agents.brain_eval`), or `live: true` on the API. Needs `ANTHROPIC_API_KEY` in `.env` (never committed).
Default model `claude-haiku-5-5` (`LLM_MODEL`); `claude-sonnet-5-5` only for the demo recording (`--model`).

## How cost is capped (layered)
1. **One wrapper.** `backend/llm.py` is the only code that calls the API. Every request sets `max_tokens`
   (1024 per agent turn).
2. **Prompt caching** on the system prompt and the last tool definition, so repeated turns read the long prefix
   from cache.
3. **Per-run budget guard.** The agent loop adds up `cost_usd` per call (price table in `llm.py`) and aborts the run
   with `status: budget_abort` once it passes `MAX_RUN_COST_USD` (default $0.05).
4. **Step limits.** Each agent has a maximum number of LLM turns (8–10); the loop stops there.
5. **API gate** (`backend/api/guard.py`). The server runs live only if the request has `live: true`, the
   `X-Access-Code` header matches `ACCESS_CODE` (constant-time compare), the server has a key, and today's
   `DAILY_LIVE_RUNS` cap (a Redis counter with a TTL) has room. Otherwise it runs mock and says why; over the cap it
   returns 429. Plus a per-IP rate limit (`RATE_LIMIT_PER_MIN`).
6. **Budget for the hackathon:** about ₹500 in total. Rough plan: the first live check ≈ 50 Haiku calls.

## First live run (when a key is added)
```bash
python -m backend.agents.firefighter --service svc:payments-api --symptom "5xx rate 12% and p99 4.1s on payments-api for the last 15 minutes" --live
python -m backend.agents.check_run runs/<that file>.json
python -m backend.demo story --live            # ≈ 30 Haiku calls
python -m backend.agents.brain_eval --live     # ≈ 55 Haiku calls; the restart case runs in-process when live
```


## 08: one-command live validation (not run yet)
**Nothing in 08 called the API.** Everything new (the Firefighter's leads/hypotheses/action plan, alert storms,
`why` lines, MCP mode) runs in mock mode, and the live paths are tested only with fake clients
(`tests/test_hypotheses.py::test_live_path_parses_why_lines`, `tests/test_firefighter.py::test_5_*`).

When a key is in `.env`: `scripts/live-check.sh` (Haiku by default):
1. the Firefighter on the hero alert, then `check_run` on its record;
2. the same with `--tools-via mcp` (tool list + calls over MCP);
3. the alert storm (`python -m backend.demo storm --live`);
4. the scenario library + held-out set, full profile (`firefighter_eval --live`, results printed, docs not overwritten).

**Estimated cost (Haiku 5.5 at $0.10 / $0.50 per M tokens in/out, prompt caching on):** a single-alert run is ~5 LLM
calls × ~8k input tokens (22 tool schemas + the conversation) + ~600 output tokens each ≈ **$0.006**; a storm ~6 calls
× ~12k ≈ **$0.01**; the 21 eval scenarios ≈ **$0.13**. **Total ≈ $0.15 (~₹13).** Sonnet would be ~20× that.
The per-run guard (`MAX_RUN_COST_USD`, $0.05) stops any run that goes over.

What the live prompts now ask for (so a model produces what the UI shows): `why <tool>: <reason>` lines before tool
calls (every prompt), and in the Firefighter's report `rejected_leads`, `look_first`, `incidents` (+ `root`,
`suppressed_pages`, `notify`), `hypotheses`, `confidence_breakdown`; the Investigator's handoff carries `hypotheses`.
Expect one round of prompt tuning: the mock planner's rules are spelled out in `prompts/firefighter.md`, but a model
will word things differently, and the eval's scorer is strict about ids and rollback/page phrasing.
