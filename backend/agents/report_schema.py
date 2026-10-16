"""submit_report tool schema (structured output) + the grounding checker every submit tool uses."""
import re

from backend.tools.receipt import excerpt_error, ids_in

_S = {"type": "string"}
_SN = {"type": ["string", "null"]}
_IDS = {"type": "array", "items": _S}


def _obj(props, required=None):
    return {"type": "object", "properties": props, "required": list(required if required is not None else props),
            "additionalProperties": False}


REPORT_PROPS = {
    "summary": {"type": "string", "description": "At most 3 sentences."},
    "likely_cause": _obj({"service_id": _SN, "deploy_id": _SN, "ticket_key": _SN,
                          "path": {**_IDS, "description": "Service ids from the alerting service to the culprit."},
                          "explanation": _S}),
    "blast_radius": {**_IDS, "description": "Upstream service ids hurt by this."},
    "contact": _obj({"person_id": _SN, "name": _SN, "reason": _S,
                     "team_id": {**_SN, "description": "Only when no active person can be paged: the owning team to escalate to."}},
                    ["person_id", "name", "reason"]),
    "bus_factor_warning": {**_SN, "description": "Say so if the maintainer has left; null otherwise."},
    "conflicting_decision": {"anyOf": [{"type": "null"}, _obj({
        "decision_id": _S, "source_id": _S, "excerpt": {"type": "string", "description": "Verbatim quote from the source."},
        "how_it_conflicts": _S})]},
    "similar_past_incidents": {"type": "array", "items": _obj({"incident_id": _S, "what_fixed_it": _S, "resolved_by": _S})},
    "evidence": {"type": "array", "minItems": 3, "items": _obj({"node_id": _S, "claim": _S})},
    "recommended_actions": {"type": "array", "maxItems": 4, "items": _S},
    "confidence": {"enum": ["low", "medium", "high"]},
    "industry_pattern": {**_SN, "description": "'Matches known industry pattern: <company> — <title> (<url>)' from "
                                                "industry_matches, or null if nothing matched."},
}
_LC = REPORT_PROPS["likely_cause"]
_SUPPRESSED = {"type": "array", "description": "Pages NOT sent because another page covers the same incident, each with the graph's reason.",
               "items": _obj({"alert": _S, "person_id": _SN, "name": _SN, "team_id": _SN, "reason": _S})}
FIREFIGHTER_EXTRA = {  # optional: the Firefighter's leads, its pointer when nothing changed, and several incidents
    "rejected_leads": {"type": "array", "description": "Every recent change that is NOT the cause, with the graph's reason.",
                       "items": _obj({"deploy_id": _S, "service_id": _S, "reason": _S})},
    "look_first": {"anyOf": [{"type": "null"}, _obj({"service_ids": _IDS, "algorithm": _S, "reason": _S})],
                   "description": "Only when no cause was found: where to look first (e.g. the top PageRank hub on the call path). Never a cause."},
    "incidents": {"type": "array", "description": "Several alerts: one entry per separate incident.",
                  "items": _obj({"alerts": _IDS, "summary": _S, "likely_cause": _LC, "contact": REPORT_PROPS["contact"],
                                 "bus_factor_warning": REPORT_PROPS["bus_factor_warning"], "blast_radius": _IDS,
                                 "recommended_actions": REPORT_PROPS["recommended_actions"],
                                 "confidence": REPORT_PROPS["confidence"], "look_first": {"type": ["object", "null"]},
                                 "root": {"type": ["object", "null"], "description": "Alert storm: the shared dependency these alerts all call (no change explains them)."},
                                 "suppressed_pages": _SUPPRESSED,
                                 "notify": {"type": "array", "description": "Silent callers of a storm root: notify, don't page.",
                                            "items": _obj({"service_id": _S, "hops": {"type": "integer"}})}},
                                ["alerts", "summary", "likely_cause", "contact", "bus_factor_warning", "blast_radius",
                                 "recommended_actions", "confidence", "look_first"])},
    "suppressed_pages": _SUPPRESSED,
    "hypotheses": {"type": "array", "description": "The hypothesis board: every lead with evidence for and against, a status and the reason.",
                   "items": _obj({"id": _S, "claim": _S, "status": {"enum": ["open", "confirmed", "rejected"]},
                                  "supporting": {"type": "array", "items": _obj({"node_id": _S, "claim": _S})},
                                  "contradicting": {"type": "array", "items": _obj({"node_id": _S, "claim": _S})},
                                  "reason": _S})},
    "action_plan": {"type": "array", "description": "What to do, each step with its graph justification; nothing runs until a person approves it.",
                    "items": _obj({"id": _S, "incident": {"type": "integer"},
                                   "kind": {"enum": ["rollback", "hold", "page", "escalate", "suppress_page", "notify", "open_ticket", "flag_stale"]},
                                   "target": _S, "title": _S,
                                   "justification": _obj({"why": _S, "node_ids": _IDS, "path": _IDS}),
                                   "safety": {"type": ["object", "null"]}})},
    "confidence_breakdown": {"type": "array", "description": "What raised (+) or lowered (-) the confidence.",
                             "items": _obj({"effect": {"enum": ["+", "-"]}, "factor": _S, "node_id": _SN})},
}
SUBMIT_REPORT = {
    "description": "Submit the final incident report. Call exactly once, at the end. Every id must have come back "
                   "from a tool; excerpts must be verbatim quotes.",
    "input_schema": _obj({**REPORT_PROPS, **FIREFIGHTER_EXTRA}, list(REPORT_PROPS)),
    "action": "answer",
}


def schema_errors(report, schema, path=""):
    """Light structural check, recursive: required keys, no unknown keys, min/max items, and the same for nested
    objects (inside anyOf too) and array items. (No jsonschema dependency.)"""
    if not isinstance(report, dict):
        return [f"{path or 'report'} must be an object"]
    errs, props = [], schema.get("properties", {})
    errs += [f"missing field {path}{k!r}" for k in schema.get("required", []) if k not in report]
    errs += [f"unknown field {path}{k!r}" for k in report if k not in props]
    for k, v in report.items():
        p = props.get(k, {})
        obj = next((o for o in [p] + p.get("anyOf", []) if o.get("type") == "object"), None)
        if isinstance(v, dict) and obj:
            errs += schema_errors(v, obj, f"{path}{k}.")
        elif isinstance(v, list):
            if len(v) < p.get("minItems", 0):
                errs.append(f"{path}{k} needs at least {p['minItems']} items")
            if len(v) > p.get("maxItems", 10 ** 6):
                errs.append(f"{path}{k} allows at most {p['maxItems']} items")
            if (item := p.get("items", {})).get("type") == "object":
                for i, x in enumerate(v):
                    errs += schema_errors(x, item, f"{path}{k}[{i}].")
    return errs


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s]


def _quotes(obj):
    """(node_id, excerpt) pairs: any dict carrying an excerpt plus source_id / node_id."""
    out = []
    if isinstance(obj, dict):
        if "excerpt" in obj:  # every excerpt is checked; one without a source id or text fails the check
            out.append((obj.get("source_id") or obj.get("node_id"), obj["excerpt"]))
        for v in obj.values():
            out += _quotes(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _quotes(v)
    return out


def grounding_problems(payload, seen, graph):
    """{} if every id was seen and every excerpt is a literal quote; else {"errors": [...], "ungrounded_ids": [...]}."""
    bad = sorted(ids_in(payload) - seen)
    errs = [f"ungrounded ids {bad}"] if bad else []
    errs += [e for nid, exc in _quotes(payload) if (e := excerpt_error(graph, nid, exc))]
    return {"errors": errs, "ungrounded_ids": bad} if errs else {}


def check_report(report, seen, graph, schema=SUBMIT_REPORT["input_schema"]):
    p = grounding_problems(report, seen, graph)
    errs = schema_errors(report, schema)
    if len(sentences(report.get("summary", ""))) > 3:
        errs.append("summary must be at most 3 sentences")
    if errs:
        p = {"errors": p.get("errors", []) + errs, "ungrounded_ids": p.get("ungrounded_ids", [])}
    return p
