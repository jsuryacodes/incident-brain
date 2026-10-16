"""Firefighter playground: run the Firefighter on any scenario from the library (or your own alerts) on a fresh copy of
the company, never on the hero graph. Visitors watch recordings (runs/golden/ff-<scenario>.json, each with the action
plan approved and verified); with the access code a fresh mock run streams live and its plan can be approved.

python -m backend.agents.playground --record     # (re)record every scenario of the library, approved + verified
"""
import argparse
import json

from backend.agents.actions import execute
from backend.agents.firefighter import run_firefighter
from backend.api.views import run_graph
from backend.db import eval_twin, get_graph
from backend.llm import LLMClient
from backend.tools.receipt import ToolContext
from seed.eval_scenarios import BY_ID, SCENARIOS, fixture
from seed.load import load, package_for

GOLDEN_PREFIX = "ff-"
LIVE_TWINS = {}  # twin graph -> run_id of the run whose copy of the company it holds (only that run may be approved)


def twin(tenant):
    return eval_twin(tenant, "play")  # one per company; the next run replaces it


def scenarios(tenant, golden_dir):
    pkg = package_for(tenant)
    return [{"id": s["id"], "tenant": s["tenant"], "shape": s["shape"], "why": s["why"], "alerts": s["alerts"],
             "replay": GOLDEN_PREFIX + s["id"] if (golden_dir / f"{GOLDEN_PREFIX}{s['id']}.json").is_file() else None}
            for s in SCENARIOS if s["tenant"] == pkg]


def run(tenant, scenario_id=None, alerts=None, llm=None, on_step=None):
    """A fresh Firefighter run on a twin of `tenant`: a library scenario's fixture, or the plain seed plus your alerts.
    The twin is kept so the action plan can be approved. -> the run record with its graph snapshot."""
    sc = BY_ID.get(scenario_id) if scenario_id else None
    if scenario_id and (not sc or sc["tenant"] != package_for(tenant)):
        raise LookupError(f"no scenario {scenario_id!r} for {tenant!r}")
    if not sc and not alerts:
        raise LookupError("pick a scenario or give at least one alert")
    name = twin(tenant)
    summary = load(name, reset=True, data_package=package_for(tenant), quiet=True, transform=fixture(sc) if sc else None)
    a = sc["alerts"] if sc else alerts
    # the playground always selects its tools THROUGH MCP (an MCP client session to our server, pinned to this copy)
    rec = run_firefighter(a[0] if len(a) == 1 else a, ToolContext(tenant=name, now=summary["now"]), llm or LLMClient(),
                          on_step=on_step, save=False, tools_via="mcp")
    rec.update(twin=name, scenario=scenario_id)
    LIVE_TWINS[name] = rec["run_id"]
    rec["graph"] = run_graph(name, rec)
    return rec


def record(tenant, golden_dir):
    """Record every library scenario of this company with its whole plan approved and verified (for visitors)."""
    for s in scenarios(tenant, golden_dir):
        rec = run(tenant, s["id"], llm=LLMClient(mode="mock"))
        try:
            rec["execution"] = {k: v for k, v in execute(rec["twin"], rec, None, "jaya").items() if k != "steps"}
        finally:
            get_graph(rec["twin"]).delete()
        (golden_dir / f"{GOLDEN_PREFIX}{s['id']}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False, default=str))
        print(f"recorded {s['id']}: {rec['status']}, {len(rec['steps'])} steps")


def main():
    from backend.demo import GOLDEN
    ap = argparse.ArgumentParser(prog="python -m backend.agents.playground")
    ap.add_argument("--record", action="store_true")
    a = ap.parse_args()
    if a.record:
        for t in ("kestrel_pay", "northwind_health"):
            record(t, GOLDEN)


if __name__ == "__main__":
    main()
