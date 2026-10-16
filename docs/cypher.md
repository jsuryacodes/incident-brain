# Cypher queries & graph algorithms

> **Generated** by `python -m backend.tools.export_docs` from `backend/tools/registry.py`. Do not edit by hand.

Every product answer comes from one of these 22 fixed, parameterised, **read-only** tools (`graph.ro_query`). The LLM picks a tool and fills in arguments; it never writes Cypher. Each call also returns a *receipt* (the exact query, parameters and the nodes/edges used), which the UI shows.

- `$name` are query parameters. `N` in `*1..N` is a hop bound: variable-length bounds cannot be parameters, so it is clamped to an integer 1..6 before being written into the query.
- `(a)-[:DEPENDS_ON]->(b)` means *a calls b*. `source` on that edge is `declared` (catalog) or `learned` (written by an agent).
- Hackathon tracks: Track 1: Agents That Act on Connected Data; Track 2: Agent Memory and Coordination; Track 3: Company Brain.
- FalkorDB algorithms used: `algo.SPpaths`, `algo.SSpaths`, `algo.BFS`, `algo.WCC`, `algo.labelPropagation`, `algo.pageRank`, `algo.betweenness`, and full-text `db.idx.fulltext.queryNodes`.
- Every tool below was run against the live database while generating this file (FalkorDB graph module v6.0.2); its real output is pasted under it.

## Contents

| # | Tool | Track(s) | Algorithm |
|---|---|---|---|
| 1 | [`find_service`](#find_service) | Track 1: Agents That Act on Connected Data, Track 3: Company Brain | — |
| 2 | [`blast_radius`](#blast_radius) | Track 1: Agents That Act on Connected Data | — |
| 3 | [`recent_changes_downstream`](#recent_changes_downstream) | Track 1: Agents That Act on Connected Data | algo.SPpaths (shortest path per hit) |
| 4 | [`recent_changes`](#recent_changes) | Track 1: Agents That Act on Connected Data | — |
| 5 | [`shared_dependency_changes`](#shared_dependency_changes) | Track 1: Agents That Act on Connected Data, Track 2: Agent Memory and Coordination | — |
| 6 | [`dependency_path`](#dependency_path) | Track 1: Agents That Act on Connected Data, Track 3: Company Brain | algo.SPpaths |
| 7 | [`who_to_call`](#who_to_call) | Track 1: Agents That Act on Connected Data, Track 2: Agent Memory and Coordination, Track 3: Company Brain | — |
| 8 | [`decisions_about`](#decisions_about) | Track 3: Company Brain, Track 2: Agent Memory and Coordination | — |
| 9 | [`past_incidents`](#past_incidents) | Track 1: Agents That Act on Connected Data, Track 3: Company Brain, Track 2: Agent Memory and Coordination | — |
| 10 | [`search_knowledge`](#search_knowledge) | Track 3: Company Brain, Track 2: Agent Memory and Coordination | db.idx.fulltext.queryNodes (RediSearch full-text) |
| 11 | [`critical_services`](#critical_services) | Track 1: Agents That Act on Connected Data, Track 3: Company Brain, Track 2: Agent Memory and Coordination | algo.pageRank / algo.betweenness |
| 12 | [`stale_knowledge`](#stale_knowledge) | Track 3: Company Brain, Track 2: Agent Memory and Coordination | — |
| 13 | [`node_details`](#node_details) | Track 1: Agents That Act on Connected Data, Track 3: Company Brain, Track 2: Agent Memory and Coordination | — |
| 14 | [`read_source`](#read_source) | Track 1: Agents That Act on Connected Data, Track 3: Company Brain | — |
| 15 | [`get_incident_state`](#get_incident_state) | Track 2: Agent Memory and Coordination | — |
| 16 | [`memory_recall`](#memory_recall) | Track 2: Agent Memory and Coordination, Track 1: Agents That Act on Connected Data | — |
| 17 | [`industry_matches`](#industry_matches) | Track 3: Company Brain, Track 2: Agent Memory and Coordination, Track 1: Agents That Act on Connected Data | — |
| 18 | [`rollback_safety`](#rollback_safety) | Track 1: Agents That Act on Connected Data | — |
| 19 | [`correlate_alerts`](#correlate_alerts) | Track 1: Agents That Act on Connected Data | algo.BFS (reach per alert) + algo.SPpaths (paths) |
| 20 | [`connected_impact`](#connected_impact) | Track 1: Agents That Act on Connected Data | algo.WCC (on a projection) + algo.BFS |
| 21 | [`blast_tiers`](#blast_tiers) | Track 1: Agents That Act on Connected Data | algo.SSpaths (incoming, shortest hops per caller) |
| 22 | [`failure_domains`](#failure_domains) | Track 1: Agents That Act on Connected Data | algo.labelPropagation (CDLP) |

## find_service

**Purpose:** Resolve a fuzzy service name like 'payments api' to service ids.

**Track(s):** Track 1: Agents That Act on Connected Data, Track 3: Company Brain

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"query":{"type":"string","description":"Name or part of a name."}}` (required: query)

**LLM-facing description:** Resolve a fuzzy service name like 'payments api' to service ids. Use first when you only have a name. Returns up to 5 matches with team and tier.

**Cypher:**

```cypher
MATCH (s:Service)<-[:OWNS]-(t:Team)
WHERE toLower(s.name) CONTAINS $q OR toLower(s.id) CONTAINS $q
RETURN s.id, s.name, s.tier, t.name, t.id
```

```cypher
MATCH (s:Service)<-[:OWNS]-(t:Team)
WHERE all(tok IN $tokens WHERE toLower(s.name) CONTAINS tok OR toLower(s.description) CONTAINS tok)
RETURN s.id, s.name, s.tier, t.name, t.id
```

**Explanation:** Lower-cases the query, turns spaces into hyphens and matches it against service name/id with CONTAINS. If nothing matches, falls back to requiring every word to appear in the name or description. Ranks exact, then prefix, then substring matches. Entry point for every conversation that starts from a name.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"query": "payments api"}`, 4 ms incl. Python):

```json
{"query": "payments api", "matches": [{"id": "svc:payments-api", "name": "payments-api", "tier": 1, "team": "Payments Core", "team_id": "team:payments-core"}]}
```

## blast_radius

**Purpose:** Which upstream services are hurt if this service fails (everything that transitively calls it).

**Track(s):** Track 1: Agents That Act on Connected Data

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"service_id":{"type":"string","description":"Service id, 'svc:<name>'. Use find_service if unsure."},"max_hops":{"type":"integer","minimum":1,"maximum":6,"description":"Max DEPENDS_ON hops."}}` (required: service_id)

**LLM-facing description:** Which upstream services are hurt if this service fails (everything that transitively calls it). Returns each with tier, owning team and minimum hops, tier-1 first.

**Cypher:**

```cypher
MATCH p=(s:Service {id:$id})<-[:DEPENDS_ON*1..N]-(up:Service)
MATCH (t:Team)-[:OWNS]->(up)
RETURN up.id, up.tier, t.name, min(length(p)) AS hops
ORDER BY up.tier, hops, up.id
```

```cypher
MATCH p=(s:Service {id:$id})<-[:DEPENDS_ON*1..N]-(up:Service)
UNWIND relationships(p) AS r
RETURN DISTINCT startNode(r).id, endNode(r).id, r.source
```

**Explanation:** Walks DEPENDS_ON edges backwards (callers of callers) up to N hops. `a DEPENDS_ON b` means a calls b, so if b fails, every a that reaches b is affected. min(length(p)) keeps the shortest distance per service; sorting by tier puts customer-critical services first. The second query returns the edges of all those paths so the UI can draw them (and flags any learned edge).

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"service_id": "svc:config-service", "max_hops": 2}`, 2 ms incl. Python):

```json
{"service": "svc:config-service", "max_hops": 2, "upstream_count": 12, "tier1_count": 6, "upstream": [{"id": "svc:api-gateway", "tier": 1, "team": "Platform", "hops": 1}, {"id": "svc:auth-service", "tier": 1, "team": "Platform", "hops": 1}, {"id": "svc:bank-connector", "tier": 1, "team": "Payments Core", "hops": 1}, {"id": "svc:payments-api", "tier": 1, "team": "Payments Core", "hops": 1}, {"id": "svc:payouts-service", "tier": 1, "team": "Payments Core", "hops": 1}, {"id": "svc:web-checkout", "tier": 1, "team": "Merchant Experience", "hops": 2}, {"id": "svc:feature-flags", "tier": 2, "team": "Platform", "hops": 1}, {"id": "svc:merchant-onboarding", "tier": 2, "team": "Merchant Experience", "hops": 1}, {"id": "svc:notifications-service", "tier": 2, "team": "Merchant Experience", "hops": 1}, {"id": "svc:webhook-dispatcher", "tier": 2, "team": "Merchant Experience", "hops": 1}, {"id": "svc: …
```

## recent_changes_downstream

**Purpose:** Likely cause of an alert: the alerting service itself (hops 0) and services DOWNSTREAM of it (things it calls) that were deployed recently.

**Track(s):** Track 1: Agents That Act on Connected Data

**FalkorDB algorithm:** algo.SPpaths (shortest path per hit)

**Arguments:** `{"service_id":{"type":"string","description":"Service id, 'svc:<name>'. Use find_service if unsure."},"since_minutes":{"type":"integer","minimum":1,"description":"Look-back window in minutes."},"max_hops":{"type":"integer","minimum":1,"maximum":6,"description":"Max DEPENDS_ON hops."}}` (required: service_id)

**LLM-facing description:** Likely cause of an alert: the alerting service itself (hops 0) and services DOWNSTREAM of it (things it calls) that were deployed recently. Returns hops, the dependency path with each edge's source (declared/learned), the deploy, who shipped it and its ticket.

**Cypher:**

```cypher
MATCH p=(s:Service {id:$id})-[:DEPENDS_ON*0..N]->(d:Service)
MATCH (d)<-[:CHANGED]-(dep:Deploy) WHERE dep.ts > $since
OPTIONAL MATCH (who:Person)-[:DEPLOYED]->(dep)
OPTIONAL MATCH (dep)-[:FOR_TICKET]->(t:Ticket)
RETURN d.id, dep.id, min(length(p)) AS hops, [dep.version, dep.ts, dep.summary, who.id, who.name, t.id, t.key, t.title]
ORDER BY hops, dep.ts DESC
```

```cypher
MATCH (a:Service {id:$from}), (b:Service {id:$to})
CALL algo.SPpaths({sourceNode: a, targetNode: b, relTypes: ['DEPENDS_ON'], relDirection: $dir, maxLen: $maxlen}) YIELD path
RETURN [x IN nodes(path) | x.id], [r IN relationships(path) | r.source], [r IN relationships(path) | startNode(r).id], [r IN relationships(path) | r.kind]
```

**Explanation:** Follows DEPENDS_ON outwards from the alerting service (0 hops included, so a change to the service itself counts) and keeps services that have a Deploy newer than the window. Failures travel up the call chain, so a fresh deploy anywhere below is the prime suspect. Each hit gets its shortest path via algo.SPpaths, plus DEPLOYED (who) and FOR_TICKET (why the change was made).

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"service_id": "svc:payments-api"}`, 1 ms incl. Python):

```json
{"service": "svc:payments-api", "since_minutes": 120, "hit_count": 1, "hits": [{"service": "svc:risk-rules", "hops": 2, "path": ["svc:payments-api", "svc:fraud-scoring", "svc:risk-rules"], "edge_sources": ["declared", "declared"], "deploy": {"id": "dep:risk-rules-v2.8.0", "version": "2.8.0", "ts": 1792172188, "minutes_ago": 40, "summary": "RISK-412: lower RULES_CACHE_TTL 300s -> 5s so rule edits apply faster", "by": "Leo Park"}, "ticket": {"key": "RISK-412", "title": "Rule edits take up to 5 minutes to apply — reduce rules cache TTL"}}]}
```

## recent_changes

**Purpose:** The company-wide change log: every deploy in the window (newest first), with the service, who shipped it (and whether they are still here) and its ticket.

**Track(s):** Track 1: Agents That Act on Connected Data

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"since_minutes":{"type":"integer","minimum":1,"description":"Look-back window in minutes."},"limit":{"type":"integer","minimum":1,"maximum":30}}` (required: none)

**LLM-facing description:** The company-wide change log: every deploy in the window (newest first), with the service, who shipped it (and whether they are still here) and its ticket. No dependency information: use it to list candidate causes, then check each one against the alerting service with the dependency tools.

**Cypher:**

```cypher
MATCH (d:Deploy)-[:CHANGED]->(s:Service) WHERE d.ts > $since
OPTIONAL MATCH (who:Person)-[:DEPLOYED]->(d)
OPTIONAL MATCH (d)-[:FOR_TICKET]->(t:Ticket)
RETURN s.id, s.tier, d.id, d.version, d.ts, d.summary, who.id, who.name, who.status, t.key, t.title
ORDER BY d.ts DESC LIMIT $limit
```

**Explanation:** A flat, one-hop read: Deploy -CHANGED-> Service, newer than the window, plus DEPLOYED (who) and FOR_TICKET (why). It uses the range index on Deploy.ts. On purpose it knows nothing about dependencies: every recent change becomes a hypothesis, and the traversal tools then confirm it (it is on the alerting service's call path) or reject it (it is not). A naive investigator stops at 'the newest deploy'; this is what the graph is for.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"since_minutes": 120}`, 1 ms incl. Python):

```json
{"since_minutes": 120, "change_count": 2, "changes": [{"service": "svc:risk-rules", "tier": 1, "deploy": {"id": "dep:risk-rules-v2.8.0", "version": "2.8.0", "ts": 1792172188, "minutes_ago": 40, "summary": "RISK-412: lower RULES_CACHE_TTL 300s -> 5s so rule edits apply faster", "by": "Leo Park"}, "deployer_id": "per:leo-park", "deployer_status": "active", "ticket": {"key": "RISK-412", "title": "Rule edits take up to 5 minutes to apply — reduce rules cache TTL"}}, {"service": "svc:email-sender", "tier": 3, "deploy": {"id": "dep:email-sender-v1.14.2", "version": "1.14.2", "ts": 1792170988, "minutes_ago": 60, "summary": "Bump transactional email client to 4.2.1; no behaviour change", "by": "Kenji Watanabe"}, "deployer_id": "per:kenji-watanabe", "deployer_status": "active", "ticket": null}]}
```

## shared_dependency_changes

**Purpose:** Noisy-neighbour check: services that are NOT downstream of this one but share a dependency with it and were deployed recently.

**Track(s):** Track 1: Agents That Act on Connected Data, Track 2: Agent Memory and Coordination

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"service_id":{"type":"string","description":"Service id, 'svc:<name>'. Use find_service if unsure."},"since_minutes":{"type":"integer","minimum":1,"description":"Look-back window in minutes."},"max_hops":{"type":"integer","minimum":1,"maximum":6,"description":"Max DEPENDS_ON hops."}}` (required: service_id)

**LLM-facing description:** Noisy-neighbour check: services that are NOT downstream of this one but share a dependency with it and were deployed recently. Shows the shared service (and how many services call it, directly or not: a hub everyone calls is weak evidence) and both paths with edge sources; learned edges can reveal neighbours that declared edges miss.

**Cypher:**

```cypher
MATCH (s:Service {id:$id})-[:DEPENDS_ON*1..6]->(x:Service) RETURN DISTINCT x.id
```

```cypher
MATCH p1=(s:Service {id:$id})-[:DEPENDS_ON*1..N]->(shared:Service),
      p2=(shared)<-[:DEPENDS_ON*1..N]-(n:Service)
MATCH (n)<-[:CHANGED]-(d:Deploy)
WHERE d.ts > $since AND n.id <> $id AND NOT n.id IN $downstream AND NOT $id IN [x IN nodes(p2) | x.id]
OPTIONAL MATCH (who:Person)-[:DEPLOYED]->(d)
OPTIONAL MATCH (d)-[:FOR_TICKET]->(t:Ticket)
RETURN n.id, shared.id, d.id, d.version, d.ts, d.summary, who.id, who.name, t.id, t.key, t.title,
       [x IN nodes(p1) | x.id], [r IN relationships(p1) | r.source],
       [x IN nodes(p2) | x.id], [r IN relationships(p2) | r.source],
       [r IN relationships(p1) + relationships(p2) WHERE r.learned_from IS NOT NULL | r.learned_from]
ORDER BY length(p1) + length(p2), d.ts DESC
LIMIT 60
```

```cypher
MATCH (c:Service)-[:DEPENDS_ON*1..6]->(s:Service) WHERE s.id IN $ids RETURN s.id, count(DISTINCT c)
```

**Explanation:** Pattern (s)-[:DEPENDS_ON*]->(shared)<-[:DEPENDS_ON*]-(n)<-[:CHANGED]-(deploy): another service n hammers a dependency that s also needs. Services already downstream of s are excluded (that is recent_changes_downstream's job). This is the tool that gets smarter with memory: once an agent has written a learned DEPENDS_ON edge, the same query finds neighbours through it.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"service_id": "svc:payouts-service", "since_minutes": 120}`, 1 ms incl. Python):

```json
{"service": "svc:payouts-service", "since_minutes": 120, "hit_count": 0, "hits": [], "note": "no recently changed service shares a downstream dependency with this one"}
```

## dependency_path

**Purpose:** Shortest DEPENDS_ON path between two services, trying caller->callee first, then callee->caller, then either way.

**Track(s):** Track 1: Agents That Act on Connected Data, Track 3: Company Brain

**FalkorDB algorithm:** algo.SPpaths

**Arguments:** `{"from_id":{"type":"string","description":"Service id, 'svc:<name>'. Use find_service if unsure."},"to_id":{"type":"string","description":"Service id, 'svc:<name>'. Use find_service if unsure."}}` (required: from_id, to_id)

**LLM-facing description:** Shortest DEPENDS_ON path between two services, trying caller->callee first, then callee->caller, then either way. Returns the nodes, the direction that matched and each hop's source (declared/learned).

**Cypher:**

```cypher
MATCH (a:Service {id:$from}), (b:Service {id:$to})
CALL algo.SPpaths({sourceNode: a, targetNode: b, relTypes: ['DEPENDS_ON'], relDirection: $dir, maxLen: $maxlen}) YIELD path
RETURN [x IN nodes(path) | x.id], [r IN relationships(path) | r.source], [r IN relationships(path) | startNode(r).id], [r IN relationships(path) | r.kind]
```

**Explanation:** Calls FalkorDB's algo.SPpaths with relTypes ['DEPENDS_ON'] (no weight property needed; it counts hops) and tries relDirection outgoing, incoming, then both, reporting which matched. Each hop is returned with its source so answers can say 'via a dependency learned earlier'.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"from_id": "svc:web-checkout", "to_id": "svc:risk-rules"}`, 1 ms incl. Python):

```json
{"from": "svc:web-checkout", "to": "svc:risk-rules", "found": true, "direction_matched": "outgoing", "length": 4, "nodes": ["svc:web-checkout", "svc:api-gateway", "svc:payments-api", "svc:fraud-scoring", "svc:risk-rules"], "hops": [{"caller": "svc:web-checkout", "callee": "svc:api-gateway", "source": "declared", "kind": "sync"}, {"caller": "svc:api-gateway", "callee": "svc:payments-api", "source": "declared", "kind": "sync"}, {"caller": "svc:payments-api", "callee": "svc:fraud-scoring", "source": "declared", "kind": "sync"}, {"caller": "svc:fraud-scoring", "callee": "svc:risk-rules", "source": "declared", "kind": "sync"}]}
```

## who_to_call

**Purpose:** Who to page for a service.

**Track(s):** Track 1: Agents That Act on Connected Data, Track 2: Agent Memory and Coordination, Track 3: Company Brain

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"service_id":{"type":"string","description":"Service id, 'svc:<name>'. Use find_service if unsure."}}` (required: service_id)

**LLM-facing description:** Who to page for a service. Returns the official maintainer (and whether they left), a bus_factor_risk flag, ranked active candidates with transparent signals (commits, recency, past incident resolutions) and the owning team as fallback.

**Cypher:**

```cypher
MATCH (p:Person)-[:MAINTAINS]->(s:Service {id:$id}) RETURN p.id, p.name, p.status, p.left_at
```

```cypher
MATCH (p:Person {status:'active'})-[w:WORKED_ON]->(s:Service {id:$id})
RETURN p.id, p.name, p.role, w.commits, w.last_at
```

```cypher
MATCH (s:Service {id:$id})<-[:AFFECTED]-(i:Incident)-[:RESOLVED_BY]->(r:Resolution)-[:PERFORMED_BY]->(p:Person {status:'active'})
RETURN p.id, p.name, p.role, collect(DISTINCT r.id)
```

```cypher
MATCH (s:Service {id:$id})<-[:CHANGED]-(:Deploy)<-[:CAUSED_BY]-(i:Incident)-[:RESOLVED_BY]->(r:Resolution)-[:PERFORMED_BY]->(p:Person {status:'active'})
RETURN p.id, p.name, p.role, collect(DISTINCT r.id)
```

```cypher
MATCH (t:Team)-[:OWNS]->(s:Service {id:$id})
OPTIONAL MATCH (m:Person {status:'active'})-[:MEMBER_OF]->(t)
RETURN t.id, t.name, collect(m.name)
```

**Explanation:** Expertise is computed, not stored. MAINTAINS gives the official owner (flagged if they left); WORKED_ON gives commits; incidents that AFFECTED the service or were CAUSED_BY a deploy that CHANGED it give the people who actually fixed things (PERFORMED_BY). Score = commits + 25 x resolutions, so one real incident fix counts like 25 commits. bus_factor_risk is true if the maintainer left or at most one active person has touched the service.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"service_id": "svc:risk-rules"}`, 2 ms incl. Python):

```json
{"service": "svc:risk-rules", "maintainers": [{"id": "per:arjun-mehta", "name": "Arjun Mehta", "status": "left", "left_days_ago": 95}], "bus_factor_risk": true, "bus_factor_reasons": ["maintainer Arjun Mehta has left"], "score_formula": "commits + 25 * resolutions", "candidates": [{"id": "per:priya-nair", "name": "Priya Nair", "role": "Senior Engineer", "commits": 23, "last_commit_days_ago": 40, "resolutions": 1, "score": 48}, {"id": "per:leo-park", "name": "Leo Park", "role": "Engineer", "commits": 3, "last_commit_days_ago": 1, "resolutions": 0, "score": 3}, {"id": "per:dana-okafor", "name": "Dana Okafor", "role": "Engineering Manager", "commits": 2, "last_commit_days_ago": 120, "resolutions": 0, "score": 2}], "owning_team_fallback": {"id": "team:risk-fraud", "name": "Risk & Fraud", "active_members": ["Leo Park", "Dana Okafor", "Mei Lin Chen", "Ravi Shankar"]}}
```

## decisions_about

**Purpose:** Recorded decisions about a service: what was decided, why, who decided (and whether they left), and the exact quoted source (chat thread, doc or ticket) as the receipt.

**Track(s):** Track 3: Company Brain, Track 2: Agent Memory and Coordination

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"service_id":{"type":"string","description":"Service id, 'svc:<name>'. Use find_service if unsure."}}` (required: service_id)

**LLM-facing description:** Recorded decisions about a service: what was decided, why, who decided (and whether they left), and the exact quoted source (chat thread, doc or ticket) as the receipt.

**Cypher:**

```cypher
MATCH (d:Decision)-[:ABOUT]->(s:Service {id:$id})
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(d)
OPTIONAL MATCH (d)-[r:SOURCED_FROM]->(src)
RETURN d.id, d.title, d.rationale, d.decided_at, a.id, a.name, a.status,
       src.id, labels(src)[0], coalesce(src.title, src.key), src.channel,
       coalesce(src.ts, src.updated_at, src.created_at, src.started_at), r.excerpt
ORDER BY d.decided_at DESC
```

**Explanation:** Decision -ABOUT-> Service, with AUTHORED for the author and SOURCED_FROM for the provenance edge carrying the verbatim excerpt. One hop from claim to evidence: 'show the receipt'.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"service_id": "svc:risk-rules"}`, 1 ms incl. Python):

```json
{"service": "svc:risk-rules", "decisions": [{"id": "dec:rules-cache-ttl", "title": "RULES_CACHE_TTL must stay ≥ 300s", "rationale": "Below ~30s config-service saturates at checkout peak, because risk-rules refetches rulesets from it on every cache miss. This is what caused INC-2025-031.", "decided": "2025-08-12", "decided_days_ago": 430, "author": "Arjun Mehta", "author_status": "left", "sources": [{"id": "chat:risk-eng-config-load", "label": "ChatThread", "title": "How does risk-rules get its rules? (config load)", "channel": "#risk-eng", "date": "2025-08-12", "excerpt": "Decision: RULES_CACHE_TTL stays at 300s minimum. Below ~30s config-service falls over at checkout peak — that's what bit us in INC-2025-031."}]}]}
```

## past_incidents

**Purpose:** Past incidents that touched any of the given services (affected them, or were caused by a deploy that changed them).

**Track(s):** Track 1: Agents That Act on Connected Data, Track 3: Company Brain, Track 2: Agent Memory and Coordination

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"service_ids":{"type":"array","items":{"type":"string"},"minItems":1,"maxItems":10,"description":"Service ids, e.g. ['svc:<name>', 'svc:<other>']."},"limit":{"type":"integer","minimum":1,"maximum":10}}` (required: service_ids)

**LLM-facing description:** Past incidents that touched any of the given services (affected them, or were caused by a deploy that changed them). Returns root cause, how it was resolved and by whom, sources, and SIMILAR_TO links, including incidents written by agents in earlier sessions.

**Cypher:**

```cypher
MATCH (i:Incident)-[:AFFECTED]->(s:Service) WHERE s.id IN $ids
RETURN DISTINCT i.id, s.id
```

```cypher
MATCH (i:Incident)-[:CAUSED_BY]->(dep:Deploy)-[:CHANGED]->(s:Service) WHERE s.id IN $ids
RETURN DISTINCT i.id, s.id, dep.id
```

```cypher
MATCH (i:Incident) WHERE i.id IN $iids
OPTIONAL MATCH (i)-[:HAS_ROOT_CAUSE]->(rc:RootCause)
OPTIONAL MATCH (i)-[:RESOLVED_BY]->(r:Resolution)
OPTIONAL MATCH (r)-[:PERFORMED_BY]->(p:Person)
OPTIONAL MATCH (r)-[:SOURCED_FROM]->(src)
OPTIONAL MATCH (i)-[sim:SIMILAR_TO]-(o)
OPTIONAL MATCH (rb:Runbook)-[:SOURCED_FROM]->(i)
RETURN i.id, i.key, i.title, i.severity, i.started_at, i.origin, i.status,
       collect(DISTINCT rc.id), collect(DISTINCT r.id), collect(DISTINCT r.summary), collect(DISTINCT p.id),
       collect(DISTINCT p.name), collect(DISTINCT src.id), collect(DISTINCT {id: o.id, score: sim.score}),
       collect(DISTINCT rb.id)
```

**Explanation:** Two routes into an incident: AFFECTED (it hurt the service) and CAUSED_BY a Deploy that CHANGED the service (it came from there). Ranked by how many of the given services it touches, then recency. Detail query follows HAS_ROOT_CAUSE, RESOLVED_BY, PERFORMED_BY and SOURCED_FROM; SIMILAR_TO is read in both directions so links written by agents show up. Nothing filters on origin, so agent-written incidents are recalled too.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"service_ids": ["svc:risk-rules"], "limit": 2}`, 2 ms incl. Python):

```json
{"service_ids": ["svc:risk-rules"], "incident_count": 1, "incidents": [{"id": "inc:2025-031", "key": "INC-2025-031", "title": "fraud-scoring timeouts during checkout peak", "severity": 2, "started": "2025-07-18", "origin": "seed", "status": "resolved", "overlap": 1, "via": ["caused_by_deploy"], "caused_by_change_to": ["svc:risk-rules"], "root_causes": ["rc:cache-ttl-thundering-herd"], "resolution": "Rolled back TTL to 300s and added cache warm-up", "resolved_by": ["Priya Nair", "Arjun Mehta"], "resolution_sources": ["tkt:PM-2025-031"], "similar_to": []}]}
```

## search_knowledge

**Purpose:** Full-text search over docs, tickets, chat threads, decisions, incidents and runbooks (also root causes and public postmortems if listed in labels).

**Track(s):** Track 3: Company Brain, Track 2: Agent Memory and Coordination

**FalkorDB algorithm:** db.idx.fulltext.queryNodes (RediSearch full-text)

**Arguments:** `{"query":{"type":"string"},"labels":{"type":"array","items":{"enum":["Doc","Ticket","ChatThread","Decision","Incident","Runbook","RootCause","PublicPostmortem"]},"description":"Subset of Doc, Ticket, ChatThread, Decision, Incident, Runbook (the default), or RootCause / PublicPostmortem (only when listed)."},"limit":{"type":"integer","minimum":1,"maximum":20}}` (required: query)

**LLM-facing description:** Full-text search over docs, tickets, chat threads, decisions, incidents and runbooks (also root causes and public postmortems if listed in labels). Returns id, type, title, snippet around the match, date and author (and whether they left). Use for open questions; follow up with node_details.

**Cypher:**

```cypher
CALL db.idx.fulltext.queryNodes($label, $q) YIELD node, score
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(node)
RETURN node.id, score, coalesce(node.title, node.key, node.name), coalesce(node.text, node.rationale, node.summary, node.steps, node.description),
       coalesce(node.ts, node.updated_at, node.decided_at, node.started_at, node.created_at), a.name, a.status
ORDER BY score DESC, node.id LIMIT $limit
```

**Explanation:** Runs FalkorDB's full-text index per label. The query is stripped to plain words (no operator characters) and passed as a parameter. First pass requires all words (precise); if there is room, a second pass accepts any word (recall) ranked lower. Each index's scores are normalised to its best hit because scores are not comparable across indexes; ties go to raw sources (chats, docs, tickets) before derived summaries. No embeddings: the graph supplies context.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"query": "rules cache ttl", "limit": 3}`, 4 ms incl. Python):

```json
{"query": "rules cache ttl", "terms": ["rules", "cache", "ttl"], "hit_count": 12, "hits": [{"id": "chat:risk-eng-config-load", "label": "ChatThread", "title": "How does risk-rules get its rules? (config load)", "snippet": "…I go through the INC-2025-031 action items: where does risk-rules actually read rules from at request time? [2025-08-12 18:19] Arjun Mehta: Not from its own DB on the hot path. rules-store-db is just…", "date": "2025-08-12", "author": "Arjun Mehta", "author_status": "left", "score": 1.0}, {"id": "tkt:RISK-412", "label": "Ticket", "title": "Rule edits take up to 5 minutes to apply — reduce rules cache TTL", "snippet": "…up to 5 minutes to take effect in production, because risk-rules caches the rule set for RULES_CACHE_TTL (currently 300s). Proposal: reduce RULES_CACHE_TTL from 300s to 5s so edits apply almost immed…", "date": "2026-10-13", "author": "Leo Park", "autho …
```

## critical_services

**Purpose:** Rank services by structural importance.

**Track(s):** Track 1: Agents That Act on Connected Data, Track 3: Company Brain, Track 2: Agent Memory and Coordination

**FalkorDB algorithm:** algo.pageRank / algo.betweenness

**Arguments:** `{"algorithm":{"enum":["pagerank","betweenness","fan_in"]},"limit":{"type":"integer","minimum":1,"maximum":50},"downstream_of":{"type":"array","items":{"type":"string"},"maxItems":10,"description":"Optional service ids: only rank services these call (directly or not), e.g. where to look first on an alert's call path."}}` (required: none)

**LLM-facing description:** Rank services by structural importance. 'pagerank' finds shared dependencies many services rely on; 'betweenness' finds chokepoints on many call paths; 'fan_in' simply counts how many services reach each one (no algorithm). With downstream_of, only services on those services' call paths are ranked (where to look first when nothing changed). Returns name, tier, team and score.

**Cypher:**

```cypher
CALL algo.pageRank('Service', 'DEPENDS_ON') YIELD node, score
MATCH (t:Team)-[:OWNS]->(node)
RETURN node.id, node.name, node.tier, t.name, score ORDER BY score DESC LIMIT $limit
```

```cypher
CALL algo.betweenness({nodeLabels: ['Service'], relationshipTypes: ['DEPENDS_ON'], samplingSize: 64, samplingSeed: 42}) YIELD node, score
MATCH (t:Team)-[:OWNS]->(node)
RETURN node.id, node.name, node.tier, t.name, score ORDER BY score DESC LIMIT $limit
```

```cypher
MATCH (c:Service)-[:DEPENDS_ON*1..6]->(node:Service)
MATCH (t:Team)-[:OWNS]->(node)
RETURN node.id, node.name, node.tier, t.name, count(DISTINCT c) AS score ORDER BY score DESC, node.id LIMIT $limit
```

```cypher
MATCH (s:Service)-[:DEPENDS_ON*1..6]->(d:Service) WHERE s.id IN $ids RETURN DISTINCT d.id
```

**Explanation:** PageRank over DEPENDS_ON passes credit from callers to callees, so heavily shared dependencies (config-service, its database, kafka-events) rise to the top: single points of failure. Betweenness counts shortest paths running through a node (sampled, fixed seed for repeatable results): it surfaces middle layers like payments-api and api-gateway that everything funnels through. Different questions: 'what do we all depend on' vs 'what sits in the middle'.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"algorithm": "pagerank", "limit": 4, "downstream_of": ["svc:payouts-service"]}`, 1 ms incl. Python):

```json
{"algorithm": "pagerank", "meaning": "shared dependencies: services many others call, directly or indirectly", "services": [{"id": "svc:config-db", "name": "config-db", "tier": 1, "team": "Platform", "score": 0.1215}, {"id": "svc:config-service", "name": "config-service", "tier": 1, "team": "Platform", "score": 0.1213}, {"id": "svc:kafka-events", "name": "kafka-events", "tier": 1, "team": "Platform", "score": 0.089}, {"id": "svc:ledger-service", "name": "ledger-service", "tier": 1, "team": "Payments Core", "score": 0.0532}], "downstream_of": ["svc:payouts-service"], "note": "ranked over the whole company, then limited to services the given ones call (directly or not)"}
```

## stale_knowledge

**Purpose:** Docs and runbooks that are probably out of date, with reasons: author_left, names_departed_person, old_vs_changes (>1 year old but the service kept deploying), missing_learned_dependency (a dependency was learned after the doc was written).

**Track(s):** Track 3: Company Brain, Track 2: Agent Memory and Coordination

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"service_id":{"type":["string","null"],"description":"Service id, or null for all."}}` (required: none)

**LLM-facing description:** Docs and runbooks that are probably out of date, with reasons: author_left, names_departed_person, old_vs_changes (>1 year old but the service kept deploying), missing_learned_dependency (a dependency was learned after the doc was written). Omit service_id to scan everything.

**Cypher:**

```cypher
MATCH (x)-[:DESCRIBES]->(s:Service)
WHERE (x:Doc OR x:Runbook) AND ($sid IS NULL OR s.id = $sid)
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(x)
OPTIONAL MATCH (x)-[:MENTIONS]->(gone:Person {status: 'left'})
OPTIONAL MATCH (dp:Deploy)-[:CHANGED]->(s) WHERE dp.ts > x.updated_at
OPTIONAL MATCH (s)-[l:DEPENDS_ON {source: 'learned'}]->(t:Service) WHERE l.learned_at > x.updated_at
RETURN x.id, labels(x)[0], x.title, x.updated_at, s.id, a.id, a.name, a.status, coalesce(x.flagged_stale, false),
       collect(DISTINCT gone.name), collect(DISTINCT gone.id), count(DISTINCT dp), collect(DISTINCT t.id)
ORDER BY x.updated_at
```

**Explanation:** Documentation rots in ways the graph can see: the AUTHORED person has status left, the text MENTIONS a departed person, the document is older than a year while the service it DESCRIBES kept getting CHANGED by deploys, or a DEPENDS_ON edge with source 'learned' was written after the document's updated_at. Only items with at least one reason are returned.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"service_id": "svc:risk-rules"}`, 1 ms incl. Python):

```json
{"service": "svc:risk-rules", "stale_count": 1, "items": [{"id": "doc:risk-rules-readme", "kind": "Doc", "title": "risk-rules README", "describes": "svc:risk-rules", "updated": "2025-02-23", "updated_days_ago": 600, "flagged": false, "reasons": ["author_left", "names_departed_person", "old_vs_changes"], "author": "Arjun Mehta", "departed_people": ["Arjun Mehta"], "deploys_since_update": 3}]}
```

## node_details

**Purpose:** Drill down into any node by id: its label, properties (long text shortened), counts of edges by type and up to 25 neighbours.

**Track(s):** Track 1: Agents That Act on Connected Data, Track 3: Company Brain, Track 2: Agent Memory and Coordination

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"node_id":{"type":"string","description":"Any node id: '<prefix>:<name>', e.g. 'chat:<slug>', 'per:<name>'."}}` (required: node_id)

**LLM-facing description:** Drill down into any node by id: its label, properties (long text shortened), counts of edges by type and up to 25 neighbours. Use to 'show the source' for an id returned by another tool.

**Cypher:**

```cypher
MATCH (n:<Label from id prefix> {id: $id}) RETURN n
```

```cypher
MATCH (n:<Label from id prefix> {id: $id})-[r]-(m)
RETURN type(r), startNode(r).id = n.id, m.id, coalesce(m.name, m.title, m.key, m.summary, m.statement)
LIMIT 300
```

**Explanation:** Looks the node up by its prefixed id (the prefix selects the label, so the index on id is used) and lists one-hop neighbours with edge type and direction. Neighbours are taken round-robin across edge types so a node with many mentions still shows its maintainer, dependencies and owner.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"node_id": "per:arjun-mehta"}`, 2 ms incl. Python):

```json
{"id": "per:arjun-mehta", "label": "Person", "props": {"status": "left", "origin": "seed", "name": "Arjun Mehta", "role": "Staff Engineer", "email": "arjun.mehta@kestrelpay.example", "joined_at": 1602094588, "left_at": 1783966588}, "dates": {"joined_at": "2020-10-07", "left_at": "2026-07-13"}, "neighbour_counts": {"MEMBER_OF (out)": 1, "MAINTAINS (out)": 2, "WORKED_ON (out)": 3, "DEPLOYED (out)": 1, "AUTHORED (out)": 6, "MENTIONS (in)": 2, "PERFORMED_BY (in)": 1}, "neighbours": [{"edge": "MEMBER_OF", "dir": "out", "id": "team:risk-fraud", "name": "Risk & Fraud"}, {"edge": "MAINTAINS", "dir": "out", "id": "svc:fraud-scoring", "name": "fraud-scoring"}, {"edge": "WORKED_ON", "dir": "out", "id": "svc:fraud-scoring", "name": "fraud-scoring"}, {"edge": "DEPLOYED", "dir": "out", "id": "dep:risk-rules-v2.3.0", "name": "Lower RULES_CACHE_TTL to 10s"}, {"edge": "AUTHORED", "dir": "out", "id": "cha …
```

## read_source

**Purpose:** Read the full text (up to 1,800 chars) of a doc, ticket, chat thread, decision, runbook or incident, with title, author (and whether they left), date and what it mentions/describes.

**Track(s):** Track 1: Agents That Act on Connected Data, Track 3: Company Brain

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"node_id":{"type":"string","description":"A 'doc:', 'tkt:', 'chat:', 'dec:', 'rb:' or 'inc:' id returned by another tool."}}` (required: node_id)

**LLM-facing description:** Read the full text (up to 1,800 chars) of a doc, ticket, chat thread, decision, runbook or incident, with title, author (and whether they left), date and what it mentions/describes. node_details only shows 200 chars; use this to read a source and quote it verbatim.

**Cypher:**

```cypher
MATCH (n:<Label from id prefix> {id:$id})
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(n)
RETURN n, a.id, a.name, a.status
```

```cypher
MATCH (n:<Label from id prefix> {id:$id})-[r:MENTIONS|DESCRIBES|ABOUT|SUPERSEDES|SOURCED_FROM]->(m)
RETURN type(r), m.id
```

```cypher
MATCH (o:Runbook)-[:SUPERSEDES]->(n:Runbook {id:$id}) RETURN o.id
```

**Explanation:** Looks the node up by its prefixed id and returns its main text field (text, rationale, steps or summary) with AUTHORED for the author and the outgoing MENTIONS / DESCRIBES / ABOUT / SUPERSEDES / SOURCED_FROM links. Agents need the full text because key chat lines sit deep in a thread, and every excerpt they write must be a literal quote of it.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"node_id": "dec:rules-cache-ttl"}`, 1 ms incl. Python):

```json
{"id": "dec:rules-cache-ttl", "label": "Decision", "title": "RULES_CACHE_TTL must stay ≥ 300s", "author": "Arjun Mehta", "author_status": "left", "date": "2025-08-12", "days_ago": 430, "text": "Below ~30s config-service saturates at checkout peak, because risk-rules refetches rulesets from it on every cache miss. This is what caused INC-2025-031.", "truncated": false, "about": ["svc:risk-rules"], "sourced_from": ["chat:risk-eng-config-load"], "origin": "seed"}
```

## get_incident_state

**Purpose:** The shared state of an incident: status, severity, affected services, cause (deploy/service), root causes, facts learned in its sessions, handoff notes from earlier agents (in order), actions taken (pages, tickets, writes), similar incidents and the resolution.

**Track(s):** Track 2: Agent Memory and Coordination

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"incident_id":{"type":"string","description":"Incident id, 'inc:<year>-<nnn>'."}}` (required: incident_id)

**LLM-facing description:** The shared state of an incident: status, severity, affected services, cause (deploy/service), root causes, facts learned in its sessions, handoff notes from earlier agents (in order), actions taken (pages, tickets, writes), similar incidents and the resolution.

**Cypher:**

```cypher
MATCH (i:Incident {id:$id}) RETURN i
```

```cypher
MATCH (i:Incident {id:$id})-[:AFFECTED]->(s:Service) RETURN s.id ORDER BY s.id
```

```cypher
MATCH (i:Incident {id:$id})-[:CAUSED_BY]->(c)
OPTIONAL MATCH (c)-[:CHANGED]->(s:Service)
OPTIONAL MATCH (c)-[:FOR_TICKET]->(t:Ticket)
OPTIONAL MATCH (who:Person)-[:DEPLOYED]->(c)
RETURN c.id, labels(c)[0], c.summary, c.ts, s.id, t.key, t.title, who.name
```

```cypher
MATCH (i:Incident {id:$id})-[:HAS_ROOT_CAUSE]->(rc:RootCause) RETURN rc.id, rc.name
```

```cypher
MATCH (:Incident {id:$id})<-[:FOR_INCIDENT]-(:Session)<-[:WRITTEN_IN]-(f:Fact)
OPTIONAL MATCH (f)-[:ABOUT]->(x)
OPTIONAL MATCH (f)-[r:SOURCED_FROM]->(src)
RETURN f.id, f.statement, f.confidence, collect(DISTINCT x.id), collect(DISTINCT [src.id, r.excerpt])
```

```cypher
MATCH (:Incident {id:$id})<-[:FOR_INCIDENT]-(ses:Session)<-[:IN_SESSION]-(st:Step)
WHERE st.action IN ['handoff', 'write', 'page']
RETURN ses.id, ses.started_at, st.seq, st.agent, st.action, st.tool, st.summary, st.params_json
ORDER BY ses.started_at, st.seq
```

```cypher
MATCH (t:Ticket)-[:ABOUT]->(:Incident {id:$id}) RETURN t.id, t.key, t.title, t.status
```

```cypher
MATCH (i:Incident {id:$id})-[s:SIMILAR_TO]-(o)
OPTIONAL MATCH (o)-[:RESOLVED_BY]->(r:Resolution)
OPTIONAL MATCH (r)-[:PERFORMED_BY]->(p:Person)
OPTIONAL MATCH (rb:Runbook)-[:SOURCED_FROM]->(o)
RETURN o.id, o.key, s.score, s.reason, r.summary, collect(DISTINCT p.name), collect(DISTINCT rb.id)
```

```cypher
MATCH (i:Incident {id:$id})-[:RESOLVED_BY]->(r:Resolution)
OPTIONAL MATCH (r)-[:PERFORMED_BY]->(p:Person)
RETURN r.id, r.summary, collect(p.id), collect(p.name)
```

**Explanation:** This is how agents hand off: each agent starts with an empty conversation and reads the incident's state from the graph. Sessions point at the incident (FOR_INCIDENT); their Steps (IN_SESSION) with action 'handoff' carry the notes, and Facts WRITTEN_IN those sessions are what the team learned. Nine small queries instead of one big one, because FalkorDB drops rows when a MATCH follows an aggregation.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"incident_id": "inc:2025-031"}`, 4 ms incl. Python):

```json
{"id": "inc:2025-031", "key": "INC-2025-031", "title": "fraud-scoring timeouts during checkout peak", "severity": 2, "status": "resolved", "symptom": "payments-api 5xx; fraud-scoring calls timing out at 800ms; config-service CPU at 98%", "summary": "risk-rules v2.3.0 lowered RULES_CACHE_TTL to 10s. At checkout peak every risk-rules pod refetched rulesets, saturating config-service and timing out fraud-scoring. Rolled back the TTL to 300s and added cache warm-up.", "origin": "seed", "started_minutes_ago": 655200, "affected": ["svc:config-service", "svc:fraud-scoring", "svc:payments-api"], "caused_by": [{"id": "dep:risk-rules-v2.3.0", "label": "Deploy", "service": "svc:risk-rules", "summary": "Lower RULES_CACHE_TTL to 10s", "minutes_ago": 655380, "by": "Arjun Mehta", "ticket": null}], "root_causes": [{"id": "rc:cache-ttl-thundering-herd", "name": "Cache TTL too low → thundering herd on a s …
```

## memory_recall

**Purpose:** Call FIRST on an alert: what earlier agent sessions learned about this service and its dependencies (DEPENDS_ON 1..3 hops).

**Track(s):** Track 2: Agent Memory and Coordination, Track 1: Agents That Act on Connected Data

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"service_id":{"type":"string","description":"Service id, 'svc:<name>'. Use find_service if unsure."},"max_hops":{"type":"integer","minimum":1,"maximum":6,"description":"Max DEPENDS_ON hops."}}` (required: service_id)

**LLM-facing description:** Call FIRST on an alert: what earlier agent sessions learned about this service and its dependencies (DEPENDS_ON 1..3 hops). Returns learned dependencies (with the Fact, quoted source and session), agent-written facts, incidents agents resolved (cause, root cause, who fixed it and how, latest runbook steps) and `suspects`: services that memory points at, each with relation 'downstream' or 'shares_dependency'. Empty when nothing was learned yet.

**Cypher:**

```cypher
MATCH (s:Service {id:$id})-[:DEPENDS_ON*1..N]->(d:Service) RETURN DISTINCT d.id
```

```cypher
MATCH (a:Service)-[r:DEPENDS_ON {source:'learned'}]->(b:Service)
WHERE a.id IN $ids OR b.id IN $ids
OPTIONAL MATCH (f:Fact) WHERE f.id = r.learned_from
OPTIONAL MATCH (f)-[sf:SOURCED_FROM]->(src)
OPTIONAL MATCH (f)-[:WRITTEN_IN]->(ses:Session)
RETURN a.id, b.id, r.kind, r.learned_at, f.id, f.statement, src.id, sf.excerpt, ses.id
```

```cypher
MATCH (f:Fact)-[:ABOUT]->(s:Service)
WHERE s.id IN $ids AND NOT f.id IN $skip
OPTIONAL MATCH (f)-[sf:SOURCED_FROM]->(src)
OPTIONAL MATCH (f)-[:WRITTEN_IN]->(ses:Session)
RETURN f.id, f.statement, f.confidence, collect(DISTINCT s.id), collect(DISTINCT [src.id, sf.excerpt]), collect(DISTINCT ses.id)
```

```cypher
MATCH (i:Incident {origin:'agent', status:'resolved'})-[:AFFECTED]->(s:Service)
WHERE s.id IN $ids
OPTIONAL MATCH (i)-[:CAUSED_BY]->(c)
OPTIONAL MATCH (c)-[:CHANGED]->(cs:Service)
OPTIONAL MATCH (i)-[:HAS_ROOT_CAUSE]->(rc:RootCause)
OPTIONAL MATCH (i)-[:RESOLVED_BY]->(r:Resolution)
OPTIONAL MATCH (r)-[:PERFORMED_BY]->(p:Person)
OPTIONAL MATCH (i)-[:WRITTEN_IN]->(ses:Session)
RETURN i.id, i.key, i.title, i.resolved_at, collect(DISTINCT s.id), collect(DISTINCT [c.id, labels(c)[0], cs.id]),
       collect(DISTINCT rc.id), r.id, r.summary, collect(DISTINCT [p.id, p.name]), collect(DISTINCT ses.id)
ORDER BY i.resolved_at DESC
```

```cypher
MATCH (rb:Runbook)-[:SOURCED_FROM]->(i:Incident)
WHERE i.id IN $iids
MATCH (latest:Runbook)-[:SUPERSEDES*0..5]->(rb)
WHERE NOT ()-[:SUPERSEDES]->(latest)
RETURN DISTINCT i.id, latest.id, latest.title, latest.version, latest.steps
```

**Explanation:** Memory-first recall. The scope is the alerting service plus everything it calls within N hops (declared or learned edges). Then four small queries: learned DEPENDS_ON edges touching the scope (with the Fact on learned_from, its SOURCED_FROM excerpt and the Session it was WRITTEN_IN); other agent Facts ABOUT scope services; incidents with origin 'agent' and status 'resolved' that AFFECTED the scope (CAUSED_BY, HAS_ROOT_CAUSE, RESOLVED_BY, PERFORMED_BY); and for those incidents the newest runbook, found by following SUPERSEDES*0..5 back to a runbook that nothing supersedes. A learned edge into one of my dependencies makes its caller a noisy-neighbour suspect; a learned edge on my own path or the cause of a recalled incident makes that service a suspect too. Only agent-written memory is recalled: seeded history stays with past_incidents, so a first session honestly recalls nothing.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"service_id": "svc:payments-api"}`, 2 ms incl. Python):

```json
{"service": "svc:payments-api", "scope": ["svc:payments-api", "svc:ledger-service", "svc:card-processor-adapter", "svc:fx-rates-service", "svc:fraud-scoring", "svc:config-service", "svc:kafka-events", "svc:config-db", "svc:risk-rules", "svc:kyc-service", "svc:sanctions-screening", "svc:rules-store-db", "svc:ledger-db", "svc:audit-log"], "learned_edges": [], "facts": [], "incidents": [], "suspects": [], "note": "no memory yet: earlier agent sessions learned nothing about this service or its dependencies"}
```

## industry_matches

**Purpose:** Real public postmortems from other companies (Cloudflare, AWS, GitHub, Slack, ...) that share a root cause with an incident or a root-cause id.

**Track(s):** Track 3: Company Brain, Track 2: Agent Memory and Coordination, Track 1: Agents That Act on Connected Data

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"root_cause_id":{"type":"string","description":"'rc:<pattern>', e.g. from past_incidents' root_causes."},"incident_id":{"type":"string","description":"'inc:<year>-<nnn>'; uses its HAS_ROOT_CAUSE."},"limit":{"type":"integer","minimum":1,"maximum":10}}` (required: none)

**LLM-facing description:** Real public postmortems from other companies (Cloudflare, AWS, GitHub, Slack, ...) that share a root cause with an incident or a root-cause id. Pass exactly one of incident_id or root_cause_id. Returns company, title, url, a short summary in our own words, the shared root causes and overlapping terms, best match first.

**Cypher:**

```cypher
MATCH (i:Incident {id:$id})
OPTIONAL MATCH (i)-[:HAS_ROOT_CAUSE]->(rc:RootCause)
RETURN i.title, i.symptom, i.summary, collect(rc.id)
```

```cypher
MATCH (:Incident {id:$id})-[s:SIMILAR_TO]->(pm:PublicPostmortem) RETURN pm.id, s.score
```

```cypher
MATCH (pm:PublicPostmortem)-[:HAS_ROOT_CAUSE]->(rc:RootCause)
WHERE rc.id IN $rcs
RETURN pm.id, pm.company, pm.title, pm.url, pm.published_at, pm.summary, collect(DISTINCT rc.id)
```

**Explanation:** The industry-pattern layer: every tenant graph holds the same ~20 PublicPostmortem nodes, each HAS_ROOT_CAUSE -> RootCause. Incident -[:HAS_ROOT_CAUSE]-> RootCause <-[:HAS_ROOT_CAUSE]- PublicPostmortem is a two-hop join, so 'has anyone else had this?' is a graph query, not a web search. Ranked by number of shared root causes, then words shared with the incident's title/symptom/summary, then recency. SIMILAR_TO edges an agent already wrote are flagged as already_linked.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"root_cause_id": "rc:retry-storm", "limit": 2}`, 1 ms incl. Python):

```json
{"root_causes": ["rc:retry-storm"], "match_count": 2, "matches": [{"id": "pm:gcp-2025-06-12", "company": "Google Cloud", "title": "Multiple GCP products are experiencing Service issues", "url": "https://status.cloud.google.com/incidents/ow5i3PPK96RduMcb1SsW", "published": "2025-06-12", "summary": "A policy with blank fields replicated globally within seconds and hit new, unflagged Service Control code without error handling, which crashed in a loop. A kill switch disabled the path quickly, but restarting tasks without randomized backoff overloaded the Spanner backend in a large region, stretching recovery there by hours.", "shared_root_causes": ["rc:retry-storm"], "overlap_terms": []}, {"id": "pm:aws-2021-12-07", "company": "Amazon Web Services", "title": "Summary of the AWS Service Event in the Northern Virginia (US-EAST-1) Region", "url": "https://aws.amazon.com/message/12721/", "publi …
```

## rollback_safety

**Purpose:** Before recommending a rollback: is it safe? Shows later deploys to the same service (they would be rolled back too), whether the change looks irreversible (migration, schema, drop, rebuild...), and how many services depend on the changed one.

**Track(s):** Track 1: Agents That Act on Connected Data

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"deploy_id":{"type":"string","description":"'dep:<service>-v<version>' from a tool result."}}` (required: deploy_id)

**LLM-facing description:** Before recommending a rollback: is it safe? Shows later deploys to the same service (they would be rolled back too), whether the change looks irreversible (migration, schema, drop, rebuild...), and how many services depend on the changed one. Verdict 'safe' or 'risky' with reasons; risky means hold and page the owner instead.

**Cypher:**

```cypher
MATCH (d:Deploy {id:$id})-[:CHANGED]->(s:Service) RETURN s.id, s.tier, d.ts, d.version, d.summary
```

```cypher
MATCH (x:Deploy)-[:CHANGED]->(s:Service {id:$sid}) WHERE x.ts > $ts RETURN x.id, x.ts, x.summary ORDER BY x.ts
```

```cypher
MATCH (c:Service)-[:DEPENDS_ON*1..4]->(s:Service {id:$sid}) RETURN c.tier, count(DISTINCT c)
```

**Explanation:** Three small reads around the Deploy: the service it CHANGED, any later Deploy that CHANGED the same service (a rollback would take those with it), and how many services reach the changed one over DEPENDS_ON (who briefly sees the old version). The deploy summary is checked for words that mean the change touched data (migration, schema, drop, rebuild, delete, backfill, truncate, reindex): rolling back code does not undo those. Any later deploy or such a word makes the verdict 'risky'.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"deploy_id": "dep:risk-rules-v2.8.0"}`, 1 ms incl. Python):

```json
{"deploy": "dep:risk-rules-v2.8.0", "service": "svc:risk-rules", "service_tier": 1, "version": "2.8.0", "later_deploys": [], "dependents": 5, "tier1_dependents": 4, "hard_to_undo_terms": [], "verdict": "safe", "reasons": ["nothing shipped to risk-rules after it and nothing in the change looks irreversible"], "blast_of_rollback": "5 service(s) call risk-rules (directly or not), 4 of them tier-1: they briefly see the old version"}
```

## correlate_alerts

**Purpose:** Several alerts at once: the dependencies they share, ranked by how many of the alerting services reach each one (then alerting before silent, then fewer hops), with every alert's path to the top candidates.

**Track(s):** Track 1: Agents That Act on Connected Data

**FalkorDB algorithm:** algo.BFS (reach per alert) + algo.SPpaths (paths)

**Arguments:** `{"service_ids":{"type":"array","items":{"type":"string"},"minItems":1,"maxItems":12,"description":"The alerting service ids, e.g. ['svc:<name>', 'svc:<other>']."},"max_hops":{"type":"integer","minimum":1,"maximum":6,"description":"Max DEPENDS_ON hops."}}` (required: service_ids)

**LLM-facing description:** Several alerts at once: the dependencies they share, ranked by how many of the alerting services reach each one (then alerting before silent, then fewer hops), with every alert's path to the top candidates. A shared root that explains most alerts means one incident, not one per alert.

**Cypher:**

```cypher
UNWIND $ids AS sid
MATCH (s:Service {id:sid})
CALL algo.BFS(s, $depth, 'DEPENDS_ON') YIELD nodes
UNWIND nodes AS d
RETURN d.id, collect(DISTINCT sid)
```

```cypher
MATCH (c:Service)-[:DEPENDS_ON*1..6]->(s:Service) WHERE s.id IN $ids RETURN s.id, count(DISTINCT c)
```

```cypher
MATCH (a:Service {id:$from}), (b:Service {id:$to})
CALL algo.SPpaths({sourceNode: a, targetNode: b, relTypes: ['DEPENDS_ON'], relDirection: $dir, maxLen: $maxlen}) YIELD path
RETURN [x IN nodes(path) | x.id], [r IN relationships(path) | r.source], [r IN relationships(path) | startNode(r).id], [r IN relationships(path) | r.kind]
```

**Explanation:** Runs algo.BFS from every alerting service over DEPENDS_ON (what it calls, up to N hops) in one query, then counts, for every dependency, how many alerting services reach it (each alerting service counts for itself too: it may be the shared root). The candidates covering the most alerts are ranked: more alerts covered, then a candidate that is itself alerting, then fewer total hops. algo.SPpaths gives each alert's shortest path to the leading candidates, so the UI can draw the storm converging. Only two columns per row: FalkorDB 6.0.2 crashed on wide aggregation rows.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"service_ids": ["svc:auth-service", "svc:payouts-service", "svc:webhook-dispatcher", "svc:card-processor-adapter"]}`, 5 ms incl. Python):

```json
{"alerts": ["svc:auth-service", "svc:payouts-service", "svc:webhook-dispatcher", "svc:card-processor-adapter"], "max_hops": 6, "roots": [{"id": "svc:config-service", "covers": ["svc:auth-service", "svc:payouts-service", "svc:webhook-dispatcher"], "coverage": 3, "alerting": false, "total_hops": 3, "callers": 12, "paths": {"svc:auth-service": ["svc:auth-service", "svc:config-service"], "svc:payouts-service": ["svc:payouts-service", "svc:config-service"], "svc:webhook-dispatcher": ["svc:webhook-dispatcher", "svc:config-service"]}}, {"id": "svc:config-db", "covers": ["svc:auth-service", "svc:payouts-service", "svc:webhook-dispatcher"], "coverage": 3, "alerting": false, "total_hops": 6, "callers": 13, "paths": {"svc:auth-service": ["svc:auth-service", "svc:config-service", "svc:config-db"], "svc:payouts-service": ["svc:payouts-service", "svc:config-service", "svc:config-db"], "svc:webhook-dis …
```

## connected_impact

**Purpose:** Several alerts at once: which of them COULD share a cause.

**Track(s):** Track 1: Agents That Act on Connected Data

**FalkorDB algorithm:** algo.WCC (on a projection) + algo.BFS

**Arguments:** `{"service_ids":{"type":"array","items":{"type":"string"},"minItems":1,"maxItems":12,"description":"The alerting service ids, e.g. ['svc:<name>', 'svc:<other>']."}}` (required: service_ids)

**LLM-facing description:** Several alerts at once: which of them COULD share a cause. Projects the alerting services plus everything they call into a scratch graph and runs weakly connected components. Alerts in different components share no dependency at all, so they are separate incidents.

**Cypher:**

```cypher
UNWIND $ids AS sid
MATCH (s:Service {id:sid})
CALL algo.BFS(s, 6, 'DEPENDS_ON') YIELD nodes
UNWIND nodes AS d
RETURN DISTINCT d.id
```

```cypher
MATCH (a:Service)-[:DEPENDS_ON]->(b:Service) WHERE a.id IN $ids AND b.id IN $ids RETURN a.id, b.id
```

```cypher
UNWIND $ids AS i CREATE (:Service {id: i})
```

```cypher
UNWIND $pairs AS p MATCH (a:Service {id: p[0]}), (b:Service {id: p[1]}) CREATE (a)-[:DEPENDS_ON]->(b)
```

```cypher
CALL algo.WCC({nodeLabels: ['Service'], relationshipTypes: ['DEPENDS_ON']}) YIELD node, componentId
RETURN node.id, componentId
```

**Explanation:** algo.WCC over the whole service graph is useless here: every service reaches the same hubs, so it is one component. So the alerting services and their downstream closure (algo.BFS) are copied, with the DEPENDS_ON edges among them, into a scratch graph with the same labels, algo.WCC runs there, and the scratch graph is deleted at once (a few milliseconds). The tenant graph is only read. Two alerts in different components cannot have one cause: that is a lower bound on the number of incidents.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"service_ids": ["svc:auth-service", "svc:payouts-service", "svc:card-processor-adapter"]}`, 4 ms incl. Python):

```json
{"alerts": ["svc:auth-service", "svc:payouts-service", "svc:card-processor-adapter"], "projection": {"services": 11, "edges": 12}, "components": [{"alerts": ["svc:auth-service", "svc:payouts-service"], "size": 10}, {"alerts": ["svc:card-processor-adapter"], "size": 1}], "incidents_at_least": 2, "meaning": "alerts in different components share no dependency at all, so no single cause can explain them together"}
```

## blast_tiers

**Purpose:** Who calls a service, tier by tier (1 hop, 2 hops, ...), split into services that are already alerting and silent ones (the next to feel it: notify them, don't page them).

**Track(s):** Track 1: Agents That Act on Connected Data

**FalkorDB algorithm:** algo.SSpaths (incoming, shortest hops per caller)

**Arguments:** `{"service_id":{"type":"string","description":"Service id, 'svc:<name>'. Use find_service if unsure."},"alerting":{"type":"array","items":{"type":"string"},"maxItems":30},"max_hops":{"type":"integer","minimum":1,"maximum":6,"description":"Max DEPENDS_ON hops."}}` (required: service_id)

**LLM-facing description:** Who calls a service, tier by tier (1 hop, 2 hops, ...), split into services that are already alerting and silent ones (the next to feel it: notify them, don't page them).

**Cypher:**

```cypher
MATCH (s:Service {id:$id})
CALL algo.SSpaths({sourceNode: s, relTypes: ['DEPENDS_ON'], relDirection: 'incoming', maxLen: $depth, pathCount: 1000}) YIELD path, pathWeight
RETURN last(nodes(path)).id, min(pathWeight)
```

**Explanation:** algo.SSpaths from the service with relDirection 'incoming' enumerates paths to every caller; the shortest weight per caller is its tier (FalkorDB's algo.BFS only walks outgoing edges, so it can't do callers). Joined with the list of alerting services, the silent ones are the blast radius that has not fired yet.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"service_id": "svc:config-service", "alerting": ["svc:auth-service", "svc:payouts-service"], "max_hops": 2}`, 1 ms incl. Python):

```json
{"service": "svc:config-service", "max_hops": 2, "tiers": [{"hops": 1, "alerting": ["svc:auth-service", "svc:payouts-service"], "silent": ["svc:api-gateway", "svc:bank-connector", "svc:feature-flags", "svc:merchant-onboarding", "svc:notifications-service", "svc:payments-api", "svc:webhook-dispatcher"]}, {"hops": 2, "alerting": [], "silent": ["svc:merchant-dashboard", "svc:reconciliation-job", "svc:web-checkout"]}], "callers": 12, "silent_callers": ["svc:api-gateway", "svc:bank-connector", "svc:feature-flags", "svc:merchant-dashboard", "svc:merchant-onboarding", "svc:notifications-service", "svc:payments-api", "svc:reconciliation-job", "svc:web-checkout", "svc:webhook-dispatcher"], "meaning": "tier n = services that call this one at n hops (shortest); silent ones have not alerted yet"}
```

## failure_domains

**Purpose:** Community detection over the dependency graph (label propagation): which community each given service falls in.

**Track(s):** Track 1: Agents That Act on Connected Data

**FalkorDB algorithm:** algo.labelPropagation (CDLP)

**Arguments:** `{"service_ids":{"type":"array","items":{"type":"string"},"minItems":0,"maxItems":12,"description":"The alerting service ids, e.g. ['svc:<name>', 'svc:<other>']."}}` (required: none)

**LLM-facing description:** Community detection over the dependency graph (label propagation): which community each given service falls in. Context only: in a hub-heavy graph communities are coarse.

**Cypher:**

```cypher
CALL algo.labelPropagation({nodeLabels: ['Service'], relationshipTypes: ['DEPENDS_ON'], maxIterations: 20}) YIELD node, communityId
RETURN node.id, communityId
```

**Explanation:** algo.labelPropagation over Service/DEPENDS_ON groups services that are densely linked. Useful as context (are these alerts in one part of the system?), never as proof: in this graph everything links through a few hubs, so the result is two coarse communities. The planner reports it and decides nothing on it.

**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{"service_ids": ["svc:auth-service", "svc:card-processor-adapter"]}`, 4 ms incl. Python):

```json
{"algorithm": "algo.labelPropagation (CDLP) over DEPENDS_ON", "communities": 2, "sizes": [22, 5], "services": [{"id": "svc:auth-service", "community": 0, "community_size": 22}, {"id": "svc:card-processor-adapter", "community": 1, "community_size": 5}], "same_community": false, "caveat": "communities come from link density; in a hub-heavy graph they are coarse, so treat them as context, not as proof that alerts are related"}
```

## FalkorDB notes

- Variable-length paths use `p=(a)-[:DEPENDS_ON*1..N]->(b)`; `min(length(p))` gives shortest distance per target.
- A `MATCH` placed after `WITH … aggregate` can silently return nothing in FalkorDB, so aggregations are always the last step (in `RETURN`).
- `shortestPath()` is only allowed in `WITH`/`RETURN` in FalkorDB; `algo.SPpaths` is used instead.
- Full-text indexes are created with `CREATE FULLTEXT INDEX FOR (n:Label) ON (n.a, n.b)`.
