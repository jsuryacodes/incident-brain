"""Prove the planted stories hold.  python -m seed.verify --graph kestrel_pay [--now EPOCH]
Prints every Cypher query it runs (the receipts) and PASS/FAIL per check; exits 1 on any failure.
'Recent' checks are relative to now: run right after loading (or pass the same --now as the load)."""
import argparse
import os
import sys
import time

from dotenv import load_dotenv
from falkordb import FalkorDB

from seed import schema

TARGETS = {  # label -> target count (±30%); 0 means must be exactly 0
    "Team": 4, "Service": 27, "Person": 20, "Deploy": 30, "Doc": 12, "Ticket": 15, "ChatThread": 10,
    "Decision": 5, "Incident": 6, "Resolution": 6, "Runbook": 3, "RootCause": 5,
    "PublicPostmortem": 0, "Fact": 0, "Session": 0, "Step": 0,
}
EXACT = {"Team", "Service"}
PA, RR, CS = "svc:payments-api", "svc:risk-rules", "svc:config-service"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True)
    ap.add_argument("--now", type=int, default=int(time.time()))
    ap.add_argument("--data", help="which seed's checks to run (default: the graph name if known, else kestrel_pay)")
    args = ap.parse_args()
    pkg = args.data or (args.graph if args.graph in ("kestrel_pay", "northwind_health") else "kestrel_pay")
    load_dotenv()
    g = FalkorDB(host=os.getenv("FALKORDB_HOST", "localhost"), port=int(os.getenv("FALKORDB_PORT", "6379"))).select_graph(args.graph)
    since = args.now - 2 * 3600
    results = []

    def q(cypher, params=None):
        print("    cypher>", " ".join(cypher.split()), "" if not params else f"   {params}")
        return g.query(cypher, params).result_set

    def check(n, name, fn):
        print(f"\n[{n}] {name}")
        try:
            ok, detail = fn()
        except Exception as e:  # a crashing check is a failing check
            ok, detail = False, f"error: {e}"
        print(f"  {'PASS' if ok else 'FAIL'}  {detail}")
        results.append(ok)

    def c1():
        got = {l: c for l, c in q("MATCH (n) RETURN labels(n)[0], count(n)")}
        bad = []
        for label, target in TARGETS.items():
            n = got.get(label, 0)
            lo, hi = (target, target) if label in EXACT or target == 0 else (target * 0.7, target * 1.3)
            if not lo <= n <= hi:
                bad.append(f"{label}={n} (want {lo:g}..{hi:g})")
        return not bad, ("; ".join(bad) or "counts: " + ", ".join(f"{k}={got.get(k, 0)}" for k in TARGETS if got.get(k)))

    def c2():
        miss = q("MATCH (n) WHERE n.id IS NULL OR n.origin IS NULL RETURN count(n)")[0][0]
        unsourced = q("MATCH (n) WHERE (n:Decision OR n:Resolution) AND NOT (n)-[:SOURCED_FROM]->() RETURN n.id")
        bad = q("MATCH (n)-[r:SOURCED_FROM]->(s) WHERE r.excerpt IS NULL OR r.excerpt = '' "
                "OR NOT coalesce(s.text, s.summary) CONTAINS r.excerpt RETURN n.id, s.id")
        return not (miss or unsourced or bad), f"missing id/origin={miss}; unsourced={len(unsourced)}; excerpts not in source={bad}"

    def c3():
        m = q("MATCH (p:Person)-[:MAINTAINS]->(:Service {id:$s}) RETURN p.id, p.status", {"s": RR})
        top = q("MATCH (p:Person {status:'active'})-[w:WORKED_ON]->(:Service {id:$s}) "
                "RETURN p.id, w.commits ORDER BY w.commits DESC LIMIT 1", {"s": RR})
        return m == [["per:arjun-mehta", "left"]] and top[0][0] == "per:priya-nair", f"maintainer={m}, top active={top}"

    def c4():
        r = q("MATCH p=(:Service {id:$a})-[:DEPENDS_ON*1..4]->(:Service {id:$b}) RETURN length(p) ORDER BY length(p)", {"a": PA, "b": RR})
        return [x[0] for x in r] == [2], f"path lengths payments-api -> risk-rules: {[x[0] for x in r]}"

    def c5():
        r = q("MATCH (:Service {id:$a})-[:DEPENDS_ON*1..4]->(d:Service)<-[:CHANGED]-(dep:Deploy) WHERE dep.ts > $since "
              "RETURN DISTINCT d.id, dep.id", {"a": PA, "since": since})
        t = q("MATCH (:Deploy {id:'dep:risk-rules-v2.8.0'})-[:FOR_TICKET]->(t:Ticket) RETURN t.id")
        return r == [[RR, "dep:risk-rules-v2.8.0"]] and t == [["tkt:RISK-412"]], f"recent downstream deploys={r}; ticket={t}"

    def c6():
        r = q("MATCH (:Service {id:$a})-[d:DEPENDS_ON]->(x:Service) RETURN x.id, d.source", {"a": RR})
        return r == [["svc:rules-store-db", "declared"]], f"risk-rules outgoing DEPENDS_ON={r}"

    def c7():
        r = q("MATCH (:Service {id:'svc:payouts-service'})-[:DEPENDS_ON*1..3]->(c:Service {id:$c}) RETURN count(c)", {"c": CS})[0][0]
        shared = q("MATCH (:Service {id:'svc:payouts-service'})-[:DEPENDS_ON*1..3]->(x:Service)<-[:DEPENDS_ON*1..3]-(:Service {id:$r}) "
                   "RETURN DISTINCT x.id", {"r": RR})
        return r > 0 and not shared, f"payouts reaches config-service via {r} path(s); shared downstream with risk-rules={shared}"

    def c8():
        r = q("MATCH (i:Incident {status:'resolved'})-[:HAS_ROOT_CAUSE]->(:RootCause {id:'rc:cache-ttl-thundering-herd'}) "
              "OPTIONAL MATCH (i)-[:RESOLVED_BY]->(:Resolution)-[:PERFORMED_BY]->(p:Person {id:'per:priya-nair'}) "
              "RETURN count(DISTINCT i), count(DISTINCT p)")[0]
        return r[0] >= 2 and r[1] >= 1, f"resolved incidents sharing the root cause={r[0]}; Priya performed a resolution={bool(r[1])}"

    def c9():
        r = q("MATCH (:Decision {id:'dec:rules-cache-ttl'})-[:SOURCED_FROM]->(c:ChatThread {id:'chat:risk-eng-config-load'}) "
              "RETURN c.text CONTAINS 'config-service', c.text CONTAINS '300s'")
        return r == [[True, True]], f"{r}"

    def c10():
        r = q("MATCH (:Service {id:'svc:email-sender'})<-[:CHANGED]-(dep:Deploy) WHERE dep.ts > $since RETURN dep.id", {"since": since})
        down = q("MATCH (:Service {id:$a})-[:DEPENDS_ON*1..10]->(e:Service {id:'svc:email-sender'}) RETURN count(e)", {"a": PA})[0][0]
        return bool(r) and down == 0, f"email-sender recent deploys={r}; paths from payments-api={down}"

    def c11():
        s = q("MATCH ()-[r:SIMILAR_TO]->() RETURN count(r)")[0][0]
        a = q("MATCH (n) WHERE n.origin <> 'seed' RETURN count(n)")[0][0]
        return s == 0 and a == 0, f"SIMILAR_TO={s}; non-seed nodes={a}"

    def c12():
        r = [x[0] for x in q("CALL db.idx.fulltext.queryNodes('ChatThread', 'config') YIELD node RETURN node.id")]
        return "chat:risk-eng-config-load" in r, f"hits={r}"

    def c13():
        have = {}
        for label, props, types, *_ in q("CALL db.indexes()"):
            for p in props:
                have[(label, p)] = set(types[p])
        want = [(l, p, "RANGE") for l, p in schema.RANGE_INDEXES] + [(l, p, "FULLTEXT") for l, ps in schema.FULLTEXT_INDEXES for p in ps]
        missing = [w for w in want if w[2] not in have.get((w[0], w[1]), set())]
        return not missing, f"{len(want) - len(missing)}/{len(want)} expected indexes present; missing={missing}"

    def n1():
        got = dict(q("MATCH (n) RETURN labels(n)[0], count(n)"))
        return got.get("Team") == 2 and got.get("Service") == 9 and got.get("Person") == 8 and 35 <= sum(got.values()) <= 50, f"{got}"

    def n2():
        r = q("MATCH (:Service {id:'svc:patient-portal'})-[:DEPENDS_ON*1..4]->(d:Service)<-[:CHANGED]-(dep:Deploy) WHERE dep.ts > $since "
              "RETURN DISTINCT d.id, dep.id", {"since": since})
        return r == [["svc:notifications", "dep:notifications-v3.2.0"]], f"recent downstream deploys of patient-portal={r}"

    def n3():
        r = q("MATCH (:Decision {id:'dec:sms-retry-cap'})-[:SOURCED_FROM]->(c:ChatThread) RETURN c.id")
        m = q("MATCH (p:Person)-[:MAINTAINS]->(:Service {id:'svc:notifications'}) RETURN p.status")
        return r == [["chat:platform-sms-retries"]] and m == [["left"]], f"decision source={r}; notifications maintainer={m}"

    def n4():
        kp = q("MATCH (n) WHERE n.text CONTAINS 'RULES_CACHE_TTL' OR n.id IN ['svc:risk-rules', 'per:priya-nair'] RETURN count(n)")[0][0]
        return kp == 0, f"Kestrel Pay nodes/text found={kp}"

    checks = [("Counts: 2 teams, 9 services, 8 people, ~40 nodes", n1), ("Provenance: ids/origin + literal excerpts", c2),
              ("Planted story: only notifications changed recently downstream of patient-portal", n2),
              ("Decision sourced from #platform chat; notifications maintainer has left", n3),
              ("Isolation: nothing from Kestrel Pay in this graph", n4), ("No SIMILAR_TO edges and no agent-origin nodes", c11),
              ("All expected indexes exist", c13)] if pkg == "northwind_health" else [
        ("Counts per label within ±30% (4 teams, 27 services)", c1),
        ("Provenance: ids/origin everywhere; every Decision+Resolution has a literal SOURCED_FROM excerpt", c2),
        ("Bus factor: risk-rules maintainer has left; Priya is top active contributor", c3),
        ("Causal path: payments-api -> risk-rules exists (length 2)", c4),
        ("Likely cause: only risk-rules changed in last 2h downstream of payments-api (RISK-412)", c5),
        ("Hidden dependency absent: risk-rules only declares rules-store-db", c6),
        ("Session 2 precondition: payouts reaches config-service; shares nothing with risk-rules", c7),
        ("Recurring pattern: >=2 resolved incidents share the TTL root cause, Priya fixed one", c8),
        ("Buried decision: dec:rules-cache-ttl sourced from the #risk-eng thread", c9),
        ("Decoy: email-sender deployed recently but is not downstream of payments-api", c10),
        ("No SIMILAR_TO edges and no agent-origin nodes", c11),
        ("Full-text search finds the config-load thread", c12),
        ("All expected indexes exist", c13)]
    for i, (name, fn) in enumerate(checks, 1):
        check(i, name, fn)

    print(f"\n{sum(results)}/{len(results)} checks passed")
    if not all(results):
        if since < time.time() - 3 * 3600:
            print("hint: 'recent deploy' checks are relative to now; re-run load or pass --now", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
