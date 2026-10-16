# Explain it to a judge

Plain-language explanations of each piece of work, newest first. Each section: what it is, why it is built that way,
and what to say if asked.

## 07B/07D: the web UI (demo console)
**How the UI gets its data.** The browser never talks to FalkorDB. It asks the API for: the company list and the story
(`/api/meta`, `/api/story`), a recorded run as a list of step events (`/api/replay/<name>`), the nodes and edges that
run touches (`/api/run-graph/<run>`), the before/after numbers (`/api/compare/latest`), suggested questions and Brain
answers, and the Explorer graph. Every step event carries what the drawer and the graph need: the tool, a one-line
summary, the exact Cypher and parameters, a result preview, the ids to highlight, the sources it quoted, and what it
wrote (with `origin: agent`). Recorded runs and fresh runs produce the same event shape.

**How the graph stays still.** When the Story view opens, it fetches the run graphs of the whole story and computes
one layout (fcose force layout with a fixed random seed), then caches the positions. Playing a run only changes what
is visible and highlighted; nodes never move. A fresh run that touches a node the recording didn't is placed beside
its neighbours. Only the camera moves, to frame the current step.

**The learned edge.** When a step writes a `DEPENDS_ON` edge, the graph hides the real edge, animates a dashed amber
line from the source service to the target, then shows the real (dashed, amber, glowing) edge. Scrub back and it
disappears; play forward and it draws again.

**The access-code gate.** No code: everything works on recorded runs, the Brain answers but saves nothing, and the
server refuses every write with 403. With the code (kept in the browser tab only, sent as a header): the story
buttons start fresh mock runs that write to the graph. Browsers can't add headers to a live event stream, so the code
is checked when the run is created and the stream URL carries a random one-time token that expires in a minute.

**Likely judge questions**
- *"Is the replay real?"* It is the record of a real mock run, including a snapshot of the graph right after it.
  Enter the code and the same button runs it fresh; the before/after panel then says "from your fresh runs".
- *"Why mock and not the real model?"* Free, deterministic, and the same loop, tools and checks as live mode. Live
  mode exists behind the code, a key, a budget guard and a daily cap; it hasn't been run yet.
- *"What does amber mean?"* Only one thing: written by an agent. Red is the alerting service, blue the current step.
  Colour is never the only signal: agent nodes have a double border and an "AI ·" label, learned edges are dashed.
- *"How do you know the UI works?"* `scripts/e2e.sh`: 10 headless-browser tests (theme, the full story, the learned
  edge appearing at the right step, numbers matching the API, Brain, Explorer, the gate, fresh runs, zero console
  errors), plus screenshots in both themes that were reviewed and fixed in three rounds.
- *"Does the frontend know the story?"* No. No company ids, names, people or tickets in `frontend/`; button labels,
  alerts and questions all come from the API (`backend/demo.py` is the only story code).

## 07C: one container
**What:** a single Docker image that serves both the web page and the API on one port. On first start it fills an
empty database with the two demo companies, checks them, and plays the demo story once (free mock mode), so a fresh
deployment shows memory straight away. A restart never wipes anything.
**If asked "where is it hosted?":** it isn't yet; the image is host-agnostic and only needs a FalkorDB address
(`docs/deploy.md`). We tested it locally with Docker Compose, including the full browser test suite against it.

## 07A: the API the web UI reads
**What:** a handful of read endpoints that turn the graph and the recorded runs into what a browser can draw: the
story's buttons, every step of a run (with its Cypher, sources and what it wrote), the nodes and edges a run touches,
the before/after numbers, six suggested questions and an Explorer view with PageRank.
**Why recordings:** a judge without a code watches the exact recorded run (a "golden replay") so the demo is free and
identical every time. With the access code the same buttons start a fresh mock run that really writes to the graph.
**The gate:** anything that writes needs the code. Asking the Brain works for everyone, but without the code nothing
is saved; follow-up questions still work because the browser sends the earlier turns back.
**If asked "is the replay faked?":** it is the record of a real mock run, including the graph snapshot taken right
after it. `python -m backend.demo story --compare-no-memory --save-golden` regenerates all four.

## 06F: hardening
**What:** an independent reviewer agent went through the code looking for leaks of the demo story into agent logic,
unsafe queries, holes in grounding, missing write validation, tenant mix-ups, secrets and flaky tests.
**What it found and we fixed:** an agent could overwrite the company's recorded history of an old incident; an agent
could quote its own invented text as a "source"; a twice-rejected (ungrounded) answer was still passed on. Now
history is read-only, only the operator's words in an agent-written incident are quotable, and an ungrounded answer
ends the run with no answer at all. Tool descriptions no longer use the demo's ids as examples.
**If asked "how do you know it's not overfit to the demo?":** the agent logic only reads tool results; the second
company (Northwind) runs the same agents unchanged; story ids appear only in seed data, tests, evals and docs.

## 06E: README draft
**What:** the submission README: what it is, how to run it in 3 minutes, how it's built, the graph model, which
FalkorDB queries and algorithms carry the product, how memory works (with the before/after table), and one section per
hackathon track. Plus `docs/live-mode.md`, which explains how spending is capped.
**Still to fill in:** demo video, live URL, screenshots, and the official focus bullets for each track.

## 06D: the Brain eval (15 questions)
**What:** a fixed exam for Ask the Brain: 15 questions that each test one kind of company question (why did we
decide, who knows, who owns, what breaks, seen before, what did an agent session learn, industry pattern, follow-ups
with "that"/"it", a follow-up after a restart, someone else's conversation, and a question with no answer), plus 3
for the second company. Each answer is graded by machine: required citations, people, quoted words, and that the
answer is grounded.
**What it caught:** the Brain used to answer a question it had no data for (Kubernetes policy) by quoting an
unrelated Kafka ticket, because it fell back to a weak keyword match. Now a source must match all the specific terms,
otherwise it says "I don't know".
**Score:** 15/15 for Kestrel Pay (fresh and after the demo story), 3/3 for Northwind Health, in mock mode.

## 06C: public postmortems (industry pattern layer)
**What:** 21 real outage write-ups from companies like Cloudflare, AWS, GitHub and Slack, stored in every company's
graph as `PublicPostmortem` nodes tagged with root causes (cache stampede, bad config push, retry storm, DNS/BGP,
hidden dependency, database failover…). The text is a short summary in our own words plus the link.
**How it's used:** an incident's root cause is a node; the same node is attached to matching public postmortems. So
"has anyone else had this?" is a two-hop graph query (`industry_matches`). When an incident is resolved, the agent
links it to the best 1–2 matches (`SIMILAR_TO`), and the incident report says e.g. "Matches known industry pattern:
Slack — Slack's Incident on 2-22-22 (link)".
**If asked "is this scraped?":** no. Each page was read and summarised by hand-checked facts, with no copied
sentences, and pages we couldn't verify were left out. A root cause with no public match simply returns nothing.

## 06B: memory-first recall
**What:** a new tool, `memory_recall`, that the Investigator calls before anything else. It asks the graph "what have
earlier agent sessions learned about this service and the things it calls?": dependencies they discovered (with the
quote that proved it), incidents they resolved (who fixed it, how, and the newest runbook) and a short list of
suspects.
**How it makes Session 2 instant:** Session 1 learned "risk-rules calls config-service". When payouts-service (which
also calls config-service) alerts, recall says "suspect: risk-rules, it shares config-service with you, and it caused
INC-2026-032 last time". The Investigator then checks only that one thing: did risk-rules ship recently? It did
(v2.8.1, 5 minutes ago), so the cause is set on its 3rd tool call, with "Seen before: INC-2026-032, fixed by Priya
Nair (…), see Runbook v2 step 2".
**Why it's honest:** memory is a hypothesis, not an answer. It is always verified against live data (a recent
deploy) before the cause is set, and if the suspect didn't change, the agent falls back to the full scan. Session 1
recalls nothing because only agent-written memory counts; seeded history is still searched by `past_incidents`.
Without Session 1 (the contrast run), Session 2 can't find the cause at all.
**Numbers:** Investigator tool calls until cause: Session 1 = 8, Session 2 = 3; Session 2 without memory = not found.

## 06A: setup that works on a fresh Mac
**What:** `scripts/setup.sh` gets a new machine from a fresh clone to a seeded, verified graph in one command, and
`scripts/demo.sh` plays the whole story.
**Why:** macOS ships Python 3.9 as `python3` and often has no `python`; our code needs 3.10+. The script looks for
the newest Python 3.10+ it can find, builds `.venv` with it, installs pinned dependencies, makes sure Docker and the
`falkordb` container are up, then seeds and verifies both companies. Re-running it is safe.
**If asked:** "Everything runs in mock mode by default, so a judge can clone, run two scripts and see the full demo
without an API key or any cost."


## 08: Track 1 additions (plain words)

**Every recent change is a lead (`recent_changes`).** A flat list of every deploy in the last two hours, newest first.
It deliberately knows nothing about dependencies: a naive responder blames the newest deploy; our agent makes each one a
hypothesis and lets the graph keep or reject it.

**Keeping or rejecting a lead.** `recent_changes_downstream` follows `DEPENDS_ON` outward from the alerting service
(0–6 hops: the service itself counts) and keeps services with a recent deploy: those are on the call path, nearest
first. `shared_dependency_changes` finds services that are *not* on the path but call something the alerting service
also calls (a noisy neighbour). In a real company everything calls the same few hubs, so a neighbour only counts when
the shared service is narrow (fewer than 4 services reach it) or something corroborates it: a learned dependency on the
path, the shared service is alerting too, or the alert names it. Everything else is rejected, with that reason.

**Alert storms.** `correlate_alerts` runs `algo.BFS` from every alerting service in one query and counts, for each
dependency, how many alerting services reach it; the top one (more alerts covered, alerting before silent, fewer hops)
is the shared root. `connected_impact` copies the alerting services and everything they call into a scratch graph and
runs `algo.WCC` there: alerts in different components share no dependency, so they can't have one cause. If the root
explains at least 3 alerts and more than any single change does, they are ONE incident; one page goes to the root's
owner and every other alert's page is suppressed with its path as the reason. `blast_tiers` (`algo.SSpaths` incoming)
lists the root's callers tier by tier, alerting vs silent (notify the silent ones, don't page them).

**Actions and the safety check.** The plan per incident: roll back (or hold), page (or escalate to the team when nobody
active owns the service), suppress pages, notify, open a ticket, flag stale docs. `rollback_safety` reads three things
around the deploy: later deploys to the same service (a rollback takes them along), words in the change that mean data
was touched (migration, schema, drop, rebuild…: rolling back code won't undo it), and how many services depend on it.
Risky → hold and page the owner. Approve (access code) executes in simulation on the run's own copy of the company and
re-runs `recent_changes_downstream`: "cleared" only if the newest change on the culprit is now the rollback.

**Why this tool, hypotheses, confidence.** Every model turn starts with `why <tool>: <reason>` lines; the loop attaches
each reason to its step. The report's hypothesis board lists every lead with evidence for and against (node ids), a
status and the reason; the confidence breakdown says what raised or lowered it.

**MCP.** The same registry is served over MCP (stdio, and streamable HTTP at `/mcp/<company>/`). `--tools-via mcp` makes
our own Firefighter discover and call its tools through an MCP client session; a test checks the run is identical.

### Likely judge questions (Track 1)
- **"Isn't this a rules engine with an LLM costume?"** In mock mode the planner IS deterministic rules (so the demo and
  eval are free and repeatable), and we say so everywhere. The live planner is Claude with the same tools, prompt and
  grounding checks; it has not been run yet (no key during the build). What we show is that the *graph tools* make
  the decision possible: the same planner without the graph fails.
- **"Do the algorithms matter, or is it all traversals?"** Honestly: on single alerts plain traversals tie
  (docs/eval.md shows it from the data). The algorithms change the outcome in alert storms (correlation over many
  alerts at once) and answer questions in one call (PageRank, communities, components). At 2,000 services both stay
  fast (docs/benchmarks.md).
- **"Is the eval rigged?"** Expected answers come from an independent oracle in plain Python; 6 held-out scenarios
  were written by an agent that never saw the planner and run once (6/6); 50 scenarios are generated from seeds; the
  baselines are the same planner with fewer tools, and their wins are reported too.
- **"Does it really act?"** It writes incidents, pages, tickets, stale flags and a rollback deploy into the graph, but
  only after approval, only on a copy of the company, and in simulation (no real pager or CI). Verification then
  re-checks the graph and says plainly when a page cannot clear a saturation.
- **"What did you find out about FalkorDB?"** Whole-graph WCC is one component in a hub-heavy graph (hence the
  projection); a MATCH after an aggregation returns nothing; and a wide aggregation row with NULLs crashed FalkorDB
  6.0.2 (minimal repro in docs/progress.md).
