"""HELD-OUT eval scenarios: written by a separate agent that never saw the planner (backend/agents/ff_policy.py), kept
outside the repo with only its sha256 recorded (docs/progress.md, 08A), and run ONCE against the finished Part A planner:
6/6 for the full and no-algorithms profiles on that first run. Caveat: the author's brief listed the shapes to cover,
including "a noisy neighbour where the alert text names the shared dependency", which is one of the planner's rules.
Same format as seed/eval_scenarios.py. Now part of every eval run (set "holdout").
sha256 of the file as written by its author: 57264681bd26cedd7fb4f0b7a8ec52a5adb48adc1db9d34016be2ddb666dbc73
"""
"""Held-out eval scenarios (same format as seed/eval_scenarios.py). Not used for development."""

_SETTLE = ("reporting-service pulls the card settlement report from card-processor-adapter for every statements export, "
           "it's not in the catalog, so if the adapter is slow the export just hangs.")

SCENARIOS = [
    dict(id="h-k-ledger3", tenant="kestrel_pay", shape="bad deploy 3 hops downstream plus a fresher off-path deploy",
         why="web-checkout -> api-gateway -> payments-api -> ledger-service. merchant-onboarding changed more recently "
             "but is not on web-checkout's dependency path.",
         fixture=dict(quiet=True, deploys=[
             ("ledger-service", "4.2.0", 38, "marcus-webb", "Write double-entry rows in one serialisable transaction per payment", None),
             ("merchant-onboarding", "3.7.0", 6, "kenji-watanabe", "New document upload step for business verification", None)]),
         alerts=[{"service_id": "svc:web-checkout", "symptom": "checkout p99 4.1s and 5xx 5% for the last 15 minutes"}],
         expect=dict(incidents=[dict(alerts=["svc:web-checkout"], cause_service="svc:ledger-service",
                                     cause_deploy="dep:ledger-service-v4.2.0",
                                     path=["svc:web-checkout", "svc:api-gateway", "svc:payments-api", "svc:ledger-service"],
                                     contact="per:priya-nair")],
                     false_leads=["dep:merchant-onboarding-v3.7.0"], look_first=None, never_page=[])),
    dict(id="h-k-flagsneighbour", tenant="kestrel_pay", shape="noisy neighbour through a shared dependency",
         why="auth-service and feature-flags both call config-service; feature-flags is not downstream of auth-service.",
         fixture=dict(quiet=True, deploys=[
             ("feature-flags", "1.14.0", 22, "elena-petrova", "Re-fetch the full flag set from config-service on every evaluation", None)]),
         alerts=[{"service_id": "svc:auth-service",
                  "symptom": "token validation p99 2.8s and login 5xx 4%; config-service latency high"}],
         expect=dict(incidents=[dict(alerts=["svc:auth-service"], cause_service="svc:feature-flags",
                                     cause_deploy="dep:feature-flags-v1.14.0",
                                     path=["svc:auth-service", "svc:config-service", "svc:feature-flags"],
                                     contact="per:elena-petrova")],
                     false_leads=[], look_first=None, never_page=[])),
    dict(id="h-n-nochange", tenant="northwind_health", shape="no recent change: load spike",
         why="Nothing deployed in the window; the honest answer is 'no change found' plus the top PageRank hub below "
             "patient-portal.",
         fixture=dict(quiet=True),
         alerts=[{"service_id": "svc:patient-portal",
                  "symptom": "portal page loads p99 3.8s with sessions 2.5x normal after the flu-clinic reminder blast"}],
         expect=dict(incidents=[dict(alerts=["svc:patient-portal"], cause_service=None, cause_deploy=None, path=None,
                                     contact="per:ines-moreau")],
                     false_leads=[], look_first=["svc:sms-gateway"], never_page=[])),
    dict(id="h-n-schedulerdb", tenant="northwind_health", shape="two alerts, one common downstream cause, fresher partial false lead",
         why="appointments and patient-portal both reach scheduler-db. identity changed more recently but only "
             "patient-portal depends on it, so it explains one alert, not both.",
         fixture=dict(quiet=True, deploys=[
             ("scheduler-db", "14.10.0", 28, "tariq-hassan", "Drop the slot_start index during the booking table rewrite", None),
             ("identity", "5.5.0", 9, "victor-lund", "Rotate session signing keys on a shorter schedule", None)]),
         alerts=[{"service_id": "svc:appointments", "symptom": "booking API p99 6s; slot search queries timing out"},
                 {"service_id": "svc:patient-portal", "symptom": "book-an-appointment page 504s 12% for 20 minutes"}],
         expect=dict(incidents=[dict(alerts=["svc:appointments", "svc:patient-portal"], cause_service="svc:scheduler-db",
                                     cause_deploy="dep:scheduler-db-v14.10.0",
                                     path=["svc:appointments", "svc:scheduler-db"], contact="per:tariq-hassan")],
                     false_leads=["dep:identity-v5.5.0"], look_first=None, never_page=[])),
    dict(id="h-n-notifyorphan", tenant="northwind_health", shape="departed maintainer, no active person on the culprit",
         why="notifications' maintainer Owen Bryce left and (in this twin) no active person has worked on it; the "
             "deploy was automated. Escalate to the owning team.",
         fixture=dict(quiet=True, drop_edges=[("per:maya-okoro", "WORKED_ON", "svc:notifications"),
                                              ("per:sam-reyes", "WORKED_ON", "svc:notifications")], deploys=[
             ("notifications", "3.4.0", 17, None, "Automated dependency bump: HTTP client 4.x -> 5.0", None)]),
         alerts=[{"service_id": "svc:lab-results",
                  "symptom": "critical-result clinician alerts delayed 15 min; result publishing 5xx 8%"}],
         expect=dict(incidents=[dict(alerts=["svc:lab-results"], cause_service="svc:notifications",
                                     cause_deploy="dep:notifications-v3.4.0",
                                     path=["svc:lab-results", "svc:notifications"], contact="team:clinical-platform")],
                     false_leads=[], look_first=None, never_page=["per:owen-bryce"])),
    dict(id="h-k-learnedsettle", tenant="kestrel_pay", shape="cause reachable only through a learned edge",
         why="The catalog says reporting-service calls only ledger-service. An earlier session learned it also calls "
             "card-processor-adapter (Fact quoting a chat). notifications-service (newer) is a decoy.",
         fixture=dict(quiet=True, deploys=[
             ("card-processor-adapter", "2.9.0", 33, "marcus-webb", "Paginate settlement report downloads 50 rows per page", None),
             ("notifications-service", "2.4.0", 7, "fatima-zahra", "Batch merchant notification digests hourly", None)],
             learned=[("reporting-service", "card-processor-adapter", "reporting-calls-cpa",
                       "reporting-service calls card-processor-adapter for settlement reports; the catalog does not list it.",
                       "chat:eval-reporting-settlement", _SETTLE)],
             nodes=[{"label": "ChatThread", "id": "chat:eval-reporting-settlement", "channel": "#merchant-exp",
                     "title": "Statements export hanging again?", "ts_days": 55,
                     "text": "[reports] Ben Walker: " + _SETTLE}],
             edges=[("per:ben-walker", "AUTHORED", "chat:eval-reporting-settlement", {}),
                    ("chat:eval-reporting-settlement", "MENTIONS", "svc:reporting-service", {}),
                    ("chat:eval-reporting-settlement", "MENTIONS", "svc:card-processor-adapter", {})]),
         alerts=[{"service_id": "svc:merchant-dashboard", "symptom": "statements export 504s 25%; reports tab p99 9s for 20 minutes"}],
         expect=dict(incidents=[dict(alerts=["svc:merchant-dashboard"], cause_service="svc:card-processor-adapter",
                                     cause_deploy="dep:card-processor-adapter-v2.9.0",
                                     path=["svc:merchant-dashboard", "svc:reporting-service", "svc:card-processor-adapter"],
                                     contact="per:sofia-alvarez")],
                     false_leads=["dep:notifications-service-v2.4.0"], look_first=None, never_page=[])),
]
