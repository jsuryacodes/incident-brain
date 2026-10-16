import json

import pytest

from backend.db import get_graph
from backend.tools.receipt import MAX_RESULT_CHARS, fit
from backend.tools import graph_tools as gt
from backend.tools.registry import TOOLS, call

RR, CS, PA, PO = "svc:risk-rules", "svc:config-service", "svc:payments-api", "svc:payouts-service"


def ids(items, key="id"):
    return [i[key] for i in items]


def test_1_find_service(ctx):
    r = call("find_service", {"query": "payments api"}, ctx).result
    assert r["matches"][0]["id"] == PA
    assert call("find_service", {"query": "no such thing xyz"}, ctx).result["matches"] == []


def test_2_blast_radius(ctx):
    up = ids(call("blast_radius", {"service_id": CS}, ctx).result["upstream"])
    for s in (PA, PO, "svc:merchant-onboarding", "svc:web-checkout"):
        assert s in up
    assert "svc:fraud-scoring" not in up and RR not in up  # not connected before learning


def test_3_recent_changes_downstream(ctx):
    r = call("recent_changes_downstream", {"service_id": PA, "since_minutes": 120}, ctx).result
    assert r["hit_count"] == 1
    h = r["hits"][0]
    assert h["service"] == RR and h["hops"] == 2
    assert h["path"] == [PA, "svc:fraud-scoring", RR] and h["edge_sources"] == ["declared", "declared"]
    assert h["deploy"]["id"] == "dep:risk-rules-v2.8.0" and h["deploy"]["by"] == "Leo Park"
    assert h["ticket"]["key"] == "RISK-412"
    assert "svc:email-sender" not in json.dumps(r)  # decoy absent


def test_4_memory_learned_edge_changes_behaviour(ctx, learned_edge):
    before = call("shared_dependency_changes", {"service_id": PO, "since_minutes": 1440}, ctx).result
    assert RR not in ids(before["hits"], "neighbour")
    with learned_edge():
        after = call("shared_dependency_changes", {"service_id": PO, "since_minutes": 1440}, ctx).result
        hit = next(h for h in after["hits"] if h["neighbour"] == RR)
        assert hit["shared"] == CS and hit["uses_learned_edge"] is True
        assert "learned" in hit["neighbour_path_sources"]
        assert hit["neighbour_path"] == [RR, CS] and hit["deploy"]["id"] == "dep:risk-rules-v2.8.0"
    again = call("shared_dependency_changes", {"service_id": PO, "since_minutes": 1440}, ctx).result
    assert RR not in ids(again["hits"], "neighbour")  # cleanup worked, order-independent


def test_5_dependency_path(ctx):
    r = call("dependency_path", {"from_id": PA, "to_id": RR}, ctx).result
    assert r["found"] and r["length"] == 2 and r["direction_matched"] == "outgoing"
    rev = call("dependency_path", {"from_id": RR, "to_id": PA}, ctx).result
    assert rev["found"] and rev["direction_matched"] == "incoming" and rev["length"] == 2
    far = call("dependency_path", {"from_id": PO, "to_id": RR}, ctx).result  # only connected ignoring direction
    assert far["found"] and far["direction_matched"] == "both" and far["length"] > 2


def test_6_who_to_call(ctx):
    r = call("who_to_call", {"service_id": RR}, ctx).result
    assert r["bus_factor_risk"] is True
    assert r["maintainers"][0]["name"] == "Arjun Mehta" and r["maintainers"][0]["status"] == "left"
    assert r["candidates"][0]["name"] == "Priya Nair"
    assert r["candidates"][0]["score"] == 23 + 25 * 1
    assert "25" in r["score_formula"] and r["owning_team_fallback"]["id"] == "team:risk-fraud"


def test_7_decisions_about(ctx):
    d = call("decisions_about", {"service_id": RR}, ctx).result["decisions"]
    dec = next(x for x in d if x["id"] == "dec:rules-cache-ttl")
    assert dec["sources"][0]["id"] == "chat:risk-eng-config-load"
    assert "300s" in dec["sources"][0]["excerpt"]


def test_8_past_incidents(ctx):
    r = call("past_incidents", {"service_ids": [RR]}, ctx).result["incidents"]
    inc = next(i for i in r if i["id"] == "inc:2025-031")
    assert inc["via"] == ["caused_by_deploy"] and set(inc["resolved_by"]) == {"Arjun Mehta", "Priya Nair"}
    r = call("past_incidents", {"service_ids": [CS]}, ctx).result["incidents"]
    assert {"inc:2025-031", "inc:2026-012"} <= set(ids(r))
    assert all("rc:cache-ttl-thundering-herd" in i["root_causes"] for i in r)


def test_8b_past_incidents_recalls_agent_written(ctx, graph):
    """Session-2 recall depends on agent-written incidents showing up (origin 'agent', SIMILAR_TO)."""
    graph.query("MERGE (i:Incident {id:'inc:test-agent'}) SET i.origin='agent', i.key='INC-T', i.title='t', i.severity=2, "
                "i.status='open', i.symptom='s', i.summary='s', i.started_at=1, i.created_at=1")
    graph.query("MATCH (i:Incident {id:'inc:test-agent'}), (s:Service {id:'svc:risk-rules'}) MERGE (i)-[:AFFECTED]->(s)")
    graph.query("MATCH (i:Incident {id:'inc:test-agent'}), (o:Incident {id:'inc:2025-031'}) MERGE (i)-[:SIMILAR_TO {score:0.9, reason:'t'}]->(o)")
    try:
        r = call("past_incidents", {"service_ids": [RR]}, ctx).result["incidents"]
        agent = next(i for i in r if i["id"] == "inc:test-agent")
        assert agent["origin"] == "agent" and agent["similar_to"][0]["id"] == "inc:2025-031"
        old = next(i for i in r if i["id"] == "inc:2025-031")
        assert old["similar_to"][0]["id"] == "inc:test-agent"  # link visible from both ends
    finally:
        graph.query("MATCH (i:Incident {id:'inc:test-agent'}) DETACH DELETE i")


def test_9_search_knowledge(ctx):
    hits = call("search_knowledge", {"query": "rulesets config-service"}, ctx).result["hits"]
    assert "chat:risk-eng-config-load" in ids(hits)[:3]
    assert call("search_knowledge", {"query": "x", "labels": ["Nope"]}, ctx).result["error"]


def test_10_critical_services(ctx):
    pr = call("critical_services", {"algorithm": "pagerank"}, ctx).result["services"]
    assert CS in ids(pr)[:3]
    bt = call("critical_services", {"algorithm": "betweenness", "limit": 15}, ctx).result["services"]
    assert len(bt) >= 10
    print("\nbetweenness top 5:", [(s["id"], s["score"]) for s in bt[:5]])


def test_11_stale_knowledge(ctx, learned_edge):
    items = call("stale_knowledge", {"service_id": RR}, ctx).result["items"]
    readme = next(i for i in items if i["id"] == "doc:risk-rules-readme")
    assert "author_left" in readme["reasons"] and "missing_learned_dependency" not in readme["reasons"]
    with learned_edge():
        items = call("stale_knowledge", {"service_id": RR}, ctx).result["items"]
        readme = next(i for i in items if i["id"] == "doc:risk-rules-readme")
        assert "missing_learned_dependency" in readme["reasons"]
    fs = call("stale_knowledge", {"service_id": "svc:fraud-scoring"}, ctx).result["items"]
    assert "rb:fraud-scoring-latency" in ids(fs)
    assert all(i["reasons"] for i in call("stale_knowledge", {}, ctx).result["items"])


def test_12_node_details(ctx):
    r = call("node_details", {"node_id": RR}, ctx).result
    assert any(n["id"] == "per:arjun-mehta" and n["edge"] == "MAINTAINS" for n in r["neighbours"])
    assert call("node_details", {"node_id": "chat:risk-eng-config-load"}, ctx).result["label"] == "ChatThread"


GOOD = [
    ("recent_changes", {}), ("recent_changes", {"since_minutes": 43200, "limit": 30}),
    ("critical_services", {"algorithm": "pagerank", "downstream_of": [PO]}),
    ("find_service", {"query": "payments api"}), ("blast_radius", {"service_id": CS}), ("blast_radius", {"service_id": CS, "max_hops": 6}),
    ("recent_changes_downstream", {"service_id": PA}), ("recent_changes_downstream", {"service_id": PA, "since_minutes": 43200, "max_hops": 6}),
    ("shared_dependency_changes", {"service_id": PO}), ("shared_dependency_changes", {"service_id": PO, "since_minutes": 43200}),
    ("dependency_path", {"from_id": PA, "to_id": RR}), ("who_to_call", {"service_id": RR}), ("who_to_call", {"service_id": CS}),
    ("decisions_about", {"service_id": RR}), ("past_incidents", {"service_ids": [RR]}), ("past_incidents", {"service_ids": [CS, RR, "svc:fraud-scoring"], "limit": 10}),
    ("search_knowledge", {"query": "rulesets config-service"}), ("search_knowledge", {"query": "incident config cache ttl timeout deploy", "limit": 20}),
    ("critical_services", {"algorithm": "pagerank"}), ("critical_services", {"algorithm": "betweenness", "limit": 27}),
    ("stale_knowledge", {"service_id": RR}), ("stale_knowledge", {}),
    ("node_details", {"node_id": RR}), ("node_details", {"node_id": CS}), ("node_details", {"node_id": "per:priya-nair"}),
    ("read_source", {"node_id": "chat:risk-eng-config-load"}), ("read_source", {"node_id": "rb:fraud-scoring-latency"}),
    ("read_source", {"node_id": "dec:rules-cache-ttl"}), ("get_incident_state", {"incident_id": "inc:2025-031"}),
    ("memory_recall", {"service_id": PO}), ("memory_recall", {"service_id": PA, "max_hops": 6}),
    ("industry_matches", {"incident_id": "inc:2025-031"}), ("industry_matches", {"root_cause_id": "rc:bad-config-push", "limit": 10}),
]
LIMITS = {"read_source": gt.SOURCE_CHARS + 1200, "get_incident_state": gt.STATE_CHARS, "memory_recall": 4500,
          "industry_matches": 4000}  # deliberately bigger
BAD = [
    ("critical_services", {"algorithm": "pagerank", "downstream_of": ["svc:nope"]}),
    ("find_service", {"query": ""}), ("blast_radius", {"service_id": "svc:nope"}), ("blast_radius", {"service_id": "per:priya-nair"}),
    ("recent_changes_downstream", {"service_id": "nope"}), ("shared_dependency_changes", {"service_id": "svc:nope"}),
    ("dependency_path", {"from_id": PA, "to_id": "svc:nope"}), ("who_to_call", {"service_id": "svc:nope"}),
    ("decisions_about", {"service_id": "svc:nope"}), ("past_incidents", {"service_ids": ["svc:nope"]}), ("past_incidents", {"service_ids": []}),
    ("search_knowledge", {"query": "!!! ???"}), ("critical_services", {"algorithm": "nope"}),
    ("stale_knowledge", {"service_id": "svc:nope"}), ("node_details", {"node_id": "nope"}), ("node_details", {"node_id": "svc:nope"}),
    ("not_a_tool", {}), ("blast_radius", {}), ("read_source", {"node_id": "svc:risk-rules"}),
    ("read_source", {"node_id": "doc:nope"}), ("get_incident_state", {"incident_id": "inc:nope"}),
    ("memory_recall", {"service_id": "svc:nope"}), ("memory_recall", {}),
    ("industry_matches", {}), ("industry_matches", {"incident_id": "inc:nope"}),
    ("industry_matches", {"incident_id": "inc:2025-031", "root_cause_id": "rc:retry-storm"}), ("industry_matches", {"root_cause_id": "svc:x"}),
]


def test_13_every_tool_is_small_receipted_and_grounded(ctx, learned_edge):
    assert {n for n, _ in GOOD} == set(TOOLS)  # every tool covered
    g = get_graph(ctx.tenant)
    with learned_edge():  # the learned path adds the most content
        for name, args in GOOD:
            out = call(name, args, ctx)
            assert "error" not in out.result, (name, out.result)
            assert len(json.dumps(out.result)) <= LIMITS.get(name, MAX_RESULT_CHARS), (name, args)
            assert len(out.receipt["queries"]) >= 1 and all("cypher" in q and "params" in q for q in out.receipt["queries"])
            hl = out.receipt["highlight"]
            if hl["nodes"]:
                found = {r[0] for r in g.ro_query("MATCH (n) WHERE n.id IN $ids RETURN n.id", {"ids": hl["nodes"]}).result_set}
                assert set(hl["nodes"]) <= found, (name, set(hl["nodes"]) - found)
            for e in hl["edges"]:
                n = g.ro_query("MATCH (a {id:$a})-[r]->(b {id:$b}) WHERE type(r) = $t RETURN count(r)",
                               {"a": e["from"], "b": e["to"], "t": e["type"]}).result_set[0][0]
                assert n >= 1, (name, e)
            assert out.receipt["tool"] == name


@pytest.mark.parametrize("name,args", BAD)
def test_13b_bad_input_returns_error_not_exception(ctx, name, args):
    out = call(name, args, ctx)
    assert isinstance(out.result.get("error"), str) and out.result["error"]


def test_13c_every_query_is_read_only(ctx, graph, monkeypatch):
    """Tools must go through ro_query: make plain query() blow up and run everything."""
    monkeypatch.setattr(type(graph), "query", lambda *a, **k: (_ for _ in ()).throw(AssertionError("write path used")))
    for name, args in GOOD:
        assert "error" not in call(name, args, ctx).result


def test_13d_fit_truncates_longest_list():
    r = fit({"a": list(range(2000)), "b": [1]})
    assert len(json.dumps(r)) <= MAX_RESULT_CHARS and r["truncated"] is True and r["b"] == [1]


def test_14_unknown_tenant():
    with pytest.raises(ValueError):
        get_graph("not_a_tenant")


def test_15_read_source_full_text_and_links(ctx):
    r = call("read_source", {"node_id": "chat:risk-eng-config-load"}, ctx).result
    assert "risk-rules polls config-service's internal /v1/rulesets endpoint" in r["text"]  # past node_details' 200 chars
    assert r["truncated"] is False and r["author"] == "Arjun Mehta" and r["author_status"] == "left"
    assert {"svc:risk-rules", "svc:config-service"} <= set(r["mentions"])
    rb = call("read_source", {"node_id": "rb:fraud-scoring-latency"}, ctx).result
    assert rb["describes"] == ["svc:fraud-scoring"] and rb["version"] == 1 and rb["superseded_by"] == []


def test_16_past_incidents_says_which_change_caused_it(ctx):
    r = call("past_incidents", {"service_ids": [PA, RR]}, ctx).result
    i = next(x for x in r["incidents"] if x["id"] == "inc:2025-031")
    assert i["caused_by_change_to"] == [RR]


def test_17_memory_recall_is_empty_without_agent_memory(ctx):
    """Seeded history (e.g. resolved INC-2025-031 on payments-api) is not agent memory: a first session recalls nothing."""
    r = call("memory_recall", {"service_id": PA}, ctx).result
    assert not (r["learned_edges"] or r["facts"] or r["incidents"] or r["suspects"]) and "no memory" in r["note"]
    assert RR in r["scope"] and CS in r["scope"]


def test_18_memory_recall_turns_a_learned_edge_into_a_suspect(ctx, learned_edge):
    with learned_edge():
        r = call("memory_recall", {"service_id": PO}, ctx).result
    assert [(e["from"], e["to"]) for e in r["learned_edges"]] == [(RR, CS)]
    assert r["suspects"] == [{"service": RR, "relation": "shares_dependency", "via": [f"learned edge {RR} -> {CS}"], "shared": CS}]


def test_19_industry_matches_share_a_root_cause(ctx):
    r = call("industry_matches", {"incident_id": "inc:2025-031"}, ctx).result
    assert r["root_causes"] == ["rc:cache-ttl-thundering-herd"] and len(r["matches"]) >= 2
    assert all(m["url"].startswith("https://") and "rc:cache-ttl-thundering-herd" in m["shared_root_causes"] for m in r["matches"])
    many = call("industry_matches", {"root_cause_id": "rc:bad-config-push", "limit": 10}, ctx).result
    assert many["match_count"] >= 5 and len({m["company"] for m in many["matches"]}) >= 3


def test_20_recent_changes_is_a_flat_change_log(ctx):
    r = call("recent_changes", {"since_minutes": 120}, ctx).result
    assert [c["deploy"]["id"] for c in r["changes"]] == ["dep:risk-rules-v2.8.0", "dep:email-sender-v1.14.2"]  # newest first
    c = r["changes"][0]
    assert c["service"] == RR and c["deployer_status"] == "active" and c["ticket"]["key"] == "RISK-412"
    assert "DEPENDS_ON" not in " ".join(q["cypher"] for q in call("recent_changes", {}, ctx).receipt["queries"])


def test_21_a_change_to_the_alerting_service_itself_counts(ctx):
    r = call("recent_changes_downstream", {"service_id": RR, "since_minutes": 120}, ctx).result
    assert r["hits"][0]["service"] == RR and r["hits"][0]["hops"] == 0 and r["hits"][0]["path"] == [RR]


def test_22_critical_services_scoped_to_a_call_path(ctx):
    r = call("critical_services", {"algorithm": "pagerank", "downstream_of": [PO], "limit": 3}, ctx).result
    ids = [s["id"] for s in r["services"]]
    assert set(ids[:2]) == {CS, "svc:config-db"} and "svc:fraud-scoring" not in ids  # a hub and its database: a near-tie


def test_23_no_algorithms_mode_uses_plain_cypher_with_the_same_path(ctx):
    from dataclasses import replace
    algo = call("recent_changes_downstream", {"service_id": "svc:web-checkout", "since_minutes": 120}, ctx)
    plain = call("recent_changes_downstream", {"service_id": "svc:web-checkout", "since_minutes": 120}, replace(ctx, algorithms=False))
    assert plain.result["hits"][0]["path"] == algo.result["hits"][0]["path"]
    assert not any("algo." in q["cypher"] for q in plain.receipt["queries"])
    assert any("algo.SPpaths" in q["cypher"] for q in algo.receipt["queries"])
    assert "switched off" in call("critical_services", {}, replace(ctx, algorithms=False)).result["error"]


def test_24_downstream_hit_without_a_ticket(ctx):
    """email-sender's deploy has no ticket: the aggregation with a NULL ticket used to crash FalkorDB 6.0.2."""
    r = call("recent_changes_downstream", {"service_id": "svc:notifications-service", "since_minutes": 120}, ctx).result
    assert r["hits"][0]["service"] == "svc:email-sender" and r["hits"][0]["ticket"] is None


def test_25_every_service_tool_on_every_service(ctx, graph):
    """A sweep: no tool errors (or takes the database down) on any service of the company."""
    svcs = [r[0] for r in graph.ro_query("MATCH (s:Service) RETURN s.id ORDER BY s.id").result_set]
    for s in svcs:
        for name, args in (("blast_radius", {"service_id": s}), ("recent_changes_downstream", {"service_id": s, "since_minutes": 43200}),
                           ("shared_dependency_changes", {"service_id": s, "since_minutes": 43200}), ("who_to_call", {"service_id": s}),
                           ("decisions_about", {"service_id": s}), ("past_incidents", {"service_ids": [s]}),
                           ("stale_knowledge", {"service_id": s}), ("memory_recall", {"service_id": s}),
                           ("critical_services", {"downstream_of": [s]})):
            assert "error" not in call(name, args, ctx).result, (name, s)
