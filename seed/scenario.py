"""World events for the demo (origin 'seed': they happen in the world, they are not agent memory).

python -m seed.scenario session2 --graph kestrel_pay
  adds dep:risk-rules-v2.8.1 (now - 5 min, by Leo Park, RISK-412 follow-up), so Session 2 is a fresh regression.
"""
import argparse
import os
import time

from dotenv import load_dotenv
from falkordb import FalkorDB

Q_SESSION2 = """MATCH (s:Service {id:'svc:risk-rules'}), (p:Person {id:'per:leo-park'}), (t:Ticket {id:'tkt:RISK-412'})
MERGE (d:Deploy {id:'dep:risk-rules-v2.8.1'})
  ON CREATE SET d.version = '2.8.1', d.ts = $ts, d.origin = 'seed', d.created_at = $now,
                d.summary = 'RISK-412 follow-up: re-enable 5s TTL for EU ruleset'
MERGE (p)-[:DEPLOYED]->(d)
MERGE (d)-[:CHANGED]->(s)
MERGE (d)-[:FOR_TICKET]->(t)
RETURN d.id, d.ts"""

SCENARIOS = {"session2": Q_SESSION2}


def apply(name, graph, now=None, graph_obj=None):
    now = int(now or time.time())
    load_dotenv()
    g = graph_obj or FalkorDB(host=os.getenv("FALKORDB_HOST", "localhost"),
                              port=int(os.getenv("FALKORDB_PORT", "6379"))).select_graph(graph)
    rows = g.query(SCENARIOS[name], {"ts": now - 5 * 60, "now": now}).result_set
    if not rows:
        raise RuntimeError(f"scenario {name}: risk-rules / Leo Park / RISK-412 not found in graph {graph!r}; seed it first")
    return rows[0][0]


def main():
    ap = argparse.ArgumentParser(prog="python -m seed.scenario")
    ap.add_argument("name", choices=sorted(SCENARIOS))
    ap.add_argument("--graph", required=True)
    a = ap.parse_args()
    print(f"{a.name}: added {apply(a.name, a.graph)} to {a.graph}")


if __name__ == "__main__":
    main()
