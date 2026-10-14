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
