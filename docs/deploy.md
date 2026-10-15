# Deploying Incident Brain (one container)

**Status: nothing has been deployed, and no host has been tested.** This page describes the container and what any
container host needs. Which host to use (and its config files) is still to be chosen with Jaya.

## What the image is
`Dockerfile` is multi-stage: a Node 22 stage builds `frontend/dist`, then a Python 3.12 slim stage runs FastAPI, which
serves the web UI at `/` (with an `index.html` fallback for client routes such as `/brain`) and the API at `/api`, on
one port (`PORT`, default 8000). The recorded runs (`runs/golden/`) are baked in, so visitors without a code always get
the replays. It runs as a non-root user and has a Docker `HEALTHCHECK` on `/api/health` (which pings FalkorDB).

The only external dependency is **FalkorDB** (any reachable instance: FalkorDB Cloud, or a sibling container).

## Environment variables

| Variable | Default | What it does |
|---|---|---|
| `PORT` | `8000` | Port the app listens on (UI + API). |
| `FALKORDB_HOST` | `localhost` | FalkorDB host. |
| `FALKORDB_PORT` | `6379` | FalkorDB port. |
| `FALKORDB_USERNAME` | empty | FalkorDB user, if your instance has ACL users. |
| `FALKORDB_PASSWORD` | empty | FalkorDB password (FalkorDB Cloud needs one). |
| `FALKORDB_TLS` | `0` | `1` for a TLS endpoint (FalkorDB Cloud). |
| `TENANTS` | `kestrel_pay,northwind_health` | Tenant graphs the app may serve (one FalkorDB graph each). |
| `SEED_ON_START` | `0` (`1` in both compose files) | On start, seed every **empty** tenant graph (+ public postmortems), run `seed.verify`, then play the demo story once in mock mode. Graphs that already have data are never touched, so restarts keep memory. |
| `ACCESS_CODE` | empty | Unlocks fresh story runs, persisted Brain conversations, live mode and `/api/admin/reseed`. **Empty = nobody can write**; the UI then works on recorded runs only. |
| `LLM_MODE` | `mock` | `mock` (free) or `live`. Live also needs a request with `live: true`, a valid code and a key. The UI never asks for live. |
| `LLM_MODEL` | `claude-haiku-5-5` | Model for live runs. |
| `ANTHROPIC_API_KEY` | empty | Only for live mode. Leave empty for a free public demo. |
| `MAX_RUN_COST_USD` | `0.05` | Per-run budget guard for live runs. |
| `DAILY_LIVE_RUNS` | `30` | Live runs allowed per UTC day (counter in FalkorDB's Redis). |
| `RATE_LIMIT_PER_MIN` | `60` | Per-IP token bucket on `/api/*` (static files are not limited). |
| `CORS_ORIGINS` | empty | Only needed if another origin calls the API; the bundled UI is same-origin. |

## Run it on any container host (generic steps)
1. Create a FalkorDB instance and note host, port, password and whether it uses TLS.
2. Build the image from the repo root: `docker build -t incident-brain .` (or let the host build the `Dockerfile`).
3. Set the variables above as the host's secrets/env: at least `FALKORDB_*`, `SEED_ON_START=1`, `ACCESS_CODE`
   (a long random string you share only with yourself), and keep `ANTHROPIC_API_KEY` empty unless you mean to spend.
4. Expose the container's `PORT` over HTTPS (TLS terminated by the host). Health check path: `/api/health`.
5. Open the URL: the Story view should play the recorded runs; the Explorer should show amber memory on the first
   company and none on the second.

With Docker Compose on a VM: `FALKORDB_HOST=… FALKORDB_PASSWORD=… FALKORDB_TLS=1 ACCESS_CODE=… docker compose -f docker-compose.prod.yml up --build -d`.

## Local
- `docker compose up --build` → FalkorDB (Browser on http://localhost:3000) + the app on http://localhost:8000 (seeds itself on first start).
- Without Docker for the app: `scripts/setup.sh`, then `scripts/ui.sh`.
- Check a running stack in a real browser: `E2E_BASE_URL=http://localhost:8000 E2E_CODE=<your code> scripts/e2e.sh --no-server`.

## Notes for the host decision
- One instance is enough: the rate limiter is in memory and fresh story runs take a per-tenant lock in the process.
  More than one replica would need the limiter moved to Redis.
- Fresh runs write to the tenant graphs; the "Compare without memory" fresh run uses a temporary twin graph
  `<tenant>__nomem` that is deleted afterwards.
- Run records of fresh runs are also written to `runs/` inside the container (ephemeral; not needed by the UI).
