"""07A: the endpoints the web UI uses. Mock only; fresh runs go through the access-code gate."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.api import main
from backend.db import client as db_client, get_graph

CODE = "open-sesame"
H = {"X-Access-Code": CODE}


@pytest.fixture(scope="module")
def tenant(fresh):
    return fresh("kestrel_pay_ui")


@pytest.fixture(scope="module")
def other(fresh):
    return fresh("northwind_test")


@pytest.fixture()
def client(monkeypatch, tenant, other):
    monkeypatch.setenv("ACCESS_CODE", CODE)
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1000")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    main.limiter.buckets.clear()
    return TestClient(main.app)


def sse(resp):
    out, ev = [], None
    for line in resp.iter_lines():
        if line.startswith("event: "):
            ev = line[7:]
        elif line.startswith("data: "):
            out.append((ev, json.loads(line[6:])))
    return out


def fresh_beat(client, tenant, beat):
    r = client.post(f"/api/story/{beat}/run", headers=H, json={"tenant": tenant})
    assert r.status_code == 200, r.text
    with client.stream("GET", r.json()["stream"]) as s:
        assert s.status_code == 200
        return sse(s)


def agent_nodes(tenant):
    return get_graph(tenant).ro_query("MATCH (n {origin:'agent'}) RETURN count(n)").result_set[0][0]


def test_meta_and_story(client, tenant, other):
    m = client.get("/api/meta").json()
    t = {x["id"]: x for x in m["tenants"]}
    assert t[tenant]["has_story"] and not t[other]["has_story"] and t[tenant]["name"] == "Kestrel Pay Ui"
    assert m["llm_modes"] == ["replay", "mock"] and m["writes_need_code"] and m["code_configured"]
    st = client.get("/api/story", params={"tenant": tenant}).json()
    assert [b["id"] for b in st["beats"]] == ["session1", "resolve", "session2", "compare"]
    assert all(b["label"] and b["replay"] for b in st["beats"])
    assert client.get("/api/story", params={"tenant": other}).json() == {"tenant": other, "name": "Northwind Test",
                                                                          "has_story": False, "beats": []}
    assert client.get("/api/story", params={"tenant": "nope"}).status_code == 404


def test_access_check(client):
    assert client.post("/api/access/check").json() == {"ok": False}
    assert client.post("/api/access/check", headers={"X-Access-Code": "x"}).json() == {"ok": False}
    assert client.post("/api/access/check", headers=H).json() == {"ok": True}


def test_replay_json_events_and_run_graph(client):
    r = client.get("/api/replay/team-session1").json()
    steps = [e["data"] for e in r["events"] if e["event"] == "step"]
    assert r["mode"] == "replay" and len(steps) == 25 and [s["seq"] for s in steps] == list(range(1, 26))
    s = steps[0]
    assert {"seq", "agent", "action", "tool", "summary", "cypher", "params", "result_preview", "highlight", "cited",
            "writes", "elements", "mode"} <= set(s) and s["mode"] == "replay" and "MATCH" in s["cypher"]
    learned = next(s for s in steps if s["tool"] == "record_learned_dependency")
    edge = next(e for e in learned["writes"]["edges"] if e["type"] == "DEPENDS_ON")
    assert edge["origin"] == "agent" and edge["props"]["source"] == "learned"
    assert {"source", "target", "type", "props"} <= set(learned["highlight"]["edges"][0])
    dec = next(s for s in steps if s["tool"] == "read_source")
    assert dec["cited"] and dec["cited"][0]["excerpt"]
    g = client.get("/api/run-graph/team-session1").json()
    ids = {n["id"] for n in g["nodes"]}
    assert g["alert"] == "svc:payments-api" and g["alert"] in ids
    for st in steps:  # the run graph contains everything any step highlights
        assert set(st["highlight"]["nodes"]) <= ids
    assert not any(i.startswith(("ses:", "step:")) for i in ids)
    leak = client.get("/api/run-graph/../../.env")  # normalised to /.env: the SPA answers with index.html or 404, never the file
    assert "ACCESS_CODE" not in leak.text and "ANTHROPIC" not in leak.text
    assert client.get("/api/run-graph/..%2F..%2F.env").status_code == 404
    assert client.get("/api/replay/nope").status_code == 404


def test_spa_serves_index_for_client_routes_but_not_for_api(client, monkeypatch, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>Incident Brain</title>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setattr(main, "DIST", tmp_path)
    assert "Incident Brain" in client.get("/explorer").text and "Incident Brain" in client.get("/").text
    r = client.get("/assets/app.js")
    assert r.text == "console.log(1)" and "immutable" in r.headers["cache-control"]
    assert client.get("/api/nope").status_code == 404 and client.get("/api/nope").json()["detail"] == "not found"
    assert "console" not in client.get("/assets/../../etc/passwd").text


def test_subgraph(client, tenant):
    g = client.get("/api/subgraph", params={"tenant": tenant, "ids": "svc:risk-rules", "hops": 1}).json()
    ids = {n["id"] for n in g["nodes"]}
    assert "svc:risk-rules" in ids and "svc:fraud-scoring" in ids and g["edges"]
    assert all({"id", "label", "name", "origin", "props"} <= set(n) for n in g["nodes"])
    assert client.get("/api/subgraph", params={"tenant": tenant}).status_code == 400


def test_compare_latest_uses_the_recordings_by_default(client, tenant):
    c = client.get("/api/compare/latest", params={"tenant": tenant}).json()
    s1, s2, nomem = c["columns"]
    assert c["source"] == "replay" and c["metric"].startswith("Investigator tool calls")
    assert s1["investigator_tool_calls_until_cause"] == 8 and s1["cause_found"] and s1["recalled_incident"] is None
    assert s2["investigator_tool_calls_until_cause"] == 3 and s2["recalled_incident"]["key"] == "INC-2026-032"
    assert s2["recalled_incident"]["fixed_by"] == ["Priya Nair"] and s2["industry_match"]
    assert not nomem["cause_found"] and nomem["cause"] is None and nomem["investigator_tool_calls_until_cause"] is None


def test_suggestions_are_generic_and_answerable(client, tenant, other):
    for t in (tenant, other):
        qs = client.get("/api/brain/suggestions", params={"tenant": t}).json()["questions"]
        assert len(qs) == 6 and len({q["question"] for q in qs}) == 6
    qs = client.get("/api/brain/suggestions", params={"tenant": tenant}).json()["questions"]
    why = next(q["question"] for q in qs if q["kind"] == "why")
    r = client.post("/api/brain/ask", json={"tenant": tenant, "user": "v", "question": why}).json()
    assert r["citations"] and r["sources"][0]["excerpt"] and not r["persisted"] and r["session_id"] is None


def test_brain_without_code_writes_nothing_but_follow_ups_work(client, tenant):
    before = agent_nodes(tenant)
    r = client.post("/api/brain/ask", json={"tenant": tenant, "user": "v", "question": "Why must RULES_CACHE_TTL stay at 300 seconds?"}).json()
    turn = {"question": r["question"], "answer": r["answer"], "citations": [{"node_id": c["node_id"]} for c in r["citations"]],
            "people": r["people"]}
    f = client.post("/api/brain/ask", json={"tenant": tenant, "user": "v", "question": "Who should I talk to about that?",
                                            "turns": [turn]}).json()
    assert "per:priya-nair" in f["people"] and f["turn"] == 2 and f["cited_graph"]["nodes"]
    unrelated = client.post("/api/brain/ask", json={"tenant": tenant, "user": "v", "turns": [turn],
                                                    "question": "What is our policy for Kubernetes cluster upgrades?"}).json()
    assert unrelated["citations"] == [] and "don't know" in unrelated["answer"]  # history is only for "that"/"it"
    stale = client.post("/api/brain/ask", json={"tenant": tenant, "user": "v", "question": "Which docs about risk-rules are out of date, and why?"}).json()
    assert stale["citations"]
    assert agent_nodes(tenant) == before  # no Session, no Step, no flag
    assert not get_graph(tenant).ro_query("MATCH (d:Doc {id:'doc:risk-rules-readme'}) RETURN d.flagged_reason").result_set[0][0]


def test_explorer_default_and_agent_only(client, tenant, other):
    e = client.get("/api/explorer", params={"tenant": tenant}).json()
    assert {n["label"] for n in e["nodes"]} == {"Service", "Team", "Person"}
    assert any("pagerank" in n for n in e["nodes"] if n["label"] == "Service") and "pageRank" in e["pagerank"]
    assert client.get("/api/explorer", params={"tenant": tenant, "labels": "Decision"}).json()["nodes"][0]["label"] == "Decision"
    assert client.get("/api/explorer", params={"tenant": tenant, "origin": "x"}).status_code == 400
    empty = client.get("/api/explorer", params={"tenant": other, "origin": "agent"}).json()
    assert empty["nodes"] == [] and empty["agent_nodes"] == 0 and empty["agent_edges"] == 0


def test_story_fresh_runs_need_the_code(client, tenant):
    for beat in ("session1", "resolve", "session2", "compare"):
        assert client.post(f"/api/story/{beat}/run", json={"tenant": tenant}).status_code == 403
        assert client.post(f"/api/story/{beat}/run", headers={"X-Access-Code": "no"}, json={"tenant": tenant}).status_code == 403
    assert client.post("/api/story/nope/run", headers=H, json={"tenant": tenant}).status_code == 404
    assert client.get("/api/stream/made-up-token").status_code == 404


def test_story_fresh_beats_end_to_end(client, tenant, other):
    before_other = agent_nodes(other)
    s1 = fresh_beat(client, tenant, "session1")
    names = [e for e, _ in s1]
    assert names[0] == "start" and s1[0][1]["mode"] == "mock" and "run" in names and "error" not in names
    run_id = next(d for e, d in s1 if e == "run")["run_id"]
    steps = [d for e, d in s1 if e == "step"]
    learned = next(s for s in steps if s["tool"] == "record_learned_dependency")
    assert any(w["type"] == "DEPENDS_ON" and w["origin"] == "agent" for w in learned["writes"]["edges"])
    g = client.get(f"/api/run-graph/{run_id}").json()
    assert {n["id"] for n in g["nodes"]} >= set(learned["highlight"]["nodes"])
    resolve = fresh_beat(client, tenant, "resolve")
    assert any(d["tool"] == "write_runbook" for e, d in resolve if e == "step")
    s2 = fresh_beat(client, tenant, "session2")
    inv = [d for e, d in s2 if e == "step" and d["agent"] == "investigator"]
    assert inv[0]["tool"] == "memory_recall"
    nomem = fresh_beat(client, tenant, "compare")
    assert next(d for e, d in nomem if e == "report")["report"]["confidence"] == "low"
    assert f"{tenant}__nomem" not in db_client().list_graphs()  # the contrast twin is deleted afterwards
    c = client.get("/api/compare/latest", params={"tenant": tenant}).json()
    assert c["source"] == "fresh" and [x["investigator_tool_calls_until_cause"] for x in c["columns"]] == [8, 3, None]
    tok = client.post("/api/story/session2/run", headers=H, json={"tenant": tenant}).json()["stream"]
    with client.stream("GET", tok) as s:
        sse(s)
    assert client.get(tok).status_code == 404  # tokens are single-use
    assert agent_nodes(other) == before_other  # the other tenant never sees any of it
    e = client.get("/api/explorer", params={"tenant": tenant, "origin": "agent"}).json()
    assert e["agent_nodes"] > 0 and any(x["type"] == "DEPENDS_ON" and x["origin"] == "agent" for x in e["edges"])


def test_seed_on_start_seeds_empty_graphs_once(monkeypatch, capsys):
    g = "kestrel_pay_iso"
    if not main.is_empty(g):
        get_graph(g).delete()
    monkeypatch.setattr(main, "allowed_tenants", lambda: [g])
    monkeypatch.delenv("SEED_ON_START", raising=False)
    main.seed_on_start()
    assert main.is_empty(g)  # off unless asked
    monkeypatch.setenv("SEED_ON_START", "1")
    try:
        main.seed_on_start()
        out = capsys.readouterr().out
        assert "14/14 checks passed" in out and "demo story played" in out
        memory = agent_nodes(g)
        assert memory > 0
        main.seed_on_start()  # a restart: the graph has data, so nothing is reseeded and memory survives
        assert agent_nodes(g) == memory and "seeded" not in capsys.readouterr().out
    finally:
        get_graph(g).delete()
