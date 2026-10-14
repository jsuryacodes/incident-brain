"""python -m backend.tools.export_docs  ->  docs/cypher.md, generated from the registry."""
import json
from pathlib import Path

from backend.tools.registry import ALL_TRACKS, TOOLS

OUT = Path(__file__).resolve().parents[2] / "docs" / "cypher.md"


def render():
    L = ["# Cypher queries & graph algorithms",
         "",
         "> **Generated** by `python -m backend.tools.export_docs` from `backend/tools/registry.py`. Do not edit by hand.",
         "",
         f"Every product answer comes from one of these {len(TOOLS)} fixed, parameterised, **read-only** tools "
         "(`graph.ro_query`). The LLM picks a tool and fills in arguments; it never writes Cypher. "
         "Each call also returns a *receipt* (the exact query, parameters and the nodes/edges used), which the UI shows.",
         "",
         "- `$name` are query parameters. `N` in `*1..N` is a hop bound: variable-length bounds cannot be parameters, "
         "so it is clamped to an integer 1..6 before being written into the query.",
         "- `(a)-[:DEPENDS_ON]->(b)` means *a calls b*. `source` on that edge is `declared` (catalog) or `learned` (written by an agent).",
         f"- Hackathon tracks: {'; '.join(ALL_TRACKS)}.",
         "- FalkorDB algorithms used: `algo.SPpaths`, `algo.pageRank`, `algo.betweenness`, and full-text `db.idx.fulltext.queryNodes`.",
         "",
         "## Contents",
         "",
         "| # | Tool | Track(s) | Algorithm |",
         "|---|---|---|---|"]
    for i, (name, t) in enumerate(TOOLS.items(), 1):
        L.append(f"| {i} | [`{name}`](#{name}) | {', '.join(t['track'])} | {t['algorithm'] or '—'} |")
    for name, t in TOOLS.items():
        purpose = t["description"].split(". ")[0].rstrip(".") + "."
        L += ["", f"## {name}", "", f"**Purpose:** {purpose}", "", f"**Track(s):** {', '.join(t['track'])}",
              "", f"**FalkorDB algorithm:** {t['algorithm'] or 'none (plain pattern matching)'}", "",
              f"**Arguments:** `{json.dumps(t['input_schema']['properties'], separators=(',', ':'))}` "
              f"(required: {', '.join(t['input_schema']['required']) or 'none'})", "",
              f"**LLM-facing description:** {t['description']}", "", "**Cypher:**", ""]
        for q in t["cypher"]:
            L += ["```cypher", q.replace("__N__", "N").replace("__LABEL__", "<Label from id prefix>"), "```", ""]
        L += ["**Explanation:** " + t["explanation"]]
    L += ["", "## FalkorDB notes", "",
          "- Variable-length paths use `p=(a)-[:DEPENDS_ON*1..N]->(b)`; `min(length(p))` gives shortest distance per target.",
          "- A `MATCH` placed after `WITH … aggregate` can silently return nothing in FalkorDB, so aggregations are always the last step (in `RETURN`).",
          "- `shortestPath()` is only allowed in `WITH`/`RETURN` in FalkorDB; `algo.SPpaths` is used instead.",
          "- Full-text indexes are created with `CREATE FULLTEXT INDEX FOR (n:Label) ON (n.a, n.b)`.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    OUT.write_text(render())
    print(f"wrote {OUT} ({len(OUT.read_text().splitlines())} lines)")
