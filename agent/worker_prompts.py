"""STT biasing text shared by the live agent, the backend /api/stt route and the A/B scripts.

Kept in one module so every path biases decoding the same way. Vocabulary comes from the
project record (data/site.db) when it is readable, otherwise from a static fallback.
"""
from __future__ import annotations

import os
import sqlite3
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# Whisper continues the STYLE of its prompt, so this is a sample site transcript rather than
# a word list — it biases decoding toward grid refs, drawing numbers, revisions and QA terms.
STT_PROMPT = (
    "Column line C-5, rebar spacing 180 millimetres, drawing A-102 revision R4. "
    "Cover at E-1 column is 40 millimetres per IS 456. Stirrup spacing at C-6 measured 220. "
    "RW-1 retaining wall on C-401 revision R2, excavation permit EXC-0041. "
    "L4 slab thickness 150 millimetres on S-301 revision R2, RFI-050 still open. "
    "What is the cover at E-2? Raise an NCR. Log the observation. Pre-pour hold point."
)

# Sarvam realtime accepts a free-text terminology hint (`prompt`).
SARVAM_STT_PROMPT = (
    "Construction QA/QC site conversation, Pithoragarh District Hospital, Uttarakhand. "
    "Grid columns like E-1, E-2, C-5; drawings like A-201 R1, C-401 R2, S-301; RFI-050; "
    "permits EXC-0041, HWP-0112; OPD block, maternity wing, retaining wall RW-1; "
    "cover, stirrup spacing, rebar, millimetres, hold point, NCR, IS 456."
)

_STATIC_TERMS = [
    "Pithoragarh", "Uttarakhand", "OPD block", "maternity wing", "E-1", "E-2", "C-5", "C-6",
    "RW-1", "WT-1", "A-201", "C-401", "S-301", "RFI-050", "EXC-0041", "HWP-0112", "NCR",
    "IS 456", "hold point", "stirrup spacing", "cover", "millimetres",
]


def _db_path() -> str:
    raw = os.getenv("SITE_DB_PATH", "../data/site.db")
    return raw if os.path.isabs(raw) else str((_ROOT / "backend" / raw).resolve())


@lru_cache(maxsize=1)
def site_vocabulary() -> dict[str, list[str]]:
    """IDs and names from the project record. Empty lists when the DB is unavailable."""
    vocab: dict[str, list[str]] = {"grids": [], "drawings": [], "rfis": [], "permits": [],
                                   "places": [], "zones": []}
    try:
        con = sqlite3.connect(f"file:{_db_path()}?mode=ro", uri=True)
        q = lambda sql: [r[0] for r in con.execute(sql) if r[0]]  # noqa: E731
        vocab["grids"] = sorted(set(q("SELECT grid FROM locations")))
        vocab["zones"] = sorted(set(q("SELECT zone FROM locations")))
        vocab["drawings"] = sorted(set(q("SELECT drawing_number FROM drawings")))
        vocab["rfis"] = sorted(set(q("SELECT rfi_id FROM rfis")))
        vocab["permits"] = sorted(set(q("SELECT permit_id FROM permits")))
        places: set[str] = set()
        for (loc,) in con.execute("SELECT location FROM projects"):
            places.update(p.strip() for p in str(loc).split(",") if p.strip())
        for (name,) in con.execute("SELECT name FROM projects"):
            places.update(w for w in str(name).replace("&", " ").split() if len(w) >= 8)
        vocab["places"] = sorted(places)
        con.close()
    except Exception:
        pass
    return vocab


def sarvam_keyterms(limit: int = 50) -> list[str]:
    """REST `keyterms` list (≤ 50 terms, ≤ 64 chars each)."""
    v = site_vocabulary()
    terms: list[str] = []
    for t in (_STATIC_TERMS + v["places"] + v["rfis"] + v["permits"] + v["drawings"] + v["grids"]):
        if t and t not in terms and len(t) <= 64:
            terms.append(t)
    return terms[:limit]
