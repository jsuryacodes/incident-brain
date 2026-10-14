"""Root causes, past incidents (episodic memory), resolutions, runbooks. No SIMILAR_TO edges: agents write those."""
from seed.timeutil import ago

from .knowledge import PM_RES

NODES, EDGES = [], []

ROOT_CAUSES = {
    "cache-ttl-thundering-herd": ("Cache TTL too low → thundering herd on a shared config store",
                                  "A client cache expires too often or is disabled, so many instances refetch from a shared store at once and overload it."),
    "connection-pool-exhaustion": ("Database connection pool exhaustion",
                                   "More concurrent work than the connection pool allows, so requests queue or fail."),
    "expired-tls-certificate": ("Expired TLS certificate",
                                "A certificate expired without renewal, and every TLS handshake to the peer fails."),
    "bad-config-push": ("Bad configuration push",
                        "An invalid or wrong configuration was rolled out to production without validation or canary."),
    "retry-storm": ("Retry storm",
                    "Uncapped, unjittered retries amplify load on a recovering dependency and keep it down."),
}

# slug: dict(...)   times are days before NOW
INCIDENTS = {
    "2025-031": dict(
        title="fraud-scoring timeouts during checkout peak", sev=2, days=455, hours_to_resolve=2,
        symptom="payments-api 5xx; fraud-scoring calls timing out at 800ms; config-service CPU at 98%",
        summary="risk-rules v2.3.0 lowered RULES_CACHE_TTL to 10s. At checkout peak every risk-rules pod refetched rulesets, "
                "saturating config-service and timing out fraud-scoring. Rolled back the TTL to 300s and added cache warm-up.",
        affected=["fraud-scoring", "payments-api", "config-service"], cause="dep:risk-rules-v2.3.0",
        rc="cache-ttl-thundering-herd", people=["arjun-mehta", "priya-nair"],
        res_summary="Rolled back TTL to 300s and added cache warm-up",
        res_steps="1. Roll back RULES_CACHE_TTL to 300s.\n2. Restart risk-rules pods gradually.\n3. Add cache warm-up on pod start.\n4. Watch config-service CPU until it is below 40%."),
    "2026-012": dict(
        title="merchant-onboarding config reads timing out", sev=3, days=150, hours_to_resolve=1,
        symptom="merchant signups slow or failing; config-service latency elevated",
        summary="merchant-onboarding v2.11.0 disabled its local config cache, so every request hit config-service and "
                "timed out under signup load. Re-enabled the cache with a jittered TTL.",
        affected=["merchant-onboarding", "config-service"], cause="dep:merchant-onboarding-v2.11.0",
        rc="cache-ttl-thundering-herd", people=["priya-nair"],
        res_summary="Re-enabled local config cache with jittered TTL",
        res_steps="1. Redeploy merchant-onboarding with the local config cache enabled.\n2. Add +/-20% jitter to the cache TTL.\n3. Confirm config-service latency returns to normal."),
    "2025-044": dict(
        title="ledger-service connection pool exhausted during payout run", sev=2, days=395, hours_to_resolve=3,
        symptom="payout run stalled; payment captures failing with pool timeout errors",
        summary="ledger-service v3.4.0 added a parallel payout journal writer that opened more connections than the "
                "ledger-db pool allowed, starving payment captures. Raised the pool ceiling and capped writer concurrency.",
        affected=["ledger-service", "payouts-service", "payments-api"], cause="dep:ledger-service-v3.4.0",
        rc="connection-pool-exhaustion", people=["marcus-webb"],
        res_summary="Raised pool ceiling and capped payout writer concurrency",
        res_steps="1. Reduce payout writer concurrency to 4.\n2. Raise the ledger-db connection pool limit.\n3. Re-run the stalled payout batch."),
    "2025-067": dict(
        title="card-processor-adapter TLS handshake failures", sev=1, days=340, hours_to_resolve=1,
        symptom="all card authorisations failing; TLS handshake errors in card-processor-adapter",
        summary="The acquirer client certificate expired at midnight UTC. Every TLS handshake from card-processor-adapter "
                "failed until the renewed certificate was installed.",
        affected=["card-processor-adapter", "payments-api"], cause="svc:card-processor-adapter",
        rc="expired-tls-certificate", people=["sofia-alvarez", "marcus-webb"],
        res_summary="Installed renewed acquirer certificate and added expiry alerting",
        res_steps="1. Request the renewed certificate from the acquirer.\n2. Install it and restart card-processor-adapter.\n3. Add an alert 30 days before certificate expiry."),
    "2025-089": dict(
        title="api-gateway routing misconfiguration after config push", sev=2, days=295, hours_to_resolve=1,
        symptom="EU traffic returning 404 on web-checkout and merchant dashboard",
        summary="api-gateway v8.2.0 shipped a routing table pointing EU traffic at a service name that did not exist. "
                "Reverted the routing table and re-applied it through a canary step.",
        affected=["api-gateway", "web-checkout", "merchant-dashboard"], cause="dep:api-gateway-v8.2.0",
        rc="bad-config-push", people=["elena-petrova", "nikhil-rao"],
        res_summary="Reverted routing table and re-applied through canary",
        res_steps="1. Revert the routing table to the previous version.\n2. Validate the new table against the service registry.\n3. Re-apply to a canary slice, then to all traffic."),
    "2026-031": dict(
        title="webhook-dispatcher retry storm after merchant outage", sev=3, days=80, hours_to_resolve=2,
        symptom="merchant endpoint repeatedly overloaded; kafka-events consumer lag growing",
        summary="After a merchant endpoint recovered, webhook-dispatcher retried every queued event at once and took it "
                "down again. Paused the retry queue and redelivered with capped attempts and jitter.",
        affected=["webhook-dispatcher", "kafka-events"], cause="svc:webhook-dispatcher",
        rc="retry-storm", people=["ben-walker"],
        res_summary="Paused retry queue and redelivered with capped attempts and jitter",
        res_steps="1. Pause the webhook retry queue.\n2. Deploy capped retry attempts with jittered backoff.\n3. Resume and redeliver gradually."),
}

for slug, (name, desc) in ROOT_CAUSES.items():
    NODES.append({"label": "RootCause", "id": f"rc:{slug}", "name": name, "description": desc})

for slug, i in INCIDENTS.items():
    iid, rid = f"inc:{slug}", f"res:{slug}"
    started = ago(days=i["days"])
    NODES.append({"label": "Incident", "id": iid, "key": f"INC-{slug}", "title": i["title"], "severity": i["sev"],
                  "status": "resolved", "symptom": i["symptom"], "summary": i["summary"],
                  "started_at": started, "resolved_at": started + i["hours_to_resolve"] * 3600})
    NODES.append({"label": "Resolution", "id": rid, "summary": i["res_summary"], "steps": i["res_steps"]})
    for s in i["affected"]:
        EDGES.append((iid, "AFFECTED", f"svc:{s}", {}))
    EDGES.append((iid, "CAUSED_BY", i["cause"], {}))
    EDGES.append((iid, "HAS_ROOT_CAUSE", f"rc:{i['rc']}", {}))
    EDGES.append((iid, "RESOLVED_BY", rid, {}))
    for p in i["people"]:
        EDGES.append((rid, "PERFORMED_BY", f"per:{p}", {}))
    EDGES.append((rid, "SOURCED_FROM", f"tkt:PM-{slug}", {"excerpt": PM_RES[slug]}))

# ───────────────────────────── runbooks (v1; the stale fraud-scoring one is the planted story) ─────────────────────────────
RUNBOOKS = [
    ("fraud-scoring-latency", "Runbook: fraud-scoring latency", "arjun-mehta", 540, "fraud-scoring",
     "1. Open the fraud-scoring dashboard and check p99 latency and pod CPU.\n"
     "2. If CPU is above 70%, scale the deployment up by 50% and wait five minutes.\n"
     "3. Check the feature store database for slow queries and connection saturation.\n"
     "4. If latency is still high, restart the pods one at a time.\n"
     "5. If payments are being declined, ask payments-api on-call to enable the conservative fallback.",
     "doc:fraud-scoring-readme", "The service is CPU-bound and scales horizontally."),
    ("ledger-db-failover", "Runbook: ledger-db failover", "marcus-webb", 150, "ledger-db",
     "1. Confirm the primary is unhealthy from two independent monitors.\n"
     "2. Pause the payout batch in payouts-service.\n"
     "3. Promote the synchronous replica using the failover script.\n"
     "4. Point ledger-service at the new primary and verify journal writes succeed.\n"
     "5. Rebuild the old primary as a replica and resume payouts.",
     "doc:ledger-service-readme", "Failover is covered by the ledger-db failover runbook."),
    ("kafka-consumer-lag", "Runbook: kafka-events consumer lag", "nikhil-rao", 295, "kafka-events",
     "1. Identify which consumer group is lagging on the kafka-events dashboard.\n"
     "2. Check whether the consumer pods are healthy and not restarting.\n"
     "3. Scale the consumer group up to the partition count if CPU-bound.\n"
     "4. If a poison message is blocking a partition, move it to the dead-letter topic.\n"
     "5. Replays older than 7 days must be rebuilt from the ledger.",
     "chat:platform-kafka-retention", "replays older than that are rebuilt from the ledger, not from Kafka."),
]
for slug, title, author, days, svc, steps, src, excerpt in RUNBOOKS:
    rid = f"rb:{slug}"
    NODES.append({"label": "Runbook", "id": rid, "title": title, "steps": steps, "version": 1, "updated_at": ago(days=days)})
    EDGES.append((f"per:{author}", "AUTHORED", rid, {}))
    EDGES.append((rid, "DESCRIBES", f"svc:{svc}", {}))
    EDGES.append((rid, "SOURCED_FROM", src, {"excerpt": excerpt}))
