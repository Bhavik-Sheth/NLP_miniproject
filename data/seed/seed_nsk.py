#!/usr/bin/env python3
"""
Demo project NSK — "Nashik Civil Hospital — 300-bed Super Speciality Block", Nashik, Maharashtra.

Generator for data/seed/project_nsk.json (build_db.py loads every data/seed/project_*.json; P1 is still
built from seed_p1.py). Regenerate with:  python3 data/seed/seed_nsk.py

Consistent with the onboarding sample in app/components/onboarding/prefill.ts (Deccan Buildcon for PWD
Maharashtra; G+7 RCC, 2 basements, OT complex on L3, ICU on L4; seismic zone III, moderate exposure;
M35 raft/retaining wall, M30 columns/shear walls, M25 beams/slabs; Fe500D; covers raft 50 / column 40 /
beam 30 / slab 25; drawings SSB-<DISC>-<LEVEL>-<SHEET>; RFI-SSB-###; NCR-SSB-###; SI-###).

Voice-test contract (data/seed/scenarios_nsk.json depends on these — do not change casually):
  NSK:C-7:L3 / NSK:C-8:L3  SSB-STR-L3-201 R0/R1 Superseded, R2 For Construction (2026-08-21, via RFI-SSB-006):
                           tie spacing 150 -> 100 ±10; cover 40 ±5 (IS 456 Cl. 26.4)
  C-7 and D-7 exist on L3 AND L4 (level ambiguity); C-6, C-8, C-9, E-8 only on L3
  NSK:Slab:L3              SSB-STR-L3-211 R0 Superseded (150), R1 For Construction (200 ±5, via RFI-SSB-008);
                           pre-pour CL-PP-SSB-L3-001 (QC-CON-CHK-001) on HOLD, hold point NOT released
  HWP-2031 hot work @ NSK:ZoneC:L4 Active — fire watch checks unsatisfied (permit blocker)
  EXC-2017 excavation @ NSK:Sump:GF Suspended (shoring / groundwater)
  SSB-STR-L3-209 must NOT exist (unknown drawing)
"""
from __future__ import annotations

import json
from pathlib import Path

PID = "NSK"

PROJECT = {
    "project_id": PID,
    "name": "Nashik Civil Hospital — 300-bed Super Speciality Block",
    "client": "Public Works Department, Government of Maharashtra",
    "location": "Nashik, Maharashtra",
    "contract_type": "Item Rate (Maharashtra PWD)",
    "start_date": "2026-02-17",
}

# ----------------------------------------------------------------------------------------------
# Locations + spoken aliases (English, Hinglish, Marathi romanised, Devanagari)
# ----------------------------------------------------------------------------------------------
_LETTER = {
    "A": ["A", "ay", "ए"], "B": ["B", "bee", "बी"], "C": ["C", "see", "सी"], "D": ["D", "dee", "डी"],
    "E": ["E", "ee", "ई"], "F": ["F", "ef", "एफ"], "G": ["G", "gee", "जी"], "H": ["H", "aitch", "एच"],
}
# digit, English, Hindi, Marathi, Devanagari (Marathi)
_NUM = {
    4: ("4", "four", "char", "chaar", "चार"), 6: ("6", "six", "chhe", "saha", "सहा"),
    7: ("7", "seven", "saat", "saat", "सात"), 8: ("8", "eight", "aath", "aath", "आठ"),
    9: ("9", "nine", "nau", "nau", "नऊ"), 10: ("10", "ten", "das", "daha", "दहा"),
    12: ("12", "twelve", "barah", "bara", "बारा"),
}
_LEVEL_ALIASES = {
    "L2": ["L2", "level 2", "level two", "second floor", "doosra floor", "dusra majla", "दुसरा मजला"],
    "L3": ["L3", "level 3", "level three", "third floor", "OT floor", "teesra floor", "tisra majla", "तिसरा मजला"],
    "L4": ["L4", "level 4", "level four", "fourth floor", "ICU floor", "chautha floor", "chautha majla", "चौथा मजला"],
}


def _grid_aliases(grid: str, level: str) -> list[str]:
    letter, n = grid.split("-")
    n = int(n)
    L_en, L_rom, L_dev = _LETTER[letter]
    d, n_en, n_hi, n_mr, n_dev = _NUM[n]
    a = [
        f"{L_en}-{d}", f"{L_en}{d}", f"{L_en} {d}", f"{L_en.lower()}{d}",
        f"{L_en} {n_en}", f"{L_rom} {n_en}", f"{L_en} {n_hi}", f"{L_rom} {n_hi}", f"{L_en} {n_mr}",
        f"{L_dev} {d}", f"{L_dev}-{d}", f"{L_dev} {n_dev}",
        f"column {L_en}{d}", f"column line {L_en}-{d}", f"grid {L_en}-{d}", f"{L_en}-{d} column",
        f"{L_en}-{d} khamb", f"कॉलम {L_dev} {d}", f"खांब {L_dev} {d}",
    ]
    if letter == "C":
        a += [f"sea {n_en}", f"si {n_en}", f"c{n_en}"]
    if letter == "D":
        a += [f"the {n_en}", f"de {n_en}"]
    a += [f"{grid} {lv}" for lv in _LEVEL_ALIASES[level][:3]]
    out, seen = [], set()
    for x in a:
        if x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out


L3_COLUMNS = {  # grid -> zone
    "B-4": "ZoneA", "C-6": "ZoneB", "C-7": "ZoneB", "C-8": "ZoneB", "C-9": "ZoneB", "D-7": "ZoneB",
    "D-8": "ZoneB", "E-7": "ZoneB", "E-8": "ZoneB", "F-10": "ZoneC", "H-12": "ZoneC",
}
OT_BAY = {"C-7", "C-8", "D-7", "D-8"}          # heavier columns under OT pendants / modular OT
PENDANT = {"C-7", "C-8"}                       # RFI-SSB-006: ties 100 c/c full height
L4_COLUMNS = {"C-7": "ZoneB", "D-7": "ZoneB"}
L3_BEAMS = {"G-7": "B3-G07", "G-8": "B3-G08"}


def locations() -> list[dict]:
    locs = []
    for g, z in L3_COLUMNS.items():
        locs.append({"location_id": f"{PID}:{g}:L3", "project_id": PID, "grid": g, "level": "L3", "zone": z,
                     "aliases": _grid_aliases(g, "L3") + (["OT bay column", f"OT column {g}"] if g in OT_BAY else [])})
    for g, z in L4_COLUMNS.items():
        locs.append({"location_id": f"{PID}:{g}:L4", "project_id": PID, "grid": g, "level": "L4", "zone": z,
                     "aliases": _grid_aliases(g, "L4") + [f"ICU column {g}"]})
    for g in L3_BEAMS:
        locs.append({"location_id": f"{PID}:{g}:L3", "project_id": PID, "grid": g, "level": "L3", "zone": "ZoneB",
                     "aliases": _grid_aliases(g, "L3") + [f"beam line {g}", f"{L3_BEAMS[g]}", f"{g} beam"]})
    locs.append({"location_id": f"{PID}:G-12:L2", "project_id": PID, "grid": "G-12", "level": "L2", "zone": "ZoneC",
                 "aliases": ["G-12", "G12", "G 12", "gee twelve", "G barah", "G bara", "जी 12", "column G-12",
                             "G-12 level 2", "G-12 L2", "G-12 dusra majla"]})
    zone_alias = {
        "ZoneA": ["Zone A", "zone ay", "A zone", "OPD side", "Zone-A", "झोन ए", "ज़ोन ए"],
        "ZoneB": ["Zone B", "zone bee", "B zone", "OT ICU zone", "Zone-B", "झोन बी", "ज़ोन बी"],
        "ZoneC": ["Zone C", "zone see", "C zone", "services core", "Zone-C", "झोन सी", "ज़ोन सी"],
    }
    for zid, lvl in (("ZoneA", "L4"), ("ZoneB", "L3"), ("ZoneB", "L4"), ("ZoneC", "L4")):
        locs.append({"location_id": f"{PID}:{zid}:{lvl}", "project_id": PID, "grid": None, "level": lvl, "zone": zid,
                     "aliases": [f"{a} {v}" for a in zone_alias[zid][:4] for v in _LEVEL_ALIASES[lvl][:2]]
                     + zone_alias[zid]})
    slab = {
        "L2": ["L2 slab", "level 2 slab", "second floor slab", "dusra slab", "dusrya majlyacha slab", "लेवल 2 स्लैब"],
        "L3": ["L3 slab", "level 3 slab", "level three slab", "OT slab", "OT floor slab", "third floor slab",
               "teesra slab", "tisrya majlyacha slab", "लेवल 3 स्लैब", "तिसरा स्लैब", "el three slab"],
        "L4": ["L4 slab", "level 4 slab", "ICU slab", "fourth floor slab", "chautha slab", "लेवल 4 स्लैब"],
    }
    for lvl, al in slab.items():
        locs.append({"location_id": f"{PID}:Slab:{lvl}", "project_id": PID, "grid": None, "level": lvl, "zone": None,
                     "aliases": al})
    locs += [
        {"location_id": f"{PID}:OT-1:L3", "project_id": PID, "grid": "OT-1", "level": "L3", "zone": "ZoneB",
         "aliases": ["OT block", "OT complex", "operation theatre", "modular OT", "OT-1", "ऑपरेशन थिएटर"]},
        {"location_id": f"{PID}:ICU-1:L4", "project_id": PID, "grid": "ICU-1", "level": "L4", "zone": "ZoneB",
         "aliases": ["ICU", "ICU block", "intensive care unit", "ICU-1", "आयसीयू"]},
        {"location_id": f"{PID}:LC-1:L4", "project_id": PID, "grid": "LC-1", "level": "L4", "zone": "ZoneC",
         "aliases": ["lift core", "lift shaft", "bed lift core", "LC-1", "lift core level 4", "लिफ्ट कोर"]},
        {"location_id": f"{PID}:RW-N1:B2", "project_id": PID, "grid": "RW-N1", "level": "B2", "zone": "Basement",
         "aliases": ["RW-N1", "RW N1", "north retaining wall", "basement retaining wall", "B2 retaining wall",
                     "uttar retaining wall", "रिटेनिंग वॉल"]},
        {"location_id": f"{PID}:Raft:B2", "project_id": PID, "grid": "RAFT", "level": "B2", "zone": "Basement",
         "aliases": ["raft", "raft foundation", "B2 raft", "basement raft", "raft slab", "राफ्ट"]},
        {"location_id": f"{PID}:Sump:GF", "project_id": PID, "grid": "SUMP-1", "level": "GF", "zone": "External",
         "aliases": ["sump", "sump pit", "1.2 ML sump", "fire sump", "SUMP-1", "sump ki khudai", "सम्प", "संप"]},
    ]
    return locs


# ----------------------------------------------------------------------------------------------
# BOQ (Maharashtra PWD Schedule of Rates 2025-26 style item codes; Nashik region rates, INR)
# ----------------------------------------------------------------------------------------------
_BOQ = [
    ("SSR-2.1.4", "Excavation for foundation in all types of soil and soft murum, depth 0–6 m, incl. dewatering, shoring and strutting, lead up to 50 m and lift up to 1.5 m (basement B1/B2 and sump)", "cum", 38400, 318, "MH PWD SSR 2025-26 Ch. 2; IS 3764"),
    ("SSR-2.4.2", "Excavation in hard murum / soft rock by mechanical means incl. controlled breaking (no blasting near live OPD)", "cum", 9600, 540, "MH PWD SSR 2025-26 Ch. 2"),
    ("SSR-2.9.1", "Filling in plinth and around basement retaining walls with selected murum in 150 mm layers, watered and compacted to 95% MDD", "cum", 7200, 395, "MH PWD SSR 2025-26; IS 2720 (Part 8)"),
    ("SSR-4.1.2", "Providing and laying M15 PCC below raft, footings and sump base, 100 mm thick, incl. curing", "cum", 1150, 6850, "IS 456 Cl. 6; IS 10262"),
    ("SSR-5.12.6", "Providing and laying design mix M35 RMC in raft foundation incl. pumping, retarder and thermal control (pour size ≤ 350 cum)", "cum", 5350, 8950, "IS 456 Cl. 34; IS 10262; IS 4926"),
    ("SSR-5.12.7", "Design mix M35 RMC for basement retaining walls RW-N1 to RW-S4 and lift pit walls incl. water bar at kicker", "cum", 1420, 9150, "IS 456; IS 3370 (Part 2); IS 4926"),
    ("SSR-5.12.4", "Design mix M30 RMC for RCC columns, shear walls and lift core walls, all levels B2 to terrace, incl. pumping and PCE admixture", "cum", 3860, 8720, "IS 456; IS 10262; IS 9103"),
    ("SSR-5.12.3", "Design mix M25 RMC for slabs, beams, landings and staircases at all levels incl. pumping (OT slab 200 mm, typical 175 mm)", "cum", 9800, 8240, "IS 456; IS 10262; IS 4926"),
    ("SSR-5.12.9", "Design mix M30 RMC for 1.2 ML fire & domestic sump walls and base with crystalline admixture", "cum", 610, 9400, "IS 3370 (Part 1 & 2); IS 456"),
    ("SSR-5.6.2", "Supplying, cutting, bending and placing TMT Fe500D reinforcement up to plinth (raft, retaining walls, sump) incl. binding wire", "kg", 1265000, 88.5, "IS 1786:2008; IS 2502; IS 456 Cl. 26"),
    ("SSR-5.6.3", "Supplying, cutting, bending and placing TMT Fe500D reinforcement above plinth (columns, beams, slabs, walls) incl. couplers where shown", "kg", 2940000, 91.0, "IS 1786:2008; IS 13920; SP 34"),
    ("SSR-5.8.1", "Centering and shuttering for raft edges, footings and sump walls (steel plates / ply), incl. removal", "sqm", 6800, 455, "IS 14687; IS 456 Cl. 11"),
    ("SSR-5.8.3", "Centering and shuttering for suspended slabs incl. cup-lock staging up to 4.2 m, props at ≤ 900 c/c under OT slab", "sqm", 46500, 725, "IS 14687; IS 456 Cl. 11.3"),
    ("SSR-5.8.5", "Centering and shuttering for beams, lintels and cantilevers (ply 12 mm, runners at 600 c/c)", "sqm", 27800, 760, "IS 14687"),
    ("SSR-5.8.6", "Centering and shuttering for columns and shear walls (steel column boxes / ply with tie rods)", "sqm", 21400, 790, "IS 14687"),
    ("SSR-5.10.1", "Providing and fixing 25 mm / 40 mm / 50 mm cement-concrete cover blocks of M30-equivalent strength (PVC blocks not permitted)", "nos", 185000, 4.5, "IS 456 Cl. 26.4; RFI-SSB-007"),
    ("SSR-22.3.1", "Providing crystalline integral waterproofing to raft, retaining walls and sump (dose 0.8% by weight of cement)", "kg", 38500, 118, "IS 2645; MH PWD SSR Ch. 22"),
    ("SSR-22.5.2", "APP modified bitumen membrane 4 mm to basement retaining wall external face with 50 mm PCC protection (hold point before backfill)", "sqm", 5200, 1180, "IS 1322; MH PWD SSR Ch. 22"),
    ("SSR-6.14.1", "AAC block masonry 200 mm in CM 1:4 / thin-bed adhesive for internal walls L1–L7 (density 551–650)", "cum", 5600, 5780, "IS 2185 (Part 3); IS 6041"),
    ("SSR-13.2.3", "Gypsum plaster 12 mm to internal walls and ceilings of ward and ICU areas incl. corner beads", "sqm", 96000, 262, "IS 2547"),
    ("SSR-11.8.4", "Seamless conductive/antistatic vinyl flooring 2 mm for modular OT and ICU incl. copper grounding grid", "sqm", 2350, 4650, "HTM 03-01 / NABH guidance"),
    ("SSR-10.2.6", "Structural steel for OT pendant support frames and helipad edge frames incl. welding and primer (Fe 410)", "kg", 38600, 124, "IS 800:2007; IS 2062; IS 816"),
    ("SSR-15.4.1", "Medical gas pipeline sleeves (MS / uPVC) cast in slabs and beams as per SSB-MEP-L3-431", "nos", 460, 1450, "HTM 02-01; IS 1239"),
]


def boq_items() -> list[dict]:
    return [{"boq_id": f"{PID}-BOQ-{code}", "project_id": PID, "item_code": code, "description": desc, "unit": unit,
             "qty_tendered": float(qty), "rate": float(rate), "amount": round(qty * rate, 2), "spec_ref": spec,
             "template_id": "FMT-TND-005"} for code, desc, unit, qty, rate, spec in _BOQ]


# ----------------------------------------------------------------------------------------------
# Drawing register + atomic facts
# ----------------------------------------------------------------------------------------------
def drawings() -> list[dict]:
    D = []

    def add(num, rev, title, disc, status, issued, zone, level, latest, sup_by, note):
        D.append({"drawing_id": f"{num}@{rev}", "project_id": PID, "drawing_number": num, "revision": rev,
                  "rev_ordinal": int(rev[1:]), "title": title, "discipline": disc, "status": status,
                  "issued_on": issued, "zone": zone, "level": level, "is_latest": latest,
                  "superseded_by": sup_by, "change_note": note})

    t = "Column Reinforcement Details — Level 3 (OT floor)"
    add("SSB-STR-L3-201", "R0", t, "Structural", "Superseded", "2026-06-10", None, "L3", 0, "SSB-STR-L3-201@R1",
        "First issue for construction. L3 columns: 8/12 nos 16–20 dia main bars, 8 dia ties @ 150 c/c.")
    add("SSB-STR-L3-201", "R1", t, "Structural", "Superseded", "2026-07-15", None, "L3", 0, "SSB-STR-L3-201@R2",
        "OT bay columns C-7, C-8, D-7, D-8: main bars 20 → 25 dia (12 nos), ties 10 dia, for modular OT and "
        "pendant loads (RFI-SSB-003). Tie spacing unchanged at 150 c/c.")
    add("SSB-STR-L3-201", "R2", t, "Structural", "For Construction", "2026-08-21", None, "L3", 1, None,
        "Tie spacing at C-7 and C-8 reduced from 150 to 100 c/c over full height (ductile detailing under OT "
        "pendant supports, IS 13920 Cl. 7.4) per RFI-SSB-006. All other details as R1.")
    add("SSB-STR-L4-202", "R0", "Column Reinforcement Details — Level 4 (ICU floor)", "Structural", "For Construction",
        "2026-08-28", None, "L4", 1, None, "First issue. ICU columns C-7, D-7: 12-20 dia, 8 dia ties @ 150 c/c.")
    add("SSB-STR-L3-205", "R0", "Column Schedule — Levels 2 to 4 (sizes and grades)", "Structural", "For Construction",
        "2026-06-10", None, "L3", 1, None, "Column sizes and concrete grade (M30) schedule, L2–L4.")
    add("SSB-STR-L2-210", "R0", "Level 2 Slab GA", "Structural", "For Construction", "2026-07-02", None, "L2", 1, None,
        "Typical slab 175 thk, M25, cover 25.")
    t = "Level 3 Slab GA (OT floor)"
    add("SSB-STR-L3-211", "R0", t, "Structural", "Superseded", "2026-07-28", None, "L3", 0, "SSB-STR-L3-211@R1",
        "First issue: slab 150 thk typical, M25.")
    add("SSB-STR-L3-211", "R1", t, "Structural", "For Construction", "2026-08-26", None, "L3", 1, None,
        "OT floor slab thickness increased 150 → 200 mm for modular OT floor loads and vibration control "
        "(RFI-SSB-008). Staging to be certified by structural consultant before pour.")
    add("SSB-STR-L3-212", "R0", "Level 3 Slab Reinforcement Layout (OT floor)", "Structural", "For Construction",
        "2026-08-27", None, "L3", 1, None, "Bottom mesh 12 dia @ 150 c/c both ways; top extra bars over supports.")
    t = "Level 3 Beam Layout & Reinforcement"
    add("SSB-STR-L3-221", "R0", t, "Structural", "Superseded", "2026-07-05", "ZoneB", "L3", 0, "SSB-STR-L3-221@R1",
        "First issue. Beams B3-G07 / B3-G08 300x600.")
    add("SSB-STR-L3-221", "R1", t, "Structural", "For Construction", "2026-08-02", "ZoneB", "L3", 1, None,
        "Beams B3-G07 / B3-G08 deepened 600 → 750 with 5 bottom bars and stirrups @ 125 c/c for the OT AHU duct "
        "opening (RFI-SSB-004).")
    t = "Lift Core Walls — Level 4 to Terrace"
    add("SSB-STR-L4-230", "R0", t, "Structural", "Superseded", "2026-07-20", "ZoneC", "L4", 0, "SSB-STR-L4-230@R1",
        "First issue: core walls 230 thk.")
    add("SSB-STR-L4-230", "R1", t, "Structural", "For Construction", "2026-08-18", "ZoneC", "L4", 1, None,
        "Core walls 230 → 250 thk for bed-lift machine loads (consultant memo SM-07, lift vendor data).")
    add("SSB-STR-B2-101", "R0", "Raft Foundation Plan & Reinforcement", "Structural", "For Construction", "2026-03-30",
        "Basement", "B2", 1, None, "Raft 900 thk, M35, 25 dia @ 150 c/c top and bottom, cover 50.")
    t = "Basement Retaining Wall RW-N1 Details"
    add("SSB-STR-B2-102", "R0", t, "Structural", "Superseded", "2026-04-08", "Basement", "B2", 0, "SSB-STR-B2-102@R1",
        "First issue: RW-N1 300 thk.")
    add("SSB-STR-B2-102", "R1", t, "Structural", "For Construction", "2026-05-12", "Basement", "B2", 1, None,
        "RW-N1 thickened 300 → 350 with PVC water bar at kicker; membrane waterproofing is a hold point before "
        "backfill (RFI-SSB-001).")
    add("SSB-PLB-GF-401", "R0", "1.2 ML Sump & Pump Room — Structure", "Public Health", "For Construction", "2026-08-10",
        "External", "GF", 1, None, "Sump walls 300 thk M30 (IS 3370), crystalline admixture, 45 cover.")
    t = "OT Complex Layout (Architectural)"
    add("SSB-ARC-L3-151", "R0", t, "Architectural", "Superseded", "2026-06-01", "ZoneB", "L3", 0, "SSB-ARC-L3-151@R1",
        "First issue: 6 modular OTs, pre-op and recovery.")
    add("SSB-ARC-L3-151", "R1", t, "Architectural", "For Construction", "2026-07-30", "ZoneB", "L3", 1, None,
        "OT-3 and OT-4 doors widened to 1500 clear for bed movement; scrub bay relocated (RFI-SSB-005).")
    add("SSB-MEP-L3-431", "R0", "OT Medical Gas & HVAC Sleeve Layout — Level 3", "MEP", "For Construction", "2026-08-30",
        "ZoneB", "L3", 1, None, "Sleeve positions for O2, N2O, vacuum and AHU ducts through the OT slab and beams.")
    add("SSB-ELE-L4-461", "R0", "ICU Slab Electrical Conduit Layout — Level 4", "Electrical", "For Approval",
        "2026-09-08", "ZoneB", "L4", 0, None, "Issued for approval; conduit density near ICU nurse station (RFI-SSB-010 open).")
    return D


def drawing_facts() -> list[dict]:
    F = []

    def f(did, loc, el, mark, attr, num=None, text=None, unit=None, tol=None, ref=None):
        F.append({"drawing_id": did, "location_id": loc, "element": el, "element_mark": mark, "attribute": attr,
                  "value_num": num, "value_text": text, "unit": unit, "tolerance": tol, "code_ref": ref})

    # --- SSB-STR-L3-201 column reinforcement, three revisions --------------------------------
    for rev in ("R0", "R1", "R2"):
        did = f"SSB-STR-L3-201@{rev}"
        for g in L3_COLUMNS:
            loc = f"{PID}:{g}:L3"
            ot = g in OT_BAY
            spacing = 100 if (rev == "R2" and g in PENDANT) else 150
            dia = (25 if rev != "R0" else 20) if ot else 16
            bars = 12 if ot else 8
            tie = 10 if (ot and rev != "R0") else 8
            f(did, loc, "column", g, "rebar_spacing", spacing, None, "mm", 10,
              "IS 13920 Cl. 7.4; IS 456 Cl. 26.5.3.2(c)" if spacing == 100 else "IS 456 Cl. 26.5.3.2(c)")
            f(did, loc, "column", g, "rebar_dia", dia, None, "mm", 0, "IS 456 Cl. 26.5.3.1; IS 1786")
            f(did, loc, "column", g, "bar_count", bars, None, "nos", 0, "IS 456 Cl. 26.5.3.1(c)")
            f(did, loc, "column", g, "tie_dia", tie, None, "mm", 0, "IS 456 Cl. 26.5.3.2(c)")
            f(did, loc, "column", g, "cover", 40, None, "mm", 5, "IS 456 Cl. 26.4 (moderate exposure, Table 16)")
    # --- SSB-STR-L4-202 ICU columns -------------------------------------------------------
    for g in L4_COLUMNS:
        loc = f"{PID}:{g}:L4"
        did = "SSB-STR-L4-202@R0"
        f(did, loc, "column", g, "rebar_spacing", 150, None, "mm", 10, "IS 456 Cl. 26.5.3.2(c)")
        f(did, loc, "column", g, "rebar_dia", 20, None, "mm", 0, "IS 456 Cl. 26.5.3.1; IS 1786")
        f(did, loc, "column", g, "bar_count", 12, None, "nos", 0, "IS 456 Cl. 26.5.3.1(c)")
        f(did, loc, "column", g, "tie_dia", 8, None, "mm", 0, "IS 456 Cl. 26.5.3.2(c)")
        f(did, loc, "column", g, "cover", 40, None, "mm", 5, "IS 456 Cl. 26.4 (moderate exposure, Table 16)")
    # --- SSB-STR-L3-205 column schedule: size + grade -------------------------------------
    sizes = {"B-4": "450x600", "C-6": "600x600", "C-7": "600x600", "C-8": "600x600", "C-9": "600x600",
             "D-7": "600x600", "D-8": "600x600", "E-7": "600x600", "E-8": "600x600", "F-10": "450x750",
             "H-12": "500x500"}
    sched = [(f"{PID}:{g}:L3", g, s) for g, s in sizes.items()] + [
        (f"{PID}:C-7:L4", "C-7", "600x600"), (f"{PID}:D-7:L4", "D-7", "600x600"), (f"{PID}:G-12:L2", "G-12", "450x600")]
    for loc, g, s in sched:
        f("SSB-STR-L3-205@R0", loc, "column", g, "size", None, s, "mm", 5, "IS 456 Cl. 11 (formwork tolerance)")
        f("SSB-STR-L3-205@R0", loc, "column", g, "grade", 30, "M30", "MPa", 0, "IS 456 Table 5")
    # --- slabs -----------------------------------------------------------------------------
    f("SSB-STR-L2-210@R0", f"{PID}:Slab:L2", "slab", "S2-TYP", "thickness", 175, None, "mm", 5, "IS 456 Cl. 24.1")
    f("SSB-STR-L2-210@R0", f"{PID}:Slab:L2", "slab", "S2-TYP", "cover", 25, None, "mm", 5, "IS 456 Cl. 26.4.2.2")
    f("SSB-STR-L2-210@R0", f"{PID}:Slab:L2", "slab", "S2-TYP", "grade", 25, "M25", "MPa", 0, "IS 456 Table 5")
    f("SSB-STR-L3-211@R0", f"{PID}:Slab:L3", "slab", "S3-OT", "thickness", 150, None, "mm", 5, "IS 456 Cl. 24.1")
    f("SSB-STR-L3-211@R0", f"{PID}:Slab:L3", "slab", "S3-OT", "grade", 25, "M25", "MPa", 0, "IS 456 Table 5")
    f("SSB-STR-L3-211@R0", f"{PID}:Slab:L3", "slab", "S3-OT", "cover", 25, None, "mm", 5, "IS 456 Cl. 26.4.2.2")
    f("SSB-STR-L3-211@R1", f"{PID}:Slab:L3", "slab", "S3-OT", "thickness", 200, None, "mm", 5, "IS 456 Cl. 24.1; RFI-SSB-008")
    f("SSB-STR-L3-211@R1", f"{PID}:Slab:L3", "slab", "S3-OT", "grade", 25, "M25", "MPa", 0, "IS 456 Table 5")
    f("SSB-STR-L3-211@R1", f"{PID}:Slab:L3", "slab", "S3-OT", "cover", 25, None, "mm", 5, "IS 456 Cl. 26.4.2.2")
    f("SSB-STR-L3-211@R1", f"{PID}:Slab:L3", "slab", "S3-OT", "level", 10.650, None, "m", 0.01, "Top of slab (TOS) +10.650")
    f("SSB-STR-L3-212@R0", f"{PID}:Slab:L3", "slab", "S3-OT", "rebar_dia", 12, None, "mm", 0, "IS 456 Cl. 26.5.2.2")
    f("SSB-STR-L3-212@R0", f"{PID}:Slab:L3", "slab", "S3-OT", "rebar_spacing", 150, None, "mm", 10, "IS 456 Cl. 26.3.3(b)")
    # --- beams (own locations, so column questions are never element-ambiguous) ----------------
    for rev, depth, stir, bars in (("R0", 600, 150, 4), ("R1", 750, 125, 5)):
        did = f"SSB-STR-L3-221@{rev}"
        for g, mark in L3_BEAMS.items():
            loc = f"{PID}:{g}:L3"
            f(did, loc, "beam", mark, "size", None, f"300x{depth}", "mm", 5, "IS 456 Cl. 11")
            f(did, loc, "beam", mark, "rebar_spacing", stir, None, "mm", 10, "IS 456 Cl. 26.5.1.5; IS 13920 Cl. 6.3")
            f(did, loc, "beam", mark, "rebar_dia", 20, None, "mm", 0, "IS 456 Cl. 26.5.1")
            f(did, loc, "beam", mark, "bar_count", bars, None, "nos", 0, "IS 456 Cl. 26.5.1.1")
            f(did, loc, "beam", mark, "cover", 30, None, "mm", 5, "IS 456 Cl. 26.4 (moderate exposure)")
    # --- lift core ------------------------------------------------------------------------
    f("SSB-STR-L4-230@R0", f"{PID}:LC-1:L4", "wall", "LC-1", "thickness", 230, None, "mm", 5, "IS 456 Cl. 32")
    f("SSB-STR-L4-230@R0", f"{PID}:LC-1:L4", "wall", "LC-1", "grade", 30, "M30", "MPa", 0, "IS 456 Table 5")
    f("SSB-STR-L4-230@R1", f"{PID}:LC-1:L4", "wall", "LC-1", "thickness", 250, None, "mm", 5, "IS 456 Cl. 32")
    f("SSB-STR-L4-230@R1", f"{PID}:LC-1:L4", "wall", "LC-1", "grade", 30, "M30", "MPa", 0, "IS 456 Table 5")
    f("SSB-STR-L4-230@R1", f"{PID}:LC-1:L4", "wall", "LC-1", "cover", 40, None, "mm", 5, "IS 456 Cl. 26.4")
    f("SSB-STR-L4-230@R1", f"{PID}:LC-1:L4", "wall", "LC-1", "rebar_spacing", 200, None, "mm", 10, "IS 456 Cl. 32.5")
    f("SSB-STR-L4-230@R1", f"{PID}:LC-1:L4", "wall", "LC-1", "rebar_dia", 12, None, "mm", 0, "IS 456 Cl. 32.5")
    # --- raft + retaining wall + sump ------------------------------------------------------
    for attr, num, text, unit, tol, ref in (("thickness", 900, None, "mm", 10, "IS 456 Cl. 34"),
                                            ("cover", 50, None, "mm", 5, "IS 456 Cl. 26.4.2.2 (footings)"),
                                            ("grade", 35, "M35", "MPa", 0, "IS 456 Table 5"),
                                            ("rebar_dia", 25, None, "mm", 0, "IS 456 Cl. 34.5"),
                                            ("rebar_spacing", 150, None, "mm", 10, "IS 456 Cl. 26.3.3")):
        f("SSB-STR-B2-101@R0", f"{PID}:Raft:B2", "footing", "RAFT-1", attr, num, text, unit, tol, ref)
    f("SSB-STR-B2-102@R0", f"{PID}:RW-N1:B2", "wall", "RW-N1", "thickness", 300, None, "mm", 5, "IS 456 Cl. 32")
    f("SSB-STR-B2-102@R0", f"{PID}:RW-N1:B2", "wall", "RW-N1", "cover", 50, None, "mm", 5, "IS 456 Cl. 26.4")
    f("SSB-STR-B2-102@R0", f"{PID}:RW-N1:B2", "wall", "RW-N1", "grade", 35, "M35", "MPa", 0, "IS 456 Table 5")
    f("SSB-STR-B2-102@R1", f"{PID}:RW-N1:B2", "wall", "RW-N1", "thickness", 350, None, "mm", 5, "IS 456 Cl. 32; RFI-SSB-001")
    f("SSB-STR-B2-102@R1", f"{PID}:RW-N1:B2", "wall", "RW-N1", "cover", 50, None, "mm", 5, "IS 456 Cl. 26.4")
    f("SSB-STR-B2-102@R1", f"{PID}:RW-N1:B2", "wall", "RW-N1", "grade", 35, "M35", "MPa", 0, "IS 456 Table 5")
    f("SSB-STR-B2-102@R1", f"{PID}:RW-N1:B2", "wall", "RW-N1", "rebar_spacing", 150, None, "mm", 10, "IS 456 Cl. 32.5")
    f("SSB-STR-B2-102@R1", f"{PID}:RW-N1:B2", "wall", "RW-N1", "rebar_dia", 16, None, "mm", 0, "IS 456 Cl. 32.5")
    f("SSB-PLB-GF-401@R0", f"{PID}:Sump:GF", "tank", "SUMP-1", "thickness", 300, None, "mm", 5, "IS 3370 (Part 2)")
    f("SSB-PLB-GF-401@R0", f"{PID}:Sump:GF", "tank", "SUMP-1", "cover", 45, None, "mm", 5, "IS 3370 (Part 2) Cl. 7")
    f("SSB-PLB-GF-401@R0", f"{PID}:Sump:GF", "tank", "SUMP-1", "grade", 30, "M30", "MPa", 0, "IS 3370 (Part 1)")
    # --- MEP sleeves in the OT zone -----------------------------------------------------------
    for mark, size, ref in (("SL-OT-01", 100, "HTM 02-01 (O2 riser sleeve)"), ("SL-OT-02", 80, "HTM 02-01 (vacuum sleeve)"),
                            ("SL-OT-03", 150, "HTM 02-01 (medical gas manifold sleeve)")):
        f("SSB-MEP-L3-431@R0", f"{PID}:ZoneB:L3", "pipe", mark, "size", size, None, "mm", 0, ref)
    return F


# ----------------------------------------------------------------------------------------------
# RFIs, submittals, DPRs, permits, checklists, observations
# ----------------------------------------------------------------------------------------------
def _rfi(rid, subject, loc, dref, spec, status, q, a, raised, answered, impact, result):
    return {"rfi_id": rid, "subject": subject, "location_id": loc, "drawing_ref": dref, "spec_ref": spec,
            "status": status, "question": q, "response": a, "raised_on": raised, "answered_on": answered,
            "impact": impact, "resulting_drawing_id": result}


RFIS = [
    _rfi("RFI-SSB-001", "RW-N1 retaining wall thickness and water bar at kicker", f"{PID}:RW-N1:B2", "SSB-STR-B2-102",
         "IS 456 Cl. 32; IS 3370 (Part 2)", "Closed",
         "Water table observed at 3.1 m during B2 excavation. SSB-STR-B2-102 R0 shows 300 mm wall with no water bar. Confirm section and kicker detail.",
         "Increase RW-N1 to 350 mm with PVC water bar at kicker; membrane waterproofing inspection is a hold point before backfill. SSB-STR-B2-102 R1 issued.",
         "2026-04-20", "2026-05-09", "Revision issued: SSB-STR-B2-102 R1", "SSB-STR-B2-102@R1"),
    _rfi("RFI-SSB-002", "Raft construction joint location and waterproofing lap", f"{PID}:Raft:B2", "SSB-STR-B2-101",
         "IS 456 Cl. 13.4", "Closed",
         "Raft pour 3 (Zone C) exceeds 350 cum in one go. Propose construction joint along grid 9 with shear keys; confirm membrane lap.",
         "Accepted. Joint along grid 9 with 75 mm shear key and hydrophilic strip; 150 mm membrane lap. No drawing change (SI-014).",
         "2026-04-02", "2026-04-06", "No revision; site instruction SI-014", None),
    _rfi("RFI-SSB-003", "OT bay column main bars for modular OT and pendant loads", f"{PID}:C-7:L3", "SSB-STR-L3-201",
         "IS 456 Cl. 26.5.3.1; IS 1893", "Closed",
         "Modular OT vendor data shows ceiling pendant and laminar-flow loads higher than design basis. Confirm main bars for C-7, C-8, D-7, D-8.",
         "Upgrade main bars to 12 nos 25 dia with 10 dia ties for C-7, C-8, D-7, D-8. SSB-STR-L3-201 R1 issued 15-Jul-2026.",
         "2026-07-02", "2026-07-13", "Revision issued: SSB-STR-L3-201 R1", "SSB-STR-L3-201@R1"),
    _rfi("RFI-SSB-004", "Beam B3-G07/B3-G08 depth clash with OT AHU duct", f"{PID}:G-8:L3", "SSB-STR-L3-221",
         "IS 456 Cl. 23", "Closed",
         "1200x400 AHU supply duct to OT-3 passes under B3-G08 at 600 deep; false-ceiling height falls below 3.0 m. Advise.",
         "Deepen B3-G07/B3-G08 to 750 with 5 bottom bars, stirrups @ 125 c/c, duct opening per detail 7. SSB-STR-L3-221 R1 issued.",
         "2026-07-18", "2026-07-31", "Revision issued: SSB-STR-L3-221 R1", "SSB-STR-L3-221@R1"),
    _rfi("RFI-SSB-005", "OT-3 / OT-4 door clear width for bed movement", f"{PID}:OT-1:L3", "SSB-ARC-L3-151",
         "NABH OT guidelines; NBC 2016", "Closed",
         "SSB-ARC-L3-151 R0 shows 1200 clear doors to OT-3 and OT-4; ICU beds with monitors need 1500. Confirm.",
         "Widen OT-3 and OT-4 doors to 1500 clear and relocate scrub bay. SSB-ARC-L3-151 R1 issued.",
         "2026-07-10", "2026-07-28", "Revision issued: SSB-ARC-L3-151 R1", "SSB-ARC-L3-151@R1"),
    _rfi("RFI-SSB-006", "Tie spacing at C-7 and C-8 under OT pendant supports", f"{PID}:C-7:L3", "SSB-STR-L3-201",
         "IS 13920 Cl. 7.4; IS 456 Cl. 26.5.3.2", "Answered",
         "SSB-STR-L3-201 R1 shows 10 dia ties @ 150 c/c at C-7 and C-8. Pendant support brackets sit at mid-height; confirm confinement spacing.",
         "Adopt 10 dia ties @ 100 c/c over full height for C-7 and C-8 (ductile detailing). SSB-STR-L3-201 R2 issued 21-Aug-2026.",
         "2026-08-08", "2026-08-19", "Revision issued: SSB-STR-L3-201 R2", "SSB-STR-L3-201@R2"),
    _rfi("RFI-SSB-007", "Cover block type for OT slab and columns", f"{PID}:Slab:L3", "SSB-STR-L3-211",
         "IS 456 Cl. 26.4", "Answered",
         "Contractor proposes 25 mm PVC cover blocks for the OT slab bottom mesh and 40 mm PVC for columns. Acceptable?",
         "No. Use cement-concrete cover blocks of M30-equivalent strength: 25 mm slab, 40 mm column, 30 mm beam. No drawing change (SI-021).",
         "2026-08-22", "2026-08-25", "No revision; site instruction SI-021", None),
    _rfi("RFI-SSB-008", "Level 3 OT slab thickness 150 vs 200", f"{PID}:Slab:L3", "SSB-STR-L3-211",
         "IS 456 Cl. 24.1", "Answered",
         "Modular OT floor loads and vibration criteria from the OT vendor exceed what a 150 mm slab (SSB-STR-L3-211 R0) was designed for. Confirm thickness.",
         "OT floor slab revised to 200 mm, M25. SSB-STR-L3-211 R1 issued 26-Aug-2026; staging to be certified before pour.",
         "2026-08-12", "2026-08-24", "Revision issued: SSB-STR-L3-211 R1", "SSB-STR-L3-211@R1"),
    _rfi("RFI-SSB-009", "Medical gas sleeve SL-OT-03 clashes with beam B3-G08", f"{PID}:ZoneB:L3", "SSB-MEP-L3-431",
         None, "Open",
         "Sleeve SL-OT-03 (150 dia) on SSB-MEP-L3-431 R0 falls 90 mm from the face of beam B3-G08. Can it shift 250 mm towards OT-3?",
         None, "2026-09-06", None, "Pending — L3 OT slab pour dependency", None),
    _rfi("RFI-SSB-010", "Electrical conduit density in ICU slab near nurse station", f"{PID}:Slab:L4", "SSB-ELE-L4-461",
         "IS 456 Cl. 11.5", "Open",
         "SSB-ELE-L4-461 (For Approval) shows 9 conduits of 25 dia crossing within 400 mm at the ICU nurse station. Confirm reroute before L4 reinforcement.",
         None, "2026-09-08", None, "Pending — L4 slab dependency", None),
    _rfi("RFI-SSB-011", "Sump excavation shoring after groundwater at 3.2 m", f"{PID}:Sump:GF", "SSB-PLB-GF-401",
         "IS 3764; BOCW Rules 1998", "Open",
         "Sump excavation hit groundwater at 3.2 m after rain on 8-Sep; murum sides slumping. Provide shoring design and dewatering scheme before restart.",
         None, "2026-09-09", None, "Pending — excavation permit EXC-2017 suspended", None),
    _rfi("RFI-SSB-012", "Staircase ST-2 waist slab thickness at L3–L4 mid-landing", f"{PID}:ZoneC:L4", "SSB-STR-L3-211",
         "IS 456 Cl. 33", "Open",
         "ST-2 waist slab is not dimensioned on SSB-STR-L3-211 R1. Confirm 175 mm?",
         None, "2026-09-10", None, "Pending", None),
]

SUBMITTALS = [
    {"submittal_id": "SUB-SSB-001", "type": "Material", "material": "TMT bars Fe 500D (8–32 dia) — primary producer",
     "spec_section": "IS 1786:2008", "status": "Approved",
     "reviewer_comments": "Approved. MTC with each lot; tensile, bend and rebend tests per 40 t at Nashik Materials Testing Lab.",
     "submitted_on": "2026-02-24", "reviewed_on": "2026-03-02", "template_hint": "QC-STL-REG-001"},
    {"submittal_id": "SUB-SSB-002", "type": "Material", "material": "RMC design mix M30 (columns, shear walls) — mix design report",
     "spec_section": "IS 10262:2019; IS 456 Cl. 9", "status": "Approved as Noted",
     "reviewer_comments": "w/c capped at 0.40; slump 120±25 with PCE admixture; trial cubes 7/28 day witnessed by PMC.",
     "submitted_on": "2026-03-05", "reviewed_on": "2026-03-14", "template_hint": "QC-CON-FRM-001"},
    {"submittal_id": "SUB-SSB-003", "type": "Material", "material": "RMC design mix M35 (raft, retaining walls) with retarder",
     "spec_section": "IS 10262:2019; IS 456 Cl. 34", "status": "Approved",
     "reviewer_comments": "Approved. Placing temperature ≤ 32 °C; thermocouples in raft pours over 1 m depth.",
     "submitted_on": "2026-03-10", "reviewed_on": "2026-03-18", "template_hint": None},
    {"submittal_id": "SUB-SSB-004", "type": "Method Statement", "material": "Method statement — L3 OT slab 200 mm pour, cup-lock staging and sequence",
     "spec_section": "IS 456 Cl. 11, 13, 14; IS 14687", "status": "Under Review",
     "reviewer_comments": "Pending: staging design certificate from structural consultant (props @ 900 c/c) and construction joint over OT-3.",
     "submitted_on": "2026-09-04", "reviewed_on": None, "template_hint": "QC-CON-FRM-002"},
    {"submittal_id": "SUB-SSB-005", "type": "Material", "material": "Crystalline waterproofing admixture — sump and RW-N1",
     "spec_section": "IS 2645; IS 3370", "status": "Approved as Noted",
     "reviewer_comments": "Dose 0.8% by cement weight; third-party permeability test (DIN 1048) report to be attached per lot.",
     "submitted_on": "2026-07-22", "reviewed_on": "2026-08-01", "template_hint": None},
    {"submittal_id": "SUB-SSB-006", "type": "Material", "material": "PVC cover blocks 25 mm / 40 mm",
     "spec_section": "IS 456 Cl. 26.4", "status": "Rejected",
     "reviewer_comments": "Rejected — use cement-concrete cover blocks (RFI-SSB-007 / SI-021).",
     "submitted_on": "2026-08-20", "reviewed_on": "2026-08-25", "template_hint": None},
    {"submittal_id": "SUB-SSB-007", "type": "Shop Drawing", "material": "Modular OT wall panel lifting frames and anchor details",
     "spec_section": "IS 800:2007; lifting plan LP-OT-02", "status": "Under Review",
     "reviewer_comments": "Awaiting load test certificate for lifting frames and revised tag-line arrangement (no swing over east wing).",
     "submitted_on": "2026-09-03", "reviewed_on": None, "template_hint": None},
    {"submittal_id": "SUB-SSB-008", "type": "MTC", "material": "OPC 53 grade cement — MTC batch 0826/NSK",
     "spec_section": "IS 269:2015", "status": "Approved",
     "reviewer_comments": "MTC complies; site setting time and fineness OK.", "submitted_on": "2026-08-27",
     "reviewed_on": "2026-08-29", "template_hint": "QC-CEM-REG-001"},
]

DPRS = [
    {"log_date": "2026-09-05", "weather": "Heavy rain 04:00–09:00 (38 mm), overcast, 22–27 °C",
     "manpower": {"mason": 18, "bar_bender": 16, "carpenter": 22, "helper": 38, "welder": 3, "electrician": 5, "plumber": 4, "supervisor": 5},
     "work_done": "Work started 10:00 after rain. L3 columns C-6, C-9, E-7, E-8 reinforcement fixed to SSB-STR-L3-201 R2. OT slab cup-lock staging Zone B 70% erected. Basement dewatering pumps running at sump pit.",
     "materials": {"TMT Fe500D received (t)": 24.6, "OPC 53 (bags)": 600, "cup-lock verticals (nos)": 420},
     "equipment": {"tower crane TC-1": "working", "tower crane TC-2": "idle — wind check", "dewatering pumps 5 HP": 3},
     "safety": "Nil. Toolbox talk: wet formwork and slab-edge protection in monsoon."},
    {"log_date": "2026-09-06", "weather": "Intermittent showers, 23–28 °C",
     "manpower": {"mason": 20, "bar_bender": 18, "carpenter": 24, "helper": 41, "welder": 3, "electrician": 6, "plumber": 4, "supervisor": 5},
     "work_done": "C-7 / C-8 cages fixed with 12-25 dia and 10 dia ties @ 100 c/c per SSB-STR-L3-201 R2. OT slab bottom mesh started in OT-1/OT-2. RFI-SSB-009 raised for sleeve SL-OT-03 clash with beam B3-G08.",
     "materials": {"binding wire (kg)": 180, "cover blocks 40 mm concrete (nos)": 900},
     "equipment": {"tower crane TC-1": "working", "bar bending machine": 3},
     "safety": "Near miss: unsecured cup-lock ledger at L3 edge during gusts. Area barricaded and re-secured."},
    {"log_date": "2026-09-07", "weather": "Cloudy, light drizzle 15:00–16:30, 22–29 °C",
     "manpower": {"mason": 22, "bar_bender": 17, "carpenter": 23, "helper": 44, "welder": 4, "electrician": 6, "plumber": 5, "supervisor": 5},
     "work_done": "L3 column pour C-6, C-9, E-7, E-8 (M30 RMC, 11.4 cum), 6 cubes cast and witnessed by lab. ICU (L4) column starter bars checked for C-7 and D-7. Facade scaffold Zone A up to L4 completed and tagged green.",
     "materials": {"RMC M30 (cum)": 11.4, "PCE admixture (kg)": 38},
     "equipment": {"concrete pump": "working 4 h", "needle vibrators": 4},
     "safety": "PPE audit: 3 workers on Zone A scaffold without double lanyard — stopped and re-briefed."},
    {"log_date": "2026-09-08", "weather": "Heavy rain after 13:00 (52 mm), work stopped 14:00",
     "manpower": {"mason": 16, "bar_bender": 14, "carpenter": 18, "helper": 30, "welder": 2, "electrician": 4, "plumber": 3, "supervisor": 5},
     "work_done": "Sump excavation reached 3.2 m; groundwater ingress and murum sides slumping after rain. Excavation stopped, permit EXC-2017 suspended. OT slab bottom mesh OT-3/OT-4 40%.",
     "materials": {"TMT Fe500D received (t)": 9.8, "tarpaulin (sqm)": 600},
     "equipment": {"excavator EX-200": "standby — excavation suspended", "dewatering pumps": 4},
     "safety": "Sump edge exclusion zone set at 2 m; no entry into excavation."},
    {"log_date": "2026-09-09", "weather": "Overcast, dry, 23–29 °C",
     "manpower": {"mason": 21, "bar_bender": 19, "carpenter": 25, "helper": 42, "welder": 4, "electrician": 7, "plumber": 5, "supervisor": 6},
     "work_done": "Hot work (welding) for OT pendant support frames at Zone B L3 under HWP-2029, closed 17:15. OT slab top bars started. RFI-SSB-011 raised for sump shoring. NCR-SSB-004 raised: B-4 L3 column cover 30 mm measured (req. 40).",
     "materials": {"structural steel Fe 410 (kg)": 1850, "welding rods E7018 (kg)": 30},
     "equipment": {"welding sets": 3, "tower crane TC-1": "working"},
     "safety": "Nil. 2 x 9 kg DCP extinguishers and fire watcher present during HWP-2029."},
    {"log_date": "2026-09-10", "weather": "Partly cloudy, 24–30 °C",
     "manpower": {"mason": 20, "bar_bender": 18, "carpenter": 22, "helper": 40, "welder": 3, "electrician": 7, "plumber": 5, "supervisor": 6},
     "work_done": "C-7 / C-8 columns poured (M30, 5.2 cum) after pre-pour release CL-PP-SSB-C78-001. OT modular panel lift trial under LFT-2009 by TC-2 — swing radius barricade over east wing walkway incomplete, lifts paused. OT slab medical gas sleeves being placed except SL-OT-03.",
     "materials": {"RMC M30 (cum)": 5.2, "concrete cover blocks 25 mm (nos)": 2400},
     "equipment": {"tower crane TC-2": "paused 11:30 — barricade", "concrete pump": "working 2 h"},
     "safety": "Observation: crane load path close to live OPD east-wing walkway; lifting stopped until barricade completed."},
    {"log_date": "2026-09-11", "weather": "Light rain morning (9 mm), cloudy, 22–28 °C",
     "manpower": {"mason": 19, "bar_bender": 20, "carpenter": 21, "helper": 39, "welder": 3, "electrician": 8, "plumber": 5, "supervisor": 6},
     "work_done": "Pre-pour inspection of L3 OT slab (SSB-STR-L3-211 R1, 200 mm) — HOLD raised: cover 15–18 mm at 4 locations, staging not yet certified by structural consultant, RFI-SSB-009 open. Pour planned 13-Sep subject to release. Lift core (Zone C L4) embed plate welding started under HWP-2031.",
     "materials": {"concrete cover blocks 25 mm (nos)": 1500, "MS embed plates (nos)": 24},
     "equipment": {"welding sets": 2, "tower crane TC-1": "working"},
     "safety": "HSE walk: no fire watcher at lift core welding (HWP-2031) at 15:40 — reported to site in-charge."},
]

PERMITS = [
    {"permit_id": "HWP-2031", "permit_type": "hot_work", "location_id": f"{PID}:ZoneC:L4",
     "valid_from": "2026-09-11T08:00", "valid_to": "2026-09-11T18:00", "status": "Active",
     "issued_by": "Rajesh Yadav (HSE Officer)", "template_pref": ["QC-HSE-PRM-002", "PMC-SAF-PMT-001"],
     "unsatisfied_keywords": ["fire watch", "fire watcher", "fire-watch"]},
    {"permit_id": "WAH-2044", "permit_type": "height", "location_id": f"{PID}:ZoneA:L4",
     "valid_from": "2026-09-11T08:00", "valid_to": "2026-09-11T18:00", "status": "Active",
     "issued_by": "Rajesh Yadav (HSE Officer)", "template_pref": ["QC-HSE-PRM-001"], "unsatisfied_keywords": []},
    {"permit_id": "EXC-2017", "permit_type": "excavation", "location_id": f"{PID}:Sump:GF",
     "valid_from": "2026-09-07T08:00", "valid_to": "2026-09-14T18:00", "status": "Suspended",
     "issued_by": "Imran Khan (Site Engineer)", "template_pref": ["QC-HSE-PRM-005"],
     "unsatisfied_keywords": ["shoring", "groundwater", "heavy rain"]},
    {"permit_id": "LFT-2009", "permit_type": "lifting", "location_id": f"{PID}:ZoneB:L3",
     "valid_from": "2026-09-10T08:00", "valid_to": "2026-09-12T18:00", "status": "Active",
     "issued_by": "Rajesh Yadav (HSE Officer)", "template_pref": ["QC-HSE-PRM-004"],
     "unsatisfied_keywords": ["swing radius"]},
    {"permit_id": "HWP-2029", "permit_type": "hot_work", "location_id": f"{PID}:ZoneB:L3",
     "valid_from": "2026-09-09T08:00", "valid_to": "2026-09-09T18:00", "status": "Closed",
     "issued_by": "Rajesh Yadav (HSE Officer)", "template_pref": ["QC-HSE-PRM-002"], "unsatisfied_keywords": []},
]

CHECKLISTS = [
    {"instance_id": "CL-PP-SSB-L3-001", "template_id": "QC-CON-CHK-001", "location_id": f"{PID}:Slab:L3",
     "element": "slab", "element_mark": "S3-OT", "drawing_id": "SSB-STR-L3-211@R1",
     "planned_activity": "concrete_pour", "planned_for": "2026-09-13",
     "status": "Hold", "hold_point_released": 0, "inspected_by": "Sneha Pawar (QA/QC Engineer)",
     "inspected_on": "2026-09-11",
     "notes": "HOLD — cover 15–18 mm at 4 locations in OT-3/OT-4 bottom mesh (req. 25 ±5); staging for 200 mm OT slab "
              "not certified by structural consultant (Dr. V. N. Rao); RFI-SSB-009 sleeve clash open; PMC QA release pending.",
     "item_overrides": [
         {"match": ["cover"], "status": "HOLD", "remarks": "Cover 15–18 mm at 4 locations, OT-3/OT-4 (req. 25 ±5). PVC blocks being replaced with 25 mm concrete blocks (SI-021)."},
         {"match": ["conduit", "embedded", "sleeve"], "status": "HOLD", "remarks": "RFI-SSB-009 open — medical gas sleeve SL-OT-03 clashes with beam B3-G08."},
         {"match": ["formwork", "staging", "prop"], "status": "HOLD", "remarks": "Staging for 200 mm OT slab (props @ 900 c/c) not yet certified by the structural consultant."},
         {"match": ["hold point"], "status": "HOLD", "remarks": "ITP hold point not signed off by PMC QA (Tandon Infra, Meera Joshi)."},
         {"match": ["consultant"], "status": "pending", "remarks": "Awaiting structural consultant release."},
         {"match": ["verdict"], "status": "HOLD — CORRECTIONS REQUIRED", "remarks": None},
         {"match": ["cube", "slump", "curing", "pump", "vibrator", "weather", "lighting", "concrete delivery", "batch"],
          "status": "pending", "remarks": "To be verified on pour day (cubes witnessed by Nashik Materials Testing Lab)."},
     ]},
    {"instance_id": "CL-PP-SSB-C78-001", "template_id": "QC-CON-CHK-001", "location_id": f"{PID}:C-7:L3",
     "element": "column", "element_mark": "C-7", "drawing_id": "SSB-STR-L3-201@R2",
     "planned_activity": "concrete_pour", "planned_for": "2026-09-10",
     "status": "Released", "hold_point_released": 1, "inspected_by": "Sneha Pawar (QA/QC Engineer)",
     "inspected_on": "2026-09-10", "notes": "Released for pour 10-Sep 10:40 by PMC QA. C-7/C-8 ties 100 c/c verified vs SSB-STR-L3-201 R2.",
     "item_overrides": []},
]


def _obs(oid, text, summary, loc, el, attr, val, unit, did, rev, kinds, clar, decision, rfi, at):
    return {"observation_id": oid, "project_id": PID, "session_id": None, "spoken_text": text,
            "structured_summary": summary, "location_id": loc, "element": el, "attribute": attr,
            "value_claimed": val, "unit": unit, "drawing_id": did, "revision_claimed": rev,
            "contradiction_flag": 1 if kinds else 0, "contradiction_kinds": json.dumps(kinds),
            "clarification_asked": clar, "final_decision": decision, "linked_rfi_id": rfi,
            "linked_template_id": "QC-SPW-REG-004", "created_at": at}


OBSERVATIONS = [
    _obs("OBS-000201", "C-8 column pe cover chaalees mm check kiya, concrete blocks lage hain.",
         "Column C-8 L3: cover 40 mm measured; concrete cover blocks installed (per RFI-SSB-007).",
         f"{PID}:C-8:L3", "column", "cover", 40, "mm", "SSB-STR-L3-201@R2", "R2", [], None, "log_observation",
         "RFI-SSB-007", "2026-09-09T11:05:00+05:30"),
    _obs("OBS-000202", "C-7 ke ties sau mm pe hain, R2 ke hisaab se theek.",
         "Column C-7 L3: tie spacing 100 mm matches SSB-STR-L3-201 R2.",
         f"{PID}:C-7:L3", "column", "rebar_spacing", 100, "mm", "SSB-STR-L3-201@R2", "R2", [], None, "log_observation",
         "RFI-SSB-006", "2026-09-10T09:20:00+05:30"),
    _obs("OBS-000203", "B-4 column level 3 cover tees mm aa raha hai, NCR daalo.",
         "Column B-4 L3: cover 30 mm measured vs 40 ±5 on SSB-STR-L3-201 R2 — NCR-SSB-004 raised.",
         f"{PID}:B-4:L3", "column", "cover", 30, "mm", "SSB-STR-L3-201@R2", None, ["dimension_mismatch"],
         "B-4, Level 3 ki cover drawing SSB-STR-L3-201 R2 mein 40 mm plus minus 5 hai; aapka 30 mm tolerance se bahar hai.",
         "raise_ncr", None, "2026-09-09T15:30:00+05:30"),
    _obs("OBS-000204", "Sump ki khudai rok do, pani aa gaya hai aur side gir rahi hai.",
         "Sump excavation: groundwater at 3.2 m, sides slumping — work stopped; EXC-2017 suspended pending RFI-SSB-011.",
         f"{PID}:Sump:GF", None, "activity:excavation", None, None, "SSB-PLB-GF-401@R0", None, ["permit_blocker"],
         "Permit EXC-2017 suspended hai; shoring aur dewatering ke bina khudai nahi ho sakti.", "stop_work",
         "RFI-SSB-011", "2026-09-08T14:10:00+05:30"),
    _obs("OBS-000205", "RW-N1 retaining wall thickness 350 check kiya, water bar laga hai.",
         "RW-N1 B2: wall thickness 350 mm verified against SSB-STR-B2-102 R1; water bar at kicker in place.",
         f"{PID}:RW-N1:B2", "wall", "thickness", 350, "mm", "SSB-STR-B2-102@R1", "R1", [], None, "log_observation",
         "RFI-SSB-001", "2026-05-28T16:45:00+05:30"),
    _obs("OBS-000206", "G-8 beam stirrups 125 pe hain, 750 deep beam.",
         "Beam B3-G08 at G-8 L3: stirrup spacing 125 mm matches SSB-STR-L3-221 R1.",
         f"{PID}:G-8:L3", "beam", "rebar_spacing", 125, "mm", "SSB-STR-L3-221@R1", "R1", [], None, "log_observation",
         "RFI-SSB-004", "2026-08-12T12:00:00+05:30"),
]

# Short paraphrased code notes for this project (NSK values; not verbatim code text).
CODE_CLAUSES = [
    ("IS 456 Cl. 26.4", "IS 456 Cl. 26.4 — Nominal cover depends on exposure (Table 16); Nashik block is moderate exposure. "
                        "Project NSK nominal covers: raft / footing 50 mm, column and shear wall 40 mm, beam 30 mm, slab 25 mm; "
                        "sump 45 mm (IS 3370). Site acceptance used on NSK: ±5 mm on the drawing value."),
    ("IS 13920 Cl. 7.4", "IS 13920 Cl. 7.4 — Special confining reinforcement in columns of ductile frames; spacing not more than 1/4 "
                         "of the least column dimension and not more than 100 mm in the confinement zone. On NSK, C-7 and C-8 under the "
                         "OT pendants use 10 dia ties @ 100 c/c over full height (SSB-STR-L3-201 R2, RFI-SSB-006)."),
    ("IS 456 Cl. 24.1", "IS 456 Cl. 24.1 — Slab thickness governed by span/depth and serviceability. NSK L3 OT floor slab is 200 mm "
                        "(SSB-STR-L3-211 R1, RFI-SSB-008); typical floors 175 mm."),
    ("IS 456 Cl. 11.3.1", "IS 456 Cl. 11.3.1 — Stripping time: vertical faces 16–24 h, slab soffit props 7 days, beam soffit props "
                          "14 days (OPC). NSK strips slab soffits at 7 days and beam soffits at 14 days."),
    ("IS 1893 Zone III", "IS 1893 (Part 1) — Nashik lies in seismic zone III (Z = 0.16). The super speciality block is an importance "
                         "factor 1.5 hospital building with ductile detailing to IS 13920."),
    ("IS 3370", "IS 3370 (Parts 1 & 2) — Water-retaining structures: minimum M30, crack width control, cover 45 mm on NSK sump "
                "(SSB-PLB-GF-401), crystalline admixture and hydro-test before backfill."),
    ("IS 14489 hot work", "IS 14489 — Hot work needs a valid permit, combustibles removed within 11 m, a dedicated trained fire "
                          "watcher during work and for 60 minutes after, and extinguishers at the work point. No fire watch → stop "
                          "hot work (applies to HWP-2031, lift core Zone C L4)."),
    ("BOCW Rules excavation", "BOCW Central Rules 1998 — excavations deeper than 1.5 m need shoring, sloping or benching designed by a "
                              "competent person, and re-inspection after heavy rain. NSK sump excavation EXC-2017 is suspended until "
                              "shoring and dewatering are in place (RFI-SSB-011)."),
]


def build_seed() -> dict:
    return {
        "project": PROJECT,
        "locations": locations(),
        "boq_items": boq_items(),
        "drawings": drawings(),
        "drawing_facts": drawing_facts(),
        "rfis": RFIS,
        "submittals": SUBMITTALS,
        "daily_logs": DPRS,
        "permits": PERMITS,
        "checklists": CHECKLISTS,
        "observations": OBSERVATIONS,
        "code_clauses": CODE_CLAUSES,
    }


if __name__ == "__main__":
    S = build_seed()
    out = Path(__file__).resolve().parent / "project_nsk.json"
    out.write_text(json.dumps(S, ensure_ascii=False, indent=1))
    print(f"wrote {out}: " + ", ".join(f"{k}={len(v)}" for k, v in S.items() if isinstance(v, list)))
