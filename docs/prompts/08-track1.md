Resume line if stopped: "Read docs/prompts/08-track1.md and docs/progress.md and continue."

# 08 — TRACK 1 ALL-IN: "Agents That Act on Connected Data"
Official Track 1 focus: multi-hop reasoning · graph queries and algorithms as agent tools · tool selection through MCP · actions based on what the graph shows · explainable results. Prize text: "the best agent that uses a graph to make decisions and take action." Every part below must make one of these visibly stronger IN THE UI and in the video.

## Hard rules (override anything else)
- ZERO Anthropic API calls. No key exists. LLM_MODE=mock everywhere. Live code paths are tested only with fake clients.
- Nothing deployed, no host accounts, no registries, no secrets. Network only for package registries and docs.
- Schema: NO new labels, NO new edge types. Allowed: optional new properties and new indexes, each logged in the docs/schema.md changelog (v1.3). If a feature seems to need a new label, model it with existing ones and write the proposal in progress.md instead.
- No story knowledge in agent code, prompts, tools or frontend (only seed/, backend/demo.py, scenario fixtures and tests know stories). Same code must work on every tenant.
- The hero story must not regress: seed.verify, Brain eval 15/15 + 3/3, the demo before/after numbers, and all existing Playwright specs stay green. If golden replays must be regenerated, do it in its own commit.
- Stay inside the repo. Scratch files go in ./.scratch/ (add to .gitignore). Do not read or write outside the repo. No rm outside the repo, no force-push, no amend, no squash, no history rewrite, no git remote changes.
- FalkorDB quirks in CLAUDE.md apply. Parameterised Cypher only.

## Commit protocol (Jaya must be able to revert any single piece)
- Before any code: `git tag pre-08 && git push origin pre-08`.
- One logical, green change per commit, named `08<Part><n>: <what>` (e.g. 08A1, 08A2). Each commit: relevant tests green → progress.md + ai-log.md updated → commit → `git push origin main`. Never leave a part half-committed; never mix two parts in one commit.
- Prefer commits that can be reverted independently (feature behind its own module/endpoint/flag; backend before UI).
- Keep a "Revert map" table at the top of docs/progress.md: commit hash · part · what it changed · safe to revert alone? (yes / needs also X).
- Ultracode/workflows: use parallel agents for exploration, scenario authoring, test writing, verification and review. Code changes land on main ONE sub-step at a time, sequentially, after verification. No two agents edit the same files at once.

## 0. Preflight
Docker + FalkorDB up, scripts/setup.sh OK, pytest -q, npm test, scripts/e2e.sh all green BEFORE changes; record the counts as the baseline in progress.md.

## A. Scenario library + Firefighter eval scoreboard (generality proof)
- 8+ new incident scenarios across both tenants, each a different reasoning shape: bad deploy 3+ hops downstream; FALSE LEAD (a fresh deploy NOT on the dependency path; agent must reject it); no recent change (capacity/traffic: agent must say "no change found" and pick a hub via PageRank, not invent a cause); shared hub saturation; betweenness chokepoint cascade; two independent simultaneous incidents; a cause only reachable via a learned edge; departed owner with no clear successor (honest "no one active", escalate to team).
- Scenarios are fixtures applied to twin graphs (`<tenant>__eval_<id>`), seeded, run, scored, deleted; never the hero graphs.
- `python -m backend.agents.firefighter_eval` → per scenario: cause correct, path correct, false leads rejected, tool calls, grounding ok, paged an active person, wrong-action count. JSON results + docs/eval.md table. Fix the planner GENERICALLY until scores are honest-good; document any scenario it still fails and why.
- API `GET /api/eval/latest`.

## B. Hypotheses and decision trace (explainability)
- The Investigator keeps explicit hypotheses: each with supporting evidence, contradicting evidence (ids + receipts), status (open/confirmed/rejected) and reason. Every step records "why this tool" (the rule or reasoning that chose it).
- Final report adds: hypotheses considered, rejected ones with the evidence that killed them, and a confidence breakdown (what raised or lowered it).
- Stored as optional properties on Step/Incident (schema changelog). Live planner prompt asks for the same structure (fake-client test).

## C. Alert storm: multi-alert correlation with graph algorithms (hero moment)
- New read tools (registry, receipts, docs/cypher.md): `correlate_alerts(services[])` = common upstream dependencies via variable-length paths + algo.SPpaths, ranked; `failure_domains` = algo.CDLP community detection over DEPENDS_ON; `connected_impact` = algo.WCC on the alerting subgraph (one incident or several?); `blast_tiers` = BFS levels from a service; optionally harmonic centrality. Use only algorithms FalkorDB really supports; verify each against the running DB first and note results.
- Story beat "Alert storm": 5+ alerts fire at once on one tenant. The agent decides from the graph: they share one upstream → ONE incident, ONE page to the right active owner, other pages suppressed with the reason; a 6th unrelated alert is correctly kept separate. Fixture-driven, generic code.
- Golden replay for it; numbers in /api/compare-style JSON.

## D. Actions with a safety check and an approval gate ("decide and act")
- An action plan: each action (rollback deploy X, page P, open ticket, flag stale doc, suppress duplicate page) carries its graph justification (path, ids, receipts).
- Before proposing a rollback, a graph safety check: what else depends on the changed service / later deploys, blast radius of the rollback itself; risky → recommend "hold, page owner" instead.
- Execution needs the access code (existing gate), is simulated (writes existing labels, origin:'agent'), idempotent, and followed by a verification step that re-runs the checks and reports whether the signal cleared.

## E. MCP, for real
- Our own agents can select tools THROUGH MCP: a `--tools-via mcp` mode where the agent loop gets tool list + calls from an MCP client session to our server (same results/receipts as direct). Tests prove parity.
- Streamable HTTP MCP endpoint mounted in the FastAPI app (`/mcp`), read-only tools, tenant per connection, rate-limited; stdio stays.
- MCP prompts/resources (e.g. "investigate alert on <service>", schema resource).
- A scripted MCP client session (no LLM) saved as docs/mcp-transcript.md showing tool discovery → selection → receipts. Update docs/mcp.md.

## F. Scale proof (the graph is load-bearing)
- Generated `scale_demo` tenant (~2,000 services, ~10k DEPENDS_ON, people/teams/deploys), deterministic generator, same schema.
- Every receipt gets query time in ms. docs/benchmarks.md: each tool + algorithm at hero size vs scale size (median of N runs, machine noted). Explorer can open it (with caps).

## G. UI (everything above must be visible)
- Firefighter playground: pick tenant + any service + symptom (or a scenario from the library) → watch the run (replay for visitors, fresh mock with code).
- Alert storm beat in Story view: many red alerts collapse into one incident; suppressed pages shown with reasons.
- Hypothesis board in the receipt drawer (open/confirmed/rejected, evidence links); "why this tool" on each step card.
- Action plan panel with justification, safety-check result, Approve (code-gated), verification result.
- Eval scoreboard page + benchmark panel. Keep the fixed colour meanings (amber = agent-written, red = alert, blue = current path).
- Playwright specs for every new view; screenshots in both themes at 1440×900 + 1920×1080 hero; LOOK at every screenshot and do up to 3 polish rounds; no console errors.

## H. Live-readiness (no calls)
LLMPlanner + prompts know the new tools/structures; fake-client tests; docs/live-mode.md gets a one-command live validation script for later with an estimated Haiku cost.

## I. Docs
README rewritten Track 1 first: the five official focus bullets each checked off with where it shows in the product (keep Tracks 2/3 sections). docs/demo-script.md v2: a 2:45 Track-1-first cut (alert storm, hypotheses, action + safety check, MCP, eval). docs/explain.md: every new query/algorithm explained in plain words + likely judge questions with answers. docs/blog-draft.md (draft for Jaya to rewrite in her voice). Keep video/URL TODOs.

## J. Independent review + final verification
A reviewer agent that has not seen the work audits: correctness, story leaks, grounding, gate bypasses, tenant isolation, schema rule, flaky tests. Fix findings (each its own commit). Final: fresh-clone setup → pytest, vitest, e2e, verify, both evals, docker build, all green; numbers in progress.md.

## Priority / cut order
0 → A → C → B → G (for A/B/C) → D → E → I → F → H → J. Cut first: F, then H, then the HTTP part of E. A, B, C and their UI are must-haves.

## Morning list
End progress.md with "Look at these first": the screenshots to open, the commands to run (`scripts/ui.sh`, `scripts/e2e.sh`, `python -m backend.agents.firefighter_eval`), decisions needing Jaya, known gaps, and the revert map.


## QUALITY MODE (overrides the cut order: usage is not a constraint, quality is)
- Do NOT cut any part. Do every part 0–J fully. If time remains after J, run another round of the judge panel below and act on it.
- Before each part: a short design pass with 2–3 independent agents proposing approaches; pick the best, record why in progress.md.
- Before EVERY commit: an adversarial verifier agent that did not write the code checks it (correctness, edge cases, story leaks, grounding, schema rule, tenant isolation) and runs the relevant tests. Fix until it passes. Never commit on "probably fine".
- Every new tool/algorithm: verified against the running FalkorDB with real output pasted into docs/cypher.md; no claimed feature that was not actually run.
- Flake check: run pytest and Playwright 3× in a row at the end of each part; all 3 must be green.
- JUDGE PANEL (after G, after I, and at the very end): 5 independent agents act as hackathon judges for "Track 1: Agents That Act on Connected Data". Each opens the screenshots, reads the README and the demo script, runs scripts/ui.sh flows via Playwright, and scores 1–10 on each official bullet (multi-hop reasoning, graph queries and algorithms as agent tools, tool selection through MCP, actions based on what the graph shows, explainable results) plus "wow in a 2:45 video" and "does the graph clearly drive the decisions". They list the 3 weakest things. Save scores to docs/judge-panel.md, fix the weakest items (each its own commit), re-score. Target: every bullet ≥ 9 with concrete evidence.
- Video-first acceptance: every hero beat (alert storm, false lead rejected, hypothesis board, rollback safety check + approve, MCP tool selection, eval scoreboard) must be understandable with the sound off: clear on-screen labels, no clipped text, readable at 1920×1080.
- Honesty bar: README and UI must never overstate (mock vs live labelled; no live claims). Judges reward credibility.


## SIGNATURE PROOF: "the graph is the brain" (add to Part A and the UI)
- Baseline agents on the SAME scenarios, same planner/loop, same report format:
  (1) "No graph": only full-text search over the same docs/tickets/chats (no traversals, no algorithms).
  (2) "Graph, no algorithms": traversals allowed, algo.* tools removed.
  (3) "Full Incident Brain".
- docs/eval.md and the scoreboard page show all three columns per scenario: cause correct, false lead rejected, right person paged, tool calls, wrong actions. Expected story: (1) fails on multi-hop and false-lead cases, (2) misses hub/chokepoint/storm cases, (3) wins. Report the real numbers honestly, even where the baseline does OK.
- Ablation: remove the learned DEPENDS_ON edge and rerun Session 2 → cause not found (already shown; include it in the same table).
- UI: a "Why a graph?" panel with this comparison, one click from the Story view; one beat in demo-script v2.
- Each baseline is its own module + commit; zero story knowledge; same grounding checks.
