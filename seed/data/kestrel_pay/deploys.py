"""Deploys + DEPLOYED, CHANGED, FOR_TICKET.
Fixtures: risk-rules-v2.8.0 (40 min ago, the culprit), email-sender-v1.14.2 (60 min ago, the decoy).
Every other recent deploy is >= 6h old. A few old deploys exist as causes of seeded incidents."""
from seed.timeutil import ago

# (service, version, when, person, summary, ticket key or None)
DEPLOYS = [
    # --- fixtures ---
    ("risk-rules", "2.8.0", ago(minutes=40), "leo-park",
     "RISK-412: lower RULES_CACHE_TTL 300s -> 5s so rule edits apply faster", "RISK-412"),
    ("email-sender", "1.14.2", ago(minutes=60), "kenji-watanabe",
     "Bump transactional email client to 4.2.1; no behaviour change", None),
    # --- last 30 days (all >= 6h old) ---
    ("payments-api", "5.31.0", ago(hours=7), "sofia-alvarez", "Validate idempotency-key on the refund endpoint", "PAY-1604"),
    ("api-gateway", "8.14.0", ago(days=1, hours=6), "nikhil-rao", "Canary + schema validation for routing config pushes", "PLAT-902"),
    ("ledger-service", "3.12.0", ago(days=2), "priya-nair", "Batch journal writes to cut p99 latency", None),
    ("web-checkout", "12.4.0", ago(days=2, hours=5), "ben-walker", "Apple Pay button layout fix on small screens", None),
    ("payments-api", "5.30.2", ago(days=3), "priya-nair", "Fix panic in 3DS fallback when issuer returns empty ACS URL", "PAY-1520"),
    ("card-processor-adapter", "2.8.1", ago(days=4), "sofia-alvarez", "Update acquirer certificate bundle", None),
    ("payouts-service", "4.4.0", ago(days=5), "sofia-alvarez", "Raise payout batch size from 200 to 500", "PAY-1633"),
    ("merchant-dashboard", "7.9.0", ago(days=5, hours=3), "fatima-zahra", "New payouts tab with CSV export", None),
    ("bank-connector", "1.19.0", ago(days=6), "tomasz-kowalski", "Support ISO 20022 pain.001 v9 for partner bank", None),
    ("auth-service", "2.21.0", ago(days=7), "elena-petrova", "Rotate JWT signing keys automatically every 30 days", None),
    ("reconciliation-job", "1.7.2", ago(days=8), "tomasz-kowalski", "Tolerate duplicate lines in bank statements", None),
    ("web-checkout", "12.3.1", ago(days=8, hours=4), "fatima-zahra", "Fix 3DS iframe sizing on Safari", None),
    ("notifications-service", "3.1.2", ago(days=9), "fatima-zahra", "Throttle SMS retries per recipient", None),
    ("payments-api", "5.30.1", ago(days=9, hours=2), "marcus-webb", "Add structured logging for processor timeouts", None),
    ("fraud-scoring", "6.2.0", ago(days=10), "mei-lin-chen", "Add devices-per-card velocity feature", "RISK-401"),
    ("kyc-service", "3.5.0", ago(days=11), "mei-lin-chen", "Switch document OCR vendor", None),
    ("merchant-onboarding", "2.14.0", ago(days=12), "kenji-watanabe", "Run KYC checks asynchronously after account creation", "MX-701"),
    ("ledger-service", "3.11.4", ago(days=12, hours=8), "tomasz-kowalski", "Fix rounding in multi-currency journal entries", None),
    ("fx-rates-service", "2.2.0", ago(days=13), "sofia-alvarez", "Cache rates for 60s instead of 30s", None),
    ("webhook-dispatcher", "2.6.0", ago(days=14), "ben-walker", "Cap webhook retries and add jitter", "MX-655"),
    ("api-gateway", "8.13.2", ago(days=14, hours=9), "elena-petrova", "Tighten per-key rate limits for the sandbox", None),
    ("sanctions-screening", "1.9.1", ago(days=15), "ravi-shankar", "Run list refresh on weekends too", "RISK-377"),
    ("payments-api", "5.30.0", ago(days=16), "sofia-alvarez", "Expose payment method details on refund responses", None),
    ("config-service", "1.30.0", ago(days=17), "omar-haddad", "Add per-client request metrics", None),
    ("risk-rules", "2.7.3", ago(days=18), "leo-park", "Fix rule editor audit timestamps", None),
    ("audit-log", "1.5.0", ago(days=20), "omar-haddad", "Partition audit tables by month", None),
    ("card-processor-adapter", "2.8.0", ago(days=21), "marcus-webb", "Add retry budget per acquirer", None),
    ("feature-flags", "1.12.4", ago(days=22), "elena-petrova", "Fix stale flag cache after rollout changes", None),
    ("fraud-scoring", "6.1.5", ago(days=24), "leo-park", "Lower feature-store read timeout to 40 ms", None),
    ("kafka-events", "3.7.1", ago(days=26), "jonas-eriksson", "Upgrade brokers to 3.7.1", "PLAT-871"),
    ("reporting-service", "1.3.1", ago(days=27), "ben-walker", "Fix timezone in monthly report headers", None),
    # --- old deploys that caused seeded incidents ---
    ("risk-rules", "2.3.0", ago(days=455, hours=3), "arjun-mehta", "Lower RULES_CACHE_TTL to 10s", None),
    ("merchant-onboarding", "2.11.0", ago(days=150, hours=1), "kenji-watanabe",
     "Disable local config cache; read config on every request", None),
    ("ledger-service", "3.4.0", ago(days=395, hours=2), "tomasz-kowalski", "Add parallel payout journal writer", None),
    ("api-gateway", "8.2.0", ago(days=295, hours=1), "elena-petrova", "Routing table update for new EU region", None),
]

NODES, EDGES = [], []
for svc, ver, ts, person, summary, ticket in DEPLOYS:
    did = f"dep:{svc}-v{ver}"
    NODES.append({"label": "Deploy", "id": did, "version": ver, "ts": ts, "summary": summary})
    EDGES.append((f"per:{person}", "DEPLOYED", did, {}))
    EDGES.append((did, "CHANGED", f"svc:{svc}", {}))
    if ticket:
        EDGES.append((did, "FOR_TICKET", f"tkt:{ticket}", {}))
