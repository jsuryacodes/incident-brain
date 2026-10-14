# Claude Code task — Build step 2: seed the Kestrel Pay graph

You are working in the `incident-brain` repo (hackathon project, Python backend, FalkorDB).
**Read `docs/schema.md` fully before writing any code. It is LOCKED and is the source of truth.**
Do not add, rename or remove labels, edge types or properties. If you believe the schema must change, STOP and ask me.

## Goal
A repeatable Python seed that loads a synthetic company ("Kestrel Pay") into FalkorDB graph `kestrel_pay`,
with the planted stories from schema.md §7 wired exactly, plus a verify script that proves the stories hold.
No LLM/API calls anywhere in this step. You (Claude Code) write the content directly into the data files.

## Environment
- FalkorDB runs locally in Docker (`docker start falkordb`), Redis protocol on `localhost:6379`, Browser UI at http://localhost:3000.
- Python ≥ 3.10. Use `uv` if installed, else `python3 -m venv .venv` + pip. Add `requirements.txt` (`falkordb`, `python-dotenv`).
- Connection from env: `FALKORDB_HOST` (default localhost), `FALKORDB_PORT` (default 6379). Create `.env.example`; make sure `.env` is git-ignored.
- Use the official `falkordb` Python client (`FalkorDB(host, port).select_graph(name)`, `graph.query(q, params)`). FalkorDB is NOT Neo4j: no APOC, no Neo4j-only procedures.

## Files to create
```
seed/
  __init__.py
  schema.py        # machine-readable copy of schema.md: label→id prefix, required props per label,
                   # EDGE_RULES: edge type → set of allowed (from_label, to_label) pairs
  timeutil.py      # NOW (epoch secs, settable) + ago(days=0, hours=0, minutes=0) -> int
  load.py          # python -m seed.load --graph kestrel_pay [--reset] [--now EPOCH]
  verify.py        # python -m seed.verify --graph kestrel_pay
  data/kestrel_pay/
    __init__.py    # exposes NODES (list) and EDGES (list) aggregated from the modules below
    org.py         # teams, people, MEMBER_OF, OWNS, MAINTAINS, WORKED_ON
    services.py    # services, DEPENDS_ON
    deploys.py     # deploys, DEPLOYED, CHANGED, FOR_TICKET
    knowledge.py   # docs, tickets, chat threads, decisions + their edges
    incidents.py   # root causes, past incidents, resolutions, runbooks + their edges
```
Data format:
- Node = dict: `{"label": "Service", "id": "svc:risk-rules", ...props}`. Loader adds `origin='seed'` and `created_at` if missing.
- Edge = tuple: `(from_id, "TYPE", to_id, {props})`. Labels are inferred from id prefixes.
- Times always via `ago(...)` so the data is relative to NOW. `load.py` must call `timeutil.set_now()` BEFORE importing the data package (use importlib) so `--now` works.

## Loader requirements (`seed/load.py`)
1. Validate everything before touching the DB, and fail loudly with a clear message on: unknown id prefix, label/prefix mismatch, duplicate id, missing required prop, edge endpoint id that doesn't exist, edge (from_label, type, to_label) not allowed by EDGE_RULES, any time prop that isn't an int.
2. `--reset` deletes the graph first (ignore error if it doesn't exist).
3. Create all indexes from schema.md §6 (range index on `id` for EVERY label incl. agent-only ones, extra range indexes, full-text indexes). Ignore "already exists" errors. Try unique constraints on `id`; if not clean within a reasonable effort, skip with a printed note.
4. Write nodes in batches: one parameterised `UNWIND $rows AS row MERGE (n:<Label> {id: row.id}) SET n += row` per label. Edges grouped by (from_label, type, to_label): `UNWIND $rows AS row MATCH (a:<From> {id: row.from}), (b:<To> {id: row.to}) MERGE (a)-[r:<TYPE>]->(b) SET r += row.props`. Labels/types may be interpolated ONLY after being checked against schema.py; values always as parameters.
5. Print a summary: count per label and per edge type, and seconds taken.

## Content to write (sizes are targets, not exact)
- **4 teams:** `team:payments-core`, `team:risk-fraud`, `team:platform`, `team:merchant-exp`.
- **27 services, names/teams/tiers fixed:**
  - payments-core: payments-api(1), ledger-service(1), card-processor-adapter(1), bank-connector(1), payouts-service(1), reconciliation-job(2), fx-rates-service(2), ledger-db(1)
  - risk-fraud: fraud-scoring(1), risk-rules(1), rules-store-db(1), kyc-service(2), sanctions-screening(2)
  - platform: api-gateway(1), auth-service(1), config-service(1), config-db(1), kafka-events(1), feature-flags(2), audit-log(2)
  - merchant-exp: web-checkout(1), merchant-dashboard(2), merchant-onboarding(2), notifications-service(2), email-sender(3), webhook-dispatcher(2), reporting-service(3)
  - ids are `svc:<name>`; write a one-line realistic description + language for each; `repo_url` like `https://git.kestrelpay.example/<name>`.
- **~40 declared DEPENDS_ON edges** (`source:'declared'`, sensible `kind`). MUST include:
  web-checkout→api-gateway, api-gateway→auth-service, api-gateway→payments-api,
  payments-api→fraud-scoring, payments-api→ledger-service, payments-api→card-processor-adapter, payments-api→config-service, payments-api→kafka-events,
  fraud-scoring→risk-rules, risk-rules→rules-store-db,
  payouts-service→config-service, payouts-service→bank-connector, payouts-service→ledger-service,
  merchant-onboarding→config-service, merchant-onboarding→kyc-service, feature-flags→config-service, config-service→config-db, ledger-service→ledger-db.
  Make config-service a clear hub (many callers). HARD CONSTRAINTS: risk-rules has NO other outgoing DEPENDS_ON besides rules-store-db; NO `risk-rules→config-service` edge; rules-store-db has no outgoing edges and is reachable only via risk-rules; payouts-service must not reach rules-store-db or risk-rules within 3 hops.
- **~20 people** (fictional, diverse names, emails `@kestrelpay.example`), every person MEMBER_OF one team, plus every service has exactly one MAINTAINS and 1–4 WORKED_ON edges. Fixtures:
  - `per:priya-nair`: Senior Engineer, payments-core, active. WORKED_ON risk-rules {commits:23, last_at: ago(days=40)} and several payments services. She is the cross-team bridge.
  - `per:arjun-mehta`: Staff Engineer, risk-fraud, status 'left', left_at ago(days=95). MAINTAINS risk-rules and fraud-scoring. WORKED_ON risk-rules {commits:180, last_at: ago(days=100)}.
  - `per:leo-park`: Engineer, risk-fraud, joined_at ago(days=60). WORKED_ON risk-rules {commits:3, last_at: ago(days=1)}.
  - `per:dana-okafor`: Engineering Manager, risk-fraud. WORKED_ON risk-rules {commits:2}.
  - Add one more 'left' person somewhere unrelated (realism). Among ACTIVE people, Priya must have the most commits on risk-rules.
- **~30 deploys** over the last 30 days across many services (`dep:<service>-v<version>`), each with DEPLOYED + CHANGED. Fixtures:
  - `dep:risk-rules-v2.8.0`: ts ago(minutes=40), by Leo, summary "RISK-412: lower RULES_CACHE_TTL 300s -> 5s so rule edits apply faster", FOR_TICKET `tkt:RISK-412`.
  - `dep:email-sender-v1.14.2`: ts ago(minutes=60), harmless (decoy).
  - `dep:risk-rules-v2.3.0`: ts ago(days=455, hours=3), by Arjun, "lower RULES_CACHE_TTL to 10s" (the old cause of inc:2025-031).
  - Every OTHER deploy is at least 6 hours old.
- **~12 docs** (80–250 words each, realistic engineering prose): onboarding guide for Payments Core, architecture overview, service READMEs, on-call guide, etc. Fixture `doc:risk-rules-readme`: AUTHORED by Arjun, updated_at ago(days=600), names Arjun as owner/contact, lists only rules-store-db as dependency (no config-service), DESCRIBES risk-rules, MENTIONS Arjun.
- **~15 tickets** (bugs, tasks, postmortems). Fixture `tkt:RISK-412` (key "RISK-412"): by Leo, created ago(days=3), status 'done', "Rule edits take up to 5 minutes to apply — reduce rules cache TTL", ABOUT + MENTIONS risk-rules. Each seeded past incident has one `kind:'postmortem'` ticket.
- **~10 chat threads** (Slack-style text, lines like `[2025-08-14 11:02] Arjun Mehta: ...`, 6–15 lines). Fixture `chat:risk-eng-config-load`: channel '#risk-eng', ts ago(days=430), AUTHORED by Arjun, MENTIONS Priya, risk-rules, config-service, fraud-scoring, inc:2025-031. Must contain, in natural wording, these three points:
  1. Arjun: risk-rules doesn't read rules from its own DB on the hot path; on every cache miss it polls config-service's internal `/v1/rulesets` endpoint. It's not in the service catalog because it started as a "temporary" hack.
  2. Priya: so if the rules cache is cold, every fraud-scoring call can fan out to config-service?
  3. Arjun: "Decision: RULES_CACHE_TTL stays at 300s minimum. Below ~30s config-service falls over at checkout peak — that's what bit us in INC-2025-031."
  Other threads: ordinary engineering chatter, some containing the sources for the other decisions.
- **5 decisions**, each with AUTHORED, ABOUT and SOURCED_FROM {excerpt: exact quote from the source text}. Fixture `dec:rules-cache-ttl` "RULES_CACHE_TTL must stay ≥ 300s", decided_at ago(days=430), ABOUT risk-rules, SOURCED_FROM the chat thread with point 3 as excerpt. Others e.g. ledger idempotency window (from a ticket), webhook retry policy (from a doc), card-processor timeout budget (from a chat), etc.
- **5 root causes:** `rc:cache-ttl-thundering-herd` ("Cache TTL too low → thundering herd on a shared config store"), plus e.g. connection-pool exhaustion, expired TLS certificate, bad config push, retry storm. Generic industry-style names (they will later match public postmortems).
- **6 past incidents** (keys like INC-2025-031), each with AFFECTED, CAUSED_BY, HAS_ROOT_CAUSE, RESOLVED_BY → Resolution (PERFORMED_BY + SOURCED_FROM its postmortem ticket), status 'resolved'. Fixtures:
  - `inc:2025-031` "fraud-scoring timeouts during checkout peak", sev 2, started_at ago(days=455), AFFECTED fraud-scoring, payments-api, config-service; CAUSED_BY dep:risk-rules-v2.3.0; root cause rc:cache-ttl-thundering-herd; resolution "rolled back TTL to 300s, added cache warm-up" PERFORMED_BY Arjun AND Priya.
  - `inc:2026-012` "merchant-onboarding config reads timing out", sev 3, started_at ago(days=150), AFFECTED merchant-onboarding, config-service; CAUSED_BY a merchant-onboarding deploy (create it, ~150 days ago) that disabled local config caching; root cause rc:cache-ttl-thundering-herd; resolution "re-enabled local config cache with jittered TTL" PERFORMED_BY Priya.
  - 4 more incidents with other root causes and services.
  - Do NOT create any SIMILAR_TO edges (agents write those).
- **3 runbooks** (version 1, steps as numbered text). Fixture `rb:fraud-scoring-latency`: AUTHORED by Arjun, updated_at ago(days=540), DESCRIBES fraud-scoring, steps about scaling pods and checking the DB, NO mention of config-service or rules TTL.
- No Fact, Session, Step or PublicPostmortem nodes (but their indexes must exist).

## Verify script (`seed/verify.py`)
Run Cypher checks against the loaded graph and print `PASS`/`FAIL` per check, then exit non-zero on any failure. Print each Cypher query you run (they're part of our "show the receipt" story). Checks:
1. Counts per label within ±30% of the targets above; 4 teams, 27 services.
2. Every node has `id` and `origin`; every Decision and Resolution has ≥1 SOURCED_FROM with a non-empty excerpt that literally appears in the source node's text.
3. Bus factor: the MAINTAINS person of risk-rules has status 'left'; top active WORKED_ON person on risk-rules is Priya.
4. Causal path: directed DEPENDS_ON path payments-api → risk-rules exists (length 2).
5. Likely cause: among services downstream of payments-api within 4 hops, exactly one has a deploy in the last 2 hours, and it's risk-rules (with dep:risk-rules-v2.8.0 FOR_TICKET tkt:RISK-412).
6. Hidden dependency: no DEPENDS_ON from risk-rules to config-service; risk-rules' only outgoing DEPENDS_ON is rules-store-db.
7. Session 2 precondition: payouts-service reaches config-service via DEPENDS_ON; payouts-service and risk-rules share NO common downstream service within 3 hops.
8. Recurring pattern: ≥2 resolved incidents share rc:cache-ttl-thundering-herd, and Priya PERFORMED at least one of their resolutions.
9. Buried decision: dec:rules-cache-ttl SOURCED_FROM chat:risk-eng-config-load; that thread's text contains "config-service" and "300s".
10. Decoy: email-sender has a deploy in the last 2h but is NOT downstream of payments-api.
11. No SIMILAR_TO edges and no `origin:'agent'` nodes exist.
12. Full-text search works: `CALL db.idx.fulltext.queryNodes('ChatThread', 'config')` returns chat:risk-eng-config-load.
13. All expected indexes exist (`CALL db.indexes()`).

## Done when
- `python -m seed.load --graph kestrel_pay --reset` then `python -m seed.verify --graph kestrel_pay` → all PASS. Running load twice without `--reset` must not duplicate anything (re-run verify to prove it).
- Add a short `seed/README.md`: how to run, what each planted story is, and 3 queries to paste into the FalkorDB Browser to see the stories (e.g. the risk-rules neighbourhood).
- Append an entry to `docs/ai-log.md` (what you built, what I should double-check).
- Make a git commit: "Step 2: Kestrel Pay seed + verify". Don't push.
- Finally, explain to me in plain language (I must defend this to judges): how the loader works, why MERGE + UNWIND, why ids are prefixed, why times are relative, and what each verify check proves. Keep it under ~400 words.

Work autonomously; only stop to ask if the schema seems wrong or FalkorDB rejects something you can't work around.
