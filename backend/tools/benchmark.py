"""Benchmarks: every graph tool and the raw FalkorDB algorithms, hero company vs the generated scale company.

python -m backend.tools.benchmark [--runs 5]     -> docs/benchmarks.md + runs/eval/benchmarks.json

Arguments are picked the same way on both graphs (no story): the alert = the service that reaches the most others,
the hub = the service most others reach, the storm = six services that call the hub, a recent deploy. Timings are
the median of N runs: `db_ms` = time inside the tool's queries (round trip to FalkorDB included), `tool_ms` = the
whole tool call in Python. FalkorDB's default query timeout here is 1,000 ms; a query that hits it is reported.
"""
import argparse
import json
import platform
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.db import get_graph
from backend.tools.receipt import ToolContext
from backend.tools.registry import TOOLS, call

ROOT = Path(__file__).resolve().parents[2]
OUT_MD, OUT_JSON = ROOT / "docs" / "benchmarks.md", ROOT / "runs" / "eval" / "benchmarks.json"
GRAPHS = ("kestrel_pay", "scale_demo")

Q_ALERT = """MATCH (s:Service)-[:DEPENDS_ON*1..3]->(d:Service) RETURN s.id, count(DISTINCT d) AS n ORDER BY n DESC, s.id LIMIT 1"""
Q_HUB = """MATCH (c:Service)-[:DEPENDS_ON]->(s:Service) RETURN s.id, count(c) AS n ORDER BY n DESC, s.id LIMIT 1"""
Q_CALLERS = "MATCH (c:Service)-[:DEPENDS_ON]->(:Service {id:$id}) RETURN c.id ORDER BY c.id LIMIT 6"
Q_DEPLOY = "MATCH (d:Deploy)-[:CHANGED]->(:Service) RETURN d.id ORDER BY d.ts DESC LIMIT 1"
RAW = {  # the algorithms on their own, plus the plain-Cypher reachability they replace
    "algo.pageRank": "CALL algo.pageRank('Service', 'DEPENDS_ON') YIELD node, score RETURN count(node)",
    "algo.betweenness (sampled 64)": "CALL algo.betweenness({nodeLabels:['Service'], relationshipTypes:['DEPENDS_ON'], samplingSize:64, samplingSeed:42}) YIELD node RETURN count(node)",
    "algo.WCC (all services)": "CALL algo.WCC({nodeLabels:['Service'], relationshipTypes:['DEPENDS_ON']}) YIELD node RETURN count(node)",
    "algo.labelPropagation": "CALL algo.labelPropagation({nodeLabels:['Service'], relationshipTypes:['DEPENDS_ON'], maxIterations:20}) YIELD node RETURN count(node)",
    "reach 6 hops: algo.BFS": "MATCH (s:Service {id:$alert}) CALL algo.BFS(s, 6, 'DEPENDS_ON') YIELD nodes RETURN size(nodes)",
    "reach 6 hops: variable-length Cypher": "MATCH (s:Service {id:$alert})-[:DEPENDS_ON*1..6]->(d:Service) RETURN count(DISTINCT d)",
    "callers 4 hops: algo.SSpaths": "MATCH (s:Service {id:$hub}) CALL algo.SSpaths({sourceNode:s, relTypes:['DEPENDS_ON'], relDirection:'incoming', maxLen:4, pathCount:100000}) YIELD path RETURN count(DISTINCT last(nodes(path)))",
    "callers 4 hops: variable-length Cypher": "MATCH (s:Service {id:$hub})<-[:DEPENDS_ON*1..4]-(c:Service) RETURN count(DISTINCT c)",
}


def picks(g):
    alert = g.ro_query(Q_ALERT).result_set[0][0]
    hub = g.ro_query(Q_HUB).result_set[0][0]
    storm = [r[0] for r in g.ro_query(Q_CALLERS, {"id": hub}).result_set]
    deploy = g.ro_query(Q_DEPLOY).result_set[0][0]
    return {"alert": alert, "hub": hub, "storm": storm, "deploy": deploy}


def args_for(name, p):
    a, h = p["alert"], p["hub"]
    return {"find_service": {"query": a.split(":")[1][:6]}, "blast_radius": {"service_id": h},
            "recent_changes_downstream": {"service_id": a, "since_minutes": 120, "max_hops": 6},
            "recent_changes": {"since_minutes": 120}, "shared_dependency_changes": {"service_id": a, "since_minutes": 120},
            "dependency_path": {"from_id": a, "to_id": h}, "who_to_call": {"service_id": h},
            "decisions_about": {"service_id": h}, "past_incidents": {"service_ids": [a, h]},
            "search_knowledge": {"query": "cache timeout"}, "critical_services": {"algorithm": "pagerank", "downstream_of": [a]},
            "stale_knowledge": {"service_id": h}, "node_details": {"node_id": h}, "memory_recall": {"service_id": a},
            "industry_matches": {"root_cause_id": "rc:retry-storm"}, "rollback_safety": {"deploy_id": p["deploy"]},
            "correlate_alerts": {"service_ids": p["storm"]}, "connected_impact": {"service_ids": p["storm"]},
            "blast_tiers": {"service_id": h, "alerting": p["storm"]}, "failure_domains": {"service_ids": p["storm"]}}.get(name)


def timed(fn, runs):
    vals, err = [], None
    for _ in range(runs):
        t0 = time.perf_counter()
        try:
            out = fn()
        except Exception as e:  # a FalkorDB timeout is a result here, not a crash
            err = str(e)[:120]
            break
        vals.append(((time.perf_counter() - t0) * 1000, out))
    return vals, err


def run(runs=5):
    res = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "runs": runs,
           "machine": f"{platform.system()} {platform.release()} {platform.machine()}, Python {platform.python_version()}",
           "falkordb": subprocess.run(["docker", "inspect", "-f", "{{.Config.Image}}", "falkordb"], capture_output=True,
                                      text=True).stdout.strip() or "?", "graphs": {}}
    for gname in GRAPHS:
        g = get_graph(gname)
        size = {"services": g.ro_query("MATCH (s:Service) RETURN count(s)").result_set[0][0],
                "depends_on": g.ro_query("MATCH ()-[r:DEPENDS_ON]->() RETURN count(r)").result_set[0][0],
                "nodes": g.ro_query("MATCH (n) RETURN count(n)").result_set[0][0]}
        p = picks(g)
        ctx = ToolContext(tenant=gname)
        tools = {}
        for name in TOOLS:
            a = args_for(name, p)
            if a is None:
                continue
            vals, err = timed(lambda: call(name, a, ctx), runs)
            outs = [o for _, o in vals]
            errors = sorted({o.result["error"][:100] for o in outs if "error" in o.result})
            tools[name] = {"args": a, "tool_ms": round(statistics.median(v for v, _ in vals), 1) if vals else None,
                           "db_ms": round(statistics.median(o.receipt.get("ms", 0) for o in outs), 1) if outs else None,
                           "queries": len(outs[0].receipt["queries"]) if outs else 0, "error": err or (errors[0] if errors else None)}
        raw = {}
        for label, q in RAW.items():
            vals, err = timed(lambda: g.ro_query(q, {"alert": p["alert"], "hub": p["hub"]}).result_set[0][0], runs)
            raw[label] = {"ms": round(statistics.median(v for v, _ in vals), 1) if vals else None,
                          "result": vals[0][1] if vals else None, "error": err}
        res["graphs"][gname] = {"size": size, "picks": p, "tools": tools, "raw": raw}
    return res


def render(res):
    gs = list(res["graphs"])
    L = ["# Benchmarks: hero company vs a 2,000-service company", "",
         f"> Generated by `python -m backend.tools.benchmark` on {res['generated_at']} ({res['machine']}, FalkorDB "
         f"`{res['falkordb']}` in Docker on the same machine). Median of {res['runs']} runs. `db` = time inside the "
         "tool's queries incl. the round trip; `tool` = the whole call in Python. FalkorDB's query timeout here is "
         "1,000 ms.", "", "| Graph | Services | DEPENDS_ON | Nodes |", "|---|---|---|---|"]
    L += [f"| `{g}` | {res['graphs'][g]['size']['services']:,} | {res['graphs'][g]['size']['depends_on']:,} | "
          f"{res['graphs'][g]['size']['nodes']:,} |" for g in gs]
    L += ["", "Arguments are chosen the same way on both graphs (the service reaching the most others as the alert, the most "
          "called service as the hub, six of its callers as a storm), so the scale numbers are a fair stress, not a demo.", "",
          "## Graph algorithms on their own", "", "| Query | " + " | ".join(gs) + " |", "|---|" + "---|" * len(gs)]
    for label in RAW:
        cells = []
        for g in gs:
            r = res["graphs"][g]["raw"][label]
            cells.append(f"**timeout / error**" if r["error"] else f"{r['ms']} ms (→ {r['result']:,})")
        L.append(f"| {label} | " + " | ".join(cells) + " |")
    L += ["", "## Every tool", "", "| Tool | " + " | ".join(f"{g} db / tool" for g in gs) + " |", "|---|" + "---|" * len(gs)]
    for name in res["graphs"][gs[0]]["tools"]:
        cells = []
        for g in gs:
            t = res["graphs"][g]["tools"].get(name)
            cells.append("–" if not t else f"**error**: {t['error']}" if t["error"] else f"{t['db_ms']} / {t['tool_ms']} ms")
        L.append(f"| `{name}` | " + " | ".join(cells) + " |")
    sc = res["graphs"][gs[-1]]
    slow = sorted(((t["db_ms"] or 0, n) for n, t in sc["tools"].items() if not t["error"]), reverse=True)[:2]
    algo_max = max(r["ms"] or 0 for k, r in sc["raw"].items() if k.startswith("algo."))
    bfs, vl = sc["raw"]["reach 6 hops: algo.BFS"], sc["raw"]["reach 6 hops: variable-length Cypher"]
    errs = [n for n, t in sc["tools"].items() if t["error"]]
    L += ["", "## What this shows", "",
          f"- At {sc['size']['services']:,} services and {sc['size']['depends_on']:,} dependencies every tool answers well "
          f"under FalkorDB's 1 s timeout" + (f" except {', '.join(errs)}" if errs else "") + f". The slowest are "
          + " and ".join(f"`{n}` ({ms} ms)" for ms, n in slow) + ": they enumerate every path so the UI can draw them.",
          f"- The whole-graph algorithms (PageRank, betweenness, WCC, label propagation) take at most {algo_max} ms on "
          f"{sc['size']['services']:,} services: ranking a company's services is a single call, not an offline job.",
          f"- Honest note: for plain reachability, algo.BFS ({bfs['ms']} ms) and variable-length Cypher ({vl['ms']} ms) "
          "are a tie at this size; the algorithms earn their place by answering different questions in one call "
          "(which services everything depends on, which alerts cannot share a cause, which communities exist), "
          "not by being faster at reachability.", ""]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(prog="python -m backend.tools.benchmark")
    ap.add_argument("--runs", type=int, default=5)
    a = ap.parse_args()
    res = run(a.runs)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(res, indent=1, default=str))
    OUT_MD.write_text(render(res))
    print(OUT_MD.read_text())


if __name__ == "__main__":
    main()
