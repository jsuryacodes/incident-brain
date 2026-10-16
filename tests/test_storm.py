"""Part C: several alerts at once, read through the graph algorithms. Mock only."""
from backend.agents.firefighter import run_firefighter
from backend.db import eval_twin, get_graph
from backend.llm import LLMClient
from backend.tools.receipt import ToolContext
from seed.eval_scenarios import BY_ID, fixture
from seed.load import load


def storm(scenario_id, tool_names=None, algorithms=True):
    sc = BY_ID[scenario_id]
    name = eval_twin("northwind_test" if sc["tenant"] == "northwind_health" else "kestrel_pay_test", "storm_" + scenario_id.replace("-", "_"))
    s = load(name, reset=True, data_package=sc["tenant"], quiet=True, transform=fixture(sc))
    try:
        return run_firefighter(sc["alerts"], ToolContext(tenant=name, now=s["now"], algorithms=algorithms),
                               LLMClient(mode="mock"), save=False, tool_names=tool_names)
    finally:
        get_graph(name).delete()


def test_storm_is_one_incident_with_one_page():
    rec = storm("k-storm")
    r = rec["report"]
    assert rec["status"] == "ok" and len(r["incidents"]) == 2
    big, card = r["incidents"]
    assert big["root"]["service_id"] == "svc:config-service" and big["likely_cause"]["deploy_id"] is None
    assert big["contact"]["person_id"] == "per:omar-haddad" and len(big["suppressed_pages"]) == 5
    assert all("config-service" in p["reason"] for p in big["suppressed_pages"])
    assert card["likely_cause"]["deploy_id"] == "dep:card-processor-adapter-v2.9.0"
    lead = next(x for x in r["rejected_leads"] if x["deploy_id"] == "dep:email-sender-v1.15.0")
    assert "no change explains this storm" in lead["reason"]
    used = {q["cypher"].split("algo.", 1)[1].split("(", 1)[0] for s in rec["steps"] for q in s["receipt"]["queries"] if "algo." in q["cypher"]}
    assert {"BFS", "WCC", "SPpaths", "SSpaths"} <= used


def test_a_hub_does_not_swallow_an_unrelated_alert():
    r = storm("k-storm-hub")["report"]
    assert [i["alerts"] for i in r["incidents"]][1] == ["svc:reporting-service"]
    assert r["incidents"][1]["likely_cause"]["deploy_id"] == "dep:reporting-service-v1.4.0"


def test_without_algorithms_the_storm_is_six_incidents():
    """Honest ablation: without correlate_alerts / connected_impact the same planner pages per alert."""
    from backend.agents.baseline_noalgo import TOOL_NAMES
    r = storm("k-storm", tool_names=TOOL_NAMES, algorithms=False)["report"]
    assert len(r["incidents"]) > 2 and not any(i.get("root") for i in r["incidents"])
