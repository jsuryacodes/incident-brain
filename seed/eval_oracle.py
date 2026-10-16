"""Ground truth for the eval, independent of the agent: plain Python over the seed's node/edge lists.

No Cypher and no agent tool is used here, so the eval's expected answers do not come from the code it grades.
Used by tests/test_eval_scenarios.py (checks the hand-written expectations) and seed/eval_generator.py.
"""
from collections import deque


def deps(edges):
    out = {}
    for a, t, b, _ in edges:
        if t == "DEPENDS_ON":
            out.setdefault(a, set()).add(b)
    return out


def dist_from(src, adj):
    d, q = {src: 0}, deque([src])
    while q:
        x = q.popleft()
        for y in sorted(adj.get(x, ())):
            if y not in d:
                d[y] = d[x] + 1
                q.append(y)
    return d


def shortest_count(src, dst, adj):
    """Number of distinct shortest DEPENDS_ON paths src -> dst."""
    d, n, q = {src: 0}, {src: 1}, deque([src])
    while q:
        x = q.popleft()
        for y in adj.get(x, ()):
            if y not in d:
                d[y], n[y] = d[x] + 1, n[x]
                q.append(y)
            elif d[y] == d[x] + 1:
                n[y] += n[x]
    return n.get(dst, 0)


def shortest_path(src, dst, adj):
    prev, q = {src: None}, deque([src])
    while q:
        x = q.popleft()
        for y in sorted(adj.get(x, ())):
            if y not in prev:
                prev[y] = x
                q.append(y)
    if dst not in prev:
        return None
    path = [dst]
    while prev[path[-1]] is not None:
        path.append(prev[path[-1]])
    return path[::-1]


def pagerank(services, adj, damping=0.85, iters=100):
    """Credit flows from caller to callee (like algo.pageRank over DEPENDS_ON); dangling nodes spread evenly."""
    n = len(services)
    pr = dict.fromkeys(services, 1 / n)
    for _ in range(iters):
        nxt = dict.fromkeys(services, (1 - damping) / n)
        dangling = sum(pr[s] for s in services if not adj.get(s))
        for s in services:
            outs = adj.get(s) or ()
            for t in outs:
                nxt[t] += damping * pr[s] / len(outs)
        for s in services:
            nxt[s] += damping * dangling / n
        pr = nxt
    return pr


def contact_scores(svc, nodes, edges):
    active = lambda p: nodes.get(p, {}).get("status") == "active"
    score = {}
    for a, t, b, props in edges:
        if t == "WORKED_ON" and b == svc and active(a):
            score[a] = score.get(a, 0) + props["commits"]
    changed = {a for a, t, b, _ in edges if t == "CHANGED" and b == svc}
    incs = {a for a, t, b, _ in edges if (t == "AFFECTED" and b == svc) or (t == "CAUSED_BY" and b in changed)}
    res = {b for a, t, b, _ in edges if t == "RESOLVED_BY" and a in incs}
    fixers = {}
    for a, t, b, _ in edges:
        if t == "PERFORMED_BY" and a in res and active(b):
            fixers.setdefault(b, set()).add(a)
    for p, rs in fixers.items():
        score[p] = score.get(p, 0) + 25 * len(rs)
    return score


def contact_unique(svc, nodes, edges):
    """True if the who-to-call winner is not tied (the agent breaks ties by recency, the oracle by id)."""
    top = sorted(contact_scores(svc, nodes, edges).values(), reverse=True)
    return len(top) < 2 or top[0] != top[1]


def contact(svc, nodes, edges):
    """Top active person by commits + 25 x incident fixes on the service; else the owning team."""
    score = contact_scores(svc, nodes, edges)
    if score:
        return max(sorted(score), key=lambda p: score[p])
    return next(a for a, t, b, _ in edges if t == "OWNS" and b == svc)
