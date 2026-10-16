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


ROOT_MIN = 3  # a shared root (no change) opens one incident only when it explains at least this many alerts


def storm_root(alerts, cands, corr):
    """The top shared dependency from correlate_alerts, if it explains more alerts (>= ROOT_MIN) than any single
    change does: then these alerts are one incident about that root (saturation), not one each. -> (root, covered)"""
    roots = (corr or {}).get("roots") or []
    if not roots:
        return None, []
    ids = [a["service_id"] for a in alerts]
    covered = [x for x in ids if x in roots[0]["covers"]]
    by_change = {}
    for x in ids:
        for c in cands[x]:
            by_change.setdefault(c["deploy"]["id"], set()).add(x)
    best = max((len(v) for v in by_change.values()), default=0)
    return (roots[0], covered) if len(covered) >= ROOT_MIN and len(covered) > best else (None, [])


def group(alerts, cands, corr=None):
    """Greedy: the explanation covering the most still-unexplained alerts first: a recent change, or (several alerts)
    a shared root that explains more alerts than any change. -> [{alerts, cause or None, root or None}]"""
    root, covered = storm_root(alerts, cands, corr)
    pool = {x: list(cs) for x, cs in cands.items()}
    if root:
        root = {**root, "tied": [r["id"] for r in corr["roots"][1:] if r["coverage"] == root["coverage"]]}
        for x in covered:
            path = root["paths"].get(x) or [x, root["id"]]
            pool[x].append({"deploy": {"id": "root:" + root["id"], "minutes_ago": 10 ** 6}, "service": root["id"],
                            "path": path, "hops": len(path) - 1, "kind": "root", "shared": None, "learned_hop": False})
    left, incidents = [a["service_id"] for a in alerts], []
    while left:
        best = None
        for d in sorted({c["deploy"]["id"] for x in left for c in pool[x]}):
            cov = [x for x in left if any(c["deploy"]["id"] == d for c in pool[x])]
            mine = [next(c for c in pool[x] if c["deploy"]["id"] == d) for x in cov]
            if best is None or _key(mine, cov) < best[0]:
                best = (_key(mine, cov), cov, mine[0])
        if best is None:
            incidents += [{"alerts": [x], "cause": None, "root": None} for x in left]
            break
        c = best[2]
        incidents.append({"alerts": best[1], "cause": None if c["kind"] == "root" else c,
                          "root": root if c["kind"] == "root" else None})
        left = [x for x in left if x not in best[1]]
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
            if inc.get("root"):
                mine = sum(1 for x in inc["alerts"] if any(k["deploy"]["id"] == d for k in cands.get(x, [])))
                reason = (f"{svc_name(svc)} {_where(c, s)}, but no change explains this storm: {len(inc['alerts'])} alerts "
                          f"all call {svc_name(inc['root']['id'])} (correlate_alerts), this change explains {mine} of them")
            elif inc["cause"]:
                reason = f"{svc_name(svc)} {_where(c, s)}, but " + _why_lost(c, s, inc, cands)
            else:
                reason = f"{svc_name(svc)} {_where(c, s)}"
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


def root_pointer(root, crit):
    """Where to look in a storm: the correlated root (and a runner-up the algorithms can't separate from it)."""
    ids = [root["id"]] + [r for r in (root.get("tied") or [])][:1]
    return {"service_ids": ids, "algorithm": "correlate_alerts (algo.BFS coverage + algo.SPpaths)",
            "reason": f"{svc_name(root['id'])} is reached by {root['coverage']} of the alerting services "
                      f"({root['total_hops']} hops in total)" + (f"; {svc_name(ids[1])} right behind it is reached by "
                                                                 "as many" if len(ids) > 1 else "") + ": check its load first."}


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
        root = inc.get("root")
        look = root_pointer(root, crit) if root else look_first_from(crit, inc["alerts"])
        if root:
            cause["explanation"] = (f"No recent change explains these {len(inc['alerts'])} alerts, and all of them call "
                                    f"{svc_name(root['id'])} ({root['total_hops']} hops in total; it is "
                                    + ("alerting itself" if root["alerting"] else "not alerting itself") + "): one shared "
                                    "dependency under load, so one incident, not " + str(len(inc["alerts"])) + ".")
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
        root = inc.get("root")
        summary = (f"{len(inc['alerts'])} alerts ({names}) are one incident: they all call {svc_name(root['id'])}, and no "
                   f"recent change explains them. Page {contact['name'] if contact and contact.get('person_id') else 'the owning team'} "
                   f"once instead of {len(inc['alerts'])} times." if root else
                   f"No recent change explains the {names} alert; the cause is unknown." + (
                       f" Look at {', '.join(map(svc_name, look['service_ids']))} first." if look else ""))
    sims = [{"incident_id": i["id"], "what_fixed_it": i.get("resolution") or "unknown",
             "resolved_by": ", ".join(i.get("resolved_by") or []) or "unknown"} for i in similar]
    confidence = "low" if text_only else "medium" if inc.get("root") else ["low", "medium", "medium", "high"][score]
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
        report = assemble(alerts, incidents, reps, rejected, None, notes)
        report["hypotheses"] = hypotheses(incidents, reps, rejected, changes, {}, {})
        report["confidence_breakdown"] = [{"effect": "-", "factor": "no dependency data: the cause was matched by words",
                                           "node_id": None}]
        return turn(v.turns, ("submit_report", report))
    if changes != []:  # nothing changed anywhere -> no scans needed
        scans = _calls_needed(v, [(t, {"service_id": s, "since_minutes": SCAN, **({"max_hops": DEPTH} if t == "recent_changes_downstream" else {})})
                                  for s in svcs for t in ("recent_changes_downstream", "shared_dependency_changes")])
        if scans:
            return turn(v.turns, *scans)
    if len(svcs) > 1:  # several alerts: which share dependencies, and which cannot share a cause at all
        corr_calls = _calls_needed(v, [("correlate_alerts", {"service_ids": svcs}), ("connected_impact", {"service_ids": svcs})])
        if corr_calls:
            return turn(v.turns, *corr_calls)
    corr = v.last("correlate_alerts", service_ids=svcs) if len(svcs) > 1 else None
    cands, weak, cut = candidates(v, alerts)
    incidents = group(alerts, cands, corr)
    detail = []
    for inc in incidents:
        c, root = inc["cause"], inc.get("root")
        focus = c["service"] if c else root["id"] if root else inc["alerts"][0]
        detail += [("blast_radius", {"service_id": inc["alerts"][0]}), ("who_to_call", {"service_id": focus})]
        if c:
            detail += [("decisions_about", {"service_id": c["service"]}), ("rollback_safety", {"deploy_id": c["deploy"]["id"]}),
                       ("stale_knowledge", {"service_id": c["service"]})]
        elif root:
            detail.append(("blast_tiers", {"service_id": root["id"], "alerting": svcs}))
        else:
            detail.append(("critical_services", {"algorithm": "pagerank", "limit": 5, "downstream_of": inc["alerts"]}))
        if len(inc["alerts"]) > 1:  # who each alert would page on its own: the pages this incident replaces
            detail += [("who_to_call", {"service_id": x}) for x in inc["alerts"]]
        ids = list(dict.fromkeys(inc["alerts"] + ([c["service"]] + ([c["shared"]] if c["shared"] else []) if c else [])
                                 + ([root["id"]] if root else [])))
        detail.append(("past_incidents", {"service_ids": ids[:10]}))
    if any(i.get("root") for i in incidents):
        detail.append(("failure_domains", {"service_ids": svcs}))
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
        c, root = inc["cause"], inc.get("root")
        focus = c["service"] if c else root["id"] if root else inc["alerts"][0]
        ids = list(dict.fromkeys(inc["alerts"] + ([c["service"]] + ([c["shared"]] if c["shared"] else []) if c else [])
                                 + ([root["id"]] if root else [])))
        reps.append(incident_report(alerts, inc, v.last("who_to_call", service_id=focus),
                                    v.last("blast_radius", service_id=inc["alerts"][0]),
                                    v.last("decisions_about", service_id=c["service"]) if c else None,
                                    v.last("past_incidents", service_ids=ids[:10]),
                                    v.last("critical_services", downstream_of=inc["alerts"]) if not c else None,
                                    extra=[{"node_id": x, "claim": "on the dependency path to the culprit"} for x in (c["path"][1:-1] if c else [])]
                                    + leads + [{"node_id": u["id"], "claim": "upstream of the alert (exposed)"} for u in
                                               (v.last("blast_radius", service_id=inc["alerts"][0]) or {}).get("upstream", [])]
                                    + checked))
        reps[-1].update(pages_for(v, inc, reps[-1], focus))
    if len(incidents) == 1 and incidents[0]["cause"]:
        c = incidents[0]["cause"]
        ids = list(dict.fromkeys(incidents[0]["alerts"] + [c["service"]] + ([c["shared"]] if c["shared"] else [])))
        rc = next((r for i in recalled(c, v.last("past_incidents", service_ids=ids[:10]))
                   for r in i.get("root_causes", [])), None)
        if rc and "industry_matches" in v.tools and not v.called("industry_matches"):
            return turn(v.turns, ("industry_matches", {"root_cause_id": rc}))
    rejected = rejected_leads(changes, incidents, cands, weak, cut, v.tools)
    for inc, rep in zip(incidents, reps):  # a rollback the graph says is risky becomes "hold"
        safety = v.last("rollback_safety", deploy_id=inc["cause"]["deploy"]["id"]) if inc["cause"] else None
        if safety and safety.get("verdict") == "risky":
            rep["recommended_actions"] = [f"Hold the rollback of {safety['deploy']}: {safety['reasons'][0]}; page the owner first."
                                          if a.startswith("Roll back") else a for a in rep["recommended_actions"]]
    for inc, rep in zip(incidents, reps):
        rep["confidence_breakdown"] = confidence_breakdown(inc, rep)
    report = assemble(alerts, incidents, reps, rejected, industry_line(v.last("industry_matches")), notes)
    report["action_plan"] = action_plan(v, incidents, reps)
    report["hypotheses"] = hypotheses(incidents, reps, rejected, changes, cands, weak)
    report["confidence_breakdown"] = confidence_breakdown(incidents[0], reps[0]) if incidents else []
    return turn(v.turns, ("submit_report", report))


def action_plan(v, incidents, reps):
    """What the agent proposes to DO, each step with its graph justification. Nothing runs until a person approves it
    (POST /api/actions/execute with the access code); execution is simulated and writes only agent-origin nodes."""
    plan = []

    def add(k, kind, target, title, why, node_ids, path=None, safety=None):
        plan.append({"id": f"A{len(plan) + 1}", "incident": k, "kind": kind, "target": target, "title": title,
                     "justification": {"why": why, "node_ids": [x for x in node_ids if x], "path": path or []},
                     "safety": safety})
    for k, (inc, rep) in enumerate(zip(incidents, reps)):
        c, root = inc["cause"], inc.get("root")
        if c:
            sf = v.last("rollback_safety", deploy_id=c["deploy"]["id"])
            safety = {"verdict": sf["verdict"], "reasons": sf["reasons"], "dependents": sf["dependents"],
                      "later_deploys": [x["id"] for x in sf["later_deploys"]], "blast": sf["blast_of_rollback"]} if sf else None
            risky = bool(sf) and sf["verdict"] == "risky"
            add(k, "hold" if risky else "rollback", c["deploy"]["id"],
                (f"Hold the rollback of {c['deploy']['id']} (risky): page the owner first" if risky else
                 f"Roll back {c['deploy']['id']} on {svc_name(c['service'])}"),
                rep["likely_cause"]["explanation"], [c["deploy"]["id"], c["service"]] + c["path"], c["path"], safety)
        ct = rep.get("contact") or {}
        if ct.get("person_id"):
            add(k, "page", ct["person_id"], f"Page {ct['name']}", ct["reason"], [ct["person_id"], (c or {}).get("service")
                                                                               or (root or {}).get("id") or inc["alerts"][0]])
        elif ct.get("team_id"):
            add(k, "escalate", ct["team_id"], f"Escalate to {ct['team_id']} (nobody active to page)", ct["reason"], [ct["team_id"]])
        for sp in rep.get("suppressed_pages") or []:
            who = sp.get("person_id") or sp.get("team_id")
            add(k, "suppress_page", who, f"Don't page {sp.get('name') or who} for {svc_name(sp['alert'])}", sp["reason"],
                [who, sp["alert"]], (root["paths"].get(sp["alert"]) if root else c and c["path"]) or [])
        if rep.get("notify"):
            ids = [n["service_id"] for n in rep["notify"]]
            add(k, "notify", ",".join(ids), "Tell the owners of " + ", ".join(map(svc_name, ids[:4])) + (" …" if len(ids) > 4 else "")
                + " (not alerting yet)", f"they call {svc_name(root['id'])} and will feel it next (blast_tiers)", ids)
        focus = (c or {}).get("service") or (root or {}).get("id") or inc["alerts"][0]
        add(k, "open_ticket", focus, f"Open a follow-up ticket for {svc_name(focus)}",
            "track the fix and the lessons on the service that needs them", [focus])
        if c:
            for it in (v.last("stale_knowledge", service_id=c["service"]) or {}).get("items", []):
                if not it.get("flagged"):
                    add(k, "flag_stale", it["id"], f"Flag {it['title']} as stale", ", ".join(it["reasons"]), [it["id"], c["service"]])
    return plan


def _ev(node_id, claim):
    return {"node_id": node_id, "claim": claim}


def hypotheses(incidents, reps, rejected, changes, cands, weak):
    """The hypothesis board: every lead (and, when nothing changed, the alternatives) with evidence for and against,
    a status and the reason. Built only from tool results."""
    out, n = [], 0

    def add(claim, status, sup, con, reason):
        nonlocal n
        n += 1
        out.append({"id": f"H{n}", "claim": claim, "status": status, "supporting": sup, "contradicting": con, "reason": reason})
    by_dep = {ch["deploy"]["id"]: ch for ch in changes or []}
    for inc, rep in zip(incidents, reps):
        names = ", ".join(map(svc_name, inc["alerts"]))
        c, root = inc["cause"], inc.get("root")
        if c:
            d = c["deploy"]
            sup = [_ev(d["id"], f"deployed {d['minutes_ago']} min ago: {d['summary']}")]
            sup += [_ev(x, f"on the path {' -> '.join(map(svc_name, c['path']))}") for x in c["path"][1:]] if len(c["path"]) > 1 else \
                [_ev(c["service"], "the alerting service itself changed")]
            if (cd := rep.get("conflicting_decision")):
                sup.append(_ev(cd["decision_id"], "the change contradicts this recorded decision"))
            sup += [_ev(i["incident_id"], f"a past incident caused by a change to {svc_name(c['service'])}") for i in rep.get("similar_past_incidents") or []]
            add(f"{d['id']} on {svc_name(c['service'])} caused the {names} alert{'s' * (len(inc['alerts']) > 1)}", "confirmed",
                sup, [], ("explains " + str(len(inc["alerts"])) + " alerts; " if len(inc["alerts"]) > 1 else "")
                + (("the alerting service itself changed" if not c["hops"] else f"a change on the call path ({_hops(c['hops'])})")
                   if c["kind"] == "downstream" else
                   f"a noisy neighbour through {svc_name(c['shared'])}, corroborated by {c.get('corroborated_by')}"))
        elif root:
            sup = [_ev(x, f"calls {svc_name(root['id'])} ({_hops(len(root['paths'].get(x, [x, root['id']])) - 1)})") for x in inc["alerts"]]
            add(f"{svc_name(root['id'])} is saturated and takes the {len(inc['alerts'])} alerts down with it", "confirmed",
                sup, [_ev(root["id"], "no recent change on it or on the alerts' paths (an inference from structure, not a deploy)")],
                f"one shared dependency explains {len(inc['alerts'])} alerts; no single change explains more than "
                + str(max([len([x for x in inc["alerts"] if any(k["deploy"]["id"] == d for k in cands.get(x, []))])
                           for d in by_dep] or [0])))
        else:
            look = rep.get("look_first") or {}
            add(f"a recent change caused the {names} alert", "rejected", [],
                [_ev(inc["alerts"][0], "no change on its call path or in a corroborated shared dependency")],
                "nothing that changed in the window is connected to it")
            if look.get("service_ids"):
                add(f"load on {', '.join(map(svc_name, look['service_ids']))} (the most depended-on services on the call path)",
                    "open", [_ev(x, f"top of {look['algorithm']} on the call path") for x in look["service_ids"]], [],
                    "where to look first; not a confirmed cause")
    for r in rejected:
        ch = by_dep.get(r["deploy_id"], {})
        d = ch.get("deploy") or {}
        status = "open" if "stays possible" in r["reason"] else "rejected"
        add(f"{r['deploy_id']} on {svc_name(r['service_id'])} caused it", status,
            [_ev(r["deploy_id"], f"deployed {d.get('minutes_ago')} min ago" + (f": {d.get('summary')}" if d.get("summary") else ""))],
            [] if status == "open" else [_ev(r["service_id"], r["reason"])], r["reason"])
    return out


def confidence_breakdown(inc, rep):
    """What raised or lowered the confidence of the (first) incident's conclusion."""
    c, root, out = inc["cause"], inc.get("root"), []
    if c:
        out.append({"effect": "+", "factor": ("the alerting service itself changed" if not c["hops"] else
                                              f"the change is on the alert's call path ({_hops(c['hops'])})") if c["kind"] == "downstream"
                    else f"a neighbour through {svc_name(c['shared'])} ({c.get('corroborated_by')})", "node_id": c["deploy"]["id"]})
        if c["kind"] != "downstream":
            out.append({"effect": "-", "factor": "a shared dependency, not a direct one", "node_id": c["shared"]})
        cd = rep.get("conflicting_decision")
        out.append({"effect": "+", "factor": "it contradicts a recorded decision", "node_id": cd["decision_id"]} if cd else
                   {"effect": "-", "factor": "no recorded decision says it is risky", "node_id": None})
        sims = rep.get("similar_past_incidents") or []
        out.append({"effect": "+", "factor": "a past incident had the same cause", "node_id": sims[0]["incident_id"]} if sims else
                   {"effect": "-", "factor": "no past incident with the same cause", "node_id": None})
        if c.get("learned_hop"):
            out.append({"effect": "+", "factor": "the path uses a dependency an earlier session learned", "node_id": None})
    elif root:
        out += [{"effect": "+", "factor": f"{len(inc['alerts'])} alerts share {svc_name(root['id'])}", "node_id": root["id"]},
                {"effect": "-", "factor": "no change on it: saturation is inferred from structure", "node_id": None}]
    else:
        out.append({"effect": "-", "factor": "no recent change is connected to the alert", "node_id": None})
    return out


INCIDENT_KEYS = ("alerts", "summary", "likely_cause", "contact", "bus_factor_warning", "blast_radius",
                 "recommended_actions", "confidence", "look_first", "root", "suppressed_pages", "notify",
                 "confidence_breakdown")


def pages_for(v, inc, rep, focus):
    """One page per incident. For every other alert of the incident: who it would have paged on its own, suppressed
    with the graph's reason. Silent callers of a storm root: notify, don't page."""
    out = {"root": None, "suppressed_pages": [], "notify": []}
    root = inc.get("root")
    if root:
        out["root"] = {"service_id": root["id"], "covers": root["covers"], "alerting": root["alerting"],
                       "total_hops": root["total_hops"], "tied": root.get("tied", [])}
        tiers = next((r for i, r in v.all("blast_tiers") if i.get("service_id") == root["id"]), {})
        out["notify"] = [{"service_id": x, "hops": t["hops"]} for t in tiers.get("tiers", []) for x in t["silent"]][:8]
    if len(inc["alerts"]) < 2:
        return out
    me = (rep.get("contact") or {}).get("person_id")
    target = root["id"] if root else (inc["cause"] or {}).get("service")
    for x in inc["alerts"]:
        naive, _ = contact_or_team(v.last("who_to_call", service_id=x))
        pid = (naive or {}).get("person_id")
        if not naive or (pid and pid == me) or (not pid and naive.get("team_id") == (rep.get("contact") or {}).get("team_id")):
            continue
        path = (root["paths"].get(x) if root else (inc["cause"] or {}).get("path")) or []
        out["suppressed_pages"].append({
            "alert": x, "person_id": pid, "name": naive.get("name"), "team_id": naive.get("team_id"),
            "reason": f"{svc_name(x)} is part of this incident: " + (" -> ".join(map(svc_name, path)) if len(path) > 1 else
                                                                     f"{svc_name(x)} ({svc_name(target)})") + "; one page goes to "
                      + ((rep.get("contact") or {}).get("name") or (rep.get("contact") or {}).get("team_id") or "the owner")
                      + " instead"})
    return out


def assemble(alerts, incidents, reps, rejected, industry, notes=()):
    """The submitted report: the first incident's fields at the top, plus leads and (several alerts) every incident."""
    report = {k: val for k, val in reps[0].items() if k not in ("alerts", "root", "suppressed_pages", "notify", "confidence_breakdown")}
    report["industry_pattern"] = industry
    report["rejected_leads"] = rejected
    if len(alerts) > 1:
        report["incidents"] = [{k: r.get(k) for k in INCIDENT_KEYS} for r in reps]
        report["suppressed_pages"] = [p for r in reps for p in r.get("suppressed_pages") or []]
    if len(incidents) > 1:
        report["summary"] = (f"{len(alerts)} alerts, {len(incidents)} separate incidents: "
                             + "; ".join(f"{', '.join(map(svc_name, r['alerts']))} -> "
                                         + (r["likely_cause"]["deploy_id"] or (f"shared root {svc_name(r['root']['service_id'])}, "
                                                                               "no change" if r.get("root") else "cause unknown"))
                                         for r in reps) + ".")
    if notes:  # summary stays <= 3 sentences
        report["summary"] = " ".join(re.split(r"(?<=[.!?])\s+", report["summary"])[:3 - len(notes)] + list(notes))
    return report
