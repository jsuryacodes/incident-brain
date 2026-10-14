# Demo & recording checklist

Grows as we build. Run top to bottom before recording the demo video or showing judges.

## Before every recording / live demo
- [ ] Docker Desktop open, `docker start falkordb`.
- [ ] **Re-seed:** `python -m seed.load --graph kestrel_pay --reset`, then `python -m seed.verify --graph kestrel_pay` → 14/14 PASS.
      All seed times are relative to load time ("risk-rules deployed 40 min ago"). Check 5 and 10 use a 2-hour window, so start recording within ~1 hour of seeding.
- [ ] Confirm no leftover agent memory from rehearsals: `MATCH (n {origin:'agent'}) RETURN count(n)` → 0 (the reset handles this).
- [ ] Product agents use `claude-sonnet-5-5` for the recording (Haiku during dev).
- [ ] Also re-seed the second tenant: `python -m seed.load --graph northwind_health --reset`, then `python -m seed.verify --graph northwind_health` → 8/8 PASS. `TENANTS` must include it (default `kestrel_pay,northwind_health`).

## The storyline in one command (added in M2–M6)
- [ ] Dry run, free: `python -m backend.demo story` (re-seeds both tenants, S1 → resolve → `session2` scenario → S2 → summary → switch tenant). Expect: S2's Investigator calls `memory_recall` first and names `dep:risk-rules-v2.8.1` on its 3rd tool call (S1: 8th), finding `svc:risk-rules` **only via the learned edge**; Northwind shows 0 agent nodes and the Brain says "I don't know".
- [ ] One command for the whole before/after: `scripts/demo.sh --quiet` (= `story --compare-no-memory --quiet`): runs S2 on a fresh seed first (cause unknown, confidence low), then the full story, and prints the three-column box.
- [ ] **Session 2 needs the world event first.** If driving the steps by hand: `python -m seed.scenario session2 --graph kestrel_pay` right before the payouts-service run (it adds `dep:risk-rules-v2.8.1` at now − 5 min). The story command does this for you.
- [ ] Resolve wording used by the demo: `--by per:priya-nair --summary "Priya rolled back RULES_CACHE_TTL to 300s; config-service load recovered"`.
- [ ] Show the memory in the Browser (graph `kestrel_pay`): `MATCH (n {origin:'agent'})-[r]-(m) RETURN n,r,m`; the learned edge alone: `MATCH (a)-[r:DEPENDS_ON {source:'learned'}]->(b) RETURN a,r,b`.
- [ ] Ask the Brain: `python -m backend.agents.brain_eval` → 15/15 (`--tenant northwind_health` → 3/3). Follow-ups use `--session ses:...` (works across restarts).
- [ ] Live/recording run: needs `ANTHROPIC_API_KEY` in `.env`. Check spend first; `MAX_RUN_COST_USD` (default 0.05) aborts a run that gets expensive. `python -m backend.demo story --live --model claude-sonnet-5-5` only for the recording.
- [ ] API: `uvicorn backend.api.main:app`. If the live model misbehaves on stage, fall back to `POST /api/replay/team-session1.json` (recorded, no LLM). Regenerate golden runs after any agent change: `python -m backend.demo story --quiet --save-golden`.
- [ ] MCP (Track 1): see `docs/mcp.md`; `claude mcp list` shows `incident-brain` connected.
