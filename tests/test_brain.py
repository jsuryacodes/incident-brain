"""M3: Ask the Brain + persistent conversation history. Mock only."""
import copy
import subprocess
import sys

import pytest

from backend import demo
from backend.agents import mock_policy
from backend.agents.brain import ask, list_sessions
from backend.agents.brain_eval import run_eval
from backend.llm import LLMClient


def test_eval_passes_on_fresh_seed(fresh):
    res = run_eval(fresh("kestrel_pay_brain2"), quiet=True)
    assert all(r["ok"] for r in res), [(r["q"], r["problems"]) for r in res]


def test_eval_has_15_kestrel_and_3_northwind_questions():
    from backend.agents.brain_eval import EVAL
    assert len(EVAL["kestrel_pay"]) == 15 and len(EVAL["northwind_health"]) == 3


def test_northwind_eval_passes(fresh):
    res = run_eval(fresh("northwind_test"), quiet=True)
    assert len(res) == 3 and all(r["ok"] for r in res), [(r["q"], r["problems"]) for r in res]


def test_eval_passes_after_story_with_learned_reason(fresh):
    g = fresh("kestrel_pay_brain")
    demo.story(g, quiet=True)
    res = run_eval(g, quiet=True)  # Q4 now also requires missing_learned_dependency
    assert all(r["ok"] for r in res), [(r["q"], r["problems"]) for r in res]


def test_followup_after_new_process(fresh):
    g = fresh("kestrel_pay_brain2")
    code = ("from backend.agents.brain import ask; "
            f"print(ask({g!r}, 'jaya', 'Why must RULES_CACHE_TTL stay at 300 seconds?')['session_id'])")
    sid = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.split()[-1]
    r = ask(g, "jaya", "Who should I talk to about that?", sid)  # this process never saw turn 1
    assert r["turn"] == 2 and r["session_id"] == sid and "per:priya-nair" in r["people"]
    assert r["grounding"]["ok"]


def test_sessions_are_per_user(fresh):
    g = fresh("kestrel_pay_brain2")
    a = ask(g, "alice", "Why must RULES_CACHE_TTL stay at 300 seconds?")
    b = ask(g, "bob", "Arjun left. Who knows risk-rules best now?")
    alice = {s["id"] for s in list_sessions(g, "alice")}
    assert a["session_id"] in alice and b["session_id"] not in alice
    with pytest.raises(PermissionError):
        ask(g, "alice", "Who should I talk to about that?", b["session_id"])


def _fake(change):
    def policy(agent, system, tools, messages):
        out = mock_policy.respond(agent, system, tools, messages)
        for blk in out:
            if blk["name"] == "submit_answer":
                blk["input"] = copy.deepcopy(blk["input"])
                change(blk["input"])
        return out
    return policy


@pytest.mark.parametrize("change,needle", [
    (lambda a: a["citations"].append({"node_id": "doc:made-up", "excerpt": "an excerpt that is long enough"}), "doc:made-up"),
    (lambda a: a["citations"][0].update(excerpt="RULES_CACHE_TTL can be anything you like"), "literal quote"),
    (lambda a: a.update(citations=[]), "cite at least one source"),
])
def test_grounding_rejects_fake_citations(fresh, change, needle):
    g = fresh("kestrel_pay_brain2")
    r = ask(g, "jaya", "Why must RULES_CACHE_TTL stay at 300 seconds?", llm=LLMClient(mode="mock", policy=_fake(change)))
    submits = [s for s in r["steps"] if s["tool"] == "submit_answer"]
    assert needle in submits[0]["result"]["error"]
    assert r["grounding"]["ok"] is False
