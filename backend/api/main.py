"""Incident Brain HTTP API (local; deployment comes later).   uvicorn backend.api.main:app

Everyone can explore for free: agents run in MOCK mode unless the request asks for live AND carries a valid
X-Access-Code (and today's live-run cap has room). Responses always say which mode ran and why.
"""
import json
import os
import queue
import secrets
import threading
import time
from collections import OrderedDict
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.agents.brain import ask, list_sessions
from backend.agents.team import resolve_incident, run_team
from backend import demo
from backend.api import views
from backend.api.guard import RateLimiter, code_ok, decide_mode, require_code
from backend.db import allowed_tenants, get_graph
from backend.llm import LLMClient
from backend.tools.registry import call
from backend.tools.receipt import ToolContext
from seed.load import load

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "runs" / "golden"
GRAPH_CAP, EDGE_CAP = 300, 1500

VERSION = "1.1"
app = FastAPI(title="Incident Brain API", version=VERSION)
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


Q_NODE_SOURCES = """MATCH (n {id:$id})-[r:SOURCED_FROM]->(src)
RETURN src.id, labels(src)[0], coalesce(src.title, src.key, src.name), r.excerpt"""


@app.get("/api/node/{node_id}")
def node(node_id: str, tenant: str = "kestrel_pay"):
    out = call("node_details", {"node_id": node_id}, ToolContext(tenant=tenant_ok(tenant)))
    if "error" in out.result:
        raise HTTPException(404, out.result["error"])
    g = get_graph(tenant)
    srcs = [{"id": i, "label": l, "title": t or i, "excerpt": ex}
            for i, l, t, ex in g.ro_query(Q_NODE_SOURCES, {"id": node_id}).result_set if ex]
    origin = (out.result.get("props") or {}).get("origin") or "seed"
    return {"result": out.result, "receipt": out.receipt, "origin": origin, "sources": srcs,
            "element": next(iter(views.elements(g, [node_id])["nodes"]), None)}


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


def ui_events(tenant, mode):
    """Wrap a run's on_event so step events carry the UI shape (views.step_event), like replays."""
    index = views.LiveIndex(tenant)

    def wrap(ev):
        return lambda typ, data: ev(typ, index.event(data, mode) if typ == "step" else data)
    return wrap


@app.post("/api/team/run", dependencies=[Depends(require_code)])
def team_run(body: TeamRun, request: Request):
    """A fresh team run. It writes memory, so it needs the access code (visitors use the replays)."""
    tenant_ok(body.tenant)
    mode, reason = decide_mode(request, body.live)
    alert = {"service_id": body.service_id, "symptom": body.symptom}
    wrap = ui_events(body.tenant, mode)
    return stream(lambda ev: run_team(alert, body.tenant, body.user, make_llm(mode), wrap(ev)),
                  {"mode": mode, "mode_reason": reason, "alert": alert})


class Resolve(BaseModel):
    tenant: str = "kestrel_pay"
    resolved_by_ids: list[str] = Field(min_length=1)
    what_fixed_it: str = Field(min_length=12, max_length=500)
    user: str = "web"
    live: bool = False


@app.post("/api/incidents/{incident_id}/resolve", dependencies=[Depends(require_code)])
def resolve(incident_id: str, body: Resolve, request: Request):
    tenant_ok(body.tenant)
    mode, reason = decide_mode(request, body.live)
    rec = resolve_incident(incident_id, body.resolved_by_ids, body.what_fixed_it, body.tenant, make_llm(mode), body.user)
    return {"mode": mode, "mode_reason": reason, "status": rec["status"], "session_id": rec["session_id"],
            "incident_id": rec["incident_id"], "handoff": rec["report"], "totals": rec["totals"]}


class Cite(BaseModel):
    node_id: str = Field(max_length=200)


class Turn(BaseModel):
    question: str = Field(max_length=500)
    answer: str | None = Field(default=None, max_length=3000)
    citations: list[Cite] = Field(default_factory=list, max_length=20)
    people: list[str] = Field(default_factory=list, max_length=20)


class Ask(BaseModel):
    tenant: str = "kestrel_pay"
    user: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=500)
    session_id: str | None = None
    turns: list[Turn] = Field(default_factory=list, max_length=10)  # earlier turns, used only when not persisted
    live: bool = False


@app.post("/api/brain/ask")
def brain_ask(body: Ask, request: Request):
    """Answers work for everyone. With the access code the conversation is persisted in the graph (follow-ups via
    session_id); without it nothing is written and follow-ups use the `turns` the client kept."""
    tenant_ok(body.tenant)
    mode, reason = decide_mode(request, body.live)
    persist = code_ok(request)
    try:
        r = ask(body.tenant, body.user, body.question, body.session_id if persist else None, make_llm(mode),
                persist=persist, turns=[t.model_dump() for t in body.turns])
    except PermissionError as e:
        raise HTTPException(403, str(e))
    g = get_graph(body.tenant)
    ids = [c["node_id"] for c in r.get("citations") or []] + list(r.get("people") or [])
    return {"mode": mode, "mode_reason": reason, **{k: v for k, v in r.items() if k != "steps"},
            "cited_graph": views.elements(g, views.hops_out(g, ids, 0)),
            "sources": [{"id": c["node_id"], "label": views.PREFIX_TO_LABEL.get(c["node_id"].split(":", 1)[0], "?"),
                         "title": views.node_name(*_label_props(g, c["node_id"])), "excerpt": c.get("excerpt")}
                        for c in r.get("citations") or []],
            "steps": [{k: s.get(k) for k in ("seq", "tool", "action", "summary", "receipt")} for s in r["steps"]]}


def _label_props(g, nid):
    rows = g.ro_query("MATCH (n {id:$id}) RETURN labels(n)[0], n", {"id": nid}).result_set
    return (rows[0][0], rows[0][1].properties) if rows else ("?", {"id": nid})


@app.post("/api/replay/{run_file}")
def replay(run_file: str, delay_ms: int = 600):
    """Stream a recorded team run from runs/golden/ with realistic pacing. No LLM, no graph writes."""
    path = GOLDEN / Path(run_file).name
    if path.suffix != ".json" or not path.is_file():
        raise HTTPException(404, f"no golden run {run_file!r}; have: {sorted(p.name for p in GOLDEN.glob('*.json'))}")
    rec = json.loads(path.read_text())
    delay = max(0, min(delay_ms, 3000)) / 1000

    def work(ev):
        for typ, data in views.replay_events(rec):
            if typ == "step":
                time.sleep(delay)
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
    try:
        summary = load(body.tenant, reset=True, quiet=True)  # seed package chosen by seed.load.package_for
    except ValueError as e:  # no seed package for this tenant: refuse rather than load another company's data
        raise HTTPException(400, str(e))
    return {"tenant": body.tenant, "nodes": sum(summary["nodes"].values()), "edges": sum(summary["edges"].values()),
            "now": summary["now"]}


# ───────────── web UI ─────────────
@app.get("/api/meta")
def meta():
    modes = ["replay", "mock"] + (["live"] if os.getenv("ANTHROPIC_API_KEY") else [])
    return {"version": VERSION, "tenants": [{"id": t, "name": demo.tenant_name(t), "has_story": demo.has_story(t)}
                                            for t in allowed_tenants()],
            "llm_modes": modes, "default_llm_mode": os.getenv("LLM_MODE", "mock"),
            "writes_need_code": True, "code_configured": bool(os.getenv("ACCESS_CODE"))}


@app.post("/api/access/check")
def access_check(request: Request):
    """The UI's access-code dialog: does this X-Access-Code unlock fresh runs?"""
    return {"ok": code_ok(request)}


@app.get("/api/story")
def story(tenant: str = "kestrel_pay"):
    return demo.story_meta(tenant_ok(tenant))


RUNS: "OrderedDict[str, dict]" = OrderedDict()  # run_id -> {tenant, beat, record}: this process's fresh story runs
LATEST: dict = {}  # tenant -> {beat_id: record} of the latest fresh story runs (compare/latest prefers them)
RUNS_KEEP = 50


def remember(tenant, beat, rec):
    RUNS[rec["run_id"]] = {"tenant": tenant, "beat": beat, "record": rec}
    while len(RUNS) > RUNS_KEEP:
        RUNS.popitem(last=False)
    LATEST.setdefault(tenant, {})[beat] = rec


def beat_or_404(tenant, beat_id):
    meta = demo.story_meta(tenant_ok(tenant))
    beat = next((b for b in meta["beats"] if b["id"] == beat_id), None)
    if not beat:
        raise HTTPException(404, f"no story beat {beat_id!r} for tenant {tenant!r}")
    return beat


def replay_payload(name):
    rec = demo.golden(name)
    if rec is None:
        raise HTTPException(404, f"no recorded run {name!r}")
    return rec


@app.get("/api/replay/{name}")
def replay_json(name: str):
    """A recorded run as UI events in one response (the UI paces playback itself, so it is deterministic)."""
    rec = replay_payload(name)
    return {"run_id": Path(name).stem, "mode": "replay", "alert": rec.get("alert"), "incident_id": rec.get("incident_id"),
            "incident_key": rec.get("incident_key"), "status": rec.get("status"), "report": rec.get("report"),
            "time_to_cause": rec.get("time_to_cause"), "totals": rec.get("totals"),
            "events": [{"event": t, "data": d} for t, d in views.replay_events(rec)]}


@app.get("/api/run-graph/{run_id}")
def run_graph(run_id: str):
    """Union of every node/edge any step of the run highlights or writes (+ the alert's neighbourhood), so the UI can
    lay the graph out once. run_id: a recorded run name (team-session1 …) or a fresh run id from this process."""
    if run_id in RUNS:
        return RUNS[run_id]["record"]["graph"]
    return replay_payload(run_id)["graph"]


@app.get("/api/subgraph")
def subgraph(tenant: str = "kestrel_pay", ids: str = "", hops: int = 1):
    want = [i for i in ids.split(",") if i.strip()][:100]
    if not want:
        raise HTTPException(400, "ids=… is required (comma-separated node ids)")
    return views.subgraph(tenant_ok(tenant), [i.strip() for i in want], max(0, min(hops, 2)))


STREAMS: dict = {}  # token -> job; EventSource can't send headers, so the code is checked when the job is created
STREAM_TTL = 60
BUSY: dict = {}  # tenant -> Lock: one fresh story run per tenant at a time


class StoryRun(BaseModel):
    tenant: str = "kestrel_pay"
    live: bool = False


@app.post("/api/story/{beat_id}/run", dependencies=[Depends(require_code)])
def story_run(beat_id: str, body: StoryRun, request: Request):
    """Start a FRESH run of a story beat (writes to the graph: access code required). Returns a one-time stream
    token; open GET /api/stream/{token} with EventSource to watch it."""
    beat_or_404(body.tenant, beat_id)
    mode, reason = decide_mode(request, body.live)
    now = time.time()
    for k in [k for k, j in STREAMS.items() if now - j["at"] > STREAM_TTL]:
        STREAMS.pop(k, None)
    token = secrets.token_urlsafe(16)
    STREAMS[token] = {"tenant": body.tenant, "beat": beat_id, "mode": mode, "reason": reason, "at": now}
    return {"stream": f"/api/stream/{token}", "mode": mode, "mode_reason": reason}


@app.get("/api/stream/{token}")
def story_stream(token: str):
    job = STREAMS.pop(token, None)
    if not job or time.time() - job["at"] > STREAM_TTL:
        raise HTTPException(404, "unknown or expired stream token; start the run again")
    tenant, beat_id, mode = job["tenant"], job["beat"], job["mode"]
    beat = beat_or_404(tenant, beat_id)
    lock = BUSY.setdefault(tenant, threading.Lock())
    if not lock.acquire(blocking=False):
        raise HTTPException(409, f"a fresh story run is already in progress on {tenant}; try again in a moment")
    run_tenant = tenant if beat.get("memory", True) else demo.nomem_twin(tenant)

    def work(ev):
        try:
            rec = demo.run_beat(tenant, beat_id, make_llm(mode), ui_events(run_tenant, mode)(ev), LATEST.get(tenant, {}))
            remember(tenant, beat_id, rec)
            ev("run", {"run_id": rec["run_id"], "beat": beat_id, "status": rec["status"]})
        except LookupError as e:
            ev("error", {"error": str(e)})
        finally:
            lock.release()
    return stream(work, {"mode": mode, "mode_reason": job["reason"], "beat": beat_id, "alert": beat.get("alert")})


COMPARE = (("session1", "Session 1"), ("session2", "Session 2 with memory"), ("compare", "Session 2 without memory"))


@app.get("/api/compare/latest")
def compare_latest(tenant: str = "kestrel_pay"):
    """Before/after numbers: this process's latest fresh runs if all three exist, else the recorded runs."""
    meta = demo.story_meta(tenant_ok(tenant))
    if not meta["has_story"]:
        raise HTTPException(404, f"tenant {tenant!r} has no story to compare")
    beats = {b["id"]: b for b in meta["beats"]}
    fresh = LATEST.get(tenant, {})
    use_fresh = all(k in fresh for k, _ in COMPARE)
    cols = [views.compare_column(k, title, fresh[k] if use_fresh else replay_payload(beats[k]["replay"]),
                                 "fresh" if use_fresh else "replay") for k, title in COMPARE]
    return {"tenant": tenant, "source": "fresh" if use_fresh else "replay", "columns": cols,
            "metric": "Investigator tool calls until cause found"}


@app.get("/api/brain/suggestions")
def brain_suggestions(tenant: str = "kestrel_pay"):
    return {"tenant": tenant, "questions": views.suggestions(tenant_ok(tenant))}


@app.get("/api/explorer")
def explorer(tenant: str = "kestrel_pay", labels: str = "", origin: str | None = None):
    if origin not in (None, "", "agent"):
        raise HTTPException(400, "origin must be empty or 'agent'")
    return views.explorer(tenant_ok(tenant), [l for l in labels.split(",") if l] or None, origin or None)
