"""Deterministic Hinglish entity extractor. No network, no LLM.

Faithful 1:1 port of app/lib/parser/extract.ts.
"""
from __future__ import annotations

import re

from .numbers import devanagari_to_latin, normalize_numbers

LOW_CONFIDENCE = 0.7

SLOT_ATTRS = (
    "grid", "level", "zone", "element", "attribute", "value", "unit",
    "drawingNumber", "revisionClaimed", "drawingValueClaimed", "activity", "defect",
)


class Extraction:
    def __init__(self, normalized: str = "") -> None:
        self.normalized = normalized
        self.grid = None
        self.level = None
        self.zone = None
        self.element = None
        self.attribute = None
        self.value = None
        self.unit = None
        self.drawingNumber = None
        self.revisionClaimed = None
        self.drawingValueClaimed = None
        self.activity = None
        self.defect = None
        self.negatedGrids: list[str] = []
        self.negatedValues: list[float] = []
        self.decision = None
        self.rfiDeclined = False
        self.affirm = False
        self.deny = False
        self.isCorrection = False

    # dict-style access mirrors the TS `ex[k]` casts
    def __getitem__(self, k):
        return getattr(self, k)

    def __setitem__(self, k, v):
        setattr(self, k, v)

    def get(self, k, default=None):
        return getattr(self, k, default)


# ---------------------------------------------------------------- helpers
LETTER_WORDS: dict[str, str] = {
    "a": "A", "ay": "A", "ae": "A", "bee": "B", "be": "B", "b": "B", "bi": "B", "c": "C", "see": "C",
    "sea": "C", "si": "C", "cee": "C", "d": "D", "dee": "D", "di": "D", "e": "E", "ee": "E", "f": "F",
    "ef": "F", "eff": "F", "g": "G", "gee": "G", "jee": "G", "h": "H", "aitch": "H", "ech": "H",
}
SMALL_NUM_WORDS: dict[str, int] = {
    "one": 1, "two": 2, "to": 2, "too": 2, "three": 3, "four": 4, "for": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "ek": 1, "do": 2,
    "teen": 3, "tin": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12,
}
ORDINALS: dict[str, int] = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
    "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "pehli": 1, "pahli": 1, "pehla": 1,
    "pehle": 1, "doosri": 2, "dusri": 2, "dusra": 2, "doosra": 2, "doosre": 2, "dusre": 2, "teesri": 3,
    "tisri": 3, "teesra": 3, "teesre": 3, "tisre": 3, "chauthi": 4, "chautha": 4, "chauthe": 4,
    "paanchvi": 5, "panchvi": 5, "paanchve": 5, "chhathi": 6, "chhathe": 6, "saatvi": 7, "satvi": 7,
    "aathvi": 8, "nauvi": 9, "dasvi": 10,
}


def _slot(value, confidence, source, raw=None):
    s = {"value": value, "confidence": confidence, "source": source}
    if raw is not None:
        s["raw"] = raw
    return s


def _mask(s: str, start: int, end: int, ch: str = "#") -> str:
    return s[:start] + ch * (end - start) + s[end:]


def _is_negated(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 14):start]
    after = text[end:end + 12]
    if re.search(r"\b(not|na ki|instead of|nahi ki)\s*[,:]?\s*$", before):
        return True
    if re.search(r"^\s*[,]?\s*(nahi|nahin|nai|galat|wrong)\b", after):
        return True
    return False


def _find_all(pattern: str, s: str):
    return list(re.finditer(pattern, s))


def _pick(ms: list[dict], text: str):
    negated: list[dict] = []
    positive: list[dict] = []
    for m in ms:
        if _is_negated(text, m["start"], m["end"]):
            negated.append(m)
        else:
            positive.append(m)
    chosen = positive[-1] if positive else None
    return chosen, negated


def normalize_text(raw: str) -> str:
    t = devanagari_to_latin(raw).lower()
    t = t.replace("“", "").replace("”", "").replace('"', "").replace("'", "")
    t = re.sub(r"[—–]", ", ", t)
    t = t.replace("...", ", ")
    t = re.sub(r"\s+", " ", t)
    # join spelled units: "m m" -> mm
    t = re.sub(r"\bm\s?m\b", "mm", t)
    t = re.sub(r"\bmilli?\s?meters?\b|\bmilli?\s?metres?\b|\bmili\b|\bmilli\b", "mm", t)
    t = re.sub(r"\bcenti\s?meters?\b|\bcenti\s?metres?\b|\bcenti\b", "cm", t)
    # ASR spells the plural several ways ("RFI-S", "R F I s"); a stray "rfi" must not read as "raise an RFI"
    t = re.sub(r"\br\.?\s?f\.?\s?i\.?\s?-?\s?s\b", "rfis", t)
    return normalize_numbers(t)


# ---------------------------------------------------------------- main
def extract(raw: str) -> Extraction:
    normalized = normalize_text(raw or "")
    work = normalized  # progressively masked
    ex = Extraction(normalized)

    ex.isCorrection = bool(re.search(
        r"\b(wait|sorry|galti|galat|actually|matlab|i mean|correction|nahi nahi|no no|not|sahi wala|oh no)\b",
        normalized,
    ))

    # --- grade (M25) before grids/drawings
    grade = re.search(r"\bm\s?-?(15|20|25|30|35|40|45|50)\b(?!\s*(mm|cm))", work)
    if grade:
        ex.attribute = _slot("grade", 0.9, "parser", grade.group(0))
        ex.value = _slot(int(grade.group(1)), 0.9, "parser", grade.group(0))
        ex.unit = _slot("MPa", 0.9, "parser")
        work = _mask(work, grade.start(), grade.start() + len(grade.group(0)))

    # --- drawing numbers: A-102, "a 102", S-301, "drawing 102"
    dwg_mentions: list[dict] = []
    # block-discipline-level-sheet convention (Nashik NSK: SSB-STR-L3-201); spoken short form "STR 201"
    for m in _find_all(r"\bs\s?s\s?b\s?-?\s?(str|arc|mep|hvac|plb|ele|fir)\s?-?\s?(b[12]|gf|tr|l[1-7])\s?-?\s?(\d{3})\b",
                       work):
        dwg_mentions.append({"value": f"SSB-{m.group(1).upper()}-{m.group(2).upper()}-{m.group(3)}",
                             "start": m.start(), "end": m.end(), "confidence": 0.95, "raw": m.group(0)})
    for m in _find_all(r"\b(str|arc|mep|hvac|plb|ele|fir)\s?-?\s?(\d{3})\b", work):
        if not any(d["start"] <= m.start() < d["end"] for d in dwg_mentions):
            dwg_mentions.append({"value": m.group(2), "start": m.start(), "end": m.end(),
                                 "confidence": 0.85, "raw": m.group(0)})
    for d in dwg_mentions:
        work = _mask(work, d["start"], d["end"])
    for m in _find_all(r"\b([a-z])\s?-?\s?(\d{3})\b", work):
        m0 = m.group(0)
        explicit = bool(re.search(r"[a-z]-\d", m0) or re.match(r"[a-z]\d", m0))
        dwg_mentions.append({
            "value": f"{m.group(1).upper()}-{m.group(2)}", "start": m.start(),
            "end": m.start() + len(m0), "confidence": 0.95 if explicit else 0.85, "raw": m0,
        })
    for m in _find_all(r"\b(drawing|dwg|drg)\s*(?:no\.?|number|num)?\s*(\d{3})\b", work):
        m0 = m.group(0)
        s = m.start() + len(m0) - len(m.group(2))
        if not any(d["start"] <= s and d["end"] >= s for d in dwg_mentions):
            dwg_mentions.append({"value": m.group(2), "start": s, "end": m.start() + len(m0),
                                 "confidence": 0.6, "raw": m0})
    chosen, _ = _pick(dwg_mentions, work)
    if chosen:
        ex.drawingNumber = _slot(chosen["value"], chosen["confidence"], "parser", chosen["raw"])
    for d in dwg_mentions:
        work = _mask(work, d["start"], d["end"])

    # --- revisions: Rev 3, R3, R-3, revision 3
    rev_mentions: list[dict] = []
    for m in _find_all(r"\b(?:rev(?:ision)?|r)\s?\.?\s?-?\s?(\d{1,2})\b", work):
        m0 = m.group(0)
        conf = 0.95 if (re.match(r"r\d", m0) or re.search(r"rev", m0)) else 0.85
        rev_mentions.append({"value": f"R{int(m.group(1))}", "start": m.start(),
                             "end": m.start() + len(m0), "confidence": conf, "raw": m0})
    chosen, _ = _pick(rev_mentions, work)
    if chosen:
        ex.revisionClaimed = _slot(chosen["value"], chosen["confidence"], "parser", chosen["raw"])
    for r in rev_mentions:
        work = _mask(work, r["start"], r["end"])

    # --- levels
    lvl_mentions: list[dict] = []
    for m in _find_all(r"\b(?:l|level|lvl|floor|manzil|tal)\s?-?\s?(\d{1,2})\b", work):
        lvl_mentions.append({"value": f"L{int(m.group(1))}", "start": m.start(),
                             "end": m.start() + len(m.group(0)), "confidence": 0.95, "raw": m.group(0)})
    # Do not treat the numeric half of a grid such as "C-7 level 3" as
    # "7 level". The explicit "level 3" matcher above supplies the real level.
    for m in _find_all(r"(?<![-/])\b(\d{1,2})\s?(?:st|nd|rd|th)?\s+(?:floor|level|manzil|slab)\b", work):
        lvl_mentions.append({"value": f"L{int(m.group(1))}", "start": m.start(),
                             "end": m.start() + len(m.group(0)), "confidence": 0.9, "raw": m.group(0)})
    ord_re = r"\b(" + "|".join(ORDINALS.keys()) + r")\s+(floor|level|manzil|mala|maala|tal|slab)\b"
    for m in _find_all(ord_re, work):
        lvl_mentions.append({"value": f"L{ORDINALS[m.group(1)]}", "start": m.start(),
                             "end": m.start() + len(m.group(0)), "confidence": 0.9, "raw": m.group(0)})
    if re.search(r"\bground floor\b", work):
        m = re.search(r"\bground floor\b", work)
        lvl_mentions.append({"value": "L0", "start": m.start(), "end": m.start() + len(m.group(0)),
                             "confidence": 0.9, "raw": m.group(0)})
    lvl_mentions.sort(key=lambda a: a["start"])
    chosen, _ = _pick(lvl_mentions, work)
    if chosen:
        ex.level = _slot(chosen["value"], chosen["confidence"], "parser", chosen["raw"])
    for l in lvl_mentions:
        work = _mask(work, l["start"], l["end"])

    # --- zone
    zm = re.search(r"\bzone\s?-?\s?(a|b|c|d|e|ay|bee|be|see|si|dee)\b", work)
    if zm:
        g1 = zm.group(1)
        ex.zone = _slot(f"Zone {LETTER_WORDS.get(g1, g1.upper())}", 0.95 if len(g1) == 1 else 0.75,
                        "parser", zm.group(0))
        work = _mask(work, zm.start(), zm.start() + len(zm.group(0)))

    # --- named remote-site assets ----------------------------------------------------------
    # These are project-memory locations, not generic construction terms. Keep them explicit so
    # a manager can naturally say "ambulance road retaining wall" without needing a grid code.
    named_grid_mentions: list[dict] = []
    for m in _find_all(r"\b(?:rw\s?-?\s?1|(?<!north )retaining\s+wall(?:\s+(?:one|1))?|ambulance\s+road\s+wall)\b", work):
        named_grid_mentions.append({"value": "RW-1", "start": m.start(), "end": m.start() + len(m.group(0)),
                                    "confidence": 0.95, "raw": m.group(0)})
    for m in _find_all(r"\b(?:rw\s?-?\s?n\s?-?\s?1|north\s+retaining\s+wall)\b", work):
        named_grid_mentions.append({"value": "RW-N1", "start": m.start(), "end": m.end(),
                                    "confidence": 0.95, "raw": m.group(0)})
    for m in _find_all(r"\b(?:sump|sump\s+pit|sump\s+tank)\b", work):
        named_grid_mentions.append({"value": "SUMP-1", "start": m.start(), "end": m.end(),
                                    "confidence": 0.95, "raw": m.group(0)})
    for m in _find_all(r"\b(?:wt\s?-?\s?1|hospital\s+water\s+tank|overhead\s+water\s+tank)\b", work):
        named_grid_mentions.append({"value": "WT-1", "start": m.start(), "end": m.start() + len(m.group(0)),
                                    "confidence": 0.95, "raw": m.group(0)})

    # --- grids: C-5 / C5 / C 5 / C/5 ; spoken "see five" / "si paanch"
    grid_mentions: list[dict] = named_grid_mentions[:]
    for m in _find_all(r"\b([a-h])\s?([-/])?\s?(\d{1,2})\b(?!\s?(mm|cm|m|mpa)\b)(?!\d)", work):
        form = m.group(0)
        conf = 0.95 if (re.match(r"[a-h][-/]\d", form) or re.match(r"[a-h]\d", form)) else 0.85
        if m.group(1) == "a" and not re.search(r"[-/]", form) and not re.search(
                r"(column|grid|line|kolam)\s*$", work[:m.start()]):
            continue
        grid_mentions.append({"value": f"{m.group(1).upper()}-{int(m.group(3))}", "start": m.start(),
                              "end": m.start() + len(form), "confidence": conf, "raw": form})
    letter_alt = "|".join(k for k in LETTER_WORDS.keys() if len(k) > 1)
    num_alt = "|".join(SMALL_NUM_WORDS.keys())
    for m in _find_all(rf"\b({letter_alt})\s?-?\s?({num_alt}|\d{{1,2}})\b(?!\s?(mm|cm|m)\b)", work):
        if any(g["start"] <= m.start() and g["end"] > m.start() for g in grid_mentions):
            continue
        g2 = m.group(2)
        n = int(g2) if re.fullmatch(r"\d+", g2) else SMALL_NUM_WORDS[g2]
        ctx = bool(re.search(r"(column|grid|line|kolam|pe|par|at|on)\s*$", work[:m.start()]))
        grid_mentions.append({"value": f"{LETTER_WORDS[m.group(1)]}-{n}", "start": m.start(),
                              "end": m.start() + len(m.group(0)), "confidence": 0.6 if ctx else 0.5,
                              "raw": m.group(0)})
    grid_mentions.sort(key=lambda a: a["start"])
    chosen, negated = _pick(grid_mentions, work)
    if chosen:
        ex.grid = _slot(chosen["value"], chosen["confidence"], "parser", chosen["raw"])
    ex.negatedGrids = [n["value"] for n in negated if n["value"] != (chosen["value"] if chosen else None)]
    if ex.negatedGrids:
        ex.isCorrection = True
    for g in grid_mentions:
        work = _mask(work, g["start"], g["end"])

    # --- element
    el = [
        (r"\b(column|columns|colum|coloumn|kolam|kalam|khamba|stambh)\b", "column"),
        (r"\b(beam|beams|bim)\b", "beam"),
        (r"\b(slab|chhat|chat|lenter|linter)\b", "slab"),
        (r"\b(footing|footings|foundation|neev|raft)\b", "footing"),
        (r"\b(wall|deewar|diwar)\b", "wall"),
    ]
    el_hits = [{"m": re.search(rx, work), "v": v} for rx, v in el]
    el_hits = [x for x in el_hits if x["m"]]
    if el_hits:
        el_hits.sort(key=lambda x: x["m"].start())
        ex.element = _slot(el_hits[0]["v"], 0.9, "parser", el_hits[0]["m"].group(0))

    # --- attribute
    if not ex.attribute:
        at = [
            (r"\b(stirrups?|rings?|ties?|lateral ties)\s*(ka|ki|ke)?\s*(dia|diameter|sariya|size)\b|\btie[_ ]dia\b", "tie_dia"),
            (r"\b(stirrups?|rings?|ties|lateral ties)\b(\s+(ki|ka))?\s*(spacing|doori|duri|gap|c\/c)?", "stirrup_spacing"),
            (r"\b(spacing|doori|duri|c\/c|centre to centre|center to center)\b", "rebar_spacing"),
            (r"\b(clear cover|cover|kavar)\b", "cover"),
            (r"\b(thickness|motai|thick|depth|mota)\b", "thickness"),
            (r"\b(dia|diameter|bar size|sariya ka size|sariye ka size|sutar|sooter)\b", "rebar_dia"),
            (r"\b(bar count|number of bars|kitne bar|bars count)\b", "bar_count"),
            (r"\bgrade\b", "grade"),
            (r"\bsize\b", "size"),
        ]
        for rx, v in at:
            m = re.search(rx, work)
            if m:
                ex.attribute = _slot(v, 0.9, "parser", m.group(0))
                break

    # --- activity (permits / hold points)
    act = [
        (r"\b(hot work|hotwork|welding|weld|welder|gas cutting|cutting|grinding|grinder|brazing|kataai)\b", "hot_work"),
        (r"\b(pour|pouring|casting|cast|concreting|concrete daal\w*|dhalai|dhalaai|dhalayi|dhaal\w*)\b", "pour"),
        (r"\b(scaffold\w*|height work|work at height|uchai)\b", "height"),
        (r"\b(excavation|khudai|digging)\b", "excavation"),
    ]
    for rx, v in act:
        m = re.search(rx, work)
        if m:
            # "pour se pehle" / "pour ke baad" are temporal references, not an active pour
            if v == "pour" and re.match(r"\s*(se|ke)\s+(pehle|pahle|phle|baad)\b", work[m.end():]):
                continue
            ex.activity = _slot(v, 0.9, "parser", m.group(0))
            break

    # --- defects (qualitative observations)
    df = re.search(
        r"\b(honeycomb\w*|crack\w*|daraar|leak\w*|seepage|spalling|exposed (rebar|bar|sariya)|segregation|bulging)\b",
        work,
    )
    if df:
        ex.defect = _slot(df.group(1), 0.9, "parser", df.group(0))

    # --- numbers (after masking grids/drawings/revs/levels)
    nums: list[dict] = []
    clause_breaks = [0]
    for m in _find_all(
        r",|;|\bbut\b|\blekin\b|\bjabki\b|\bwhereas\b|\bwhile\b|\baur\b|\bmagar\b|\bpar drawing\b",
        normalized,
    ):
        clause_breaks.append(m.start())
    clause_breaks.append(len(normalized))

    def clause_of(pos: int) -> str:
        s, e = 0, len(normalized)
        for b in clause_breaks:
            if b <= pos:
                s = b
            else:
                e = b
                break
        return normalized[s:e]

    DRAWING_REF = r"(drawing|dwg|drg|\brev\b|revision|\br\s?\d|\b[a-z]-?\s?\d{3}\b|as per|ke hisaab|ke hisab|according)"
    DRAWING_SAYS = r"(dikh|dikha|likha|diya|given|shows?|says?|mentioned|specified|chahiye|hona|should|required|bataya|mein hai|me hai|mein \d|me \d|main \d)"
    for m in _find_all(r"(?<![\w#-])(\d+(?:\.\d+)?)\s?(mm|cm|m|mpa|nos)?\b(?!\s?(st|nd|rd|th)\b)", work):
        clause = clause_of(m.start())
        drawing_clause = bool(re.search(DRAWING_REF, clause)) and bool(re.search(DRAWING_SAYS, clause))
        raw_n = m.group(1)
        num = float(raw_n)
        if num.is_integer():
            num = int(num)
        nums.append({"value": num, "unit": m.group(2), "start": m.start(),
                     "end": m.start() + len(m.group(0)), "raw": m.group(0),
                     "confidence": 0.95 if m.group(2) else 0.8, "drawingClause": drawing_clause})
    # "40 wale blocks", "25 wala bar" — the number qualifies a noun (corrective instruction),
    # it is not an observed measurement.
    def _is_qualifier(n: dict) -> bool:
        return bool(re.match(r"\s*(wale|wala|waale|waala|vale)\b", work[n["end"]:n["end"] + 10]))

    obs_nums = [n for n in nums if not n["drawingClause"] and not _is_qualifier(n)]
    dwg_nums = [n for n in nums if n["drawingClause"]]

    chosen, negated = _pick(obs_nums, work)
    ex.negatedValues = [n["value"] for n in negated if n["value"] != (chosen["value"] if chosen else None)]
    if ex.negatedValues:
        ex.isCorrection = True
    if chosen and not ex.value:
        v = chosen["value"]
        unit = chosen["unit"]
        if unit == "cm":
            v = v * 10
            unit = "mm"
        ex.value = _slot(v, chosen["confidence"], "parser", chosen["raw"])
        if unit:
            ex.unit = _slot("MPa" if unit == "mpa" else unit, 0.95, "parser")
    dchosen, _ = _pick(dwg_nums, work)
    if dchosen:
        v = dchosen["value"]
        if dchosen["unit"] == "cm":
            v = v * 10
        ex.drawingValueClaimed = _slot(v, dchosen["confidence"], "parser", dchosen["raw"])

    # --- decisions
    decisions: list[dict] = []
    rfi_neg = re.search(
        r"\brfi\b\s*(ki\s*)?(nahi|nahin|mat|na|not needed|nahi chahiye|ki zarurat nahi|ki zaroorat nahi)|\b(no|don'?t|do not|dont)\s+(raise\s+)?(an?\s+)?rfi\b",
        normalized,
    )
    if rfi_neg:
        ex.rfiDeclined = True
    rfi_pos = re.search(
        r"\b(raise|create|file|open|log|bhejo|daalo|dalo)\s+(an?\s+)?rfi\b|\brfi\b\s*(raise|bhej|daal|dal|bana|create|file|open|kar|chahiye|karo|kar do)",
        normalized,
    )
    if rfi_pos and not rfi_neg:
        decisions.append({"d": "raise_rfi", "pos": rfi_pos.start()})
    ncr = re.search(r"\bncr\b|non[- ]?conformance", normalized)
    if ncr and not re.search(r"\bncr\s*(nahi|mat|na)\b|\bno ncr\b", normalized):
        decisions.append({"d": "raise_ncr", "pos": ncr.start()})
    stop = re.search(
        r"\b(kaam|kam|work|pour|pouring|dhalai|dhalaai)\s*(ko\s*)?(rok|rok do|roko|band|stop|halt|hold)|\bstop (the )?work\b|\bstop karo\b|\brok do\b|\broko\b|\bband karo\b|\bhalt\b|\bhold\s*(karo|kar do|kar lo|rakho|rakh do|karao)\b|\bwait\s*kar(o|ao|wao)\b|\brukwa\s*(do|deta)\b",
        normalized,
    )
    if stop:
        decisions.append({"d": "stop_work", "pos": stop.start()})
    cancel = re.search(
        r"\b(cancel|rehne do|rahne do|chhod do|chod do|chhodo|chodo|discard|abort|mat karo|nevermind|never mind)\b",
        normalized,
    )
    if cancel:
        decisions.append({"d": "cancel", "pos": cancel.start()})
    log = re.search(
        r"\blog\s*(kar|karo|kardo|kar do|it|this|that|the|karna|karein|kijiye|observation)\b|\b(observation|entry)\s*(log|save|darj|record)\b|\b(record|save|darj|note)\s*(kar|karo|kar do|it)\b|\blog observation\b|^log$|\bhaan,? log\b|\blog\b[.!]?$",
        normalized,
    )
    if log and not re.search(r"\blog\s*(mat|nahi|na)\b|\bdon'?t log\b|\bdo not log\b", normalized):
        decisions.append({"d": "log_observation", "pos": log.start()})
    if decisions:
        decisions.sort(key=lambda a: a["pos"])
        ex.decision = decisions[-1]["d"]
        dset = {x["d"] for x in decisions}
        if "stop_work" in dset:
            ex.decision = "stop_work"
        if "cancel" in dset and len(dset) == 1:
            ex.decision = "cancel"

    # --- yes / no
    ex.affirm = bool(re.search(
        r"^(haan|han|haa|ha|ji|jee|yes|yeah|yep|yup|sahi|correct|theek|thik|ok|okay|bilkul|confirm\w*|right|done|haanji|hanji)\b",
        normalized,
    ) or re.search(
        r"\b(sahi hai|correct hai|confirm hai|confirmed|haan ji|haan sahi|bilkul sahi|that'?s right|yes correct)\b",
        normalized,
    ))
    ex.deny = bool(re.search(r"^(nahi|nahin|nai|na|no|nope|galat|wrong)\b", normalized)
                   or re.search(r"\b(galat hai|wrong hai|sahi nahi|not correct)\b", normalized))
    if ex.deny:
        ex.affirm = False

    return ex


def chips(ex: Extraction) -> list[dict]:
    """Slots that were extracted (for UI chips)."""
    out: list[dict] = []

    def add(kind, s, fmt=None):
        if s:
            out.append({"kind": kind, "label": fmt(s["value"]) if fmt else str(s["value"]),
                        "confidence": s["confidence"]})

    add("grid", ex.grid)
    add("level", ex.level)
    add("zone", ex.zone)
    add("element", ex.element)
    add("attribute", ex.attribute)
    add("value", ex.value, lambda v: f"{v}{(' ' + ex.unit['value']) if ex.unit else ''}")
    add("drawing", ex.drawingNumber)
    add("revision", ex.revisionClaimed)
    add("drawing says", ex.drawingValueClaimed, lambda v: f"{v}")
    add("activity", ex.activity)
    add("defect", ex.defect)
    if ex.decision:
        out.append({"kind": "decision", "label": ex.decision, "confidence": 1})
    return out
