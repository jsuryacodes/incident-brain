"""Eval baseline 2, "graph, no algorithms": the same Firefighter, planner, loop and report, but no algo.* procedure.

Traversals stay (variable-length DEPENDS_ON paths, one-hop joins, full-text), so this answers "what do the graph
ALGORITHMS add on top of plain graph queries?". Tools whose answer IS an algorithm are removed; the shortest-path
helper the traversal tools use for display falls back to plain variable-length Cypher (ToolContext.algorithms=False),
and the eval checks that no algo.* query ran.
"""
from backend.tools.registry import TOOLS

# critical_services stays: with algorithms off it only runs its plain-Cypher 'fan_in' count (a fair stand-in for PageRank)
ALGORITHM_TOOLS = {n for n, t in TOOLS.items() if (t["algorithm"] or "").startswith("algo.")
                   and n not in ("recent_changes_downstream", "critical_services")}
TOOL_NAMES = sorted(set(TOOLS) - ALGORITHM_TOOLS)
PROFILE = {"title": "Graph, no algorithms", "tools": TOOL_NAMES, "algorithms": False,
           "about": "traversals and full-text only: no PageRank, betweenness, shortest-path or other algo.* procedure "
                    f"(removed: {', '.join(sorted(ALGORITHM_TOOLS))}; shortest paths become plain Cypher; instead of "
                    "PageRank, critical_services can only count how many services reach each one)"}
