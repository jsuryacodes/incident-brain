"""M5: FastAPI backend, TestClient, mock mode only (live is faked: no network, ever)."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.api import guard, main
from backend.db import redis
from backend.llm import LLMClient

CODE = "open-sesame"


@pytest.fixture(scope="module")
def tenant(fresh):
    return fresh("kestrel_pay_api")


@pytest.fixture()
def client(monkeypatch, tenant):
    monkeypatch.setenv("ACCESS_CODE", CODE)
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1000")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    main.limiter.buckets.clear()
    return TestClient(main.app)


def events(resp):
    out, ev = [], None
    for line in resp.iter_lines():
        if line.startswith("event: "):
            ev = line[7:]
        elif line.startswith("data: "):
            out.append((ev, json.loads(line[6:])))
    return out


def run_team(client, tenant, headers=None, live=False):
    with client.stream("POST", "/api/team/run", headers=headers or {},
                       json={"tenant": tenant, "service_id": "svc:payments-api", "symptom": "5xx rate 12%", "live": live}) as r:
        assert r.status_code == 200, r.read()
        return events(r)


def test_health_and_tenants(client, tenant):
    assert client.get("/api/health").json()["ok"] is True
    assert {"id": tenant} in client.get("/api/tenants").json()


def test_graph_overview_and_node(client, tenant):
    g = client.get("/api/graph", params={"tenant": tenant}).json()
    assert 100 < len(g["nodes"]) <= main.GRAPH_CAP and g["edges"]
    assert set(g["nodes"][0]) == {"id", "label", "name", "origin"} and set(g["edges"][0]) == {"from", "type", "to", "source"}
    assert client.get("/api/graph", params={"tenant": "nope"}).status_code == 404
    n = client.get("/api/node/svc:risk-rules", params={"tenant": tenant}).json()
    assert n["result"]["label"] == "Service" and n["receipt"]["queries"]
    assert client.get("/api/node/svc:nope", params={"tenant": tenant}).status_code == 404


def test_fresh_runs_need_the_code(client, tenant):
    body = {"tenant": tenant, "service_id": "svc:payments-api", "symptom": "5xx rate 12%"}
    assert client.post("/api/team/run", json=body).status_code == 403
    assert client.post("/api/team/run", json=body, headers={"X-Access-Code": "wrong"}).status_code == 403
    r = client.post("/api/incidents/inc:2026-032/resolve", json={"tenant": tenant, "resolved_by_ids": ["per:priya-nair"],
                                                                 "what_fixed_it": "Priya rolled back RULES_CACHE_TTL"})
    assert r.status_code == 403


def test_team_run_streams_in_order_and_is_forced_to_mock(client, tenant, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    ev = run_team(client, tenant, {"X-Access-Code": CODE}, live=True)  # asks for live: the server has no key
    names = [e for e, _ in ev]
    assert ev[0][0] == "start" and ev[0][1]["mode"] == "mock" and "ANTHROPIC_API_KEY" in ev[0][1]["mode_reason"]
    for a, b in (("step", "handoff"), ("handoff", "report"), ("report", "done")):
        assert names.index(a) < names.index(b)
    assert names.count("handoff") == 3 and names[-1] == "done" and "error" not in names
    step = next(d for e, d in ev if e == "step")
    assert {"seq", "agent", "tool", "args", "summary", "cypher", "params", "result_preview", "highlight", "cited",
            "writes", "elements", "mode"} <= set(step) and step["mode"] == "mock"
    assert any(d["tool"] == "open_incident" for e, d in ev if e == "write")
    report = next(d for e, d in ev if e == "report")
    assert report["report"]["likely_cause"]["deploy_id"] == "dep:risk-rules-v2.8.0"
    # incident graph + session replay from the graph
    inc = report["incident_id"]
    g = client.get("/api/graph", params={"tenant": tenant, "mode": "incident", "id": inc}).json()
    assert inc in {n["id"] for n in g["nodes"]} and any(n["origin"] == "agent" for n in g["nodes"])
    done = ev[-1][1]
    s = client.get(f"/api/sessions/{done['session_id']}", params={"tenant": tenant}).json()
    assert s["mode"] == "team" and inc in s["incidents"] and len(s["steps"]) == names.count("step")
    assert [st["seq"] for st in s["steps"]] == sorted(st["seq"] for st in s["steps"])


def test_resolve_endpoint(client, tenant):
    inc = next(d for e, d in run_team(client, tenant, {"X-Access-Code": CODE}) if e == "report")["incident_id"]
    r = client.post(f"/api/incidents/{inc}/resolve", headers={"X-Access-Code": CODE}, json={"tenant": tenant, "resolved_by_ids": ["per:priya-nair"],
                                                            "what_fixed_it": "Priya rolled back RULES_CACHE_TTL to 300s"})
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["mode"] == "mock"


def test_brain_ask_and_sessions(client, tenant):
    code = {"X-Access-Code": CODE}  # with the code the conversation is persisted in the graph
    r = client.post("/api/brain/ask", headers=code, json={"tenant": tenant, "user": "ann", "question": "Why must RULES_CACHE_TTL stay at 300 seconds?"}).json()
    assert r["mode"] == "mock" and {c["node_id"] for c in r["citations"]} >= {"dec:rules-cache-ttl"} and r["persisted"]
    f = client.post("/api/brain/ask", headers=code, json={"tenant": tenant, "user": "ann", "question": "Who should I talk to about that?",
                                                          "session_id": r["session_id"]}).json()
    assert "per:priya-nair" in f["people"] and f["turn"] == 2
    assert r["session_id"] in {s["id"] for s in client.get("/api/sessions", params={"tenant": tenant, "user": "ann"}).json()}
    assert r["session_id"] not in {s["id"] for s in client.get("/api/sessions", params={"tenant": tenant, "user": "bo"}).json()}
    stolen = client.post("/api/brain/ask", headers=code, json={"tenant": tenant, "user": "bo", "question": "x?", "session_id": r["session_id"]})
    assert stolen.status_code == 403


def test_replay_golden(client):
    with client.stream("POST", "/api/replay/team-session1.json", params={"delay_ms": 0}) as r:
        ev = events(r)
    names = [e for e, _ in ev]
    assert ev[0][1]["mode"] == "replay" and names.count("handoff") == 3 and names[-2:] == ["report", "done"]
    learned = [d for e, d in ev if e == "step" and d["tool"] == "record_learned_dependency"][0]
    assert any(w["type"] == "DEPENDS_ON" and w["origin"] == "agent" for w in learned["writes"]["edges"])
    r = client.post("/api/replay/..%2F..%2F.env")  # never a file outside runs/golden (the SPA catch-all is GET-only)
    assert r.status_code in (404, 405) and "ACCESS_CODE" not in r.text
    assert client.post("/api/replay/nope.json").status_code == 404


def test_admin_needs_the_code(client, tenant):
    assert client.post("/api/admin/reseed", json={"tenant": tenant}).status_code == 403
    assert client.post("/api/admin/reseed", json={"tenant": tenant}, headers={"X-Access-Code": "wrong"}).status_code == 403
    r = client.post("/api/admin/reseed", json={"tenant": tenant}, headers={"X-Access-Code": CODE})
    assert r.status_code == 200 and r.json()["nodes"] > 100


def test_daily_cap_blocks_run_n_plus_1(client, tenant, monkeypatch):
    monkeypatch.setenv("DAILY_LIVE_RUNS", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-real-key")
    monkeypatch.setattr(guard, "live_key", lambda now=None: "ib:live_runs:pytest")
    monkeypatch.setattr(main, "make_llm", lambda mode: LLMClient(mode="mock"))  # "live" without the network
    redis().delete("ib:live_runs:pytest")
    try:
        first = run_team(client, tenant, {"X-Access-Code": CODE}, live=True)
        assert first[0][1]["mode"] == "live"
        r = client.post("/api/team/run", headers={"X-Access-Code": CODE},
                        json={"tenant": tenant, "service_id": "svc:payments-api", "symptom": "5xx", "live": True})
        assert r.status_code == 429 and "cap" in r.json()["detail"]
        assert redis().ttl("ib:live_runs:pytest") > 0
    finally:
        redis().delete("ib:live_runs:pytest")


def test_rate_limit(client, tenant, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")
    main.limiter.buckets.clear()
    codes = [client.get("/api/tenants").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]
    assert client.get("/api/health").status_code == 200  # health is never limited


def test_network_is_blocked_in_tests():
    import socket
    with pytest.raises(RuntimeError, match="network"):
        socket.create_connection(("1.1.1.1", 443), timeout=1)
