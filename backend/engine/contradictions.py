"""Deterministic contradiction + blocker rules. Pure function of (slots, DB).

Faithful 1:1 port of app/lib/engine/contradictions.ts.
"""
from __future__ import annotations

from .extract import LOW_CONFIDENCE

CRITICAL_SLOTS = ["grid", "level", "zone", "attribute", "value", "drawingNumber", "element", "activity"]


class CheckResult:
    def __init__(self) -> None:
        self.mode = "unknown"
        self.location = None
        self.locationInferred = False
        self.locationCandidates: list = []
        self.fact = None
        self.drawing = None
        self.element = None
        self.attribute = None
        self.unit = None
        self.value = None
        self.contradictions: list[dict] = []
        self.blockers: list[dict] = []
        self.missing: list[dict] = []
        self.lowConfidence: list[str] = []


def _jsnum(x):
    """Mimic JS number stringification: an integral float prints without a trailing .0."""
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return x


def _norm_fact(f):
    """DB REAL columns come back as floats; JS/better-sqlite3 would treat 180.0 as 180."""
    if not f:
        return f
    g = dict(f)
    if "value_num" in g:
        g["value_num"] = _jsnum(g["value_num"])
    if "tolerance" in g:
        g["tolerance"] = _jsnum(g["tolerance"])
    return g


def _coalesce(*xs):
    for x in xs:
        if x is not None:
            return x
    return None


def _to_unit(v, frm, to):
    if not frm or not to or frm == to:
        return v
    mm = {"mm": 1, "cm": 10, "m": 1000}
    if frm in mm and to in mm:
        return (v * mm[frm]) / mm[to]
    return v


def check(slots: dict, repo, confirmed: set | None = None) -> CheckResult:
    if confirmed is None:
        confirmed = set()
    r = CheckResult()

    def sv(name):
        s = slots.get(name)
        return s["value"] if s else None

    # ---------------------------------------- low confidence (ASR-garbled or LLM-only)
    for k in CRITICAL_SLOTS:
        s = slots.get(k)
        if not s or k in confirmed:
            continue
        if s["confidence"] < LOW_CONFIDENCE or s["source"] == "llm":
            r.lowConfidence.append(k)

    r.mode = (
        "activity" if slots.get("activity")
        else "measurement" if (slots.get("value") or slots.get("attribute"))
        else "defect" if slots.get("defect")
        else "unknown"
    )

    # ---------------------------------------- drawing (spoken)
    spoken_drawing = None
    if slots.get("drawingNumber"):
        spoken_drawing = repo.resolve_drawing_number(slots["drawingNumber"]["value"])
        latest = repo.latest_drawing(spoken_drawing) if spoken_drawing else None
        if not spoken_drawing or not latest:
            r.contradictions.append({
                "kind": "unknown_drawing", "severity": "clarify",
                "detail": f"Drawing {slots['drawingNumber']['value']} not in the register"
                          + (" (no For Construction revision)" if spoken_drawing else ""),
                "evidence": {"drawing_number": slots["drawingNumber"]["value"],
                             "candidates": repo.drawing_numbers()},
            })
            spoken_drawing = None

    # ---------------------------------------- location
    level = sv("level")
    cands = repo.resolve_location({
        "grid": sv("grid"), "level": level, "zone": sv("zone"), "element": sv("element"),
    })
    if not level and len(cands) > 1 and spoken_drawing:
        dl = (repo.latest_drawing(spoken_drawing) or {}).get("level")
        if dl:
            fltr = [c for c in cands if c.get("level") == dl]
            if fltr:
                cands = fltr
    r.locationCandidates = cands
    if len(cands) == 1:
        r.location = cands[0]
        r.locationInferred = (not slots.get("level")) and bool(cands[0].get("level"))
        level = cands[0].get("level")

    has_loc_words = bool(slots.get("grid") or slots.get("zone")
                         or (sv("element") == "slab" and slots.get("level")))
    if not r.location:
        if not has_loc_words:
            r.missing.append({"kind": "missing_critical_field", "severity": "clarify",
                              "detail": "location missing", "evidence": {"field": "location"}})
        elif len(cands) > 1:
            r.missing.append({"kind": "missing_critical_field", "severity": "clarify",
                              "detail": "level ambiguous",
                              "evidence": {"field": "level",
                                           "candidates": [c["location_id"] for c in cands]}})
        else:
            r.missing.append({
                "kind": "missing_critical_field", "severity": "clarify",
                "detail": "location not in register",
                "evidence": {"field": "location_unknown",
                             "claimed": _coalesce(sv("grid"), sv("zone")),
                             "candidates": [x for x in
                                            (l.get("grid") or l.get("zone") or l.get("location_id")
                                             for l in repo.locations()) if x]},
            })

    # ---------------------------------------- activity mode -> blockers
    if r.mode == "activity" and r.location:
        act = slots["activity"]["value"]
        if act == "pour":
            for hp in repo.hold_point_blockers(r.location["location_id"]):
                r.blockers.append({
                    "kind": "hold_point_blocker", "severity": "blocker",
                    "detail": f"Hold point not released on {hp['ref']}",
                    "evidence": {"checklist": hp["ref"], "template_id": hp.get("template_id"),
                                 "items": [i["label"] for i in hp["items"]],
                                 "code_ref": (hp["items"][0].get("code_ref") if hp["items"] else None)},
                })
        else:
            pb = repo.permit_blockers(r.location["location_id"], act)
            for b in pb["blocks"]:
                r.blockers.append({
                    "kind": "permit_blocker", "severity": "blocker",
                    "detail": f"Permit {b['permit_id']} has unsatisfied mandatory checks",
                    "evidence": {"permit_id": b["permit_id"],
                                 "checks": [u["label"] for u in b["unsatisfied"]]},
                })
            if pb["noPermit"] and not pb["blocks"]:
                r.blockers.append({
                    "kind": "permit_blocker", "severity": "blocker",
                    "detail": f"No active {act} permit",
                    "evidence": {"permit_id": None,
                                 "checks": [f"No active {act.replace('_', ' ')} permit"]},
                })
        r.drawing = repo.latest_drawing_for_location(r.location["location_id"], level)
        return r

    # ---------------------------------------- measurement: attribute + value required
    if r.mode in ("measurement", "unknown"):
        if not slots.get("attribute"):
            r.missing.append({"kind": "missing_critical_field", "severity": "clarify",
                              "detail": "attribute missing", "evidence": {"field": "attribute"}})
        if not slots.get("value"):
            r.missing.append({"kind": "missing_critical_field", "severity": "clarify",
                              "detail": "value missing", "evidence": {"field": "value"}})

    # ---------------------------------------- fact lookup (latest For Construction revision only)
    if r.location and slots.get("attribute"):
        attr = slots["attribute"]["value"]
        facts = repo.current_facts(r.location["location_id"], attr, sv("element"))
        if not facts and slots.get("element"):
            facts = repo.current_facts(r.location["location_id"], attr)
        if not facts and attr == "stirrup_spacing":
            attr = "rebar_spacing"
            facts = repo.current_facts(r.location["location_id"], attr)
        if spoken_drawing and len(facts) > 1:
            facts = ([f for f in facts if f["drawing_number"] == spoken_drawing]
                     + [f for f in facts if f["drawing_number"] != spoken_drawing])
        r.attribute = attr
        elements = list(dict.fromkeys(f["element"] for f in facts))
        if not slots.get("element") and len(elements) > 1:
            r.missing.append({"kind": "missing_critical_field", "severity": "clarify",
                              "detail": "element ambiguous",
                              "evidence": {"field": "element", "candidates": elements}})
            facts = []
        if facts:
            f = _norm_fact(facts[0])
            r.fact = f
            r.element = f["element"]
            r.unit = f.get("unit")
            r.drawing = repo.drawing_by_id(f["drawing_id"])
        else:
            r.element = sv("element")
            r.drawing = (repo.latest_drawing(spoken_drawing) if spoken_drawing
                         else repo.latest_drawing_for_location(r.location["location_id"], level))
    elif r.location:
        r.element = sv("element")
        r.drawing = (repo.latest_drawing(spoken_drawing) if spoken_drawing
                     else repo.latest_drawing_for_location(r.location["location_id"], level))

    if not r.unit:
        r.unit = _coalesce(
            sv("unit"),
            "mm" if (slots.get("attribute") and slots["attribute"]["value"] in
                     ["rebar_spacing", "stirrup_spacing", "cover", "thickness", "rebar_dia", "size"])
            else None,
        )
    if slots.get("value"):
        r.value = _to_unit(slots["value"]["value"], sv("unit"), r.unit)

    f = r.fact
    d = r.drawing
    # spoken drawing that doesn't govern this location/attribute
    if f and spoken_drawing and spoken_drawing != f["drawing_number"]:
        r.contradictions.append({
            "kind": "unknown_drawing", "severity": "clarify",
            "detail": f"{spoken_drawing} does not govern this element; {f['drawing_number']} {f['revision']} does",
            "evidence": {"drawing_number": sv("drawingNumber"), "drawing_id": f["drawing_id"],
                         "revision": f["revision"], "issued_on": f.get("issued_on"),
                         "candidates": [f["drawing_number"]]},
        })

    # ---------------------------------------- revision_mismatch
    if d and slots.get("revisionClaimed") and slots["revisionClaimed"]["value"] != d["revision"]:
        old = (repo.fact_on_revision(d["drawing_number"], slots["revisionClaimed"]["value"],
                                     f["location_id"], f["attribute"]) if f else None)
        # If the claimed (superseded) revision's value equals what was actually observed, the
        # revision reference is just the *explanation* for the dimension_mismatch that the next
        # block raises (e.g. "shuttering lag gayi per R1" -> 125 = R1 value). Not a separate flag.
        _explains_dim = (old is not None and _jsnum(old.get("value_num")) is not None
                         and r.value is not None and _jsnum(old.get("value_num")) == r.value)
        if _explains_dim:
            pass
        else:
            r.contradictions.append({
            "kind": "revision_mismatch", "severity": "flag",
            "detail": f"Claimed {d['drawing_number']} {slots['revisionClaimed']['value']}; "
                      f"latest For Construction is {d['revision']}",
            "evidence": {
                "drawing_id": d["drawing_id"], "drawing_number": d["drawing_number"],
                "revision": d["revision"], "issued_on": d.get("issued_on"),
                "via_rfi": _coalesce(f.get("via_rfi") if f else None,
                                     (repo.rfi_for_drawing(d["drawing_id"]) or {}).get("rfi_id"), None),
                "code_ref": (f.get("code_ref") if f else None),
                "expected": (f.get("value_num") if f else None),
                "unit": (f.get("unit") if f else None),
                "claimed_revision": slots["revisionClaimed"]["value"],
                "claimed_revision_value": _coalesce(_jsnum(old.get("value_num")) if old else None,
                                                    sv("drawingValueClaimed"), None),
            },
        })
    elif (f and slots.get("drawingValueClaimed") and f.get("value_num") is not None
          and abs(_to_unit(slots["drawingValueClaimed"]["value"], sv("unit"), f.get("unit"))
                  - f["value_num"]) > (f.get("tolerance") or 0)):
        older = next(
            (o for o in repo.facts_any_revision(f["drawing_number"], f["location_id"], f["attribute"])
             if o.get("value_num") == slots["drawingValueClaimed"]["value"] and o.get("revision") != f["revision"]),
            None,
        )
        r.contradictions.append({
            "kind": "revision_mismatch" if older else "dimension_mismatch", "severity": "flag",
            "detail": (f"Value {slots['drawingValueClaimed']['value']} is from superseded {older['revision']}"
                       if older else
                       f"Drawing value claimed {slots['drawingValueClaimed']['value']} ≠ latest {f['value_num']}"),
            "evidence": {
                "drawing_id": f["drawing_id"], "drawing_number": f["drawing_number"],
                "revision": f["revision"], "issued_on": f.get("issued_on"),
                "via_rfi": _coalesce(f.get("via_rfi"), None),
                "code_ref": f.get("code_ref"), "expected": f.get("value_num"), "unit": f.get("unit"),
                "tolerance": f.get("tolerance"), "claimed": slots["drawingValueClaimed"]["value"],
                "claimed_revision": (older.get("revision") if older else None),
                "claimed_revision_value": _coalesce(_jsnum(older.get("value_num")) if older else None, None),
            },
        })

    # ---------------------------------------- dimension_mismatch (observed vs latest fact)
    if f and r.value is not None and f.get("value_num") is not None:
        diff = abs(r.value - f["value_num"])
        tol = f.get("tolerance") or 0
        if diff > tol:
            r.contradictions.append({
                "kind": "dimension_mismatch", "severity": "flag",
                "detail": f"Observed {r.value} {f.get('unit')} vs {f['value_num']} ±{tol}",
                "evidence": {"drawing_id": f["drawing_id"], "drawing_number": f["drawing_number"],
                             "revision": f["revision"], "issued_on": f.get("issued_on"),
                             "via_rfi": _coalesce(f.get("via_rfi"), None), "code_ref": f.get("code_ref"),
                             "expected": f["value_num"], "claimed": r.value, "tolerance": tol,
                             "unit": f.get("unit")},
            })

    # de-duplicate kinds (keep first of each kind)
    seen: set[str] = set()
    deduped = []
    for c in r.contradictions:
        if c["kind"] in seen:
            continue
        seen.add(c["kind"])
        deduped.append(c)
    r.contradictions = deduped
    return r
