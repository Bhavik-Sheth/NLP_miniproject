"""Deterministic English reply templates for the default Talk experience.

Safety decisions stay in ``contradictions.py`` and ``dialogue.py``; this module only
changes the wording presented to the manager.
"""
from __future__ import annotations

import re

from .replies import attr_label, level_label, loc_label, spoken_date, to_speech

ACT = {"hot_work": "hot work", "pour": "concrete pouring", "height": "work at height", "excavation": "excavation"}


def R(text: str) -> dict:
    return {"text": text, "speech": to_speech(text)}


reply = R


def _v(slots: dict, key: str):
    slot = slots.get(key)
    return slot["value"] if slot else None


def _short(items: list[str] | None) -> str:
    if not items:
        return ""
    values = [re.split(r"[,(—;]| - ", item)[0].strip() for item in items]
    return "; ".join(values[:2]) + (f", plus {len(values) - 2} more" if len(values) > 2 else "")


def challenge_reply(c, slots: dict, prefix: str = "") -> dict:
    parts = [prefix] if prefix else []
    loc, attr = loc_label(c, slots), attr_label(c.attribute or _v(slots, "attribute"))
    for issue in c.contradictions:
        evidence, kind = issue["evidence"], issue["kind"]
        if kind == "revision_mismatch":
            line = f"The latest revision of drawing {evidence.get('drawing_number')} is {evidence.get('revision')}, issued {spoken_date(evidence.get('issued_on'))}."
            if evidence.get("expected") is not None:
                line += f" It shows {attr} at {loc} as {evidence['expected']} {evidence.get('unit') or 'mm'}."
            if evidence.get("via_rfi"):
                line += f" This is confirmed by {evidence['via_rfi']}."
            parts.append(line)
        elif kind == "dimension_mismatch":
            parts.append(f"You reported {attr} at {loc} as {evidence.get('claimed')} {evidence.get('unit') or 'mm'}, but {evidence.get('drawing_number')} {evidence.get('revision')} shows {evidence.get('expected')} {evidence.get('unit') or 'mm'}, with a tolerance of plus or minus {evidence.get('tolerance') or 0}.")
        elif kind == "unknown_drawing":
            parts.append(f"Drawing {evidence.get('drawing_number')} is not in the project register.")
        else:
            parts.append(issue["detail"])
    parts.append("Would you like to log the observation, raise an RFI, or raise an NCR?")
    return R(" ".join(parts))


def unknown_drawing_reply(issue: dict) -> dict:
    choices = ", ".join((issue["evidence"].get("candidates") or [])[:4])
    return R(f"Drawing {issue['evidence'].get('drawing_number')} is not in the register. Please repeat the drawing number" + (f". Available matches are {choices}" if choices else "") + ". Nothing will be logged until it is clear.")


def missing_reply(c, slots: dict) -> dict:
    missing = c.missing[0]
    field = missing["evidence"].get("field")
    if field == "level":
        choices = " or ".join(level_label(item.split(":")[2]) for item in (missing["evidence"].get("candidates") or []))
        return R(f"Which level is {_v(slots, 'grid') or _v(slots, 'zone')} on — {choices}?")
    if field == "element":
        return R(f"Which element is this at {loc_label(c, slots)} — {' or '.join(missing['evidence'].get('candidates') or [])}?")
    if field == "location_unknown":
        return R(f"{missing['evidence'].get('claimed')} is not in the project register. Please repeat the grid line.")
    if field == "location":
        return R("Please specify the location: which grid line and level? For example, C-5, Level 3.")
    if field == "attribute":
        return R(f"What did you check at {loc_label(c, slots) or 'that location'} — spacing, cover, or thickness?")
    if field == "value":
        return R(f"What is the {attr_label(c.attribute or _v(slots, 'attribute')) or 'measurement'}? Please give it in millimetres.")
    return R("I need a little more detail: location, what you checked, and the measurement.")


def confirm_slots_reply(names: list[str], slots: dict, resolved_drawing: str | None = None) -> dict:
    said = ", ".join(str(_v(slots, name) or name) for name in names)
    return R(f"I could not hear that clearly. I understood: {said}. Is that correct?")


def blocker_reply(c, slots: dict, attempted: str | None = None) -> dict:
    parts = [f"{attempted} is not allowed yet." if attempted else "Stop work for now."]
    loc = loc_label(c, slots)
    for blocker in c.blockers:
        evidence = blocker["evidence"]
        if blocker["kind"] == "permit_blocker":
            activity = ACT.get(_v(slots, "activity") or "", "this work")
            parts.append(f"At {loc}, the {activity} permit {evidence.get('permit_id') or ''} has mandatory checks still pending: {_short(evidence.get('checks'))}. Work cannot start until they are confirmed.")
        elif blocker["kind"] == "hold_point_blocker":
            parts.append(f"The pre-pour hold point at {loc} is not released: {_short(evidence.get('items'))}. Concrete pouring cannot begin.")
    parts.append("Would you like to stop work, raise an NCR, or cancel?")
    return R(" ".join(parts))


def readback_reply(c, slots: dict, prefix: str = "") -> dict:
    loc = loc_label(c, slots)
    drawing = f"{c.drawing['drawing_number']} {c.drawing['revision']}" if c.drawing else None
    if c.mode == "activity":
        text = f"I found no blocker for {ACT.get(_v(slots, 'activity') or '', 'this work')} at {loc}."
    elif c.mode == "defect":
        text = f"I understood a {_v(slots, 'defect') or 'defect'} on {_v(slots, 'element') or 'the element'} at {loc}."
    else:
        text = f"At {loc}, {c.element or _v(slots, 'element') or ''} {attr_label(c.attribute)} is {c.value} {c.unit or 'mm'}" + (f", which matches {drawing}." if c.fact and drawing else ".")
    return R(f"{prefix + ' ' if prefix else ''}{text} Log it?")


def done_reply(decision: str, obs_id: str | None = None, rfi_id: str | None = None, drawing_label: str | None = None) -> dict:
    if decision == "log_observation": return R(f"Observation {obs_id} has been logged" + (f" and linked to {drawing_label}." if drawing_label else "."))
    if decision == "raise_rfi": return R(f"{rfi_id} has been raised and linked to observation {obs_id}.")
    if decision == "raise_ncr": return R(f"The observation {obs_id} has been logged for an NCR. Please notify the QA team.")
    if decision == "stop_work": return R(f"A stop-work instruction has been logged as {obs_id}. Please inform the safety officer now.")
    if decision == "cancel": return R("Cancelled. Nothing has been logged.")
    return R("Okay.")


REFUSE = {"confirmFirst": "Please confirm that first.", "clarifyFirst": "Before I log this:", "ambiguousYes": "Do you want to log the observation or raise an RFI?", "rfiDeclined": "Okay, no RFI. Shall I log the observation?", "nothing": "I am listening. Please give the location, what you checked, and the measurement — for example, C-5 spacing 180 mm."}

DECISION_LABEL = {"log_observation": "Logging the observation", "raise_rfi": "Raising an RFI", "raise_ncr": "Raising an NCR", "stop_work": "Stopping work", "cancel": "Cancelling"}
