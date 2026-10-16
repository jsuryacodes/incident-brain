"""python -m backend.tools.export_docs  ->  docs/cypher.md (from the registry) and docs/postmortems.md (from the public postmortems seed)."""
import json
from pathlib import Path

from backend.tools.registry import ALL_TRACKS, TOOLS, call

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "cypher.md"
PM_OUT = ROOT / "docs" / "postmortems.md"


# one real call per tool, run against a fresh seed of the first company (pasted into docs/cypher.md as proof it runs)
EXAMPLES = {
    "find_service": {"query": "payments api"}, "blast_radius": {"service_id": "svc:config-service", "max_hops": 2},
    "recent_changes_downstream": {"service_id": "svc:payments-api"}, "recent_changes": {"since_minutes": 120},
    "shared_dependency_changes": {"service_id": "svc:payouts-service", "since_minutes": 120},
    "dependency_path": {"from_id": "svc:web-checkout", "to_id": "svc:risk-rules"},
    "who_to_call": {"service_id": "svc:risk-rules"}, "decisions_about": {"service_id": "svc:risk-rules"},
    "past_incidents": {"service_ids": ["svc:risk-rules"], "limit": 2}, "search_knowledge": {"query": "rules cache ttl", "limit": 3},
    "critical_services": {"algorithm": "pagerank", "limit": 4, "downstream_of": ["svc:payouts-service"]},
    "stale_knowledge": {"service_id": "svc:risk-rules"}, "node_details": {"node_id": "per:arjun-mehta"},
    "read_source": {"node_id": "dec:rules-cache-ttl"}, "memory_recall": {"service_id": "svc:payments-api"},
    "industry_matches": {"root_cause_id": "rc:retry-storm", "limit": 2}, "get_incident_state": {"incident_id": "inc:2025-031"},
    "correlate_alerts": {"service_ids": ["svc:auth-service", "svc:payouts-service", "svc:webhook-dispatcher", "svc:card-processor-adapter"]},
    "connected_impact": {"service_ids": ["svc:auth-service", "svc:payouts-service", "svc:card-processor-adapter"]},
    "blast_tiers": {"service_id": "svc:config-service", "alerting": ["svc:auth-service", "svc:payouts-service"], "max_hops": 2},
    "failure_domains": {"service_ids": ["svc:auth-service", "svc:card-processor-adapter"]},
    "rollback_safety": {"deploy_id": "dep:risk-rules-v2.8.0"},
}
DOCS_GRAPH = "kestrel_pay__eval_docs"


def verified_outputs():
    """{tool: (args, result json, ms)} from a fresh seed in a scratch twin (deleted afterwards)."""
    import time

    from backend.db import client
    from backend.tools.receipt import ToolContext
    from seed.load import load
    summary = load(DOCS_GRAPH, reset=True, data_package="kestrel_pay", quiet=True)
    ctx = ToolContext(tenant=DOCS_GRAPH, now=summary["now"])
    out = {}
    try:
        for name, args in EXAMPLES.items():
            if name in TOOLS:
                t0 = time.perf_counter()
                res = call(name, args, ctx).result
                out[name] = (args, res, (time.perf_counter() - t0) * 1000)
        mods = client().connection.execute_command("MODULE", "LIST")
        n = int(next((m[3] for m in mods if m[1] in (b"graph", "graph")), 0))
        ver = f"v{n // 10000}.{n // 100 % 100}.{n % 100}" if n else "?"
    finally:
        client().select_graph(DOCS_GRAPH).delete()
    return out, ver


def render(verified=None, version="?"):
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
         "- FalkorDB algorithms used: `algo.SPpaths`, `algo.SSpaths`, `algo.BFS`, `algo.WCC`, `algo.labelPropagation`, "
         "`algo.pageRank`, `algo.betweenness`, and full-text `db.idx.fulltext.queryNodes`.",
         f"- Every tool below was run against the live database while generating this file (FalkorDB graph module "
         f"{version}); its real output is pasted under it.",
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
        if verified and name in verified:
            args, res, ms = verified[name]
            text = json.dumps(res, ensure_ascii=False, default=str)
            L += ["", f"**Verified against the running FalkorDB** (fresh Kestrel Pay seed, `{json.dumps(args)}`, "
                      f"{ms:.0f} ms incl. Python):", "", "```json", text[:900] + (" …" if len(text) > 900 else ""), "```"]
    L += ["", "## FalkorDB notes", "",
          "- Variable-length paths use `p=(a)-[:DEPENDS_ON*1..N]->(b)`; `min(length(p))` gives shortest distance per target.",
          "- A `MATCH` placed after `WITH … aggregate` can silently return nothing in FalkorDB, so aggregations are always the last step (in `RETURN`).",
          "- `shortestPath()` is only allowed in `WITH`/`RETURN` in FalkorDB; `algo.SPpaths` is used instead.",
          "- Full-text indexes are created with `CREATE FULLTEXT INDEX FOR (n:Label) ON (n.a, n.b)`.", ""]
    return "\n".join(L)


def render_postmortems():
    d = json.loads((ROOT / "seed" / "data" / "public_postmortems.json").read_text())
    names = d["root_causes"]
    L = ["# Public postmortems (industry pattern layer)", "",
         "> **Generated** by `python -m backend.tools.export_docs` from `seed/data/public_postmortems.json`. Do not edit by hand.", "",
         f"{len(d['postmortems'])} real, publicly available incident write-ups from company engineering blogs and status pages. "
         "Each is loaded into **every** tenant graph as a `PublicPostmortem` node with `HAS_ROOT_CAUSE` edges, so "
         "`industry_matches` can answer \"has anyone else had this?\" with a two-hop graph query, and the postmortem pass "
         "writes `SIMILAR_TO {score, reason}` from a resolved incident to the best 1–2 matches.", "",
         "**The summaries are our own words** (≤ 60 words each), written after reading each linked page on 15 Oct 2026. "
         "They are not quotes; read the original for the authoritative account. Only pages whose facts could be checked "
         "on the page itself were included. `published` is the page's date, or the incident date when the page shows none.", "",
         "| Company | Title | Published | Our summary | Root-cause tags |", "|---|---|---|---|---|"]
    for p in sorted(d["postmortems"], key=lambda p: p["published_at"], reverse=True):
        tags = ", ".join(f"`{r}`" for r in p["root_causes"])
        L.append(f"| {p['company']} | [{p['title']}]({p['url']}) | {p['published_at']} | {p['summary']} | {tags} |")
    L += ["", "## Root-cause tags", "", "| id | name | meaning |", "|---|---|---|"]
    L += [f"| `{k}` | {n} | {desc} |" for k, (n, desc) in names.items()]
    L += ["", "A tenant that already defines one of these ids (Kestrel Pay defines `rc:cache-ttl-thundering-herd`, "
          "`rc:bad-config-push`, `rc:retry-storm`; Northwind Health `rc:retry-storm`) keeps its own name and description; "
          "the others are added by the loader.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    v, ver = verified_outputs()
    OUT.write_text(render(v, ver))
    PM_OUT.write_text(render_postmortems())
    print(f"wrote {OUT} ({len(OUT.read_text().splitlines())} lines) and {PM_OUT}")
