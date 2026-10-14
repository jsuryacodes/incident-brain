# Progress

**Current task: `docs/prompts/07-ui.md`** (the demo console: parts 0, A–E, unattended, mock only, zero live API calls).
Resume line: "Read docs/prompts/07-ui.md and docs/progress.md and continue."

| Part | Status | Commit |
|---|---|---|
| 0 Preflight + demo script | DONE | 07-0 |
| A API additions | TODO | |
| B Frontend (themes, shell, Story, Brain, Explorer, polish) | TODO | |
| C Deploy-ready container | TODO | |
| D Headless-browser self-check | TODO | |
| E Docs | TODO | |

**Total live API spend: $0.00** (0 live calls, no key).

## 07-0 — Preflight + demo script
**Status:** DONE
- `node -v` → **v22.23.2** (npm 10.9.8, Homebrew present). Node ≥ 18, so the **Vite path** (React + Vite + TS), not the no-build fallback.
- Docker up, `falkordb` container running; `scripts/setup.sh` clean (kestrel_pay 14/14, northwind_health 8/8); `pytest -q` → 105 passed before any change.
- `docs/demo-script.md`: the 2:45 shot list (7 beats, screen / click / narrator / timestamp) plus the list of UI features the script needs.

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
