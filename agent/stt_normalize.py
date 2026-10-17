"""Deterministic post-STT normaliser: maps known mishearings onto site vocabulary.

Conservative by design — every rule needs either an exact vocabulary hit or construction
context next to the token, and every change is returned (and logged by the caller) so a wrong
rewrite is visible in the transcript log. The engine's own parser (backend/engine/extract.py)
still does all entity extraction; this only repairs what the parser cannot see through.

Rules
  1. Punctuation / filler-only transcripts ("." "..." "Thank you.") -> "" (turn dropped).
  2. Place names from the project record (e.g. "Pithoragarh"): fuzzy match of 1-3 word windows,
     same first letter, similarity >= 0.78 on the letters-only form.
  3. Grid homophones Whisper produces ("even" -> "E-1", "eat to" -> "E-2") only when a column /
     grid / cover / at context word is within two words.
  4. Spaced or spelled IDs that exist in the record: "RFI 050" -> "RFI-050",
     "EXC 0041" -> "EXC-0041", "R W 1" -> "RW-1", "O P D" -> "OPD".
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from worker_prompts import site_vocabulary

logger = logging.getLogger("vesper.stt.normalize")

_FILLER_ONLY = re.compile(
    r"^\W*(?:(?:thank you|thanks|thank you for watching|bye|you|uh|um|hmm|okay\?)\W*)?$", re.I)
_CONTEXT = r"(?:column|columns|grid|line|cover|at|on|pe|par|near|kolam)"

# Whisper/ASR homophones for grid refs. Value -> grid. Only applied with _CONTEXT nearby.
_GRID_HOMOPHONES = {
    # "cover at E one" under drill noise came back as "cover, everyone" from Sarvam (2026-09-15)
    "everyone": "E-1", "every one": "E-1",
    "even": "E-1", "evan": "E-1", "e van": "E-1", "ee van": "E-1", "e-one": "E-1", "eone": "E-1",
    "e too": "E-2", "e to": "E-2", "eat to": "E-2", "eat two": "E-2", "e-two": "E-2",
    "sea five": "C-5", "sea six": "C-6", "si 5": "C-5", "c paanch": "C-5",
}


@dataclass
class Normalized:
    text: str
    changes: list[str] = field(default_factory=list)

    @property
    def dropped(self) -> bool:
        return not self.text


def _letters(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def _fix_places(text: str, places: list[str], changes: list[str]) -> str:
    targets = [(p, _letters(p)) for p in places if len(_letters(p)) >= 8]
    if not targets:
        return text
    tokens = list(re.finditer(r"[A-Za-z][A-Za-z'\-]*", text))
    out, i, cursor = [], 0, 0
    while i < len(tokens):
        best = None
        for n in (1, 2, 3):  # smallest window first; a longer one must score strictly higher
            if i + n > len(tokens):
                continue
            start, end = tokens[i].start(), tokens[i + n - 1].end()
            span = text[start:end]
            # windows may only cross spaces / hyphens / commas, never sentence ends, and never
            # swallow an acronym the parser needs ("Pithoragar OPD block" keeps OPD)
            if re.search(r"[.?!]", span) or any(re.fullmatch(r"[A-Z]{2,}", t.group(0)) for t in tokens[i + 1:i + n]):
                continue
            cand = _letters(span)
            for name, target in targets:
                if cand == target:
                    if span != name:
                        best = (n, start, end, name, 1.0)
                    else:
                        best = (n, start, end, None, 1.0)
                    break
                if not cand or cand[0] != target[0] or abs(len(cand) - len(target)) > 5:
                    continue
                ratio = SequenceMatcher(None, cand, target).ratio()
                if ratio >= 0.78 and (best is None or ratio > best[4]):
                    best = (n, start, end, name, ratio)
            if best:
                break
        if best:
            n, start, end, name, ratio = best
            if name:
                out.append(text[cursor:start] + name)
                changes.append(f"place {text[start:end]!r}->{name!r} ({ratio:.2f})")
                cursor = end
            i += n
        else:
            i += 1
    out.append(text[cursor:])
    return "".join(out)


def _fix_grids(text: str, grids: set[str], changes: list[str]) -> str:
    for heard, grid in _GRID_HOMOPHONES.items():
        if grids and grid not in grids:
            continue
        pat = re.compile(
            rf"(?P<pre>\b{_CONTEXT}\b(?:\W+\w+)?\W+)(?P<g>{re.escape(heard)})\b"
            rf"|\b(?P<g2>{re.escape(heard)})(?P<post>\W+(?:\w+\W+)?{_CONTEXT}\b)", re.I)

        def sub(m: re.Match) -> str:
            if m.group("g"):
                changes.append(f"grid {m.group('g')!r}->{grid!r}")
                return m.group("pre") + grid
            changes.append(f"grid {m.group('g2')!r}->{grid!r}")
            return grid + m.group("post")

        text = pat.sub(sub, text)
    return text


def _fix_ids(text: str, vocab: dict[str, list[str]], changes: list[str]) -> str:
    known = set(vocab["rfis"]) | set(vocab["permits"]) | {"RW-1", "WT-1", "LP-1"}
    # "RFI 050", "RFI number 50", "R F I 050", "EXC 0041", "HWP 112"
    def sub(m: re.Match) -> str:
        prefix = re.sub(r"[\s.]", "", m.group(1)).upper()
        digits = m.group(2)
        for width in (len(digits), 3, 4, 2, 1):
            cand = f"{prefix}-{int(digits):0{width}d}"
            if cand in known:
                if cand != m.group(0):
                    changes.append(f"id {m.group(0)!r}->{cand!r}")
                return cand
        return m.group(0)

    text = re.sub(r"\b(R\.?\s?F\.?\s?I|EXC|HWP|WAH|CSE|R\.?\s?W|W\.?\s?T|L\.?\s?P)\.?\s?(?:-\s?|number\s|no\.?\s)?(\d{1,4})\b",
                  sub, text, flags=re.I)
    new = re.sub(r"\bO\.?\s?P\.?\s?D\b\.?", "OPD", text)
    if new != text:
        changes.append("id 'O P D'->'OPD'")
    return new


# Observed Whisper garbles of site names (real transcripts, 2026-09). Exact phrase aliases, so
# they apply without fuzzy matching; each needs its trailing context where it is ambiguous.
_PHRASE_ALIASES = [
    (re.compile(r"\bpit[\s-]?thorough(?:ly)?\b|\bpit[\s-]?torqued?\b|\bpithor(?:a)?gad\b|\bpitt?oragarh\b", re.I),
     "Pithoragarh"),
    (re.compile(r"\b(?:do[\s-]?pity|the[\s-]?pity|o[\s-]?pd|opity)(?=\s+(?:block|column|building|wing)\b)", re.I),
     "OPD"),
    # Sarvam romanises Hinglish ordinals/floors with spellings the parser does not list
    # ("Teesari Manzil" -> no level). Only rewritten directly before a floor word.
    (re.compile(r"\bteesari(?=\s+(?:manzil|manjil|mazil|floor|tal|maala|mala)\b)", re.I), "teesri"),
    (re.compile(r"\bchauthee(?=\s+(?:manzil|manjil|floor)\b)", re.I), "chauthi"),
    (re.compile(r"\bmanjil\b", re.I), "manzil"),  # "manjil" is only ever "manzil" (floor)
]


def _fix_aliases(text: str, changes: list[str]) -> str:
    for pat, repl in _PHRASE_ALIASES:
        def sub(m: re.Match, repl: str = repl) -> str:
            if m.group(0) != repl:
                changes.append(f"alias {m.group(0)!r}->{repl!r}")
            return repl
        text = pat.sub(sub, text)
    return text


def normalize(raw: str | None) -> Normalized:
    text = (raw or "").strip()
    if not re.search(r"[0-9A-Za-zऀ-ॿ]", text) or _FILLER_ONLY.match(text):
        return Normalized("", [f"dropped {text!r}"] if text else [])
    vocab = site_vocabulary()
    changes: list[str] = []
    text = _fix_aliases(text, changes)
    text = _fix_places(text, vocab["places"] or ["Pithoragarh", "Uttarakhand"], changes)
    text = _fix_grids(text, set(vocab["grids"]), changes)
    text = _fix_ids(text, vocab, changes)
    text = re.sub(r"\s+", " ", text).strip()
    if changes:
        logger.info("stt normalize: %s", "; ".join(changes))
    return Normalized(text, changes)
