"""M2: memory write tools, the three-agent team, resolve, Session 2 recall, no-memory compare, concurrency. Mock only."""
import threading

import pytest

from backend import demo
from backend.agents.team import run_team
from backend.db import get_graph
from backend.memory.sessions import start_session
from backend.tools.memory_tools import MEMORY_TOOLS
from backend.tools.receipt import ToolContext
from backend.tools.registry import call

RR, CS, PA = "svc:risk-rules", "svc:config-service", "svc:payments-api"
CHAT = "chat:risk-eng-config-load"
QUOTE = "On every cache miss risk-rules polls config-service's internal /v1/rulesets endpoint."


def one(g, q, p=None):
    return g.ro_query(q, p or {}).result_set


# ───────────── write tools ─────────────
@pytest.fixture(scope="module")
def mem(fresh):
    name = fresh("kestrel_pay_mem")
    ctx = ToolContext(tenant=name)
    ctx.session_id = start_session(name, "tester", "team")
    w = lambda tool, **a: call(tool, a, ctx, MEMORY_TOOLS)
    inc = w("open_incident", service_id=PA, symptom="5xx on payments-api", severity=2).result
    return {"ctx": ctx, "g": get_graph(name), "w": w, "inc": inc}


def written_ok(g, out, label, node_id, ses):
    """origin agent + WRITTEN_IN + a receipt with at least one write query."""
    assert "error" not in out.result, out.result
    assert any(q.get("write") for q in out.receipt["queries"]) and out.receipt["highlight"]["nodes"]
    assert one(g, f"MATCH (n:{label} {{id:$id}})-[:WRITTEN_IN]->(:Session {{id:$s}}) RETURN n.origin, n.created_at",
               {"id": node_id, "s": ses})[0][0] == "agent"


def test_open_incident(mem):
    g, inc, ses = mem["g"], mem["inc"], mem["ctx"].session_id
    assert inc["key"].startswith("INC-") and inc["id"] == "inc:" + inc["key"][4:]
    assert inc["key"] not in ("INC-2026-012", "INC-2026-031")  # next free, never a seeded key
    assert one(g, "MATCH (s:Session {id:$s})-[:FOR_INCIDENT]->(i:Incident {id:$i})-[a:AFFECTED]->(:Service {id:$p}) "
                  "RETURN i.status, a.origin", {"s": ses, "i": inc["id"], "p": PA}) == [["open", "agent"]]
    out = mem["w"]("open_incident", service_id=PA, symptom="again", severity=3)
    written_ok(g, out, "Incident", out.result["id"], ses)
    assert out.result["key"] != inc["key"]


def test_update_incident(mem):
    out = mem["w"]("update_incident", incident_id=mem["inc"]["id"], cause_deploy_id="dep:risk-rules-v2.8.0",
                   cause_service_id=RR, affected_ids=["svc:fraud-scoring"], root_cause_id="rc:cache-ttl-thundering-herd")
    assert "error" not in out.result, out.result
    assert {r[0] for r in one(mem["g"], "MATCH (:Incident {id:$i})-[:CAUSED_BY]->(c) RETURN c.id", {"i": mem["inc"]["id"]})} == {
        "dep:risk-rules-v2.8.0", RR}
    assert "error" in mem["w"]("update_incident", incident_id="inc:2025-031", status="open").result  # seeded history is read-only
    assert "error" in mem["w"]("update_incident", incident_id=mem["inc"]["id"], cause_deploy_id="dep:nope").result


def test_learned_dependency_and_duplicate(mem):
    g, w = mem["g"], mem["w"]
    bad = w("record_learned_dependency", from_service_id=RR, to_service_id=CS, kind="sync", statement="x calls y",
            confidence=0.8, sources=[{"node_id": CHAT, "excerpt": "risk-rules talks to config-service all the time"}])
    assert "literal quote" in bad.result["error"]
    assert not one(g, "MATCH (:Service {id:$a})-[r:DEPENDS_ON]->(:Service {id:$b}) RETURN r", {"a": RR, "b": CS})
    out = w("record_learned_dependency", from_service_id=RR, to_service_id=CS, kind="sync",
            statement="risk-rules calls config-service", confidence=0.8, sources=[{"node_id": CHAT, "excerpt": QUOTE}])
    fid = out.result["fact_id"]
    written_ok(g, out, "Fact", fid, mem["ctx"].session_id)
    assert one(g, "MATCH (:Service {id:$a})-[r:DEPENDS_ON]->(:Service {id:$b}) RETURN r.source, r.learned_from, r.origin",
               {"a": RR, "b": CS}) == [["learned", fid, "agent"]]
    assert one(g, "MATCH (:Fact {id:$f})-[r:SOURCED_FROM]->(:ChatThread {id:$c}) RETURN r.excerpt", {"f": fid, "c": CHAT}) == [[QUOTE]]
    for a, b in ((RR, CS), (CS, RR), ("svc:payments-api", "svc:fraud-scoring")):  # learned, reverse, declared
        dup = w("record_learned_dependency", from_service_id=a, to_service_id=b, kind="sync", statement="dup",
                confidence=0.5, sources=[{"node_id": CHAT, "excerpt": QUOTE}])
        assert "already exists" in dup.result["error"]
    assert one(g, "MATCH (:Service {id:$a})-[r:DEPENDS_ON]-(:Service {id:$b}) RETURN count(r)", {"a": RR, "b": CS}) == [[1]]


def test_record_fact(mem):
    out = mem["w"]("record_fact", statement="config-service is shared by risk-rules", about_ids=[CS, RR], confidence=0.6,
                   sources=[{"node_id": CHAT, "excerpt": QUOTE}])
    written_ok(mem["g"], out, "Fact", out.result["fact_id"], mem["ctx"].session_id)
    assert "error" in mem["w"]("record_fact", statement="x", about_ids=["per:priya-nair"], confidence=0.6,
                               sources=[{"node_id": CHAT, "excerpt": QUOTE}]).result


def test_page_person(mem):
    ok = mem["w"]("page_person", person_id="per:priya-nair", incident_id=mem["inc"]["id"], message="please look")
    assert ok.result["simulated"] is True and set(ok.receipt["highlight"]["nodes"]) == {"per:priya-nair", mem["inc"]["id"]}
    gone = mem["w"]("page_person", person_id="per:arjun-mehta", incident_id=mem["inc"]["id"], message="please look")
    assert "left the company" in gone.result["error"]
    assert "error" in mem["w"]("page_person", person_id="per:nobody", incident_id=mem["inc"]["id"], message="x").result


def test_open_ticket_and_flag_stale(mem):
    t = mem["w"]("open_ticket", title="follow-up", text="restore TTL", service_id=RR, incident_id=mem["inc"]["id"])
    written_ok(mem["g"], t, "Ticket", t.result["id"], mem["ctx"].session_id)
    assert t.result["key"].startswith("OPS-")
    assert one(mem["g"], "MATCH (t:Ticket {id:$t})-[:ABOUT]->(:Incident {id:$i}) RETURN t.kind, t.status",
               {"t": t.result["id"], "i": mem["inc"]["id"]}) == [["incident-followup", "open"]]
    f = mem["w"]("flag_stale", node_id="doc:risk-rules-readme", reason="names a person who left")
    assert "error" not in f.result
    assert one(mem["g"], "MATCH (d:Doc {id:'doc:risk-rules-readme'}) RETURN d.flagged_stale, d.flagged_reason") == [
        [True, "names a person who left"]]
    assert "error" in mem["w"]("flag_stale", node_id=RR, reason="x").result


def test_resolution_similar_runbook(mem):
    g, w, inc, ses = mem["g"], mem["w"], mem["inc"]["id"], mem["ctx"].session_id
    w("update_incident", incident_id=inc, summary="5xx on payments-api. The cache TTL was rolled back.")
    # an agent can't quote what it wrote itself, only the operator's words
    bad = w("record_resolution", incident_id=inc, summary="x", steps=["x"], performed_by_ids=["per:priya-nair"],
            sources=[{"node_id": inc, "excerpt": "The cache TTL was rolled back."}])
    assert "operator" in bad.result["error"]
    w("update_incident", incident_id=inc, summary="5xx on payments-api. Resolution (operator): Priya rolled back the TTL.")
    r = w("record_resolution", incident_id=inc, summary="rolled back the TTL", steps=["roll back"],
          performed_by_ids=["per:priya-nair"], sources=[{"node_id": inc, "excerpt": "Priya rolled back the TTL."}])
    written_ok(g, r, "Resolution", r.result["id"], ses)
    assert one(g, "MATCH (i:Incident {id:$i}) RETURN i.status", {"i": inc}) == [["resolved"]]
    s = w("link_similar", incident_id=inc, other_id="inc:2025-031", score=0.8, reason="same TTL pattern")
    assert "error" not in s.result and "error" in w("link_similar", incident_id=inc, other_id=inc, score=1, reason="x").result
    rb = w("write_runbook", service_id="svc:fraud-scoring", title="Runbook: fraud-scoring latency", steps=["check risk-rules TTL"],
           sources=[{"node_id": inc, "excerpt": "Priya rolled back the TTL."}], supersedes_id="rb:fraud-scoring-latency")
    written_ok(g, rb, "Runbook", "rb:fraud-scoring-latency-v2", ses)
    assert one(g, "MATCH (n:Runbook {id:'rb:fraud-scoring-latency-v2'})-[:SUPERSEDES]->(o:Runbook {id:'rb:fraud-scoring-latency'}) "
                  "RETURN n.version") == [[2]]
    again = w("write_runbook", service_id="svc:fraud-scoring", title="t", steps=["s"],
              sources=[{"node_id": inc, "excerpt": "Priya rolled back the TTL."}], supersedes_id="rb:fraud-scoring-latency")
    assert "already superseded" in again.result["error"]


def test_seed_history_cannot_be_rewritten(mem):
    """Seed incidents are read-only for every write tool that changes an incident or links from it."""
    w = mem["w"]
    r = w("record_resolution", incident_id="inc:2025-031", summary="OVERWRITTEN", steps=["x"], performed_by_ids=["per:priya-nair"],
          sources=[{"node_id": "inc:2025-031", "excerpt": "Rolled back the TTL to 300s and added cache warm-up."}])
    assert "historical (seed)" in r.result["error"]
    assert one(mem["g"], "MATCH (r:Resolution {id:'res:2025-031'}) RETURN r.summary") != [["OVERWRITTEN"]]
    assert "historical (seed)" in w("link_similar", incident_id="inc:2025-031", other_id="inc:2026-012", score=0.5, reason="x").result["error"]
    assert "error" in w("record_fact", statement=42, about_ids=[RR], confidence=0.5,
                        sources=[{"node_id": CHAT, "excerpt": "risk-rules polls config-service"}]).result
    assert "error" in w("write_runbook", service_id=RR, title="!!!", steps=["x"],
                        sources=[{"node_id": CHAT, "excerpt": "risk-rules polls config-service"}]).result


def test_writes_need_a_session_and_valid_labels(mem):
    no_ses = ToolContext(tenant=mem["ctx"].tenant)
    assert "session" in call("open_incident", {"service_id": PA, "symptom": "x", "severity": 2}, no_ses, MEMORY_TOOLS).result["error"]
    assert "error" in mem["w"]("open_incident", service_id="per:priya-nair", symptom="x", severity=2).result
    assert "error" in mem["w"]("open_incident", service_id=PA, symptom="x", severity=9).result
    assert "error" in mem["w"]("open_incident", service_id=PA, symptom="x", severity=2, extra=1).result


# ───────────── the story: S1 team, resolve, scenario, S2 ─────────────
@pytest.fixture(scope="module")
def story(fresh):
    name = fresh("kestrel_pay_story")
    out = demo.story(name, quiet=True)
    return {**out, "g": get_graph(name)}


def test_s1_team_run(story):
    g, s1 = story["g"], story["s1"]
    inc, ses = s1["incident_id"], s1["session_id"]
    assert s1["status"] == "ok" and inc and all(a["grounding"]["ok"] for a in s1["agents"])
    assert one(g, "MATCH (i:Incident {id:$i}) RETURN i.origin", {"i": inc}) == [["agent"]]
    assert one(g, "MATCH (:Incident {id:$i})-[:CAUSED_BY]->(d:Deploy) RETURN d.id", {"i": inc}) == [["dep:risk-rules-v2.8.0"]]
    assert one(g, "MATCH (:Service {id:$a})-[r:DEPENDS_ON {source:'learned'}]->(:Service {id:$b}), "
                  "(f:Fact)-[:SOURCED_FROM]->(:ChatThread {id:$c}) WHERE f.id = r.learned_from RETURN f.id",
               {"a": RR, "b": CS, "c": CHAT})
    assert one(g, "MATCH (:Session {id:$s})<-[:IN_SESSION]-(st:Step {action:'page'})-[:CITED]->(:Person {id:'per:priya-nair'}) "
                  "RETURN count(st)", {"s": ses}) == [[1]]
    assert one(g, "MATCH (t:Ticket)-[:ABOUT]->(:Incident {id:$i}) RETURN t.key, t.status", {"i": inc})[0][1] == "open"
    assert one(g, "MATCH (d:Doc {id:'doc:risk-rules-readme'}) RETURN d.flagged_stale") == [[True]]
    assert one(g, "MATCH (st:Step {action:'handoff'})-[:IN_SESSION]->(:Session {id:$s}) RETURN collect(st.agent)",
               {"s": ses})[0][0] == ["triage", "investigator", "communicator"]


def chain_ok(g, session_id):
    n, first, last = one(g, "MATCH (st:Step)-[:IN_SESSION]->(:Session {id:$s}) RETURN count(st), min(st.seq), max(st.seq)",
                         {"s": session_id})[0]
    ids = {r[0]: r[1] for r in one(g, "MATCH (st:Step)-[:IN_SESSION]->(:Session {id:$s}) RETURN st.seq, st.id", {"s": session_id})}
    longest = one(g, "MATCH p=(:Step {id:$a})-[:NEXT*1..200]->(:Step {id:$b}) RETURN max(length(p))", {"a": ids[first], "b": ids[last]})
    return n, (n > 1 and longest == [[n - 1]] and last - first == n - 1)


def test_s1_step_chain_unbroken(story):
    n, ok = chain_ok(story["g"], story["s1"]["session_id"])
    assert ok and n == len(story["s1"]["steps"])


def test_resolve(story):
    g, inc = story["g"], story["s1"]["incident_id"]
    assert story["resolve"]["status"] == "ok"
    assert one(g, "MATCH (:Incident {id:$i})-[:RESOLVED_BY]->(r:Resolution)-[:PERFORMED_BY]->(:Person {id:'per:priya-nair'}) "
                  "MATCH (r)-[:SOURCED_FROM]->(:Incident {id:$i}) RETURN r.origin", {"i": inc}) == [["agent"]]
    assert one(g, "MATCH (:Runbook {id:'rb:fraud-scoring-latency-v2'})-[:SUPERSEDES]->(:Runbook {id:'rb:fraud-scoring-latency'}) "
                  "RETURN count(*)") == [[1]]
    steps = one(g, "MATCH (r:Runbook {id:'rb:fraud-scoring-latency-v2'}) RETURN r.steps")[0][0]
    assert "RULES_CACHE_TTL" in steps and "config-service" in steps
    sim = {r[0] for r in one(g, "MATCH (:Incident {id:$i})-[:SIMILAR_TO]->(o) RETURN o.id", {"i": inc})}
    assert {"inc:2025-031", "inc:2026-012"} <= sim
    pms = one(g, "MATCH (:Incident {id:$i})-[s:SIMILAR_TO]->(p:PublicPostmortem) RETURN p.id, s.score, s.reason, s.origin", {"i": inc})
    assert 1 <= len(pms) <= 2 and all(0 < sc <= 1 and "industry pattern" in rs and o == "agent" for _, sc, rs, o in pms)
    assert one(g, "MATCH (i:Incident {id:$i}) RETURN i.status", {"i": inc}) == [["resolved"]]


def test_s2_recall_via_learned_edge(story):
    s1, s2 = story["s1"], story["s2"]
    hit = story["s2_learned_hit"]
    assert hit and hit["neighbour"] == RR and hit["shared"] == CS and "learned" in hit["neighbour_path_sources"]
    r = s2["report"]
    assert r["likely_cause"]["service_id"] == RR and r["likely_cause"]["deploy_id"] == "dep:risk-rules-v2.8.1"
    recall = next(x for x in r["similar_past_incidents"] if x["incident_id"] == s1["incident_id"])
    assert "Priya" in recall["resolved_by"] and "RULES_CACHE_TTL" in recall["what_fixed_it"]
    assert any("rb:fraud-scoring-latency-v2 step" in a for a in r["recommended_actions"])
    t1, t2 = s1["time_to_cause"], s2["time_to_cause"]
    assert t2["llm_calls"] < t1["llm_calls"] and t2["tool_calls"] < t1["tool_calls"]


def test_steps_cite_only_existing_nodes(story):
    g = story["g"]
    assert one(g, "MATCH (:Step)-[r:CITED]->() RETURN count(r)")[0][0] > 20
    assert one(g, "MATCH (:Step)-[:CITED]->(n) WHERE n.id IS NULL RETURN count(n)") == [[0]]
    recorded = {i for s in story["s1"]["steps"] for i in s["receipt"]["highlight"]["nodes"]}
    cited = {r[0] for r in one(g, "MATCH (:Session {id:$s})<-[:IN_SESSION]-(:Step)-[:CITED]->(n) RETURN DISTINCT n.id",
                               {"s": story["s1"]["session_id"]})}
    assert cited and cited <= recorded


def test_s2_memory_first(story):
    """Session 2's Investigator recalls first, verifies memory's suspect with one tool and names the culprit at its
    3rd tool call, quoting who fixed it before and the runbook step."""
    s2 = story["s2"]
    inv = [s for s in s2["steps"] if s["agent"] == "investigator"]
    assert [s["tool"] for s in inv[:3]] == ["memory_recall", "shared_dependency_changes", "update_incident"]
    assert inv[2]["args"]["cause_deploy_id"] == "dep:risk-rules-v2.8.1"
    recall = inv[0]["result"]
    assert recall["suspects"][0]["service"] == RR and recall["learned_edges"][0]["fact"]["sources"][0]["id"] == CHAT
    assert recall["learned_edges"][0]["session"] == story["s1"]["session_id"]
    mem = recall["incidents"][0]
    assert mem["id"] == story["s1"]["incident_id"] and mem["runbook"]["id"] == "rb:fraud-scoring-latency-v2" and mem["runbook"]["version"] == 2
    t = s2["time_to_cause"]
    assert t["agent"] == "investigator" and t["agent_tool_calls"] <= 3
    key = story["s1"]["incident_key"]
    assert (f"Seen before: {key}, fixed by Priya Nair (Priya rolled back RULES_CACHE_TTL to 300s; config-service load recovered), "
            "see Runbook v2 step 2 (rb:fraud-scoring-latency-v2)") in s2["report"]["summary"]
    assert all(a["grounding"]["ok"] for a in s2["agents"])
    assert s2["report"]["industry_pattern"].startswith("Matches known industry pattern: ") and "(https://" in s2["report"]["industry_pattern"]


def test_s1_recalls_nothing_and_scans_as_before(story):
    inv = [s for s in story["s1"]["steps"] if s["agent"] == "investigator"]
    assert inv[0]["tool"] == "memory_recall" and "no memory" in inv[0]["result"]["note"]
    assert {inv[1]["tool"], inv[2]["tool"]} == {"recent_changes_downstream", "shared_dependency_changes"}
    assert inv[1]["llm_call"] == inv[2]["llm_call"]  # one turn, as before memory_recall existed


def test_no_memory_compare(fresh):
    out = demo.story(fresh("kestrel_pay_nomem"), quiet=True, compare_no_memory=True)
    nm = out["s2_nomem"]
    r = nm["report"]
    assert r["likely_cause"]["service_id"] != RR and RR not in str(r["likely_cause"])
    assert r["confidence"] == "low" and nm["time_to_cause"] is None
    assert out["s2"]["time_to_cause"]["agent_tool_calls"] <= 3  # the full story still runs after the contrast


# ───────────── concurrency ─────────────
def test_five_parallel_team_runs(fresh):
    name = fresh("kestrel_pay_conc")
    g, recs, errs = get_graph(name), [None] * 5, []

    def go(i):
        try:
            recs[i] = run_team(demo.S1_ALERT, name, f"user{i}", save=False)
        except Exception as e:  # surfaced below
            errs.append(e)
    threads = [threading.Thread(target=go, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errs and all(r["status"] == "ok" for r in recs), errs
    keys = one(g, "MATCH (i:Incident {origin:'agent'}) RETURN i.key")
    assert len(keys) == 5 and len({k[0] for k in keys}) == 5
    assert len({r["incident_id"] for r in recs}) == 5
    tickets = one(g, "MATCH (t:Ticket {origin:'agent'}) RETURN t.key")
    assert len({t[0] for t in tickets}) == len(tickets) == 5
    assert one(g, "MATCH (:Service)-[r:DEPENDS_ON {source:'learned'}]->(:Service) RETURN count(r)") == [[1]]
    assert one(g, "MATCH (n) WITH n.id AS id, count(n) AS c WHERE c > 1 RETURN id") == []
    for r in recs:
        n, ok = chain_ok(g, r["session_id"])
        assert ok and n == len(r["steps"])
        assert one(g, "MATCH (:Incident {id:$i})-[:CAUSED_BY]->(d:Deploy) RETURN d.id", {"i": r["incident_id"]}) == [
            ["dep:risk-rules-v2.8.0"]]
