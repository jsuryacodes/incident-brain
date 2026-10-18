# Progress

**Current task: `docs/prompts/08-track1.md`** (Track 1 all-in: scenario eval, hypotheses, alert storm, actions, MCP, scale, UI, docs; unattended, mock only, zero live API calls).
Resume line: "Read docs/prompts/08-track1.md and docs/progress.md and continue."

## Revert map (08)
Tag `pre-08` = the state before any 08 code (`git checkout pre-08` to see it; `git revert <hash>` undoes one piece).

| Commit | Part | What it changed | Safe to revert alone? |
|---|---|---|---|
| e1f9787 | spec | `docs/prompts/08-track1.md` | yes |
| 41f066f | 08-0 | preflight baseline in progress.md, .scratch/ ignored | yes |
| f7e13a9 | 08A1 | eval scenario library (12 fixtures on twin graphs), load(transform=), independent oracle test | no: A2–A8 build on it |
| 06afb91 | 08A2 | recent_changes tool, self-change hits, critical_services(downstream_of), no-algorithms mode, verified tool output in cypher.md, FalkorDB crash workaround | no: A3 uses recent_changes |
| 0a76b14 | 08A3 | generalised Firefighter planner (leads judged by the graph, multi-alert, team escalation, look_first, tool-aware), shared_callers | no: the eval and C/D build on the planner |
| b61b93e | 08A4 | eval oracle module (plain Python ground truth) + seeded scenario generator (50 random scenarios) | no: A5 imports the generator |
| efed1e1 | 08A5 | Firefighter eval runner (twins, per-profile scoring, per-incident actions), runs/eval/latest.json, docs/eval.md, GET /api/eval/latest | yes (removes the eval runner + /api/eval/latest; the Eval view then shows 'no results') |
| 366a1fa | 08A6 | eval baseline 'graph, no algorithms' (plain-Cypher paths and fan_in count), deterministic search tie-break, honest eval wording | yes (the no-algo column disappears) |
| ccca66b | 08A7 | eval baseline 'no graph' (full-text + catalog + flat change log), deterministic full-text order | yes (the no-graph column disappears) |
| 85a12a7 | 08A8 | held-out eval set (run once: 6/6), now a permanent eval set; Part A done | yes (held-out set leaves the eval) |
| e98d9b0 | 08C1 | storm tools (correlate_alerts, connected_impact, blast_tiers, failure_domains) verified against FalkorDB | no: C2/C3, D and the UI use the storm tools |
| 111070c | 08C2 | storm correlation in the Firefighter planner (one incident per shared root, suppressed pages), storm eval scenarios | needs also 08C3, 08G1/G2 (storm UI) |
| 83d30dd | 08C3 | alert-storm story beat (golden replay, fresh run, /api/storm/latest numbers) | yes (storm beat + /api/storm/latest go) |
| b838983 | 08B1 | hypotheses + confidence breakdown in reports, why-this-tool on every step (mock, prompts, live parser), Step.why / Step.hypotheses_json (schema v1.3) | needs also 08B2 (replays carry why/hypotheses; harmless if kept) |
| 2ce2001 | 08B2 | regenerate golden replays (steps now carry why; Investigator handoff carries its hypothesis board) | yes (replays fall back to the pre-08B recordings) |
| c0205c1 | 08D1 | rollback_safety tool and the Firefighter action plan (justified actions, risky rollback -> hold) | needs also 08D2, 08G1/G2 |
| 90f4f60 | 08D2 | approval-gated simulated execution on twins (idempotent), verification re-check, POST /api/actions/execute, storm replay with execution | needs also 08G1/G2 (Approve button) |
| ae654d9 | 08G1 | Firefighter playground backend (scenario list, fresh runs on a kept twin, 15 recordings with approved execution) | needs also 08G2 |
| 1911520 | 08G2 | UI: Firefighter view (why, hypotheses, actions + approve + verification), Eval view (why a graph), story hooks; Playwright 18/18 + screenshots | yes (UI only) |
| a4f9b12 | 08E | MCP for real: tools via MCP for our agents (parity test), streamable HTTP /mcp/<tenant>/, prompts + resources, structured receipts, scripted transcript | yes (MCP extras; --tools-via mcp, HTTP mount, prompts go) but 08J3 uses it in the playground: revert 08J3 too |
| 2904cb4 | 08E fix | MCP parity test compares the Cypher, not the clock-based since parameter | yes |
| a016203 | 08F | scale proof: generated 2,000-service company, query times in receipts, benchmarks (docs + API + Eval panel) | yes (scale tenant, benchmarks, ms in receipts) |
| ad939a2 | 08H | live-readiness: scripts/live-check.sh (one command, est. ~$0.15 on Haiku), firefighter_eval --live, live-mode.md | yes |
| ad66567 | 08I | README Track 1 first (five focus areas ticked, three-profile table), demo script v2 (2:45), explain.md Track 1 + judge Q&A, blog draft | yes (docs only) |
| 1ef84b5 | 08J1 | container includes the eval/benchmark results and the docs the MCP resources serve | yes |
| 6716dd0 | 08J2 | review fixes: approve only the twin's own run, additive graph-derived approvals, busy lock, honest verification, graph-based safety reasons, projection cap, per-incident confidence | yes (re-opens the review findings) |
| 8d21315 | 08J3 | MCP visible in the playground (tools selected through an MCP session, labelled mock planner), re-recorded replays, re-shot screenshots | yes (playground back to direct tools) |

## 08 status
| Part | Status | Commits |
|---|---|---|
| 0 Preflight | DONE | (no code) |
| A Scenario library + eval + baselines | DONE | 08A1–08A8 |
| B Hypotheses + decision trace | DONE (backend; UI in G) | 08B1–08B2 |
| C Alert storm | DONE (backend; UI in G) | 08C1–08C3 |
| D Actions + safety check + approval | DONE (backend; UI in G) | 08D1–08D2 |
| E MCP for real | DONE | 08E |
| F Scale proof | DONE | 08F |
| G UI | DONE (benchmark panel comes with F) | 08G1–08G2 |
| H Live-readiness | DONE (no calls) | 08H |
| I Docs | DONE | 08I |
| J Review + final verification | DONE | 08J1–08J3 |

**Total live API spend in 08: $0.00** (0 live calls, no key). **All parts DONE.** The morning list is at the end of this file.

## 08-0 — Preflight (baseline before any 08 code)
- Docker up, `falkordb` container running (`falkordb/falkordb:latest`); `scripts/setup.sh` clean: kestrel_pay **14/14**, northwind_health **8/8** on a fresh seed.
- `pytest -q` **118 passed** (9 s) · `npm test` (vitest) **17 passed** · `scripts/e2e.sh` Playwright **10/10** (49 s).
- Brain eval **15/15** (kestrel_pay, after the story) + **3/3** (northwind_health).
- Machine: macOS (Darwin 25.4), Python 3.15.0 in `.venv`, Node 22.
- Tag `pre-08` pushed. `.scratch/` added to `.gitignore`.

## 08A — Scenario library + Firefighter eval + baselines
**Design pass (3 proposals: two Plan agents + mine), decision:**
- Fixtures live in `seed/eval_scenarios.py` and are applied through a new `seed.load.load(transform=...)` hook on the seed's own node/edge lists, so every fixture goes through the same validator and writer as the seed (proposal 1). Twins `<tenant>__eval_<id>` are fresh seeds, never copies of the hero graphs (whose story memory would leak in).
- Ground truth is hand-written but re-derived by an **independent oracle** (plain Python BFS / PageRank / the who-to-call formula over the fixture lists, no Cypher, no agent tools) in `tests/test_eval_scenarios.py` (proposal 2: avoid circular truth).
- Overfitting guard (proposal 2): a **held-out set of 6 scenarios** written by an agent that never saw the planner code; only its hash is recorded now and it runs once at the end of Part A. **sha256 `57264681bd26cedd7fb4f0b7a8ec52a5adb48adc1db9d34016be2ddb666dbc73`** (`.scratch/holdout/eval_holdout.py`, not opened by me). Plus a seeded random scenario generator.
- Tools: a flat tenant-wide change log `recent_changes` (both proposals), a change to the alerting service itself counts (proposal 2 found the `*1..` gap), team escalation when nobody active owns the culprit (proposal 2 found `owning_team_fallback` unused), `critical_services(downstream_of=...)` (proposal 1).
- Planner rule from proposal 2: in a company where everything calls the same hubs, a noisy-neighbour hit is a cause only when corroborated (a learned edge on the path, the shared service is alerting, or the alert names it).
- "Nothing changed" is never reported as a cause: `look_first` (top PageRank on the call path) is a separate field (proposal 2). PageRank can't separate config-service from config-db (within 1%), so `look_first` expectations list both.
- Multi-alert in A: per-alert candidates + "the change explaining the most alerts wins" (traversal only). Part C adds the algorithm tools; the eval measures what they add instead of assuming it.
- Baselines (both proposals): no-graph = full-text + the flat change log (without the log it could not name any deploy; documented as a deviation from "only full-text"); no-algo = every tool except the algo.* ones, and `ToolContext.algorithms=False` makes shortest paths plain Cypher (the eval checks no `algo.` query ran).

**08A1** (fixtures + oracle): 12 dev scenarios (8 Kestrel incl. the hero Session 2 and its ablation, 4 Northwind); verifier PASS, its findings applied (neighbour-lead and "not found" checks in the oracle, unique shortest paths, path edges on neighbour paths, verbatim quotes, "why" wording, twin-name test).

**08A2** (tools): `recent_changes` (flat change log), a change to the alerting service itself now counts in
`recent_changes_downstream` (hops 0), `critical_services(downstream_of=...)`, `ToolContext.algorithms=False` (plain-Cypher
shortest paths, `critical_services` refuses), docs/cypher.md now pastes each tool's real output from the running DB.
Verifier PASS; applied: deterministic tie-break in the plain-Cypher shortest path, same 365-day cap everywhere.
**FalkorDB bug found:** FalkorDB 6.0.2 (graph module 60002) **crashes the whole server** (`panicked at src/reply.rs:655`,
`reply_compact`, `Option::unwrap()` on `None`) on `recent_changes_downstream`'s aggregation when the row had ~11 columns
and the optional ticket was NULL (a deploy without a ticket, first hit in an eval fixture). Minimal repro in
`.scratch/crashprobe*.py`. Workaround: few grouping columns + the details as one list column. Regression test
`test_24_downstream_hit_without_a_ticket` plus a sweep running every service tool on every service (`test_25`).
Worth reporting upstream to FalkorDB (decision for Jaya: it's a nice "we found a bug" story for the judges, but check
the latest image first).

**08A3** (planner): `backend/agents/ff_policy.py` is the Firefighter's mock planner (the old one in mock_policy.py is
gone; the team personas are untouched). Every recent change is a lead; the graph confirms or rejects each one, with the
reason. Multi-alert input; team escalation when nobody active owns the culprit; `look_first` when nothing changed;
tool-aware degradation for the baselines. **Four verifier rounds** (FAIL, FAIL, FAIL, FAIL→fixed): they found false
rejection reasons, a hub rule that never measured the hub, claims about scans that never ran, ungrounded runs with sparse
tool sets, a caller looping through the alert treated as a neighbour, invented contact numbers in text mode. All fixed,
each with a test; `test_16` sweeps every scenario × 7 tool subsets and must stay grounded (the last verifier also ran
1,620 alert × deploy pairs + 90 random multi-alert runs: no false cause, no crash).
Decisions: a neighbour (shares a dependency) counts when the narrowest shared service is reached by fewer than 4
services, or when corroborated (learned edge on the path, the shared service is alerting, or the alert names it).
Known behaviour (judgement call, left as is): a CALLER of the alerting service that shares a narrow dependency through
another route counts as a neighbour (e.g. Northwind patient-portal for an appointments alert).
Hero numbers re-checked on a twin: unchanged (S1 14 total / 8 investigator, S2 9 / 3, without memory not found).

**08A4** (oracle + generator): `seed/eval_oracle.py` (ground truth in plain Python, shared by the oracle test and the
generator) and `seed/eval_generator.py` (50 seeded random scenarios: random alert, culprit 1-4 hops down with a unique
shortest path and an untied contact, an unrelated decoy deploy in 40 of 50, often fresher than the culprit).
**08A5** (runner): `python -m backend.agents.firefighter_eval` (dev + generated sets, per profile, twins deleted even on
errors), `runs/eval/latest.json`, `docs/eval.md`, `GET /api/eval/latest`. Verifier FAIL → fixed: the scorer now fails a
report that names a cause and also rejects it, catches any "roll back / revert / undo dep:…" and every `per:` id in
actions, scores actions per incident, requires a non-empty reason for each rejected lead; doc overclaims removed.
Full profile: **dev 12/12, generated 50/50**.

**08A6** (baseline "graph, no algorithms", `backend/agents/baseline_noalgo.py`): every tool except the algo.* ones;
shortest paths become plain Cypher; `critical_services` keeps only a plain `fan_in` count (services that reach each one)
as its stand-in for PageRank. Verifier findings applied: search results now have a deterministic tie-break (the
no-graph numbers wobbled between runs), the n-chokepoint label no longer claims betweenness decides it, the ablation
cell reads "no cause: right", eval.md lists (from the data) the scenarios where algorithms changed the outcome.
**Honest result: on single alerts it ties the full profile (dev 12/12, generated 50/50).** The plain traversals are
what finds causes; the algorithm calls there only draw paths. The algorithms have to earn their place in Part C.

**08A7** (baseline "no graph", `backend/agents/baseline_text.py`): full-text search (titles + snippets), the service
catalog (`find_service`, now also returns the owning team id) and the flat change log. It picks the change whose words
best match the alert and its search hits, pages whoever shipped it, or escalates to the owning team when nobody active
did. Verifier findings applied: it uses snippets, escalates to the team, `read_source` (never needed) dropped from its
list, results are now deterministic (the full-text query's LIMIT cut among tied scores in server order; `ORDER BY
score DESC, node.id`; three identical runs). Brain eval still 15/15 + 3/3.
**Honest result: dev 0/12 (it can never give a dependency path), causes right 10/13, false leads rejected 4/7, right
person 4/13, 11 wrong actions; generated: causes right 38/50, 50 wrong actions.**

**08A8** (held-out set): run ONCE against the finished Part A planner, hash checked first
(`57264681…dbc73`, matches): **full 6/6, no-algorithms 6/6, no-graph 0/6** (no-graph can't give paths). Now committed as
`seed/eval_holdout.py` and part of every eval run; its oracle checks run in pytest. Caveat written into the file: its
author's brief listed the shapes to cover, including one of the planner's corroboration rules.

**Part A result** (`docs/eval.md`): full and no-algorithms both pass dev 12/12, generated 50/50, held-out 6/6; no-graph
passes nothing (no paths) but gets 10/13 dev causes and 38/50 generated causes right, takes the bait on false leads
(4/7 rejected) and recommends 11 + 50 wrong actions. The graph (traversals) is what finds and defends the cause; on
single alerts the algorithms add nothing measurable, which docs/eval.md states from the data.

**Part A flake check:** pytest 161 passed ×3, Playwright 10/10 ×3 (on the Part A head).

**Usage note (Jaya, mid-run):** "my usage is getting burnt like crazy … reduce testing, focus more on building". From
here on: no design-pass or per-commit verifier agents, no 3× flake runs, tests once per part, one small final review.
This overrides QUALITY MODE in the spec.

## 08C — Alert storm
**Design** (two proposals, merged): storms run as a read-only Firefighter run (the team is single-alert; teaching it N
incidents would risk Sessions 1/2), on a fresh twin with a fixture from the scenario library, never on the hero graph
(Session 1's learned edge would change the answer). The root of the storm is pure saturation (no deploy), so "the change
that explains most alerts" finds nothing and only correlation over the graph points at it.
- `backend/tools/storm_tools.py`: `correlate_alerts` (algo.BFS reach per alert + algo.SPpaths paths; coverage, alerting
  first, total hops), `connected_impact` (algo.WCC on a scratch projection graph `<tenant>__proj_<hex>`: the alerting
  services + their downstream closure; deleted at once; the tenant graph is only read), `blast_tiers` (algo.SSpaths
  incoming: callers per tier, alerting vs silent), `failure_domains` (algo.labelPropagation, context only).
  All verified against the running DB (docs/cypher.md pastes their real output).
- Planner: for 3+ alerts, the top correlated root opens ONE incident when it explains more alerts than any single change
  (a lone change on one alert's path becomes a rejected lead); one page to the root's owner, every other page
  suppressed with its path as the reason, silent callers listed to notify.
- Scenarios: `k-storm` (5 config-service callers + an unrelated card-processor-adapter with its own change; email-sender
  change on 2 alerts' paths rejected), `k-storm-hub` (an unrelated alert that shares only kafka-events), `n-storm`.
  Eval: **full 15/15; no-algorithms 12/15 (fails the 3 storms: it has no correlation tool, so it pages per alert)**.
  eval.md says plainly that a Cypher version of correlate_alerts would likely match at 27 services; the algorithms'
  case at scale is Part F.
- Story beat (backend): `STORM_BEAT` in `backend/demo.py` (+ `python -m backend.demo storm [--save-golden]`), golden
  replay `runs/golden/firefighter-storm.json`, fresh run via `/api/story/storm/run` (access code), numbers
  `GET /api/storm/latest`: naive 6 incidents / 6 pages / 5 people woken vs agent 2 / 2 / 2, 5 pages suppressed, 35 tool
  calls, algorithms BFS, SPpaths, SSpaths, WCC, labelPropagation.

## 08B — Hypotheses and the decision trace
- **"Why this tool"**: every assistant turn starts with `why <tool>: <reason>` lines (the mock writes them, every prompt
  asks a live model for them); the loop attaches each to its step (`step.why`), the UI event carries it, and team runs
  persist it as `Step.why`. A fake-client test proves the live path parses them (no network).
- **Hypothesis board**: the Firefighter report has `hypotheses` (every lead + the alternatives when nothing changed:
  claim, status confirmed/rejected/open, supporting and contradicting evidence as node ids + claims, reason) and
  `confidence_breakdown` (+/- factors). The team Investigator calls `recent_changes` in the same turn as
  `update_incident` (so tool calls until cause stay 8 and 3) and hands off its own board, persisted as
  `Step.hypotheses_json`. Schema **v1.3** (two optional Step properties; changelog in docs/schema.md).
- Hero numbers re-checked: unchanged (S1 14 total / 8 investigator, S2 9 / 3, LLM calls 12 / 11 / 10, no-memory not found).

## 08D — Decide and act
- `rollback_safety(deploy_id)` (read tool): later deploys to the same service (a rollback takes them along), words that
  mean the change touched data (migration, schema, drop, rebuild, delete, backfill, truncate, reindex), and how many
  services depend on the changed one. Verdict safe/risky; risky turns "Roll back" into "Hold the rollback … page the
  owner first" (e.g. n-falselead's "Rebuild the visit table" on records-db).
- The Firefighter report has an `action_plan`: rollback/hold, page or escalate, suppress_page (storms), notify (silent
  callers), open_ticket, flag_stale; each with its justification (why, node ids, path) and the safety result.
- `backend/agents/actions.py`: approval executes on the run's own twin graph only (refuses hero graphs), simulated,
  existing labels, origin 'agent' (Incident, pages, ticket, stale flags, a rollback Deploy that CHANGED the service, one
  Step per action as 'communicator' in a Session 'firefighter' whose id is derived from the run: approving twice does
  nothing). Then `verify()` re-runs `recent_changes_downstream`: cleared only if the newest change on the culprit is
  now the rollback; for a storm root it says plainly that a page can't clear a saturation signal.
- `POST /api/actions/execute` (access code; fresh runs only; recordings are replays). The storm recording now includes
  an approved execution + verification for visitors.

## 08G — UI
- **Firefighter view** (`/firefighter`): the scenario library of the current company (recordings for visitors, fresh
  mock runs with the access code, or your own alert), the graph growing step by step with every alerting service red
  and a storm's shared root ringed and labelled, a step list with "why: …" on every card, and a drawer with Receipt
  (+ why this tool), Hypotheses (board + confidence breakdown), Actions (plan, justification, safety check, Approve
  (simulated, code-gated, fresh runs only), verification) and Report (incidents, suppressed pages, ruled-out changes).
  Each recording (`runs/golden/ff-<scenario>.json`, `python -m backend.agents.playground --record`) includes an
  approved execution + verification. API: `GET /api/playground`, `POST /api/firefighter/run` (code).
- **Eval view** (`/eval`): "Why a graph?" bars (causes, false leads, right person, wrong actions per profile), the
  scoreboard per set, per-scenario table linking to the Firefighter.
- **Story view**: "Alert storm" and "Why a graph?" buttons (the storm's scenario id comes from the API), "why:" on step
  cards, a Hypotheses tab in the receipt drawer (the Investigator's board).
- Playwright: new `07-firefighter.spec.ts` (storm collapse, hypotheses, risky hold, eval + story buttons, fresh run +
  approve + verification with the code, screenshots both themes + `ff-storm-1920.png`). **18/18 passed.** Looked at the
  storm hero, hypotheses and safety screenshots; fixed: end-of-run camera framing, chip wrapping, duplicated reasons,
  step list following the current step, a missing why, a truncated result line.

## 08E — MCP for real
- `--tools-via mcp`: the Firefighter's tool list and every call go through an MCP client session to our server
  (`backend/agents/mcp_tools.py`, an anyio blocking portal around `mcp.Client`); parity test vs direct.
- Streamable HTTP mounted in the API at `/mcp/<tenant>/` (one read-only server per company, stateless JSON, rate-limited,
  Host/Origin checks), stdio unchanged. Results also travel as structuredContent `{result, receipt}`.
- Prompts `investigate_alert`, `alert_storm`; resources `incident-brain://schema`, `incident-brain://tools`.
- `docs/mcp-transcript.md` from a scripted client against the real HTTP endpoint; `docs/mcp.md` updated.

## 08F — Scale proof
- `seed/data/scale_demo`: a deterministic generated company (2,000 services in 6 layers, 9,375 DEPENDS_ON with
  preferential attachment so hubs form, 40 teams, 320 people, 2,000 deploys); loads in ~2 s; seeded by setup.sh;
  added to the default `TENANTS` (also in `.env.example` and your local `.env`). The UI's company switcher, Explorer
  (capped at 400 nodes) and the Firefighter's "your own alert" work on it.
- Every receipt now carries per-query `ms` and a total.
- `python -m backend.tools.benchmark` → `docs/benchmarks.md` + `runs/eval/benchmarks.json` (+ `GET /api/benchmarks`,
  a panel in the Eval view). **Result:** everything stays far under the 1 s timeout at 2,000 services; the slowest tools
  are the path-enumerating ones (~140–165 ms); whole-graph algorithms take ≤ 7 ms; **algo.BFS vs variable-length
  Cypher reachability is a tie at this size** (written down as such; eval.md's earlier "speed at scale" sentence was
  corrected).

## 08J — Independent review + final verification
**Fresh clone** (`.scratch/fresh`, `scripts/setup.sh` from scratch): kestrel_pay 14/14, northwind_health 8/8, scale_demo
seeded; pytest **188 passed**; firefighter_eval full 15/15 · 50/50 · 6/6; Brain eval 15/15 + 3/3; vitest 17; Playwright
**18/18**; `docker build` OK (08J1 then put the eval/benchmark JSON and the docs MCP serves into the image).

**One independent reviewer + judge pass** (lean, instead of 5 judges; see the usage note). No gate bypass, no tenant
isolation breach, schema rule kept, no story leaks in agent code/prompts/frontend. Its findings and what was done:
1. An old run could be approved after a newer run replaced its copy of the company → fixed: only the run that owns the
   twin can be approved (409 otherwise); 2. partial approval worked once → approvals now add up, derived from the graph
   (each executed Step is tagged with its action id), an empty choice is refused; 3. approval didn't take the
   per-company lock → it does; 4. verification overclaimed ("signal should clear") → it now says what the graph shows
   ("rollback in place … whether the alert clears would show in real metrics") and catches a missing deploy;
   5. the HOLD verdict came only from text → `rollback_safety` now also checks a graph fact (callers that shipped after
   the change and may rely on it) and labels every reason "graph:" or "deploy summary:"; 6. anonymous MCP callers
   could make large scratch projections → capped at 3,000 services; 7. stale/clipped screenshots → re-shot, root label
   no longer clipped, scenario list shrinks once a run starts; 8. confidence breakdown per incident; 10. expired stream
   tokens are cleaned on the Firefighter endpoint. Not changed: CLI/doc tooling uses story ids as examples (allowed: it
   is not agent code).
**Judge scores (one reviewer, before the fixes):** multi-hop 8 · algorithms as tools 8 · tool selection through MCP 6
· actions 7 · explainable 9 · wow 7 · graph drives decisions 8. Weakest: MCP not visible in the UI (fixed: the
playground now selects every tool through an MCP session and the caption says so, honestly labelled "mock planner
(scripted, no LLM)"), act path rigor (fixed above), screenshots (re-shot).

---

# Earlier: task 07 (`docs/prompts/07-ui.md`, all DONE)

| Part | Status | Commit |
|---|---|---|
| 0 Preflight + demo script | DONE | 07-0 |
| A API additions | DONE | 07A |
| B Frontend (themes, shell, Story, Brain, Explorer, polish) | DONE (polish continues in D) | 07B |
| C Deploy-ready container | DONE (nothing deployed) | 07C |
| D Headless-browser self-check | DONE | 07D |
| E Docs | DONE | 07E |

**Total live API spend: $0.00** (0 live calls, no key). **All parts DONE; nothing deployed.**
Tests: `pytest -q` **118 passed** · `npm test` (vitest) **17 passed** · Playwright **10/10** (`scripts/e2e.sh`, also 10/10
against the `docker compose` container) · `seed.verify` 14/14 + 8/8 on a fresh seed · Brain eval 15/15 + 3/3.
Preflight path: **Vite** (Node v22.23.2), not the no-build fallback.

## Look at these first in the morning
1. **Run it:** `scripts/ui.sh` → http://localhost:8000 → Story → *Fire alert*. Watch step 15 (the learned edge draws in), then Resolve → Fire Session 2 → Compare without memory → the before/after panel.
2. **Screenshots** in `docs/screenshots/`: `story-learned-edge-1920.png` (README hero), `story-before-after-light.png`, `story-session2-recall-dark.png`, `mobile-story.png`.
3. **One command for the whole UI check:** `scripts/e2e.sh` (≈1 min; it re-seeds `kestrel_pay` + `northwind_health` and replays the story into them).
4. **Behaviour changes to confirm:** every write now needs the access code (incl. `POST /api/team/run` and resolve, which M5 left open in mock mode); Brain answers without a code are not saved; your local `.env` `RATE_LIMIT_PER_MIN` was raised 20 → 60.
5. **`docs/demo-script.md`:** the 2:45 shot list with measured replay lengths (Session 1 at 1×, the rest at 2×).
6. **Deploy:** `docs/deploy.md` has the env table and generic steps; the host is still your call. Set `ACCESS_CODE` to a long random string before anything goes public.

## Decisions taken in 07 (details in each part below)
- Replays are JSON paced by the browser (deterministic, scrubbable); fresh runs stream over EventSource with a one-time token.
- No code → no writes anywhere; the no-memory contrast runs on a temporary twin graph, never the hero graph.
- One layout per story (seeded fcose, cached); the camera, not the nodes, follows the current step.
- Amber only ever means "written by an agent" (industry-match postmortems are seeded, so only their links are amber).
- Container seeds only EMPTY graphs, verifies them and plays the story once (mock); restarts keep memory.

## Known gaps
- Labels can overlap where many nodes sit close; the full Explorer graph is dense at 1440 px.
- The bundle is ~850 KB (262 KB gzip), mostly Cytoscape.
- The UI never offers live mode (by design for this run); live is reachable over the API with code + key.
- Rate limiter and the fresh-run lock are per process: run one replica (see `docs/deploy.md`).
- Not tried on a real phone or Safari/Firefox; Playwright covers Chromium (desktop + a 390×844 viewport).

## 07-0 — Preflight + demo script
**Status:** DONE
- `node -v` → **v22.23.2** (npm 10.9.8, Homebrew present). Node ≥ 18, so the **Vite path** (React + Vite + TS), not the no-build fallback.
- Docker up, `falkordb` container running; `scripts/setup.sh` clean (kestrel_pay 14/14, northwind_health 8/8); `pytest -q` → 105 passed before any change.
- `docs/demo-script.md`: the 2:45 shot list (7 beats, screen / click / narrator / timestamp) plus the list of UI features the script needs.

## 07A — API additions for the UI
**Status:** DONE · tests: `pytest -q` 116 passed (10 new in `tests/test_ui_api.py`, 1 new + 4 updated in `tests/test_api.py`)

**What was built** (`backend/api/views.py` = generic read models; `backend/demo.py` = the only story knowledge)
- `GET /api/meta` (tenants with display name + `has_story`, llm modes, `writes_need_code`, version), `POST /api/access/check`.
- `GET /api/story?tenant=`: beats from `demo.BEATS` (Fire alert → Resolve → Fire Session 2 → Compare without memory) with alerts, labels, resolver/summary, replay names.
- One **step event shape** for replays and fresh runs (`views.step_event`): `seq, agent, action, tool, summary, args, cypher, params, queries, result_preview, highlight{nodes, edges{source,target,type,props}}, cited[] (source cards), writes{nodes, edges} (agent-written, with origin), elements, mode, ms, llm_call`.
- `GET /api/replay/{name}` (the whole recorded run as events, JSON), `GET /api/run-graph/{run_id}` (golden name or a fresh run id), `GET /api/subgraph?ids=&hops=`, `GET /api/compare/latest`, `GET /api/brain/suggestions`, `GET /api/explorer?labels=&origin=agent`.
- Fresh story beats: `POST /api/story/{beat}/run` (**access code required**) → one-time stream token → `GET /api/stream/{token}` (EventSource). One fresh run per tenant at a time (409 otherwise).
- Golden runs regenerated with a **graph snapshot embedded** (`graph`), plus a 4th recording `team-session2-nomem.json`.
- `seed/conn.py`: one FalkorDB connection helper (host, port, optional username/password, `FALKORDB_TLS`) used by seed, scenario, verify and the backend.

**Decisions**
- *No code → no writes, everywhere.* `POST /api/team/run` and `/api/incidents/{id}/resolve` now need the code too (M5 let anyone write in mock mode). The UI's visitor path is the golden replays. Brain answers work without a code but are **not persisted** (`ask(persist=False)`: no Session/Step, `flag_stale` is a no-op); follow-ups then use the earlier turns the client sends back (`turns`, max 10, ids still grounded by tools).
- *EventSource can't send headers,* so the code is checked when the run is created and the stream URL carries a random single-use token that expires after 60 s.
- *Replays are JSON, not SSE:* the UI paces playback itself, so autoplay is deterministic and the scrubber can jump anywhere.
- *The no-memory contrast never touches the hero graph:* a fresh compare run uses an internal twin graph `<tenant>__nomem` (seeded, run, deleted). `get_graph` accepts the twin; the HTTP tenant check does not.
- *Run graph = snapshot taken right after the run*, so a replay looks the same whatever state the live graph is in. Session/Step nodes are not drawn (the timeline shows them).
- *Suggested questions are templates filled by Cypher* (decision behind the most recently changed service, a departed maintainer's service, top PageRank service, a doc by someone who left, a root cause shared with public postmortems, a team named in a doc title). All 12 (both tenants) were checked against the mock Brain; that found "decide" missing from the mock's stop words (fixed).

## 07B — Frontend (`frontend/`)
**Status:** DONE (screenshot polish rounds are in 07D) · `npm test` (vitest) 17 passed · `npm run build` OK (TypeScript 7, Vite 8)

**What was built**
- Stack as specified: React 19 + Vite 8 + TypeScript 7, Tailwind 4, zustand, lucide-react, Cytoscape.js + cytoscape-fcose, self-hosted Inter + JetBrains Mono, EventSource for fresh runs, Vitest.
- **B1 themes:** tokens on `:root` + `[data-theme="dark"]`; header toggle System → Light → Dark, stored in localStorage inside try/catch; an inline script in `index.html` sets `data-theme` before paint. The Cytoscape stylesheet is built from the computed tokens and re-applied on theme change. Amber = agent-written (double border + "AI ·" label), red = alerting service, blue = current path, dashed amber = learned edge. `prefers-reduced-motion` turns off pulses, the draw-in and transitions.
- **B2 shell:** header (glyph, Story · Ask the Brain · Explorer, company switcher, mode badge Replay/Mock, access-code dialog with sessionStorage, theme toggle, About with the three tracks); client routes `/`, `/brain`, `/explorer`; toasts with Retry; skeletons; stacked panes below 1024 px.
- **B3 Story:** timeline lanes with per-agent "tool call n", prominent hand-off cards, amber "wrote …" chips; graph laid out ONCE per story (fcose with a seeded RNG, positions cached per layout key; fresh-run nodes are placed beside their neighbours, existing nodes never move); the graph grows step by step, current path thick blue, earlier steps quieter; writes pulse amber; **the learned DEPENDS_ON draws itself in as a dashed amber line** (a ghost node animates from source to target); the camera smoothly frames the current step. Receipt drawer: tool + summary, highlighted Cypher per query with copy and a WRITE badge, parameters, result, source cards; node pane; final report card (cause + path, who to call + "maintainer left", the decision with its excerpt, "Seen before", industry match link, actions, confidence, mode, cost). Controls: play/pause, step, 0.5×/1×/2×, scrubber, space/←/→; deterministic dwell per step type. Story buttons from `/api/story`, ending on the before/after panel from `/api/compare/latest`.
- **B4 Brain:** suggestions from the API, answers with source cards, honest "I don't know" styling, "How I got this" with Cypher, a mini graph of cited nodes, follow-ups (client-kept turns without a code, graph session with a code).
- **B5 Explorer:** label filters, agent-memory-only toggle, search, "Critical hubs" sizing by `algo.pageRank`, node details pane, an empty state that explains tenant isolation.

**Decisions**
- *Replays are paced by the browser*, not the server, so a take is identical every time and the scrubber can jump anywhere.
- *The camera follows the current step* (positions never move): fitting the whole story at once made labels unreadable.
- *Industry-match nodes are not amber:* public postmortems are seeded data; the `SIMILAR_TO` edges the agent wrote to them are amber. Amber means "written by an agent" and nothing else.
- Chromium 156's `scrollIntoView` returns a Promise; an arrow-bodied `useEffect` returned it and React crashed on unmount. All effects use block bodies.

## 07D — Headless-browser self-check
**Status:** DONE · Playwright **10/10** (`scripts/e2e.sh`), pytest 117, vitest 17

**What was built**
- `frontend/playwright.config.ts` + `frontend/e2e/`: theme (both themes render, persists, follows the OS), story replay (all four buttons, the learned edge appears exactly at its step and disappears when scrubbing back, the before/after numbers equal `/api/compare/latest`, keyboard, no story POSTs without a code), deterministic autoplay + pause, Brain (suggestion → answer with source cards, follow-up "Who should I call about it?", "I don't know" styled as an answer not an error, "How I got this"), Explorer (filters, hubs, search, agent-only on the hero company, zero memory on the second), the gate (403s, wrong code rejected, badge stays Replay), and the full story run fresh with the code (writes, compare source "fresh", Brain answer saved). Every test fails on any console error.
- `docs/screenshots/`: 9 views × light/dark at 1440×900, `story-learned-edge-1920.png` (README hero) and `mobile-story.png` (390×844, no horizontal scroll).
- `scripts/e2e.sh`: builds the frontend, re-seeds both tenants and plays the story (mock), starts the app with a test code on :8765, runs Playwright. `--no-server` tests an app that is already running.

**Polish rounds (from looking at the screenshots)**
1. *Empty graph:* Cytoscape forces `position: relative` on its container, which collapsed an `inset-0` box to 0 px height. *Unreadable labels:* fitting the whole story made 11 px labels render at ~6 px; the camera now frames the current step plus the alert (positions never move), labels 12 px. Dimmed nodes were too faint (0.4 → 0.55). Write chips were a whole Fact sentence (now "wrote Fact · learned DEPENDS_ON"); `read_source → ok` cards now say what was read; the WRITE badge overlapped the Cypher (moved to a header strip); Brain disclosure markers were doubled.
2. *Screenshots were 1280×720:* the Playwright device preset overrode the viewport. The learned edge got a soft amber glow and a bolder label so the money shot reads at a glance; "PublicPostmortem" overflowed its filter cell; hand-off meta shortened; story toolbar no longer wraps at 1440 px (Restart is icon-only below 2xl).
3. *Bugs the browser found:* the mock Brain answered an unrelated question ("Kubernetes upgrade policy") from the previous turn's subject; it now leans on history only when the question says "that/it/this…" (pytest case added; eval still 15/15 + 3/3). The e2e `fire` helper raced the next beat's load (waits on `aria-current`/`aria-busy` now).

**Known gaps (cosmetic):** labels can still overlap where many nodes sit close (e.g. a chat title over the incident triangle); the Explorer's full company graph is dense at 1440 px.

## 07C — One deploy-ready container (nothing deployed)
**Status:** DONE · `docker build` OK · `docker compose up` served UI + API, seeded itself (kestrel_pay 14/14, northwind_health 8/8, story played) · **Playwright 10/10 against the container** · restart kept memory (no reseed)

**What was built**
- Multi-stage `Dockerfile` (Node 22 builds `frontend/dist` → Python 3.12 slim; non-root; `PORT` env; `HEALTHCHECK` on `/api/health`; golden replays baked in).
- `SEED_ON_START=1`: empty tenant graphs are seeded (+ public postmortems) and verified with `seed.verify`, then the story is played once in mock mode so memory exists; graphs with data are left alone (pytest covers both).
- `docker-compose.yml` (FalkorDB + app, both bound to 127.0.0.1) and `docker-compose.prod.yml` (app only; FalkorDB host/port/user/password/TLS from env).
- `seed/conn.py` gives every connection the same env (incl. `FALKORDB_USERNAME`, `FALKORDB_PASSWORD`, `FALKORDB_TLS`); `.env.example` updated.
- `docs/deploy.md`: env var table, generic steps for any container host, and a clear note that the host is still to be chosen.

**How it was verified:** the local compose stack ran as a separate project on 127.0.0.1:8001 with FalkorDB unpublished (so the dev `falkordb` container on :6379 was untouched), `scripts/e2e.sh --no-server` ran against it, then the test stack, its volume and images were removed. No registry, no host account, no deploy.

## 07E — Docs
**Status:** DONE
- `README.md`: hero screenshot (light, 1920) + dark and before/after in a fold-out; "Run the UI locally" (`scripts/setup.sh` → `scripts/ui.sh`, or `docker compose up --build`); the three views mapped to the tracks; architecture diagram gains the Web UI; test counts and repo map updated. Video/live-URL `TODO:`s kept.
- `docs/explain.md`: how the UI gets its data, why the layout is stable, the learned-edge animation, the access-code gate, likely judge questions; plus 07A and 07C sections.
- `docs/demo-script.md`: timings measured from the recordings; beat 3 wording made accurate (amber = the links, not the postmortems).

---

# Earlier: overnight task 06 (`docs/prompts/06-overnight.md`, all DONE)

| Part | Status | Commit |
|---|---|---|
| A Setup on a fresh Mac | DONE | 06A |
| B Memory-first recall | DONE | 06B |
| C Public postmortems | DONE | 06C |
| D Brain eval 5 → 15 | DONE | 06D |
| E README draft | DONE | 06E |
| F Hardening pass | DONE | 06F |

Tests at the end of 06: 105 passed ×3 in a fresh Python 3.12 venv; `seed.verify`: kestrel_pay 14/14, northwind_health 8/8; Brain eval 15/15 + 3/3.

## Look at these first in the morning (06)
1. **The before/after box** below (`scripts/demo.sh --quiet`). Session 2's Investigator names the culprit on its 3rd tool call via `memory_recall`; without memory the cause isn't found.
2. **`docs/postmortems.md`:** 21 real public postmortems with summaries written by the AI from each page. Read them; they are about real companies. No certificate-expiry entry (couldn't verify a primary page).
3. **Two judgement calls to confirm** (06B): `memory_recall` returns only agent-written memory (so Session 1 recalls nothing), and "within 3 tool calls" is counted for the Investigator (Triage needs 5 calls first).
4. **Security fixes from the review** (06F): agents could overwrite seeded history via `record_resolution` (high) and quote their own invented incident summaries; both are closed, with tests.
5. **README draft:** paste the official track focus bullets into the three `TODO:` lines; add video/URL/screenshots.
6. **Schema v1.2** (06D): two full-text indexes only (RootCause, PublicPostmortem). The doc's changelog says why.

## Final before/after box (fresh reseed, mock, `scripts/demo.sh --quiet`)
```
  +------------------------+-----------------------------+----------------------------+----------------------+
  |                        | Session 1                   | Session 2                  | Session 2, no memory |
  +------------------------+-----------------------------+----------------------------+----------------------+
  | alert                  | payments-api                | payouts-service            | payouts-service      |
  | incident               | INC-2026-032                | INC-2026-033               | INC-2026-032         |
  | cause                  | dep:risk-rules-v2.8.0       | dep:risk-rules-v2.8.1      | unknown              |
  | confidence             | high                        | high                       | low                  |
  | tool calls until cause | 14 total, 8 by investigator | 9 total, 3 by investigator | cause NOT found      |
  | LLM calls until cause  | 8                           | 6                          | -                    |
  | LLM calls total        | 12                          | 11                         | 10                   |
  +------------------------+-----------------------------+----------------------------+----------------------+

  Session 2, from memory: Seen before: INC-2026-032, fixed by Priya Nair (Priya rolled back RULES_CACHE_TTL to 300s;
  config-service load recovered), see Runbook v2 step 2 (rb:fraud-scoring-latency-v2).
```
(The no-memory run is on its own fresh seed, which is why its incident key is also INC-2026-032.)

## 06F — Hardening pass
**Status:** DONE

One independent reviewer agent (it hadn't seen the work) checked the 8 areas in the spec and ran `pytest -q` 3× (102/102 each time). It found 1 high and 6 medium issues. All are fixed, each with a test:
- **High: seed history could be overwritten.** `record_resolution` didn't check origin, and `res:<id>` collides with the seed Resolution id, so a resolve on a historical incident would overwrite it. Now refused, like `update_incident`.
- `link_similar` now requires an agent-opened incident and an active session (it could link seed→seed).
- **Agents can't quote themselves:** an agent-written incident is quotable only after "Resolution (operator): " (the operator's words). Before, an agent could put any text into its incident summary and then cite it as a "verbatim source".
- **Grounding:** a second failed submit used to be accepted with `grounding.ok=false` and still handed off or served. Now the run ends with `status: ungrounded` and **no report** (kept as `rejected_report`). Tool calls after a submit in the same turn are skipped. Nested schema fields are checked (e.g. `conflicting_decision.source_id`), and every `excerpt` is checked, including citations missing an id or text.
- **Story ids removed from LLM-facing tool descriptions** (`registry.py`: `svc:<name>`, `inc:<year>-<nnn>` …) and from the Brain prompt's examples.
- `package_for` raises for an unknown tenant instead of silently loading Kestrel Pay's data; `/api/admin/reseed` turns that into a 400; `demo story` refuses non-Kestrel graphs.
- Low: `record_fact` with a non-string statement no longer crashes; `write_runbook` refuses a title with no letters; the seed loader raises instead of `assert`; FalkorDB ports are bound to 127.0.0.1 (compose + setup.sh); dead `llm_tool_specs()` removed; the test allowlist no longer includes the real `kestrel_pay` graph.

**Not fixed (low; listed on purpose)**
- `_Q_STOP` in the Brain mock has eval-flavoured words ("seconds", "stay", "left"). No ids, so not a leak; a live model doesn't use it.
- Nothing checks that `people` / `contact.person_id` in a final answer are still active (who_to_call only returns active people, and paging someone who left is refused).
- `page_person` / `open_ticket` accept a historical incident id (harmless, inconsistent).
- `ToolContext()` defaults to `kestrel_pay` if a caller forgets the context; all real callers pass it.
- `/api/sessions?user=` and `/api/sessions/{id}` don't check ownership (the UI replay needs them); Brain follow-ups do.
- `seed.load` / `seed.scenario` / `seed.verify` CLIs connect directly (no allowlist): CLI-only.
- `falkordb/falkordb:latest` is unpinned in docker-compose.
- Two simultaneous pytest runs against one FalkorDB would collide on the fixed scratch graph names.

**Final checks (fresh reseed):** kestrel_pay 14/14, northwind_health 8/8; `pytest -q` 105 passed ×3 in a fresh Python 3.12 venv (and in `.venv`); `scripts/demo.sh --quiet` box above; golden runs and `docs/cypher.md` regenerated.

## 06E — README draft
**Status:** DONE (draft; `TODO:` placeholders for demo video, live URL, screenshots and the official track focus bullets)

**What was built:** `README.md`: pitch, 3-minute quickstart (`scripts/setup.sh`, `scripts/demo.sh --quiet`), architecture Mermaid (FalkorDB ↔ tools registry ↔ agent loop (RulePlanner | LLMPlanner) ↔ CLI / FastAPI / MCP), data model (link to `docs/schema.md` + a small diagram), the Cypher/algorithm table (variable-length paths, `algo.SPpaths`, `algo.pageRank`, `algo.betweenness`, full-text, single-query allocation), "How memory works" with the before/after table, one section per track, modes + cost caps, MCP, tenant isolation, repo map, AI-assistant disclosure. New `docs/live-mode.md` (mock vs live, the six cost layers, first live run commands). `docs/demo-checklist.md` numbers refreshed. `brain_eval --live` no longer aborts on the restart case (runs it in-process when live).

**Decisions:** the hackathon's official per-track focus bullets are not in the repo, so each track section maps features to the themes we know ("tool selection via MCP", "high-concurrency reads/writes", "separate memory per tenant") and has a `TODO:` to paste the official bullets. No claims about live behaviour; the README says live mode has not been run.

## 06D — Ask the Brain eval: 5 → 15 (+3 Northwind)
**Status:** DONE · **pass rate: Kestrel Pay 15/15 on a fresh seed and 15/15 after the story; Northwind Health 3/3** (mock).

**What was built**
- `backend/agents/brain_eval.py`: 15 Kestrel questions, one per intent: why-decided with an exact quote (`300s` must be in a cited excerpt), who-knows after Arjun left, onboarding, stale docs, follow-up "that", who owns config-service (must name Platform + Omar Haddad), what breaks if config-service fails, have we seen config-service overloaded before, follow-up pronoun "Who should I call about it?", what did session N learn, industry pattern for our thundering herd, another user continuing a session (must be refused), the same follow-up from a NEW Python process (restart persistence), a question with no answer (Kubernetes upgrade policy → "I don't know", no citations), and "Why did we decide that?" after onboarding. Plus 3 Northwind questions (SMS retry decision, who knows notifications after Owen left, industry pattern for retry storms). `--tenant northwind_health` runs those.
- Brain (mock policy + prompt): new intents `blast`, `seen`, `session`, `industry`; services resolved from plain words too ("notifications"); owner team in "who" answers; pronoun follow-ups resolve from cited history; "decided by" only for Decisions.
- **Router fix found by the eval:** the knowledge path used to fall back to the best *any-word* search hit, so "Kubernetes upgrade policy" was answered from an unrelated Kafka ticket. Now only sources matching ALL the specific terms count; otherwise "I don't know".
- Brain tools + `blast_radius`, `industry_matches`. Schema **v1.2**: full-text indexes on `RootCause(name, description)` and `PublicPostmortem(title, summary)` (index-only; changelog in `docs/schema.md`); `search_knowledge` still searches the original six labels unless `labels` asks for these.
- Tests: eval size, Northwind eval; existing fresh/after-story eval tests now cover all 15.

**Decisions**
- *Session question on a fresh seed:* there is no team session yet, so Q10 asks about a non-existent session and must answer "I don't know" (that also tests honesty). After the story it asks about the latest session that wrote a Fact and must cite every such Fact.
- *Restart persistence* is checked with a real subprocess (mock only; the eval refuses that case in live mode so it never spends money twice).

## 06C — Public postmortems (industry pattern layer)
**Status:** DONE

**What was built**
- `seed/data/public_postmortems.json`: **21 real public postmortems** (Cloudflare ×4, AWS ×4, Google Cloud ×2, Meta ×2, Slack ×2, GitHub, Stripe, Fastly, Roblox, GitLab, Datadog, Twilio). Each: company, exact title, url, published date, **our own ≤ 60-word summary** (no quotes), 1–2 root-cause tags. Every page was fetched and its facts checked on the page itself on 15 Oct 2026. `docs/postmortems.md` is generated from it (`python -m backend.tools.export_docs`).
- `seed.load` adds the layer to EVERY tenant: `PublicPostmortem` nodes + `HAS_ROOT_CAUSE`; generic RootCauses (`rc:dns-bgp-misconfiguration`, `rc:hidden-dependency`, `rc:database-failover`, `rc:capacity-limit`, `rc:operator-error`, plus the reused ids) are added only where the tenant doesn't define them. Northwind's `rc:nw-retry-storm` was renamed to the generic `rc:retry-storm` so its incidents match too.
- `seed.verify`: new check for both tenants (≥ 15 postmortems, each with a root cause, https url, ≤ 60 words); Kestrel targets updated (RootCause 10, PublicPostmortem 21). kestrel_pay 14/14, northwind_health 8/8.
- Read tool #16 `industry_matches(root_cause_id | incident_id)`: postmortems sharing a root cause, ranked by shared root causes → words shared with the incident → recency; flags ones already linked.
- Resolve (postmortem pass) calls it and writes `SIMILAR_TO {score, reason, origin:'agent'}` to the best 1–2 not yet linked. S1's incident links to Slack 2-22-22 and Facebook 2010 (both cache stampedes).
- Reports gain `industry_pattern`: "Matches known industry pattern: Slack — Slack's Incident on 2-22-22 (https://slack.engineering/slacks-incident-on-2-22-22/)" (Communicator and Firefighter; mock + prompts). Firefighter: 5 LLM calls, check_run 12/12.
- MCP now lists 16 read tools; golden runs and `docs/cypher.md` regenerated; 5 new tests.

**Decisions**
- *Skipped when unverifiable:* Epic Games' certificate post (403), Microsoft Azure 2013 certificate post (URL now redirects to a category page), Reddit Pi-Day (fetch blocked), Google Voice 2021 (no primary page found). So **no postmortem is tagged `rc:expired-tls-certificate`** yet; add one when a primary page can be read.
- *Dates:* AWS S3 2017 / Kinesis 2020 / DynamoDB 2025 and both GCP status pages show the incident date, not a publication date; those use the incident date (stated in the doc).
- *Tag judgement calls:* Slack 2-22-22 and Facebook 2010 are tagged `cache-ttl-thundering-herd` (a cache emptied or judged invalid → everyone hits one store); Datadog 2023 is `bad-config-push` + `hidden-dependency` (an automatic OS update rolled widely and collided with container routing). Worth a look.
- *Ranking is deliberately simple:* shared root causes, then word overlap. Good enough to pick 1–2 links; no embeddings (schema §5.3).

## 06B — Memory-first recall
**Status:** DONE

**What was built**
- Read tool #15 `memory_recall(service_id, max_hops=3)` (`graph_tools.py`, registry, MCP, `docs/cypher.md`). Scope = the alert service + everything it calls within 3 hops (declared or learned). Returns: learned `DEPENDS_ON` edges touching the scope (with the Fact on `learned_from`, its `SOURCED_FROM` excerpt and the Session it was written in), other agent Facts about scope services, incidents with `origin:'agent'` and `status:'resolved'` that AFFECTED the scope (cause deploy + service, root causes, Resolution summary, PERFORMED_BY people, session) and, for each, the newest runbook (`SUPERSEDES*0..5` back to one that nothing supersedes) with its steps; plus `suspects` (services memory points at, relation `downstream` or `shares_dependency`). Result ≤ 4,500 chars.
- Investigator + Firefighter (mock policy AND live prompts): call `memory_recall` first, alone. With a suspect: verify it with ONE tool (`recent_changes_downstream` if downstream, else `shared_dependency_changes`); if it changed recently it is the culprit and the cause is set immediately (`update_incident` + `link_similar` to the recalled incident, in the same turn as `decisions_about` / `past_incidents` / `who_to_call`). Without a suspect, or if the suspect didn't change: exactly the old scan.
- The Investigator note and the final report say: "Seen before: INC-2026-032, fixed by Priya Nair (Priya rolled back RULES_CACHE_TTL to 300s; config-service load recovered), see Runbook v2 step 2 (rb:fraud-scoring-latency-v2)." Every value comes from the `memory_recall` result.
- `time_to_cause` now also has `agent_tool_calls` (the setting agent's own calls). Demo summary is a before/after box with Session 1, Session 2 and Session 2 without memory. `--compare-no-memory` now runs the no-memory contrast FIRST (fresh seed + scenario + S2), then the full story, so one command shows all three.
- Prompts no longer name Kestrel Pay ("at this company"): the same prompts serve Northwind.
- Golden runs regenerated; 6 new tests (recall empty on a fresh seed, learned edge → suspect, S2 order recall → verify → cause, S1 recalls nothing and scans as before, contrast).

**Numbers (mock):** Session 2's Investigator names `dep:risk-rules-v2.8.1` at its **3rd** tool call (memory_recall → shared_dependency_changes → update_incident); 9 tool calls / 6 LLM calls from session start (Triage uses 5 + its handoff before the Investigator starts). Session 1: 14 / 8 (8 by the Investigator); it was 13 / 7: the +1 is the empty `memory_recall`. Session 2 without memory: cause not found.

**Decisions**
- *Recall = agent-written memory only.* Seeded history (e.g. resolved INC-2025-031 on payments-api) stays with `past_incidents`. Otherwise Session 1 would "recall" the seed and change, and the spec says Session 1 has no memory to recall. A first session therefore honestly recalls nothing.
- *"Within its first 3 tool calls" is counted for the Investigator,* the agent that names the cause. Session-wide it can't be ≤ 3: Triage must open the incident first (5 calls). Both numbers are in the box.
- *Session 1's results are unchanged* (same cause, learned edge, page, ticket, flags, resolve); its only behavioural change is one empty `memory_recall` call first.
- *Learned edges count if they touch the scope,* not only if they lie on the alert service's outgoing paths: a learned edge INTO one of my dependencies is exactly how a noisy neighbour shows up.

## 06A — Setup that works on a fresh Mac
**Status:** DONE

**What was built**
- `scripts/setup.sh`: finds Python ≥ 3.10 (tries python3.15 … python3.10, then python3; macOS's `/usr/bin/python3` is 3.9 and there is often no `python`, which is what broke the first setup), creates/repairs `.venv`, installs `requirements.txt`, copies `.env.example` → `.env` if missing (mock mode), checks Docker is installed and running, starts the `falkordb` container if stopped (creates it if missing), waits for :6379, seeds and verifies both tenants. Idempotent; each failure says what to do.
- `scripts/demo.sh`: activates `.venv` and runs `python -m backend.demo story --compare-no-memory` (extra flags such as `--quiet` are passed through).
- `requirements.txt`: every direct dependency pinned (`==`), incl. `pydantic` and `anyio`, which the code imports directly.
- `python -m backend.demo story --quiet` now prints the session headers, every handoff note and the summary box (it used to print nothing). Verbose stays the default.
- Tests now block the network: `tests/conftest.py` refuses any socket connect that isn't localhost / the FalkorDB host (+ a test proving it).

**Checks:** `scripts/setup.sh` ran clean (kestrel_pay 13/13, northwind_health 7/7). Fresh Python 3.12 venv + `pip install -r requirements.txt` + `pytest -q` → 87 passed (before the network test was added); `.venv` (3.15) → 88 passed.

**Decisions:** demo.sh is the literal command from the spec; `scripts/demo.sh --quiet` gives the short version. `.venv` and `.env` were already git-ignored.

---

# Earlier: mega task M1–M6 (`docs/prompts/05-mega.md`, all DONE)

**Run constraint (from Jaya, 15 Oct 2026):** build all LLM code, but make **no live API calls** and use **no API key**. Every "Live check" is therefore `SKIPPED (no key)`, and everything was built and tested in mock mode.

**Total live API spend: $0.00** (0 live calls). Tests: `pytest -q` → 87 passed. `seed.verify`: kestrel_pay 13/13, northwind_health 7/7.

| Milestone | Status | Commit |
|---|---|---|
| M1 Firefighter agent | DONE (live check SKIPPED, no key) | 5f54e03 |
| M2 Memory write-back + team + Session 2 | DONE (live check SKIPPED, no key) | 66db978 |
| M3 Ask the Brain | DONE (live check SKIPPED, no key) | bd91e13 |
| M4 MCP server | DONE | 75f3109 |
| M5 Backend API | DONE | bcaa44b |
| M6 Second tenant | DONE | e00b14f |

## How to run the demo story (5 commands)
```bash
docker start falkordb && source .venv/bin/activate && pip install -r requirements.txt
python -m backend.demo story                       # re-seed both tenants, S1, resolve, S2, summary, switch tenant (mock, free)
python -m backend.demo story --compare-no-memory   # the contrast: Session 2 without Session 1's memory
python -m backend.agents.brain_eval                # Ask the Brain: 5 canned questions incl. a follow-up
uvicorn backend.api.main:app                       # API + SSE; POST /api/replay/team-session1.json for a recorded run
```
Add `--live` to the first two (needs `ANTHROPIC_API_KEY` in `.env`) once you decide to spend.

## Things Jaya must understand before judging
1. **Memory changes the graph's structure, not a prompt.** In Session 1 the Investigator reads the chat line "On every cache miss risk-rules polls config-service's internal /v1/rulesets endpoint." and writes a `DEPENDS_ON {source:'learned'}` edge plus a `Fact` that quotes it. In Session 2 the *same, unchanged* noisy-neighbour query on payouts-service finds risk-rules only because that edge now exists. `--compare-no-memory` proves it: without the edge, the cause is "unknown".
2. **Agents hand off through the graph.** Triage, Investigator and Communicator each start with an empty conversation: just the alert plus `get_incident_state`. Every note one agent leaves for the next is a `Step` node (`action:'handoff'`). So the team's reasoning is inspectable in the FalkorDB Browser, crash-safe, and replayable (`/api/sessions/{id}`).
3. **Every step is a receipt.** Each tool call is persisted live as a `Step` with the exact Cypher, its parameters and `CITED` edges to the nodes it used, chained by `NEXT`. "How did it get the answer?" is a graph query.
4. **Grounding.** An agent may only cite or write ids that came back from a tool in that run, and every quote must be a literal substring of its source node. Violations are rejected with the reason (one retry), then recorded as `grounding.ok = false`. This is what stops invented people, ids and quotes.
5. **Writes are validated and atomic.** Every write checks that ids exist with the right label, quotes are literal and learned edges aren't duplicates, and refuses to page someone who left. Incident/ticket keys and the learned edge are each allocated and created in one Cypher query. FalkorDB runs write queries one at a time per graph, so 5 parallel team runs gave 5 distinct incidents and exactly 1 learned edge, with no retries needed.
6. **Mock mode is a real "fake model", not canned output.** `mock_policy.py` reads tool results and applies rules (nearest downstream deploy = culprit; ≥2 shared words between change and decision title = conflict; resolved incidents caused by the same service = "seen before"). It solved Northwind's different story without changes. It makes development, tests and a public demo free, and the live LLM uses the identical loop, tools and checks.
7. **Cost control is layered.** Default mock; one LLM wrapper (`backend/llm.py`) with `max_tokens`, prompt caching (system + last tool) and a per-run budget guard (`MAX_RUN_COST_USD`). The API serves live only with `live: true` plus a valid access code, a server key and room under a daily cap (Redis counter), and rate-limits per IP.
8. **Expertise is computed, not stored.** "Who to call" ranks active people by commits + 25 × incident fixes. After Session 1 is resolved, Priya's score rises (48 → 73) because she now has another fix in the graph. The maintainer who left is flagged as a bus-factor risk.
9. **Tenant isolation is structural.** One FalkorDB graph per company. A Kestrel Pay id doesn't exist in Northwind's graph, so tools can't reach it; the Brain on Northwind honestly answers "I don't know" about RULES_CACHE_TTL. The MCP server is pinned to one tenant per process.
10. **Honest metrics.** (Updated in 06B.) Investigator tool calls until cause: Session 1 = 8, Session 2 = 3 (memory recall, one verification, set cause); session-wide 14 vs 9. Without Session 1's memory, Session 2 doesn't find the cause at all.

## Known issues
- **No live run has ever happened** (by instruction). Prompts are written for Haiku but untested against a real model; expect one round of prompt tuning on the first live run (see each milestone's "Live check" commands).
- `get_incident_state` returns up to 10,000 chars (other tools 2,500) so handoffs are never trimmed; it grows with the number of sessions per incident.
- Rate limiter is in-process memory; the daily cap is per Redis. Fine for one container.
- Incident keys assume < 1,000 incidents per year per tenant (3-digit sequence).
- `/api/graph` overview hides Step/Session nodes to stay ≤300 nodes.
- A Brain "who" answer with no source mentioning the person falls back to "I don't know" (citations are mandatory).
- MCP not yet tried inside the Claude Desktop GUI (verified with the SDK client over real stdio).

## Suggested next steps
1. **Live checks** (when you add a key): `python -m backend.agents.firefighter ... --live` + `check_run`, then `python -m backend.demo story --live`, then `python -m backend.agents.brain_eval --live`. Budget ≈ 50 Haiku calls total.
2. **UI:** graph panel on `/api/graph` (colour `origin:'agent'`), an SSE trace view on `/api/team/run`, Ask-the-Brain chat on `/api/brain/ask` with session history, and replay from `/api/replay`.
3. **Deployment:** `docker compose up --build` is ready; set `ACCESS_CODE`, `CORS_ORIGINS`, `DAILY_LIVE_RUNS`, seed via `/api/admin/reseed`.
4. **Public postmortems** (schema's PublicPostmortem / SIMILAR_TO to `pm:`), still out of scope.
5. **README rewrite and the demo video** (use `docs/demo-checklist.md`; record with Sonnet only).

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

## M4 — MCP server (Track 1: tool selection via MCP)
**Status:** DONE · commit `75f3109` · no live calls involved

**What was built:** `backend/mcp_server.py` (stdio). It exposes all 14 read tools from the registry: names, descriptions and JSON schemas generated from it. Each call returns the result JSON plus a "Cypher receipt" text block. Also `tests/test_mcp.py` (in-process client: tool count = registry, `recent_changes_downstream` on the test graph, errors) and `docs/mcp.md` (Claude Code + Claude Desktop config, 3 prompts).

**How to run:** `python -m backend.mcp_server --tenant kestrel_pay`; for Claude Code: `claude mcp add incident-brain -e PYTHONPATH=$PWD -- $PWD/.venv/bin/python -m backend.mcp_server --tenant kestrel_pay`.

**Decisions (plain language)**
- *Read-only over MCP.* External clients can query everything our agents can read, with receipts, but can't write memory or start agent runs. That keeps it safe and keeps API spend inside our budget.
- *The registry is the single source of truth.* The installed SDK is mcp 2.3, where FastMCP became `MCPServer`. Its decorators build schemas from Python signatures, so I used the SDK's low-level `Server`, which takes the registry's schemas as data. Adding a tool to the registry adds it to MCP automatically.
- *One process per tenant.* `--tenant` picks the graph, so a client connected to Kestrel Pay can never see another company's graph.

**Open issues:** none known. Not yet tried inside Claude Desktop itself (no GUI in this unattended run).

## M5 — Backend API (local)
**Status:** DONE · commit `bcaa44b` · no live calls involved

**What was built:** FastAPI app `backend/api/main.py` + `backend/api/guard.py`:
- reads: `/api/health`, `/api/tenants`, `/api/graph` (overview / incident, ≤300 nodes; each node has id/label/name/origin, each edge from/type/to/source), `/api/node/{id}`, `/api/sessions`, `/api/sessions/{id}` (full steps with CITED ids, for replay);
- runs: `POST /api/team/run` (SSE: `start`, `agent`, `step`, `write`, `handoff`, `report`, `done`, `error`), `POST /api/incidents/{id}/resolve`, `POST /api/brain/ask`, `POST /api/replay/{run_file}` (golden runs, no LLM);
- admin: `POST /api/admin/reseed`.

Also `Dockerfile`, `.dockerignore`, `docker-compose.yml` (falkordb + api with healthchecks, optional `.env`), golden runs in `runs/golden/`, and 9 tests. `docker compose config` parses; `docker build` succeeds and the app imports inside the image (image removed afterwards; nothing deployed).

**How to run**
```
uvicorn backend.api.main:app --reload            # http://localhost:8000/docs
curl -N -X POST localhost:8000/api/team/run -H 'Content-Type: application/json' \
     -d '{"service_id":"svc:payments-api","symptom":"5xx rate 12%"}'
curl -N -X POST 'localhost:8000/api/replay/team-session1.json?delay_ms=300'
python -m backend.demo story --quiet --save-golden   # regenerate the golden runs
docker compose up --build
```

**Decisions (plain language)**
- *Free by default, live behind a code.* Every agent endpoint works without credentials in mock mode, so judges and the public can explore. The real model runs only if the request asks for `live: true` and carries the right `X-Access-Code` (constant-time compare), the server has a key, and today's cap (`DAILY_LIVE_RUNS`, a Redis counter `ib:live_runs:<date>` with a TTL) has room. Otherwise it falls back to mock and says why; over the cap returns 429.
- *Per-IP token bucket* (`RATE_LIMIT_PER_MIN`, default 20) on everything except `/api/health`.
- *Streaming via SSE.* The team run executes in a worker thread; every Step becomes a `step` event (plus `write` / `handoff` events) the moment it is written to the graph. Golden replays reuse the exact same step→event mapping.
- *Admin needs the code.* Re-seeding is the only write outside agent runs and requires `X-Access-Code`. Resolve is an agent run (the postmortem pass), so it follows the agent rules.
- *CORS allowlist* from `CORS_ORIGINS`; nothing is open by default.

**Open issues**
- The rate limiter and cap are per process / per Redis; fine for one container.
- `/api/graph` overview hides Step/Session nodes to stay under 300 nodes; the incident view shows the memory around one incident.

## M6 — Second tenant: tenant isolation
**Status:** DONE · commit `e00b14f` · no live calls involved

**What was built:** `seed/data/northwind_health/`: 42 fully synthetic nodes (Patient Experience + Clinical Platform, 8 people, 9 services, a planted story: notifications v3.2.0 / NW-88 contradicts `dec:sms-retry-cap`, and its maintainer has left). Also a 7-check verify set, `seed.load.package_for`, `TENANTS` default `kestrel_pay,northwind_health`, the demo's final "switch tenant" beat, and `tests/test_tenants.py` (no agent nodes leak; Brain says "I don't know" about RULES_CACHE_TTL; Kestrel ids fail cleanly in every write tool; Kestrel session ids are refused; API + MCP serve the second tenant).

**How to run:** `python -m seed.load --graph northwind_health --reset && python -m seed.verify --graph northwind_health`; `python -m backend.agents.team run --tenant northwind_health --service svc:patient-portal --symptom "..."`; `python -m backend.agents.brain ask "Why are SMS retries capped?" --tenant northwind_health`.

**Decisions (plain language)**
- *Isolation by construction.* Memory lives inside each tenant's own graph, so there is no filter to forget: a query on Northwind physically cannot traverse into Kestrel Pay.
- *A different story, the same agents.* Northwind has its own incident pattern and the unchanged mock policies solve it (the team blames NW-88 and pages Maya because Owen left). Evidence that the agents are driven by the graph, not by Kestrel-specific code.
- *Synthetic only.* Northwind describes systems, teams and decisions; there is no patient data anywhere, and it says so in a seeded policy doc.

**Open issues:** none known.

---

# Look at these first (08, morning list)

**Commands**
- `scripts/ui.sh` → http://localhost:8000 → **Story** → *Alert storm* (or the **Firefighter** tab): watch 6 alerts become
  2 incidents and 2 pages; then the *Hypotheses* and *Actions* tabs. **Eval** tab: "Why a graph?" + scoreboard + benchmarks.
- `scripts/e2e.sh` (≈2 min, 18 Playwright tests, re-shoots the screenshots; it re-seeds kestrel_pay and northwind_health).
- `python -m backend.agents.firefighter_eval` (≈10 s; writes docs/eval.md + runs/eval/latest.json).
- `python -m backend.tools.benchmark` (docs/benchmarks.md), `python -m backend.agents.mcp_transcript` (docs/mcp-transcript.md).
- `python -m backend.agents.firefighter --service svc:payments-api --symptom "5xx" --tools-via mcp`.

**Screenshots** (`docs/screenshots/`): `ff-storm-1920.png` (new README hero), `ff-storm-correlate-*.png`,
`ff-storm-outcome-*.png`, `ff-storm-actions-*.png`, `ff-hypotheses-*.png`, `ff-safety-hold-*.png`,
`eval-why-a-graph-*.png`, plus the earlier story shots (re-shot with the new nav).

**Decisions for Jaya**
1. Schema **v1.3**: two optional Step properties (`why`, `hypotheses_json`), no labels/edges (docs/schema.md changelog).
2. Your local `.env` `TENANTS` now includes `scale_demo` (the switcher shows "Scale Demo"); remove it if you don't want
   it in the video.
3. README hero is now the storm screenshot; the old learned-edge hero is in the fold-out.
4. The FalkorDB 6.0.2 crash (wide aggregation row with NULLs; repro in `.scratch/crashprobe*.py`, described under 08A2):
   report it upstream? It's a credible "we stress-tested FalkorDB" story.
5. Demo script v2 (Track 1 first) replaces the v1 order; v1 is kept below it in docs/demo-script.md.
6. The usage note: I stopped using per-commit verifier agents and the 5-judge panel after your message; one
   independent reviewer + judge pass ran at the end (scores and fixes under 08J).

**Known gaps (honest)**
- Everything is mock mode: the planner is deterministic rules; no LLM has selected a tool yet (live check:
  `scripts/live-check.sh`, ≈$0.15 on Haiku).
- On single alerts the algorithms add nothing measurable over traversals; they matter in storms. Benchmarks: at 2,000
  services BFS and variable-length Cypher tie.
- The held-out set's author was told the shapes to cover (incl. one planner rule); generated scenarios use the same
  oracle for their expectations.
- "Approve" is simulated (no pager/CI) and only on the run's own copy of the company.
- A caller of the alerting service that shares a narrow dependency counts as a neighbour (judgement call).
- The 2,000-service company is generated (shallow layers), so it stresses size more than depth.

**Revert map:** the table at the top of this file.

## Landing page
- 2026-10-18: `docs/site/index.html` written (single static file, mock-mode wording, VIDEO_URL/REPO_URL placeholders still to replace) and pushed.
