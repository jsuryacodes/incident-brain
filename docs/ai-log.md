# AI assistance log (for the hackathon disclosure)

Running log of where AI tools helped. Tools: Claude (claude.ai, Opus 5.5) for planning/design; Claude Code (Sonnet 5.5) for implementation.

## 2026-10-15 — Step 1: graph schema
- Designed with Claude in claude.ai: node labels, edges, provenance pattern (SOURCED_FROM), learned DEPENDS_ON edge for memory, indexes, planted-story fixtures.
- My decisions: hidden dependency absent from seed and learned at runtime; postmortems copied per tenant; no embeddings (full-text + traversal).
- Output: `docs/schema.md` (locked v1), `docs/prompts/02-seed.md` (task spec for Claude Code).

## 2026-10-15 — Step 2: Kestrel Pay seed + verify
- Claude Code (Sonnet 5.5) wrote `seed/` (loader, schema copy, verify) and all Kestrel Pay content (27 services, 20 people, 37 deploys, docs, chats, tickets, incidents) from `docs/prompts/02-seed.md`. No LLM/API calls at runtime.
- Loader validates everything before touching the DB (prefixes, required/unknown props, enums, time props are ints, edge endpoints and edge-type rules); writes with UNWIND + MERGE. `seed/verify.py` proves the 13 story checks.
- Double-check: (1) FalkorDB 4.x rejects the multi-arg `db.idx.fulltext.createNodeIndex` shown in schema.md §6; the loader uses `CREATE FULLTEXT INDEX FOR (n:Label) ON (n.a, n.b)` (same index) — consider updating §6 wording. (2) Fictional prose and chat transcripts: read `chat:risk-eng-config-load` yourself, it is the demo's key evidence. (3) Counts above the prompt's targets: Deploy 37 (33 in last 30 days + 4 older incident causes), Ticket 17 (11 + 6 postmortems). (4) Chat/doc dates are generated from the relative clock, so they shift on re-seed. (5) Extras beyond the prompt: runbooks also have SOURCED_FROM (design rule 2); Priya WORKED_ON merchant-onboarding (she fixed INC-2026-012).
