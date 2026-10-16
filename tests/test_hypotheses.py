"""Part B: hypotheses and the decision trace ("why this tool"). Mock only; the live path is tested with a fake client."""
import json

from backend.agents.firefighter import run_firefighter
from backend.agents.team import run_team
from backend.db import eval_twin, get_graph
from backend.llm import LLMClient, LLMResponse
from backend.tools.receipt import ToolContext
from seed.eval_scenarios import BY_ID, fixture
from seed.load import load

S1 = {"service_id": "svc:payments-api", "symptom": "5xx rate 12% and p99 4.1s on payments-api for the last 15 minutes"}


def test_firefighter_board_and_why():
    sc = BY_ID["k-falselead"]
    name = eval_twin("kestrel_pay_test", "hyp")
    s = load(name, reset=True, data_package="kestrel_pay", quiet=True, transform=fixture(sc))
    try:
        rec = run_firefighter(sc["alerts"][0], ToolContext(tenant=name, now=s["now"]), LLMClient(mode="mock"), save=False)
    finally:
        get_graph(name).delete()
    hs = {h["claim"].split(" ")[0]: h for h in rec["report"]["hypotheses"]}
    assert hs["dep:bank-connector-v1.20.0"]["status"] == "confirmed"
    dead = hs["dep:merchant-dashboard-v7.10.0"]
    assert dead["status"] == "rejected" and dead["contradicting"] and "hub" in dead["reason"]
    assert rec["report"]["confidence_breakdown"][0]["effect"] == "+"
    assert all(st["why"] for st in rec["steps"])  # every step says why its tool was chosen


def test_team_investigator_board_is_persisted(fresh):
    g = fresh("kestrel_pay_mem")
    rec = run_team(S1, g, "test", LLMClient(mode="mock"), save=False)
    inv = next(s for s in rec["steps"] if s["agent"] == "investigator" and s["action"] == "handoff")
    hs = inv["args"]["details"]["hypotheses"]
    assert hs[0]["status"] == "confirmed" and "risk-rules" in hs[0]["claim"]
    assert any(h["status"] == "rejected" and "email-sender" in h["claim"] for h in hs)
    rows = get_graph(g).ro_query("MATCH (st:Step) WHERE st.id = $id RETURN st.why, st.hypotheses_json",
                                 {"id": inv["step_id"]}).result_set
    assert rows[0][0] and json.loads(rows[0][1])[0]["status"] == "confirmed"


class _FakeSDK:
    """Stands in for anthropic.Anthropic: one turn with a why line + a tool call, then a submit. No network."""
    class messages:
        n = 0

        @classmethod
        def create(cls, **req):
            cls.n += 1
            assert "why <tool name>" in req["system"][0]["text"]
            Usage = type("U", (), {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0})
            Block = lambda **k: type("B", (), k)()
            if cls.n == 1:
                content = [Block(type="text", text="why recent_changes: every change is a lead"),
                           Block(type="tool_use", id="t1", name="recent_changes", input={"since_minutes": 120})]
            else:
                content = [Block(type="text", text="done")]
            return type("R", (), {"content": content, "usage": Usage(), "stop_reason": "tool_use"})()


def test_live_path_parses_why_lines(ctx):
    llm = LLMClient(mode="live", model="claude-haiku-5-5")
    llm._sdk = _FakeSDK
    rec = run_firefighter(S1, ctx, llm, max_steps=2, save=False)
    assert rec["steps"][0]["tool"] == "recent_changes" and rec["steps"][0]["why"] == "every change is a lead"
    assert rec["totals"]["llm_calls"] == 2 and isinstance(LLMResponse, type)
