# CLAUDE.md — standing rules for Claude Code in this repo

Project: **Incident Brain** — FalkorDB hackathon entry (deadline 18 Oct 2026, 11:59 PM IST). Solo developer: Jaya.

## Read first
- `docs/schema.md` is the LOCKED graph model and the source of truth. Never add/rename/remove labels, edge types or properties without asking. If FalkorDB syntax in it turns out wrong, fix the code, then tell me so the doc can be corrected.
- Task specs live in `docs/prompts/NN-*.md`. Do exactly what the current spec says; ask only if blocked or if the schema seems wrong.

## Finishing every task (always, without being asked)
1. Run the task's checks (at minimum `python -m seed.verify --graph kestrel_pay` if the seed or graph code changed). Don't commit failing work.
2. Append an entry to `docs/ai-log.md`: date, step, what you built, what I should double-check.
3. `git status` and review what's staged. Never commit `.env`, secrets, `.venv/`, `__pycache__/`, `.DS_Store`.
4. Commit with a clear message, e.g. `Step 3: core graph tools`.
5. **Push to GitHub: `git push origin main`.** If the push fails (auth, network, rejected), tell me the exact error — don't force-push, don't rewrite history.
6. End with a plain-language explanation (under ~400 words) of what was built and the key queries/decisions, so I can defend them to judges.

## Tech rules
- Python ≥ 3.10, venv in `.venv`, deps in `requirements.txt`. FalkorDB on `localhost:6379` (Docker container `falkordb`), Browser at http://localhost:3000.
- FalkorDB is not Neo4j: no APOC or Neo4j-only procedures. Full-text index: `CREATE FULLTEXT INDEX FOR (n:Label) ON (n.a, n.b)`.
- Cypher is always parameterised; only schema-validated label/type names may be interpolated.
- Writes use `MERGE` on `id`. Times are integer epoch seconds.
- Product LLM calls (later steps) go through ONE wrapper, have `max_tokens` set, and support a mock mode. Never call the Anthropic API during seeding or tests unless the spec says so. API keys only in `.env`.
