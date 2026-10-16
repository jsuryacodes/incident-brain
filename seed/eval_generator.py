"""Seeded random scenarios for the Firefighter eval: a generality check beyond the hand-written library.

generate(seed, tenant) -> a scenario dict in seed/eval_scenarios.py's format. Deterministic per seed:
  - a random alerting service that calls something;
  - a culprit at a random depth 1..4 downstream of it (the depth is drawn first; Northwind only has depth 1-2),
    chosen only where the shortest path is unique and the expected contact has no tie;
  - a decoy deploy on a service the alert cannot reach and shares no dependency with (if the company has one), often
    FRESHER than the culprit, so "pick the newest deploy" is wrong;
  - expected contact from the who-to-call formula (seed.eval_oracle), never someone who left.
Ground truth comes from seed.eval_oracle (plain Python over the seed lists), not from the agent's tools.
"""
import random

from seed import eval_oracle as o
from seed.load import build

TENANTS = ("kestrel_pay", "northwind_health")
SUMMARIES = ["Raise connection pool limits and shorten idle timeouts", "Switch the HTTP client to the new retry library",
             "Enable request batching on the hot path", "Upgrade the database driver to the next major version",
             "Turn on synchronous audit writes", "Tighten the per-caller rate limit", "Roll out the new cache layer",
             "Change the default serialisation format"]
SYMPTOMS = ["5xx rate {p}% and p99 {s}s for the last {m} minutes", "p99 latency {s}s, error budget burning at {p}x",
            "timeouts to downstream calls, {p}% of requests failing for {m} minutes"]


def generate(seed, tenant=None):
    rnd = random.Random(seed)
    tenant = tenant or TENANTS[seed % len(TENANTS)]
    nodes, edges = build(tenant, 1_800_000_000)  # only the structure matters here; times are relative in the fixture
    nodes = {n["id"]: n for n in nodes}
    adj = o.deps(edges)
    services = sorted(i for i, n in nodes.items() if n["label"] == "Service")
    people = {i: n for i, n in nodes.items() if n["label"] == "Person" and n["status"] == "active"}
    by_depth = {}  # depth -> [(alert, culprit)] where the shortest path is unique
    for alert in services:
        for s, h in o.dist_from(alert, adj).items():
            if 1 <= h <= 4 and o.shortest_count(alert, s, adj) == 1:
                by_depth.setdefault(h, []).append((alert, s))
    by_depth = {h: [(a, c) for a, c in pairs if o.contact_unique(c, nodes, edges)] for h, pairs in by_depth.items()}
    by_depth = {h: v for h, v in by_depth.items() if v}
    hops = rnd.choice(sorted(by_depth))  # depth first, so deep culprits are common (Northwind only goes 2 deep)
    alert, culprit = rnd.choice(sorted(by_depth[hops]))
    reach = set(o.dist_from(alert, adj))
    unrelated = [s for s in services if s not in reach and not ((reach - {alert}) & set(o.dist_from(s, adj)) - {s})]
    decoy = rnd.choice(unrelated) if unrelated else None
    by = rnd.choice(sorted(people))
    cause_min = rnd.randint(15, 90)
    deploys = [(culprit.split(":", 1)[1], f"9.{seed % 97}.0", cause_min, by.split(":", 1)[1], rnd.choice(SUMMARIES), None)]
    if decoy:
        deploys.append((decoy.split(":", 1)[1], f"9.{seed % 97}.1", rnd.randint(3, cause_min) if rnd.random() < 0.6 else rnd.randint(cause_min + 1, 110), rnd.choice(sorted(people)).split(":", 1)[1],
                        rnd.choice(SUMMARIES), None))
    path = o.shortest_path(alert, culprit, adj)
    sc = {"id": f"g-{seed}", "tenant": tenant, "shape": f"generated: culprit {hops} hop{'s' * (hops > 1)} down"
          + (", fresher unrelated decoy" if decoy and deploys[1][2] < cause_min else ", unrelated decoy" if decoy else ""),
          "why": f"seed {seed}: random alert, culprit chosen where the shortest path is unique.",
          "fixture": {"quiet": True, "deploys": deploys},
          "alerts": [{"service_id": alert, "symptom": rnd.choice(SYMPTOMS).format(p=rnd.randint(3, 40), s=round(rnd.uniform(1.5, 6), 1),
                                                                                    m=rnd.randint(5, 30))}]}
    from seed.eval_scenarios import fixture  # the contact depends on the fixture (e.g. who deployed)
    fnodes, fedges = build(tenant, 1_800_000_000, fixture(sc))
    sc["expect"] = {"incidents": [{"alerts": [alert], "cause_service": culprit, "cause_deploy": f"dep:{deploys[0][0]}-v{deploys[0][1]}",
                                   "path": path, "contact": o.contact(culprit, {n["id"]: n for n in fnodes}, fedges)}],
                    "false_leads": [f"dep:{deploys[1][0]}-v{deploys[1][1]}"] if decoy else [], "look_first": None, "never_page": []}
    return sc


def scenarios(n=50, start=1000):
    return [generate(s) for s in range(start, start + n)]
