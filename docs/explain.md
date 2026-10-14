# Explain it to a judge

Plain-language explanations of each piece of work, newest first. Each section: what it is, why it is built that way,
and what to say if asked.

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
