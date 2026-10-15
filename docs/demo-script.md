# Demo video: 2:45 shot list

Recorded in the web UI (`scripts/ui.sh`, http://localhost:8000) at 1920×1080, light theme, **replay mode** (no access
code), so every take is identical. Autoplay speed 1×. Mock mode for everything; Sonnet only if Jaya decides to record a
live take (see `docs/live-mode.md`).

Before recording: `scripts/setup.sh`, then `scripts/ui.sh`. Hard-refresh the page. Theme: Light. View: Story.
Tenant: Kestrel Pay.

| # | Time | Screen | Click / do | Narrator (1–2 lines) |
|---|---|---|---|---|
| 1 | 0:00–0:10 | Story view, empty graph with the hero alert card | nothing (title card) | "An alert fires at 2 a.m. A team of three agents finds the cause, shows every query it ran, and remembers what it learned." |
| 2a | 0:10–0:25 | Story view | **Fire alert** (Session 1). Triage lane fills: find_service → blast_radius → PageRank → past incidents → open_incident (amber chip) | "Triage reads the company graph: who calls payments-api, how critical it is by PageRank, and what broke here before. It opens the incident in the graph." |
| 2b | 0:25–0:40 | Story view, Investigator lane, path lights up blue hop by hop | let it play; at `recent_changes_downstream` the path payments-api → fraud-scoring → risk-rules is thick blue | "The Investigator walks the dependency graph downstream with a variable-length path query and finds a risk-rules deploy 40 minutes ago." |
| 2c | 0:40–0:52 | Receipt drawer on `decisions_about` | press **space** to pause; point at the Cypher and the source card | "Every step is a receipt: the exact Cypher, the parameters, and the sources. Here: a buried decision in a chat thread, 'RULES_CACHE_TTL stays at 300s minimum'. The deploy set it to 5 seconds." |
| 2d | 0:52–1:02 | Drawer on `who_to_call` | **space** to resume | "The maintainer, Arjun, left the company. The graph computes who actually knows this code: call Priya instead." |
| 2e | 1:02–1:15 | Graph: dashed amber edge draws from risk-rules to config-service | let `record_learned_dependency` play (the money shot) | "And it learns. A chat message says risk-rules polls config-service on every cache miss. That dependency wasn't in the catalog. Now it is, in amber, with the quote as its source." |
| 2f | 1:15–1:22 | Final report card (Session 1) | none | "The Communicator pages Priya, opens a ticket and flags the stale README." |
| 3 | 1:22–1:35 | Story view, Resolve | **Resolve** at 2×. Resolution and Runbook v2 appear in amber, linked by amber edges to two public postmortems | "Priya fixes it. Resolving writes the fix, a better runbook, and links to two real public postmortems with the same root cause." |
| 4 | 1:35–1:55 | Story view, Session 2 (payouts-service) | **Fire Session 2** at 2×. Investigator lane: memory_recall → shared_dependency_changes → update_incident (pause with space) | "A different service alerts the next day. The Investigator asks memory first: the learned edge says payouts-service shares config-service with risk-rules. One check, and the cause is named on its third tool call. 'Seen before: INC-2026-032, fixed by Priya.'" |
| 5 | 1:55–2:12 | Story view → before/after panel | **Compare without memory**, then the before/after panel slides in | "Same alert, same agents, but without Session 1's memory: the cause is never found. Memory changed the graph, not a prompt." |
| 6 | 2:12–2:30 | Ask the Brain | Suggested question "Why did we decide …" → answer with a source card; then type "Who should I call about it?" | "Anyone can ask the company brain. Every answer quotes its source, and follow-ups work because the conversation lives in the graph too." |
| 7 | 2:30–2:45 | Explorer, switch tenant to the second company; About dialog | tenant switcher → Northwind Health; "Agent memory only" is empty; open About | "Each company is its own FalkorDB graph: Northwind has zero agent memory from Kestrel. Agents that act on connected data, shared memory and coordination, and a company brain: three tracks, one graph." |

## On-screen timing targets (measured from the recorded runs)
- Replay lengths at 1×: Session 1 = 24 steps, 51 s · Resolve = 12 steps, 26 s · Session 2 = 21 steps, 44 s ·
  No-memory = 15 steps, 31 s. That is 2:32 of playback, so not everything can run at 1×.
- Plan: Session 1 at **1×** (beats 2a–2f, with the two pauses); Resolve at **2×** (13 s); Session 2 at **2×** and pause
  (space) on `update_incident`, the Investigator's 3rd call; Compare at **2×** or drag the scrubber to the end (the
  before/after panel opens by itself at the end).
- Keep the receipt drawer open throughout; the viewer should always see Cypher.
- The learned edge draws in over about 1.3 s and its step stays on screen 3.6 s at 1×; pause on it for a beat.
- Everything is deterministic: a re-take plays identically. Restart (↺) clears the story.

## What the UI has for this script (all built in 07; checked by `scripts/e2e.sh`)
- Story buttons with labels from `/api/story`: Fire alert → Resolve → Fire Session 2 → Compare without memory.
- Space / ← / → keyboard control, deterministic autoplay, 0.5× / 1× / 2×.
- Receipt drawer with Cypher, params, result and source cards.
- Final report card with "who to call" (departed maintainer flagged), decision excerpt, "Seen before…", industry match.
- Before/after panel with numbers from `/api/compare/latest`.
- Brain suggested questions + follow-up; Explorer tenant switch with an empty-memory message.
