"""Firefighter eval: the scenario library (seed/eval_scenarios.py) on twin graphs, scored per agent profile.

python -m backend.agents.firefighter_eval [--only k-deep,n-two] [--profiles full,no_algo,no_graph] [--generated 50]
                                         [--holdout PATH] [--no-write]

For each scenario: load a fresh seed of its tenant into `<tenant>__eval_<id>` with the scenario's fixture, run the
Firefighter once per profile (every tool is read-only, so one twin serves all profiles), score the report against the
expected answers, delete the twin. Mock mode only: the planner is the deterministic policy, so a run costs nothing.

Profiles (same planner, same loop, same report format and grounding checks; only the tools differ):
  full      every read tool
  no_algo   "graph, no algorithms": no algo.* procedure may run (see baseline_noalgo.py)
  no_graph  full-text search + a flat change log only (see baseline_text.py)
Sets: "dev" = the hand-written library (seed/eval_scenarios.py); "generated" = N seeded random scenarios
(seed/eval_generator.py); "holdout" = scenarios written by someone who never saw the planner (--holdout file with a
SCENARIOS list), run once. Writes runs/eval/latest.json and docs/eval.md.
"""
import importlib.util
import argparse
import json
import re
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from backend.agents.firefighter import RUNS, run_firefighter
from backend.db import client, eval_twin, get_graph
from backend.llm import LLMClient
from backend.tools.receipt import ToolContext
from backend.tools.registry import TOOLS
from seed import eval_generator
from seed.eval_scenarios import SCENARIOS, fixture
from seed.load import load

ROOT = Path(__file__).resolve().parents[2]
OUT = RUNS / "eval" / "latest.json"
DOC = ROOT / "docs" / "eval.md"
ROLLBACK = re.compile(r"(?i)\b(?:roll ?back|revert|undo)\b")
DEP_ID = re.compile(r"\bdep:[\w.\-]*\w")
PER_ID = re.compile(r"\bper:[\w.\-]*\w")

PROFILES = {"full": {"title": "Full Incident Brain", "tools": None, "algorithms": True,
                     "about": "every read tool: traversals, algorithms (PageRank, betweenness, shortest paths), full-text, memory"}}
try:  # each baseline is its own module (and commit)
    from backend.agents.baseline_noalgo import PROFILE as _NOALGO
    PROFILES["no_algo"] = _NOALGO
except ImportError:
    pass
try:
    from backend.agents.baseline_text import PROFILE as _TEXT
    PROFILES["no_graph"] = _TEXT
except ImportError:
    pass


TWIN_BASE = {}  # tenant -> graph name the twins are named after (tests point this at their allowed scratch names)


def twin_name(sc):
    return eval_twin(TWIN_BASE.get(sc["tenant"], sc["tenant"]), sc["id"].replace("-", "_"))


def cleanup_stale(extra=()):
    """Delete this eval's own twins left behind by a crashed run (only the scenario twins it creates)."""
    mine = {twin_name(sc) for sc in list(SCENARIOS) + list(extra)}
    for name in client().list_graphs():
        if name in mine:
            try:
                client().select_graph(name).delete()
            except Exception:
                pass


def got_incidents(report, alerts):
    if not report:
        return []
    if report.get("incidents"):
        return report["incidents"]
    return [{"alerts": [a["service_id"] for a in alerts], **{k: report.get(k) for k in
            ("likely_cause", "contact", "recommended_actions", "look_first", "root")}}]


def score(sc, rec, twin):
    """Metrics for one run against the scenario's expected answers."""
    exp, rep = sc["expect"], rec.get("report")
    got = got_incidents(rep, sc["alerts"])
    g = get_graph(twin)
    status = dict(g.ro_query("MATCH (p:Person) RETURN p.id, p.status").result_set)
    m = {"cause_correct": 0, "path_correct": 0, "incidents_expected": len(exp["incidents"]),
         "cause_expected": any(e["cause_deploy"] or e.get("root") for e in exp["incidents"])}
    pages_ok = 0
    for e in exp["incidents"]:
        mine = next((x for x in got if e["alerts"][0] in (x.get("alerts") or [])), None) or {}
        lc = mine.get("likely_cause") or {}
        m["cause_correct"] += (lc.get("deploy_id") == e["cause_deploy"] and lc.get("service_id") == e["cause_service"]
                               and (mine.get("root") or {}).get("service_id") == e.get("root"))
        m["path_correct"] += (lc.get("path") or []) == (e["path"] or [])
        c = mine.get("contact") or {}
        want = e["contact"]
        pages_ok += (c.get("person_id") == want and status.get(want) == "active") if want.startswith("per:") else (
            c.get("team_id") == want and not c.get("person_id"))
    m["grouping_exact"] = sorted(sorted(x.get("alerts") or []) for x in got) == sorted(sorted(e["alerts"]) for e in exp["incidents"])
    causes = {e["cause_deploy"] for e in exp["incidents"] if e["cause_deploy"]}
    rolled, paged, wrong = set(), set(), 0
    for x in got:  # actions are scored per incident: a right rollback or page in the wrong incident is still wrong
        e = next((e for e in exp["incidents"] if set(x.get("alerts") or []) & set(e["alerts"])), None)
        acts = x.get("recommended_actions") or []
        r = {d for a in acts if ROLLBACK.search(a) for d in DEP_ID.findall(a)}
        p = {q for a in acts for q in PER_ID.findall(a)} | ({(x.get("contact") or {}).get("person_id")} - {None})
        rolled |= r
        paged |= p
        wrong += len(r - ({e["cause_deploy"]} if e and e["cause_deploy"] else set())) + len(p - ({e["contact"]} if e else set()))
    named = {(x.get("likely_cause") or {}).get("deploy_id") for x in got}
    leads = {r["deploy_id"]: r.get("reason") for r in (rep or {}).get("rejected_leads") or []}
    m["false_leads"] = len(exp["false_leads"])
    m["false_leads_rejected"] = sum(1 for d in exp["false_leads"]
                                    if d not in named and d not in rolled and str(leads.get(d) or "").strip())
    m["cause_also_rejected"] = sorted(causes & set(leads))  # naming a cause and rejecting it is a contradiction
    m["paged_right"] = pages_ok
    m["paged_left_person"] = sorted(p for p in paged if status.get(p) == "left" or p in exp["never_page"])
    m["wrong_actions"] = wrong
    lf = exp.get("look_first")
    pointer = [s for x in got for s in ((x.get("look_first") or {}).get("service_ids") or [])[:1]]
    m["look_first_ok"] = None if not lf else bool(pointer) and pointer[0] in lf
    m["pages_sent"] = len({(x.get("contact") or {}).get("person_id") or (x.get("contact") or {}).get("team_id") for x in got} - {None})
    m["pages_suppressed"] = len((rep or {}).get("suppressed_pages") or [])
    m["tool_calls"] = rec["totals"]["tool_calls"]
    m["llm_calls"] = rec["totals"]["llm_calls"]
    m["grounding_ok"] = rec["status"] == "ok" and (rec.get("grounding") or {}).get("ok") is True
    m["used_algorithms"] = sorted({q["cypher"].split("algo.", 1)[1].split("(", 1)[0] for s in rec["steps"]
                                   for q in s["receipt"].get("queries", []) if "algo." in q["cypher"]})
    m["passed"] = bool(m["cause_correct"] == m["incidents_expected"] and m["path_correct"] == m["incidents_expected"]
                       and m["grouping_exact"] and m["false_leads_rejected"] == m["false_leads"] and not m["cause_also_rejected"]
                       and m["paged_right"] == m["incidents_expected"] and not m["paged_left_person"]
                       and m["wrong_actions"] == 0 and m["look_first_ok"] is not False and m["grounding_ok"])
    return m


def brief(rec):
    rep = rec.get("report") or {}
    return {"summary": rep.get("summary"), "status": rec["status"],
            "causes": [(x.get("likely_cause") or {}).get("deploy_id") for x in got_incidents(rep, [])] if rep.get("incidents")
            else [(rep.get("likely_cause") or {}).get("deploy_id")],
            "rejected_leads": rep.get("rejected_leads"), "look_first": rep.get("look_first"),
            "steps": [{"tool": s["tool"], "summary": s["summary"][:200]} for s in rec["steps"]]}


def run_scenario(sc, profiles, llm, kind="dev"):
    twin = twin_name(sc)
    out = {"id": sc["id"], "set": kind, "tenant": sc["tenant"], "shape": sc["shape"], "why": sc["why"],
           "alerts": sc["alerts"], "expect": sc["expect"], "results": {}}
    try:
        summary = load(twin, reset=True, data_package=sc["tenant"], quiet=True, transform=fixture(sc))
        for name in profiles:
            p = PROFILES[name]
            ctx = replace(ToolContext(tenant=twin, now=summary["now"]), algorithms=p["algorithms"])
            alert = sc["alerts"][0] if len(sc["alerts"]) == 1 else sc["alerts"]
            rec = run_firefighter(alert, ctx, llm, save=False, tool_names=p["tools"])
            out["results"][name] = {**score(sc, rec, twin), "run": brief(rec)}
    finally:
        get_graph(twin).delete()
    return out


TOTAL_KEYS = ("passed", "cause_correct", "incidents_expected", "path_correct", "false_leads_rejected", "false_leads",
              "paged_right", "wrong_actions", "tool_calls")


def totals(scenarios, profiles):
    t = {}
    for p in profiles:
        rs = [s["results"][p] for s in scenarios]
        if not rs:
            continue
        t[p] = {k: sum(int(r[k]) for r in rs) for k in TOTAL_KEYS}
        t[p]["scenarios"] = len(rs)
        t[p]["paged_left_person"] = sum(len(r["paged_left_person"]) for r in rs)
        t[p]["grounding_ok"] = sum(r["grounding_ok"] for r in rs)
    return t


def load_holdout(path):
    spec = importlib.util.spec_from_file_location("eval_holdout", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SCENARIOS


def run_eval(only=None, profiles=None, write=True, llm=None, generated=0, holdout=None):
    llm = llm or LLMClient(mode="mock")
    profiles = [p for p in (profiles or PROFILES) if p in PROFILES]
    sets = [("dev", [s for s in SCENARIOS if not only or s["id"] in only])]
    if generated:
        sets.append(("generated", eval_generator.scenarios(generated)))
    if holdout:
        sets.append(("holdout", load_holdout(holdout)))
    cleanup_stale([sc for _, scs in sets for sc in scs])
    t0 = time.time()
    scenarios = [run_scenario(sc, profiles, llm, kind) for kind, scs in sets for sc in scs]
    res = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "mode": llm.mode,
           "profiles": {p: {k: PROFILES[p][k] for k in ("title", "about")} for p in profiles},
           "scenarios": scenarios, "seconds": round(time.time() - t0, 1),
           "totals": {kind: totals([s for s in scenarios if s["set"] == kind], profiles) for kind, _ in sets}}
    if write and not only:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
        DOC.write_text(render(res))
    return res


# ───────────── docs/eval.md ─────────────
def _cell(r):
    if r is None:
        return "–"
    marks = "✓" if r["passed"] else "✗"
    bits = [f"cause {r['cause_correct']}/{r['incidents_expected']}" if r.get("cause_expected", True) else
            ("no cause: right" if r["cause_correct"] else "no cause expected: wrong")]
    if r["false_leads"]:
        bits.append(f"leads {r['false_leads_rejected']}/{r['false_leads']}")
    if r["look_first_ok"] is not None:
        bits.append("hub ✓" if r["look_first_ok"] else "hub ✗")
    bits.append(f"page {r['paged_right']}/{r['incidents_expected']}")
    if r["wrong_actions"]:
        bits.append(f"**{r['wrong_actions']} wrong action{'s' * (r['wrong_actions'] > 1)}**")
    bits.append(f"{r['tool_calls']} calls")
    return f"{marks} " + ", ".join(bits)


SET_TITLES = {"dev": "Scenario library (hand-written)", "generated": "Generated (seeded random)",
              "holdout": "Held-out (written by someone who never saw the planner, run once)"}


def render(res):
    ps = list(res["profiles"])
    L = ["# Firefighter eval", "",
         "> Generated by `python -m backend.agents.firefighter_eval` (mock mode: the deterministic planner; no LLM, no cost). "
         f"Last run: {res['generated_at']}, {res['seconds']} s. Raw results: `runs/eval/latest.json` (also `GET /api/eval/latest`).",
         "",
         "Each scenario is a fixture applied to a fresh copy of one company in a twin graph `<tenant>__eval_<id>`: seeded, "
         "run, scored, deleted; the hero graphs are not used. The hand-written expectations are re-derived by an "
         "independent oracle (`seed/eval_oracle.py`: plain Python BFS, PageRank and the who-to-call formula over the "
         "fixture's own data, no Cypher, no agent tool) in `tests/test_eval_scenarios.py`.", "",
         "**Profiles** (same planner, same loop, same report format, same grounding checks; only the tools differ):", ""]
    L += [f"- **{res['profiles'][p]['title']}** (`{p}`): {res['profiles'][p]['about']}" for p in ps]
    L += ["", "## Scores", "", "| Set | Profile | Scenarios passed | Causes right | False leads rejected | Right person paged | "
          "Wrong actions | Paged someone who left | Tool calls |", "|---|---|---|---|---|---|---|---|---|"]
    for kind, tot in res["totals"].items():
        for p in ps:
            if p not in tot:
                continue
            t = tot[p]
            L.append(f"| {SET_TITLES.get(kind, kind)} | {res['profiles'][p]['title']} | **{t['passed']}/{t['scenarios']}** | "
                     f"{t['cause_correct']}/{t['incidents_expected']} | {t['false_leads_rejected']}/{t['false_leads']} | "
                     f"{t['paged_right']}/{t['incidents_expected']} | {t['wrong_actions']} | {t['paged_left_person']} | {t['tool_calls']} |")
    for kind in res["totals"]:
        rows = [s for s in res["scenarios"] if s["set"] == kind]
        L += ["", f"## {SET_TITLES.get(kind, kind)}: per scenario", ""]
        if kind == "generated":
            n_decoy = sum(1 for s in rows if s["expect"]["false_leads"])
            L += [f"{len(rows)} scenarios from `seed/eval_generator.py`: a random alert, a culprit 1-4 hops down where the "
                  f"shortest path is unique, and (in {n_decoy} of them) a decoy deploy the alert cannot reach and shares no "
                  "dependency with, often fresher than the culprit. Their expected path and contact come from the oracle "
                  "itself; what is independent there is the agent having to find them. Results:", ""]
            fails = [(s, p) for s in rows for p in ps if not s["results"][p]["passed"]]
            for p in ps:
                f = [s["id"] for s, q in fails if q == p]
                L.append(f"- {res['profiles'][p]['title']}: {len(rows) - len(f)}/{len(rows)} passed"
                         + (f"; failed {', '.join(f[:12])}{' …' if len(f) > 12 else ''}" if f else ""))
            continue
        L += ["| Scenario | Shape | " + " | ".join(res["profiles"][p]["title"] for p in ps) + " |", "|---|---|" + "---|" * len(ps)]
        for s in rows:
            L.append(f"| `{s['id']}` ({s['tenant']}) | {s['shape']} | " + " | ".join(_cell(s["results"].get(p)) for p in ps) + " |")
    L += ["", "A scenario passes when every incident has the right cause (deploy and service) and path, alerts are grouped "
          "into the right incidents, every false lead is rejected (not named, not rolled back, listed with a reason), the "
          "right active person (or, when nobody active owns the service, the team) is paged, nobody who left is paged, no "
          "wrong action is recommended (rollbacks and pages are checked per incident), no cause is also listed as a "
          "rejected lead, the hub pointer is right when nothing changed, and the report is grounded."
          + (" The no-graph profile can never give a dependency path, so it can't pass a scenario that has a cause; its "
             "'causes right' column is the fair comparison. 'Right person paged' is defined by the graph's who-to-call "
             "formula, so its deployer heuristic is at a structural disadvantage there too, and a wrong page counts both "
             "there and as a wrong action." if "no_graph" in ps else "")
          + (" Scenarios where the graph ALGORITHMS changed the outcome (full passes, no-algorithms fails): "
             + (", ".join(f"`{s['id']}`" for s in res["scenarios"] if s["results"]["full"]["passed"]
                          and not s["results"]["no_algo"]["passed"]) or "none")
             + ". Everywhere else the plain traversals find the same answer; the algorithm calls there (shortest "
             "paths) only draw the path." if "no_algo" in ps and "full" in ps else ""),
          "", "## What each scenario tests", ""]
    for s in res["scenarios"]:
        if s["set"] == "generated":
            continue
        L += [f"**`{s['id']}`** · {s['shape']}. {s['why']}", ""]
        for p in ps:
            r = s["results"][p]
            if not r["passed"]:
                L.append(f"- {res['profiles'][p]['title']} failed: {r['run']['summary']}")
        L.append("")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(prog="python -m backend.agents.firefighter_eval")
    ap.add_argument("--only", help="comma-separated scenario ids (dev set)")
    ap.add_argument("--profiles", help=f"comma-separated, from {sorted(PROFILES)}")
    ap.add_argument("--generated", type=int, default=50, help="seeded random scenarios to add (0 = none)")
    ap.add_argument("--holdout", help="a Python file with SCENARIOS (the held-out set)")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    res = run_eval(a.only.split(",") if a.only else None, a.profiles.split(",") if a.profiles else None,
                   not a.no_write, generated=0 if a.only else a.generated, holdout=a.holdout)
    ps = list(res["profiles"])
    print(f"{'scenario':24s}" + "".join(f"{p:>12s}" for p in ps))
    for s in res["scenarios"]:
        if s["set"] != "generated":
            print(f"{s['id']:24s}" + "".join(f"{('PASS' if s['results'][p]['passed'] else 'fail'):>12s}" for p in ps))
    for kind, tot in res["totals"].items():
        print(f"{kind + ' passed':24s}" + "".join(f"{str(tot[p]['passed']) + '/' + str(tot[p]['scenarios']):>12s}" for p in ps))
    for s in res["scenarios"]:
        r = s["results"].get("full")
        if r and not r["passed"]:
            print(f"  FULL FAILED {s['id']}: " + json.dumps({k: r[k] for k in r if k != "run"}, default=str))
            print(f"      {r['run']['summary']}")
    if not a.no_write and not a.only:
        print(f"\nwrote {OUT.relative_to(ROOT)} and {DOC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
