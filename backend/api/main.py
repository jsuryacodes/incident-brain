"""Incident Brain HTTP API (local; deployment comes later).   uvicorn backend.api.main:app

Everyone can explore for free: agents run in MOCK mode unless the request asks for live AND carries a valid
X-Access-Code (and today's live-run cap has room). Responses always say which mode ran and why.
"""
import json
import os
import queue
import threading
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.agents.brain import ask, list_sessions
from backend.agents.team import resolve_incident, run_team, step_events
from backend.api.guard import RateLimiter, decide_mode, require_code
from backend.db import allowed_tenants, get_graph
from backend.llm import LLMClient
from backend.tools.registry import call
from backend.tools.receipt import ToolContext
from seed.load import load

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "runs" / "golden"
GRAPH_CAP, EDGE_CAP = 300, 1500

app = FastAPI(title="Incident Brain API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()],
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Access-Code"])
limiter = RateLimiter()


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path != "/api/health" and not limiter.allow(request.client.host if request.client else "?"):
        return JSONResponse({"detail": "rate limit exceeded; slow down"}, status_code=429)
    return await call_next(request)


def make_llm(mode):  # one place to build the client (tests swap it)
    return LLMClient(mode=mode)


def tenant_ok(tenant):
    if tenant not in allowed_tenants():
        raise HTTPException(404, f"unknown tenant {tenant!r}")
    return tenant


# ───────────── read endpoints ─────────────
@app.get("/api/health")
def health():
    try:
        get_graph(allowed_tenants()[0]).ro_query("RETURN 1")
        db = "ok"
    except Exception as e:  # report, don't crash: this is what the healthcheck reads
        db = f"error: {type(e).__name__}"
    return {"ok": db == "ok", "falkordb": db, "default_llm_mode": os.getenv("LLM_MODE", "mock")}


@app.get("/api/tenants")
def tenants():
    return [{"id": t} for t in allowed_tenants()]


Q_OVERVIEW = """MATCH (n) WHERE NOT n:Step AND NOT n:Session
RETURN n.id, labels(n)[0], coalesce(n.name, n.title, n.key, n.statement, n.summary), n.origin
ORDER BY n.origin, labels(n)[0], n.id LIMIT $cap"""
Q_AROUND = """MATCH (i:Incident {id:$id})-[*1..2]-(n) WHERE NOT n:Step
RETURN DISTINCT n.id, labels(n)[0], coalesce(n.name, n.title, n.key, n.statement, n.summary), n.origin LIMIT $cap"""
Q_INC = "MATCH (n:Incident {id:$id}) RETURN n.id, labels(n)[0], coalesce(n.title, n.key), n.origin"
Q_EDGES = """MATCH (a)-[r]->(b) WHERE a.id IN $ids AND b.id IN $ids
RETURN a.id, type(r), b.id, coalesce(r.source, r.origin, 'seed') LIMIT $cap"""


@app.get("/api/graph")
def graph(tenant: str = "kestrel_pay", mode: str = "overview", id: str | None = None):
    g = get_graph(tenant_ok(tenant))
    if mode == "incident":
        if not id:
            raise HTTPException(400, "mode=incident needs id=inc:...")
        head = g.ro_query(Q_INC, {"id": id}).result_set
        if not head:
            raise HTTPException(404, f"unknown incident {id!r}")
        rows = head + g.ro_query(Q_AROUND, {"id": id, "cap": GRAPH_CAP - 1}).result_set
    elif mode == "overview":
        rows = g.ro_query(Q_OVERVIEW, {"cap": GRAPH_CAP}).result_set
    else:
        raise HTTPException(400, "mode must be overview or incident")
    nodes = {r[0]: {"id": r[0], "label": r[1], "name": r[2], "origin": r[3] or "seed"} for r in rows}
    edges = [{"from": a, "type": t, "to": b, "source": s}
             for a, t, b, s in g.ro_query(Q_EDGES, {"ids": list(nodes), "cap": EDGE_CAP}).result_set]
    return {"tenant": tenant, "mode": mode, "nodes": list(nodes.values()), "edges": edges,
            "truncated": len(nodes) >= GRAPH_CAP or len(edges) >= EDGE_CAP}


@app.get("/api/node/{node_id}")
def node(node_id: str, tenant: str = "kestrel_pay"):
    out = call("node_details", {"node_id": node_id}, ToolContext(tenant=tenant_ok(tenant)))
    if "error" in out.result:
        raise HTTPException(404, out.result["error"])
    return {"result": out.result, "receipt": out.receipt}


@app.get("/api/sessions")
def sessions(user: str, tenant: str = "kestrel_pay"):
    return list_sessions(tenant_ok(tenant), user)


Q_SESSION = "MATCH (s:Session {id:$id}) OPTIONAL MATCH (s)-[:FOR_INCIDENT]->(i:Incident) RETURN s, collect(i.id)"
Q_STEPS = """MATCH (st:Step)-[:IN_SESSION]->(:Session {id:$id})
OPTIONAL MATCH (st)-[:CITED]->(c)
RETURN st, collect(c.id) ORDER BY st.seq"""


@app.get("/api/sessions/{session_id}")
def session(session_id: str, tenant: str = "kestrel_pay"):
    g = get_graph(tenant_ok(tenant))
    head = g.ro_query(Q_SESSION, {"id": session_id}).result_set
    if not head:
        raise HTTPException(404, f"unknown session {session_id!r}")
    steps = [{**st.properties, "cited": cited} for st, cited in g.ro_query(Q_STEPS, {"id": session_id}).result_set]
    return {**head[0][0].properties, "incidents": head[0][1], "steps": steps}


# ───────────── agent runs ─────────────
def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def stream(work, first):
    """Run work(on_event) in a thread and stream its events as SSE, starting with `first`."""
    q = queue.Queue()

    def target():
        try:
            work(lambda t, d: q.put((t, d)))
        except Exception as e:  # surfaced to the client as an error event
            q.put(("error", {"error": f"{type(e).__name__}: {e}"}))
        finally:
            q.put(None)
    threading.Thread(target=target, daemon=True).start()

    def gen():
        yield sse("start", first)
        while (item := q.get()) is not None:
            yield sse(*item)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


class TeamRun(BaseModel):
    tenant: str = "kestrel_pay"
    service_id: str
    symptom: str = Field(min_length=1, max_length=500)
    user: str = "web"
    live: bool = False


@app.post("/api/team/run")
def team_run(body: TeamRun, request: Request):
    tenant_ok(body.tenant)
    mode, reason = decide_mode(request, body.live)
    alert = {"service_id": body.service_id, "symptom": body.symptom}
    return stream(lambda ev: run_team(alert, body.tenant, body.user, make_llm(mode), ev),
                  {"mode": mode, "mode_reason": reason, "alert": alert})


class Resolve(BaseModel):
    tenant: str = "kestrel_pay"
    resolved_by_ids: list[str] = Field(min_length=1)
    what_fixed_it: str = Field(min_length=12, max_length=500)
    user: str = "web"
    live: bool = False


@app.post("/api/incidents/{incident_id}/resolve")
def resolve(incident_id: str, body: Resolve, request: Request):
    tenant_ok(body.tenant)
    mode, reason = decide_mode(request, body.live)
    rec = resolve_incident(incident_id, body.resolved_by_ids, body.what_fixed_it, body.tenant, make_llm(mode), body.user)
    return {"mode": mode, "mode_reason": reason, "status": rec["status"], "session_id": rec["session_id"],
            "incident_id": rec["incident_id"], "handoff": rec["report"], "totals": rec["totals"]}


class Ask(BaseModel):
    tenant: str = "kestrel_pay"
    user: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=500)
    session_id: str | None = None
    live: bool = False


@app.post("/api/brain/ask")
def brain_ask(body: Ask, request: Request):
    tenant_ok(body.tenant)
    mode, reason = decide_mode(request, body.live)
    try:
        r = ask(body.tenant, body.user, body.question, body.session_id, make_llm(mode))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    return {"mode": mode, "mode_reason": reason, **{k: v for k, v in r.items() if k != "steps"},
            "steps": [{k: s.get(k) for k in ("seq", "tool", "action", "summary", "receipt")} for s in r["steps"]]}


@app.post("/api/replay/{run_file}")
def replay(run_file: str, delay_ms: int = 600):
    """Stream a recorded team run from runs/golden/ with realistic pacing. No LLM, no graph writes."""
    path = GOLDEN / Path(run_file).name
    if path.suffix != ".json" or not path.is_file():
        raise HTTPException(404, f"no golden run {run_file!r}; have: {sorted(p.name for p in GOLDEN.glob('*.json'))}")
    rec = json.loads(path.read_text())
    delay = max(0, min(delay_ms, 3000)) / 1000

    def work(ev):
        agent = None
        for step in rec["steps"]:
            if step["agent"] != agent:
                agent = step["agent"]
                ev("agent", {"agent": agent})
            time.sleep(delay)
            for typ, data in step_events(step):
                ev(typ, data)
        ev("report", {"report": rec.get("report"), "incident_id": rec.get("incident_id"), "time_to_cause": rec.get("time_to_cause")})
        ev("done", {"status": rec.get("status"), "session_id": rec.get("session_id"), "totals": rec.get("totals"), "replay": True})
    return stream(work, {"mode": "replay", "mode_reason": f"recorded run {path.name}", "alert": rec.get("alert")})


# ───────────── admin ─────────────
class Reseed(BaseModel):
    tenant: str = "kestrel_pay"


@app.post("/api/admin/reseed", dependencies=[Depends(require_code)])
def reseed(body: Reseed):
    tenant_ok(body.tenant)
    pkg = body.tenant if (ROOT / "seed" / "data" / body.tenant).is_dir() else "kestrel_pay"  # scratch/test graphs
    summary = load(body.tenant, reset=True, data_package=pkg, quiet=True)
    return {"tenant": body.tenant, "nodes": sum(summary["nodes"].values()), "edges": sum(summary["edges"].values()),
            "now": summary["now"]}
