"""Deterministic answers to site QUESTIONS ("what is the cover at E-1?", "and at E-2?").

The observation flow (dialogue.py) asks for missing fields until it can check a claim. A
question has no claim to check, so routing it through that flow produced a follow-up prompt
("what is the cover? give it in mm") instead of an answer. This module answers from the
same SQLite record: latest For-Construction facts, open hold points / permits / RFIs at the
location, and project memory as a fallback. Nothing here writes.
"""
from __future__ import annotations

import re

from . import memory
from .replies import attr_label, level_label, spoken_date

_Q_WORDS = re.compile(
    r"^(what|whats|which|how|when|where|who|why|is|are|was|were|does|do|did|can|could|should|"
    r"will|tell|show|give|list|check|any|kya|kitna|kitni|kitne|kaun|kaunsa|kaunsi|kab|kahan|"
    r"batao|bataiye|bata|and|what about|how about)\b")
_Q_ANYWHERE = re.compile(
    r"\?|\b(kya hai|kitna hai|kitni hai|kya tha|batao|bataiye|required|should be|as per (the )?drawing|"
    r"what about|how about|status of|latest (drawing|revision)|any (open|pending)|is there|are there|"
    r"where did|where does|come from|you said|explain|why is|why did|how come|all information|blockers?)\b")


NOT_FOUND = "I could not find that in the project record. Give me a grid line, drawing number or RFI."
KB_NOT_FOUND = "That isn't in the project record or the knowledge base."

# A number in a KNOWLEDGE question ("lap length 16 mm M25?", "curing period IS 456?") is not a site
# measurement: there is no location or drawing to check it against.
_KNOWLEDGE_CUE = re.compile(
    r"\b(IS|IRC|SP)\s?\d{2,5}\b|\b(lap|development|anchorage) length\b|\bcuring\b|\brates?\b|\bprices?\b|"
    r"\bperiod\b|\bchecklist\b|\btemplate\b|\bprocedure\b|\bminimum\b|\bmaximum\b|\bhow many days\b|"
    r"\bkitne din\b|\bclause\b|\bcode\b|\bstandard\b|\bdaam\b|\bbhav\b", re.I)


def is_question(raw: str, ex) -> bool:
    """A question asks for the record; it does not assert a measured value or a decision."""
    t = (ex.normalized or raw or "").strip().lower()
    if not t or ex.decision or ex.affirm or ex.deny:
        return False
    if ex.value and not re.search(r"\b(should|required|as per|allowed|ok|okay|within)\b", t):
        if (not (ex.grid or ex.zone or ex.drawingNumber) and _KNOWLEDGE_CUE.search(raw or t)
                and ("?" in (raw or "") or _Q_WORDS.search(t))):
            return True
        return False  # "E-1 cover 30 mm" is an observation, even with a trailing "?"
    return bool(_Q_WORDS.search(t) or _Q_ANYWHERE.search(t))


# ---------------------------------------------------------------- relevance gate (no confident wrong answers)
_GENERIC = {
    "what", "whats", "which", "how", "when", "where", "who", "why", "is", "are", "was", "were", "does", "do", "did",
    "can", "could", "should", "will", "would", "tell", "show", "give", "list", "check", "any", "the", "a", "an", "of",
    "for", "at", "in", "on", "to", "and", "or", "me", "us", "my", "our", "we", "i", "please", "status", "open",
    "pending", "current", "latest", "all", "active", "there", "kya", "hai", "hain", "ka", "ki", "ke", "ko", "pe",
    "par", "mein", "batao", "bataiye", "bata", "about", "now", "so", "far", "happened", "happen", "yesterday", "today",
    "kal", "aaj", "catch", "up", "summary", "progress", "update", "s", "it", "this", "that", "be", "been", "have",
    "has", "had", "with", "from", "by", "as", "per", "not", "yet", "still", "abhi", "tak", "kaun", "kaunsa", "kaunsi",
    "kab", "kahan", "what's", "site", "project", "things", "thing", "anything", "everything", "else",
}


def _content_terms(raw: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (raw or "").lower()) if len(w) >= 2 and w not in _GENERIC]


def _covers(terms: list[str], blob: str) -> bool:
    """Every content word of the question appears in the candidate answer (5-char stem match for long words)."""
    b = (blob or "").lower()
    b_compact = re.sub(r"[^a-z0-9]", "", b)
    return all(t in b or (len(t) > 5 and t[:5] in b) or (t.isalnum() and any(c.isdigit() for c in t)
                                                           and t in b_compact) for t in terms)


def _memory_answer(repo, raw: str) -> dict | None:
    """Unresolved questions go to the memory layer (hybrid retrieval + grounded LLM). None on abstain,
    timeout or when the memory layer is unavailable — the caller keeps NOT_FOUND."""
    import os
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as FutTimeout

    if os.getenv("VESPER_MEMORY_ASK", "1").strip().lower() in ("0", "false", "no", "off"):
        return None
    try:
        from memory import api as memapi  # type: ignore
        from memory import config as memcfg  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    global _mem_pool
    if _mem_pool is None:
        _mem_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="engine-memory")
    fut = _mem_pool.submit(memapi.ask, raw, org_id=memcfg.DEMO_ORG, project_id=repo.project_id)
    try:
        res = fut.result(timeout=float(os.getenv("VESPER_MEMORY_ASK_TIMEOUT", "8")))
    except (FutTimeout, Exception):  # noqa: BLE001
        return None
    if not res or res.get("abstain"):
        return None
    return res


_mem_pool = None


def _num(v):
    return int(v) if isinstance(v, float) and v.is_integer() else v


def _loc_name(loc: dict) -> str:
    head = loc.get("grid") or loc.get("zone") or loc["location_id"].split(":")[1]
    lvl = level_label(loc.get("level"))
    return f"{head}, {lvl}" if lvl else head


def _fact_line(f: dict) -> str:
    val = _num(f.get("value_num")) if f.get("value_num") is not None else f.get("value_text")
    tol = _num(f.get("tolerance"))
    s = f"{f.get('element') or ''} {attr_label(f['attribute'])} is {val}{(' ' + f['unit']) if f.get('unit') else ''}"
    if tol:
        s += f" plus or minus {tol}"
    s += f", per {f['drawing_number']} {f['revision']}"
    if f.get("issued_on"):
        s += f" issued {spoken_date(f['issued_on'])}"
    if f.get("via_rfi"):
        s += f" after {f['via_rfi']}"
    if f.get("code_ref"):
        s += f" ({f['code_ref']})"
    return s.strip()


def answer(repo, raw: str, ex, ctx: dict) -> dict:
    """Return {text, facts, location_id, context}. `ctx` carries the previous question so a
    follow-up like "and at E-2?" or "what about thickness?" keeps the missing half."""
    sv = lambda k: (getattr(ex, k) or {}).get("value") if getattr(ex, k, None) else None  # noqa: E731
    grid, zone, level = sv("grid"), sv("zone"), sv("level")
    element, attribute = sv("element"), sv("attribute")
    if not (grid or zone or (element == "slab" and level)):
        grid, zone = grid or ctx.get("grid"), zone or ctx.get("zone")
        level = level or ctx.get("level")
    attribute = attribute or (ctx.get("attribute") if (grid or zone) and not _asks_everything(raw) else None)
    element = element or ctx.get("element") if attribute else element
    new_ctx = {"grid": grid, "zone": zone, "level": level, "element": element, "attribute": attribute}

    locs = repo.resolve_location({"grid": grid, "zone": zone, "level": level, "element": element})
    facts: list[dict] = []
    loc = None
    for cand in locs:
        rows = (repo.current_facts(cand["location_id"], attribute, element)
                or (repo.current_facts(cand["location_id"], attribute) if attribute else [])
                or ([] if attribute else repo.current_facts(cand["location_id"])))
        if attribute == "stirrup_spacing" and not rows:
            rows = repo.current_facts(cand["location_id"], "rebar_spacing")
        if rows:
            loc, facts = cand, rows
            break
    loc = loc or (locs[0] if len(locs) == 1 else None)

    parts: list[str] = []
    # an RFI named in the question is explained from the register (and linked to a drawing it names)
    rfi_ids = _rfi_ids(raw)
    if rfi_ids and not ex.attribute:
        text = _explain_rfis(repo, rfi_ids, ex)
        if text:
            return {"text": text, "facts": [], "location_id": None, "context": dict(ctx), "resolved": True}
    # a level on its own ("everything for Level 3") is a level summary, not a grid lookup
    if level and sv("level") and not (sv("grid") or sv("zone") or ex.drawingNumber or sv("attribute")
                                      or sv("element")):
        text = _level_summary(repo, sv("level"))
        return {"text": text, "facts": [], "location_id": None, "context": {**new_ctx, "level": sv("level")},
                "resolved": True}
    topic = _topic(raw)
    if topic and not ex.attribute and not (ex.grid or ex.zone or ex.drawingNumber):  # own location beats carried context
        text = _topic_answer(repo, topic)
        # the topic word must BE the question: "any open RFIs?" yes, "today's steel rate?" no (a site diary
        # entry is not a steel rate) — every other content word has to appear in the topic answer
        rest = _content_terms(dict(_TOPICS)[topic].sub(" ", raw.lower()))
        if _covers(rest, text):
            return {"text": text, "facts": [], "location_id": None, "context": dict(ctx), "resolved": True}
    if loc:
        name = _loc_name(loc)
        items = _open_items(repo, loc["location_id"])
        if attribute:
            # a specific question gets its answer first; open items follow as a short aside
            if facts:
                parts.append(f"At {name}: " + "; ".join(_fact_line(f) for f in facts[:2]) + ".")
            else:
                parts.append(f"I have no {attr_label(attribute)} on any current drawing for {name}.")
            parts += items[:1]
        else:
            # a general "what should I check" leads with blockers: that is what must be acted on
            parts += items
            if facts:
                n = 2 if items else 3
                parts.append(f"At {name}: " + "; ".join(_fact_line(f) for f in facts[:n]) + ".")
                if len(facts) > n:
                    parts.append(f"{len(facts) - n} more checks are on record here.")
        if not parts:
            parts.append(f"Nothing open at {name}, and no drawing facts are recorded there.")
    elif len(locs) > 1:
        lv = " or ".join(sorted({level_label(l.get('level')) for l in locs if l.get("level")}))
        parts.append(f"{grid or zone} exists on more than one level — {lv}. Which one?")
    elif ex.drawingNumber:
        dn = repo.resolve_drawing_number(ex.drawingNumber["value"])
        latest = repo.latest_drawing(dn) if dn else None
        if latest:
            rfi = repo.rfi_for_drawing(latest["drawing_id"])
            parts.append(f"The latest For Construction revision of {dn} is {latest['revision']}, issued "
                         f"{spoken_date(latest.get('issued_on'))}" + (f", driven by {rfi['rfi_id']}" if rfi else "")
                         + (f". {latest['title']}." if latest.get("title") else "."))
        else:
            parts.append(f"Drawing {ex.drawingNumber['value']} is not in the register.")
    else:
        parts.append(_from_memory(repo, raw))

    text = " ".join(p for p in parts if p).strip()
    if text == NOT_FOUND:
        mem = _memory_answer(repo, raw)
        if mem:
            return {"text": mem.get("speech") or mem["answer"], "facts": [], "location_id": None,
                    "context": new_ctx, "resolved": True, "source": "memory", "memory_answer": mem["answer"],
                    "citations": mem.get("citations") or [], "confidence": mem.get("confidence")}
        if _KNOWLEDGE_CUE.search(raw or ""):  # a code / price / template question: don't ask for a grid line
            text = KB_NOT_FOUND
    return {"text": text, "facts": [f["fact_id"] for f in facts[:3]] if facts else [],
            "location_id": loc["location_id"] if loc else None, "context": new_ctx,
            "resolved": text not in (NOT_FOUND, KB_NOT_FOUND)}


_TOPICS = [
    ("blockers", re.compile(r"\b(blockers?|blocked|blocking|pending (items|issues|work|things)|what'?s pending|"
                            r"what is pending|holding (us|work|things) up|kya pending|kya ruka)\b")),
    ("rfi", re.compile(r"\brfis?\b")),
    ("hold", re.compile(r"\bhold[- ]?points?\b")),
    ("permit", re.compile(r"\bpermits?\b")),
    ("submittal", re.compile(r"\bsubmittals?\b")),
    ("drawing", re.compile(r"\b(drawings|drawing register|revisions)\b")),
    ("today", re.compile(r"\b(today|yesterday|progress|status|catch me up|summary|kal|aaj)\b")),
]


def _topic(raw: str) -> str | None:
    t = raw.lower()
    for name, rx in _TOPICS:
        if rx.search(t):
            return name
    return None


def _safe_all(repo, sql: str, args: tuple = ()) -> list[dict]:
    try:
        return repo._all(sql, args)
    except Exception:  # noqa: BLE001
        return []


def _rfi_ids(raw: str) -> list[str]:
    out = []
    for pfx, n in re.findall(r"\bRFI[\s\-]?(?:(?!(?:for|and|the|not|no|pe|par|ka|ki|ke|on|at|in|is|was|has)\b)"
                             r"([A-Za-z]{2,4})[\s\-]?)?(\d{1,4})\b", raw or "", re.I):
        out.append(f"RFI-{pfx.upper()}-{int(n):03d}" if pfx else f"RFI-{int(n):03d}")
    return list(dict.fromkeys(out))


def _explain_rfis(repo, ids: list[str], ex) -> str:
    dn = repo.resolve_drawing_number(ex.drawingNumber["value"]) if ex.drawingNumber else None
    out = []
    for rid in ids[:3]:
        r = repo._one("SELECT * FROM rfis WHERE rfi_id = ? AND project_id = ?", (rid, repo.project_id))
        if not r:
            out.append(f"{rid} is not in the RFI register.")
            continue
        loc = (r.get("location_id") or "").split(":", 1)[-1].replace(":", " ")
        s = (f"{rid}, {r['subject']}, is {str(r['status']).lower()}, raised {spoken_date(r.get('raised_on'))}"
             + (f" at {loc}" if loc else "") + (f" against drawing {r['drawing_ref']}" if r.get("drawing_ref") else "")
             + ".")
        if r.get("impact"):
            s += f" Impact: {r['impact']}."
        if dn and r.get("drawing_ref") == dn:
            latest = repo.latest_drawing(dn)
            if latest:
                s += (f" So {dn} {latest['revision']} is flagged because this RFI is still "
                      f"{str(r['status']).lower()}.")
        elif dn and r.get("drawing_ref") and r["drawing_ref"] != dn:
            s += f" It is not linked to {dn}."
        if r.get("response") and r["status"] != "Open":
            s += f" Answer: {r['response']}"
        out.append(s)
    return " ".join(out)


def _level_summary(repo, level: str) -> str:
    pid, name = repo.project_id, (level_label(level) or level)
    like = f"{pid}:%:{level}"
    holds = _safe_all(repo, "SELECT instance_id, planned_activity FROM v_open_hold_points WHERE location_id LIKE ?", (like,))
    permits = _safe_all(repo, "SELECT permit_id, permit_type, status FROM permits WHERE project_id = ? AND "
                              "status IN ('Active','Suspended') AND location_id LIKE ?", (pid, like))
    rfis = _safe_all(repo, "SELECT rfi_id, subject FROM rfis WHERE project_id = ? AND status = 'Open' "
                           "AND location_id LIKE ?", (pid, like))
    dwgs = _safe_all(repo, "SELECT drawing_number, revision FROM v_latest_drawings WHERE project_id = ? AND level = ? "
                           "ORDER BY drawing_number", (pid, level))
    nf = (_safe_all(repo, "SELECT COUNT(*) AS n FROM v_current_facts WHERE location_id LIKE ?", (like,)) or [{"n": 0}])[0]["n"]
    parts = []
    if holds:
        parts.append("Open hold points: " + "; ".join(
            f"{h['instance_id']} for {str(h.get('planned_activity') or '').replace('_', ' ')}" for h in holds) + ".")
    for p in permits:
        un = len(_safe_all(repo, "SELECT 1 FROM permit_checks WHERE permit_id = ? AND is_mandatory = 1 AND satisfied = 0",
                           (p["permit_id"],)))
        parts.append(f"Permit {p['permit_id']} ({p['permit_type'].replace('_', ' ')}) is {p['status'].lower()}"
                     + (f", {un} mandatory checks pending." if un else "."))
    if rfis:
        parts.append("Open RFIs: " + "; ".join(f"{r['rfi_id']}, {r['subject']}" for r in rfis[:4]) + ".")
    if dwgs:
        parts.append("Current drawings: " + ", ".join(f"{d['drawing_number']} {d['revision']}" for d in dwgs) + ".")
    if nf:
        parts.append(f"{nf} drawing checks are on record at {name}.")
    return f"{name}: " + " ".join(parts) if parts else f"Nothing is on record for {name}."


def _topic_answer(repo, topic: str) -> str:
    pid = repo.project_id
    if topic == "blockers":
        like = f"{pid}:%"
        out = []
        holds = _safe_all(repo, "SELECT instance_id, location_id, planned_activity, items_on_hold FROM v_open_hold_points "
                                "WHERE location_id LIKE ?", (like,))
        for h in holds:
            out.append(f"Hold point {h['instance_id']} at {h['location_id'].split(':', 1)[1]} for "
                       f"{str(h.get('planned_activity') or '').replace('_', ' ')} is not released"
                       + (f", {h['items_on_hold']} items on hold." if h.get("items_on_hold") else "."))
        blockers: dict[str, list[dict]] = {}
        for b in _safe_all(repo, "SELECT permit_id, permit_type, location_id, check_label FROM v_permit_blockers "
                                 "WHERE location_id LIKE ?", (like,)):
            blockers.setdefault(b["permit_id"], []).append(b)
        for pid_, rows in blockers.items():
            out.append(f"Permit {pid_} ({rows[0]['permit_type'].replace('_', ' ')}) at "
                       f"{rows[0]['location_id'].split(':', 1)[1]} is blocked on: "
                       + "; ".join(r["check_label"] for r in rows[:2]) + ".")
        rfis = _safe_all(repo, "SELECT rfi_id, subject FROM rfis WHERE project_id = ? AND status = 'Open' ORDER BY rfi_id", (pid,))
        if rfis:
            out.append("Open RFIs: " + "; ".join(f"{r['rfi_id']}, {r['subject']}" for r in rfis[:4]) + ".")
        return " ".join(out) if out else "Nothing is blocked: no open hold points, permit blockers or open RFIs."
    if topic == "rfi":
        rows = repo._all("SELECT rfi_id, subject FROM rfis WHERE project_id = ? AND status = 'Open' ORDER BY rfi_id", (pid,))
        return ("Open RFIs: " + "; ".join(f"{r['rfi_id']}, {r['subject']}" for r in rows[:4]) + "."
                if rows else "There are no open RFIs.")
    if topic == "hold":
        rows = repo._all("SELECT instance_id, location_id, planned_activity, notes FROM checklist_instances "
                         "WHERE project_id = ? AND status != 'Released'", (pid,))
        return (" ".join(f"Hold point {r['instance_id']} at {r['location_id'].split(':', 1)[1]} for "
                         f"{r['planned_activity']} is not released: {r.get('notes') or ''}".strip() for r in rows)
                if rows else "No hold points are open.")
    if topic == "permit":
        rows = repo._all("SELECT permit_id, permit_type, location_id, status FROM permits "
                         "WHERE project_id = ? AND status IN ('Active','Suspended')", (pid,))
        out = []
        for p in rows:
            un = [r["label"] for r in repo._all("SELECT label FROM permit_checks WHERE permit_id = ? AND "
                                                  "is_mandatory = 1 AND satisfied = 0", (p["permit_id"],))]
            out.append(f"{p['permit_id']} {p['permit_type'].replace('_', ' ')} at {p['location_id'].split(':', 1)[1]} "
                       f"is {p['status'].lower()}" + (f", {len(un)} mandatory checks pending" if un else ", all checks done"))
        return ("; ".join(out) + ".") if out else "No active permits."
    if topic == "submittal":
        rows = repo._all("SELECT submittal_id, material, status FROM submittals WHERE project_id = ? "
                         "AND status IN ('Under Review','Rejected')", (pid,))
        return ("Not cleared: " + "; ".join(f"{r['submittal_id']} {r['material']}, {r['status'].lower()}" for r in rows) + "."
                if rows else "All submittals are cleared.")
    if topic == "drawing":
        rows = repo._all("SELECT drawing_number, revision FROM v_latest_drawings WHERE project_id = ? "
                         "ORDER BY drawing_number", (pid,))
        return "Current For Construction drawings: " + ", ".join(f"{r['drawing_number']} {r['revision']}" for r in rows) + "."
    b = memory.site_brief(repo)
    logs = b.get("recent_daily_logs") or []
    head = f"On {logs[0]['log_date']}: {logs[0]['work_done']}" if logs else "No daily report yet."
    return head


def _asks_everything(raw: str) -> bool:
    return bool(re.search(r"\b(everything|all|status|open|pending|anything)\b", raw.lower()))


def _open_items(repo, location_id: str) -> list[str]:
    out: list[str] = []
    for hp in repo.hold_point_blockers(location_id):
        items = "; ".join(i["label"] for i in hp["items"][:2])
        out.append(f"Hold point {hp['ref']} is not released: {items}.")
    for p in repo._all("SELECT permit_id, permit_type, status FROM permits WHERE location_id = ? "
                       "AND status IN ('Active','Suspended')", (location_id,)):
        un = [r["label"] for r in repo._all(
            "SELECT label FROM permit_checks WHERE permit_id = ? AND is_mandatory = 1 AND satisfied = 0",
            (p["permit_id"],))]
        if un or p["status"] == "Suspended":
            out.append(f"Permit {p['permit_id']} ({p['permit_type'].replace('_', ' ')}) is {p['status'].lower()}"
                       + (f", pending: {'; '.join(un[:2])}." if un else "."))
    rfis = repo._all("SELECT rfi_id, subject FROM rfis WHERE location_id = ? AND status = 'Open'", (location_id,))
    if rfis:
        out.append("Open " + ", ".join(f"{r['rfi_id']} ({r['subject']})" for r in rfis[:2]) + ".")
    return out


def _from_memory(repo, raw: str) -> str:
    """Project-record recall, gated: a row is only used when it covers every content word of the question.
    Anything else is NOT_FOUND so the memory layer (or an honest 'not found') answers instead."""
    hit = memory.recall(repo, raw, limit=3)
    terms = _content_terms(raw)
    blob = lambda r: " ".join(str(v) for v in r.values() if v is not None)  # noqa: E731
    ok = lambda r: bool(terms) and _covers(terms, blob(r))  # noqa: E731
    if hit.get("current_facts"):  # only present when a location / drawing in the question resolved
        f = hit["current_facts"][0]
        return (f"{f['location_id'].split(':')[1]}: {f['element']} {attr_label(f['attribute'])} is "
                f"{_num(f['value'])} {f.get('unit') or ''} per {f['drawing']}.").replace(" .", ".")
    r = next((x for x in hit.get("rfis") or [] if ok(x)), None)
    if r:
        return f"{r['rfi_id']} — {r['subject']} — is {str(r['status']).lower()}." + (
            f" {r['impact']}." if r.get("impact") else "")
    o = next((x for x in hit.get("observations") or [] if ok(x)), None)
    if o:
        return f"Last related log was {o['observation_id']} on {str(o['at'])[:10]}: {o.get('spoken_text') or ''}"
    d = next((x for x in hit.get("daily_logs") or [] if ok(x)), None)
    if d:
        return f"On {d['log_date']}: {d['work_done']}"
    d = next((x for x in hit.get("drawings") or [] if ok(x)), None)
    if d:
        return f"{d['drawing_number']} {d['revision']} ({d['status']}), issued {spoken_date(d.get('issued_on'))}."
    ref = next((x for x in hit.get("reference_docs") or [] if ok(x)), None)
    if ref:
        return f"From {ref['doc_ref']}: {ref['snippet']}"
    return NOT_FOUND
