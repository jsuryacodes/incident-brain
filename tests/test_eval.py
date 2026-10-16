"""The Firefighter eval runner (08A): twins, scoring, the baselines, the API. Mock only."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.agents import firefighter_eval as fe
from backend.api import main
from backend.db import client


@pytest.fixture()
def twins(monkeypatch):
    monkeypatch.setattr(fe, "TWIN_BASE", {"kestrel_pay": "kestrel_pay_test", "northwind_health": "northwind_test"})


def test_eval_scores_and_cleans_up(twins):
    res = fe.run_eval(only=["k-falselead", "n-chokepoint", "k-nochange"], write=False, generated=3)
    full = {s["id"]: s["results"]["full"] for s in res["scenarios"]}
    assert all(r["passed"] for r in full.values()), {k: v for k, v in full.items() if not v["passed"]}
    assert full["k-falselead"]["false_leads_rejected"] == 2 and full["k-falselead"]["wrong_actions"] == 0
    assert res["totals"]["dev"]["full"]["passed"] == 3 and res["totals"]["generated"]["full"]["scenarios"] == 3
    assert not [g for g in client().list_graphs() if "__eval_" in g]  # every twin deleted


def test_api_eval_latest(monkeypatch, tmp_path):
    f = tmp_path / "latest.json"
    monkeypatch.setattr(main, "EVAL_LATEST", f)
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1000")
    c = TestClient(main.app)
    assert c.get("/api/eval/latest").status_code == 404
    f.write_text(json.dumps({"scenarios": [], "totals": {}}))
    assert c.get("/api/eval/latest").json() == {"scenarios": [], "totals": {}}


def _rec(report):
    return {"report": report, "status": "ok", "grounding": {"ok": True}, "totals": {"tool_calls": 1, "llm_calls": 1}, "steps": []}


def test_scorer_closes_loopholes(graph):
    """Hand-made reports: the scorer must not pass a contradictory or sloppy report."""
    from seed.eval_scenarios import BY_ID
    sc = BY_ID["k-falselead"]
    good = {"likely_cause": {"service_id": "svc:bank-connector", "deploy_id": "dep:bank-connector-v1.20.0",
                             "path": ["svc:payouts-service", "svc:bank-connector"]},
            "contact": {"person_id": "per:tomasz-kowalski"},
            "recommended_actions": ["Roll back dep:bank-connector-v1.20.0.", "Page Tomasz (per:tomasz-kowalski)."],
            "rejected_leads": [{"deploy_id": d, "reason": "not on the path"} for d in sc["expect"]["false_leads"]]}
    assert fe.score(sc, _rec(good), "kestrel_pay_test")["passed"]  # the trailing "." is not part of the id
    for change in ({"rejected_leads": good["rejected_leads"] + [{"deploy_id": "dep:bank-connector-v1.20.0", "reason": "x"}]},
                   {"recommended_actions": good["recommended_actions"] + ["revert dep:email-sender-v1.15.0 too"]},
                   {"recommended_actions": good["recommended_actions"] + ["Also page per:arjun-mehta."]},
                   {"rejected_leads": [{"deploy_id": d, "reason": " "} for d in sc["expect"]["false_leads"]]}):
        m = fe.score(sc, _rec({**good, **change}), "kestrel_pay_test")
        assert not m["passed"], change


def test_no_algorithms_baseline_is_honest(twins):
    res = fe.run_eval(only=["k-nochange", "k-learned"], profiles=["no_algo"], write=False, generated=0)
    r = {s["id"]: s["results"]["no_algo"] for s in res["scenarios"]}
    assert r["k-nochange"]["used_algorithms"] == [] and r["k-learned"]["used_algorithms"] == []  # no algo.* query ran
    assert r["k-nochange"]["passed"]  # without PageRank, counting who reaches each service points at the same hubs
    assert r["k-learned"]["passed"]  # traversals alone find the learned-edge cause


def test_no_graph_baseline_is_honest(twins):
    res = fe.run_eval(only=["k-learned", "k-falselead", "n-departed"], profiles=["no_graph"], write=False, generated=0)
    r = {s["id"]: s["results"]["no_graph"] for s in res["scenarios"]}
    assert all(x["used_algorithms"] == [] and x["grounding_ok"] for x in r.values())  # loses on the graph, not on format
    assert r["k-learned"]["path_correct"] == 0  # no dependency data, no path
    assert r["k-falselead"]["false_leads_rejected"] < r["k-falselead"]["false_leads"]  # word matching takes the bait
    assert r["n-departed"]["paged_right"] == 1  # automated deploy: it escalates to the owning team from the catalog

