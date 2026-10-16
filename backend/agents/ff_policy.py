"""The Firefighter's planner in mock mode: a deterministic stand-in for the LLM (no API, no cost).

One or several alerts -> every recent change in the company is a lead -> the dependency graph confirms or rejects each
lead -> one incident per cause -> who to page, blast radius, decisions, history -> report. Generic: every service,
deploy and person comes from tool results; nothing here knows a story.

It only uses the tools it was given (View.tools), which is how the eval baselines stay honest with the SAME planner:
  no traversal tools  -> "no graph": pick the change whose words best match the alert, path unknown, confidence low
  no algorithm tools  -> no PageRank pointer when nothing changed
Rules (also in prompts/firefighter.md):
  - a change to the alerting service or anything it calls (downstream) is a candidate; nearest first
  - a change to a service that only SHARES a dependency (a noisy neighbour) is a candidate, except when the shared
    service is a hub (HUB_CALLERS or more services call it, directly or not) and nothing corroborates it: a learned edge on the path, the
    shared service is itself alerting, or the alert text names it. Everyone calls a hub; that alone is noise.
  - several alerts: a change that explains more alerts wins (one cause beats several), then direct before neighbour,
    then fewer hops, then the newest
  - nothing changed: say so, and point at the most depended-on service on the call path (PageRank), never a cause
  - page the top ACTIVE person; if nobody active has worked on the service, escalate to the owning team
"""
import re

from backend.agents.mock_policy import conflict_from, contact_from, industry_line, recalled, svc_name, turn

SCAN = 120  # minutes
DEPTH = 6  # the deepest DEPENDS_ON scan the tools allow
CHANGE_LIMIT = 30
HUB_CALLERS = 4  # ponytail: fixed threshold for "a hub"; a relative one (share of all services) if companies differ a lot


def _calls_needed(v, calls):
    made = {(n, repr(sorted(i.items()))) for n, i, _, _ in v.calls}
    out, seen = [], set()
    for name, args in calls:
        k = (name, repr(sorted(args.items())))
        if name in v.tools and k not in made and k not in seen:
            seen.add(k)
            out.append((name, args))
    return out


def _words(text):
    return {w for w in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(w) >= 4}


def _mentions(symptom, sid):
    """Does the alert text name this service, as a whole word ('orders-db' or 'orders db')?"""
    name, s = svc_name(sid).lower(), (symptom or "").lower()
    return any(re.search(rf"(?<![a-z0-9-]){re.escape(n)}(?![a-z0-9-])", s) for n in {name, name.replace("-", " ")})


def _hops(n):
    return f"{n} hop{'s' * (n != 1)}"


# ───────────── leads: every recent change, checked against the graph ─────────────
def candidates(v, alerts):
    """-> (alert service -> [candidate], weak neighbours {deploy: (alert, candidate)}, cut-short scans {alert})."""
    alerting = {a["service_id"] for a in alerts}
    cands, weak, cut = {}, {}, set()
    for a in alerts:
        s = a["service_id"]
        out = []
        down = v.last("recent_changes_downstream", service_id=s, since_minutes=SCAN, max_hops=DEPTH) or {}
        shared = v.last("shared_dependency_changes", service_id=s, since_minutes=SCAN) or {}
        if down.get("truncated") or shared.get("truncated"):
            cut.add(s)
        for h in down.get("hits", []):
            out.append({"deploy": h["deploy"], "service": h["service"], "ticket": h.get("ticket"), "path": h["path"],
                        "hops": h["hops"], "kind": "downstream", "shared": None,
                        "learned_hop": "learned" in h.get("edge_sources", [])})
        for h in shared.get("hits", []):
            path = h["path_to_shared"] + h["neighbour_path"][::-1][1:]  # alert -> shared -> neighbour
            all_shared = dict(zip([h["shared"]] + h.get("also_shares", []),
                                  [h.get("shared_callers") or 0] + h.get("also_shares_callers", [])))
            narrow = min(all_shared, key=lambda x: (all_shared[x], x))
            c = {"deploy": h["deploy"], "service": h["neighbour"], "ticket": h.get("ticket"), "path": path,
                 "hops": len(path) - 1, "kind": "neighbour", "shared": h["shared"], "all_shared": all_shared,
                 "learned_hop": h.get("uses_learned_edge", False), "learned_facts": h.get("learned_facts", [])}
            named = next((x for x in all_shared if _mentions(a.get("symptom"), x)), None)
            why = ("a learned dependency" if c["learned_hop"] else
                   f"{svc_name(next(x for x in all_shared if x in alerting))} is alerting too" if alerting & set(all_shared) else
                   f"the alert names {svc_name(named)}" if named else
                   f"{svc_name(narrow)} is a narrow dependency ({all_shared[narrow]} services call it)"
                   if all_shared[narrow] < HUB_CALLERS else None)
            if why:
                c["corroborated_by"] = why
                out.append(c)
            else:
                weak.setdefault(h["deploy"]["id"], (s, c))
        cands[s] = out
    return cands, weak, cut


def _key(mine, covered):
    return (-len(covered), sum(c["kind"] != "downstream" for c in mine), sum(c["hops"] for c in mine),
            min(c["deploy"]["minutes_ago"] for c in mine))


def group(alerts, cands):
    """Greedy: the change explaining the most still-unexplained alerts first. -> [{alerts, cause or None}]"""
    left, incidents = [a["service_id"] for a in alerts], []
    while left:
        best = None
        for d in sorted({c["deploy"]["id"] for s in left for c in cands[s]}):
            covered = [s for s in left if any(c["deploy"]["id"] == d for c in cands[s])]
            mine = [next(c for c in cands[s] if c["deploy"]["id"] == d) for s in covered]
            if best is None or _key(mine, covered) < best[0]:
                best = (_key(mine, covered), covered, mine[0])
        if best is None:
            incidents += [{"alerts": [s], "cause": None} for s in left]
            break
        incidents.append({"alerts": best[1], "cause": best[2]})
        left = [s for s in left if s not in best[1]]
    return incidents


def _where(c, s):
    if c["kind"] == "downstream":
        return "is the alerting service itself" if c["hops"] == 0 else f"is on {svc_name(s)}'s call path ({_hops(c['hops'])})"
    return f"is not called by {svc_name(s)} but shares {_shares(c)} with it ({c.get('corroborated_by')})"


def _shares(c):
    return ", ".join(f"{svc_name(x)} ({n} callers)" for x, n in sorted(c["all_shared"].items(), key=lambda kv: -kv[1]))


def _why_lost(c, s, inc, cands):
    """The reason from the comparison group() actually made, over the incident's alerts: alerts explained, then how many
    of them only as a neighbour, then total hops, then recency."""
    w, d = inc["cause"], c["deploy"]["id"]
    covered = [x for x in inc["alerts"] if any(k["deploy"]["id"] == d for k in cands.get(x, []))]
    mine = [next(k for k in cands[x] if k["deploy"]["id"] == d) for x in covered]
    wins = [next(k for k in cands[x] if k["deploy"]["id"] == w["deploy"]["id"]) for x in inc["alerts"]]
    lk, wk = _key(mine, covered), _key(wins, inc["alerts"])
    n = len(inc["alerts"])
    if lk[0] != wk[0]:
        return f"{svc_name(w['service'])} explains {n} alert{'s' * (n > 1)}, this change {len(covered)}"
    if lk[1] != wk[1]:
        return (f"{svc_name(w['service'])} is on the call path of {'every alert' if n > 1 else svc_name(s)}"
                f"{'' if not wk[1] else f' ({n - wk[1]} of {n})'}; this change only shares a dependency with "
                f"{lk[1]} of them" if n > 1 else f"{svc_name(w['service'])} changed on {svc_name(s)}'s own call path, "
                "a more direct explanation")
    if lk[2] != wk[2]:
        return f"{svc_name(w['service'])} is nearer ({_hops(wk[2])} in total vs {lk[2]})"
    if lk[3] != wk[3]:
        return (f"{svc_name(w['service'])} is just as close and changed more recently ({wk[3]} vs {lk[3]} min ago), "
                "so it was checked first; this one stays possible")
    return f"{svc_name(w['service'])} is just as close and just as recent; it was picked first by name, this one stays possible"


def rejected_leads(changes, incidents, cands, weak, cut, tools=frozenset({"recent_changes_downstream", "shared_dependency_changes"})):
    """Every recent change that is not a cause, with the graph's reason."""
    causes = {i["cause"]["deploy"]["id"] for i in incidents if i["cause"]}
    out = []
    for ch in changes or []:
        d, svc = ch["deploy"]["id"], ch["service"]
        if d in causes:
            continue
        hit = next(((s, c) for s, cs in cands.items() for c in cs if c["deploy"]["id"] == d), None)
        if hit:
            s, c = hit
            inc = next(i for i in incidents if s in i["alerts"])
            reason = (f"{svc_name(svc)} {_where(c, s)}, but " + _why_lost(c, s, inc, cands)) if inc["cause"] else \
                f"{svc_name(svc)} {_where(c, s)}"
        elif d in weak:
            s, c = weak[d]
            reason = (f"{svc_name(svc)} is not called by {svc_name(s)}; it only shares hubs with it ({_shares(c)}; "
                      f"{HUB_CALLERS}+ services calling it, directly or not, counts as a hub) and nothing corroborates it (no learned edge, none of "
                      "them is alerting, the alert does not name them)")
        elif cut:
            reason = (f"not checked: the dependency scan of {', '.join(map(svc_name, sorted(cut)))} was cut short, so "
                      f"{svc_name(svc)} may or may not be on its path")
        else:
            reason = (f"{svc_name(svc)} is not on the call path of any alerting service (within {DEPTH} hops)"
                      + (" and shares no dependency with them (within 3 hops each side)" if "shared_dependency_changes" in tools
                         else "; shared dependencies were not checked (no shared-dependency scan)"))
        out.append({"deploy_id": d, "service_id": svc, "reason": reason})
    return out


# ───────────── report pieces ─────────────
def contact_or_team(who):
    contact, warn = contact_from(who)
    if contact or not who:
        return contact, warn
    team = who.get("owning_team_fallback")
    left = [m["name"] for m in who.get("maintainers", []) if m["status"] == "left"]
    if not team:
        return None, warn
    contact = {"person_id": None, "name": None, "team_id": team["id"],
               "reason": f"no active person has worked on {svc_name(who['service'])}; escalate to the owning team "
                         f"{team['name']} ({team['id']})"}
    warn = (f"maintainer {', '.join(left)} has left" if left else "no maintainer") + \
        f" and no active person has worked on {svc_name(who['service'])}. Do not page {', '.join(left) or 'anyone'}" \
        f"; escalate to {team['name']}."
    return contact, warn


def look_first_from(crit, alert_svcs):
    svcs = [s for s in (crit or {}).get("services", []) if s["id"] not in alert_svcs]
    if not svcs:
        return None
    top = [s for s in svcs if s["score"] >= 0.95 * svcs[0]["score"]][:3]
    return {"service_ids": [s["id"] for s in top], "algorithm": crit["algorithm"],
            "reason": f"No recent change explains the alert. {' and '.join(svc_name(s['id']) for s in top)} "
                      f"{'are' if len(top) > 1 else 'is'} the most depended-on service{'s' * (len(top) > 1)} on the call path "
                      f"({crit['algorithm']} {svcs[0]['score']}): check {'their' if len(top) > 1 else 'its'} capacity first."}


def incident_report(alerts, inc, who, blast, dec, past, crit, text_only=False, extra=None, contact=None):
    """One incident: cause (or none), contact, actions. Built only from tool results. contact: given directly (the
    no-graph path builds it from the change log / catalog) instead of from who_to_call."""
    a0 = inc["alerts"][0]
    c = inc["cause"]
    contact, warn = (dict(contact), None) if contact else contact_or_team(who)
    actions, evidence = [], []
    look = None
    if c:
        d = c["deploy"]
        tkey = (c.get("ticket") or {}).get("key")
        if text_only:
            how = "chosen from the change log by matching words with the alert (no dependency data)"
        elif len(c["path"]) == 1:
            how = f"{svc_name(a0)} itself was changed"
        elif c["kind"] == "neighbour":
            how = (f"{svc_name(a0)} and {svc_name(c['service'])} both call {svc_name(c['shared'])} (corroborated by "
                   f"{c.get('corroborated_by')})")
        else:
            how = f"{svc_name(a0)} calls {svc_name(c['service'])} via " + (
                "a learned dependency" if c["learned_hop"] else "declared dependencies")
        cause = {"service_id": c["service"], "deploy_id": d["id"], "ticket_key": tkey, "path": c["path"],
                 "explanation": f"{d['summary']} ({d['id']}, deployed {d['minutes_ago']} min ago"
                                + (f" by {d['by']}" if d.get("by") else "") + f"). {how}"
                                + (": " + " -> ".join(map(svc_name, c["path"])) if len(c["path"]) > 1 else "") + "."}
        evidence.append({"node_id": d["id"], "claim": f"{svc_name(c['service'])} deployed {d['minutes_ago']} min ago: {d['summary']}"})
        actions.append(f"Roll back {d['id']} on {svc_name(c['service'])}.")
    else:
        cause = {"service_id": None, "deploy_id": None, "ticket_key": None, "path": [],
                 "explanation": ("No change in the change log has words in common with the alert, and without dependency "
                                 "data nothing more can be checked; not guessing a cause.") if text_only else
                                ("No recent change found on the call path of " + ", ".join(map(svc_name, inc["alerts"]))
                                 + " or in a corroborated shared dependency; not inventing a cause.")}
        look = look_first_from(crit, inc["alerts"])
        if look:
            evidence += [{"node_id": s, "claim": f"most depended-on service on the call path ({look['algorithm']})"}
                         for s in look["service_ids"]]
            actions.append(f"Check {', '.join(map(svc_name, look['service_ids']))} capacity and saturation first.")
    conf = conflict_from(c, dec) if c else None
    similar = recalled(c, past) if c else []
    conflicting = None
    if conf:
        dec_, src = conf
        conflicting = {"decision_id": dec_["id"], "source_id": src["id"], "excerpt": src["excerpt"].rstrip("…"),
                       "how_it_conflicts": f"The change ({c['deploy']['summary']}) contradicts \"{dec_['title']}\", decided by "
                                           f"{dec_['author']}" + (" (who has left)" if dec_.get("author_status") == "left" else "") + "."}
        evidence.append({"node_id": dec_["id"], "claim": f"Decision \"{dec_['title']}\" ({dec_['decided']}), source {src['id']}."})
        actions.append(f"Restore the setting required by {dec_['id']} before re-shipping.")
    for i in similar[:2]:
        evidence.append({"node_id": i["id"], "claim": f"{i['key']} was caused by a change to {svc_name(c['service'])}; fixed by "
                                                       f"{', '.join(i.get('resolved_by') or ['?'])}: {i.get('resolution')}"})
    if contact and contact.get("person_id"):
        evidence.append({"node_id": contact["person_id"], "claim": f"Best active contact: {contact['reason']}."})
        actions.insert(1 if c else 0, f"Page {contact['name']} ({contact['person_id']}).")
    elif contact:
        evidence.append({"node_id": contact["team_id"], "claim": contact["reason"]})
        actions.insert(1 if c else 0, f"Escalate to team {contact['team_id']}; nobody active owns this service.")
    if similar:
        actions.append(f"Follow the {similar[0]['key']} fix: {similar[0].get('resolution')}.")
    if blast:
        evidence.append({"node_id": a0, "claim": f"{blast['upstream_count']} upstream services ({blast['tier1_count']} tier-1) are exposed."})
    for e in [{"node_id": x, "claim": "alerting service"} for x in inc["alerts"]] + (extra or []):
        if len(evidence) >= 3:
            break
        evidence.append(e)
    score = bool(c) + bool(conf) + bool(similar)
    names = ", ".join(map(svc_name, inc["alerts"]))
    if c:
        summary = (f"{names} alert{'s' * (len(inc['alerts']) > 1)} most likely caused by {c['deploy']['id']} on "
                   f"{svc_name(c['service'])}, deployed {c['deploy']['minutes_ago']} min ago.")
        if conf:
            summary += f" The change contradicts decision {conf[0]['id']}."
        if contact:
            summary += (f" Contact {contact['name']}." if contact.get("person_id") else f" Escalate to {contact['team_id']}.")
    else:
        summary = f"No recent change explains the {names} alert; the cause is unknown." + (
            f" Look at {', '.join(map(svc_name, look['service_ids']))} first." if look else "")
    sims = [{"incident_id": i["id"], "what_fixed_it": i.get("resolution") or "unknown",
             "resolved_by": ", ".join(i.get("resolved_by") or []) or "unknown"} for i in similar]
    confidence = "low" if text_only else ["low", "medium", "medium", "high"][score]
    return {"alerts": inc["alerts"], "summary": summary, "likely_cause": cause,
            "blast_radius": [u["id"] for u in (blast or {}).get("upstream", [])],
            "contact": contact or {"person_id": None, "name": None, "reason": "no candidate found"},
            "bus_factor_warning": warn, "conflicting_decision": conflicting, "similar_past_incidents": sims,
            "evidence": evidence, "recommended_actions": actions[:4], "confidence": confidence, "look_first": look}


# ───────────── the "no graph" path: full-text + change log only ─────────────
def _search_args(a):
    return {"query": f"{svc_name(a['service_id'])} {a.get('symptom', '')}"[:200], "limit": 8}


def text_only(v, alerts, changes):
    """Per alert: the change whose words best match the alert and what full-text search finds about it (newest on
    ties). No dependency data, so no path and low confidence. -> (incidents, whos, extra evidence) or calls."""
    calls = _calls_needed(v, [("search_knowledge", _search_args(a)) for a in alerts])
    if calls:
        return calls
    picks, words = {}, {}
    for a in alerts:
        hits = (v.last("search_knowledge", **_search_args(a)) or {}).get("hits", [])
        ctx = _words(f"{svc_name(a['service_id'])} {a.get('symptom', '')} " + " ".join(f"{h['title']} {h.get('snippet', '')}" for h in hits))
        overlap = lambda ch: len(ctx & _words(f"{svc_name(ch['service'])} {ch['deploy']['summary']} "
                                              f"{(ch.get('ticket') or {}).get('title', '')}"))
        for ch in changes or []:
            words[ch["deploy"]["id"]] = max(words.get(ch["deploy"]["id"], 0), overlap(ch))
        best = max(changes or [], key=lambda ch: (overlap(ch), -ch["deploy"]["minutes_ago"]), default=None)
        picks[a["service_id"]] = best if best and overlap(best) else None  # no word in common: no basis to pick one
    lookups = _calls_needed(v, [("find_service", {"query": svc_name(ch["service"])}) for ch in picks.values()
                                if ch and not (ch.get("deployer_id") and ch.get("deployer_status") == "active")])
    if lookups:  # nobody active shipped it: find the owning team in the catalog
        return lookups
    incidents, whos, extra = [], {}, {}
    for a in alerts:
        ch = picks[a["service_id"]]
        inc = next((i for i in incidents if ch and i["cause"] and i["cause"]["deploy"]["id"] == ch["deploy"]["id"]), None)
        if inc:
            inc["alerts"].append(a["service_id"])
            continue
        inc = {"alerts": [a["service_id"]], "cause": ch and {
            "deploy": ch["deploy"], "service": ch["service"], "ticket": ch.get("ticket"), "path": [], "hops": None,
            "kind": "text", "shared": None, "learned_hop": False}}
        incidents.append(inc)
        k = len(incidents) - 1
        if ch and ch.get("deployer_id") and ch.get("deployer_status") == "active":
            whos[k] = {"person_id": ch["deployer_id"], "name": ch["deploy"]["by"],
                       "reason": f"shipped the change picked for this alert ({ch['deploy']['id']})"}
        elif ch:
            m = next((x for x in (v.last("find_service", query=svc_name(ch["service"])) or {}).get("matches", [])
                      if x["id"] == ch["service"]), None)
            if m:
                whos[k] = {"person_id": None, "name": None, "team_id": m["team_id"],
                           "reason": f"nobody active shipped {ch['deploy']['id']}; escalate to the team that owns "
                                     f"{svc_name(ch['service'])} ({m['team']}, from the service catalog)"}
        hits = (v.last("search_knowledge", **_search_args(a)) or {}).get("hits", [])
        extra[k] = [{"node_id": h["id"], "claim": f"full-text match for the alert: {h['title']}"} for h in hits[:3]] + [
            {"node_id": c["deploy"]["id"], "claim": "recent change (a lead)"} for c in changes or []] + [
            {"node_id": a["service_id"], "claim": f"change log: {len(changes or [])} change(s) in {SCAN} min"},
            {"node_id": a["service_id"], "claim": f"full-text search for the alert: {len(hits)} hit(s)"}]
    return incidents, whos, extra, words


# ───────────── the policy ─────────────
def firefighter(v):
    alerts = [dict(a) for a in (v.payload.get("alerts") or [v.payload.get("alert", {})])]
    alerts = [a for i, a in enumerate(alerts) if not a.get("service_id")
              or a["service_id"] not in [b.get("service_id") for b in alerts[:i]]]  # one entry per alerting service
    unresolved = [a for a in alerts if not a.get("service_id")]
    if unresolved:
        if not v.called("find_service"):
            return turn(v.turns, *[("find_service", {"query": a.get("service_query", "")}) for a in unresolved])
        for a in unresolved:
            res = v.last("find_service", query=a.get("service_query", "")) or {}
            a["service_id"] = (res.get("matches") or [{}])[0].get("id")
        lost = [a.get("service_query", "") for a in alerts if not a.get("service_id")]
        alerts = [a for i, a in enumerate(alerts) if a.get("service_id")
                  and a["service_id"] not in [b.get("service_id") for b in alerts[:i]]]
        if not alerts:
            return []  # nothing to investigate; the loop nudges, the run ends at step_limit
    else:
        lost = []
    svcs = [a["service_id"] for a in alerts]
    first = _calls_needed(v, [("memory_recall", {"service_id": s}) for s in svcs]
                          + [("recent_changes", {"since_minutes": SCAN, "limit": CHANGE_LIMIT})])
    if first:
        return turn(v.turns, *first)
    log = v.last("recent_changes") or {}
    changes = log.get("changes") if "recent_changes" in v.tools else None
    checked = [{"node_id": svcs[0], "claim": f"change log: {log.get('change_count', 0)} change(s) anywhere in {SCAN} min"}] \
        if "recent_changes" in v.tools else []
    for t, what in (("recent_changes_downstream", "deploys to it or anything it calls"),
                    ("shared_dependency_changes", "deploys to services sharing a dependency with it")):
        for s_ in svcs:
            r = v.last(t, service_id=s_, since_minutes=SCAN, **({"max_hops": DEPTH} if t == "recent_changes_downstream" else {}))
            if r is not None:
                checked.append({"node_id": s_, "claim": f"{what} in {SCAN} min: {r.get('hit_count', 0)}"})
            elif t not in v.tools:
                checked.append({"node_id": s_, "claim": f"not checked: {what} (no {t} tool)"})
            elif changes == []:
                checked.append({"node_id": s_, "claim": f"not scanned for {what}: nothing changed anywhere in {SCAN} min"})
    notes = ([f"Could not resolve alert service(s): {', '.join(map(repr, lost))}."] if lost else []) + (
        [f"Only the newest {CHANGE_LIMIT} changes were checked."] if log.get("truncated") else [])
    leads = [{"node_id": ch["deploy"]["id"], "claim": f"recent change on {svc_name(ch['service'])} (a lead)"}
             for ch in changes or []]
    if "recent_changes_downstream" not in v.tools:
        out = text_only(v, alerts, changes)
        if isinstance(out, list):
            return turn(v.turns, *out)
        incidents, whos, extra, words = out
        reps = [incident_report(alerts, inc, None, None, None, None, None, text_only=True, extra=extra.get(k),
                                contact=whos.get(k)) for k, inc in enumerate(incidents)]
        causes = {i["cause"]["deploy"]["id"] for i in incidents if i["cause"]}
        best = max((words.get(d, 0) for d in causes), default=0)
        rejected = [{"deploy_id": ch["deploy"]["id"], "service_id": ch["service"],
                     "reason": (("no word" if not words.get(ch["deploy"]["id"]) else f"{words[ch['deploy']['id']]} word(s)")
                                + " in common with the alert" + (f" vs {best} for the change picked" if causes else "")
                                + (" (a tie: the newer change was picked)" if causes and words.get(ch["deploy"]["id"]) == best else "")
                                + "; no dependency data to check it")}
                    for ch in changes or [] if ch["deploy"]["id"] not in causes]
        return turn(v.turns, ("submit_report", assemble(alerts, incidents, reps, rejected, None, notes)))
    if changes != []:  # nothing changed anywhere -> no scans needed
        scans = _calls_needed(v, [(t, {"service_id": s, "since_minutes": SCAN, **({"max_hops": DEPTH} if t == "recent_changes_downstream" else {})})
                                  for s in svcs for t in ("recent_changes_downstream", "shared_dependency_changes")])
        if scans:
            return turn(v.turns, *scans)
    cands, weak, cut = candidates(v, alerts)
    incidents = group(alerts, cands)
    detail = []
    for inc in incidents:
        c = inc["cause"]
        focus = c["service"] if c else inc["alerts"][0]
        detail += [("blast_radius", {"service_id": inc["alerts"][0]}), ("who_to_call", {"service_id": focus})]
        if c:
            detail.append(("decisions_about", {"service_id": c["service"]}))
        else:
            detail.append(("critical_services", {"algorithm": "pagerank", "limit": 5, "downstream_of": inc["alerts"]}))
        ids = list(dict.fromkeys(inc["alerts"] + ([c["service"]] + ([c["shared"]] if c["shared"] else []) if c else [])))
        detail.append(("past_incidents", {"service_ids": ids[:10]}))
    detail = _calls_needed(v, detail)
    if not detail:  # PageRank refused (no algorithms): fall back to the plain count of services that reach each one
        detail = _calls_needed(v, [("critical_services", {"algorithm": "fan_in", "limit": 5, "downstream_of": i["alerts"]})
                                   for i in incidents if not i["cause"] and not i.get("root")
                                   and v.last("critical_services", downstream_of=i["alerts"]) is None
                                   and v.called("critical_services")])
    if detail:
        return turn(v.turns, *detail)
    reps = []
    for inc in incidents:
        c = inc["cause"]
        focus = c["service"] if c else inc["alerts"][0]
        ids = list(dict.fromkeys(inc["alerts"] + ([c["service"]] + ([c["shared"]] if c["shared"] else []) if c else [])))
        reps.append(incident_report(alerts, inc, v.last("who_to_call", service_id=focus),
                                    v.last("blast_radius", service_id=inc["alerts"][0]),
                                    v.last("decisions_about", service_id=c["service"]) if c else None,
                                    v.last("past_incidents", service_ids=ids[:10]),
                                    v.last("critical_services", downstream_of=inc["alerts"]) if not c else None,
                                    extra=[{"node_id": x, "claim": "on the dependency path to the culprit"} for x in (c["path"][1:-1] if c else [])]
                                    + leads + [{"node_id": u["id"], "claim": "upstream of the alert (exposed)"} for u in
                                               (v.last("blast_radius", service_id=inc["alerts"][0]) or {}).get("upstream", [])]
                                    + checked))
    if len(incidents) == 1 and incidents[0]["cause"]:
        c = incidents[0]["cause"]
        ids = list(dict.fromkeys(incidents[0]["alerts"] + [c["service"]] + ([c["shared"]] if c["shared"] else [])))
        rc = next((r for i in recalled(c, v.last("past_incidents", service_ids=ids[:10]))
                   for r in i.get("root_causes", [])), None)
        if rc and "industry_matches" in v.tools and not v.called("industry_matches"):
            return turn(v.turns, ("industry_matches", {"root_cause_id": rc}))
    return turn(v.turns, ("submit_report", assemble(alerts, incidents, reps, rejected_leads(changes, incidents, cands, weak, cut, v.tools),
                                                    industry_line(v.last("industry_matches")), notes)))


INCIDENT_KEYS = ("alerts", "summary", "likely_cause", "contact", "bus_factor_warning", "blast_radius",
                 "recommended_actions", "confidence", "look_first")


def assemble(alerts, incidents, reps, rejected, industry, notes=()):
    """The submitted report: the first incident's fields at the top, plus leads and (several alerts) every incident."""
    report = {k: val for k, val in reps[0].items() if k != "alerts"}
    report["industry_pattern"] = industry
    report["rejected_leads"] = rejected
    if len(alerts) > 1:
        report["incidents"] = [{k: r[k] for k in INCIDENT_KEYS} for r in reps]
    if len(incidents) > 1:
        report["summary"] = (f"{len(alerts)} alerts, {len(incidents)} separate incidents: "
                             + "; ".join(f"{', '.join(map(svc_name, r['alerts']))} -> "
                                         + (r["likely_cause"]["deploy_id"] or "cause unknown") for r in reps) + ".")
    if notes:  # summary stays <= 3 sentences
        report["summary"] = " ".join(re.split(r"(?<=[.!?])\s+", report["summary"])[:3 - len(notes)] + list(notes))
    return report
