"""Scenario library for the Firefighter eval (docs/eval.md). Story knowledge lives HERE, never in agent code.

Each scenario is a fixture applied to a fresh seed of one tenant, loaded into a twin graph `<tenant>__eval_<id>`
(seeded, run, scored, deleted; the hero graphs are never touched). `fixture(sc)` returns a transform for
`seed.load.load(transform=...)`, so every fixture goes through the same validator and writer as the seed itself.

Fixture keys (all optional):
  quiet       True: every deploy from the last 6 h is moved back 7 days, so the scenario alone decides what changed
  deploys     [(service, version, minutes_ago, person or None, summary, ticket key or None)]
  drop_edges  [(from id, TYPE, to id)]
  learned     [(from svc, to svc, fact slug, statement, source id, verbatim excerpt)]: a DEPENDS_ON {source:'learned'}
              plus the Fact an earlier agent session would have written (origin 'agent'), SOURCED_FROM its source
  nodes/edges extra seed-shaped nodes and edges (e.g. a chat thread a learned fact quotes)

`alerts` fire together. `expect`:
  incidents   [{alerts, cause_service, cause_deploy, path, contact}]  path = alerting -> culprit service ids;
              contact = the person to page ('per:...') or the team to escalate to ('team:...')
  false_leads deploys that are recent but must NOT be named as a cause or rolled back
  look_first  when nothing changed: the shared hubs on the alert's call path (top PageRank) the report may point at,
              else None. A list: a hub and the database right behind it score within a few percent of each other, and
              PageRank implementations differ on which comes first, so either is a correct pointer
  never_page  people who must not be paged (they left)
Every expectation is re-derived by an independent oracle (plain Python BFS over the fixture's own node/edge lists,
no Cypher, no agent tools) in tests/test_eval_scenarios.py.
"""
QUIET_H, QUIET_SHIFT_D = 6, 7

_RECON_FX = ("reconciliation-job pulls fx-rates-service rates for every statement line, there is no local cache, "
             "so an fx-rates slowdown stalls the whole run.")
_RISK_POLL = "On every cache miss risk-rules polls config-service's internal /v1/rulesets endpoint."

SCENARIOS = [
    # ───────────── Kestrel Pay ─────────────
    dict(id="k-deep", tenant="kestrel_pay", shape="bad deploy 4 hops downstream",
         why="web-checkout -> api-gateway -> payments-api -> fraud-scoring -> sanctions-screening; nothing else changed.",
         fixture=dict(quiet=True, deploys=[
             ("sanctions-screening", "1.10.0", 25, "ravi-shankar", "Screen every name variant synchronously (no batch cache)", None)]),
         alerts=[{"service_id": "svc:web-checkout", "symptom": "checkout 5xx 7% and p99 3.4s for the last 12 minutes"}],
         expect=dict(incidents=[dict(alerts=["svc:web-checkout"], cause_service="svc:sanctions-screening",
                                     cause_deploy="dep:sanctions-screening-v1.10.0",
                                     path=["svc:web-checkout", "svc:api-gateway", "svc:payments-api", "svc:fraud-scoring",
                                           "svc:sanctions-screening"], contact="per:mei-lin-chen")],
                     false_leads=[], look_first=None, never_page=[])),
    dict(id="k-falselead", tenant="kestrel_pay", shape="false lead: fresher deploys off the dependency path",
         why="bank-connector (called by payouts-service) changed 45 min ago. merchant-dashboard (5 min, its summary even "
             "says 'payouts') is not called by payouts-service; it only shares dependencies with it (config-service, "
             "ledger-service, kafka-events ...). email-sender (9 min) shares nothing.",
         fixture=dict(quiet=True, deploys=[
             ("bank-connector", "1.20.0", 45, "tomasz-kowalski", "Cut partner-bank socket timeout 30s -> 2s and retry inline", None),
             ("merchant-dashboard", "7.10.0", 5, "fatima-zahra", "Payouts tab: new filters for failed payout batches", None),
             ("email-sender", "1.15.0", 9, "kenji-watanabe", "Switch to the new transactional template engine", None)]),
         alerts=[{"service_id": "svc:payouts-service", "symptom": "payout batch API 5xx 6% and failed payout batches rising for 20 minutes"}],
         expect=dict(incidents=[dict(alerts=["svc:payouts-service"], cause_service="svc:bank-connector",
                                     cause_deploy="dep:bank-connector-v1.20.0",
                                     path=["svc:payouts-service", "svc:bank-connector"], contact="per:tomasz-kowalski")],
                     false_leads=["dep:merchant-dashboard-v7.10.0", "dep:email-sender-v1.15.0"], look_first=None, never_page=[])),
    dict(id="k-nochange", tenant="kestrel_pay", shape="no recent change: capacity / traffic",
         why="Nothing deployed in the window. The honest answer is 'no change found'; the most depended-on services on "
             "payouts-service's call path (PageRank) are config-service and its database config-db (within 1% of each other).",
         fixture=dict(quiet=True),
         alerts=[{"service_id": "svc:payouts-service", "symptom": "payout API p99 2.6s with request volume 2x normal (month-end run), no deploy announced"}],
         expect=dict(incidents=[dict(alerts=["svc:payouts-service"], cause_service=None, cause_deploy=None, path=None,
                                     contact="per:sofia-alvarez")],
                     false_leads=[], look_first=["svc:config-service", "svc:config-db"], never_page=[])),
    dict(id="k-hubsat", tenant="kestrel_pay", shape="noisy neighbour saturates a shared hub",
         why="reconciliation-job is not called by webhook-dispatcher, but both call kafka-events (1 hop each); the alert "
             "itself names kafka-events, which corroborates the shared-hub explanation.",
         fixture=dict(quiet=True, deploys=[
             ("reconciliation-job", "1.8.0", 20, "tomasz-kowalski", "Replay the full day of bank events into kafka-events on every run", None)]),
         alerts=[{"service_id": "svc:webhook-dispatcher", "symptom": "webhook delivery lag 14 min; kafka-events consumer lag growing"}],
         expect=dict(incidents=[dict(alerts=["svc:webhook-dispatcher"], cause_service="svc:reconciliation-job",
                                     cause_deploy="dep:reconciliation-job-v1.8.0",
                                     path=["svc:webhook-dispatcher", "svc:kafka-events", "svc:reconciliation-job"],
                                     contact="per:tomasz-kowalski")],
                     false_leads=[], look_first=None, never_page=[])),
    dict(id="k-learned", tenant="kestrel_pay", shape="cause reachable only through a learned edge",
         why="The catalog says reconciliation-job calls ledger-service, bank-connector and kafka-events. An earlier session "
             "learned it also calls fx-rates-service (Fact quoting a chat). fx-rates-service has no dependencies, so no "
             "shared-dependency check can reach it. feature-flags (newer) is a decoy.",
         fixture=dict(quiet=True, deploys=[
             ("fx-rates-service", "2.3.0", 30, "sofia-alvarez", "Fetch rates from the new provider endpoint with a 10s timeout", None),
             ("feature-flags", "1.13.0", 8, "elena-petrova", "Evaluate percentage rollouts per merchant", None)],
             learned=[("reconciliation-job", "fx-rates-service", "recon-calls-fx",
                       "reconciliation-job calls fx-rates-service for every statement line; the catalog does not list it.",
                       "chat:eval-recon-fx", _RECON_FX)],
             nodes=[{"label": "ChatThread", "id": "chat:eval-recon-fx", "channel": "#payments-core",
                     "title": "Why is the recon run slow on FX days?", "ts_days": 40,
                     "text": "[recon] Tomasz Kowalski: " + _RECON_FX}],
             edges=[("per:tomasz-kowalski", "AUTHORED", "chat:eval-recon-fx", {}),
                    ("chat:eval-recon-fx", "MENTIONS", "svc:reconciliation-job", {}),
                    ("chat:eval-recon-fx", "MENTIONS", "svc:fx-rates-service", {})]),
         alerts=[{"service_id": "svc:reconciliation-job", "symptom": "nightly reconciliation run 4x slower than usual, statement lines timing out"}],
         expect=dict(incidents=[dict(alerts=["svc:reconciliation-job"], cause_service="svc:fx-rates-service",
                                     cause_deploy="dep:fx-rates-service-v2.3.0",
                                     path=["svc:reconciliation-job", "svc:fx-rates-service"], contact="per:sofia-alvarez")],
                     false_leads=["dep:feature-flags-v1.13.0"], look_first=None, never_page=[])),
    dict(id="k-departed", tenant="kestrel_pay", shape="departed owner, no active successor",
         why="reporting-service's maintainer Carlos Mendes left and (in this twin) nobody active has worked on it. The "
             "deploy was automated (no deployer). Page no one who left; escalate to the owning team.",
         fixture=dict(quiet=True, drop_edges=[("per:ben-walker", "WORKED_ON", "svc:reporting-service")], deploys=[
             ("reporting-service", "1.4.0", 18, None, "Automated dependency bump: PDF renderer 3.9 -> 4.0", None)]),
         alerts=[{"service_id": "svc:merchant-dashboard", "symptom": "reports tab 5xx 30% for 15 minutes"}],
         expect=dict(incidents=[dict(alerts=["svc:merchant-dashboard"], cause_service="svc:reporting-service",
                                     cause_deploy="dep:reporting-service-v1.4.0",
                                     path=["svc:merchant-dashboard", "svc:reporting-service"], contact="team:merchant-exp")],
                     false_leads=[], look_first=None, never_page=["per:carlos-mendes"])),
    dict(id="k-hero-s2", tenant="kestrel_pay", shape="hero Session 2 (memory): neighbour found through a learned edge",
         why="Session 1 learned risk-rules -> config-service. payouts-service calls config-service, so risk-rules v2.8.1 "
             "(5 min ago) is a noisy neighbour, but only through that learned edge.",
         fixture=dict(quiet=True, deploys=[
             ("risk-rules", "2.8.1", 5, "leo-park", "RISK-412 follow-up: re-enable 5s TTL for EU ruleset", "RISK-412")],
             learned=[("risk-rules", "config-service", "risk-rules-polls-config",
                       "risk-rules calls config-service at request time; the service catalog does not list this dependency.",
                       "chat:risk-eng-config-load", _RISK_POLL)]),
         alerts=[{"service_id": "svc:payouts-service", "symptom": "payout batch API 5xx 9% and p99 3.2s for the last 10 minutes"}],
         expect=dict(incidents=[dict(alerts=["svc:payouts-service"], cause_service="svc:risk-rules",
                                     cause_deploy="dep:risk-rules-v2.8.1",
                                     path=["svc:payouts-service", "svc:config-service", "svc:risk-rules"], contact="per:priya-nair")],
                     false_leads=[], look_first=None, never_page=["per:arjun-mehta"])),
    dict(id="k-hero-s2-ablation", tenant="kestrel_pay", shape="ablation: hero Session 2 without the learned edge",
         why="Same as k-hero-s2 minus the learned edge. Nothing payouts-service depends on changed, and nothing it shares a "
             "dependency with changed (in the catalog). The honest answer is 'cause not found'.",
         fixture=dict(quiet=True, deploys=[
             ("risk-rules", "2.8.1", 5, "leo-park", "RISK-412 follow-up: re-enable 5s TTL for EU ruleset", "RISK-412")]),
         alerts=[{"service_id": "svc:payouts-service", "symptom": "payout batch API 5xx 9% and p99 3.2s for the last 10 minutes"}],
         expect=dict(incidents=[dict(alerts=["svc:payouts-service"], cause_service=None, cause_deploy=None, path=None,
                                     contact="per:sofia-alvarez")],
                     false_leads=["dep:risk-rules-v2.8.1"], look_first=["svc:config-service", "svc:config-db"], never_page=[])),
    # ───────────── Northwind Health ─────────────
    dict(id="n-chokepoint", tenant="northwind_health", shape="two alerts: one change on the service both call explains both",
         why="appointments and lab-results both call notifications (betweenness #1). notifications changed 22 min ago. "
             "records-db changed more recently but only lab-results calls it: one change explaining both alerts beats "
             "two separate explanations.",
         fixture=dict(quiet=True, deploys=[
             ("notifications", "3.3.0", 22, "sam-reyes", "Send SMS synchronously inside the request (no queue)", None),
             ("records-db", "15.2.0", 6, "hana-sato", "PostgreSQL minor upgrade 15.1 -> 15.2", None)]),
         alerts=[{"service_id": "svc:appointments", "symptom": "booking API p99 4s, reminder requests timing out"},
                 {"service_id": "svc:lab-results", "symptom": "result publishing p99 5s, alert requests timing out"}],
         expect=dict(incidents=[dict(alerts=["svc:appointments", "svc:lab-results"], cause_service="svc:notifications",
                                     cause_deploy="dep:notifications-v3.3.0",
                                     path=["svc:appointments", "svc:notifications"], contact="per:maya-okoro")],
                     false_leads=["dep:records-db-v15.2.0"], look_first=None, never_page=["per:owen-bryce"])),
    dict(id="n-two", tenant="northwind_health", shape="two independent incidents at once",
         why="appointments -> notifications and identity -> audit-trail share no service, so they are two incidents with "
             "two causes and two pages.",
         fixture=dict(quiet=True, deploys=[
             ("notifications", "3.3.0", 25, "sam-reyes", "Send SMS synchronously inside the request (no queue)", None),
             ("audit-trail", "2.5.0", 12, "maya-okoro", "fsync every audit write before acknowledging", None)]),
         alerts=[{"service_id": "svc:appointments", "symptom": "booking API p99 4s, reminder requests timing out"},
                 {"service_id": "svc:identity", "symptom": "sign-in p99 3s, session writes slow"}],
         expect=dict(incidents=[dict(alerts=["svc:appointments"], cause_service="svc:notifications",
                                     cause_deploy="dep:notifications-v3.3.0", path=["svc:appointments", "svc:notifications"],
                                     contact="per:maya-okoro"),
                                dict(alerts=["svc:identity"], cause_service="svc:audit-trail",
                                     cause_deploy="dep:audit-trail-v2.5.0", path=["svc:identity", "svc:audit-trail"],
                                     contact="per:maya-okoro")],
                     false_leads=[], look_first=None, never_page=["per:owen-bryce"])),
    dict(id="n-falselead", tenant="northwind_health", shape="false lead: a neighbour and an unrelated fresher deploy",
         why="lab-results calls records-db (changed 40 min ago). identity (10 min) only shares audit-trail with lab-results; "
             "scheduler-db (4 min) is unrelated (appointments' database). The page goes to Maya Okoro, not records-db's "
             "maintainer Hana Sato: Maya fixed a past records-db incident (25 points) and Hana has 20 commits.",
         fixture=dict(quiet=True, deploys=[
             ("records-db", "15.2.0", 40, "hana-sato", "Rebuild the visit table without the old visit_id index", None),
             ("identity", "5.4.0", 10, "hana-sato", "Longer session refresh window", None),
             ("scheduler-db", "14.9.0", 4, "tariq-hassan", "Vacuum settings tuned for the booking table", None)]),
         alerts=[{"service_id": "svc:lab-results", "symptom": "result publishing p99 6s; results page timing out"}],
         expect=dict(incidents=[dict(alerts=["svc:lab-results"], cause_service="svc:records-db",
                                     cause_deploy="dep:records-db-v15.2.0", path=["svc:lab-results", "svc:records-db"],
                                     contact="per:maya-okoro")],
                     false_leads=["dep:identity-v5.4.0", "dep:scheduler-db-v14.9.0"], look_first=None, never_page=[])),
    dict(id="n-departed", tenant="northwind_health", shape="departed owner two hops down, escalate to the team",
         why="appointments -> notifications -> sms-gateway. sms-gateway's maintainer Owen Bryce left and (in this twin) no "
             "active person has worked on it; the deploy was automated. Escalate to Clinical Platform.",
         fixture=dict(quiet=True, drop_edges=[("per:maya-okoro", "WORKED_ON", "svc:sms-gateway")], deploys=[
             ("sms-gateway", "1.8.0", 15, None, "Automated provider SDK upgrade 2.x -> 3.0", None)]),
         alerts=[{"service_id": "svc:appointments", "symptom": "appointment reminders failing; SMS send errors 40%"}],
         expect=dict(incidents=[dict(alerts=["svc:appointments"], cause_service="svc:sms-gateway",
                                     cause_deploy="dep:sms-gateway-v1.8.0",
                                     path=["svc:appointments", "svc:notifications", "svc:sms-gateway"],
                                     contact="team:clinical-platform")],
                     false_leads=[], look_first=None, never_page=["per:owen-bryce"])),
]
BY_ID = {s["id"]: s for s in SCENARIOS}


def fixture(sc):
    """-> transform(nodes, edges, now) for seed.load.load: applies the scenario's fixture to the seed lists."""
    fx = sc.get("fixture", {})

    def transform(nodes, edges, now):
        if fx.get("quiet"):
            for n in nodes:
                if n["label"] == "Deploy" and n["ts"] > now - QUIET_H * 3600:
                    n["ts"] -= QUIET_SHIFT_D * 86400
        drop = {tuple(e) for e in fx.get("drop_edges", [])}
        missing = drop - {(a, t, b) for a, t, b, _ in edges}
        if missing:
            raise ValueError(f"{sc['id']}: drop_edges not in the seed: {sorted(missing)}")
        edges[:] = [e for e in edges if (e[0], e[1], e[2]) not in drop]
        for n in fx.get("nodes", []):
            n = dict(n)
            if "ts_days" in n:
                n["ts"] = now - n.pop("ts_days") * 86400
            nodes.append(n)
        edges.extend(fx.get("edges", []))
        for svc, ver, mins, person, summary, ticket in fx.get("deploys", []):
            did = f"dep:{svc}-v{ver}"
            nodes.append({"label": "Deploy", "id": did, "version": ver, "ts": now - mins * 60, "summary": summary})
            edges.append((did, "CHANGED", f"svc:{svc}", {}))
            if person:
                edges.append((f"per:{person}", "DEPLOYED", did, {}))
            if ticket:
                edges.append((did, "FOR_TICKET", f"tkt:{ticket}", {}))
        for a, b, slug, statement, src, excerpt in fx.get("learned", []):
            fid, at = f"fact:{slug}", now - 3 * 86400
            nodes.append({"label": "Fact", "id": fid, "statement": statement, "confidence": 0.8, "origin": "agent",
                          "created_at": at})
            edges.append((fid, "ABOUT", f"svc:{a}", {"origin": "agent", "created_at": at}))
            edges.append((fid, "ABOUT", f"svc:{b}", {"origin": "agent", "created_at": at}))
            edges.append((fid, "SOURCED_FROM", src, {"excerpt": excerpt, "origin": "agent", "created_at": at}))
            edges.append((f"svc:{a}", "DEPENDS_ON", f"svc:{b}",
                          {"kind": "sync", "source": "learned", "learned_at": at, "learned_from": fid,
                           "origin": "agent", "created_at": at}))
    return transform
