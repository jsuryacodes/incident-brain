"""Independent oracle for the eval scenarios (seed/eval_scenarios.py).

Every expected answer is re-derived here from the fixture's own node/edge lists with plain Python (seed/eval_oracle.py:
BFS, a small PageRank, the who-to-call formula written out by hand). No Cypher and no agent tool is used, so the eval's
ground truth does not come from the code it grades.
"""
import pytest

from seed.eval_oracle import contact, deps, dist_from, pagerank, shortest_count
from seed.eval_holdout import SCENARIOS as HOLDOUT
from seed.eval_scenarios import SCENARIOS, fixture
from seed.load import build

WINDOW = 120 * 60


def world(sc, now=1_800_000_000):
    nodes, edges = build(sc["tenant"], now, fixture(sc))
    return {n["id"]: n for n in nodes}, edges, now


@pytest.mark.parametrize("sc", SCENARIOS + HOLDOUT, ids=[s["id"] for s in SCENARIOS + HOLDOUT])
def test_expectations_hold_in_the_fixture(sc):
    nodes, edges, now = world(sc)
    adj = deps(edges)
    rev = {}
    for a, bs in adj.items():
        for b in bs:
            rev.setdefault(b, set()).add(a)
    changed = {a: b for a, t, b, _ in edges if t == "CHANGED"}
    recent = {d for d, n in nodes.items() if n["label"] == "Deploy" and n["ts"] > now - WINDOW}
    exp = sc["expect"]
    causes = {i["cause_deploy"] for i in exp["incidents"] if i["cause_deploy"]}
    # every recent deploy is accounted for: a cause or a named false lead
    assert recent == causes | set(exp["false_leads"]), (recent, causes, exp["false_leads"])
    alerts = [a["service_id"] for a in sc["alerts"]]
    assert sorted(a for i in exp["incidents"] for a in i["alerts"]) == sorted(alerts)
    for inc in exp["incidents"]:
        assert contact(inc["cause_service"] or inc.get("root") or inc["alerts"][0], nodes, edges) == inc["contact"], inc
        if inc.get("root"):  # storm: the top shared dependency (coverage, alerting first, hops) explains these alerts
            reach = {a: dist_from(a, adj) for a in alerts}
            cover = {}
            for a, d in reach.items():
                for x in d:
                    cover.setdefault(x, set()).add(a)
            rank = sorted((x for x in cover if len(cover[x]) >= 2),
                          key=lambda x: (-len(cover[x]), x not in alerts, sum(reach[a][x] for a in cover[x]), x))
            assert rank[0] == inc["root"] and sorted(cover[inc["root"]]) == sorted(inc["alerts"]), (rank[:3], inc)
            by_change = [len([a for a in alerts if changed[x] in reach[a]]) for x in recent]
            assert len(inc["alerts"]) > max(by_change, default=0)  # no single change explains as many alerts
            continue
        if not inc["cause_deploy"]:
            continue
        cs = inc["cause_service"]
        assert changed[inc["cause_deploy"]] == cs
        path, a0 = inc["path"], inc["alerts"][0]
        assert path[0] == a0 and path[-1] == cs
        d = dist_from(a0, adj)
        if cs in d:  # downstream: a shortest DEPENDS_ON path, and no recent change is nearer
            assert len(path) - 1 == d[cs]
            assert all(b in adj.get(a, ()) for a, b in zip(path, path[1:]))
            assert shortest_count(a0, cs, adj) == 1, "several shortest paths: the expected path would be arbitrary"
            nearer = [x for x in recent - {inc["cause_deploy"]} if changed[x] in d and d[changed[x]] < d[cs]]
            assert not nearer, nearer
            for other in inc["alerts"][1:]:  # one cause explains every alert of the incident
                assert cs in dist_from(other, adj)
        else:  # noisy neighbour: alert -> shared <- culprit, shortest such pair, culprit not downstream
            k = next(i for i, x in enumerate(path) if x not in d or i == len(path) - 1)
            shared = path[k - 1]
            assert shared in d and shared in dist_from(cs, adj)
            assert all(b in adj.get(a, ()) for a, b in zip(path[:k], path[1:k]))  # alert -> shared, forwards
            assert all(a in adj.get(b, ()) for a, b in zip(path[k - 1:], path[k:]))  # shared <- culprit, backwards
            assert len(path) - 1 == min(d[s] + dist_from(cs, adj)[s] for s in d if s in dist_from(cs, adj) and s != a0)
    for lead in exp["false_leads"]:
        svc = changed[lead]
        explained = [a for a in alerts if svc in dist_from(a, adj)]
        best = max([len([a for a in alerts if i["cause_service"] in dist_from(a, adj)]) for i in exp["incidents"]
                    if i["cause_service"]] + [len(i["alerts"]) for i in exp["incidents"] if i.get("root")], default=0)
        assert not explained or len(explained) < best, (lead, explained)
        for inc in exp["incidents"]:
            a0 = inc["alerts"][0]
            shares = (set(dist_from(a0, adj)) & set(dist_from(svc, adj))) - {a0, svc}
            if not shares:
                continue
            # a neighbour lead (shares a dependency): only rejected because a direct downstream change (or a storm root
            # explaining more alerts) explains it
            assert inc.get("root") or (inc["cause_service"] and inc["cause_service"] in dist_from(a0, adj)), (lead, sorted(shares))
    for inc in exp["incidents"]:
        if not inc["cause_deploy"] and not inc.get("root"):  # "not found": nothing downstream and no neighbour changed
            for x in recent:
                d = dist_from(inc["alerts"][0], adj)
                assert changed[x] not in d, x
                assert not (set(d) & set(dist_from(changed[x], adj))), x
    for a, t, b, props in edges:  # every quote a fixture adds is verbatim in its source
        if t == "SOURCED_FROM" and a.startswith("fact:"):
            assert props["excerpt"] in nodes[b]["text"], (a, b)
    for p in exp["never_page"]:
        assert nodes[p]["status"] == "left"
    if exp["look_first"]:
        services = sorted(i for i, n in nodes.items() if n["label"] == "Service")
        pr = pagerank(services, adj)
        down = dist_from(alerts[0], adj)
        best = max(pr[s] for s in down if s != alerts[0])
        near_top = sorted(s for s in down if s != alerts[0] and pr[s] >= 0.95 * best)  # ties within 5% count as top
        assert near_top == sorted(exp["look_first"]), sorted(((round(pr[s], 4), s) for s in down), reverse=True)[:3]


def test_ids_unique_and_tenants_known():
    ids = [s["id"] for s in SCENARIOS]
    assert len(ids) == len(set(ids)) >= 8
    assert {s["tenant"] for s in SCENARIOS} == {"kestrel_pay", "northwind_health"}


def test_twin_graphs_are_internal_only(monkeypatch):
    from fastapi import HTTPException

    from backend.api.main import tenant_ok
    from backend.db import base_tenant, eval_twin, get_graph
    monkeypatch.setenv("TENANTS", "kestrel_pay")
    assert base_tenant(eval_twin("kestrel_pay", "k_deep")) == "kestrel_pay"
    assert base_tenant("kestrel_pay__eval_") == "kestrel_pay__eval_"  # no scenario id: not a twin
    get_graph(eval_twin("kestrel_pay", "k_deep"))  # allowed internally (no query is sent)
    with pytest.raises(ValueError):
        get_graph("other__eval_x")
    with pytest.raises(HTTPException):
        tenant_ok(eval_twin("kestrel_pay", "k_deep"))  # never over HTTP


def test_generated_scenarios_are_sound():
    from seed.eval_generator import scenarios
    gen = scenarios(50)
    assert len({s["id"] for s in gen}) == 50 and {s["tenant"] for s in gen} == {"kestrel_pay", "northwind_health"}
    for sc in gen:
        test_expectations_hold_in_the_fixture(sc)
