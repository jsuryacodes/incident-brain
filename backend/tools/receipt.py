"""ToolContext / ToolOutput and the Recorder that every tool runs its queries through.

result  -> small JSON for the LLM (<= MAX_RESULT_CHARS serialised).
receipt -> exact Cypher + params + highlight set, for the UI. The LLM never sees it.
Id-validation lookups (does svc:x exist?) are not recorded; every query that produced the answer is.
"""
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.db import get_graph
from seed.schema import LABEL_TO_PREFIX, PREFIX_TO_LABEL

MAX_RESULT_CHARS = 2500


@dataclass
class ToolContext:
    tenant: str = "kestrel_pay"
    now: int = field(default_factory=lambda: int(time.time()))  # not part of the LLM-facing schema
    session_id: str | None = None  # set by agent runs; write tools hang WRITTEN_IN / FOR_INCIDENT on it


@dataclass
class ToolOutput:
    result: dict
    receipt: dict


def clip(s, n=200):
    s = " ".join(str(s).split()) if s is not None else ""
    return s if len(s) <= n else s[: n - 1] + "…"


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if ts is not None else None


def minutes_ago(now, ts):
    return int((now - ts) // 60)


def days_ago(now, ts):
    return int((now - ts) // 86400) if ts is not None else None


def clamp(v, lo, hi, default):
    try:
        v = int(v)
    except (TypeError, ValueError):
        v = default
    return max(lo, min(hi, v))


ID_RE = re.compile(r"\b(?:" + "|".join(PREFIX_TO_LABEL) + r"):[A-Za-z0-9][A-Za-z0-9._\-]*")


def ids_in(obj):
    """Every id-shaped string (schema prefixes) anywhere inside obj (str / dict / list)."""
    text = obj if isinstance(obj, str) else json.dumps(obj, default=str, ensure_ascii=False)
    return {m.rstrip(".-") for m in ID_RE.findall(text)}


def norm(s):
    return " ".join(str(s or "").split())


Q_NODE_TEXT = "MATCH (n:__LABEL__ {id:$id}) RETURN [n.title, n.symptom, n.summary, n.text, n.rationale, n.steps, n.statement]"


def node_text(graph, node_id):
    """All human text of a node (title/symptom/summary/text/rationale/steps/statement), or None if it doesn't exist."""
    label = PREFIX_TO_LABEL.get(node_id.split(":", 1)[0]) if isinstance(node_id, str) and ":" in node_id else None
    if not label:
        return None
    rows = graph.ro_query(Q_NODE_TEXT.replace("__LABEL__", label), {"id": node_id}).result_set
    return "\n".join(str(x) for x in rows[0][0] if x) if rows else None


def excerpt_error(graph, node_id, excerpt, min_len=12):
    """None if excerpt is a literal (whitespace-normalised) substring of the node's text, else why not."""
    text = node_text(graph, node_id)
    if text is None:
        return f"source {node_id!r} does not exist"
    if len(norm(excerpt)) < min_len:
        return f"excerpt for {node_id} is too short; quote at least {min_len} characters verbatim"
    if norm(excerpt) not in norm(text):
        return f"excerpt is not a literal quote of {node_id}: {clip(excerpt, 80)!r}; copy the exact words from the source"
    return None


def _lists(obj, out):
    if isinstance(obj, dict):
        for v in obj.values():
            _lists(v, out)
    elif isinstance(obj, list):
        out.append(obj)
        for v in obj:
            _lists(v, out)


def fit(result, limit=MAX_RESULT_CHARS):
    """Safety net: drop the tail of the longest list until the serialised result fits. Marks truncated."""
    while len(json.dumps(result, default=str)) > limit:
        lists = []
        _lists(result, lists)
        lists = [l for l in lists if l]
        if not lists:
            break
        max(lists, key=lambda l: len(json.dumps(l, default=str))).pop()
        result["truncated"] = True
    return result


class Recorder:
    def __init__(self, ctx, tool, args):
        self.ctx, self.tool, self.args = ctx, tool, args
        self.graph = get_graph(ctx.tenant)
        self.queries, self.nodes, self.edges = [], [], []

    # --- queries (always read-only, always parameterised) ---
    def q(self, cypher, params=None):
        params = dict(params or {})
        self.queries.append({"cypher": " ".join(cypher.split()), "params": params})
        return self.graph.ro_query(cypher, params).result_set

    def check(self, node_id, label):
        """Return an error string if node_id is not an existing :label node, else None. Not recorded."""
        prefix = LABEL_TO_PREFIX[label] + ":"
        if not isinstance(node_id, str) or not node_id.startswith(prefix):
            return f"invalid {label.lower()} id {node_id!r}; ids look like '{prefix}<name>'" + (
                "; try find_service" if label == "Service" else "")
        found = self.graph.ro_query(f"MATCH (n:{label} {{id:$id}}) RETURN n.id", {"id": node_id}).result_set
        if not found:
            return f"unknown {label.lower()} id {node_id!r}" + ("; try find_service" if label == "Service" else "")
        return None

    # --- highlight ---
    def hl(self, *ids):
        self.nodes += [i for i in ids if i]

    def hl_edge(self, a, typ, b):
        self.nodes += [a, b]
        self.edges.append({"from": a, "type": typ, "to": b})

    def hl_path(self, ids, typ="DEPENDS_ON"):
        for a, b in zip(ids, ids[1:]):
            self.hl_edge(a, typ, b)

    # --- output ---
    def done(self, result, limit=MAX_RESULT_CHARS):
        seen_e, edges = set(), []
        for e in self.edges:
            k = (e["from"], e["type"], e["to"])
            if k not in seen_e:
                seen_e.add(k)
                edges.append(e)
        receipt = {"tool": self.tool, "args": self.args, "queries": self.queries,
                   "highlight": {"nodes": list(dict.fromkeys(self.nodes)), "edges": edges}}
        return ToolOutput(fit(result, limit), receipt)

    def error(self, msg):
        return ToolOutput({"error": msg}, {"tool": self.tool, "args": self.args, "queries": self.queries,
                                           "highlight": {"nodes": [], "edges": []}})
