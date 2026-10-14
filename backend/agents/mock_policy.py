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
        self.payload, self.calls, self.turns = {}, [], 0
        pending = {}
        for m in messages:
            c = m["content"]
            if m["role"] == "assistant":
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
def culprit_from(recent, shared):
    """First downstream hit (nearest), else first noisy neighbour. -> dict or None."""
    if recent and recent.get("hits"):
        h = recent["hits"][0]
        return {"service": h["service"], "deploy": h["deploy"], "ticket": h.get("ticket"), "path": h["path"],
                "learned_hop": "learned" in h.get("edge_sources", []), "shared": None}
    if shared and shared.get("hits"):
        h = shared["hits"][0]
        path = h["path_to_shared"] + h["neighbour_path"][::-1][1:]  # alerting -> shared -> neighbour
        return {"service": h["neighbour"], "deploy": h["deploy"], "ticket": h.get("ticket"), "path": path,
                "learned_hop": h.get("uses_learned_edge", False), "shared": h["shared"],
                "learned_facts": h.get("learned_facts", [])}
    return None


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


def build_report(alert_svc, culprit, blast, who, decisions, past):
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
            "confidence": ["low", "low", "medium", "high"][score]}


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
    recent = v.last("recent_changes_downstream")
    if recent is None:
        return turn(v.turns, ("recent_changes_downstream", {"service_id": svc, "since_minutes": 120}))
    shared = v.last("shared_dependency_changes")
    if not recent["hits"] and shared is None:
        return turn(v.turns, ("shared_dependency_changes", {"service_id": svc, "since_minutes": 120}))
    culprit = culprit_from(recent, shared)
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
    report = build_report(svc, culprit, v.last("blast_radius"), v.last("who_to_call"), v.last("decisions_about"),
                          v.last("past_incidents"))
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
def investigator(v):
    st, alert = _state(v), v.payload["alert"]
    svc, inc = alert["service_id"], _state(v).get("id")
    recent, shared = v.last("recent_changes_downstream"), v.last("shared_dependency_changes")
    if recent is None:
        return turn(v.turns, ("recent_changes_downstream", {"service_id": svc, "since_minutes": 120}),
                    ("shared_dependency_changes", {"service_id": svc, "since_minutes": 120}))
    c = culprit_from(recent, shared)
    if c is None:
        if not v.called("past_incidents"):
            return turn(v.turns, ("past_incidents", {"service_ids": [svc]}))
        note = (f"No service downstream of {svc_name(svc)}, or sharing a dependency with it, changed in the last 120 min. "
                "Cause unknown; confidence low. Not setting a cause.")
        return turn(v.turns, ("submit_handoff", {"note": note, "details": {
            "likely_cause": None, "conflicting_decision": None, "similar_past_incidents": [], "confidence": "low",
            "evidence": [{"node_id": svc, "claim": "no recent downstream or shared-dependency change in 120 min"}]}}))
    if not v.called("decisions_about"):
        ids = [svc, c["service"]] + ([c["shared"]] if c["shared"] else [])
        return turn(v.turns, ("decisions_about", {"service_id": c["service"]}),
                    ("past_incidents", {"service_ids": ids, "limit": 10}), ("who_to_call", {"service_id": c["service"]}))
    dec, past, who = v.last("decisions_about"), v.last("past_incidents"), v.last("who_to_call")
    conf = conflict_from(c, dec)
    # a learned hop means an earlier session already read that source and recorded what it says
    if conf and not c["learned_hop"] and not v.called("read_source"):
        return turn(v.turns, ("read_source", {"node_id": conf[1]["id"]}))
    similar = recalled(c, past)
    learned = learn_from_source(v.last("read_source"), c["service"]) if not c["learned_hop"] else None
    if not v.called("update_incident"):
        upd = {"incident_id": inc, "cause_deploy_id": c["deploy"]["id"], "cause_service_id": c["service"],
               "affected_ids": list(dict.fromkeys(c["path"][1:] + ([learned["to"]] if learned else [])))}
        if rc := next((r for i in similar for r in i.get("root_causes", [])), None):
            upd["root_cause_id"] = rc
        calls = [("update_incident", upd)]
        if learned:
            calls.append(("record_learned_dependency", {
                "from_service_id": learned["from"], "to_service_id": learned["to"], "kind": "sync", "confidence": 0.8,
                "statement": f"{svc_name(learned['from'])} calls {svc_name(learned['to'])} at request time; "
                             "the service catalog does not list this dependency.",
                "sources": [{"node_id": learned["source_id"], "excerpt": learned["excerpt"]}]}))
        for i in similar:
            calls.append(("link_similar", {"incident_id": inc, "other_id": i["id"], "score": 0.9 if i.get("origin") == "agent" else 0.8,
                                           "reason": f"also caused by a change to {svc_name(c['service'])}: {i['title']}"}))
        return turn(v.turns, *calls)
    rb = next((r for i in similar for r in i.get("runbooks", [])), None)
    if rb and not v.last("read_source", node_id=rb):
        return turn(v.turns, ("read_source", {"node_id": rb}))
    r = build_report(svc, c, None, who, dec, past)
    step = runbook_step(v.last("read_source", node_id=rb), similar, c["service"]) if rb else None
    facts = [x for _, x in v.all("record_learned_dependency")]
    memory = c.get("learned_facts", []) if c["learned_hop"] else []
    if memory:
        r["evidence"].insert(1, {"node_id": memory[0], "claim": f"{svc_name(svc)} and {svc_name(c['service'])} share "
                                                                 f"{svc_name(c['shared'] or svc)} only through a dependency learned in an earlier session."})
    if step:
        r["recommended_actions"].insert(1, f"Follow {step['runbook_id']} step {step['step']}: {step['text']}")
        r["recommended_actions"] = r["recommended_actions"][:4]
    cand = [{"id": x["id"], "name": x["name"], "score": x["score"]} for x in (who or {}).get("candidates", [])[:3]]
    note = (f"Cause: {c['deploy']['id']} on {svc_name(c['service'])} ({c['deploy']['summary']}), path "
            + " -> ".join(map(svc_name, c["path"])) + (" via a LEARNED dependency." if c["learned_hop"] else ".")
            + (f" It contradicts {conf[0]['id']} ({conf[1]['id']})." if conf else "")
            + "".join(f" Learned: {f['edge']['from']} -> {f['edge']['to']} ({f['fact_id']})." for f in facts)
            + (" Seen before: " + "; ".join(f"{i['key']} fixed by {', '.join(i.get('resolved_by') or ['?'])}: {i.get('resolution')}"
                                           for i in similar) + "." if similar else "")
            + (f" Runbook {step['runbook_id']} step {step['step']}: {step['text']}" if step else "")
            + (f" Contact candidates: {', '.join(x['name'] for x in cand)}." if cand else ""))
    details = {k: r[k] for k in ("likely_cause", "conflicting_decision", "similar_past_incidents", "evidence",
                                 "recommended_actions", "confidence")}
    details.update(learned=[{"fact_id": f["fact_id"], **f["edge"]} for f in facts], memory_used=memory,
                   runbook_step=step, contact_candidates=cand)
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
                    *([("stale_knowledge", {"service_id": cause})] if cause else []))
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
                detail = [f"{r} ({', '.join(map(str, it[k]))})" if k and k in it else r for r, k in
                          ((r, {"names_departed_person": "departed_people", "missing_learned_dependency": "learned_dependencies"}.get(r))
                           for r in it["reasons"])]
                calls.append(("flag_stale", {"node_id": it["id"], "reason": "; ".join(detail)}))
        return turn(v.turns, *calls)
    taken = [x["summary"] for t in ("page_person", "open_ticket", "flag_stale") for _, x in v.all(t)]
    ticket = v.last("open_ticket") or {}
    learned = [f"{f['statement']} ({f['id']})" for f in st.get("facts", [])]
    learned += [f"used memory: {m}" for m in inv.get("memory_used", [])]
    sims = inv.get("similar_past_incidents") or []
    summary = (f"{key}: {svc_name(svc)} {alert['symptom'].split(' for ')[0]}. "
               + (f"Likely cause {lc['deploy_id']} on {svc_name(lc['service_id'])}." if lc.get("deploy_id") else "Cause unknown.")
               + (f" Seen before: {sims[0]['incident_id']}, fixed by {sims[0]['resolved_by']}." if sims else ""))
    report = {"summary": summary,
              "likely_cause": lc or {"service_id": None, "deploy_id": None, "ticket_key": None, "path": [], "explanation": "unknown"},
              "blast_radius": tri.get("blast_radius", []),
              "contact": contact or {"person_id": None, "name": None, "reason": "no candidate found"},
              "bus_factor_warning": warn, "conflicting_decision": cd, "similar_past_incidents": sims,
              "evidence": (inv.get("evidence") or [])[:6] or [{"node_id": svc, "claim": "alerting service"}],
              "recommended_actions": (inv.get("recommended_actions") or [])[:4], "confidence": inv.get("confidence", "low"),
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
                    ("search_knowledge", {"query": " ".join(map(svc_name, services)), "labels": ["Runbook"], "limit": 5}))
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
    note = (f"{key} resolved by {', '.join(op['resolved_by_ids'])}: {what}. Wrote {res.get('id')}"
            + (f", runbook {rbw['id']}" + (f" (supersedes {rbw['supersedes']})" if rbw.get("supersedes") else "") if rbw else "")
            + (f"; linked similar incidents {', '.join(links)}." if links else "."))
    return turn(v.turns, ("submit_handoff", {"note": note, "details": {
        "resolution_id": res.get("id"), "runbook_id": rbw.get("id"), "supersedes": rbw.get("supersedes"), "similar": links}}))


POLICIES = {"firefighter": firefighter, "triage": triage, "investigator": investigator, "communicator": communicator,
            "postmortem": postmortem}


def respond(agent, system, tools, messages):
    return POLICIES[agent](View(messages))
