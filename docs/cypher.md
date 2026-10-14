# Cypher queries & graph algorithms

> **Generated** by `python -m backend.tools.export_docs` from `backend/tools/registry.py`. Do not edit by hand.

Every product answer comes from one of these 15 fixed, parameterised, **read-only** tools (`graph.ro_query`). The LLM picks a tool and fills in arguments; it never writes Cypher. Each call also returns a *receipt* (the exact query, parameters and the nodes/edges used), which the UI shows.

- `$name` are query parameters. `N` in `*1..N` is a hop bound: variable-length bounds cannot be parameters, so it is clamped to an integer 1..6 before being written into the query.
- `(a)-[:DEPENDS_ON]->(b)` means *a calls b*. `source` on that edge is `declared` (catalog) or `learned` (written by an agent).
- Hackathon tracks: Track 1: Agents That Act on Connected Data; Track 2: Agent Memory and Coordination; Track 3: Company Brain.
- FalkorDB algorithms used: `algo.SPpaths`, `algo.pageRank`, `algo.betweenness`, and full-text `db.idx.fulltext.queryNodes`.

## Contents

| # | Tool | Track(s) | Algorithm |
|---|---|---|---|
| 1 | [`find_service`](#find_service) | Track 1: Agents That Act on Connected Data, Track 3: Company Brain | — |
| 2 | [`blast_radius`](#blast_radius) | Track 1: Agents That Act on Connected Data | — |
| 3 | [`recent_changes_downstream`](#recent_changes_downstream) | Track 1: Agents That Act on Connected Data | algo.SPpaths (shortest path per hit) |
| 4 | [`shared_dependency_changes`](#shared_dependency_changes) | Track 1: Agents That Act on Connected Data, Track 2: Agent Memory and Coordination | — |
| 5 | [`dependency_path`](#dependency_path) | Track 1: Agents That Act on Connected Data, Track 3: Company Brain | algo.SPpaths |
| 6 | [`who_to_call`](#who_to_call) | Track 1: Agents That Act on Connected Data, Track 2: Agent Memory and Coordination, Track 3: Company Brain | — |
| 7 | [`decisions_about`](#decisions_about) | Track 3: Company Brain, Track 2: Agent Memory and Coordination | — |
| 8 | [`past_incidents`](#past_incidents) | Track 1: Agents That Act on Connected Data, Track 3: Company Brain, Track 2: Agent Memory and Coordination | — |
| 9 | [`search_knowledge`](#search_knowledge) | Track 3: Company Brain, Track 2: Agent Memory and Coordination | db.idx.fulltext.queryNodes (RediSearch full-text) |
| 10 | [`critical_services`](#critical_services) | Track 1: Agents That Act on Connected Data, Track 3: Company Brain, Track 2: Agent Memory and Coordination | algo.pageRank / algo.betweenness |
| 11 | [`stale_knowledge`](#stale_knowledge) | Track 3: Company Brain, Track 2: Agent Memory and Coordination | — |
| 12 | [`node_details`](#node_details) | Track 1: Agents That Act on Connected Data, Track 3: Company Brain, Track 2: Agent Memory and Coordination | — |
| 13 | [`read_source`](#read_source) | Track 1: Agents That Act on Connected Data, Track 3: Company Brain | — |
| 14 | [`get_incident_state`](#get_incident_state) | Track 2: Agent Memory and Coordination | — |
| 15 | [`memory_recall`](#memory_recall) | Track 2: Agent Memory and Coordination, Track 1: Agents That Act on Connected Data | — |

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
RETURN s.id, s.name, s.tier, t.name
```

```cypher
MATCH (s:Service)<-[:OWNS]-(t:Team)
WHERE all(tok IN $tokens WHERE toLower(s.name) CONTAINS tok OR toLower(s.description) CONTAINS tok)
RETURN s.id, s.name, s.tier, t.name
```

**Explanation:** Lower-cases the query, turns spaces into hyphens and matches it against service name/id with CONTAINS. If nothing matches, falls back to requiring every word to appear in the name or description. Ranks exact, then prefix, then substring matches. Entry point for every conversation that starts from a name.

## blast_radius

**Purpose:** Which upstream services are hurt if this service fails (everything that transitively calls it).

**Track(s):** Track 1: Agents That Act on Connected Data

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"service_id":{"type":"string","description":"Service id, e.g. 'svc:payments-api'. Use find_service if unsure."},"max_hops":{"type":"integer","minimum":1,"maximum":6,"description":"Max DEPENDS_ON hops."}}` (required: service_id)

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

## recent_changes_downstream

**Purpose:** Likely cause of an alert: services DOWNSTREAM of the alerting service (things it calls) that were deployed recently.

**Track(s):** Track 1: Agents That Act on Connected Data

**FalkorDB algorithm:** algo.SPpaths (shortest path per hit)

**Arguments:** `{"service_id":{"type":"string","description":"Service id, e.g. 'svc:payments-api'. Use find_service if unsure."},"since_minutes":{"type":"integer","minimum":1,"description":"Look-back window in minutes."},"max_hops":{"type":"integer","minimum":1,"maximum":6,"description":"Max DEPENDS_ON hops."}}` (required: service_id)

**LLM-facing description:** Likely cause of an alert: services DOWNSTREAM of the alerting service (things it calls) that were deployed recently. Returns hops, the dependency path with each edge's source (declared/learned), the deploy, who shipped it and its ticket.

**Cypher:**

```cypher
MATCH p=(s:Service {id:$id})-[:DEPENDS_ON*1..N]->(d:Service)
MATCH (d)<-[:CHANGED]-(dep:Deploy) WHERE dep.ts > $since
OPTIONAL MATCH (who:Person)-[:DEPLOYED]->(dep)
OPTIONAL MATCH (dep)-[:FOR_TICKET]->(t:Ticket)
RETURN d.id, min(length(p)) AS hops, dep.id, dep.version, dep.ts, dep.summary, who.id, who.name, t.id, t.key, t.title
ORDER BY hops, dep.ts DESC
```

```cypher
MATCH (a:Service {id:$from}), (b:Service {id:$to})
CALL algo.SPpaths({sourceNode: a, targetNode: b, relTypes: ['DEPENDS_ON'], relDirection: $dir, maxLen: $maxlen}) YIELD path
RETURN [x IN nodes(path) | x.id], [r IN relationships(path) | r.source], [r IN relationships(path) | startNode(r).id], [r IN relationships(path) | r.kind]
```

**Explanation:** Follows DEPENDS_ON outwards from the alerting service and keeps services that have a Deploy newer than the window. Failures travel up the call chain, so a fresh deploy anywhere below is the prime suspect. Each hit gets its shortest path via algo.SPpaths, plus DEPLOYED (who) and FOR_TICKET (why the change was made).

## shared_dependency_changes

**Purpose:** Noisy-neighbour check: services that are NOT downstream of this one but share a dependency with it and were deployed recently.

**Track(s):** Track 1: Agents That Act on Connected Data, Track 2: Agent Memory and Coordination

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"service_id":{"type":"string","description":"Service id, e.g. 'svc:payments-api'. Use find_service if unsure."},"since_minutes":{"type":"integer","minimum":1,"description":"Look-back window in minutes."},"max_hops":{"type":"integer","minimum":1,"maximum":6,"description":"Max DEPENDS_ON hops."}}` (required: service_id)

**LLM-facing description:** Noisy-neighbour check: services that are NOT downstream of this one but share a dependency with it and were deployed recently. Shows the shared service and both paths with edge sources; learned edges can reveal neighbours that declared edges miss.

**Cypher:**

```cypher
MATCH (s:Service {id:$id})-[:DEPENDS_ON*1..6]->(x:Service) RETURN DISTINCT x.id
```

```cypher
MATCH p1=(s:Service {id:$id})-[:DEPENDS_ON*1..N]->(shared:Service),
      p2=(shared)<-[:DEPENDS_ON*1..N]-(n:Service)
MATCH (n)<-[:CHANGED]-(d:Deploy)
WHERE d.ts > $since AND n.id <> $id AND NOT n.id IN $downstream
OPTIONAL MATCH (who:Person)-[:DEPLOYED]->(d)
OPTIONAL MATCH (d)-[:FOR_TICKET]->(t:Ticket)
RETURN n.id, shared.id, d.id, d.version, d.ts, d.summary, who.id, who.name, t.id, t.key, t.title,
       [x IN nodes(p1) | x.id], [r IN relationships(p1) | r.source],
       [x IN nodes(p2) | x.id], [r IN relationships(p2) | r.source],
       [r IN relationships(p1) + relationships(p2) WHERE r.learned_from IS NOT NULL | r.learned_from]
ORDER BY length(p1) + length(p2), d.ts DESC
LIMIT 60
```

**Explanation:** Pattern (s)-[:DEPENDS_ON*]->(shared)<-[:DEPENDS_ON*]-(n)<-[:CHANGED]-(deploy): another service n hammers a dependency that s also needs. Services already downstream of s are excluded (that is recent_changes_downstream's job). This is the tool that gets smarter with memory: once an agent has written a learned DEPENDS_ON edge, the same query finds neighbours through it.

## dependency_path

**Purpose:** Shortest DEPENDS_ON path between two services, trying caller->callee first, then callee->caller, then either way.

**Track(s):** Track 1: Agents That Act on Connected Data, Track 3: Company Brain

**FalkorDB algorithm:** algo.SPpaths

**Arguments:** `{"from_id":{"type":"string","description":"Service id, e.g. 'svc:payments-api'. Use find_service if unsure."},"to_id":{"type":"string","description":"Service id, e.g. 'svc:payments-api'. Use find_service if unsure."}}` (required: from_id, to_id)

**LLM-facing description:** Shortest DEPENDS_ON path between two services, trying caller->callee first, then callee->caller, then either way. Returns the nodes, the direction that matched and each hop's source (declared/learned).

**Cypher:**

```cypher
MATCH (a:Service {id:$from}), (b:Service {id:$to})
CALL algo.SPpaths({sourceNode: a, targetNode: b, relTypes: ['DEPENDS_ON'], relDirection: $dir, maxLen: $maxlen}) YIELD path
RETURN [x IN nodes(path) | x.id], [r IN relationships(path) | r.source], [r IN relationships(path) | startNode(r).id], [r IN relationships(path) | r.kind]
```

**Explanation:** Calls FalkorDB's algo.SPpaths with relTypes ['DEPENDS_ON'] (no weight property needed; it counts hops) and tries relDirection outgoing, incoming, then both, reporting which matched. Each hop is returned with its source so answers can say 'via a dependency learned earlier'.

## who_to_call

**Purpose:** Who to page for a service.

**Track(s):** Track 1: Agents That Act on Connected Data, Track 2: Agent Memory and Coordination, Track 3: Company Brain

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"service_id":{"type":"string","description":"Service id, e.g. 'svc:payments-api'. Use find_service if unsure."}}` (required: service_id)

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

## decisions_about

**Purpose:** Recorded decisions about a service: what was decided, why, who decided (and whether they left), and the exact quoted source (chat thread, doc or ticket) as the receipt.

**Track(s):** Track 3: Company Brain, Track 2: Agent Memory and Coordination

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"service_id":{"type":"string","description":"Service id, e.g. 'svc:payments-api'. Use find_service if unsure."}}` (required: service_id)

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

## past_incidents

**Purpose:** Past incidents that touched any of the given services (affected them, or were caused by a deploy that changed them).

**Track(s):** Track 1: Agents That Act on Connected Data, Track 3: Company Brain, Track 2: Agent Memory and Coordination

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"service_ids":{"type":"array","items":{"type":"string"},"minItems":1,"maxItems":10,"description":"Service ids, e.g. ['svc:risk-rules']."},"limit":{"type":"integer","minimum":1,"maximum":10}}` (required: service_ids)

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

## search_knowledge

**Purpose:** Full-text search over docs, tickets, chat threads, decisions, incidents and runbooks.

**Track(s):** Track 3: Company Brain, Track 2: Agent Memory and Coordination

**FalkorDB algorithm:** db.idx.fulltext.queryNodes (RediSearch full-text)

**Arguments:** `{"query":{"type":"string"},"labels":{"type":"array","items":{"enum":["Doc","Ticket","ChatThread","Decision","Incident","Runbook"]},"description":"Subset of Doc, Ticket, ChatThread, Decision, Incident, Runbook."},"limit":{"type":"integer","minimum":1,"maximum":20}}` (required: query)

**LLM-facing description:** Full-text search over docs, tickets, chat threads, decisions, incidents and runbooks. Returns id, type, title, snippet around the match, date and author (and whether they left). Use for open questions; follow up with node_details.

**Cypher:**

```cypher
CALL db.idx.fulltext.queryNodes($label, $q) YIELD node, score
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(node)
RETURN node.id, score, coalesce(node.title, node.key), coalesce(node.text, node.rationale, node.summary, node.steps),
       coalesce(node.ts, node.updated_at, node.decided_at, node.started_at, node.created_at), a.name, a.status
ORDER BY score DESC LIMIT $limit
```

**Explanation:** Runs FalkorDB's full-text index per label. The query is stripped to plain words (no operator characters) and passed as a parameter. First pass requires all words (precise); if there is room, a second pass accepts any word (recall) ranked lower. Each index's scores are normalised to its best hit because scores are not comparable across indexes; ties go to raw sources (chats, docs, tickets) before derived summaries. No embeddings: the graph supplies context.

## critical_services

**Purpose:** Rank services by structural importance.

**Track(s):** Track 1: Agents That Act on Connected Data, Track 3: Company Brain, Track 2: Agent Memory and Coordination

**FalkorDB algorithm:** algo.pageRank / algo.betweenness

**Arguments:** `{"algorithm":{"enum":["pagerank","betweenness"]},"limit":{"type":"integer","minimum":1,"maximum":27}}` (required: none)

**LLM-facing description:** Rank services by structural importance. 'pagerank' finds shared dependencies many services rely on; 'betweenness' finds chokepoints on many call paths. Returns name, tier, team and score.

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

**Explanation:** PageRank over DEPENDS_ON passes credit from callers to callees, so heavily shared dependencies (config-service, its database, kafka-events) rise to the top: single points of failure. Betweenness counts shortest paths running through a node (sampled, fixed seed for repeatable results): it surfaces middle layers like payments-api and api-gateway that everything funnels through. Different questions: 'what do we all depend on' vs 'what sits in the middle'.

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

## node_details

**Purpose:** Drill down into any node by id: its label, properties (long text shortened), counts of edges by type and up to 25 neighbours.

**Track(s):** Track 1: Agents That Act on Connected Data, Track 3: Company Brain, Track 2: Agent Memory and Coordination

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"node_id":{"type":"string","description":"Any node id, e.g. 'chat:risk-eng-config-load'."}}` (required: node_id)

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

## read_source

**Purpose:** Read the full text (up to 1,800 chars) of a doc, ticket, chat thread, decision, runbook or incident, with title, author (and whether they left), date and what it mentions/describes.

**Track(s):** Track 1: Agents That Act on Connected Data, Track 3: Company Brain

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"node_id":{"type":"string","description":"e.g. 'chat:risk-eng-config-load', 'doc:risk-rules-readme', 'rb:fraud-scoring-latency'."}}` (required: node_id)

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

## get_incident_state

**Purpose:** The shared state of an incident: status, severity, affected services, cause (deploy/service), root causes, facts learned in its sessions, handoff notes from earlier agents (in order), actions taken (pages, tickets, writes), similar incidents and the resolution.

**Track(s):** Track 2: Agent Memory and Coordination

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"incident_id":{"type":"string","description":"Incident id, e.g. 'inc:2026-032'."}}` (required: incident_id)

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

## memory_recall

**Purpose:** Call FIRST on an alert: what earlier agent sessions learned about this service and its dependencies (DEPENDS_ON 1..3 hops).

**Track(s):** Track 2: Agent Memory and Coordination, Track 1: Agents That Act on Connected Data

**FalkorDB algorithm:** none (plain pattern matching)

**Arguments:** `{"service_id":{"type":"string","description":"Service id, e.g. 'svc:payments-api'. Use find_service if unsure."},"max_hops":{"type":"integer","minimum":1,"maximum":6,"description":"Max DEPENDS_ON hops."}}` (required: service_id)

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

## FalkorDB notes

- Variable-length paths use `p=(a)-[:DEPENDS_ON*1..N]->(b)`; `min(length(p))` gives shortest distance per target.
- A `MATCH` placed after `WITH … aggregate` can silently return nothing in FalkorDB, so aggregations are always the last step (in `RETURN`).
- `shortestPath()` is only allowed in `WITH`/`RETURN` in FalkorDB; `algo.SPpaths` is used instead.
- Full-text indexes are created with `CREATE FULLTEXT INDEX FOR (n:Label) ON (n.a, n.b)`.
