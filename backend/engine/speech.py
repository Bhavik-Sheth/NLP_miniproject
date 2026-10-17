"""Shape engine text for the ear before it goes to Rime.

The full reply stays on screen; what is *spoken* must be short, sentence-shaped and free of
typographic characters. Found by scripts/voice_acceptance.py: the open-RFI list — one 230-char
sentence joined by semicolons with an en dash ("L3–L4") — made the Rime websocket time out
(no audio for 10 s, then a retry), while the same content split into short sentences returned
first audio in ~330 ms. See RIME_EVIDENCE.md.
"""
from __future__ import annotations

import re

MAX_SPOKEN_CHARS = 260


def speakable(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"(\w)\s*[–—]\s*(\w)", r"\1 to \2", t)          # ranges: L3–L4 -> L3 to L4
    t = t.replace("—", ", ").replace("–", ", ")
    t = re.sub(r"\s*;\s*", ". ", t)                              # one clause per sentence
    t = re.sub(r"\s*\(([^)]*)\)", r", \1,", t)                   # parentheses read as asides
    t = re.sub(r",\s*([.?!])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    if len(t) <= MAX_SPOKEN_CHARS:
        return t
    out = ""
    for sent in re.split(r"(?<=[.?!])\s+", t):                    # keep whole sentences only
        if len(out) + len(sent) > MAX_SPOKEN_CHARS and out:
            return out.strip() + " The rest is on your screen."
        out += sent + " "
    return out.strip()
