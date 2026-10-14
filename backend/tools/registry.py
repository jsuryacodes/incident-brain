"""TOOLS: name -> {fn, description (for the LLM), input_schema (JSON Schema), track, explanation (for humans), cypher, algorithm}.

`track` uses the hackathon's official track names (ALL_TRACKS below).
"""
from backend.tools import graph_tools as gt
from backend.tools.receipt import ToolContext, ToolOutput

F = "Track 1: Agents That Act on Connected Data"  # Firefighter: traversal + algorithm tools
T = "Track 2: Agent Memory and Coordination"  # team memory: how learned memory gets used
B = "Track 3: Company Brain"  # Ask the Brain: company knowledge
ALL_TRACKS = (F, T, B)


def _obj(props, required=()):
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


_SVC = {"type": "string", "description": "Service id, e.g. 'svc:payments-api'. Use find_service if unsure."}
_SINCE = {"type": "integer", "minimum": 1, "description": "Look-back window in minutes."}
_HOPS = {"type": "integer", "minimum": 1, "maximum": 6, "description": "Max DEPENDS_ON hops."}

TOOLS = {
    "find_service": dict(
        fn=gt.find_service, track=[F, B],
        description="Resolve a fuzzy service name like 'payments api' to service ids. Use first when you only have a name. Returns up to 5 matches with team and tier.",
        input_schema=_obj({"query": {"type": "string", "description": "Name or part of a name."}}, ["query"]),
        cypher=[gt.Q_FIND, gt.Q_FIND_TOKENS], algorithm=None,
        explanation="Lower-cases the query, turns spaces into hyphens and matches it against service name/id with CONTAINS. If nothing matches, falls back to requiring every word to appear in the name or description. Ranks exact, then prefix, then substring matches. Entry point for every conversation that starts from a name."),
    "blast_radius": dict(
        fn=gt.blast_radius, track=[F],
        description="Which upstream services are hurt if this service fails (everything that transitively calls it). Returns each with tier, owning team and minimum hops, tier-1 first.",
        input_schema=_obj({"service_id": _SVC, "max_hops": _HOPS}, ["service_id"]),
        cypher=[gt.Q_BLAST, gt.Q_BLAST_EDGES], algorithm=None,
        explanation="Walks DEPENDS_ON edges backwards (callers of callers) up to N hops. `a DEPENDS_ON b` means a calls b, so if b fails, every a that reaches b is affected. min(length(p)) keeps the shortest distance per service; sorting by tier puts customer-critical services first. The second query returns the edges of all those paths so the UI can draw them (and flags any learned edge)."),
    "recent_changes_downstream": dict(
        fn=gt.recent_changes_downstream, track=[F],
        description="Likely cause of an alert: services DOWNSTREAM of the alerting service (things it calls) that were deployed recently. Returns hops, the dependency path with each edge's source (declared/learned), the deploy, who shipped it and its ticket.",
        input_schema=_obj({"service_id": _SVC, "since_minutes": _SINCE, "max_hops": _HOPS}, ["service_id"]),
        cypher=[gt.Q_RECENT, gt.Q_SP], algorithm="algo.SPpaths (shortest path per hit)",
        explanation="Follows DEPENDS_ON outwards from the alerting service and keeps services that have a Deploy newer than the window. Failures travel up the call chain, so a fresh deploy anywhere below is the prime suspect. Each hit gets its shortest path via algo.SPpaths, plus DEPLOYED (who) and FOR_TICKET (why the change was made)."),
    "shared_dependency_changes": dict(
        fn=gt.shared_dependency_changes, track=[F, T],
        description="Noisy-neighbour check: services that are NOT downstream of this one but share a dependency with it and were deployed recently. Shows the shared service and both paths with edge sources; learned edges can reveal neighbours that declared edges miss.",
        input_schema=_obj({"service_id": _SVC, "since_minutes": _SINCE, "max_hops": _HOPS}, ["service_id"]),
        cypher=[gt.Q_DOWNSTREAM, gt.Q_SHARED], algorithm=None,
        explanation="Pattern (s)-[:DEPENDS_ON*]->(shared)<-[:DEPENDS_ON*]-(n)<-[:CHANGED]-(deploy): another service n hammers a dependency that s also needs. Services already downstream of s are excluded (that is recent_changes_downstream's job). This is the tool that gets smarter with memory: once an agent has written a learned DEPENDS_ON edge, the same query finds neighbours through it."),
    "dependency_path": dict(
        fn=gt.dependency_path, track=[F, B],
        description="Shortest DEPENDS_ON path between two services, trying caller->callee first, then callee->caller, then either way. Returns the nodes, the direction that matched and each hop's source (declared/learned).",
        input_schema=_obj({"from_id": _SVC, "to_id": _SVC}, ["from_id", "to_id"]),
        cypher=[gt.Q_SP], algorithm="algo.SPpaths",
        explanation="Calls FalkorDB's algo.SPpaths with relTypes ['DEPENDS_ON'] (no weight property needed; it counts hops) and tries relDirection outgoing, incoming, then both, reporting which matched. Each hop is returned with its source so answers can say 'via a dependency learned earlier'."),
    "who_to_call": dict(
        fn=gt.who_to_call, track=[F, T, B],
        description="Who to page for a service. Returns the official maintainer (and whether they left), a bus_factor_risk flag, ranked active candidates with transparent signals (commits, recency, past incident resolutions) and the owning team as fallback.",
        input_schema=_obj({"service_id": _SVC}, ["service_id"]),
        cypher=[gt.Q_MAINT, gt.Q_WORKERS, gt.Q_RES_AFFECTED, gt.Q_RES_DEPLOY, gt.Q_TEAM], algorithm=None,
        explanation="Expertise is computed, not stored. MAINTAINS gives the official owner (flagged if they left); WORKED_ON gives commits; incidents that AFFECTED the service or were CAUSED_BY a deploy that CHANGED it give the people who actually fixed things (PERFORMED_BY). Score = commits + 25 x resolutions, so one real incident fix counts like 25 commits. bus_factor_risk is true if the maintainer left or at most one active person has touched the service."),
    "decisions_about": dict(
        fn=gt.decisions_about, track=[B, T],
        description="Recorded decisions about a service: what was decided, why, who decided (and whether they left), and the exact quoted source (chat thread, doc or ticket) as the receipt.",
        input_schema=_obj({"service_id": _SVC}, ["service_id"]),
        cypher=[gt.Q_DECISIONS], algorithm=None,
        explanation="Decision -ABOUT-> Service, with AUTHORED for the author and SOURCED_FROM for the provenance edge carrying the verbatim excerpt. One hop from claim to evidence: 'show the receipt'."),
    "past_incidents": dict(
        fn=gt.past_incidents, track=[F, B, T],
        description="Past incidents that touched any of the given services (affected them, or were caused by a deploy that changed them). Returns root cause, how it was resolved and by whom, sources, and SIMILAR_TO links, including incidents written by agents in earlier sessions.",
        input_schema=_obj({"service_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                           "description": "Service ids, e.g. ['svc:risk-rules']."},
                           "limit": {"type": "integer", "minimum": 1, "maximum": 10}}, ["service_ids"]),
        cypher=[gt.Q_INC_AFFECTED, gt.Q_INC_DEPLOY, gt.Q_INC_DETAIL], algorithm=None,
        explanation="Two routes into an incident: AFFECTED (it hurt the service) and CAUSED_BY a Deploy that CHANGED the service (it came from there). Ranked by how many of the given services it touches, then recency. Detail query follows HAS_ROOT_CAUSE, RESOLVED_BY, PERFORMED_BY and SOURCED_FROM; SIMILAR_TO is read in both directions so links written by agents show up. Nothing filters on origin, so agent-written incidents are recalled too."),
    "search_knowledge": dict(
        fn=gt.search_knowledge, track=[B, T],
        description="Full-text search over docs, tickets, chat threads, decisions, incidents and runbooks (also root causes and public postmortems if listed in labels). Returns id, type, title, snippet around the match, date and author (and whether they left). Use for open questions; follow up with node_details.",
        input_schema=_obj({"query": {"type": "string"},
                           "labels": {"type": "array", "items": {"enum": gt.SEARCH_LABELS},
                                      "description": "Subset of Doc, Ticket, ChatThread, Decision, Incident, Runbook (the default), or RootCause / PublicPostmortem (only when listed)."},
                           "limit": {"type": "integer", "minimum": 1, "maximum": 20}}, ["query"]),
        cypher=[gt.Q_SEARCH], algorithm="db.idx.fulltext.queryNodes (RediSearch full-text)",
        explanation="Runs FalkorDB's full-text index per label. The query is stripped to plain words (no operator characters) and passed as a parameter. First pass requires all words (precise); if there is room, a second pass accepts any word (recall) ranked lower. Each index's scores are normalised to its best hit because scores are not comparable across indexes; ties go to raw sources (chats, docs, tickets) before derived summaries. No embeddings: the graph supplies context."),
    "critical_services": dict(
        fn=gt.critical_services, track=[F, B, T],
        description="Rank services by structural importance. 'pagerank' finds shared dependencies many services rely on; 'betweenness' finds chokepoints on many call paths. Returns name, tier, team and score.",
        input_schema=_obj({"algorithm": {"enum": ["pagerank", "betweenness"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 27}}),
        cypher=[gt.Q_PAGERANK, gt.Q_BETWEENNESS], algorithm="algo.pageRank / algo.betweenness",
        explanation="PageRank over DEPENDS_ON passes credit from callers to callees, so heavily shared dependencies (config-service, its database, kafka-events) rise to the top: single points of failure. Betweenness counts shortest paths running through a node (sampled, fixed seed for repeatable results): it surfaces middle layers like payments-api and api-gateway that everything funnels through. Different questions: 'what do we all depend on' vs 'what sits in the middle'."),
    "stale_knowledge": dict(
        fn=gt.stale_knowledge, track=[B, T],
        description="Docs and runbooks that are probably out of date, with reasons: author_left, names_departed_person, old_vs_changes (>1 year old but the service kept deploying), missing_learned_dependency (a dependency was learned after the doc was written). Omit service_id to scan everything.",
        input_schema=_obj({"service_id": {"type": ["string", "null"], "description": "Service id, or null for all."}}),
        cypher=[gt.Q_STALE], algorithm=None,
        explanation="Documentation rots in ways the graph can see: the AUTHORED person has status left, the text MENTIONS a departed person, the document is older than a year while the service it DESCRIBES kept getting CHANGED by deploys, or a DEPENDS_ON edge with source 'learned' was written after the document's updated_at. Only items with at least one reason are returned."),
    "node_details": dict(
        fn=gt.node_details, track=[F, B, T],
        description="Drill down into any node by id: its label, properties (long text shortened), counts of edges by type and up to 25 neighbours. Use to 'show the source' for an id returned by another tool.",
        input_schema=_obj({"node_id": {"type": "string", "description": "Any node id, e.g. 'chat:risk-eng-config-load'."}}, ["node_id"]),
        cypher=[gt.Q_NODE, gt.Q_NEIGHBOURS], algorithm=None,
        explanation="Looks the node up by its prefixed id (the prefix selects the label, so the index on id is used) and lists one-hop neighbours with edge type and direction. Neighbours are taken round-robin across edge types so a node with many mentions still shows its maintainer, dependencies and owner."),
    "read_source": dict(
        fn=gt.read_source, track=[F, B],
        description="Read the full text (up to 1,800 chars) of a doc, ticket, chat thread, decision, runbook or incident, with title, author (and whether they left), date and what it mentions/describes. node_details only shows 200 chars; use this to read a source and quote it verbatim.",
        input_schema=_obj({"node_id": {"type": "string", "description": "e.g. 'chat:risk-eng-config-load', 'doc:risk-rules-readme', 'rb:fraud-scoring-latency'."}}, ["node_id"]),
        cypher=[gt.Q_SOURCE, gt.Q_SOURCE_LINKS, gt.Q_SUPERSEDED_BY], algorithm=None,
        explanation="Looks the node up by its prefixed id and returns its main text field (text, rationale, steps or summary) with AUTHORED for the author and the outgoing MENTIONS / DESCRIBES / ABOUT / SUPERSEDES / SOURCED_FROM links. Agents need the full text because key chat lines sit deep in a thread, and every excerpt they write must be a literal quote of it."),
    "get_incident_state": dict(
        fn=gt.get_incident_state, track=[T],
        description="The shared state of an incident: status, severity, affected services, cause (deploy/service), root causes, facts learned in its sessions, handoff notes from earlier agents (in order), actions taken (pages, tickets, writes), similar incidents and the resolution.",
        input_schema=_obj({"incident_id": {"type": "string", "description": "Incident id, e.g. 'inc:2026-032'."}}, ["incident_id"]),
        cypher=[gt.Q_STATE, gt.Q_STATE_AFFECTED, gt.Q_STATE_CAUSE, gt.Q_STATE_RC, gt.Q_STATE_FACTS, gt.Q_STATE_STEPS,
                gt.Q_STATE_TICKETS, gt.Q_STATE_SIMILAR, gt.Q_STATE_RESOLUTION], algorithm=None,
        explanation="This is how agents hand off: each agent starts with an empty conversation and reads the incident's state from the graph. Sessions point at the incident (FOR_INCIDENT); their Steps (IN_SESSION) with action 'handoff' carry the notes, and Facts WRITTEN_IN those sessions are what the team learned. Nine small queries instead of one big one, because FalkorDB drops rows when a MATCH follows an aggregation."),
    "memory_recall": dict(
        fn=gt.memory_recall, track=[T, F],
        description="Call FIRST on an alert: what earlier agent sessions learned about this service and its dependencies (DEPENDS_ON 1..3 hops). Returns learned dependencies (with the Fact, quoted source and session), agent-written facts, incidents agents resolved (cause, root cause, who fixed it and how, latest runbook steps) and `suspects`: services that memory points at, each with relation 'downstream' or 'shares_dependency'. Empty when nothing was learned yet.",
        input_schema=_obj({"service_id": _SVC, "max_hops": _HOPS}, ["service_id"]),
        cypher=[gt.Q_RECALL_SCOPE, gt.Q_RECALL_LEARNED, gt.Q_RECALL_FACTS, gt.Q_RECALL_INCIDENTS, gt.Q_RECALL_RUNBOOKS],
        algorithm=None,
        explanation="Memory-first recall. The scope is the alerting service plus everything it calls within N hops (declared or learned edges). Then four small queries: learned DEPENDS_ON edges touching the scope (with the Fact on learned_from, its SOURCED_FROM excerpt and the Session it was WRITTEN_IN); other agent Facts ABOUT scope services; incidents with origin 'agent' and status 'resolved' that AFFECTED the scope (CAUSED_BY, HAS_ROOT_CAUSE, RESOLVED_BY, PERFORMED_BY); and for those incidents the newest runbook, found by following SUPERSEDES*0..5 back to a runbook that nothing supersedes. A learned edge into one of my dependencies makes its caller a noisy-neighbour suspect; a learned edge on my own path or the cause of a recalled incident makes that service a suspect too. Only agent-written memory is recalled: seeded history stays with past_incidents, so a first session honestly recalls nothing."),
    "industry_matches": dict(
        fn=gt.industry_matches, track=[B, T, F],
        description="Real public postmortems from other companies (Cloudflare, AWS, GitHub, Slack, ...) that share a root cause with an incident or a root-cause id. Pass exactly one of incident_id or root_cause_id. Returns company, title, url, a short summary in our own words, the shared root causes and overlapping terms, best match first.",
        input_schema=_obj({"root_cause_id": {"type": "string", "description": "e.g. 'rc:bad-config-push'."},
                           "incident_id": {"type": "string", "description": "e.g. 'inc:2026-032'; uses its HAS_ROOT_CAUSE."},
                           "limit": {"type": "integer", "minimum": 1, "maximum": 10}}),
        cypher=[gt.Q_IND_INCIDENT, gt.Q_IND_LINKED, gt.Q_IND_MATCHES], algorithm=None,
        explanation="The industry-pattern layer: every tenant graph holds the same ~20 PublicPostmortem nodes, each HAS_ROOT_CAUSE -> RootCause. Incident -[:HAS_ROOT_CAUSE]-> RootCause <-[:HAS_ROOT_CAUSE]- PublicPostmortem is a two-hop join, so 'has anyone else had this?' is a graph query, not a web search. Ranked by number of shared root causes, then words shared with the incident's title/symptom/summary, then recency. SIMILAR_TO edges an agent already wrote are flagged as already_linked."),
}


def call(name, args=None, ctx=None, table=None):
    """Dispatch by name (table: TOOLS by default, or memory_tools.MEMORY_TOOLS). Unknown tools / missing or
    unexpected args come back as an error result, never an exception."""
    table = TOOLS if table is None else table
    ctx = ctx or ToolContext()
    args = dict(args or {})
    err = None
    if name not in table:
        err = f"unknown tool {name!r}; available: {sorted(table)}"
    else:
        schema = table[name]["input_schema"]
        extra = sorted(set(args) - set(schema["properties"]))
        missing = [r for r in schema["required"] if r not in args]
        if extra or missing:
            err = f"{name}: " + "; ".join(x for x in (f"unexpected args {extra}" if extra else "",
                                                       f"missing required args {missing}" if missing else "") if x)
    if err:
        return ToolOutput({"error": err}, {"tool": name, "args": args, "queries": [], "highlight": {"nodes": [], "edges": []}})
    return table[name]["fn"](ctx, **args)


def llm_tool_specs():
    """Anthropic-style tool definitions (what step 4 sends to the model)."""
    return [{"name": n, "description": t["description"], "input_schema": t["input_schema"]} for n, t in TOOLS.items()]
