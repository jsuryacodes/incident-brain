"""scale_demo: a deterministic, generated company (~2,000 services, ~10,000 DEPENDS_ON) for the scale benchmarks.

Same schema as every tenant. Services sit in 6 layers (edge/frontends down to core platforms); each service calls
3-7 services in deeper layers, preferring already-popular ones (preferential attachment), so real hubs form like in
a real company. 40 teams, 320 people (some left), 2-3 people per service, one deploy per service in the last 30 days
and a handful in the last two hours. No story: it exists to measure the tools. Import AFTER timeutil.set_now().
"""
import random

from seed.timeutil import ago

R = random.Random(2026)
LAYERS = [220, 420, 520, 480, 260, 100]  # 2,000 services, edge -> core
AREAS = ["pay", "ledger", "risk", "kyc", "card", "bank", "fx", "auth", "edge", "search", "cart", "order", "ship", "stock",
         "price", "promo", "mail", "sms", "push", "report", "audit", "config", "flag", "event", "queue", "cache", "store",
         "media", "geo", "tax", "invoice", "refund", "loyalty", "review", "chat", "ml", "rank", "feed", "profile", "session"]
KINDS = ["api", "svc", "worker", "gateway", "db", "cache", "stream", "engine", "proxy", "store"]
LANGS = ["Go", "Java", "Python", "Kotlin", "TypeScript", "Rust"]
FIRST = ["Ana", "Ben", "Chen", "Dev", "Eli", "Fay", "Gus", "Hira", "Ivan", "Jo", "Kai", "Lea", "Mo", "Nia", "Oz", "Pia",
         "Quinn", "Raj", "Sol", "Tia"]
LAST = ["Abara", "Brook", "Costa", "Dahl", "Endo", "Frey", "Gold", "Hale", "Iqbal", "Jung", "Kato", "Lind", "Moss", "Nair",
        "Ortiz", "Park"]

NODES, EDGES = [], []
TEAMS = [f"team:{a}" for a in AREAS]
for t in TEAMS:
    NODES.append({"label": "Team", "id": t, "name": t.split(":")[1].capitalize() + " Team"})

people = []
for i in range(320):
    pid = f"per:p{i:03d}"
    left = R.random() < 0.06
    team = TEAMS[i % len(TEAMS)]
    p = {"label": "Person", "id": pid, "name": f"{R.choice(FIRST)} {R.choice(LAST)} {i}", "role": R.choice(["Engineer", "Senior Engineer", "Staff Engineer", "SRE"]),
         "email": f"p{i:03d}@scale.example", "status": "left" if left else "active", "joined_at": ago(days=R.randint(60, 2500))}
    if left:
        p["left_at"] = ago(days=R.randint(10, 400))
    NODES.append(p)
    EDGES.append((pid, "MEMBER_OF", team, {}))
    people.append((pid, team))
by_team = {}
for pid, team in people:
    by_team.setdefault(team, []).append(pid)

layers, n = [], 0
for depth, size in enumerate(LAYERS):
    ids = []
    for _ in range(size):
        area, kind = R.choice(AREAS), KINDS[min(len(KINDS) - 1, depth + R.randint(0, 3))]
        sid = f"svc:{area}-{kind}-{n:04d}"
        n += 1
        team = f"team:{area}"
        NODES.append({"label": "Service", "id": sid, "name": sid.split(":")[1], "tier": 1 if depth >= 4 else 2 if depth >= 2 else 3,
                      "description": f"{area} {kind}, layer {depth}", "language": R.choice(LANGS),
                      "repo_url": f"https://git.scale.example/{sid.split(':')[1]}"})
        EDGES.append((team, "OWNS", sid, {}))
        staff = by_team[team]
        EDGES.append((R.choice(staff), "MAINTAINS", sid, {}))
        for pid in R.sample(staff, k=min(len(staff), R.randint(2, 3))):
            EDGES.append((pid, "WORKED_ON", sid, {"commits": R.randint(1, 200), "last_at": ago(days=R.randint(0, 300))}))
        ids.append(sid)
    layers.append(ids)

popularity = {}
for depth, ids in enumerate(layers[:-1]):
    deeper = [s for d in layers[depth + 1:] for s in d]
    for sid in ids:
        targets = set()
        for _ in range(R.randint(3, 7)):
            # preferential attachment: popular services get picked more (hubs), with a floor for everyone
            pick = max(R.sample(deeper, k=3), key=lambda x: popularity.get(x, 0) + R.random())
            targets.add(pick)
        for tgt in sorted(targets):
            popularity[tgt] = popularity.get(tgt, 0) + 1
            EDGES.append((sid, "DEPENDS_ON", tgt, {"kind": R.choice(["sync", "sync", "async", "db", "cache"]), "source": "declared"}))

all_svcs = [s for d in layers for s in d]
for i, sid in enumerate(all_svcs):  # one deploy each in the last 30 days, a few in the last two hours
    recent = i % 250 == 7
    did = f"dep:{sid.split(':')[1]}-v{R.randint(1, 9)}.{R.randint(0, 40)}.{i % 10}"
    NODES.append({"label": "Deploy", "id": did, "version": did.split("-v")[-1],
                  "ts": ago(minutes=R.randint(5, 110)) if recent else ago(days=R.randint(1, 30)),
                  "summary": f"{R.choice(['Tune', 'Refactor', 'Upgrade', 'Fix', 'Add'])} {R.choice(['pool size', 'retry policy', 'cache TTL', 'client library', 'index', 'timeouts'])}"})
    EDGES.append((did, "CHANGED", sid, {}))
    EDGES.append((R.choice(by_team[f"team:{sid.split(':')[1].split('-')[0]}"]), "DEPLOYED", did, {}))
