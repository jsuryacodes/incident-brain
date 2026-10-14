# Explain it to a judge

Plain-language explanations of each piece of work, newest first. Each section: what it is, why it is built that way,
and what to say if asked.

## 06A: setup that works on a fresh Mac
**What:** `scripts/setup.sh` gets a new machine from a fresh clone to a seeded, verified graph in one command, and
`scripts/demo.sh` plays the whole story.
**Why:** macOS ships Python 3.9 as `python3` and often has no `python`; our code needs 3.10+. The script looks for
the newest Python 3.10+ it can find, builds `.venv` with it, installs pinned dependencies, makes sure Docker and the
`falkordb` container are up, then seeds and verifies both companies. Re-running it is safe.
**If asked:** "Everything runs in mock mode by default, so a judge can clone, run two scripts and see the full demo
without an API key or any cost."
