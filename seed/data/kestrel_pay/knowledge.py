"""Docs, tickets, chat threads, decisions and their edges (AUTHORED, MENTIONS, DESCRIBES, ABOUT, SOURCED_FROM)."""
from seed.timeutil import ago, stamp

NODES, EDGES = [], []

# Exact quotes. The same constant feeds the source text AND the SOURCED_FROM excerpt, so they can never drift.
Q_TTL = ("Decision: RULES_CACHE_TTL stays at 300s minimum. Below ~30s config-service falls over at "
         "checkout peak — that's what bit us in INC-2025-031.")
Q_CARD = ("Decision: the card processor gets a 2.5s total budget per authorisation: 1.2s for the first attempt, "
          "at most one retry, never inside the 3DS challenge window.")
Q_KAFKA = "Decision: kafka-events keeps 7 days of retention; replays older than that are rebuilt from the ledger, not from Kafka."
Q_LEDGER = ("Decision: ledger idempotency keys are honoured for 24 hours; a repeated key after that window "
            "is treated as a new request.")
Q_WEBHOOK = ("Decision: webhook deliveries retry with exponential backoff, at most 6 attempts over 24 hours, "
             "and 4xx responses (except 408 and 429) are never retried.")

# Postmortem resolution lines, reused as SOURCED_FROM excerpts by incidents.py.
PM_RES = {
    "2025-031": "Resolution: rolled back TTL to 300s and added cache warm-up on pod start.",
    "2026-012": "Resolution: re-enabled the local config cache with a jittered TTL.",
    "2025-044": "Resolution: raised the ledger connection pool ceiling and capped payout writer concurrency.",
    "2025-067": "Resolution: installed the renewed acquirer certificate and added a 30-day expiry alert.",
    "2025-089": "Resolution: reverted the routing table and re-applied it through the new canary step.",
    "2026-031": "Resolution: paused the retry queue, then redelivered with capped attempts and jitter.",
}


def _p(slug):
    return f"per:{slug}"


def _s(slug):
    return f"svc:{slug}"


def _refs(src, mentions):
    for m in mentions:
        EDGES.append((src, "MENTIONS", m if ":" in m else _s(m), {}))


def thread(slug, channel, title, days, author, lines, mentions):
    ts = ago(days=days)
    body = "\n".join(f"[{stamp(ts + m * 60)}] {who}: {msg}" for m, who, msg in lines)
    cid = f"chat:{slug}"
    NODES.append({"label": "ChatThread", "id": cid, "channel": channel, "title": title, "text": body, "ts": ts})
    EDGES.append((_p(author), "AUTHORED", cid, {}))
    _refs(cid, mentions)


def doc(slug, title, author, days, text, describes=(), mentions=()):
    did = f"doc:{slug}"
    NODES.append({"label": "Doc", "id": did, "title": title, "text": text.strip(),
                  "updated_at": ago(days=days), "flagged_stale": False})
    EDGES.append((_p(author), "AUTHORED", did, {}))
    for d in describes:
        EDGES.append((did, "DESCRIBES", _s(d), {}))
    _refs(did, mentions)


def ticket(key, title, kind, status, priority, author, days, text, about=(), mentions=()):
    tid = f"tkt:{key}"
    NODES.append({"label": "Ticket", "id": tid, "key": key, "title": title, "text": text.strip(), "kind": kind,
                  "status": status, "priority": priority, "created_at": ago(days=days)})
    EDGES.append((_p(author), "AUTHORED", tid, {}))
    for a in about:
        EDGES.append((tid, "ABOUT", a if ":" in a else _s(a), {}))
    _refs(tid, mentions)


def decision(slug, title, rationale, days, author, about, source, excerpt):
    did = f"dec:{slug}"
    NODES.append({"label": "Decision", "id": did, "title": title, "rationale": rationale, "decided_at": ago(days=days)})
    EDGES.append((_p(author), "AUTHORED", did, {}))
    EDGES.append((did, "ABOUT", _s(about), {}))
    EDGES.append((did, "SOURCED_FROM", source, {"excerpt": excerpt}))


# ───────────────────────────── chat threads ─────────────────────────────
thread("risk-eng-config-load", "#risk-eng", "How does risk-rules get its rules? (config load)", 430, "arjun-mehta", [
    (0, "Priya Nair", "Arjun, quick one while I go through the INC-2025-031 action items: where does risk-rules actually read rules from at request time?"),
    (3, "Arjun Mehta", "Not from its own DB on the hot path. rules-store-db is just the source of truth for the rule editor. On every cache miss risk-rules polls config-service's internal /v1/rulesets endpoint."),
    (4, "Arjun Mehta", "It's not in the service catalog because it started as a \"temporary\" hack two years ago and nobody ever went back to register it."),
    (6, "Priya Nair", "So if the rules cache is cold, every fraud-scoring call can fan out to config-service?"),
    (7, "Arjun Mehta", "Yes. Cold cache or tiny TTL, same thing: every payment turns into a rulesets fetch."),
    (9, "Priya Nair", "That explains why config-service CPU was pinned during the incident. 10s TTL times ~40 pods at peak..."),
    (10, "Arjun Mehta", "Exactly. Every pod refetched the full ruleset every few seconds, all at once."),
    (12, "Priya Nair", "Can we write a floor for that TTL down somewhere people will actually see it?"),
    (14, "Arjun Mehta", Q_TTL),
    (15, "Priya Nair", "Agreed. Please don't leave it only in Slack."),
    (16, "Arjun Mehta", "I'll put it in the risk-rules README next sprint."),
], ["svc:risk-rules", "svc:config-service", "svc:fraud-scoring", "per:priya-nair", "inc:2025-031"])

thread("incidents-2025-031-war-room", "#incidents", "INC-2025-031 war room: fraud-scoring timeouts", 455, "grace-liu", [
    (0, "Grace Liu", "Declaring INC-2025-031, sev 2. Checkout error rate is climbing, payments-api returning 5xx. Who is on?"),
    (2, "Marcus Webb", "payments-api is healthy, but every call to fraud-scoring is timing out at 800ms."),
    (5, "Arjun Mehta", "fraud-scoring itself looks fine. Latency is all inside risk-rules. I shipped v2.3.0 a few hours ago with a lower cache TTL."),
    (8, "Omar Haddad", "config-service CPU is at 98% and its request rate tripled in the last 10 minutes."),
    (11, "Priya Nair", "Correlates exactly with the risk-rules deploy. Can we roll the TTL back?"),
    (13, "Arjun Mehta", "Rolling TTL back to 300s now."),
    (31, "Omar Haddad", "config-service CPU down to 35%. Request rate back to normal."),
    (38, "Marcus Webb", "Checkout error rate is back under 0.5%."),
    (45, "Grace Liu", "Marking mitigated. Priya and Arjun, can you add a cache warm-up before we call it resolved?"),
    (118, "Priya Nair", "Warm-up shipped and verified in staging and prod. Resolving."),
], ["inc:2025-031", "svc:fraud-scoring", "svc:payments-api", "svc:config-service", "svc:risk-rules"])

thread("payments-card-timeouts", "#payments-core", "Card processor timeout budget", 380, "marcus-webb", [
    (0, "Marcus Webb", "We keep arguing about timeouts for the acquirer. Proposal: one number for the whole authorisation, not per-call."),
    (4, "Sofia Alvarez", "Today we do 3s then retry 3s, so customers can wait 6s plus 3DS. Too long."),
    (6, "Priya Nair", "Retries inside a 3DS challenge also risk double authorisations, ledger saw some of those."),
    (9, "Marcus Webb", Q_CARD),
    (11, "Sofia Alvarez", "p99 first-attempt latency is 900ms, so 1.2s leaves a little headroom. Fine by me."),
    (13, "Marcus Webb", "I'll implement it in card-processor-adapter this sprint."),
], ["svc:card-processor-adapter", "svc:payments-api", "per:sofia-alvarez", "per:priya-nair"])

thread("platform-kafka-retention", "#platform", "kafka-events retention and disk usage", 300, "nikhil-rao", [
    (0, "Nikhil Rao", "Broker disks are at 78%. We have 14 days of retention on payment events and almost nobody reads past day 2."),
    (3, "Jonas Eriksson", "Replays so far have all been within 48 hours. Anything older came from the ledger anyway."),
    (6, "Elena Petrova", "Audit-log consumers lag by minutes, not days. I'm fine with shorter retention."),
    (8, "Nikhil Rao", Q_KAFKA),
    (10, "Jonas Eriksson", "I'll roll the config change broker by broker tomorrow morning."),
    (12, "Nikhil Rao", "Thanks. I'll update the on-call guide too."),
], ["svc:kafka-events", "svc:audit-log", "per:jonas-eriksson"])

thread("risk-eng-sanctions-refresh", "#risk-eng", "Sanctions list not refreshed on weekends", 62, "ravi-shankar", [
    (0, "Ravi Shankar", "Found it: the sanctions list refresh cron is Mon-Fri only. Merchants onboarded Saturday were screened against Friday's list."),
    (4, "Mei Lin Chen", "Ouch. Any hits missed?"),
    (7, "Ravi Shankar", "No. I re-ran the screen for the last 3 weekends and everything is clean."),
    (9, "Dana Okafor", "Good catch. Please fix it and add an alert if the list is older than 26 hours."),
    (12, "Ravi Shankar", "Ticket is RISK-377. Fix is trivial, alert will take a bit longer."),
    (15, "Mei Lin Chen", "Thanks. Let me know when it is in and I will tell compliance."),
], ["svc:sanctions-screening", "per:mei-lin-chen", "per:dana-okafor"])

thread("payments-core-ledger-dupes", "#payments-core", "Duplicate ledger entries on client retries", 206, "priya-nair", [
    (0, "Priya Nair", "Reconciliation flagged 14 duplicate journal entries. All from clients retrying a timed-out charge with the same idempotency key."),
    (5, "Tomasz Kowalski", "The ledger dedupes on key, but only for 60s. Retries after a minute create a second entry."),
    (7, "Marcus Webb", "Stripe-style APIs usually keep keys for 24h. Cost is one extra index, cheap."),
    (10, "Priya Nair", "Proposal in PAY-1187. I'll write the decision there so it's findable."),
    (14, "Marcus Webb", "+1. Ship it with a backfill for existing keys."),
    (18, "Tomasz Kowalski", "I will add a reconciliation check that alerts on any new duplicates."),
], ["svc:ledger-service", "per:tomasz-kowalski", "per:marcus-webb"])

thread("merchant-exp-onboarding-cache", "#merchant-exp", "Onboarding config reads timing out", 151, "kenji-watanabe", [
    (0, "Kenji Watanabe", "Heads up: merchant-onboarding is timing out reading config. config-service is slow for everyone right now."),
    (3, "Priya Nair", "I'm looking. merchant-onboarding v2.11.0 disabled the local config cache, so every request now hits config-service."),
    (5, "Kenji Watanabe", "That was me, I wanted fresh config on every signup. I didn't think it would matter at this volume."),
    (8, "Priya Nair", "It matters: same thundering-herd pattern we saw last year with the rules cache. Let's re-enable the cache with jitter on the TTL."),
    (15, "Kenji Watanabe", "Deploying the fix now. I'll write the postmortem."),
    (40, "Priya Nair", "config-service latency is back to normal."),
], ["inc:2026-012", "svc:merchant-onboarding", "svc:config-service", "per:priya-nair"])

thread("oncall-handoff-week-41", "#oncall", "On-call handoff, week 41", 14, "jonas-eriksson", [
    (0, "Jonas Eriksson", "Handoff: quiet week. One page for a ledger-db replica disk alert, resolved by expanding the volume."),
    (3, "Omar Haddad", "Anything to watch?"),
    (5, "Jonas Eriksson", "The api-gateway canary dashboard is new, so alerts there may be noisy. Ignore anything under 2% for now."),
    (8, "Omar Haddad", "Got it. I'll watch the quarter-end payout spike on Friday."),
    (10, "Jonas Eriksson", "Runbooks for ledger-db failover and kafka consumer lag are both up to date."),
    (12, "Omar Haddad", "Great, thanks for the clean handoff."),
], ["svc:ledger-db", "svc:api-gateway", "per:omar-haddad"])

thread("eng-all-release-freeze", "#eng-all", "Quarter-end release freeze", 40, "grace-liu", [
    (0, "Grace Liu", "Reminder: quarter-end release freeze starts Thursday 18:00 UTC and lasts until Monday morning."),
    (2, "Camila Torres", "Merchant Experience has two small fixes in flight. Can they go out before Thursday?"),
    (4, "Grace Liu", "Yes, as long as they ship before the freeze starts. Emergency fixes need an approver from the on-call rota."),
    (7, "Nikhil Rao", "Platform will freeze config-service and api-gateway as well, no exceptions for 'tiny' changes."),
    (9, "Camila Torres", "Understood. We'll flag anything risky in the release channel."),
    (11, "Grace Liu", "Thanks all. I will pin the freeze calendar in this channel."),
], ["svc:api-gateway", "svc:config-service"])

thread("payouts-bank-cutoff", "#payments-core", "Bank cut-off times for same-day payouts", 33, "sofia-alvarez", [
    (0, "Sofia Alvarez", "Partner bank moved its same-day cut-off from 15:00 to 14:00 UTC. Payouts submitted after that roll to next day."),
    (3, "Tomasz Kowalski", "We schedule the main batch at 13:30 so we're fine, but retries after failures could slip."),
    (6, "Aiko Tanaka", "Merchants are very sensitive to this. Can we surface the cut-off in the dashboard?"),
    (9, "Sofia Alvarez", "Yes, I'll ask merchant-exp. In the meantime I'm moving the batch to 13:15."),
    (12, "Tomasz Kowalski", "I'll update bank-connector so retries stop after 13:55 and alert instead."),
    (15, "Aiko Tanaka", "Perfect. I will let support know about the new cut-off."),
], ["svc:payouts-service", "svc:bank-connector", "per:tomasz-kowalski"])

# ───────────────────────────── docs ─────────────────────────────
doc("risk-rules-readme", "risk-rules README", "arjun-mehta", 600, """
# risk-rules

risk-rules is the fraud rule engine. It evaluates analyst-authored rules (velocity limits, geo mismatches, device
reputation, BIN blocklists) against the feature vector that fraud-scoring sends for every payment, and returns a
list of rule verdicts in under 20 ms.

## Ownership
Owner and primary contact: Arjun Mehta (Risk & Fraud). Page the Risk & Fraud on-call if Arjun is unavailable.

## Dependencies
- rules-store-db (PostgreSQL): rule definitions and the rule audit history.

That is the only dependency. The service is stateless apart from an in-process rules cache, controlled by
RULES_CACHE_TTL, which is refreshed on a cache miss.

## Deploying
Merge to main, wait for CI, then promote through staging. Rule edits made in the editor are picked up by the
cache on its next refresh. There is no manual flush endpoint; restart the pods if you need an immediate refresh.

## Local development
Run `make dev` to start the service against a local Postgres seeded with sample rules.
""", describes=["risk-rules"], mentions=["per:arjun-mehta", "svc:rules-store-db"])

doc("fraud-scoring-readme", "fraud-scoring README", "arjun-mehta", 545, """
# fraud-scoring

fraud-scoring produces a risk score between 0 and 1 for every authorisation request from payments-api. It
combines features from the feature store, rule verdicts from risk-rules, and an ML model served in-process.

## Latency budget
The caller allows 150 ms. A typical request spends about 40 ms on feature lookups, 20 ms on rules, 30 ms on the
model, and the rest on serialisation. If the budget is exceeded, payments-api falls back to a conservative
decision and flags the payment for review.

## Scaling
The service is CPU-bound and scales horizontally. The autoscaler targets 55% CPU with a minimum of 12 pods.

## Dependencies
risk-rules for rule verdicts, kyc-service for merchant risk tier, sanctions-screening for list matches.

## Contacts
Owner: Arjun Mehta. Secondary: Mei Lin Chen.
""", describes=["fraud-scoring"], mentions=["per:arjun-mehta", "per:mei-lin-chen", "svc:risk-rules"])

doc("payments-core-onboarding", "Payments Core onboarding guide", "marcus-webb", 120, """
# Welcome to Payments Core

Payments Core owns the money path: payments-api, ledger-service, card-processor-adapter, bank-connector,
payouts-service, reconciliation-job, fx-rates-service and the ledger database.

## Your first week
1. Get access to the repos, the staging environment and the on-call rota (you shadow for two weeks first).
2. Read the architecture overview and the ledger-service README.
3. Pair with a teammate on a small ticket and ship it to production on day three.

## Rules we care about
- Money movements are always double-entry and always idempotent.
- Never retry a card authorisation inside a 3DS challenge.
- Every production change needs a ticket and a rollback plan.

## Who to ask
Marcus Webb for architecture, Priya Nair for the ledger and for anything that crosses into Risk & Fraud,
Aiko Tanaka for planning and process.
""", mentions=["svc:payments-api", "svc:ledger-service", "svc:payouts-service", "per:priya-nair", "per:marcus-webb"])

doc("architecture-overview", "Kestrel Pay architecture overview", "nikhil-rao", 200, """
# Architecture overview

Merchants reach us through web-checkout or the public API. Both enter via api-gateway, which authenticates
requests with auth-service and routes them to payments-api.

## Payment flow
payments-api asks fraud-scoring for a risk score, writes the payment to ledger-service, and calls
card-processor-adapter to authorise with the acquirer. Events are published to kafka-events for notifications,
webhooks and reporting.

## Shared platform services
config-service serves configuration to many backends. feature-flags evaluates rollouts. audit-log keeps an
append-only trail. kafka-events is the shared event bus.

## Risk and fraud
fraud-scoring calls risk-rules for rule verdicts; risk-rules keeps its rule definitions in rules-store-db.
kyc-service and sanctions-screening support merchant onboarding and screening.

The dependency graph in the service catalog is the source of truth for who calls whom.
""", mentions=["svc:api-gateway", "svc:payments-api", "svc:fraud-scoring", "svc:config-service", "svc:kafka-events"])

doc("oncall-guide", "On-call guide", "jonas-eriksson", 90, """
# On-call guide

## Rota
One primary and one secondary per week, handing over on Monday at 10:00 UTC in #oncall.

## When you are paged
1. Acknowledge within 5 minutes.
2. Open the service dashboard linked from the alert and check recent deploys first.
3. If customer impact is likely, declare an incident and follow the incident response process.
4. Mitigate before you root-cause. Rolling back is always allowed.

## Useful starting points
- api-gateway error rate and latency per route.
- payments-api authorisation success rate.
- kafka-events consumer lag.

## Escalation
If you cannot find the owner of a failing service, check the service catalog, then page the owning team's
on-call. Engineering managers are the last resort, not the first.
""", mentions=["svc:api-gateway", "svc:payments-api", "svc:kafka-events"])

doc("ledger-service-readme", "ledger-service README", "priya-nair", 150, """
# ledger-service

The ledger records every movement of money as balanced journal entries. Nothing else in the company is allowed
to write to ledger-db.

## API
- POST /v1/journals: create a journal. Requires an Idempotency-Key header.
- GET /v1/accounts/{id}/balance: current and pending balance.

## Idempotency
Keys are stored for 24 hours. A repeated key returns the original response.

## Dependencies
ledger-db (PostgreSQL), kafka-events for publishing journal events, audit-log for administrative actions.

## Operations
Failover is covered by the ledger-db failover runbook. Deploys happen outside the payout window (13:00-14:00 UTC).

## Contacts
Priya Nair (maintainer), Marcus Webb.
""", describes=["ledger-service"], mentions=["per:priya-nair", "svc:ledger-db"])

doc("webhook-dispatcher-guide", "Webhook delivery guide", "ben-walker", 240, f"""
# Webhook delivery

webhook-dispatcher consumes events from kafka-events and delivers them as signed HTTP POSTs to merchant
endpoints.

## Signatures
Each request carries an HMAC-SHA256 signature in the Kestrel-Signature header. Merchants verify it using their
endpoint secret.

## Retry policy
{Q_WEBHOOK}

## Ordering
Events for the same payment are delivered in order, but there is no ordering guarantee across payments.

## Disabling endpoints
An endpoint that fails continuously for 72 hours is disabled and the merchant is notified by email.

## Contacts
Ben Walker (maintainer), Kenji Watanabe.
""", describes=["webhook-dispatcher"], mentions=["svc:kafka-events", "per:ben-walker"])

doc("config-service-readme", "config-service README", "omar-haddad", 300, """
# config-service

config-service is the central place for runtime configuration: per-service settings, tenant overrides and
shared reference data. It is read-heavy and backed by config-db.

## Known clients
payments-api, payouts-service, merchant-onboarding, api-gateway, auth-service, bank-connector,
notifications-service, webhook-dispatcher and feature-flags.

## Capacity
Sized for roughly 3,000 requests per second. Clients should cache responses locally and respect the Cache-Control
header; a client that polls on every request can exhaust capacity.

## Operations
Rolling deploys, three replicas minimum. Config changes are versioned; roll back via the admin API.

## Contacts
Omar Haddad (maintainer), Nikhil Rao, Jonas Eriksson (database).
""", describes=["config-service"], mentions=["per:omar-haddad", "svc:config-db"])

doc("incident-response-process", "Incident response process", "grace-liu", 180, """
# Incident response process

## Severity
- Sev 1: customers cannot pay at all.
- Sev 2: significant degradation of payments or payouts.
- Sev 3: limited impact, workaround exists.
- Sev 4: minor.

## Roles
The first responder becomes incident commander (IC) until someone takes over explicitly. The IC owns
communication; a separate engineer owns the technical investigation.

## Steps
1. Open an incident channel and post a one-line summary.
2. Mitigate first. Roll back recent changes unless there is a reason not to.
3. Update the status page for sev 1 and 2.
4. Within five working days, write a postmortem: timeline, impact, root cause, resolution, follow-ups.

INC-2025-031 is a good example of the expected format.
""", mentions=["inc:2025-031"])

doc("payouts-service-readme", "payouts-service README", "sofia-alvarez", 110, """
# payouts-service

payouts-service batches settled funds and sends them to merchants through bank-connector.

## Schedule
The main batch runs daily at 13:15 UTC, ahead of the partner bank's 14:00 cut-off. Merchants can opt into weekly
or monthly payouts.

## Batch size
Up to 500 payouts per batch. Larger runs are split.

## Dependencies
ledger-service for balances and journals, bank-connector for bank rails, fx-rates-service for currency
conversion, config-service for payout schedules, kafka-events for events.

## Failure handling
A failed payout is retried up to three times before 13:55 UTC, then raised to the on-call.

## Contacts
Sofia Alvarez (maintainer), Tomasz Kowalski.
""", describes=["payouts-service"], mentions=["per:sofia-alvarez", "svc:bank-connector"])

doc("release-process", "Release process", "elena-petrova", 260, """
# Release process

## Flow
Every service ships through the same pipeline: pull request, CI, staging, production. Production deploys are
rolling and automatic once the staging checks pass.

## Rules
- No production deploys on Fridays after 15:00 UTC, or during a freeze.
- Tier 1 services need a second reviewer from outside the owning team for risky changes.
- Every deploy references a ticket so that the change history is searchable.

## Rollbacks
The pipeline keeps the last three versions of every service. A rollback is a one-click action and does not need
approval.

## Configuration changes
Configuration pushed through config-service is a release too, and follows the same ticket and rollback rules.
""", mentions=["svc:config-service"])

doc("merchant-onboarding-flow", "Merchant onboarding flow", "kenji-watanabe", 75, """
# Merchant onboarding

## Steps
1. The merchant signs up and receives a test-mode account immediately.
2. merchant-onboarding triggers KYC through kyc-service. Checks run asynchronously and typically finish within
   ten minutes.
3. Sanctions screening runs as part of the KYC pipeline.
4. When all checks pass, live mode is enabled and notifications-service emails the merchant.

## Configuration
Onboarding reads its settings from config-service. The local config cache must stay enabled; disabling it caused
INC-2026-012.

## Failure modes
If KYC does not complete within 24 hours, the case is routed to the compliance team.

## Contacts
Kenji Watanabe (maintainer), Fatima Zahra.
""", describes=["merchant-onboarding"], mentions=["svc:kyc-service", "svc:config-service", "inc:2026-012"])

# ───────────────────────────── tickets ─────────────────────────────
ticket("RISK-412", "Rule edits take up to 5 minutes to apply — reduce rules cache TTL", "task", "done", "P2",
       "leo-park", 3, """
Analysts report that editing a fraud rule in the console takes up to 5 minutes to take effect in production,
because risk-rules caches the rule set for RULES_CACHE_TTL (currently 300s).

Proposal: reduce RULES_CACHE_TTL from 300s to 5s so edits apply almost immediately.

Acceptance criteria: an edited rule is visible to fraud-scoring within 10 seconds.
Shipped in risk-rules v2.8.0.
""", about=["risk-rules"], mentions=["risk-rules"])

ticket("PAY-1187", "Duplicate ledger entries when clients retry after 60 seconds", "bug", "done", "P1",
       "priya-nair", 205, f"""
Reconciliation found 14 duplicate journal entries. In every case a client retried a timed-out charge with the same
idempotency key more than 60 seconds later, after the dedupe window had expired.

Fix: keep idempotency keys in ledger-service for longer and backfill existing keys.

{Q_LEDGER}
""", about=["ledger-service"], mentions=["ledger-service"])

ticket("PAY-1520", "3DS fallback panics when issuer returns empty ACS URL", "bug", "done", "P2",
       "priya-nair", 5, """
payments-api panics in the 3DS fallback path when the issuer returns an empty ACS URL. The request fails with a 500
and the customer sees a generic error. Add a nil check and return a clean decline with reason code 3DS_UNAVAILABLE.
""", about=["payments-api"], mentions=["payments-api"])

ticket("PAY-1604", "Validate idempotency-key on refund endpoint", "task", "done", "P2",
       "sofia-alvarez", 6, """
The refund endpoint accepts requests without an Idempotency-Key header, so a client retry can issue a second refund.
Make the header mandatory and reject refunds with a missing or malformed key.
""", about=["payments-api"], mentions=["ledger-service"])

ticket("PAY-1633", "Raise payout batch size from 200 to 500", "task", "done", "P3",
       "sofia-alvarez", 9, """
Payout volume has grown and the daily batch now takes too long to finish before the bank cut-off. Raise the batch size
from 200 to 500 payouts and verify the ledger connection pool can handle the extra concurrency.
""", about=["payouts-service"], mentions=["bank-connector"])

ticket("RISK-377", "Sanctions list refresh skipped on weekends", "bug", "done", "P2",
       "ravi-shankar", 62, """
The sanctions list refresh job only runs Monday to Friday. Merchants onboarded on weekends are screened against
the previous Friday's list. Run the refresh daily and alert when the list is older than 26 hours.
""", about=["sanctions-screening"])

ticket("RISK-401", "Add devices-per-card velocity feature", "task", "done", "P3",
       "mei-lin-chen", 18, """
Fraud analysts want a feature counting distinct devices used with the same card over 24 hours. Add it to the feature
store and to the fraud-scoring model input. Backtest before enabling.
""", about=["fraud-scoring"])

ticket("PLAT-871", "Upgrade kafka-events brokers to 3.7.1", "task", "done", "P3",
       "jonas-eriksson", 30, """
Upgrade the Kafka brokers from 3.6 to 3.7.1 using a rolling restart, one broker at a time. Verify consumer lag stays
under 10 seconds throughout.
""", about=["kafka-events"])

ticket("PLAT-902", "Config pushes need canary and schema validation", "incident-followup", "open", "P2",
       "nikhil-rao", 280, """
Follow-up from INC-2025-089. Routing configuration pushed to api-gateway should be validated against a schema and
applied to a canary slice first. Partially done in api-gateway 8.14.0.
""", about=["inc:2025-089", "api-gateway"])

ticket("MX-655", "Webhook retries flood merchant endpoints after their outage", "incident-followup", "done", "P2",
       "ben-walker", 78, """
Follow-up from INC-2026-031. After a merchant outage, webhook-dispatcher retried every queued event at once and kept
the merchant down. Cap retry attempts and add jitter to the backoff.
""", about=["inc:2026-031", "webhook-dispatcher"])

ticket("MX-701", "Run KYC checks asynchronously after merchant account creation", "task", "done", "P2",
       "kenji-watanabe", 25, """
Merchants wait up to a minute at signup while KYC runs synchronously. Create the account in test mode right away,
run KYC in the background, and enable live mode when checks pass.
""", about=["merchant-onboarding"], mentions=["kyc-service"])


def _pm(year_n, title, author, days, inc_services, text):
    key = f"PM-{year_n}"
    ticket(key, f"Postmortem: {title}", "postmortem", "done", "P2", author, days,
           text.strip() + f"\n{PM_RES[year_n]}\n", about=[f"inc:{year_n}"], mentions=inc_services)


_pm("2025-031", "fraud-scoring timeouts during checkout peak", "arjun-mehta", 450, ["fraud-scoring", "config-service", "risk-rules"], """
INC-2025-031, sev 2. Impact: about 11% of card payments failed or were declined for two hours at the evening checkout peak.
Timeline: risk-rules v2.3.0 lowered RULES_CACHE_TTL to 10s. At peak, config-service CPU reached 98%, fraud-scoring calls
timed out and payments-api returned 5xx.
Root cause: cache TTL too low, causing a thundering herd on a shared config store.
Follow-ups: alert on config-service CPU; add a TTL floor to deploy checks.""")
_pm("2026-012", "merchant-onboarding config reads timing out", "kenji-watanabe", 146, ["merchant-onboarding", "config-service"], """
INC-2026-012, sev 3. Impact: merchant signups were slow or failed for about 40 minutes.
Timeline: merchant-onboarding v2.11.0 disabled the local config cache, so every request read config-service directly.
Latency on config-service rose and onboarding calls timed out.
Root cause: no local cache in front of a shared config store, a thundering herd under signup load.
Follow-up: document that the local config cache must stay enabled.""")
_pm("2025-044", "ledger connection pool exhausted during payout run", "tomasz-kowalski", 390, ["ledger-service", "payouts-service"], """
INC-2025-044, sev 2. Impact: payouts were delayed by three hours and some payment captures failed.
Timeline: ledger-service v3.4.0 added a parallel payout journal writer. During the daily payout run it opened more
connections than the database pool allowed, starving payments-api requests.
Root cause: database connection pool exhaustion.
Follow-up: load-test payout runs against the pool limit.""")
_pm("2025-067", "card-processor-adapter TLS handshake failures", "sofia-alvarez", 335, ["card-processor-adapter", "payments-api"], """
INC-2025-067, sev 1. Impact: all card authorisations failed for 25 minutes.
Timeline: the acquirer client certificate expired at midnight UTC. card-processor-adapter failed every TLS handshake and
payments-api returned errors.
Root cause: expired TLS certificate; renewal was a manual calendar reminder that was missed.
Follow-up: automate renewal and alert 30 days before expiry.""")
_pm("2025-089", "api-gateway routing misconfiguration after config push", "elena-petrova", 290, ["api-gateway", "web-checkout"], """
INC-2025-089, sev 2. Impact: web-checkout and the merchant dashboard returned 404 for 35 minutes in the EU region.
Timeline: api-gateway v8.2.0 shipped a routing table that pointed EU traffic at a service name that did not exist.
Root cause: bad config push without validation or canary.
Follow-up: PLAT-902, schema validation and canary for routing changes.""")
_pm("2026-031", "webhook-dispatcher retry storm after merchant outage", "ben-walker", 76, ["webhook-dispatcher", "kafka-events"], """
INC-2026-031, sev 3. Impact: a large merchant's endpoint was kept down for two hours and kafka-events consumer lag grew.
Timeline: after the merchant endpoint recovered from an outage, webhook-dispatcher retried every queued event at once.
The burst took the endpoint down again, repeatedly.
Root cause: retry storm, with no cap and no jitter on the backoff.
Follow-up: MX-655, cap attempts and add jitter.""")

# ───────────────────────────── decisions ─────────────────────────────
decision("rules-cache-ttl", "RULES_CACHE_TTL must stay ≥ 300s",
         "Below ~30s config-service saturates at checkout peak, because risk-rules refetches rulesets from it on every "
         "cache miss. This is what caused INC-2025-031.",
         430, "arjun-mehta", "risk-rules", "chat:risk-eng-config-load", Q_TTL)
decision("ledger-idempotency-window", "Ledger idempotency keys are honoured for 24 hours",
         "Client retries after the old 60-second window created duplicate journal entries (PAY-1187).",
         205, "priya-nair", "ledger-service", "tkt:PAY-1187", Q_LEDGER)
decision("webhook-retry-policy", "Webhook retries: exponential backoff, max 6 attempts over 24 hours",
         "Bounded retries protect merchant endpoints and keep the queue from growing without limit.",
         240, "ben-walker", "webhook-dispatcher", "doc:webhook-dispatcher-guide", Q_WEBHOOK)
decision("card-processor-timeout-budget", "Card processor gets a 2.5s total budget per authorisation",
         "A single end-to-end budget keeps customers from waiting 6s and avoids double authorisations during 3DS.",
         380, "marcus-webb", "card-processor-adapter", "chat:payments-card-timeouts", Q_CARD)
decision("kafka-retention", "kafka-events retention is 7 days",
         "Almost no consumer reads past two days; 14 days of retention pushed broker disks to 78%.",
         300, "nikhil-rao", "kafka-events", "chat:platform-kafka-retention", Q_KAFKA)
