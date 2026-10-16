"""Part C: the alert-storm story beat (recording, numbers, API). Mock only."""
from fastapi.testclient import TestClient

from backend import demo
from backend.api import main, views


def test_storm_numbers_and_api(monkeypatch):
    rec = demo.golden("firefighter-storm")
    n = views.storm_numbers(rec)
    naive, agent = n["columns"]
    assert naive["pages"] == 6 and agent["pages"] == 2 and agent["suppressed"] == 5 and "WCC" in agent["algorithms"]
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1000")
    monkeypatch.setenv("TENANTS", "kestrel_pay")
    c = TestClient(main.app)
    j = c.get("/api/storm/latest", params={"tenant": "kestrel_pay"}).json()
    assert j["source"] == "replay" and j["columns"][1]["incidents"] == 2
    assert c.get("/api/story", params={"tenant": "kestrel_pay"}).json()["storm"]["replay"] == "firefighter-storm"
    ev = c.get("/api/replay/firefighter-storm").json()
    assert sum(1 for e in ev["events"] if e["event"] == "step") == len(rec["steps"])


def test_playground_lists_scenarios_with_recordings(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1000")
    c = TestClient(main.app)
    p = c.get("/api/playground", params={"tenant": "kestrel_pay_test"}).json()
    ids = {s["id"]: s for s in p["scenarios"]}
    assert "k-storm" in ids and ids["k-storm"]["replay"] == "ff-k-storm" and len(p["services"]) == 27
    r = c.get("/api/replay/ff-k-falselead").json()
    assert r["execution"]["verification"]["all_cleared"] is True and r["report"]["action_plan"]
    assert c.post("/api/firefighter/run", json={"tenant": "kestrel_pay_test", "scenario_id": "k-deep"}).status_code == 403
