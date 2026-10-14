"""Deterministic, rule-based stand-in for the LLM: no API, no cost.

respond(agent, system, tools, messages) reads the conversation so far (the initial JSON payload and every tool result)
and emits the next assistant turn the way a good model would. Every choice is derived from tool results: the culprit,
contact, conflicting decision and similar incidents all come out of what the graph returned, never hard-coded.
"""
import json
import re

FENCE = re.compile(r"```json\n(.*?)\n```", re.S)
_STOP = {"the", "and", "for", "must", "stay", "with", "from", "that", "this", "into", "only", "are", "was", "not",
         "can", "new", "all", "per", "via", "its", "has", "have", "use", "when", "take", "takes", "apply"}


class View:
    """What the policy can see: the payload in the first user message, and (tool, input, result) for every call."""

    def __init__(self, messages):
        self.payload, self.calls, self.turns, self.history = {}, [], 0, []
        pending = {}
        for m in messages:
            c = m["content"]
            if isinstance(c, str) and not FENCE.search(c):
                self.history.append(c)  # earlier conversation turns (Brain follow-ups)
            elif m["role"] == "assistant":
                self.turns += 1
                for b in c:
                    if b["type"] == "tool_use":
                        pending[b["id"]] = (b["name"], b.get("input") or {})
            elif isinstance(c, str):
                if (f := FENCE.search(c)) and not self.payload:
                    self.payload = json.loads(f.group(1))
            else:
                for b in c:
                    if b.get("type") == "tool_result" and b["tool_use_id"] in pending:
                        name, inp = pending.pop(b["tool_use_id"])
                        self.calls.append((name, inp, json.loads(b["content"]), bool(b.get("is_error"))))

    def called(self, tool):
        return any(c[0] == tool for c in self.calls)

    def last(self, tool, **match):
        for name, inp, res, err in reversed(self.calls):
            if name == tool and not err and all(inp.get(k) == v for k, v in match.items()):
                return res
        return None

    def all(self, tool):
        return [(inp, res) for name, inp, res, err in self.calls if name == tool and not err]


def turn(n, *calls):
    """calls: (tool name, input) -> assistant content blocks with deterministic ids."""
    return [{"type": "tool_use", "id": f"toolu_mock_{n}_{i}", "name": t, "input": a} for i, (t, a) in enumerate(calls)]


def _tokens(text):
    return {w for w in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(w) >= 3 and w not in _STOP}


# ───────────── analysis shared by every incident agent ─────────────
def culprit_from(recent, shared, only=None):
    """First downstream hit (nearest), else first noisy neighbour; with `only`, the first hit on one of those
    services. -> dict or None."""
    for res, is_shared in ((recent, False), (shared, True)):
        for h in (res or {}).get("hits", []):
            svc = h["neighbour"] if is_shared else h["service"]
            if only is not None and svc not in only:
                continue
            if not is_shared:
                return {"service": svc, "deploy": h["deploy"], "ticket": h.get("ticket"), "path": h["path"],
                        "learned_hop": "learned" in h.get("edge_sources", []), "shared": None}
            path = h["path_to_shared"] + h["neighbour_path"][::-1][1:]  # alerting -> shared -> neighbour
            return {"service": svc, "deploy": h["deploy"], "ticket": h.get("ticket"), "path": path,
                    "learned_hop": h.get("uses_learned_edge", False), "shared": h["shared"],
                    "learned_facts": h.get("learned_facts", [])}
    return None


def suspects_of(recall):
    return (recall or {}).get("suspects") or []


def verify_call(svc, suspect):
    """The cheapest check of a suspect from memory: recent deploys where it sits relative to the alerting service."""
    tool = "recent_changes_downstream" if suspect["relation"] == "downstream" else "shared_dependency_changes"
    return tool, {"service_id": svc, "since_minutes": 120}


def find_culprit(v, svc, both_at_once):
    """Memory first: verify recall's top suspect with one tool. If nothing was recalled, or the suspect did not
    change recently, scan as before. -> ("call", [tool calls]) or ("culprit", culprit or None, from_memory)."""
    sus = {s["service"] for s in suspects_of(v.last("memory_recall"))}
    recent, shared = v.last("recent_changes_downstream"), v.last("shared_dependency_changes")
    if sus and (c := culprit_from(recent, shared, only=sus)):
        return "culprit", c, True
    if sus and recent is None and shared is None:
        return "call", [verify_call(svc, suspects_of(v.last("memory_recall"))[0])]
    scan = {"service_id": svc, "since_minutes": 120}
    if both_at_once:
        missing = [t for t, r in (("recent_changes_downstream", recent), ("shared_dependency_changes", shared)) if r is None]
        if missing:
            return "call", [(t, scan) for t in missing]
    elif recent is None:
        return "call", [("recent_changes_downstream", scan)]
    elif not recent["hits"] and shared is None:
        return "call", [("shared_dependency_changes", scan)]
    return "culprit", culprit_from(recent, shared), False


def conflict_from(culprit, decisions):
    """A decision is contradicted when the change text (deploy summary + ticket title) shares >= 2 significant words
    with the decision title. -> (decision, source) or None."""
    if not culprit or not decisions:
        return None
    change = _tokens(culprit["deploy"]["summary"] + " " + ((culprit.get("ticket") or {}).get("title") or ""))
    for d in decisions.get("decisions", []):
        if len(change & _tokens(d["title"])) >= 2 and d["sources"]:
            return d, d["sources"][0]
    return None


def recalled(culprit, past):
    """Resolved past incidents that were caused by a change to the culprit service."""
    if not culprit or not past:
        return []
    return [i for i in past.get("incidents", [])
            if culprit["service"] in i.get("caused_by_change_to", []) and i.get("status") == "resolved"]


def industry_line(res):
    """'Matches known industry pattern: <company> — <title> (<url>)' for the best industry_matches hit, else None."""
    m = ((res or {}).get("matches") or [None])[0]
    return f"Matches known industry pattern: {m['company']} — {m['title']} ({m['url']})" if m else None


def svc_name(sid):
    return sid.split(":", 1)[-1] if sid else sid


def contact_from(who):
    cands = (who or {}).get("candidates") or []
    if not cands:
        return None, None
    c = cands[0]
    reason = f"{c['commits']} commits" + (f", {c['resolutions']} past incident fix(es)" if c.get("resolutions") else "") \
             + f" on {svc_name(who['service'])} (score {c['score']})"
    left = [m["name"] for m in who.get("maintainers", []) if m["status"] == "left"]
    warn = None
    if who.get("bus_factor_risk"):
        warn = "; ".join(who.get("bus_factor_reasons", [])) + f". Page {c['name']} instead" + (
            f" of {', '.join(left)}." if left else ".")
    return {"person_id": c["id"], "name": c["name"], "reason": reason}, warn


def build_report(alert_svc, culprit, blast, who, decisions, past, industry=None):
    """The incident report, built only from tool results."""
    contact, warn = contact_from(who)
    conf = conflict_from(culprit, decisions)
    similar = recalled(culprit, past)
    evidence, actions = [], []
    if culprit:
        d = culprit["deploy"]
        tkey = (culprit.get("ticket") or {}).get("key")
        hop = "a learned dependency" if culprit["learned_hop"] else "declared dependencies"
        how = (f"{svc_name(alert_svc)} and {svc_name(culprit['service'])} both call {svc_name(culprit['shared'])} (via {hop})"
               if culprit["shared"] else f"{svc_name(alert_svc)} calls {svc_name(culprit['service'])} via {hop}")
        cause = {"service_id": culprit["service"], "deploy_id": d["id"], "ticket_key": tkey, "path": culprit["path"],
                 "explanation": f"{d['summary']} ({d['id']}, deployed {d['minutes_ago']} min ago by {d['by']}). "
                                f"{how}: " + " -> ".join(map(svc_name, culprit["path"])) + "."}
        evidence.append({"node_id": d["id"], "claim": f"{svc_name(culprit['service'])} deployed {d['minutes_ago']} min ago: {d['summary']}"})
        actions.append(f"Roll back {d['id']} on {svc_name(culprit['service'])}.")
    else:
        cause = {"service_id": None, "deploy_id": None, "ticket_key": None, "path": [],
                 "explanation": "No recent change was found downstream of or sharing a dependency with the alerting service."}
    conflicting = None
    if conf:
        dec, src = conf
        conflicting = {"decision_id": dec["id"], "source_id": src["id"], "excerpt": src["excerpt"].rstrip("…"),
                       "how_it_conflicts": f"The change ({culprit['deploy']['summary']}) contradicts \"{dec['title']}\", "
                                           f"decided by {dec['author']}" + (" (who has left)" if dec.get("author_status") == "left" else "") + "."}
        evidence.append({"node_id": dec["id"], "claim": f"Decision \"{dec['title']}\" ({dec['decided']}), source {src['id']}."})
        actions.append(f"Restore the setting required by {dec['id']} before re-shipping.")
    sims = [{"incident_id": i["id"], "what_fixed_it": i.get("resolution") or "unknown",
             "resolved_by": ", ".join(i.get("resolved_by") or []) or "unknown"} for i in similar]
    for i in similar[:2]:
        evidence.append({"node_id": i["id"], "claim": f"{i['key']} was caused by a change to {svc_name(culprit['service'])}; "
                                                       f"fixed by {', '.join(i.get('resolved_by') or ['?'])}: {i.get('resolution')}"})
    if contact:
        evidence.append({"node_id": contact["person_id"], "claim": f"Best active contact: {contact['reason']}."})
        actions.insert(1, f"Page {contact['name']} ({contact['person_id']}).")
    if similar:
        actions.append(f"Follow the {similar[0]['key']} fix: {similar[0].get('resolution')}.")
    if blast:
        evidence.append({"node_id": alert_svc, "claim": f"{blast['upstream_count']} upstream services ({blast['tier1_count']} tier-1) are exposed."})
    if len(evidence) < 3 and past:
        evidence += [{"node_id": i["id"], "claim": i["title"]} for i in past.get("incidents", [])[: 3 - len(evidence)]]
    score = bool(culprit) + bool(conf) + bool(similar)
    if culprit:
        summary = (f"{svc_name(alert_svc)} errors are most likely caused by {culprit['deploy']['id']} on "
                   f"{svc_name(culprit['service'])}, deployed {culprit['deploy']['minutes_ago']} min ago.")
        if conf:
            summary += f" The change contradicts decision {conf[0]['id']}."
        if contact:
            summary += f" Contact {contact['name']}" + ("; the maintainer has left." if warn else ".")
    else:
        summary = f"No recent change explains the {svc_name(alert_svc)} alert; the cause is unknown."
    return {"summary": summary, "likely_cause": cause,
            "blast_radius": [u["id"] for u in (blast or {}).get("upstream", [])],
            "contact": contact or {"person_id": None, "name": None, "reason": "no candidate found"},
            "bus_factor_warning": warn, "conflicting_decision": conflicting, "similar_past_incidents": sims,
            "evidence": evidence, "recommended_actions": actions[:4],
            "confidence": ["low", "low", "medium", "high"][score], "industry_pattern": industry_line(industry)}


# ───────────── firefighter ─────────────
def firefighter(v):
    alert = v.payload.get("alert", {})
    svc = alert.get("service_id")
    if not svc:
        fs = v.last("find_service")
        if fs is None:
            return turn(1, ("find_service", {"query": alert.get("service_query", "")}))
        svc = fs["matches"][0]["id"] if fs.get("matches") else None
        if not svc:
            return []  # nothing to investigate; the loop nudges, the run ends at step_limit
    if not v.called("memory_recall"):
        return turn(v.turns, ("memory_recall", {"service_id": svc}))
    found = find_culprit(v, svc, both_at_once=False)
    if found[0] == "call":
        return turn(v.turns, *found[1])
    culprit = found[1]
    if not v.called("blast_radius"):
        calls = [("blast_radius", {"service_id": svc})]
        ids = [svc]
        if culprit:
            calls += [("who_to_call", {"service_id": culprit["service"]}),
                      ("decisions_about", {"service_id": culprit["service"]})]
            ids += [culprit["service"]] + ([culprit["shared"]] if culprit["shared"] else [])
        else:
            calls.append(("who_to_call", {"service_id": svc}))
        return turn(v.turns, *calls, ("past_incidents", {"service_ids": ids}))
    rc = next((r for i in recalled(culprit, v.last("past_incidents")) for r in i.get("root_causes", [])), None)
    if rc and not v.called("industry_matches"):
        return turn(v.turns, ("industry_matches", {"root_cause_id": rc}))
    report = build_report(svc, culprit, v.last("blast_radius"), v.last("who_to_call"), v.last("decisions_about"),
                          v.last("past_incidents"), v.last("industry_matches"))
    return turn(v.turns, ("submit_report", report))


# ───────────── the team: shared helpers ─────────────
DEP_VERBS = r"(?:polls|calls|queries|fetches|reads from|depends on|talks to|hits)"
CONFIG_KEY = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b")


def _state(v):
    return v.payload.get("incident_state") or {}


def _handoff(state, agent):
    hs = [h for h in state.get("handoffs", []) if h["agent"] == agent and h.get("details")]
    return hs[-1]["details"] if hs else {}


def learn_from_source(src, culprit):
    """A sentence in the source saying '<culprit> polls/calls/... <other mentioned service>' -> learned dependency."""
    if not src:
        return None
    cname = svc_name(culprit)
    for m in src.get("mentions", []):
        if not m.startswith("svc:") or m == culprit:
            continue
        for sent in re.split(r"(?<=[.!?])\s+|\n", src.get("text", "")):
            if re.search(rf"{re.escape(cname)}\b[^.]*?\b{DEP_VERBS}\b[^.]*?{re.escape(svc_name(m))}", sent):
                quote = re.sub(r"^\[[^\]]*\] [^:]+: ", "", sent).strip()  # drop the chat "[time] Name: " prefix
                return {"from": culprit, "to": m, "excerpt": quote, "source_id": src["id"]}
    return None


def runbook_step(rb, similar, culprit):
    """The runbook step holding a past fix (else the first one naming the culprit) -> {runbook_id, step, text}."""
    if not rb:
        return None
    lines = [re.sub(r"^\s*[0-9]+[.)]\s*", "", l) for l in rb.get("text", "").split("\n") if l.strip()]
    fixes = [(i.get("resolution") or "").rstrip("…").lower() for i in similar]
    for test in (lambda l: any(f and f in l.lower() for f in fixes), lambda l: svc_name(culprit) in l):
        for n, line in enumerate(lines, 1):
            if test(line):
                return {"runbook_id": rb["id"], "step": n, "text": line}
    return None


# ───────────── triage ─────────────
def triage(v):
    alert = v.payload["alert"]
    svc = alert["service_id"]
    if not v.called("blast_radius"):
        return turn(v.turns, ("find_service", {"query": svc_name(svc)}), ("blast_radius", {"service_id": svc}),
                    ("critical_services", {"algorithm": "pagerank", "limit": 10}), ("past_incidents", {"service_ids": [svc]}))
    blast = v.last("blast_radius") or {"upstream": [], "upstream_count": 0, "tier1_count": 0}
    fs, pr, past = v.last("find_service") or {}, v.last("critical_services") or {}, v.last("past_incidents") or {}
    tier = next((m["tier"] for m in fs.get("matches", []) if m["id"] == svc), None)
    rank = next((i for i, x in enumerate(pr.get("services", []), 1) if x["id"] == svc), None)
    sev = 1 if blast["tier1_count"] >= 3 else 2 if tier == 1 or blast["tier1_count"] >= 1 else 3
    if not v.called("open_incident"):
        return turn(v.turns, ("open_incident", {"service_id": svc, "symptom": alert["symptom"], "severity": sev}))
    opened = v.last("open_incident") or {}
    t1 = [u["id"] for u in blast["upstream"] if u["tier"] == 1]
    reasoning = (f"{svc_name(svc)} is tier {tier} with {blast['upstream_count']} upstream callers "
                 f"({blast['tier1_count']} tier-1)" + (f"; PageRank rank {rank}" if rank else "; not in the PageRank top 10"))
    seen = [{"id": i["id"], "key": i["key"], "title": i["title"], "resolution": i.get("resolution"),
             "resolved_by": i.get("resolved_by")} for i in past.get("incidents", [])[:3]]
    note = (f"Opened {opened.get('key', '?')} ({opened.get('id')}) at severity {sev}: {reasoning}. "
            f"Blast radius: {', '.join(map(svc_name, t1)) or 'no tier-1 callers'}. "
            + (f"Seen on this service before: {', '.join(i['key'] for i in seen)}." if seen else "No past incidents on this service."))
    return turn(v.turns, ("submit_handoff", {"note": note, "details": {
        "incident_id": opened.get("id"), "severity": sev, "reasoning": reasoning,
        "blast_radius": [u["id"] for u in blast["upstream"]], "tier1_upstream": t1, "pagerank_rank": rank, "seen_before": seen}}))


# ───────────── investigator ─────────────
def seen_before(inc, step):
    """'Seen before: INC-x, fixed by P (summary), see Runbook vN step K (rb:...)' from a recalled incident."""
    who = ", ".join(p["name"] for p in inc.get("resolved_by", [])) or "unknown"
    fix = (inc.get("resolution") or {}).get("summary") or "fix not recorded"
    rb = inc.get("runbook")
    return (f"Seen before: {inc['key']}, fixed by {who} ({fix})"
            + (f", see Runbook v{rb['version']} step {step['step']} ({rb['id']})" if rb and step else "") + ".")


def investigator(v):
    alert = v.payload["alert"]
    svc, inc = alert["service_id"], _state(v).get("id")
    if not v.called("memory_recall"):
        return turn(v.turns, ("memory_recall", {"service_id": svc}))
    found = find_culprit(v, svc, both_at_once=True)
    if found[0] == "call":
        return turn(v.turns, *found[1])
    _, c, from_memory = found
    if c is None:
        if not v.called("past_incidents"):
            return turn(v.turns, ("past_incidents", {"service_ids": [svc]}))
        note = (f"No service downstream of {svc_name(svc)}, or sharing a dependency with it, changed in the last 120 min. "
                "Cause unknown; confidence low. Not setting a cause.")
        return turn(v.turns, ("submit_handoff", {"note": note, "details": {
            "likely_cause": None, "conflicting_decision": None, "similar_past_incidents": [], "confidence": "low",
            "evidence": [{"node_id": svc, "claim": "no recent downstream or shared-dependency change in 120 min"}]}}))
    # incidents an earlier session resolved that were caused by a change to the same service
    mem_incs = [i for i in (v.last("memory_recall") or {}).get("incidents", [])
                if (i.get("cause") or {}).get("service") == c["service"]] if from_memory else []
    reads = [("decisions_about", {"service_id": c["service"]}),
             ("past_incidents", {"service_ids": [svc, c["service"]] + ([c["shared"]] if c["shared"] else []), "limit": 10}),
             ("who_to_call", {"service_id": c["service"]})]

    def update(similar, learned=None):
        upd = {"incident_id": inc, "cause_deploy_id": c["deploy"]["id"], "cause_service_id": c["service"],
               "affected_ids": list(dict.fromkeys(c["path"][1:] + ([learned["to"]] if learned else [])))}
        if rc := next((r for i in similar for r in i.get("root_causes", [])), None):
            upd["root_cause_id"] = rc
        return "update_incident", upd

    def link(i):
        return "link_similar", {"incident_id": inc, "other_id": i["id"], "score": 0.9 if i.get("origin", "agent") == "agent" else 0.8,
                                "reason": f"also caused by a change to {svc_name(c['service'])}: {i['title']}"}
    if from_memory and not v.called("update_incident"):
        # memory named the culprit and one tool confirmed it: set the cause now, then gather the rest
        return turn(v.turns, update(mem_incs), *[link(i) for i in mem_incs], *reads)
    if not v.called("decisions_about"):
        return turn(v.turns, *reads)
    dec, past, who = v.last("decisions_about"), v.last("past_incidents"), v.last("who_to_call")
    conf = conflict_from(c, dec)
    # a learned hop means an earlier session already read that source and recorded what it says
    if conf and not c["learned_hop"] and not v.called("read_source"):
        return turn(v.turns, ("read_source", {"node_id": conf[1]["id"]}))
    similar = recalled(c, past)
    learned = learn_from_source(v.last("read_source"), c["service"]) if not c["learned_hop"] else None
    learn = [("record_learned_dependency", {
        "from_service_id": learned["from"], "to_service_id": learned["to"], "kind": "sync", "confidence": 0.8,
        "statement": f"{svc_name(learned['from'])} calls {svc_name(learned['to'])} at request time; "
                     "the service catalog does not list this dependency.",
        "sources": [{"node_id": learned["source_id"], "excerpt": learned["excerpt"]}]})] if learned else []
    if not v.called("update_incident"):
        return turn(v.turns, update(similar, learned), *learn, *[link(i) for i in similar])
    linked = {a["other_id"] for a, _ in v.all("link_similar")}
    extra = (learn if not v.called("record_learned_dependency") else []) + [link(i) for i in similar if i["id"] not in linked]
    if extra:
        return turn(v.turns, *extra)
    mem_rb = next((i["runbook"] for i in mem_incs if i.get("runbook")), None)
    if mem_rb:  # recall already returned the newest runbook's steps
        rb_src = {"id": mem_rb["id"], "text": "\n".join(mem_rb["steps"])}
    else:
        rb = next((r for i in similar for r in i.get("runbooks", [])), None)
        if rb and not v.last("read_source", node_id=rb):
            return turn(v.turns, ("read_source", {"node_id": rb}))
        rb_src = v.last("read_source", node_id=rb) if rb else None
    r = build_report(svc, c, None, who, dec, past)
    step = runbook_step(rb_src, similar, c["service"])
    facts = [x for _, x in v.all("record_learned_dependency")]
    memory = (c.get("learned_facts", []) if c["learned_hop"] else []) + [i["id"] for i in mem_incs]
    seen = seen_before(mem_incs[0], step) if mem_incs else None
    if c["learned_hop"] and c.get("learned_facts"):
        r["evidence"].insert(1, {"node_id": c["learned_facts"][0], "claim": f"{svc_name(svc)} and {svc_name(c['service'])} share "
                                                                           f"{svc_name(c['shared'] or svc)} only through a dependency learned in an earlier session."})
    if step:
        r["recommended_actions"].insert(1, f"Follow {step['runbook_id']} step {step['step']}: {step['text']}")
        r["recommended_actions"] = r["recommended_actions"][:4]
    cand = [{"id": x["id"], "name": x["name"], "score": x["score"]} for x in (who or {}).get("candidates", [])[:3]]
    note = ((f"From memory: {seen} " if seen else "")
            + f"Cause: {c['deploy']['id']} on {svc_name(c['service'])} ({c['deploy']['summary']}), path "
            + " -> ".join(map(svc_name, c["path"])) + (" via a LEARNED dependency." if c["learned_hop"] else ".")
            + (f" It contradicts {conf[0]['id']} ({conf[1]['id']})." if conf else "")
            + "".join(f" Learned: {f['edge']['from']} -> {f['edge']['to']} ({f['fact_id']})." for f in facts)
            + (" Seen before: " + "; ".join(f"{i['key']} fixed by {', '.join(i.get('resolved_by') or ['?'])}: {i.get('resolution')}"
                                           for i in similar) + "." if similar and not seen else "")
            + (f" Runbook {step['runbook_id']} step {step['step']}: {step['text']}" if step and not seen else "")
            + (f" Contact candidates: {', '.join(x['name'] for x in cand)}." if cand else ""))
    details = {k: r[k] for k in ("likely_cause", "conflicting_decision", "similar_past_incidents", "evidence",
                                 "recommended_actions", "confidence")}
    details.update(learned=[{"fact_id": f["fact_id"], **f["edge"]} for f in facts], memory_used=memory,
                   runbook_step=step, contact_candidates=cand, seen_before=seen)
    return turn(v.turns, ("submit_handoff", {"note": note, "details": details}))


# ───────────── communicator ─────────────
def _cause_service(st):
    for c in st.get("caused_by", []):
        if c["label"] == "Deploy" and c.get("service"):
            return c["service"]
    return next((c["id"] for c in st.get("caused_by", []) if c["label"] == "Service"), None)


def communicator(v):
    st, alert = _state(v), v.payload["alert"]
    svc, inc, key = alert["service_id"], st.get("id"), st.get("key")
    inv, tri = _handoff(st, "investigator"), _handoff(st, "triage")
    cause = _cause_service(st)
    if not v.called("who_to_call"):
        return turn(v.turns, ("who_to_call", {"service_id": cause or svc}),
                    *([("stale_knowledge", {"service_id": cause})] if cause else []),
                    *([("industry_matches", {"incident_id": inc})] if st.get("root_causes") else []))
    who, stale = v.last("who_to_call"), v.last("stale_knowledge") or {"items": []}
    contact, warn = contact_from(who)
    lc = inv.get("likely_cause") or {}
    cd = inv.get("conflicting_decision")
    if not v.called("page_person"):
        calls = []
        if contact:
            calls.append(("page_person", {"person_id": contact["person_id"], "incident_id": inc, "message":
                          f"{key} sev {st.get('severity')}: {alert['symptom']}. "
                          + (f"Likely cause {lc['deploy_id']} on {svc_name(lc['service_id'])}. " if lc.get("deploy_id") else "Cause unknown. ")
                          + f"You are the top active contact ({contact['reason']})."}))
        calls.append(("open_ticket", {"service_id": cause or svc, "incident_id": inc,
                      "title": f"{key} follow-up: {svc_name(cause or svc)}" + (f" change conflicts with {cd['decision_id']}" if cd else ""),
                      "text": (lc.get("explanation") or "Cause not yet known.") + (f" Conflicts with {cd['decision_id']}." if cd else "")
                              + " Actions: " + " ".join(inv.get("recommended_actions") or ["investigate further"])}))
        for it in stale["items"]:
            if not it.get("flagged"):
                calls.append(("flag_stale", {"node_id": it["id"], "reason": stale_reason(it)}))
        return turn(v.turns, *calls)
    taken = [x["summary"] for t in ("page_person", "open_ticket", "flag_stale") for _, x in v.all(t)]
    ticket = v.last("open_ticket") or {}
    learned = [f"{f['statement']} ({f['id']})" for f in st.get("facts", [])]
    learned += [f"used memory: {m}" for m in inv.get("memory_used", [])]
    sims = inv.get("similar_past_incidents") or []
    summary = (f"{key}: {svc_name(svc)} {alert['symptom'].split(' for ')[0]}. "
               + (f"Likely cause {lc['deploy_id']} on {svc_name(lc['service_id'])}." if lc.get("deploy_id") else "Cause unknown.")
               + (f" {inv['seen_before']}" if inv.get("seen_before") else
                  f" Seen before: {sims[0]['incident_id']}, fixed by {sims[0]['resolved_by']}." if sims else ""))
    report = {"summary": summary,
              "likely_cause": lc or {"service_id": None, "deploy_id": None, "ticket_key": None, "path": [], "explanation": "unknown"},
              "blast_radius": tri.get("blast_radius", []),
              "contact": contact or {"person_id": None, "name": None, "reason": "no candidate found"},
              "bus_factor_warning": warn, "conflicting_decision": cd, "similar_past_incidents": sims,
              "evidence": (inv.get("evidence") or [])[:6] or [{"node_id": svc, "claim": "alerting service"}],
              "recommended_actions": (inv.get("recommended_actions") or [])[:4], "confidence": inv.get("confidence", "low"),
              "industry_pattern": industry_line(v.last("industry_matches")),
              "actions_taken": taken, "learned": learned,
              "status_update": f"[{key}] sev {st.get('severity')}, {st.get('status')}: {svc_name(svc)} {alert['symptom']}. "
                               + (f"Likely cause: {lc['deploy_id']} on {svc_name(lc['service_id'])}"
                                  + (f" ({lc['ticket_key']})" if lc.get("ticket_key") else "") + ". " if lc.get("deploy_id") else "Cause still unknown. ")
                               + (f"{contact['name']} has been paged. " if contact else "")
                               + (f"Follow-up ticket {ticket['key']}. " if ticket.get("key") else "") + "Next update in 30 minutes."}
    while len(report["evidence"]) < 3:
        report["evidence"].append({"node_id": inc, "claim": "incident record"})
    return turn(v.turns, ("submit_report", report))


# ───────────── postmortem (operator resolved the incident) ─────────────
def postmortem(v):
    st, op = _state(v), v.payload["operator"]
    inc, key, what = st["id"], st.get("key"), op["what_fixed_it"]
    culprit = _cause_service(st)
    services = list(dict.fromkeys(([culprit] if culprit else []) + st.get("affected", [])))
    if not v.called("past_incidents"):
        return turn(v.turns, ("update_incident", {"incident_id": inc, "status": "mitigated",
                                                  "summary": f"{st.get('summary')} Resolution (operator): {what}"}),
                    ("past_incidents", {"service_ids": services[:10], "limit": 10}),
                    ("search_knowledge", {"query": " ".join(map(svc_name, services)), "labels": ["Runbook"], "limit": 5}),
                    *([("industry_matches", {"incident_id": inc})] if st.get("root_causes") else []))
    if not v.called("read_source"):
        hits = [h["id"] for h in (v.last("search_knowledge") or {}).get("hits", [])][:4]
        if hits:
            return turn(v.turns, *[("read_source", {"node_id": h}) for h in hits])
    if not v.called("record_resolution"):
        path = (_handoff(st, "investigator").get("likely_cause") or {}).get("path") or services
        order = list(dict.fromkeys(path[::-1] + services))  # nearest the culprit first
        rbs = [r for _, r in v.all("read_source") if r["label"] == "Runbook" and not r.get("superseded_by")
               and any(d in order for d in r.get("describes", []))]
        rb = min(rbs, key=lambda r: min(order.index(d) for d in r["describes"] if d in order)) if rbs else None
        rcs = [r["id"] for r in st.get("root_causes", [])]
        past = (v.last("past_incidents") or {}).get("incidents", [])
        linked = {x["id"] for x in st.get("similar", [])}
        same = [i for i in past if i["id"] != inc and i["status"] == "resolved" and set(i["root_causes"]) & set(rcs)
                and i["id"] not in linked]
        calls = [("record_resolution", {"incident_id": inc, "summary": what, "steps": [what],
                                        "performed_by_ids": op["resolved_by_ids"], "sources": [{"node_id": inc, "excerpt": what}]})]
        calls += [("link_similar", {"incident_id": inc, "other_id": i["id"], "score": 0.85,
                                    "reason": f"same root cause {', '.join(set(i['root_causes']) & set(rcs))}: {i['title']}"}) for i in same]
        # the best 1-2 public postmortems sharing a root cause (industry pattern)
        for m in [m for m in (v.last("industry_matches") or {}).get("matches", []) if "already_linked" not in m][:2]:
            calls.append(("link_similar", {"incident_id": inc, "other_id": m["id"],
                                           "score": round(min(0.9, 0.5 + 0.15 * len(m["shared_root_causes"]) + 0.05 * len(m["overlap_terms"])), 2),
                                           "reason": f"industry pattern {', '.join(m['shared_root_causes'])}: {m['company']} — {m['title']}"}))
        dep = next((c for c in st.get("caused_by", []) if c["label"] == "Deploy"), None)
        cname = svc_name(culprit) if culprit else "the service"
        conf_key = (CONFIG_KEY.findall(dep["summary"]) or ["configuration"])[0] if dep else "configuration"
        new = ([f"Check for a recent deploy to {cname} first: {key} was caused by {dep['id']} ({dep['summary']})."] if dep else []) \
            + [f"If {cname} {conf_key} was changed, roll it back. What fixed {key}: {what}"] \
            + [f"Watch {', '.join(svc_name(a) for a in f['about'] if a != culprit)} CPU and request rate: {f['statement']} ({f['id']})"
               for f in st.get("facts", []) if any(a != culprit for a in f["about"])]
        old = [re.sub(r"^\s*[0-9]+[.)]\s*", "", l) for l in (rb or {}).get("text", "").split("\n") if l.strip()]
        sources = [{"node_id": inc, "excerpt": what}] + [{"node_id": s["id"], "excerpt": s["excerpt"].rstrip("…")}
                                                         for f in st.get("facts", []) for s in f["sources"]]
        calls.append(("write_runbook", {"service_id": (rb["describes"][0] if rb else culprit or services[0]),
                                        "title": rb["title"] if rb else f"Runbook: {cname} incidents", "steps": new + old,
                                        "sources": sources, **({"supersedes_id": rb["id"]} if rb else {})}))
        return turn(v.turns, *calls)
    res, rbw = v.last("record_resolution") or {}, v.last("write_runbook") or {}
    links = [x["to"] for _, x in v.all("link_similar")]
    ind = industry_line(v.last("industry_matches"))
    note = (f"{key} resolved by {', '.join(op['resolved_by_ids'])}: {what}. Wrote {res.get('id')}"
            + (f", runbook {rbw['id']}" + (f" (supersedes {rbw['supersedes']})" if rbw.get("supersedes") else "") if rbw else "")
            + (f"; linked similar incidents {', '.join(links)}." if links else ".") + (f" {ind}" if ind else ""))
    return turn(v.turns, ("submit_handoff", {"note": note, "details": {
        "resolution_id": res.get("id"), "runbook_id": rbw.get("id"), "supersedes": rbw.get("supersedes"), "similar": links}}))


# ───────────── brain (Ask the Brain) ─────────────
_Q_STOP = {"why", "what", "who", "which", "how", "should", "must", "does", "did", "the", "and", "are", "about", "that",
           "this", "there", "now", "best", "knows", "know", "talk", "ask", "first", "read", "new", "i'm", "out", "date",
           "docs", "doc", "stay", "left", "seconds", "for", "with", "from", "into", "our", "any", "decide", "decided"}


def _qterms(q):
    return {w for w in re.split(r"[^a-z0-9_]+", q.lower()) if len(w) >= 3 and w not in _Q_STOP}


def key_terms(q):
    """Specific search terms: CONFIG_KEYS, hyphenated-service-names, Title Case Phrases; else content words."""
    keys = CONFIG_KEY.findall(q) + re.findall(r"\b[a-z0-9]+(?:-[a-z0-9]+)+\b", q.lower()) \
        + re.findall(r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)+\b", q)
    return keys or sorted(_qterms(q))


def best_quote(text, terms, key=None, speaker=False):
    """The source line/sentence sharing the most words with the question: always a literal substring.
    speaker=True keeps a chat line's "[time] Name:" prefix (and matches key against it), to quote WHO said it."""
    cands = []
    for raw in (text or "").split("\n"):
        line = raw.strip() if speaker else re.sub(r"^\[[^\]]*\] [^:]+: ", "", raw).strip()
        cands += [line] if len(line) <= 260 else re.split(r"(?<=[.!?])\s+", line)
    cands = [c.strip() for c in cands if len(c.strip()) >= 15 and not c.strip().startswith("#")]
    score = lambda c: len(_qterms(c) & terms) + (3 if key and key.lower() in c.lower() else 0)
    return max(cands, key=lambda c: (score(c), -len(c)), default=None)


def stale_reason(item):
    """'names_departed_person (Arjun Mehta); missing_learned_dependency (svc:config-service); ...'"""
    detail = {"names_departed_person": "departed_people", "missing_learned_dependency": "learned_dependencies",
              "author_left": None, "old_vs_changes": "deploys_since_update"}
    out = []
    for r in item["reasons"]:
        v = item.get(detail.get(r) or "")
        out.append(f"{r} ({', '.join(map(str, v)) if isinstance(v, list) else f'{v} deploys since'})" if v else r)
    return "; ".join(out)


def _intent(q):
    ql = q.lower()
    if re.search(r"\bses:", ql):
        return "session"
    if any(w in ql for w in ("out of date", "stale", "outdated")):
        return "stale"
    if any(w in ql for w in ("other compan", "industry", "anyone else", "public postmortem", "elsewhere")):
        return "industry"
    if re.search(r"what (breaks|happens|is affected|is hit)|blast radius|\bif\b.*\b(fails|goes down|is down|dies)\b", ql):
        return "blast"
    if re.search(r"\bseen\b.*\bbefore\b|happened before|has this happened|have we had", ql):
        return "seen"
    if "who" in ql.split() or ql.startswith("who"):
        return "who"
    if re.search(r"\bnew\b", ql) and any(w in ql for w in ("read", "start", "onboard")):
        return "onboarding"
    return "knowledge"


_IND_Q = {"other", "company", "companies", "industry", "anyone", "else", "had", "has", "have", "like", "ours", "outage",
          "outages", "incident", "incidents", "public", "postmortem", "postmortems", "pattern", "elsewhere", "similar"}
_SPECIFIC = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b|\b[a-z0-9]+(?:-[a-z0-9]+)+\b|\b[A-Z][a-z]+(?: [A-Z][a-z]+)+\b")
_HIST_ID = re.compile(r"\b(?:svc|dec|chat|doc|tkt|inc|rb|pm|fact):[A-Za-z0-9._-]+")


def _svc(v, q):
    """The service a question is about: a hyphenated name, else any word that find_service resolves.
    -> ("call", turn) | ("svc", id or None)"""
    toks = re.findall(r"\b[a-z0-9]+(?:-[a-z0-9]+)+\b", q.lower()) or sorted(_qterms(q))[:4]
    if not toks:
        return "svc", None
    if not v.called("find_service"):
        return "call", turn(v.turns, *[("find_service", {"query": t}) for t in toks])
    for inp, res in v.all("find_service"):
        m = [x for x in res.get("matches", []) if x["name"] == inp["query"] or x["name"].startswith(inp["query"])]
        if m:
            return "svc", m[0]["id"]
    return "svc", None


def _dont_know(keys):
    return ("I don't know: nothing in this company's graph answers that" + (f" (searched for {', '.join(keys)})." if keys else "."))


def brain(v):
    q = v.payload["question"]
    intent, terms, keys = _intent(q), _qterms(q), key_terms(q)
    # follow-ups ("about that", "about it"): the subject comes from the conversation history, read back from the graph
    hist = [i for h in v.history for i in _HIST_ID.findall(h)]
    answer, cites, people, warnings = None, [], [], []
    svc = None
    if intent in ("who", "blast", "seen"):
        kind, x = _svc(v, q)
        if kind == "call":
            return x
        svc = x
    if not svc and intent == "who":
        svc = next((i for i in hist if i.startswith("svc:")), None)
        if not svc and hist:
            src = v.last("read_source", node_id=hist[0])
            if src is None:
                return turn(v.turns, ("read_source", {"node_id": hist[0]}))
            svc = next((i for i in src.get("about", []) + src.get("describes", []) + src.get("mentions", [])
                        if i.startswith("svc:")), None)
    if intent == "who" and svc:
        if not v.called("who_to_call"):
            return turn(v.turns, ("who_to_call", {"service_id": svc}))
        who = v.last("who_to_call")
        contact, warn = contact_from(who)
        if contact and not v.called("search_knowledge"):
            return turn(v.turns, ("search_knowledge", {"query": f"{contact['name']} {svc_name(svc)}", "limit": 3}))
        hits = (v.last("search_knowledge") or {}).get("hits", [])
        if hits and not v.last("read_source", node_id=hits[0]["id"]):
            return turn(v.turns, ("read_source", {"node_id": hits[0]["id"]}))
        if contact:
            people = [contact["person_id"]] + [c["id"] for c in who["candidates"][1:2]]
            src = v.last("read_source", node_id=hits[0]["id"]) if hits else None
            quote = best_quote(src["text"], _qterms(svc_name(svc)), contact["name"], speaker=True) if src else None
            if quote:
                cites.append({"node_id": src["id"], "excerpt": quote})
            team = who.get("owning_team_fallback")
            answer = (f"Talk to {contact['name']} ({contact['person_id']}) about {svc_name(svc)}: {contact['reason']}."
                      + (f" {svc_name(svc)} is owned by {team['name']} ({team['id']})." if team else "")
                      + (f" {warn}" if warn else "") + (f" They took part in {src['id']}." if quote else ""))
    elif intent == "blast" and svc:
        if not v.called("blast_radius"):
            return turn(v.turns, ("blast_radius", {"service_id": svc}),
                        ("search_knowledge", {"query": svc_name(svc), "labels": ["Doc", "Incident"], "limit": 3}))
        blast, hits = v.last("blast_radius"), (v.last("search_knowledge") or {}).get("hits", [])
        if hits and not v.last("read_source", node_id=hits[0]["id"]):
            return turn(v.turns, ("read_source", {"node_id": hits[0]["id"]}))
        src = v.last("read_source", node_id=hits[0]["id"]) if hits else None
        if src and (quote := best_quote(src["text"], _qterms(svc_name(svc)), svc_name(svc))):
            cites.append({"node_id": src["id"], "excerpt": quote})
        t1 = [svc_name(u["id"]) for u in blast["upstream"] if u["tier"] == 1]
        rest = [svc_name(u["id"]) for u in blast["upstream"] if u["tier"] != 1]
        answer = (f"If {svc_name(svc)} ({svc}) fails, {blast['upstream_count']} services that call it are exposed, "
                  f"{blast['tier1_count']} of them tier-1: {', '.join(t1) or 'none'}."
                  + (f" Also: {', '.join(rest[:6])}." if rest else "")
                  + (" Some paths use a dependency learned by an agent." if blast.get("learned_edges_in_paths") else "")
                  + (f" Context: {src['id']}." if cites else ""))
    elif intent == "seen" and svc:
        if not v.called("past_incidents"):
            return turn(v.turns, ("past_incidents", {"service_ids": [svc]}))
        incs = [i for i in v.last("past_incidents").get("incidents", []) if i.get("status") == "resolved"][:2]
        unread = [i["id"] for i in incs if not v.last("read_source", node_id=i["id"])]
        if unread:
            return turn(v.turns, *[("read_source", {"node_id": i}) for i in unread])
        for i in incs:
            if quote := best_quote(v.last("read_source", node_id=i["id"])["text"], _qterms(svc_name(svc)), svc_name(svc)):
                cites.append({"node_id": i["id"], "excerpt": quote})
        if incs:
            answer = (f"Yes, {svc_name(svc)} ({svc}) has been hit before: " + "; ".join(
                f"{i['key']} \"{i['title']}\" ({i['id']}, {i['started']}), fixed by {', '.join(i.get('resolved_by') or ['?'])}: "
                f"{i.get('resolution')}" for i in incs) + ".")
    elif intent == "session":
        sid = re.search(r"ses:[A-Za-z0-9._-]+", q).group(0)
        if not v.called("node_details"):
            return turn(v.turns, ("node_details", {"node_id": sid}))
        nd = v.last("node_details", node_id=sid)
        if nd:
            written = [n for n in nd["neighbours"] if n["edge"] == "WRITTEN_IN" and n["dir"] == "in"]
            facts = [n["id"] for n in written if n["id"].startswith("fact:")]
            unread = [f for f in facts if not v.last("node_details", node_id=f)]
            if unread:
                return turn(v.turns, *[("node_details", {"node_id": f}) for f in unread])
            learned = []
            for f in facts:
                stmt = v.last("node_details", node_id=f)["props"].get("statement", "")
                if quote := best_quote(stmt, terms):
                    cites.append({"node_id": f, "excerpt": quote})
                    learned.append(f"\"{quote}\" ({f})")
            inc = next((n["id"] for n in nd["neighbours"] if n["edge"] == "FOR_INCIDENT"), None)
            other = [n["id"] for n in written if not n["id"].startswith("fact:")]
            if learned:
                answer = (f"Session {sid}" + (f" (incident {inc})" if inc else "") + " learned: " + "; ".join(learned) + "."
                          + (f" It also wrote {', '.join(other)}." if other else ""))
    elif intent == "industry":
        words = sorted(terms - _IND_Q)
        if not words:
            answer = None
        elif not v.called("search_knowledge"):
            return turn(v.turns, ("search_knowledge", {"query": " ".join(words), "labels": ["RootCause"], "limit": 3}))
        else:
            hits = [h for h in v.last("search_knowledge").get("hits", []) if h["score"] >= 1.0]
            if hits and not v.called("industry_matches"):
                return turn(v.turns, ("industry_matches", {"root_cause_id": hits[0]["id"], "limit": 3}))
            ms = (v.last("industry_matches") or {}).get("matches", [])[:2]
            for m in ms:
                if quote := best_quote(m["summary"].rstrip("…"), terms | set(m["overlap_terms"])):
                    cites.append({"node_id": m["id"], "excerpt": quote})
            if ms:
                answer = (f"Yes. Our pattern \"{hits[0]['title']}\" ({hits[0]['id']}) matches public postmortems: "
                          + "; ".join(f"{m['company']}: {m['title']} ({m['url']}, {m['id']})" for m in ms) + ".")
    elif intent == "stale":
        if not v.called("stale_knowledge"):
            return turn(v.turns, ("stale_knowledge", {"service_id": svc}))
        items = v.last("stale_knowledge")["items"][:3]
        unread = [i["id"] for i in items if not v.last("read_source", node_id=i["id"])]
        if unread:
            return turn(v.turns, *[("read_source", {"node_id": i}) for i in unread],
                        *[("flag_stale", {"node_id": i["id"], "reason": stale_reason(i)}) for i in items if not i.get("flagged")])
        parts = []
        for it in items:
            why = stale_reason(it)
            warnings.append({"node_id": it["id"], "reason": why})
            src = v.last("read_source", node_id=it["id"])
            gone = (it.get("departed_people") or [None])[0]
            if quote := best_quote(src["text"], terms | _qterms(gone or ""), gone):
                cites.append({"node_id": it["id"], "excerpt": quote})
            parts.append(f"{it['title']} ({it['id']}, updated {it['updated_days_ago']} days ago): {why}")
        answer = ("Out of date: " + "; ".join(parts) + ".") if parts else None
    elif intent in ("knowledge", "onboarding"):
        subject = None
        if hist and not _SPECIFIC.search(q):  # "why did we decide that?": the subject is what we cited before
            subject = next((i for i in hist if i.startswith("dec:")), None) or next(
                (i for i in hist if i.split(":")[0] in ("chat", "doc", "tkt", "rb", "inc")), None)
        if subject:
            pick = [{"id": subject, "label": "Decision" if subject.startswith("dec:") else "Source"}]
        else:
            if not v.called("search_knowledge"):
                return turn(v.turns, ("search_knowledge", {"query": " ".join(keys), "limit": 6}))
            # only sources matching ALL the specific terms count; a weak any-word hit is not an answer
            first = [h for h in v.last("search_knowledge")["hits"] if h["score"] >= 1.0]
            pick = ([h for h in first if h["label"] == "Decision"][:1] + [h for h in first if h["label"] in ("ChatThread", "Doc")][:1]
                    if intent == "knowledge" else [h for h in first if h["label"] == "Doc"][:1]) or first[:2]
        unread = [h["id"] for h in pick if not v.last("read_source", node_id=h["id"])]
        if unread:
            return turn(v.turns, *[("read_source", {"node_id": i}) for i in unread])
        srcs = [v.last("read_source", node_id=h["id"]) for h in pick]
        if intent == "onboarding" and srcs:
            mentioned = [m for m in srcs[0].get("mentions", []) if m.startswith("svc:")][:3]
            if mentioned and not v.called("decisions_about"):
                return turn(v.turns, *[("decisions_about", {"service_id": m}) for m in mentioned])
            decs = [d for _, r in v.all("decisions_about") for d in r.get("decisions", [])][:2]
            people = [m for m in srcs[0].get("mentions", []) if m.startswith("per:")][:2]
            quote = best_quote(srcs[0]["text"], terms)
            cites = ([{"node_id": srcs[0]["id"], "excerpt": quote}] if quote else []) + [
                {"node_id": d["id"], "excerpt": d["title"]} for d in decs]
            answer = (f"Start with the {srcs[0]['title']} ({srcs[0]['id']}). "
                      + ("Then the decisions behind the services you'll own: " + "; ".join(f"{d['title']} ({d['id']})" for d in decs) + "." if decs else "")
                      + (f" Ask {', '.join(people)} when stuck." if people else ""))
        elif srcs:
            for s_ in srcs:
                if quote := best_quote(s_["text"], terms, keys[0] if keys and not subject else None):
                    cites.append({"node_id": s_["id"], "excerpt": quote})
            lead = srcs[0]
            by = "decided by" if lead["label"] == "Decision" else "by"
            answer = (f"{lead['title']} ({lead['id']}"
                      + (f", {by} {lead['author']}" + (" who has since left" if lead.get("author_status") == "left" else "") if lead.get("author") else "")
                      + f"): {' '.join(re.split(r'(?<=[.!?])\s+', lead['text'])[:2])}"
                      + "".join(f" Source {c['node_id']}: \"{c['excerpt']}\"" for c in cites[1:2]))
    if not answer or not cites:
        answer, cites, people, warnings = _dont_know(keys), [], [], []
    words = answer.split()
    answer = " ".join(words[:150])
    return turn(v.turns, ("submit_answer", {"answer": answer, "citations": cites, "people": people, "stale_warnings": warnings}))


POLICIES = {"firefighter": firefighter, "brain": brain, "triage": triage, "investigator": investigator, "communicator": communicator,
            "postmortem": postmortem}


def respond(agent, system, tools, messages):
    return POLICIES[agent](View(messages))
