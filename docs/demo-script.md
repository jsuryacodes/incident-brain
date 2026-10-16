# Demo video v2 (Track 1 first): 2:45 shot list

Recorded in the web UI (`scripts/ui.sh`, http://localhost:8000) at 1920×1080, light theme, **replay mode** (no access
code), so every take is identical. Mock mode for everything (say so on screen once: the badge reads "Replay"). The
on-screen labels carry the story with the sound off: the outcome card, the step cards' "why:" lines, the Hypotheses
and Actions tabs.

Before recording: `scripts/setup.sh`, `scripts/ui.sh`, hard-refresh. Company: Kestrel Pay. Speed 1×.

| # | Time | Screen | Click / do | Narrator (1–2 lines) |
|---|---|---|---|---|
| 1 | 0:00–0:12 | Story view, title card | nothing, then **Alert storm** | "Six alerts fire at once. A naive pager wakes six people for six incidents. Our agent asks the company's graph first." |
| 2 | 0:12–0:38 | Firefighter view, storm playing | let it play to `correlate_alerts` / `connected_impact`; config-service gets the SHARED ROOT ring | "It lists every recent change as a lead, then uses FalkorDB's algorithms: BFS from every alert finds the one dependency five of them share; WCC on the alerting subgraph proves the sixth can't share its cause." |
| 3 | 0:38–0:55 | end of the storm: outcome card "6 alerts → 2 incidents · 2 pages · 5 suppressed"; Actions tab | scroll the suppressed pages | "One page to config-service's owner instead of five, each suppressed page with the dependency path that justifies it. The sixth alert is its own incident, with its own change." |
| 4 | 0:55–1:15 | Firefighter, scenario "false lead" at the end, **Hypotheses** tab | point at the struck-through hypotheses | "Explainable: every lead is a hypothesis. Two fresher deploys are rejected with the evidence that killed them: one isn't on the call path at all, the other only shares hubs that everything shares." |
| 5 | 1:15–1:32 | step list: the "why:" lines; Receipt tab with Cypher + ms | click one step | "Every step says why the agent chose that tool, and shows the exact Cypher it ran, with timing. The agent never writes Cypher; it picks from 22 fixed graph tools." |
| 6 | 1:32–1:50 | Northwind, scenario "neighbour and an unrelated fresher deploy" at the end, **Actions** tab: HOLD + red safety check | point at "Safety check: risky" | "Before acting it checks the graph: this change rebuilt a table, so rolling the code back won't undo it. The plan says hold and page the owner. Approval needs the access code; execution is simulated and verified." |
| 7 | 1:50–2:08 | terminal split or `docs/mcp-transcript.md` | show `--tools-via mcp` output line and the transcript's tool list | "The same tools over MCP, stdio or HTTP. Our own agent can discover and call them through an MCP session, with identical results." |
| 8 | 2:08–2:28 | **Eval** view, "Why a graph?" bars + scoreboard | scroll to the scoreboard | "Same agent, three tool sets. With the graph: 15 of 15 scenarios, zero wrong actions, 6 of 6 on held-out cases. Without it: word matching takes the bait and pages the wrong people." |
| 9 | 2:28–2:45 | Story view: the learned dependency drawing in (Session 1 step 15), then the before/after panel | **Fire alert** at 2×, jump to the end | "And it remembers: a dependency it learned from a chat thread lets the next incident be solved in three steps instead of eight. Incident Brain, on FalkorDB." |

Timings to measure on the first take; replays are deterministic, so they hold.

---

# Earlier: v1 (Story first)

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
