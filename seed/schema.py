"""Machine-readable copy of docs/schema.md (LOCKED v1). Change the doc first, then this file."""

PREFIX_TO_LABEL = {
    "team": "Team", "per": "Person", "svc": "Service", "dep": "Deploy", "doc": "Doc",
    "tkt": "Ticket", "chat": "ChatThread", "dec": "Decision", "inc": "Incident",
    "res": "Resolution", "rb": "Runbook", "rc": "RootCause", "pm": "PublicPostmortem",
    "fact": "Fact", "ses": "Session", "step": "Step",
}
LABEL_TO_PREFIX = {v: k for k, v in PREFIX_TO_LABEL.items()}
LABELS = list(PREFIX_TO_LABEL.values())

# Required props besides id/origin/created_at (optional ones are listed in OPTIONAL).
REQUIRED = {
    "Team": {"name"},
    "Person": {"name", "role", "email", "status", "joined_at"},
    "Service": {"name", "tier", "description", "language", "repo_url"},
    "Deploy": {"version", "ts", "summary"},
    "Doc": {"title", "text", "updated_at", "flagged_stale"},
    "Ticket": {"key", "title", "text", "kind", "status", "priority"},
    "ChatThread": {"channel", "title", "text", "ts"},
    "Decision": {"title", "rationale", "decided_at"},
    "Incident": {"key", "title", "severity", "status", "symptom", "summary", "started_at"},
    "Resolution": {"summary", "steps"},
    "Runbook": {"title", "steps", "version", "updated_at"},
    "RootCause": {"name", "description"},
    "PublicPostmortem": {"company", "title", "summary", "url", "published_at"},
    "Fact": {"statement", "confidence"},
    "Session": {"user", "mode", "status", "started_at"},
    "Step": {"seq", "agent", "action", "summary", "ts"},
}
OPTIONAL = {
    "Person": {"left_at"},
    "Incident": {"resolved_at"},
    "Session": {"ended_at"},
    "Step": {"tool", "cypher", "params_json"},
}
COMMON = {"id", "origin", "created_at"}

ENUMS = {
    ("Person", "status"): {"active", "left"},
    ("Service", "tier"): {1, 2, 3},
    ("Ticket", "kind"): {"bug", "task", "postmortem", "incident-followup"},
    ("Incident", "status"): {"open", "mitigated", "resolved"},
    ("Incident", "severity"): {1, 2, 3, 4},
    ("Session", "mode"): {"firefighter", "brain", "team"},
    ("Step", "agent"): {"triage", "investigator", "communicator", "brain"},
    ("Step", "action"): {"tool_call", "handoff", "write", "page", "answer"},
}

_SRC = ["Doc", "Ticket", "ChatThread"]
_CLAIM = ["Decision", "Fact", "Resolution", "Runbook"]
# edge type -> allowed (from_label, to_label) pairs
EDGE_RULES = {
    "MEMBER_OF": {("Person", "Team")},
    "OWNS": {("Team", "Service")},
    "MAINTAINS": {("Person", "Service")},
    "WORKED_ON": {("Person", "Service")},
    "DEPENDS_ON": {("Service", "Service")},
    "DEPLOYED": {("Person", "Deploy")},
    "CHANGED": {("Deploy", "Service")},
    "FOR_TICKET": {("Deploy", "Ticket")},
    "AUTHORED": {("Person", t) for t in _SRC + ["Runbook", "Decision"]},
    "MENTIONS": {(f, t) for f in _SRC for t in ["Service", "Person", "Incident"]},
    "DESCRIBES": {(f, "Service") for f in ["Doc", "Runbook"]},
    "ABOUT": {(f, t) for f in ["Decision", "Fact", "Ticket"] for t in ["Service", "Incident"]},
    "SOURCED_FROM": {(f, t) for f in _CLAIM for t in _SRC + ["Incident"]},
    "AFFECTED": {("Incident", "Service")},
    "CAUSED_BY": {("Incident", "Deploy"), ("Incident", "Service")},
    "HAS_ROOT_CAUSE": {("Incident", "RootCause"), ("PublicPostmortem", "RootCause")},
    "RESOLVED_BY": {("Incident", "Resolution")},
    "PERFORMED_BY": {("Resolution", "Person")},
    "SIMILAR_TO": {("Incident", "Incident"), ("Incident", "PublicPostmortem")},
    "SUPERSEDES": {("Runbook", "Runbook")},
    "FOR_INCIDENT": {("Session", "Incident")},
    "IN_SESSION": {("Step", "Session")},
    "NEXT": {("Step", "Step")},
    "CITED": {("Step", t) for t in LABELS},
    "WRITTEN_IN": {(f, "Session") for f in ["Fact", "Resolution", "Runbook", "Ticket", "Incident"]},
}

EDGE_PROPS = {  # type -> (required, optional)
    "WORKED_ON": ({"commits"}, {"last_at"}),
    "DEPENDS_ON": ({"kind", "source"}, {"learned_at", "learned_from"}),
    "SOURCED_FROM": ({"excerpt"}, set()),
    "SIMILAR_TO": (set(), {"score", "reason"}),
}
EDGE_ENUMS = {
    ("DEPENDS_ON", "kind"): {"sync", "async", "db", "cache"},
    ("DEPENDS_ON", "source"): {"declared", "learned"},
}

# --- indexes (schema.md §6) ---
AGENT_WRITABLE = ["Ticket", "Incident", "Resolution", "Runbook", "Fact", "Session", "Step"]
RANGE_INDEXES = (
    [(l, "id") for l in LABELS]
    + [("Deploy", "ts"), ("Incident", "started_at"), ("Incident", "status"), ("Person", "status")]
    + [(l, "origin") for l in AGENT_WRITABLE]
)
FULLTEXT_INDEXES = [
    ("Doc", ["title", "text"]), ("Ticket", ["title", "text"]), ("ChatThread", ["title", "text"]),
    ("Decision", ["title", "rationale"]), ("Incident", ["title", "summary"]),
    ("Runbook", ["title", "steps"]),
]


def is_time_prop(name):
    return name == "ts" or name.endswith("_at")
