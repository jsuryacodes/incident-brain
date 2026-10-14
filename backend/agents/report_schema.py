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
    "contact": _obj({"person_id": _SN, "name": _SN, "reason": _S}),
    "bus_factor_warning": {**_SN, "description": "Say so if the maintainer has left; null otherwise."},
    "conflicting_decision": {"anyOf": [{"type": "null"}, _obj({
        "decision_id": _S, "source_id": _S, "excerpt": {"type": "string", "description": "Verbatim quote from the source."},
        "how_it_conflicts": _S})]},
    "similar_past_incidents": {"type": "array", "items": _obj({"incident_id": _S, "what_fixed_it": _S, "resolved_by": _S})},
    "evidence": {"type": "array", "minItems": 3, "items": _obj({"node_id": _S, "claim": _S})},
    "recommended_actions": {"type": "array", "maxItems": 4, "items": _S},
    "confidence": {"enum": ["low", "medium", "high"]},
}
SUBMIT_REPORT = {
    "description": "Submit the final incident report. Call exactly once, at the end. Every id must have come back "
                   "from a tool; excerpts must be verbatim quotes.",
    "input_schema": _obj(REPORT_PROPS),
    "action": "answer",
}


def schema_errors(report, schema):
    """Light structural check: required keys, no unknown keys, simple min/max items. (No jsonschema dependency.)"""
    errs = []
    if not isinstance(report, dict):
        return ["report must be an object"]
    props = schema["properties"]
    errs += [f"missing field {k!r}" for k in schema.get("required", []) if k not in report]
    errs += [f"unknown field {k!r}" for k in report if k not in props]
    for k, v in report.items():
        p = props.get(k, {})
        if isinstance(v, list):
            if len(v) < p.get("minItems", 0):
                errs.append(f"{k} needs at least {p['minItems']} items")
            if len(v) > p.get("maxItems", 10 ** 6):
                errs.append(f"{k} allows at most {p['maxItems']} items")
    return errs


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s]


def _quotes(obj):
    """(node_id, excerpt) pairs: any dict carrying an excerpt plus source_id / node_id."""
    out = []
    if isinstance(obj, dict):
        if obj.get("excerpt") and (obj.get("source_id") or obj.get("node_id")):
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
