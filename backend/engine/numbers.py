"""Spoken-number normalisation for Hinglish (romanised Hindi + English + Devanagari).

Faithful 1:1 port of app/lib/parser/numbers.ts.

``normalize_numbers()`` rewrites number-word phrases into digits *only* where context
makes them numeric (a unit follows, a multiplier like "sau"/"hundred" is present, or a
numeric keyword precedes), so "log kar do" never becomes "log kar 2".
"""
from __future__ import annotations

import re

HI_UNITS: dict[str, int] = {
    "shunya": 0, "sifar": 0, "ek": 1, "do": 2, "teen": 3, "tin": 3, "char": 4, "chaar": 4, "chār": 4,
    "paanch": 5, "panch": 5, "paach": 5, "chhe": 6, "chhah": 6, "chah": 6, "chhai": 6, "che": 6,
    "saat": 7, "sat": 7, "aath": 8, "ath": 8, "nau": 9, "das": 10, "dus": 10, "gyarah": 11, "gyara": 11,
    "barah": 12, "bara": 12, "terah": 13, "tera": 13, "chaudah": 14, "chauda": 14, "pandrah": 15, "pandra": 15,
    "solah": 16, "sola": 16, "satrah": 17, "satra": 17, "atharah": 18, "athara": 18, "unnis": 19, "unees": 19,
    "bees": 20, "bis": 20, "ikkis": 21, "bais": 22, "baees": 22, "teis": 23, "chaubis": 24, "pachchis": 25,
    "pachis": 25, "chhabbis": 26, "sattais": 27, "atthais": 28, "untis": 29, "untees": 29, "tees": 30, "tis": 30,
    "ikattis": 31, "ektees": 31, "battis": 32, "taintis": 33, "chauntis": 34, "paintis": 35, "pentis": 35,
    "chhattis": 36, "saintis": 37, "adtis": 38, "artis": 38, "untalis": 39, "chalis": 40, "chaalis": 40,
    "chalees": 40, "chaalees": 40, "iktalis": 41, "bayalis": 42, "taintalis": 43, "chawalis": 44, "chauvalis": 44,
    "paintalis": 45, "chhiyalis": 46, "chhiyalees": 46, "saintalis": 47, "santalees": 47, "adtalis": 48,
    "unchas": 49, "pachas": 50, "pachaas": 50,
    # common romanisation variants ending -ees / -alees heard on site
    "pachees": 25, "pacchees": 25, "chhabees": 26, "santees": 27, "atthaees": 28, "beis": 22, "baees": 22,
    "chaubees": 24, "chhattees": 36, "paintees": 35,
    "ikyavan": 51, "bavan": 52, "tirpan": 53, "chauvan": 54, "pachpan": 55, "chhappan": 56, "sattavan": 57,
    "atthavan": 58, "unsath": 59, "saath": 60, "sath": 60, "iksath": 61, "basath": 62, "tirsath": 63,
    "chausath": 64, "painsath": 65, "chhiyasath": 66, "sadsath": 67, "adsath": 68, "unhattar": 69, "sattar": 70,
    "ikhattar": 71, "bahattar": 72, "tihattar": 73, "chauhattar": 74, "pachhattar": 75, "chhihattar": 76,
    "sathattar": 77, "athattar": 78, "unasi": 79, "assi": 80, "asi": 80, "ikyasi": 81, "bayasi": 82,
    "tirasi": 83, "chaurasi": 84, "pachasi": 85, "chhiyasi": 86, "sattasi": 87, "athasi": 88, "nawasi": 89,
    "nabbe": 90, "nabbey": 90, "ikyanve": 91, "banve": 92, "tiranve": 93, "chauranve": 94, "pachanve": 95,
    "chhiyanve": 96, "sattanve": 97, "atthanve": 98, "ninyanve": 99,
}

EN_UNITS: dict[str, int] = {
    "zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
EN_TENS: dict[str, int] = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}
HUNDRED = {"sau", "so", "hundred", "saw"}
THOUSAND = {"hazaar", "hazar", "thousand"}

# Devanagari -> romanised tokens (numbers + a few domain words the rest of the parser understands)
DEVANAGARI_WORDS: dict[str, str] = {
    "एक": "ek", "दो": "do", "तीन": "teen", "चार": "char", "पांच": "paanch", "पाँच": "paanch", "छह": "chhe",
    "छः": "chhe", "सात": "saat", "आठ": "aath", "नौ": "nau", "दस": "das", "बीस": "bees", "तीस": "tees",
    "चालीस": "chalis", "पचास": "pachas", "साठ": "saath", "सत्तर": "sattar", "अस्सी": "assi", "नब्बे": "nabbe",
    "सौ": "sau", "हज़ार": "hazaar", "हजार": "hazaar", "पच्चीस": "pachchis", "पैंतीस": "paintis",
    "पैंतालीस": "paintalis", "पचहत्तर": "pachhattar", "सी": "see", "बी": "bee", "ए": "ay", "डी": "dee",
    "ई": "ee", "एफ": "ef", "जी": "gee", "एच": "aitch", "कॉलम": "column", "कालम": "column", "बीम": "beam",
    "स्लैब": "slab", "मंज़िल": "manzil", "मंजिल": "manzil", "तीसरी": "teesri", "चौथी": "chauthi",
    "दूसरी": "doosri", "पहली": "pehli", "मिमी": "mm", "एमएम": "mm", "मिलीमीटर": "mm", "रिवीजन": "revision",
    "ड्राइंग": "drawing", "नहीं": "nahi", "हां": "haan", "हाँ": "haan", "स्पेसिंग": "spacing", "कवर": "cover",
    "सरिया": "sariya", "पे": "pe", "पर": "par", "है": "hai", "में": "mein", "ज़ोन": "zone", "जोन": "zone",
    "वेल्डिंग": "welding", "ढलाई": "dhalai", "लॉग": "log", "कर": "kar", "रोक": "rok",
}

DEV_DIGITS = "०१२३४५६७८९"


def devanagari_to_latin(text: str) -> str:
    t = re.sub(r"[०-९]", lambda m: str(DEV_DIGITS.index(m.group(0))), text)
    # longest-first so "पैंतालीस" wins over "पैंतीस" prefixes
    keys = sorted(DEVANAGARI_WORDS.keys(), key=len, reverse=True)
    for k in keys:
        t = f" {DEVANAGARI_WORDS[k]} ".join(t.split(k))
    t = t.replace("।", ".")
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _unit_value(w: str):
    if w in EN_UNITS:
        return EN_UNITS[w]
    if w in EN_TENS:
        return EN_TENS[w]
    if w in HI_UNITS:
        return HI_UNITS[w]
    if re.fullmatch(r"\d+", w):
        return int(w)
    return None


def _is_number_word(w: str) -> bool:
    return _unit_value(w) is not None or w in HUNDRED or w in THOUSAND


def parse_number_tokens(tokens: list[str]):
    """Parse a run of number tokens. Returns {'value', 'structured'} or None."""
    if not tokens:
        return None
    vals = [t.lower() for t in tokens]
    ws = [w for w in vals if w != "and"]
    if not all(_is_number_word(w) for w in ws):
        return None
    total = 0
    current = 0
    saw_multiplier = False
    i = 0
    while i < len(ws):
        w = ws[i]
        if w in HUNDRED:
            current = (current or 1) * 100
            saw_multiplier = True
            i += 1
            continue
        if w in THOUSAND:
            total += (current or 1) * 1000
            current = 0
            saw_multiplier = True
            i += 1
            continue
        v = _unit_value(w)
        nxt = ws[i + 1] if i + 1 < len(ws) else None
        # English "one eighty" / "one fifty" -> 1*100 + 80
        if (not saw_multiplier and current == 0 and v is not None and 1 <= v <= 9
                and nxt is not None and nxt not in HUNDRED and nxt not in THOUSAND):
            nv = _unit_value(nxt)
            if nv is not None and 10 <= nv <= 99 and (nxt in EN_TENS or nxt in EN_UNITS):
                current = v * 100 + nv
                i += 1
                saw_multiplier = True
                n2 = ws[i + 1] if i + 1 < len(ws) else None
                if n2 and n2 in EN_UNITS and EN_UNITS[n2] < 10 and nv % 10 == 0:
                    current += EN_UNITS[n2]
                    i += 1
                i += 1
                continue
        if v is not None and v >= 20 and v % 10 == 0 and v < 100:
            n2 = ws[i + 1] if i + 1 < len(ws) else None
            if n2 and n2 in EN_UNITS and EN_UNITS[n2] < 10:
                current += v + EN_UNITS[n2]
                i += 2
                continue
        current += v
        i += 1
    return {"value": total + current, "structured": saw_multiplier or len(ws) > 1}


UNIT_AFTER = re.compile(
    r"^(mm|millimeter|millimetre|millimeters|millimetres|mili|milli|mil|cm|centimeter|centimetre|centi|m|meter|metre|meters|metres|mpa|nos|number|dia)$"
)
NUMERIC_KEYWORDS = {
    "spacing", "cover", "thickness", "motai", "dia", "diameter", "size", "rev", "revision", "r", "grade",
    "value", "drawing", "level", "floor", "tolerance", "doori", "gap",
}

_AMBIGUOUS_SINGLE = ["do", "so", "saw", "sat", "tin", "bis", "ath", "che", "asi", "sath", "tis", "oh", "das"]


def normalize_numbers(text: str) -> str:
    """Replace number-word phrases with digits where context says they are numbers.
    Input must already be lowercased + Devanagari-normalised.
    """
    tokens = re.split(r"(\s+|[,.;!?—–]+)", text)  # keep separators
    words: list[dict] = []
    for idx, tok in enumerate(tokens):
        if tok.strip() and not re.fullmatch(r"[,.;!?—–]+", tok):
            words.append({"tok": tok, "idx": idx})

    out = list(tokens)
    i = 0
    while i < len(words):
        w = words[i]["tok"].lower()
        if not _is_number_word(w) or re.fullmatch(r"\d+", w):
            i += 1
            continue
        # gather a run of number words (allow "and" inside)
        j = i
        run: list[str] = []
        while j < len(words):
            wj = words[j]["tok"].lower()
            if _is_number_word(wj) and not re.fullmatch(r"\d+", wj):
                run.append(wj)
                j += 1
                continue
            if (wj == "and" and run and j + 1 < len(words)
                    and _is_number_word(words[j + 1]["tok"].lower())):
                run.append(wj)
                j += 1
                continue
            break
        parsed = parse_number_tokens(run)
        next_word = words[j]["tok"].lower() if j < len(words) else ""
        prev_words = [x["tok"].lower() for x in words[max(0, i - 3):i]]
        unit_follows = bool(UNIT_AFTER.match(next_word))
        keyword_before = any(p in NUMERIC_KEYWORDS for p in prev_words)
        has_multiplier = any(r in HUNDRED or r in THOUSAND for r in run)
        english_only = all(
            r in EN_UNITS or r in EN_TENS or r in HUNDRED or r in THOUSAND or r == "and" for r in run
        )
        ambiguous_single = len(run) == 1 and run[0] in _AMBIGUOUS_SINGLE
        last_prev = prev_words[-1] if prev_words else None
        accept = parsed and (
            (has_multiplier and len(run) > 1)
            or unit_follows
            or (keyword_before and not ambiguous_single)
            or (keyword_before and ambiguous_single and (unit_follows or (last_prev is not None and last_prev in NUMERIC_KEYWORDS)))
            or (english_only and parsed["structured"] and len(run) > 1)
        )
        if accept and parsed:
            out[words[i]["idx"]] = str(parsed["value"])
            for k in range(i + 1, j):
                out[words[k]["idx"]] = ""
            # collapse separators between removed words
            for k in range(words[i]["idx"] + 1, words[j - 1]["idx"]):
                if not tokens[k].strip():
                    out[k] = ""
        i = j
    return re.sub(r"\s+", " ", "".join(out)).strip()
