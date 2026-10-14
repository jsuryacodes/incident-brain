# Claude Code task — Build step 3: core graph tools (read-only)

Read `CLAUDE.md` and `docs/schema.md` (LOCKED v1.0.2) first. The seed in `seed/` is done; `python -m seed.verify --graph kestrel_pay` passes.

## Step 0 — housekeeping (do this first, as its own commit)
`docs/` has uncommitted changes that are not part of step 3:
- Mermaid diagrams in `docs/schema.md` (v1.0.2)
- the corrected `docs/ai-log.md`
- the new `docs/demo-checklist.md`
- this prompt file

Commit only those files with the message "Docs: data model diagrams, demo checklist, step 3 spec" and push. Then start step 3.

## Goal
A small library of **fixed, parameterised, read-only graph tools**. These are the agents' only way to see the graph:
- step 4 (agent loop) calls them,
- the MCP server (later) exposes them,
- the UI (later) draws their `highlight` paths and shows their Cypher.
Each tool returns two things:
- `result`: **small** JSON for the LLM (we have a tiny API budget)
- `receipt`: the exact Cypher + params + which nodes/edges to highlight, for the UI. The LLM never sees the receipt.

No LLM/API calls in this step. No writes to the graph. Memory-writing tools are step 5.

## Files
```
backend/
  __init__.py
  db.py               # get_graph(tenant) -> falkordb Graph. Tenant allowlist from env TENANTS (default "kestrel_pay").
                      # Unknown tenant -> ValueError. FALKORDB_HOST/PORT from .env as in seed.
  tools/
    __init__.py
    receipt.py        # ToolOutput dataclass + helpers (below)
    graph_tools.py    # the tool functions
    registry.py       # TOOLS: name -> {fn, description, input_schema (JSON Schema), track, explanation}
    __main__.py       # CLI: python -m backend.tools <tool> '<json args>' [--tenant kestrel_pay] [--receipt]
    export_docs.py    # python -m backend.tools.export_docs -> writes docs/cypher.md from the registry
tests/
  conftest.py         # loads the seed into a throwaway graph "kestrel_pay_test", deletes it afterwards
  test_graph_tools.py
```
Add `pytest` to requirements.txt. If tests need a reusable loader, refactor `seed/load.py` to expose `load(graph_name, reset=True, now=None)` that `main()` calls. Behaviour must not change; re-run verify.

## Conventions every tool must follow
- Signature: `fn(ctx: ToolContext, **args) -> ToolOutput`.
  - `ToolContext` has `tenant` (graph name) and `now` (epoch secs, default time.time()). Tests pass a fixed `now`. `now` is NOT in the LLM-facing schema.
- **All queries via `graph.ro_query(...)`** (read-only). Values are always parameters.
  - Variable-length bounds (`*1..4`) can't be parameters. Interpolate them only after clamping to ints 1..6.
- Validate inputs. Ids must exist and have the right prefix; otherwise return a `result` with an `error` string, don't raise. This lets the agent recover, e.g. "unknown service id; try find_service".
- `ToolOutput`:
  - `result` (dict, JSON-safe). Serialised it must stay ≤ 2,500 characters: truncate long text to ~200 chars, cap row counts, and include `truncated: true` when you cut.
  - `receipt`:
    - `tool`, `args`
    - `queries`: list of `{cypher, params}` exactly as executed
    - `highlight`: `{nodes: [ids], edges: [{from, type, to}]}`
  - Times in `result` should be human-friendly where useful (e.g. `minutes_ago`, ISO date), alongside the raw epoch.
- Every path-returning tool reports each `DEPENDS_ON` hop's `source` (`declared`/`learned`). This lets the agent say "via a dependency I learned in an earlier session".
- `description` in the registry is written for the LLM: one or two sentences on when to use the tool and what it returns. `explanation` is written for humans (docs + judges): what the Cypher does and why.

## The 12 tools

| # | name | args | what it does |
|---|---|---|---|
| 1 | `find_service` | query: str | Resolve a fuzzy name ("payments api") to service ids. Case-insensitive match on name/id; return up to 5 with team, tier. |
| 2 | `blast_radius` | service_id, max_hops=4 | Upstream services hurt if this one fails: `(s)<-[:DEPENDS_ON*1..N]-(up)`. Per service: min hops, tier, owning team. Sorted by tier, then hops. Highlight the paths. |
| 3 | `recent_changes_downstream` | service_id, since_minutes=120, max_hops=4 | **Likely cause.** Services downstream of the alerting one that have a `Deploy` with `ts > now - since_minutes*60`. Per hit: service, hops, the shortest path (node ids + edge sources), deploy id/version/minutes_ago/summary, who `DEPLOYED` it, linked ticket via `FOR_TICKET` (key, title). Sorted by hops, then recency. |
| 4 | `shared_dependency_changes` | service_id, since_minutes=1440, max_hops=3 | **Noisy neighbour.** Services that share a downstream dependency with this one and changed recently: `(s)-[:DEPENDS_ON*1..N]->(shared)<-[:DEPENDS_ON*1..N]-(n)<-[:CHANGED]-(d:Deploy)`, with `n <> s` and n not itself downstream of s (that case is tool 3's job). Return shared service, neighbour, deploy, ticket, both path halves with edge sources. This is the Session 2 tool: it only finds risk-rules from payouts-service once the learned edge exists. |
| 5 | `dependency_path` | from_id, to_id | Shortest DEPENDS_ON path using **`algo.SPpaths`** (`relTypes:['DEPENDS_ON']`, try `relDirection:'outgoing'`, then `'incoming'`, then `'both'`; report which direction matched). If SPpaths needs a `weightProp`, check the docs. If it can't run without one, fall back to Cypher `shortestPath()` and note it in `explanation`. Return nodes, edge sources, length. |
| 6 | `who_to_call` | service_id | Maintainer(s) via `MAINTAINS` with status/left_at. **`bus_factor_risk: true`** if the maintainer has left or ≤1 active person has `WORKED_ON` the service. Ranked active candidates with transparent signals: `commits`, `last_at` (days ago), `resolutions` (count of Resolutions they `PERFORMED_BY` for incidents that `AFFECTED` this service or were `CAUSED_BY` a Deploy that `CHANGED` it). Score = `commits + 25 * resolutions`; put the formula in `result`. Include owning team + team members as fallback. |
| 7 | `decisions_about` | service_id | Decisions `ABOUT` the service: title, rationale, decided date, author + author status, and every `SOURCED_FROM` source (id, label, title/channel, date) with the `excerpt`. Highlight decision → source. |
| 8 | `past_incidents` | service_ids: list[str], limit=5 | Incidents that `AFFECTED` any given service OR were `CAUSED_BY` a Deploy that `CHANGED` one. Per incident: key, title, severity, started date, `origin` (seed/agent), overlap count, root cause(s), resolution summary, `PERFORMED_BY` names, resolution sources, any `SIMILAR_TO` links. Sort by overlap, then recency. Session 2 recall depends on this returning agent-written incidents too. |
| 9 | `search_knowledge` | query: str, labels=["Doc","Ticket","ChatThread","Decision","Incident","Runbook"], limit=8 | Full-text over the 6 indexes via `CALL db.idx.fulltext.queryNodes(label, $q) YIELD node, score`. Merge and sort by score. Return id, label, title, ~200-char snippet, date, author + author status. Sanitise the query: strip RediSearch operator chars and pass it as a parameter. |
| 10 | `critical_services` | algorithm="pagerank" \| "betweenness", limit=8 | **`CALL algo.pageRank('Service','DEPENDS_ON') YIELD node, score`** (credit flows to callees, so shared dependencies score high). Or **`CALL algo.betweenness({nodeLabels:['Service'], relationshipTypes:['DEPENDS_ON'], samplingSize: 64, samplingSeed: 42}) YIELD node, score`** (chokepoints). Return name, id, tier, team, score (rounded). If the PageRank 2nd-arg form errors, check the docs page. |
| 11 | `stale_knowledge` | service_id=None | Docs/Runbooks that `DESCRIBES` the service (or all, if None) with a list of `reasons`: `author_left` (the AUTHORED person has status left); `names_departed_person` (MENTIONS a left person); `old_vs_changes` (updated_at > 365 days ago AND the service has deploys since); `missing_learned_dependency` (the service has a `DEPENDS_ON {source:'learned'}` edge with `learned_at` > doc.updated_at). Only return items with ≥1 reason. |
| 12 | `node_details` | node_id | Any node: label, props (long text truncated), up to 25 one-hop neighbours (id, label, name/title, edge type, direction). Used for drill-down and for "show me the source". |

## Tests (`tests/test_graph_tools.py`) — must all pass
Use the `kestrel_pay_test` graph, never `kestrel_pay`.
1. `find_service("payments api")` → first hit `svc:payments-api`.
2. `blast_radius(svc:config-service)` includes payments-api, payouts-service, merchant-onboarding and web-checkout. It must NOT include fraud-scoring or risk-rules, because they aren't connected before learning.
3. `recent_changes_downstream(svc:payments-api, 120)` → exactly one hit: risk-rules, hops 2, path [payments-api, fraud-scoring, risk-rules], deploy `dep:risk-rules-v2.8.0`, ticket RISK-412, deployed by Leo. The email-sender decoy is absent.
4. **The memory test**:
   - `shared_dependency_changes(svc:payouts-service, 1440)` does NOT contain risk-rules.
   - Then, in the test graph only, write `(risk-rules)-[:DEPENDS_ON {source:'learned', kind:'sync', learned_at: now}]->(config-service)`.
   - The same call now DOES contain risk-rules, with shared = config-service and a `learned` hop in the path.
   - Clean up (or reload) afterwards so test order doesn't matter.
5. `dependency_path(svc:payments-api, svc:risk-rules)` → length 2.
6. `who_to_call(svc:risk-rules)` → `bus_factor_risk` true, maintainer Arjun with status left, top candidate Priya.
7. `decisions_about(svc:risk-rules)` → `dec:rules-cache-ttl` sourced from `chat:risk-eng-config-load`, and the excerpt contains "300s".
8. `past_incidents([svc:risk-rules])` → includes `inc:2025-031` (via CAUSED_BY deploy), resolved by Arjun and Priya. `past_incidents([svc:config-service])` → both incidents with `rc:cache-ttl-thundering-herd`.
9. `search_knowledge("rulesets config-service")` → `chat:risk-eng-config-load` in the top 3.
10. `critical_services("pagerank")` → config-service in the top 3. `critical_services("betweenness")` returns ≥10 scored services (print the top 5; no ranking assert).
11. `stale_knowledge(svc:risk-rules)` → `doc:risk-rules-readme` with `author_left`. After adding the learned edge (as in test 4), it also has `missing_learned_dependency`. `stale_knowledge(svc:fraud-scoring)` includes `rb:fraud-scoring-latency`.
12. `node_details(svc:risk-rules)` → neighbours include Arjun via MAINTAINS.
13. For EVERY tool:
    - the serialised `result` is ≤ 2,500 chars
    - the receipt has ≥1 query
    - every id in `highlight` exists in the graph
    - a bad id returns an `error` result instead of raising
14. `get_graph("not_a_tenant")` raises ValueError.

## `docs/cypher.md` (submission requirement: "the Cypher queries / graph algorithms the product depends on")
Generate it from the registry. For each tool include:
- name
- one-line purpose
- which hackathon track(s) it serves
- the Cypher (formatted, with `$params`)
- the human `explanation`
- the FalkorDB algorithm used, if any

Start the file with a short table of contents and a note that it is generated (`python -m backend.tools.export_docs`).

## Done when
- `pytest -q` is all green, and `python -m seed.verify --graph kestrel_pay` still passes.
- These CLI calls work and print readable output (paste their output in your final message):
  - `python -m backend.tools recent_changes_downstream '{"service_id":"svc:payments-api"}'`
  - `python -m backend.tools who_to_call '{"service_id":"svc:risk-rules"}'`
  - `python -m backend.tools critical_services '{"algorithm":"pagerank"}' --receipt`
- `docs/cypher.md` is generated.
- Then follow CLAUDE.md's finishing steps (ai-log, commit "Step 3: core graph tools", push). In your plain-language explanation, cover:
  - the receipt idea
  - why tools are fixed rather than text-to-Cypher
  - how tool 3 vs tool 4 find causes
  - what PageRank vs betweenness tell us here
  - why the memory test proves the learned edge changes behaviour
