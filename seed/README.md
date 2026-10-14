# Kestrel Pay seed

Synthetic company loaded into FalkorDB graph `kestrel_pay`, following `docs/schema.md` (locked v1).

```bash
docker start falkordb
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # once
cp .env.example .env                                                  # optional, defaults are localhost:6379
.venv/bin/python -m seed.load   --graph kestrel_pay --reset           # wipe + reload (use --now EPOCH to pin the clock)
.venv/bin/python -m seed.verify --graph kestrel_pay                   # prints every Cypher + PASS/FAIL
```
Re-seed right before recording the demo: the "40 minutes ago" deploy is relative to load time, and
`verify` checks "last 2 hours" against the current clock.
Loading twice without `--reset` is safe (MERGE on `id`).

## Planted stories (schema §7)

| Story | Where |
|---|---|
| Causal chain | `web-checkout → api-gateway → payments-api → fraud-scoring → risk-rules`; `dep:risk-rules-v2.8.0` (40 min ago, RISK-412) |
| Bus factor | `per:arjun-mehta` (left) maintains `svc:risk-rules`; Priya has the most commits among active people |
| Buried decision | `dec:rules-cache-ttl` ← `chat:risk-eng-config-load`; `tkt:RISK-412` contradicts it |
| Hidden dependency | `risk-rules → config-service` is NOT in the graph; only the chat thread and `inc:2025-031` hint at it |
| Recurring pattern | `inc:2025-031` + `inc:2026-012` share `rc:cache-ttl-thundering-herd` |
| Stale knowledge | `doc:risk-rules-readme`, `rb:fraud-scoring-latency` |
| Session 2 setup | `payouts-service → config-service` declared; shares nothing with risk-rules until the learned edge exists |
| Decoy | `dep:email-sender-v1.14.2` (60 min ago), not downstream of payments-api |

## Paste into the FalkorDB Browser (http://localhost:3000, graph `kestrel_pay`)

```cypher
// 1. The risk-rules neighbourhood: owner who left, declared dependency, the decision and its receipt
MATCH (s:Service {id:'svc:risk-rules'})-[r]-(x) RETURN s, r, x

// 2. The causal chain, with the deploy that changed the last hop
MATCH p=(:Service {id:'svc:payments-api'})-[:DEPENDS_ON*1..3]->(s:Service {id:'svc:risk-rules'})<-[c:CHANGED]-(d:Deploy)-[f:FOR_TICKET]->(t:Ticket)
RETURN p, c, d, f, t

// 3. The receipt for the buried decision
MATCH (d:Decision {id:'dec:rules-cache-ttl'})-[r:SOURCED_FROM]->(src) RETURN d, r, src
```
