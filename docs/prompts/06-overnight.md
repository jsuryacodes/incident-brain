# 06 — OVERNIGHT TASK: memory-first recall, public postmortems, Brain eval, README draft, hardening

Run with: Claude Code, Opus 5.5, effort high, unattended.
Resume line if stopped by usage limits: "Read docs/prompts/06-overnight.md and docs/progress.md and continue."

Same rules as 05: read `CLAUDE.md`, `docs/progress.md`, `docs/explain.md` first. **Zero live API calls, no key**
(mock mode only; tests block the network). No hardcoded story knowledge in agent code/prompts/rules. Schema changes only
with a version bump + changelog. Per part: tests green → update `docs/progress.md` + `docs/explain.md` + `docs/ai-log.md`
→ commit `06<letter>: <what>` → `git push origin main`. Never stop to ask; record decisions in progress.md.
NO UI work in this task.

---

## A. Setup that works on a fresh Mac (do this first; small)

Jaya hit `python: command not found` and a missing `dotenv` module. Make setup foolproof:
- `scripts/setup.sh`: creates `.venv` with `python3`, installs `requirements.txt`, checks Docker + FalkorDB on 6379,
  starts the `falkordb` container if it exists but is stopped, seeds both tenants, runs verify. Idempotent, clear messages.
- `scripts/demo.sh`: activates `.venv` and runs `python -m backend.demo story --compare-no-memory`.
- Make sure `requirements.txt` is complete and pinned (fresh venv + `pytest -q` must pass). `.venv` git-ignored.
- Add a `--quiet` flag to the demo: prints only the session headers, the handoffs, and the final before/after box
  (the default verbose output stays for debugging).

## B. Memory-first recall (make Session 2 feel instant)

Today Session 2 finds the cause in 6 LLM / 12 tool calls vs 7 / 13 in Session 1. Memory should show up in step 1–2.
- New read tool `memory_recall(service_id)`: for the alert service and its downstream deps (DEPENDS_ON*1..3, declared
  or learned) return: learned DEPENDS_ON edges on those paths (with their Fact + SOURCED_FROM excerpt + session),
  agent-written Facts ABOUT those services, resolved Incidents that AFFECTED any of them (with Resolution, PERFORMED_BY,
  root cause), and the latest Runbook (via SUPERSEDES) for each. Small result + receipt, like the other tools.
- Firefighter + Investigator (RulePlanner AND the live prompts): call `memory_recall` first. If it returns a learned
  dependency or a matching resolved incident, form a hypothesis immediately and VERIFY it with the cheapest tools
  (recent deploys on the hypothesised service via shared_dependency_changes / dependency_path), then confirm.
  If nothing is recalled, behave exactly as today.
- Target: Session 2 names the culprit deploy within its first 3 tool calls and says "Seen before: <incident key>,
  fixed by <person> (<resolution summary>), see Runbook v<n> step <k>" — all from tool results, grounded.
- Session 1 behaviour and results must not change (it has no memory to recall). `--compare-no-memory` must still
  report the cause as unknown.
- Demo before/after box: add "tool calls until cause found" for Session 1, Session 2, and Session 2 without memory.
- Regenerate golden runs (`runs/golden/*`), `docs/cypher.md`, MCP tool list (now 15 read tools), tests.

## C. Public postmortems layer (build step 9; bounded)

- Collect ~20 REAL, publicly available incident postmortems from tech companies (official company engineering blogs /
  status pages preferred). Favour ones whose root causes overlap our patterns: cache / config stampede (thundering herd),
  config push gone wrong, hidden or undeclared dependency, retry storm, DNS/BGP, certificate expiry, database failover.
- For each, store ONLY: company, title, our OWN summary (≤ 60 words, written in your own words, no copied sentences),
  url, published_at, and 1–2 root-cause tags. No long quotes. If you can't verify a postmortem's facts from its page,
  skip it. Be factually careful about real companies.
- Data in `seed/data/public_postmortems.json`; loaded into EVERY tenant graph as `PublicPostmortem` nodes
  `HAS_ROOT_CAUSE` → `RootCause` (reuse existing RootCause ids where they fit; add generic new ones in the seed).
  Verify checks for both tenants.
- New read tool `industry_matches(root_cause_id | incident_id)`: public postmortems sharing a root cause, with url.
- On `resolve_incident`, also write `SIMILAR_TO {score, reason}` from the incident to the best 1–2 matching public
  postmortems. Communicator / Firefighter report gains "Matches known industry pattern: <company> — <title> (<url>)".
- `docs/postmortems.md`: table of all entries (company, title, link, our summary, tags) + a note that summaries are ours.

## D. Ask the Brain eval: 5 → 15 questions

- Extend the golden set to ~15 per tenant-agnostic intent: who knows/owns X, who to call (after someone left), why did
  we decide X (with exact quote), onboarding for a team, what is stale, what breaks if X fails, seen this before,
  what did session N learn, industry pattern for root cause Y, follow-up pronoun ("who should I call about it?"),
  multi-user isolation, restart persistence, a question with no answer (must say "I don't know" honestly).
- Add 3 Northwind questions. Fix the router/templates for any failures. Report pass rate in progress.md.

## E. README draft (submission requirement; draft, not final)

`README.md` with: one-paragraph pitch; 3-minute quickstart (`scripts/setup.sh`, `scripts/demo.sh`); architecture
(Mermaid: FalkorDB ↔ tools registry ↔ agent loop (RulePlanner | LLMPlanner) ↔ CLI / FastAPI / MCP); graph data model
(embed or link the schema Mermaid diagrams); the Cypher queries + algorithms the product depends on (link
`docs/cypher.md` + a short table naming algo.SPpaths, algo.pageRank, algo.betweenness, full-text indexes);
"How memory works" (learned edge story, with before/after numbers); one section per track mapping features to that
track's focus bullets (Track 1 Agents That Act on Connected Data, Track 2 Agent Memory and Coordination, Track 3
Company Brain); modes (mock vs live, how cost is capped, `docs/live-mode.md`); MCP usage; tenant isolation;
AI-assistant disclosure section (link `docs/ai-log.md`); `TODO:` placeholders for demo video link, live URL, screenshots.
Plain, honest wording. No claims about live LLM behaviour (not tested yet).

## F. Hardening pass (last)

- Spawn ONE independent reviewer subagent (it has not seen the work) to check: story knowledge leaking into agent
  code/prompts/rules (grep for Kestrel/Northwind ids, names, versions, ticket keys), parameterised Cypher everywhere,
  grounding check coverage, write-tool validation, tenant param plumbing (CLI/API/MCP), secrets/`.env` hygiene,
  dead code, flaky tests (run `pytest -q` 3×). Fix what it finds; list anything not fixed in progress.md.
- Re-run on a FRESH reseed: both tenants verify, full test suite, `scripts/demo.sh`. Paste the final before/after box
  into progress.md.

## If time or usage runs short

Finish parts in order A → B → D → E → C → F; never leave a part half-committed. B and E matter most.

## Definition of done

All tests green 3× in a fresh venv; Session 2 finds the cause within 3 tool calls via memory recall; ~20 public
postmortems loaded in both tenants with our own summaries; Brain eval ≥ 14/15; README draft complete except TODOs;
progress.md updated with the final before/after box and a short "what to look at first in the morning" list; pushed.
