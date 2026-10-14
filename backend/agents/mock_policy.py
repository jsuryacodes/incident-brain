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
        cause = {"service_id": culprit["service"], "deploy_id": d["id"], "ticket_key": tkey, "path": culprit["path"],
                 "explanation": f"{d['summary']} ({d['id']}, deployed {d['minutes_ago']} min ago by {d['by']}). "
                                f"{svc_name(alert_svc)} reaches {svc_name(culprit['service'])} via {hop}: "
                                + " -> ".join(map(svc_name, culprit["path"])) + "."}
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


POLICIES = {"firefighter": firefighter}


def respond(agent, system, tools, messages):
    return POLICIES[agent](View(messages))
