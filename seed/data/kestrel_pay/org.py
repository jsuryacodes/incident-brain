"""Teams, people, and their edges: MEMBER_OF, OWNS, MAINTAINS, WORKED_ON."""
from seed.timeutil import ago

TEAMS = {
    "payments-core": "Payments Core",
    "risk-fraud": "Risk & Fraud",
    "platform": "Platform",
    "merchant-exp": "Merchant Experience",
}

# slug: (name, role, team, joined_days_ago, left_days_ago or None)
PEOPLE = {
    "priya-nair": ("Priya Nair", "Senior Engineer", "payments-core", 1500, None),
    "marcus-webb": ("Marcus Webb", "Staff Engineer", "payments-core", 2300, None),
    "sofia-alvarez": ("Sofia Alvarez", "Engineer", "payments-core", 900, None),
    "tomasz-kowalski": ("Tomasz Kowalski", "Engineer", "payments-core", 700, None),
    "aiko-tanaka": ("Aiko Tanaka", "Engineering Manager", "payments-core", 1800, None),
    "arjun-mehta": ("Arjun Mehta", "Staff Engineer", "risk-fraud", 2200, 95),
    "leo-park": ("Leo Park", "Engineer", "risk-fraud", 60, None),
    "dana-okafor": ("Dana Okafor", "Engineering Manager", "risk-fraud", 400, None),
    "mei-lin-chen": ("Mei Lin Chen", "Senior Engineer", "risk-fraud", 1100, None),
    "ravi-shankar": ("Ravi Shankar", "Engineer", "risk-fraud", 520, None),
    "nikhil-rao": ("Nikhil Rao", "Staff Engineer", "platform", 2100, None),
    "elena-petrova": ("Elena Petrova", "Senior Engineer", "platform", 1300, None),
    "omar-haddad": ("Omar Haddad", "Engineer", "platform", 800, None),
    "grace-liu": ("Grace Liu", "Engineering Manager", "platform", 1600, None),
    "jonas-eriksson": ("Jonas Eriksson", "Site Reliability Engineer", "platform", 640, None),
    "camila-torres": ("Camila Torres", "Engineering Manager", "merchant-exp", 1400, None),
    "ben-walker": ("Ben Walker", "Senior Engineer", "merchant-exp", 1700, None),
    "fatima-zahra": ("Fatima Zahra", "Engineer", "merchant-exp", 950, None),
    "kenji-watanabe": ("Kenji Watanabe", "Engineer", "merchant-exp", 600, None),
    "carlos-mendes": ("Carlos Mendes", "Engineer", "merchant-exp", 1900, 210),
}

# service slug -> (owning team, maintainer)
OWNERSHIP = {
    "payments-api": ("payments-core", "marcus-webb"),
    "ledger-service": ("payments-core", "priya-nair"),
    "card-processor-adapter": ("payments-core", "sofia-alvarez"),
    "bank-connector": ("payments-core", "tomasz-kowalski"),
    "payouts-service": ("payments-core", "sofia-alvarez"),
    "reconciliation-job": ("payments-core", "tomasz-kowalski"),
    "fx-rates-service": ("payments-core", "sofia-alvarez"),
    "ledger-db": ("payments-core", "marcus-webb"),
    "fraud-scoring": ("risk-fraud", "arjun-mehta"),
    "risk-rules": ("risk-fraud", "arjun-mehta"),
    "rules-store-db": ("risk-fraud", "ravi-shankar"),
    "kyc-service": ("risk-fraud", "mei-lin-chen"),
    "sanctions-screening": ("risk-fraud", "mei-lin-chen"),
    "api-gateway": ("platform", "nikhil-rao"),
    "auth-service": ("platform", "elena-petrova"),
    "config-service": ("platform", "omar-haddad"),
    "config-db": ("platform", "jonas-eriksson"),
    "kafka-events": ("platform", "nikhil-rao"),
    "feature-flags": ("platform", "elena-petrova"),
    "audit-log": ("platform", "omar-haddad"),
    "web-checkout": ("merchant-exp", "ben-walker"),
    "merchant-dashboard": ("merchant-exp", "fatima-zahra"),
    "merchant-onboarding": ("merchant-exp", "kenji-watanabe"),
    "notifications-service": ("merchant-exp", "fatima-zahra"),
    "email-sender": ("merchant-exp", "kenji-watanabe"),
    "webhook-dispatcher": ("merchant-exp", "ben-walker"),
    "reporting-service": ("merchant-exp", "carlos-mendes"),
}

# service -> [(person, commits, last_commit_days_ago)]   (1-4 per service)
WORK = {
    "payments-api": [("marcus-webb", 120, 3), ("priya-nair", 64, 5), ("sofia-alvarez", 31, 16)],
    "ledger-service": [("priya-nair", 210, 2), ("marcus-webb", 88, 30), ("tomasz-kowalski", 14, 12)],
    "card-processor-adapter": [("sofia-alvarez", 95, 4), ("marcus-webb", 40, 21)],
    "bank-connector": [("tomasz-kowalski", 110, 6), ("sofia-alvarez", 22, 40)],
    "payouts-service": [("sofia-alvarez", 140, 5), ("tomasz-kowalski", 37, 19), ("priya-nair", 12, 55)],
    "reconciliation-job": [("tomasz-kowalski", 75, 8), ("priya-nair", 9, 70)],
    "fx-rates-service": [("sofia-alvarez", 52, 13), ("marcus-webb", 11, 90)],
    "ledger-db": [("marcus-webb", 45, 33), ("priya-nair", 18, 61)],
    "fraud-scoring": [("arjun-mehta", 240, 100), ("mei-lin-chen", 88, 10), ("leo-park", 14, 24)],
    "risk-rules": [("arjun-mehta", 180, 100), ("priya-nair", 23, 40), ("leo-park", 3, 1), ("dana-okafor", 2, 120)],
    "rules-store-db": [("ravi-shankar", 30, 50), ("arjun-mehta", 12, 130)],
    "kyc-service": [("mei-lin-chen", 66, 11), ("ravi-shankar", 40, 35)],
    "sanctions-screening": [("mei-lin-chen", 45, 15), ("ravi-shankar", 18, 15)],
    "api-gateway": [("nikhil-rao", 170, 1), ("elena-petrova", 60, 14), ("jonas-eriksson", 20, 44)],
    "auth-service": [("elena-petrova", 130, 7), ("nikhil-rao", 35, 60)],
    "config-service": [("omar-haddad", 95, 17), ("nikhil-rao", 70, 80), ("jonas-eriksson", 15, 45)],
    "config-db": [("jonas-eriksson", 22, 30), ("omar-haddad", 9, 110)],
    "kafka-events": [("nikhil-rao", 55, 26), ("jonas-eriksson", 48, 26)],
    "feature-flags": [("elena-petrova", 77, 22), ("omar-haddad", 33, 50)],
    "audit-log": [("omar-haddad", 41, 20), ("elena-petrova", 12, 75)],
    "web-checkout": [("ben-walker", 210, 2), ("fatima-zahra", 95, 8), ("kenji-watanabe", 30, 60)],
    "merchant-dashboard": [("fatima-zahra", 150, 5), ("ben-walker", 40, 33)],
    "merchant-onboarding": [("kenji-watanabe", 120, 12), ("fatima-zahra", 34, 50), ("priya-nair", 6, 148)],
    "notifications-service": [("fatima-zahra", 60, 9), ("kenji-watanabe", 28, 40)],
    "email-sender": [("kenji-watanabe", 33, 0), ("carlos-mendes", 20, 250)],
    "webhook-dispatcher": [("ben-walker", 70, 14), ("kenji-watanabe", 25, 80)],
    "reporting-service": [("carlos-mendes", 88, 215), ("ben-walker", 15, 27)],
}

NODES = [{"label": "Team", "id": f"team:{s}", "name": n} for s, n in TEAMS.items()]
EDGES = []
for slug, (name, role, team, joined, left) in PEOPLE.items():
    p = {"label": "Person", "id": f"per:{slug}", "name": name, "role": role,
         "email": f"{slug.replace('-', '.')}@kestrelpay.example",
         "status": "left" if left else "active", "joined_at": ago(days=joined)}
    if left:
        p["left_at"] = ago(days=left)
    NODES.append(p)
    EDGES.append((f"per:{slug}", "MEMBER_OF", f"team:{team}", {}))
for svc, (team, maint) in OWNERSHIP.items():
    EDGES.append((f"team:{team}", "OWNS", f"svc:{svc}", {}))
    EDGES.append((f"per:{maint}", "MAINTAINS", f"svc:{svc}", {}))
for svc, rows in WORK.items():
    for person, commits, last in rows:
        EDGES.append((f"per:{person}", "WORKED_ON", f"svc:{svc}", {"commits": commits, "last_at": ago(days=last)}))
