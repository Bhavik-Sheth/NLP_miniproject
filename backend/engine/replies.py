"""Deterministic Hinglish reply templates.

Faithful 1:1 port of app/lib/engine/replies.ts. Two renderings per reply: ``text``
(display) and ``speech`` (TTS-friendly).
"""
from __future__ import annotations

import re

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def spoken_date(iso: str | None) -> str:
    if not iso:
        return ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", iso)
    return f"{int(m.group(3))} {MONTHS[int(m.group(2)) - 1]}" if m else iso


ATTR_HI = {
    "rebar_spacing": "rebar spacing", "stirrup_spacing": "stirrup spacing", "cover": "cover",
    "thickness": "thickness", "rebar_dia": "bar dia", "size": "size", "grade": "grade",
    "bar_count": "bar count",
}


def attr_label(a: str | None) -> str:
    if not a:
        return ""
    return ATTR_HI.get(a) or a.replace("_", " ")


ACT_HI = {"hot_work": "hot work", "pour": "dhalai", "height": "height work", "excavation": "khudai"}


def level_label(l: str | None) -> str:
    if not l:
        return ""
    return re.sub(r"^L(\d+)$", r"Level \1", l)


def _v(s: dict, k: str):
    sl = s.get(k)
    return sl["value"] if sl else None


def loc_label(c, s: dict) -> str:
    loc = c.location
    if loc:
        seg = loc["location_id"].split(":")[1] if ":" in loc["location_id"] else loc["location_id"]
        if (loc.get("grid") or seg) == "Slab":
            return f"{level_label(loc.get('level'))} slab"
        head = loc.get("grid") or loc.get("zone") or seg
        head = re.sub(r"^Zone([A-Z])$", r"Zone \1", head)
        return f"{head}, {level_label(loc.get('level'))}"
    return ", ".join(x for x in [_v(s, "grid") or _v(s, "zone"), level_label(_v(s, "level"))] if x)


def to_speech(t: str) -> str:
    t = re.sub(r"(\d+(?:\.\d+)?)\s?mm\b", r"\1 millimeter", t)
    t = re.sub(r"±\s?(\d+)", r"plus minus \1", t)
    t = re.sub(r"\b(RFI|NCR)-([A-Z]{2,4})-0*(\d+)", lambda m: f"{' '.join(m.group(1))} {' '.join(m.group(2))} {m.group(3)}", t)
    t = re.sub(r"\bSSB-([A-Z]+)-([A-Z0-9]+)-(\d{3})\b", lambda m: f"S S B {' '.join(m.group(1))} {m.group(2)} {m.group(3)}", t)
    t = re.sub(r"\bRFI-0*(\d+)", lambda m: f"R F I {m.group(1)}", t)
    t = re.sub(r"\bNCR\b", "N C R", t)
    t = re.sub(r"\bOBS-0*(\d+)", lambda m: f"observation number {m.group(1)}", t)
    t = re.sub(r"\bHWP-0*(\d+)", lambda m: f"H W P {m.group(1)}", t)
    t = re.sub(r"\b([A-Z])-(\d{3})\b", r"\1 \2", t)
    t = re.sub(r"\b([A-H])-(\d{1,2})\b", r"\1 \2", t)
    t = re.sub(r"\bR(\d+)\b", r"revision \1", t)
    t = re.sub(r"\bL(\d+)\b", r"level \1", t)
    t = re.sub(r"QC-[A-Z]+-[A-Z]+-\d+", "checklist", t)
    t = re.sub(r"\bCL-[A-Z0-9-]+", "", t)
    t = re.sub(r"—", ", ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def R(text: str) -> dict:
    return {"text": text, "speech": to_speech(text)}


reply = R


def challenge_reply(c, s: dict, prefix: str = "") -> dict:
    parts: list[str] = []
    if prefix:
        parts.append(prefix)
    loc = loc_label(c, s)
    attr = attr_label(c.attribute or _v(s, "attribute"))
    for k in c.contradictions:
        parts.append(_describe(k, c, s, loc, attr))
    has_dim = any(k["kind"] == "dimension_mismatch" for k in c.contradictions)
    parts.append(
        "Kya aap observation log karna chahte hain, RFI raise karna chahte hain, ya NCR?"
        if has_dim else
        "Kya aap observation log karna chahte hain, ya RFI raise karna chahte hain?"
    )
    return R(" ".join(parts))


def _describe(k: dict, c, s: dict, loc: str, attr: str) -> str:
    e = k["evidence"]
    kind = k["kind"]
    if kind == "revision_mismatch":
        t = (f"Drawing {e.get('drawing_number')} ki latest revision {e.get('revision')} hai, "
             f"jo {spoken_date(e.get('issued_on'))} ko issue hui thi.")
        if e.get("expected") is not None:
            t += f" Usme {loc} ki {attr} {e['expected']} {e.get('unit') or 'mm'} hai."
        if e.get("via_rfi"):
            t += f" {e['via_rfi']} ne yeh confirm kiya tha."
        if e.get("claimed_revision"):
            t += (f" {e['claimed_revision']} superseded hai"
                  + (f", usme {e['claimed_revision_value']} tha"
                     if e.get("claimed_revision_value") is not None else "") + ".")
        if (c.value is not None and e.get("expected") is not None
                and not any(x["kind"] == "dimension_mismatch" for x in c.contradictions)):
            t += f" Aapka {c.value} {c.unit or 'mm'} latest drawing se match karta hai."
        return t
    if kind == "dimension_mismatch":
        if e.get("claimed") is not None and c.value is not None and e["claimed"] == c.value:
            return (f"Dhyan dijiye: {loc} pe aapne {attr} {c.value} {e.get('unit') or 'mm'} bola, "
                    f"lekin {e.get('drawing_number')} {e.get('revision')} mein {e.get('expected')} "
                    f"{e.get('unit') or 'mm'} hai, tolerance ±{e.get('tolerance') or 0}. "
                    f"Yeh {abs(e['claimed'] - e['expected'])} {e.get('unit') or 'mm'} ka farak hai."
                    + (f" Reference {e['code_ref']}." if e.get("code_ref") else ""))
        return (f"Aapne drawing mein {e.get('claimed')} bataya, lekin {e.get('drawing_number')} "
                f"{e.get('revision')} mein {e.get('expected')} {e.get('unit') or 'mm'} hai.")
    if kind == "unknown_drawing":
        if e.get("drawing_id"):
            return (f"Drawing {e.get('drawing_number')} is location ke liye applicable nahi hai; "
                    f"{e['drawing_id'].replace('@', ' ')} lagu hai, issue {spoken_date(e.get('issued_on'))}.")
        return f"Drawing {e.get('drawing_number')} register mein nahi mili."
    return k["detail"]


def unknown_drawing_reply(k: dict) -> dict:
    cands = ", ".join((k["evidence"].get("candidates") or [])[:4])
    return R(f"Drawing {k['evidence'].get('drawing_number')} register mein nahi mili. "
            f"Kripya drawing number dobara bataiye"
            + (f" — register mein {cands} hain" if cands else "")
            + ". Tab tak kuch log nahi hoga.")


def missing_reply(c, s: dict) -> dict:
    m = c.missing[0]
    f = m["evidence"].get("field")
    if f == "level":
        levels = " ya ".join(level_label(i.split(":")[2]) for i in (m["evidence"].get("candidates") or []))
        return R(f"{_v(s, 'grid') or _v(s, 'zone')} kaunse level pe hai — {levels}?")
    if f == "element":
        return R(f"{loc_label(c, s)} pe kaunsa element — {' ya '.join(m['evidence'].get('candidates') or [])}?")
    if f == "location_unknown":
        return R(f"{m['evidence'].get('claimed')} project register mein nahi mila. Grid line dobara bataiye.")
    if f == "location":
        return R("Location bataiye — kaunsi grid line aur level? Jaise C-5, Level 3.")
    if f == "attribute":
        return R(f"{loc_label(c, s) or 'Wahan'} pe kya check kiya — spacing, cover ya thickness?")
    if f == "value":
        return R(f"{attr_label(c.attribute or _v(s, 'attribute')) or 'Value'} kitni hai? mm mein bataiye.")
    return R("Thoda aur detail chahiye. Location, attribute aur value bataiye.")


_SLOT_SAY = {
    "grid": lambda s: f"grid {_v(s, 'grid')}",
    "level": lambda s: level_label(_v(s, "level")),
    "zone": lambda s: f"{_v(s, 'zone')}",
    "attribute": lambda s: attr_label(_v(s, "attribute")),
    "value": lambda s: f"{_v(s, 'value')} {_v(s, 'unit') or 'mm'}",
    "drawingNumber": lambda s: f"drawing {_v(s, 'drawingNumber')}",
    "element": lambda s: f"{_v(s, 'element')}",
    "activity": lambda s: ACT_HI.get(_v(s, "activity") or "") or str(_v(s, "activity")),
}


def confirm_slots_reply(names: list[str], s: dict, resolved_drawing: str | None = None) -> dict:
    said = ", ".join(
        (f"drawing {resolved_drawing}" if (n == "drawingNumber" and resolved_drawing)
         else (_SLOT_SAY[n](s) if n in _SLOT_SAY else n))
        for n in names
    )
    return R(f"Awaaz saaf nahi thi. Maine suna: {said}. Kya yeh sahi hai? Haan ya nahi boliye.")


def _short_list(items: list[str] | None) -> str:
    if not items:
        return ""
    short = [re.split(r"[,(—;]| - ", i)[0].strip() for i in items]
    head = "; ".join(short[:2])
    return f"{head}, aur {len(items) - 2} aur items" if len(items) > 2 else head


def blocker_reply(c, s: dict, attempted: str | None = None) -> dict:
    parts: list[str] = []
    if attempted:
        parts.append(f"{attempted} abhi allowed nahi hai.")
    parts.append("Ruko.")
    loc = loc_label(c, s)
    for b in c.blockers:
        if b["kind"] == "permit_blocker":
            act_lbl = ACT_HI.get(_v(s, "activity") or "") or "kaam"
            if b["evidence"].get("permit_id"):
                parts.append(
                    f"{loc} pe {act_lbl} permit {b['evidence']['permit_id']} active hai, lekin "
                    f"mandatory check pending hai: {_short_list(b['evidence'].get('checks'))}. "
                    f"Jab tak yeh confirm na ho, {act_lbl} shuru nahi ho sakta."
                )
            else:
                parts.append(
                    f"{loc} pe {ACT_HI.get(_v(s, 'activity') or '') or 'is kaam'} ke liye koi active permit nahi hai."
                )
        elif b["kind"] == "hold_point_blocker":
            parts.append(
                f"{loc} ka pre-pour checklist {b['evidence'].get('checklist')} ka hold point release nahi hua: "
                f"{_short_list(b['evidence'].get('items'))}. Dhalai shuru nahi ho sakti."
            )
    parts.append("Kaam rokna hai, NCR raise karna hai, ya cancel?")
    return R(" ".join(parts))


def readback_reply(c, s: dict, prefix: str = "") -> dict:
    loc = loc_label(c, s)
    d = f"{c.drawing['drawing_number']} {c.drawing['revision']}" if c.drawing else None
    t = (prefix + " ") if prefix else ""
    if c.mode == "defect":
        t += (f"{loc} pe {_v(s, 'element') or ''} {_v(s, 'defect')}"
              + (f", drawing {d} se link hoga" if d else "") + ".")
    elif c.mode == "activity":
        t += f"{loc} pe {ACT_HI.get(_v(s, 'activity') or '')} ke liye koi blocker nahi mila."
    else:
        t += (f"{loc}, {c.element or _v(s, 'element') or ''} {attr_label(c.attribute)} {c.value} "
              f"{c.unit or 'mm'}"
              + (f" — {d} ke hisaab se sahi hai" if (c.fact and d)
                 else (f" — drawing {d}" if d else "")) + ".")
    t = re.sub(r"\s+", " ", t).replace(" ,", ",")
    return R(f"{t} Log kar doon?")


def done_reply(decision: str, obs_id: str | None = None, rfi_id: str | None = None,
               drawing_label: str | None = None) -> dict:
    if decision == "log_observation":
        return R(f"Observation {obs_id} log ho gaya"
                 + (f", drawing {drawing_label} ke saath link kiya" if drawing_label else "") + ".")
    if decision == "raise_rfi":
        return R(f"{rfi_id} raise ho gaya, status Open. Observation {obs_id} usse link kar diya.")
    if decision == "raise_ncr":
        return R(f"NCR ke liye observation {obs_id} log ho gaya. QA team ko notify kijiye.")
    if decision == "stop_work":
        return R(f"Kaam rokne ka order {obs_id} log ho gaya. Safety officer ko turant inform kijiye.")
    if decision == "cancel":
        return R("Theek hai, cancel kar diya. Kuch log nahi hua.")
    return R("Theek hai.")


REFUSE = {
    "confirmFirst": "Pehle confirm kijiye, phir log karunga.",
    "clarifyFirst": "Log karne se pehle ek baat:",
    "ambiguousYes": "Log karna hai ya RFI raise karna hai? Saaf boliye.",
    "rfiDeclined": "Theek hai, RFI nahi. Toh observation log kar doon?",
    "nothing": "Main sun raha hoon. Location, attribute aur value boliye — jaise, C-5 pe spacing 180 mm.",
}

DECISION_LABEL = {
    "log_observation": "Observation log karna",
    "raise_rfi": "RFI raise karna",
    "raise_ncr": "NCR raise karna",
    "stop_work": "Kaam rokna",
    "cancel": "Cancel",
}
