# Explain it to a judge

Plain-language explanations of each piece of work, newest first. Each section: what it is, why it is built that way,
and what to say if asked.

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
