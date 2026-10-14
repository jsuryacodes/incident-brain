"""Story assertions on a Firefighter run record (payments-api scenario).

python -m backend.agents.check_run runs/<file>.json   -> PASS/FAIL per line, exit 1 on any failure.
"""
import json
import sys

PA, FS, RR = "svc:payments-api", "svc:fraud-scoring", "svc:risk-rules"


def checks(rec):
    r = rec.get("report") or {}
    lc = r.get("likely_cause") or {}
    cd = r.get("conflicting_decision") or {}
    sims = [s.get("incident_id") for s in r.get("similar_past_incidents") or []]
    return [
        ("likely_cause.service_id == svc:risk-rules", lc.get("service_id") == RR, lc.get("service_id")),
        ("deploy_id == dep:risk-rules-v2.8.0", lc.get("deploy_id") == "dep:risk-rules-v2.8.0", lc.get("deploy_id")),
        ("ticket_key == RISK-412", lc.get("ticket_key") == "RISK-412", lc.get("ticket_key")),
        ("path is payments-api -> fraud-scoring -> risk-rules", lc.get("path") == [PA, FS, RR], lc.get("path")),
        ("contact.person_id == per:priya-nair", (r.get("contact") or {}).get("person_id") == "per:priya-nair",
         (r.get("contact") or {}).get("person_id")),
        ("bus_factor_warning mentions Arjun", "Arjun" in (r.get("bus_factor_warning") or ""), r.get("bus_factor_warning")),
        ("conflicting_decision is dec:rules-cache-ttl from chat:risk-eng-config-load",
         cd.get("decision_id") == "dec:rules-cache-ttl" and cd.get("source_id") == "chat:risk-eng-config-load",
         (cd.get("decision_id"), cd.get("source_id"))),
        ("similar_past_incidents includes inc:2025-031", "inc:2025-031" in sims, sims),
        ("blast_radius includes web-checkout", "svc:web-checkout" in (r.get("blast_radius") or []), len(r.get("blast_radius") or [])),
        ("grounding.ok", (rec.get("grounding") or {}).get("ok") is True, rec.get("grounding")),
        ("status == ok", rec.get("status") == "ok", rec.get("status")),
        ("<= 6 LLM calls", (rec.get("totals") or {}).get("llm_calls", 99) <= 6, (rec.get("totals") or {}).get("llm_calls")),
    ]


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python -m backend.agents.check_run runs/<file>.json")
    rec = json.loads(open(sys.argv[1]).read())
    res = checks(rec)
    for i, (name, ok, got) in enumerate(res, 1):
        print(f"{i:2d}. {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"   (got {got!r})"))
    print(f"\n{sum(ok for _, ok, _ in res)}/{len(res)} passed")
    sys.exit(0 if all(ok for _, ok, _ in res) else 1)


if __name__ == "__main__":
    main()
