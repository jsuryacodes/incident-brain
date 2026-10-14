"""Northwind Health: a small, FULLY SYNTHETIC second tenant (systems only; no patient data of any kind).

Its own planted story: notifications v3.2.0 (30 min ago, NW-88) raised SMS_RETRY_LIMIT and removed backoff, against a
decision sourced from #platform chat. patient-portal -> appointments -> notifications, so an alert on patient-portal
traces to it. It knows nothing about Kestrel Pay (no RULES_CACHE_TTL, no risk-rules): that is the isolation test.
Import AFTER timeutil.set_now(): times are computed at import.
"""
from seed.timeutil import ago, stamp

NODES, EDGES = [], []

TEAMS = {"patient-experience": "Patient Experience", "clinical-platform": "Clinical Platform"}
# slug: (name, role, team, joined_days_ago, left_days_ago)
PEOPLE = {
    "ines-moreau": ("Ines Moreau", "Staff Engineer", "patient-experience", 1600, None),
    "tariq-hassan": ("Tariq Hassan", "Engineer", "patient-experience", 500, None),
    "lena-fischer": ("Lena Fischer", "Engineering Manager", "patient-experience", 1200, None),
    "owen-bryce": ("Owen Bryce", "Senior Engineer", "clinical-platform", 1900, 120),
    "maya-okoro": ("Maya Okoro", "Senior Engineer", "clinical-platform", 1100, None),
    "sam-reyes": ("Sam Reyes", "Engineer", "clinical-platform", 45, None),
    "hana-sato": ("Hana Sato", "Site Reliability Engineer", "clinical-platform", 800, None),
    "victor-lund": ("Victor Lund", "Engineering Manager", "clinical-platform", 1400, None),
}
# slug: (tier, language, team, maintainer, description)
SERVICES = {
    "patient-portal": (1, "TypeScript", "patient-experience", "ines-moreau", "Web and mobile portal where patients book visits and view results."),
    "appointments": (1, "Kotlin", "patient-experience", "tariq-hassan", "Books, moves and cancels appointments; sends reminder requests."),
    "lab-results": (1, "Java", "clinical-platform", "maya-okoro", "Publishes finished lab reports to the portal."),
    "notifications": (2, "Go", "clinical-platform", "owen-bryce", "Sends appointment reminders and result alerts by SMS and email."),
    "identity": (1, "Go", "clinical-platform", "hana-sato", "Patient and staff sign-in, sessions and consent records."),
    "records-db": (1, "PostgreSQL", "clinical-platform", "hana-sato", "Primary database for lab reports and visit records."),
    "scheduler-db": (2, "PostgreSQL", "patient-experience", "tariq-hassan", "Database behind appointments."),
    "sms-gateway": (3, "Go", "clinical-platform", "owen-bryce", "Thin wrapper around the SMS provider."),
    "audit-trail": (2, "Java", "clinical-platform", "maya-okoro", "Append-only access log required for compliance."),
}
DEPS = [("patient-portal", "identity", "sync"), ("patient-portal", "appointments", "sync"), ("patient-portal", "lab-results", "sync"),
        ("appointments", "scheduler-db", "db"), ("appointments", "notifications", "sync"), ("lab-results", "records-db", "db"),
        ("lab-results", "notifications", "async"), ("lab-results", "audit-trail", "async"), ("notifications", "sms-gateway", "sync"),
        ("identity", "audit-trail", "async")]
WORK = {"patient-portal": [("ines-moreau", 140, 3), ("tariq-hassan", 30, 20)], "appointments": [("tariq-hassan", 90, 2), ("ines-moreau", 25, 40)],
        "lab-results": [("maya-okoro", 110, 6)], "notifications": [("owen-bryce", 160, 125), ("maya-okoro", 18, 30), ("sam-reyes", 4, 0)],
        "identity": [("hana-sato", 70, 9), ("victor-lund", 6, 200)], "records-db": [("hana-sato", 20, 60)],
        "scheduler-db": [("tariq-hassan", 12, 80)], "sms-gateway": [("owen-bryce", 40, 130), ("maya-okoro", 5, 33)],
        "audit-trail": [("maya-okoro", 35, 15)]}
# (service, version, when, person, summary, ticket)
DEPLOYS = [("notifications", "3.2.0", ago(minutes=30), "sam-reyes", "NW-88: raise SMS_RETRY_LIMIT 3 -> 10 and drop retry backoff", "NW-88"),
           ("audit-trail", "2.4.1", ago(hours=5), "maya-okoro", "Rotate audit archive bucket credentials", None),
           ("patient-portal", "9.1.0", ago(days=2), "ines-moreau", "New results timeline view", None),
           ("lab-results", "4.0.2", ago(days=6), "maya-okoro", "Faster PDF rendering for long reports", None),
           ("notifications", "3.1.0", ago(days=300), "owen-bryce", "Unbounded SMS retries on provider timeout", None),
           ("identity", "5.3.0", ago(days=90), "hana-sato", "Shorter session token lifetime", None)]

for slug, name in TEAMS.items():
    NODES.append({"label": "Team", "id": f"team:{slug}", "name": name})
for slug, (name, role, team, joined, left) in PEOPLE.items():
    p = {"label": "Person", "id": f"per:{slug}", "name": name, "role": role, "email": f"{slug.replace('-', '.')}@northwind.example",
         "status": "left" if left else "active", "joined_at": ago(days=joined)}
    if left:
        p["left_at"] = ago(days=left)
    NODES.append(p)
    EDGES.append((f"per:{slug}", "MEMBER_OF", f"team:{team}", {}))
for slug, (tier, lang, team, maint, desc) in SERVICES.items():
    NODES.append({"label": "Service", "id": f"svc:{slug}", "name": slug, "tier": tier, "description": desc, "language": lang,
                  "repo_url": f"https://git.northwind.example/{slug}"})
    EDGES += [(f"team:{team}", "OWNS", f"svc:{slug}", {}), (f"per:{maint}", "MAINTAINS", f"svc:{slug}", {})]
EDGES += [(f"svc:{a}", "DEPENDS_ON", f"svc:{b}", {"kind": k, "source": "declared"}) for a, b, k in DEPS]
for svc, rows in WORK.items():
    EDGES += [(f"per:{p}", "WORKED_ON", f"svc:{svc}", {"commits": c, "last_at": ago(days=d)}) for p, c, d in rows]

# ───────────── knowledge ─────────────
Q_SMS = "Decision: SMS retries stay capped at 3 attempts with exponential backoff; more than that floods the provider and gets us throttled."
Q_PM1 = "Resolution: restored the 3-attempt cap with backoff and drained the retry queue."
Q_PM2 = "Resolution: added the missing index on visit_id and re-ran the report backfill."


def chat(slug, channel, title, days, author, lines, mentions):
    ts = ago(days=days)
    NODES.append({"label": "ChatThread", "id": f"chat:{slug}", "channel": channel, "title": title, "ts": ts,
                  "text": "\n".join(f"[{stamp(ts + m * 60)}] {who}: {msg}" for m, who, msg in lines)})
    EDGES.append((f"per:{author}", "AUTHORED", f"chat:{slug}", {}))
    EDGES.extend((f"chat:{slug}", "MENTIONS", m, {}) for m in mentions)


def doc(slug, title, author, days, text, describes=(), mentions=()):
    NODES.append({"label": "Doc", "id": f"doc:{slug}", "title": title, "text": text.strip(), "updated_at": ago(days=days), "flagged_stale": False})
    EDGES.append((f"per:{author}", "AUTHORED", f"doc:{slug}", {}))
    EDGES.extend((f"doc:{slug}", "DESCRIBES", d, {}) for d in describes)
    EDGES.extend((f"doc:{slug}", "MENTIONS", m, {}) for m in mentions)


def ticket(key, title, kind, author, days, text, about=()):
    NODES.append({"label": "Ticket", "id": f"tkt:{key}", "key": key, "title": title, "text": text.strip(), "kind": kind,
                  "status": "done", "priority": "P2", "created_at": ago(days=days)})
    EDGES.append((f"per:{author}", "AUTHORED", f"tkt:{key}", {}))
    EDGES.extend((f"tkt:{key}", "ABOUT", a, {}) for a in about)


chat("platform-sms-retries", "#platform", "Why are SMS retries capped?", 290, "owen-bryce", [
    (0, "Maya Okoro", "Post-incident question: why did notifications hammer the SMS provider?"),
    (2, "Owen Bryce", "Every provider timeout triggered an immediate retry, forever. The provider throttled our whole account."),
    (4, "Owen Bryce", Q_SMS),
    (6, "Maya Okoro", "Agreed. Writing it down in the notifications README."),
], ["svc:notifications", "svc:sms-gateway", "per:maya-okoro"])
chat("pe-portal-slow-results", "#patient-experience", "Results page slow after migration", 60, "ines-moreau", [
    (0, "Ines Moreau", "The results page is slow again since the records migration."),
    (3, "Maya Okoro", "lab-results is doing a sequential scan on visit_id; the index was not recreated."),
], ["svc:lab-results", "svc:records-db", "svc:patient-portal"])
doc("notifications-readme", "notifications README", "owen-bryce", 280, """
# notifications
Sends appointment reminders and result alerts. SMS goes through sms-gateway; email through the mail provider.
Owner: Owen Bryce. Retries: at most 3 SMS attempts with exponential backoff (see #platform).
""", describes=["svc:notifications"], mentions=["per:owen-bryce", "svc:sms-gateway"])
doc("patient-experience-onboarding", "Patient Experience onboarding guide", "lena-fischer", 100, """
# Welcome to Patient Experience
We own patient-portal, appointments and the scheduler database.
Your first week: get portal staging access, read the appointments booking flow, ship a small fix with a buddy.
Ask Ines Moreau about the portal and Tariq Hassan about appointments.
""", mentions=["svc:patient-portal", "svc:appointments", "per:ines-moreau", "per:tariq-hassan"])
doc("synthetic-data-policy", "Synthetic data policy", "victor-lund", 30, """
# Synthetic data only
Staging, demos and test fixtures use generated records only. No real patient information may be copied out of production.
""", mentions=["svc:records-db"])
ticket("NW-88", "Appointment reminder SMS sometimes not delivered: retry more", "task", "sam-reyes", 2, """
Some reminder SMS are not delivered when the provider times out. Proposal: raise SMS_RETRY_LIMIT from 3 to 10 and retry
immediately without backoff. Shipped in notifications v3.2.0.
""", about=["svc:notifications"])
ticket("PM-NW-2025-14", "Postmortem: SMS provider throttled our account", "postmortem", "owen-bryce", 295,
       "Unbounded retries in notifications v3.1.0 flooded the SMS provider, which throttled the account for 3 hours. "
       "Appointment reminders stopped.\n" + Q_PM1, about=["inc:nw-2025-14"])
ticket("PM-NW-2026-03", "Postmortem: results page timeouts", "postmortem", "maya-okoro", 58,
       "After the records migration, lab-results scanned records-db without the visit_id index and the portal results "
       "page timed out.\n" + Q_PM2, about=["inc:nw-2026-03"])
NODES.append({"label": "Decision", "id": "dec:sms-retry-cap", "title": "SMS retries are capped at 3 attempts with backoff",
              "rationale": "Unbounded or immediate SMS retries flood the provider, which throttles the whole account.",
              "decided_at": ago(days=290)})
EDGES += [("per:owen-bryce", "AUTHORED", "dec:sms-retry-cap", {}), ("dec:sms-retry-cap", "ABOUT", "svc:notifications", {}),
          ("dec:sms-retry-cap", "SOURCED_FROM", "chat:platform-sms-retries", {"excerpt": Q_SMS})]
NODES.append({"label": "Decision", "id": "dec:results-index", "title": "Every records-db migration recreates the visit_id index",
              "rationale": "Without it lab-results falls back to sequential scans and the portal results page times out.",
              "decided_at": ago(days=58)})
EDGES += [("per:maya-okoro", "AUTHORED", "dec:results-index", {}), ("dec:results-index", "ABOUT", "svc:records-db", {}),
          ("dec:results-index", "SOURCED_FROM", "tkt:PM-NW-2026-03", {"excerpt": Q_PM2})]

# ───────────── incidents ─────────────
NODES += [{"label": "RootCause", "id": "rc:nw-retry-storm", "name": "Retry storm against an external provider",
           "description": "Immediate, unbounded retries amplify a provider timeout until the provider throttles us."},
          {"label": "RootCause", "id": "rc:nw-missing-index", "name": "Missing database index after migration",
           "description": "A migration dropped an index, so queries fall back to sequential scans."}]
for slug, title, sev, days, symptom, summary, affected, cause, rc, people, pm, res_sum, res_quote in [
    ("nw-2025-14", "Appointment reminders stopped: SMS provider throttled us", 2, 300, "appointment reminder SMS not sent; provider 429s",
     "notifications v3.1.0 retried SMS without limit on provider timeouts; the provider throttled the account.",
     ["notifications", "appointments"], "dep:notifications-v3.1.0", "rc:nw-retry-storm", ["owen-bryce"], "tkt:PM-NW-2025-14",
     "Restored the 3-attempt cap with backoff", Q_PM1),
    ("nw-2026-03", "Results page timeouts after records migration", 3, 60, "portal results page timing out",
     "lab-results ran sequential scans on records-db after a migration dropped the visit_id index.",
     ["lab-results", "patient-portal", "records-db"], "svc:records-db", "rc:nw-missing-index", ["maya-okoro"], "tkt:PM-NW-2026-03",
     "Recreated the visit_id index", Q_PM2),
]:
    started = ago(days=days)
    NODES.append({"label": "Incident", "id": f"inc:{slug}", "key": f"INC-{slug.upper()}", "title": title, "severity": sev,
                  "status": "resolved", "symptom": symptom, "summary": summary, "started_at": started, "resolved_at": started + 3600})
    NODES.append({"label": "Resolution", "id": f"res:{slug}", "summary": res_sum, "steps": "1. " + res_sum + "."})
    EDGES += [(f"inc:{slug}", "AFFECTED", f"svc:{s}", {}) for s in affected]
    EDGES += [(f"inc:{slug}", "CAUSED_BY", cause, {}), (f"inc:{slug}", "HAS_ROOT_CAUSE", rc, {}), (f"inc:{slug}", "RESOLVED_BY", f"res:{slug}", {}),
              (f"res:{slug}", "SOURCED_FROM", pm, {"excerpt": res_quote})]
    EDGES += [(f"res:{slug}", "PERFORMED_BY", f"per:{p}", {}) for p in people]
NODES.append({"label": "Runbook", "id": "rb:notifications-delivery", "title": "Runbook: notification delivery failures", "version": 1,
              "updated_at": ago(days=280), "steps": "1. Check the sms-gateway error rate.\n2. Check provider status.\n3. Pause reminder batches if throttled."})
EDGES += [("per:owen-bryce", "AUTHORED", "rb:notifications-delivery", {}), ("rb:notifications-delivery", "DESCRIBES", "svc:notifications", {}),
          ("rb:notifications-delivery", "SOURCED_FROM", "chat:platform-sms-retries", {"excerpt": Q_SMS})]

for svc, ver, ts, person, summary, tkey in DEPLOYS:
    did = f"dep:{svc}-v{ver}"
    NODES.append({"label": "Deploy", "id": did, "version": ver, "ts": ts, "summary": summary})
    EDGES += [(f"per:{person}", "DEPLOYED", did, {}), (did, "CHANGED", f"svc:{svc}", {})]
    if tkey:
        EDGES.append((did, "FOR_TICKET", f"tkt:{tkey}", {}))
