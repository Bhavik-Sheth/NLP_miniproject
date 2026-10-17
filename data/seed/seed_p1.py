"""
Demo project P1 seed — "Pithoragarh District Hospital & Staff Quarters, Uttarakhand".

Single source of truth for the demo project. build_db.py imports `build_seed()` and also dumps the
result to data/seed/project_p1.json (human-readable mirror; do not hand-edit the JSON).

Contract IDs from README.md (app + scenarios depend on these, do not change):
  P1, P1:C-5:L3, P1:C-6:L3, P1:B-4:L3, P1:ZoneB:L3, P1:Slab:L4,
  A-102@R3 (Superseded, 2026-07-20, C-5 spacing 200), A-102@R4 (For Construction, 2026-08-12, latest,
  C-5 spacing 180 ±10, C-6 180, cover 40 IS 456 Cl. 26.4), RFI-047 -> A-102@R4 (answered 2026-08-10),
  S-301@R2 (For Construction, slab thickness 150), HWP-0112 (hot_work, P1:ZoneB:L3, Active,
  fire-watch unsatisfied), pre-pour checklist QC-CON-CHK-001 for L4 slab with hold point NOT released.
"""
from __future__ import annotations

PROJECT = {
    "project_id": "P1",
    "name": "Pithoragarh District Hospital & Staff Quarters",
    "client": "Uttarakhand Health Infrastructure Development Agency",
    "location": "Pithoragarh, Uttarakhand",
    "contract_type": "Item Rate (CPWD)",
    "start_date": "2026-03-02",
}

# ----------------------------------------------------------------------------------------------
# Locations + spoken aliases (English, Hinglish romanised, Devanagari, ASR-style mangles)
# ----------------------------------------------------------------------------------------------
_LETTER = {
    "A": ["A", "ay", "ए"],
    "B": ["B", "bee", "बी"],
    "C": ["C", "see", "सी"],
    "D": ["D", "dee", "डी"],
    "E": ["E", "ee", "ई"],
}
_NUM = {
    1: ["1", "one", "ek", "वन", "एक"],
    2: ["2", "two", "do", "टू", "दो"],
    3: ["3", "three", "teen", "थ्री", "तीन"],
    4: ["4", "four", "char", "फोर", "चार"],
    5: ["5", "five", "paanch", "फाइव", "पांच"],
    6: ["6", "six", "chhe", "सिक्स", "छह"],
}


def _grid_aliases(letter: str, n: int) -> list[str]:
    L_en, L_rom, L_dev = _LETTER[letter]
    d, n_en, n_hi, n_dev_en, n_dev_hi = _NUM[n]
    a = [
        f"{L_en}-{d}", f"{L_en}{d}", f"{L_en} {d}", f"{L_en.lower()}{d}",
        f"{L_en} {n_en}", f"{L_rom} {n_en}", f"{L_en} {n_hi}", f"{L_rom} {n_hi}",
        f"{L_dev} {d}", f"{L_dev}-{d}", f"{L_dev} {n_dev_en}", f"{L_dev} {n_dev_hi}", f"{L_dev}-{n_dev_hi}",
        f"column {L_en}{d}", f"column line {L_en}-{d}", f"grid {L_en}-{d}", f"{L_en}-{d} column",
        f"कॉलम {L_dev} {d}",
    ]
    if letter == "C":  # classic ASR confusions for "C"
        a += [f"sea {n_en}", f"si {n_en}", f"she {n_en}", f"c{n_en}"]
    if letter == "B":
        a += [f"be {n_en}", f"v {n_en}"]
    if letter == "D":
        a += [f"the {n_en}", f"de {n_en}"]
    out, seen = [], set()
    for x in a:
        if x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out


_L3 = ["L3", "level 3", "level three", "third floor", "3rd floor", "teesra floor", "teesri manzil", "तीसरा फ्लोर", "लेवल 3"]


def locations() -> list[dict]:
    locs = []
    for letter in "ABCD":
        for n in range(1, 7):
            grid = f"{letter}-{n}"
            locs.append({
                "location_id": f"P1:{grid}:L3", "project_id": "P1", "grid": grid, "level": "L3",
                "zone": "ZoneA" if n <= 3 else "ZoneB",
                "aliases": _grid_aliases(letter, n) + [f"{grid} {lv}" for lv in ("L3", "level 3")],
            })
    locs += [
        {"location_id": "P1:ZoneB:L3", "project_id": "P1", "grid": None, "level": "L3", "zone": "ZoneB",
         "aliases": ["Zone B", "zone bee", "B zone", "zone B level 3", "zone B L3", "Zone-B", "zon B",
                     "ज़ोन बी", "जोन बी", "बी ज़ोन", "zone B teesra floor", "grid 4 to 6 level 3"]},
        {"location_id": "P1:Slab:L4", "project_id": "P1", "grid": None, "level": "L4", "zone": None,
         "aliases": ["L4 slab", "level 4 slab", "level four slab", "fourth floor slab", "4th floor slab",
                     "slab L4", "chautha slab", "chauthi manzil slab", "roof of level 3", "S-301 slab",
                     "लेवल 4 स्लैब", "चौथा स्लैब", "फोर्थ फ्लोर स्लैब", "L four slab", "el four slab"]},
        {"location_id": "P1:LiftPit:B1", "project_id": "P1", "grid": "LP-1", "level": "B1", "zone": "Core",
         "aliases": ["lift pit", "lift pit B1", "lift ka pit", "basement lift pit", "लिफ्ट पिट", "LP-1"]},
        {"location_id": "P1:STP:GL", "project_id": "P1", "grid": "STP", "level": "GL", "zone": "External",
         "aliases": ["STP", "STP pit", "sewage treatment plant", "S T P excavation", "एसटीपी", "STP ka khudai"]},
        {"location_id": "P1:E-1:L1", "project_id": "P1", "grid": "E-1", "level": "L1", "zone": "OPD",
         "aliases": _grid_aliases("E", 1) + ["OPD block", "outpatient block", "OPD column E-1", "Pithoragarh OPD"]},
        {"location_id": "P1:E-2:L1", "project_id": "P1", "grid": "E-2", "level": "L1", "zone": "Maternity",
         "aliases": _grid_aliases("E", 2) + ["maternity wing", "labour room block", "OPD column E-2"]},
        {"location_id": "P1:RW-1:GL", "project_id": "P1", "grid": "RW-1", "level": "GL", "zone": "Hillside",
         "aliases": ["retaining wall", "retaining wall one", "RW-1", "RW 1", "hillside retaining wall", "ambulance road wall"]},
        {"location_id": "P1:WaterTank:GL", "project_id": "P1", "grid": "WT-1", "level": "GL", "zone": "Services",
         "aliases": ["water tank", "overhead water tank", "WT-1", "WT 1", "hospital water tank"]},
    ]
    return locs


# ----------------------------------------------------------------------------------------------
# BOQ (CPWD DSR-style item codes; Pune 2026 market-adjusted rates, INR)
# ----------------------------------------------------------------------------------------------
_BOQ = [
    # item_code, description, unit, qty, rate, spec_ref
    ("2.6.1", "Earth work in excavation by mechanical means (hydraulic excavator) / manual means over areas (exceeding 30 cm depth, 1.5 m width and 10 sqm plan) incl. disposal up to 50 m lead and 1.5 m lift — all kinds of soil", "cum", 4850, 265, "CPWD Spec 2.6; IS 3764"),
    ("2.25", "Filling available excavated earth in trenches, plinth, sides of foundations in layers not exceeding 20 cm, consolidating each layer by ramming and watering, lead up to 50 m and lift up to 1.5 m", "cum", 1620, 210, "CPWD Spec 2.25"),
    ("4.1.8", "Providing and laying in position cement concrete of specified grade excluding shuttering — 1:4:8 (1 cement : 4 coarse sand : 8 graded stone aggregate 40 mm nominal size) — PCC below footings / raft", "cum", 185, 6450, "IS 456 Cl. 6; CPWD Spec 4.1"),
    ("4.1.3", "Providing and laying in position cement concrete 1:2:4 (1 cement : 2 coarse sand : 4 graded stone aggregate 20 mm nominal size) — levelling course / sunk slab filling", "cum", 64, 7550, "IS 456; CPWD Spec 4.1"),
    ("5.33.1", "Providing and laying in position machine batched and machine mixed design mix M25 grade cement concrete (RMC) for RCC work incl. pumping, admixtures per IS 9103 — slabs, beams, lintels, landings (all levels)", "cum", 2460, 8150, "IS 456; IS 10262; IS 4926; CPWD Spec 5.33"),
    ("5.33.2", "Providing and laying in position design mix M30 grade cement concrete (RMC) for RCC columns, shear walls and core walls incl. pumping and admixtures (all levels)", "cum", 1180, 8650, "IS 456; IS 10262; IS 4926; CPWD Spec 5.33"),
    ("5.33.3", "Providing and laying design mix M30 grade concrete for raft foundation incl. pumping, retarder and temperature control", "cum", 1420, 8400, "IS 456 Cl. 34; IS 10262"),
    ("5.22.6", "Steel reinforcement for RCC work including straightening, cutting, bending, placing in position and binding all complete above plinth level — Thermo-Mechanically Treated bars of grade Fe 500D or more", "kg", 612000, 92.5, "IS 1786:2008; IS 456 Cl. 26; CPWD Spec 5.22"),
    ("5.22A.6", "Steel reinforcement for RCC work — TMT Fe 500D — up to plinth level (raft, footings, pedestals, plinth beams)", "kg", 178000, 90.0, "IS 1786:2008; IS 2502; CPWD Spec 5.22"),
    ("5.9.1", "Centering and shuttering including strutting, propping etc. and removal of form for foundations, footings, bases of columns, mass concrete", "sqm", 2100, 410, "IS 14687; CPWD Spec 5.9"),
    ("5.9.3", "Centering and shuttering including strutting, propping etc. and removal of form for suspended floors, roofs, landings, balconies and access platform (plywood 12 mm, props at ≤1.2 m)", "sqm", 16800, 690, "IS 14687; IS 456 Cl. 11; CPWD Spec 5.9"),
    ("5.9.5", "Centering and shuttering for lintels, beams, plinth beams, girders, bressumers and cantilevers", "sqm", 9400, 720, "IS 14687; CPWD Spec 5.9"),
    ("5.9.6", "Centering and shuttering for columns, pillars, piers, abutments, posts and struts (steel / ply column boxes)", "sqm", 7300, 760, "IS 14687; CPWD Spec 5.9"),
    ("5.9.7", "Centering and shuttering for stairs (excluding landings) except spiral staircases", "sqm", 820, 840, "CPWD Spec 5.9"),
    ("5.3", "Extra for providing and mixing water proofing material in cement concrete work in doses by weight of cement as per manufacturer's specification (integral crystalline admixture — terrace, sunk slabs, lift pit)", "kg", 5200, 95, "IS 2645; CPWD Spec 5.3"),
    ("6.1.2", "Brick work with common burnt clay F.P.S. (non-modular) bricks of class designation 7.5 in superstructure above plinth level up to floor V level in cement mortar 1:6 (230 mm external walls)", "cum", 1450, 7350, "IS 1077; IS 2212; CPWD Spec 6.1"),
    ("6.13.2", "Half brick masonry with common burnt clay F.P.S. bricks of class 7.5 in superstructure above plinth level up to floor V level in cement mortar 1:4 (115 mm partitions) incl. hoop iron every 4th course", "sqm", 6200, 880, "IS 2212; CPWD Spec 6.13"),
    ("6.33.1", "Providing and laying autoclaved aerated cement (AAC) block masonry 200 mm thick with AAC blocks of density 551-650 kg/m³ in cement mortar 1:4 / thin-bed adhesive — internal walls, floors VI to XIII", "cum", 1880, 5950, "IS 2185 (Part 3); IS 6041"),
    ("13.1.1", "12 mm cement plaster of mix 1:6 (1 cement : 6 coarse sand) on fair side of brick/block walls (internal)", "sqm", 48500, 318, "IS 1661; CPWD Spec 13.1"),
    ("13.2.1", "15 mm cement plaster on the rough side of single or half brick wall of mix 1:6", "sqm", 9800, 352, "IS 1661; CPWD Spec 13.2"),
    ("13.16.1", "6 mm cement plaster of mix 1:3 (1 cement : 3 fine sand) to ceiling / RCC soffits", "sqm", 15600, 248, "IS 1661; CPWD Spec 13.16"),
    ("13.5.1", "20 mm thick two-coat external cement plaster 1:4 with waterproofing compound, finished with sponge, incl. chicken mesh at RCC–masonry junctions", "sqm", 14200, 468, "IS 1661; IS 2402"),
    ("11.41.2", "Providing and laying vitrified floor tiles 600x600 mm (Group BIa, IS 15622) in all colours and shades laid on 20 mm thick cement mortar 1:4, jointing with grey cement slurry and pigment", "sqm", 21400, 1285, "IS 15622; CPWD Spec 11.41"),
    ("22.1", "Providing and laying integral cement based waterproofing treatment incl. preparation of surface for terrace / sunken toilets (brick bat coba 120 mm avg., finished with 20 mm plaster and china mosaic)", "sqm", 3150, 1340, "IS 2645; CPWD Spec 22"),
    ("12.41.1", "Providing and fixing 1st class hard wood / steel door frame (pressed steel 1.25 mm, 105x60 mm) with hold fasts in cement concrete block 30x10x15 cm of 1:3:6", "m", 5400, 690, "IS 4351; CPWD Spec 9"),
    ("10.25.1", "Structural steel work in built-up sections (lift machine room beams, canopy frames) incl. cutting, hoisting, fixing, welding and one coat of red oxide primer — Fe 350", "kg", 14800, 118, "IS 800:2007; IS 2062; IS 816"),
]


def boq_items() -> list[dict]:
    out = []
    for i, (code, desc, unit, qty, rate, spec) in enumerate(_BOQ, 1):
        out.append({
            "boq_id": f"P1-BOQ-{code}", "project_id": "P1", "item_code": code, "description": desc,
            "unit": unit, "qty_tendered": float(qty), "rate": float(rate),
            "amount": round(qty * rate, 2), "spec_ref": spec, "template_id": "FMT-TND-005",
        })
    return out


# ----------------------------------------------------------------------------------------------
# Drawing register (revision chains) + atomic facts
# ----------------------------------------------------------------------------------------------
def drawings() -> list[dict]:
    D = []

    def add(num, rev, title, disc, status, issued, zone, level, latest, sup_by, note):
        D.append({"drawing_id": f"{num}@{rev}", "project_id": "P1", "drawing_number": num, "revision": rev,
                  "rev_ordinal": int(rev[1:]), "title": title, "discipline": disc, "status": status,
                  "issued_on": issued, "zone": zone, "level": level, "is_latest": latest,
                  "superseded_by": sup_by, "change_note": note})

    t = "Column Reinforcement Details — Level 3"
    add("A-102", "R1", t, "Structural", "Superseded", "2026-05-28", None, "L3", 0, "A-102@R2",
        "First issue for construction. Columns A-1..D-6: 8-16 dia main bars, 8 dia ties @ 200 c/c.")
    add("A-102", "R2", t, "Structural", "Superseded", "2026-06-25", None, "L3", 0, "A-102@R3",
        "Main bars in C and D line columns upgraded to 20 dia after load re-check (consultant memo SM-11).")
    add("A-102", "R3", t, "Structural", "Superseded", "2026-07-20", None, "L3", 0, "A-102@R4",
        "Lap zone relocated to mid-height for columns C-3, C-4 (RFI-041). Tie spacing unchanged at 200 c/c.")
    add("A-102", "R4", t, "Structural", "For Construction", "2026-08-12", None, "L3", 1, None,
        "Tie/stirrup spacing at C-5 and C-6 reduced from 200 to 180 c/c per RFI-047 (ductile detailing, "
        "IS 13920). All other details as R3.")

    t = "Level 4 Slab GA"
    add("S-301", "R1", t, "Structural", "Superseded", "2026-07-30", None, "L4", 0, "S-301@R2",
        "Slab 125 thk typical, M25.")
    add("S-301", "R2", t, "Structural", "For Construction", "2026-08-20", None, "L4", 1, None,
        "Slab thickness increased 125 → 150 mm over Zone B services corridor and typical bays (RFI-052).")

    t = "Level 4 Slab Reinforcement Layout"
    add("S-302", "R1", t, "Structural", "For Construction", "2026-08-22", None, "L4", 1, None,
        "Bottom mesh 10 dia @ 150 c/c both ways; top extra bars 10 dia @ 150 over supports.")

    t = "Level 3 Beam Layout & Reinforcement"
    add("S-201", "R1", t, "Structural", "Superseded", "2026-06-30", None, "L3", 0, "S-201@R2",
        "First issue.")
    add("S-201", "R2", t, "Structural", "For Construction", "2026-07-28", None, "L3", 1, None,
        "Beam depth at A-2/A-3 increased 450 → 600 for plumbing sleeve (RFI-044).")

    t = "Column Schedule — Level 3 & Level 4"
    add("A-103", "R1", t, "Structural", "For Construction", "2026-05-28", None, "L3", 1, None,
        "Column sizes and concrete grade schedule.")

    t = "Level 3 Floor Plan (Architectural)"
    add("A-101", "R1", t, "Architectural", "Superseded", "2026-04-18", None, "L3", 0, "A-101@R2",
        "First issue.")
    add("A-101", "R2", t, "Architectural", "For Construction", "2026-06-10", None, "L3", 1, None,
        "Zone B flat layout revised: kitchen–utility swap, door D3 widened to 1000 (RFI-038).")

    add("M-401", "R1", "Level 3 Plumbing & Sleeve Layout", "MEP", "For Construction", "2026-07-05",
        "ZoneB", "L3", 1, None, "Sleeve positions for soil/waste stacks in Zone B.")
    add("E-501", "R1", "Level 4 Slab Electrical Conduit Layout", "MEP", "For Approval", "2026-09-02",
        None, "L4", 0, None, "Issued for approval; conduit routing in L4 slab (RFI-050 open).")
    add("A-201", "R1", "OPD & Maternity Block — Structural GA", "Structural", "For Construction", "2026-08-26",
        "OPD", "L1", 1, None, "Pithoragarh hospital OPD and maternity block: M30 columns, 40 mm cover, Fe500D reinforcement.")
    add("C-401", "R1", "Ambulance Road Retaining Wall & Drain", "Civil", "Superseded", "2026-08-19",
        "Hillside", "GL", 0, "C-401@R2", "Initial toe-wall detail before geotechnical review.")
    add("C-401", "R2", "Ambulance Road Retaining Wall & Drain", "Civil", "For Construction", "2026-09-04",
        "Hillside", "GL", 1, None, "Wall base widened after geotechnical review; weep holes and filter media mandatory (RFI-060).")
    add("P-601", "R1", "Hospital Water Supply & Fire Tank Layout", "Public Health", "For Construction", "2026-09-01",
        "Services", "GL", 1, None, "Underground fire/water tank sleeves and pump-room connections for remote-site continuity.")
    return D


def drawing_facts() -> list[dict]:
    F = []

    def f(did, loc, el, mark, attr, num=None, text=None, unit=None, tol=None, ref=None):
        F.append({"drawing_id": did, "location_id": loc, "element": el, "element_mark": mark,
                  "attribute": attr, "value_num": num, "value_text": text, "unit": unit,
                  "tolerance": tol, "code_ref": ref})

    grids = [f"{l}-{n}" for l in "ABCD" for n in range(1, 7)]
    # --- A-102 column reinforcement, all four revisions ------------------------------------
    for rev in ("R1", "R2", "R3", "R4"):
        did = f"A-102@{rev}"
        for g in grids:
            loc = f"P1:{g}:L3"
            heavy = g[0] in "CD"
            spacing = 180 if (rev == "R4" and g in ("C-5", "C-6")) else 200
            dia = 16 if (rev == "R1" or not heavy) else 20
            bars = 12 if g in ("C-5", "C-6") and rev != "R1" else 8
            f(did, loc, "column", g, "rebar_spacing", spacing, None, "mm", 10, "IS 456 Cl. 26.5.3.2(c)")
            f(did, loc, "column", g, "rebar_dia", dia, None, "mm", 0, "IS 456 Cl. 26.5.3.1; IS 1786")
            f(did, loc, "column", g, "bar_count", bars, None, "nos", 0, "IS 456 Cl. 26.5.3.1(c)")
            f(did, loc, "column", g, "tie_dia", 8, None, "mm", 0, "IS 456 Cl. 26.5.3.2(c)")
            f(did, loc, "column", g, "cover", 40, None, "mm", 5, "IS 456 Cl. 26.4")
    # --- A-103 column schedule: size + grade ------------------------------------------------
    for g in grids:
        loc = f"P1:{g}:L3"
        size = "450x600" if g[0] in "CD" else "300x600"
        f("A-103@R1", loc, "column", g, "size", None, size, "mm", 5, "IS 456 Cl. 11 (formwork tolerance)")
        f("A-103@R1", loc, "column", g, "grade", 30, "M30", "MPa", 0, "IS 456 Table 5")
    # --- S-301 L4 slab GA -------------------------------------------------------------------
    f("S-301@R1", "P1:Slab:L4", "slab", "S4-TYP", "thickness", 125, None, "mm", 5, "IS 456 Cl. 24.1")
    f("S-301@R1", "P1:Slab:L4", "slab", "S4-TYP", "grade", 25, "M25", "MPa", 0, "IS 456 Table 5")
    f("S-301@R2", "P1:Slab:L4", "slab", "S4-TYP", "thickness", 150, None, "mm", 5, "IS 456 Cl. 24.1")
    f("S-301@R2", "P1:Slab:L4", "slab", "S4-TYP", "grade", 25, "M25", "MPa", 0, "IS 456 Table 5")
    f("S-301@R2", "P1:Slab:L4", "slab", "S4-TYP", "cover", 20, None, "mm", 5, "IS 456 Cl. 26.4.2.2")
    f("S-301@R2", "P1:Slab:L4", "slab", "S4-TYP", "level", 12.150, None, "m", 0.01, "Top of slab (TOS) +12.150")
    # --- S-302 L4 slab reinforcement -------------------------------------------------------
    f("S-302@R1", "P1:Slab:L4", "slab", "S4-TYP", "rebar_dia", 10, None, "mm", 0, "IS 456 Cl. 26.5.2.2")
    f("S-302@R1", "P1:Slab:L4", "slab", "S4-TYP", "rebar_spacing", 150, None, "mm", 10, "IS 456 Cl. 26.3.3(b)")
    # --- S-201 L3 beams (at locations not used for column scenarios) -----------------------
    for rev, depth in (("R1", 450), ("R2", 600)):
        did = f"S-201@{rev}"
        for loc, mark in (("P1:A-2:L3", "B-302"), ("P1:A-3:L3", "B-303")):
            f(did, loc, "beam", mark, "size", None, f"300x{depth}", "mm", 5, "IS 456 Cl. 11")
            f(did, loc, "beam", mark, "rebar_spacing", 150, None, "mm", 10, "IS 456 Cl. 26.5.1.5")
            f(did, loc, "beam", mark, "rebar_dia", 20, None, "mm", 0, "IS 456 Cl. 26.5.1")
            f(did, loc, "beam", mark, "bar_count", 4, None, "nos", 0, "IS 456 Cl. 26.5.1.1")
            f(did, loc, "beam", mark, "cover", 25, None, "mm", 5, "IS 456 Cl. 26.4.2")
    for loc, mark in (("P1:D-2:L3", "B-312"), ("P1:D-4:L3", "B-314")):
        f("S-201@R2", loc, "beam", mark, "size", None, "300x450", "mm", 5, "IS 456 Cl. 11")
        f("S-201@R2", loc, "beam", mark, "rebar_spacing", 125, None, "mm", 10, "IS 456 Cl. 26.5.1.5")
        f("S-201@R2", loc, "beam", mark, "cover", 25, None, "mm", 5, "IS 456 Cl. 26.4.2")
    # --- M-401 sleeves in Zone B -----------------------------------------------------------
    f("M-401@R1", "P1:ZoneB:L3", "pipe", "SL-B3-01", "size", 150, None, "mm", 0, "IS 1742 (soil stack sleeve)")
    f("M-401@R1", "P1:ZoneB:L3", "pipe", "SL-B3-02", "size", 100, None, "mm", 0, "IS 1742 (waste stack sleeve)")
    # --- Pithoragarh hospital block ---------------------------------------------------------
    for loc, mark in (("P1:E-1:L1", "E-1"), ("P1:E-2:L1", "E-2")):
        f("A-201@R1", loc, "column", mark, "rebar_spacing", 150, None, "mm", 10, "IS 456 Cl. 26.5.3.2(c)")
        f("A-201@R1", loc, "column", mark, "rebar_dia", 20, None, "mm", 0, "IS 456 Cl. 26.5.3.1; IS 1786")
        f("A-201@R1", loc, "column", mark, "cover", 40, None, "mm", 5, "IS 456 Cl. 26.4")
        f("A-201@R1", loc, "column", mark, "grade", 30, "M30", "MPa", 0, "IS 456 Table 5")
    f("C-401@R1", "P1:RW-1:GL", "wall", "RW-1", "thickness", 300, None, "mm", 10, "IS 456 Cl. 11")
    f("C-401@R2", "P1:RW-1:GL", "wall", "RW-1", "thickness", 350, None, "mm", 10, "IS 456 Cl. 11")
    f("C-401@R2", "P1:RW-1:GL", "wall", "RW-1", "cover", 50, None, "mm", 5, "IS 456 Cl. 26.4")
    f("P-601@R1", "P1:WaterTank:GL", "tank", "WT-1", "thickness", 200, None, "mm", 5, "IS 3370")
    return F


# ----------------------------------------------------------------------------------------------
# RFIs, submittals, DPRs, permits, checklists
# ----------------------------------------------------------------------------------------------
RFIS = [
    {"rfi_id": "RFI-038", "subject": "Zone B door D3 width vs furniture layout", "location_id": "P1:ZoneB:L3",
     "drawing_ref": "A-101", "spec_ref": "NBC 2016 Part 3", "status": "Closed",
     "question": "Door D3 shown 900 mm on A-101 R1 but kitchen–utility layout needs 1000 mm clear. Confirm.",
     "response": "Revise D3 to 1000 mm; revised A-101 R2 issued.", "raised_on": "2026-05-20",
     "answered_on": "2026-06-06", "impact": "Revision issued: A-101 R2", "resulting_drawing_id": "A-101@R2"},
    {"rfi_id": "RFI-041", "subject": "Lap location for columns C-3 and C-4", "location_id": "P1:C-3:L3",
     "drawing_ref": "A-102", "spec_ref": "IS 456 Cl. 26.2.5; IS 13920 Cl. 7.2", "status": "Closed",
     "question": "A-102 R2 shows laps at floor level for C-3/C-4. IS 13920 requires laps in the middle half of the column. Please confirm.",
     "response": "Laps to be provided in the central half of clear height only. A-102 R3 issued.",
     "raised_on": "2026-07-08", "answered_on": "2026-07-18", "impact": "Revision issued: A-102 R3",
     "resulting_drawing_id": "A-102@R3"},
    {"rfi_id": "RFI-044", "subject": "Beam B-302/B-303 depth clash with plumbing sleeve", "location_id": "P1:A-2:L3",
     "drawing_ref": "S-201", "spec_ref": "IS 456 Cl. 23", "status": "Closed",
     "question": "150 mm soil stack sleeve passes through B-302 at 450 deep — insufficient clear depth. Advise.",
     "response": "Increase beam depth to 600 at A-2/A-3; sleeve through web at mid-depth. S-201 R2 issued.",
     "raised_on": "2026-07-14", "answered_on": "2026-07-26", "impact": "Revision issued: S-201 R2",
     "resulting_drawing_id": "S-201@R2"},
    {"rfi_id": "RFI-047", "subject": "Column C-5 stirrup spacing clarification", "location_id": "P1:C-5:L3",
     "drawing_ref": "A-102", "spec_ref": "IS 456 Cl. 26.5.3.2; IS 13920 Cl. 7.4", "status": "Answered",
     "question": "A-102 R3 shows ties at 200 c/c for C-5 (12 bars, 20 dia). With the heavier section, confirm tie spacing in the confinement zone and elsewhere — site measuring ~180 as per bar bender's BBS.",
     "response": "Adopt 180 c/c ties for C-5 and C-6 over full height (ductile detailing). Revised drawing A-102 R4 issued 12-Aug-2026.",
     "raised_on": "2026-08-02", "answered_on": "2026-08-10", "impact": "Revision issued: A-102 R4",
     "resulting_drawing_id": "A-102@R4"},
    {"rfi_id": "RFI-049", "subject": "Plumbing sleeve clash with beam at Zone B", "location_id": "P1:ZoneB:L3",
     "drawing_ref": "M-401", "spec_ref": None, "status": "Open",
     "question": "Sleeve SL-B3-02 (100 dia) on M-401 R1 falls 60 mm from beam B-314 face. Can it shift 150 mm towards the shaft?",
     "response": None, "raised_on": "2026-09-03", "answered_on": None, "impact": "Pending — may affect M-401",
     "resulting_drawing_id": None},
    {"rfi_id": "RFI-050", "subject": "Electrical conduit density in L4 slab near core", "location_id": "P1:Slab:L4",
     "drawing_ref": "E-501", "spec_ref": "IS 456 Cl. 11.5", "status": "Open",
     "question": "E-501 (For Approval) shows 6 conduits of 25 dia crossing within 300 mm near the core — exceeds 1/3 slab depth zone. Confirm reroute before pour.",
     "response": None, "raised_on": "2026-09-04", "answered_on": None, "impact": "Pending — L4 pour dependency",
     "resulting_drawing_id": None},
    {"rfi_id": "RFI-052", "subject": "L4 slab thickness — 125 vs 150 over services corridor", "location_id": "P1:Slab:L4",
     "drawing_ref": "S-301", "spec_ref": "IS 456 Cl. 24.1", "status": "Answered",
     "question": "S-301 R1 shows 125 mm slab but conduit + sleeve density needs deeper section. Confirm thickness.",
     "response": "Slab thickness revised to 150 mm throughout L4. S-301 R2 issued 20-Aug-2026.",
     "raised_on": "2026-08-11", "answered_on": "2026-08-18", "impact": "Revision issued: S-301 R2",
     "resulting_drawing_id": "S-301@R2"},
    {"rfi_id": "RFI-053", "subject": "Cover block type for columns", "location_id": "P1:C-4:L3",
     "drawing_ref": "A-102", "spec_ref": "IS 456 Cl. 26.4; CPWD Spec 5.22", "status": "Answered",
     "question": "Contractor proposes PVC cover blocks for columns. Acceptable?",
     "response": "No. Use concrete / mortar cover blocks of M30-equivalent strength, 40 mm for columns. No drawing change.",
     "raised_on": "2026-08-20", "answered_on": "2026-08-23", "impact": "No revision; site instruction SI-019",
     "resulting_drawing_id": None},
    {"rfi_id": "RFI-055", "subject": "Staircase waist slab thickness at mid-landing L3–L4", "location_id": "P1:D-6:L3",
     "drawing_ref": "S-201", "spec_ref": "IS 456 Cl. 33", "status": "Open",
     "question": "Stair waist slab not dimensioned on S-201 R2. Confirm 175 mm?",
     "response": None, "raised_on": "2026-09-07", "answered_on": None, "impact": "Pending",
     "resulting_drawing_id": None},
    {"rfi_id": "RFI-056", "subject": "Chajja projection over Zone B windows", "location_id": "P1:ZoneB:L3",
     "drawing_ref": "A-101", "spec_ref": None, "status": "Closed",
     "question": "A-101 R2 shows 600 mm chajja; elevation shows 450 mm. Which governs?",
     "response": "600 mm per A-101 R2 governs; elevation to be corrected in next issue.",
     "raised_on": "2026-08-25", "answered_on": "2026-08-28", "impact": "No revision (elevation typo)",
     "resulting_drawing_id": None},
]

# Remote-site-specific design and access constraints. These are synthetic demo records,
# not a substitute for the consultant's issued construction documents.
RFIS += [
    {"rfi_id": "RFI-060", "subject": "Ambulance road retaining wall base width and drainage", "location_id": "P1:RW-1:GL",
     "drawing_ref": "C-401", "spec_ref": "IS 14458; IS 456", "status": "Answered",
     "question": "The hillside cut exposed loose strata at RW-1. Confirm whether the 300 mm wall detail can proceed.",
     "response": "No. Use C-401 R2: 350 mm stem, revised base detail, filter media and weep holes before backfill.",
     "raised_on": "2026-08-29", "answered_on": "2026-09-03", "impact": "Revision issued: C-401 R2",
     "resulting_drawing_id": "C-401@R2"},
    {"rfi_id": "RFI-061", "subject": "OPD block monsoon concrete-pour access", "location_id": "P1:E-1:L1",
     "drawing_ref": "A-201", "spec_ref": "IS 456 Cl. 13", "status": "Open",
     "question": "Confirm the covered pump staging route during the monsoon diversion period.",
     "response": None, "raised_on": "2026-09-08", "answered_on": None,
     "impact": "Awaiting site-engineer route approval", "resulting_drawing_id": None},
]

SUBMITTALS = [
    {"submittal_id": "SUB-001", "type": "Material", "material": "TMT bars Fe 500D (8–25 dia) — primary producer",
     "spec_section": "IS 1786:2008; CPWD Spec 5.22", "status": "Approved",
     "reviewer_comments": "Approved. Each lot to be accompanied by MTC; 1 tensile + bend test per 40 t lot.",
     "submitted_on": "2026-03-20", "reviewed_on": "2026-03-27", "template_hint": "QC-STL-REG-001"},
    {"submittal_id": "SUB-002", "type": "Material", "material": "RMC design mix M30 (columns) — mix design report",
     "spec_section": "IS 10262:2019; IS 456 Cl. 9", "status": "Approved as Noted",
     "reviewer_comments": "w/c ratio to be capped at 0.42; slump 100±25 at site; trial cubes 7/28 day to be witnessed.",
     "submitted_on": "2026-04-02", "reviewed_on": "2026-04-12", "template_hint": "QC-CON-FRM-001"},
    {"submittal_id": "SUB-003", "type": "Shop Drawing", "material": "Column formwork (steel/ply boxes) shop drawing L3–L6",
     "spec_section": "IS 14687; IS 456 Cl. 11", "status": "Approved",
     "reviewer_comments": "Approved. Tie rod spacing 600 c/c max; plumb check at 3 points.",
     "submitted_on": "2026-06-18", "reviewed_on": "2026-06-24", "template_hint": "PMC-DSN-LOG-002"},
    {"submittal_id": "SUB-004", "type": "Method Statement", "material": "Method statement — L4 slab pour (pump, sequence, construction joints)",
     "spec_section": "IS 456 Cl. 13, 14", "status": "Under Review",
     "reviewer_comments": "Pending: construction joint location over Zone B corridor and curing plan.",
     "submitted_on": "2026-09-06", "reviewed_on": None, "template_hint": "QC-CON-FRM-002"},
    {"submittal_id": "SUB-005", "type": "MTC", "material": "OPC 53 grade cement — MTC batch 0826/PNE",
     "spec_section": "IS 269:2015", "status": "Approved",
     "reviewer_comments": "MTC complies; site setting-time test OK.", "submitted_on": "2026-08-27",
     "reviewed_on": "2026-08-29", "template_hint": "QC-CEM-REG-001"},
    {"submittal_id": "SUB-006", "type": "Material", "material": "PVC cover blocks 40 mm for columns",
     "spec_section": "IS 456 Cl. 26.4", "status": "Rejected",
     "reviewer_comments": "Rejected — use concrete cover blocks (see RFI-053 / SI-019).",
     "submitted_on": "2026-08-18", "reviewed_on": "2026-08-23", "template_hint": None},
    {"submittal_id": "SUB-007", "type": "Material", "material": "AAC blocks 600x200x200, density 551–650",
     "spec_section": "IS 2185 (Part 3)", "status": "Approved",
     "reviewer_comments": "Approved; compressive strength ≥ 3.5 N/mm² per lot.", "submitted_on": "2026-08-05",
     "reviewed_on": "2026-08-11", "template_hint": "QC-MAS-REG-001"},
    {"submittal_id": "SUB-008", "type": "Material", "material": "Crystalline waterproofing admixture for lift pit & sunk slabs",
     "spec_section": "IS 2645; CPWD Spec 22", "status": "Under Review",
     "reviewer_comments": "Awaiting third-party permeability test (DIN 1048).", "submitted_on": "2026-09-01",
     "reviewed_on": None, "template_hint": None},
]

DPRS = [
    {"log_date": "2026-09-05", "weather": "Light rain morning (6 mm), cloudy afternoon, 24–29 °C",
     "manpower": {"mason": 14, "bar_bender": 10, "carpenter": 12, "helper": 26, "welder": 2, "electrician": 3, "plumber": 2, "supervisor": 3},
     "work_done": "L3 columns C-1 to C-4 reinforcement fixing completed; C-5/C-6 cages as per A-102 R4 (ties 180 c/c) started. L4 slab shuttering Zone A 60% complete. Blockwork L7 Zone A.",
     "materials": {"TMT Fe500D received (t)": 18.4, "OPC 53 (bags)": 400, "AAC blocks (cum)": 22},
     "equipment": {"tower crane TC-1": "working", "concrete pump": "standby", "bar bending machine": 2},
     "safety": "Nil. Toolbox talk: working near slab edges in rain."},
    {"log_date": "2026-09-06", "weather": "Clear, 23–30 °C",
     "manpower": {"mason": 12, "bar_bender": 12, "carpenter": 14, "helper": 24, "welder": 2, "electrician": 4, "plumber": 2, "supervisor": 3},
     "work_done": "C-5/C-6 cage completed (12-20 dia, ties 180 c/c). L4 slab shuttering Zone B started; props at 1.2 m. Conduit laying L4 Zone A on hold pending RFI-050.",
     "materials": {"binding wire (kg)": 120, "plywood 12 mm (sheets)": 60},
     "equipment": {"tower crane TC-1": "working", "hoist": "working"},
     "safety": "Near miss: unsecured ply sheet at L4 edge (wind). Edge protection re-fixed."},
    {"log_date": "2026-09-07", "weather": "Cloudy, drizzle 14:00–15:00",
     "manpower": {"mason": 15, "bar_bender": 10, "carpenter": 16, "helper": 28, "welder": 3, "electrician": 4, "plumber": 3, "supervisor": 3},
     "work_done": "L3 column pour C-1..C-4 (M30, 14.2 cum), cubes cast (6 nos). L4 slab bottom mesh Zone A (S-302 R1). Structural steel lift machine-room brackets fabrication started.",
     "materials": {"RMC M30 (cum)": 14.2, "cover blocks 40 mm (nos)": 600},
     "equipment": {"concrete pump": "working 4 h", "needle vibrators": 3},
     "safety": "Nil. PPE audit: 2 workers without harness at L4 edge — stopped and briefed."},
    {"log_date": "2026-09-08", "weather": "Clear, 22–31 °C",
     "manpower": {"mason": 13, "bar_bender": 14, "carpenter": 14, "helper": 25, "welder": 3, "electrician": 5, "plumber": 3, "supervisor": 4},
     "work_done": "L3 column pour C-5, C-6 (M30, 7.8 cum). L4 slab shuttering Zone B complete; bottom mesh Zone B 40%. Hot work (welding) for MR brackets at Zone B L3 under HWP-0109 (closed 17:30).",
     "materials": {"RMC M30 (cum)": 7.8, "welding rods E7018 (kg)": 25},
     "equipment": {"welding sets": 2, "concrete pump": "working 3 h"},
     "safety": "Nil. Fire extinguishers (2 x 9 kg DCP) checked at Zone B."},
    {"log_date": "2026-09-09", "weather": "Partly cloudy, 23–30 °C",
     "manpower": {"mason": 12, "bar_bender": 16, "carpenter": 10, "helper": 27, "welder": 3, "electrician": 5, "plumber": 3, "supervisor": 4},
     "work_done": "L4 slab reinforcement Zone B top bars; cover blocks being replaced (PVC removed per SI-019). Pre-pour inspection L4 slab started — HOLD raised (cover shortfall at 3 locations, RFI-050 open). L4 pour planned 11-Sep subject to hold-point release.",
     "materials": {"TMT Fe500D received (t)": 12.0, "concrete cover blocks 20 mm (nos)": 1500},
     "equipment": {"tower crane TC-1": "working", "bar bending machine": 2},
     "safety": "Housekeeping observation at Zone B: welding cables across walkway."},
]

DPRS += [
    {"log_date": "2026-09-10", "weather": "Intermittent hill rain, low cloud, 16–21 °C",
     "manpower": {"mason": 11, "bar_bender": 8, "carpenter": 9, "helper": 21, "operator": 2, "supervisor": 3},
     "work_done": "OPD columns E-1/E-2 reinforcement checked to A-201 R1. Ambulance-road retaining wall excavation stopped after loose strata was seen; RFI-060 revision briefed.",
     "materials": {"TMT Fe500D received (t)": 8.6, "concrete cover blocks 40 mm (nos)": 420, "filter media (cum)": 0},
     "equipment": {"backhoe": "standby — excavation suspended", "concrete pump": "access route under review"},
     "safety": "Hillside exclusion zone maintained; no work below unsupported cut face."},
    {"log_date": "2026-09-11", "weather": "Overcast, rain after 15:00, 15–20 °C",
     "manpower": {"mason": 10, "bar_bender": 7, "carpenter": 8, "helper": 19, "operator": 2, "supervisor": 3},
     "work_done": "C-401 R2 retaining-wall revision issued to the crew. OPD column E-1 ties measured at 150 c/c; pre-pour materials staged under cover.",
     "materials": {"TMT Fe500D (t)": 3.2, "drainage filter aggregate (cum)": 12, "geotextile (sqm)": 180},
     "equipment": {"pickup": "working", "needle vibrator": 2},
     "safety": "Morning toolbox talk: rain, slope stability and ambulance access segregation."},
]

PERMITS = [
    {"permit_id": "HWP-0112", "permit_type": "hot_work", "location_id": "P1:ZoneB:L3",
     "valid_from": "2026-09-10T08:00", "valid_to": "2026-09-10T18:00", "status": "Active",
     "issued_by": "R. Kulkarni (HSE Manager)", "template_pref": ["QC-HSE-PRM-002", "PMC-SAF-PMT-001"],
     "unsatisfied_keywords": ["fire watch", "fire watcher", "fire-watch"]},
    {"permit_id": "WAH-0087", "permit_type": "height", "location_id": "P1:D-6:L3",
     "valid_from": "2026-09-10T08:00", "valid_to": "2026-09-10T18:00", "status": "Active",
     "issued_by": "R. Kulkarni (HSE Manager)", "template_pref": ["QC-HSE-PRM-001"],
     "unsatisfied_keywords": []},
    {"permit_id": "CSE-0021", "permit_type": "confined_space", "location_id": "P1:LiftPit:B1",
     "valid_from": "2026-09-04T09:00", "valid_to": "2026-09-04T17:00", "status": "Closed",
     "issued_by": "R. Kulkarni (HSE Manager)", "template_pref": ["QC-HSE-PRM-003"],
     "unsatisfied_keywords": []},
    {"permit_id": "EXC-0034", "permit_type": "excavation", "location_id": "P1:STP:GL",
     "valid_from": "2026-09-08T08:00", "valid_to": "2026-09-12T18:00", "status": "Suspended",
     "issued_by": "S. Deshmukh (Site In-charge)", "template_pref": ["QC-HSE-PRM-005"],
     "unsatisfied_keywords": ["shoring"]},
]

PERMITS += [
    {"permit_id": "EXC-0041", "permit_type": "excavation", "location_id": "P1:RW-1:GL",
     "valid_from": "2026-09-10T08:00", "valid_to": "2026-09-12T18:00", "status": "Suspended",
     "issued_by": "N. Rawat (HSE Officer)", "template_pref": ["QC-HSE-PRM-005"],
     "unsatisfied_keywords": ["shoring", "sloping", "benching"]},
]

# Pre-pour checklist instance for L4 slab: hold point NOT released.
CHECKLISTS = [
    {"instance_id": "CL-PP-L4-001", "template_id": "QC-CON-CHK-001", "location_id": "P1:Slab:L4",
     "element": "slab", "element_mark": "S4-TYP", "drawing_id": "S-301@R2",
     "planned_activity": "concrete_pour", "planned_for": "2026-09-11",
     "status": "Hold", "hold_point_released": 0, "inspected_by": "A. Shaikh (QC Engineer)",
     "inspected_on": "2026-09-09",
     "notes": "HOLD — cover shortfall (15 mm) at 3 locations in Zone B; RFI-050 conduit reroute open; design consultant release pending.",
     # item statuses by keyword (first match wins); default OK
     "item_overrides": [
         {"match": ["cover"], "status": "HOLD", "remarks": "Cover 15 mm measured at 3 locations Zone B (req. 20±5). PVC blocks being replaced."},
         {"match": ["conduit", "embedded", "sleeve"], "status": "HOLD", "remarks": "RFI-050 open — conduit density near core."},
         {"match": ["hold point"], "status": "HOLD", "remarks": "ITP hold point not signed off."},
         {"match": ["consultant"], "status": "pending", "remarks": "Awaiting consultant release."},
         {"match": ["verdict"], "status": "HOLD — CORRECTIONS REQUIRED", "remarks": None},
         {"match": ["cube", "slump", "curing", "pump", "vibrator", "weather", "lighting", "concrete delivery", "batch"], "status": "pending", "remarks": "To be verified on pour day."},
     ]},
    {"instance_id": "CL-PP-L3-C56-001", "template_id": "QC-CON-CHK-001", "location_id": "P1:C-5:L3",
     "element": "column", "element_mark": "C-5", "drawing_id": "A-102@R4",
     "planned_activity": "concrete_pour", "planned_for": "2026-09-08",
     "status": "Released", "hold_point_released": 1, "inspected_by": "A. Shaikh (QC Engineer)",
     "inspected_on": "2026-09-08", "notes": "Released for pour 08-Sep 10:40. Ties 180 c/c verified vs A-102 R4.",
     "item_overrides": []},
]

# A couple of historical observations (already logged before the demo) — always verified latest drawing.
OBSERVATIONS = [
    {"observation_id": "OBS-000101", "project_id": "P1", "session_id": None,
     "spoken_text": "C-4 column pe cover 40 mm check kiya, concrete blocks lag gaye hain.",
     "structured_summary": "Column C-4 L3: cover 40 mm measured; concrete cover blocks installed (per RFI-053).",
     "location_id": "P1:C-4:L3", "element": "column", "attribute": "cover", "value_claimed": 40, "unit": "mm",
     "drawing_id": "A-102@R4", "revision_claimed": "R4", "contradiction_flag": 0, "contradiction_kinds": "[]",
     "clarification_asked": None, "final_decision": "log_observation", "linked_rfi_id": "RFI-053",
     "linked_template_id": "QC-SPW-REG-004", "created_at": "2026-09-07T11:12:00+05:30"},
    {"observation_id": "OBS-000102", "project_id": "P1", "session_id": None,
     "spoken_text": "C-6 ke ties 180 pe hain, R4 ke hisaab se theek hai.",
     "structured_summary": "Column C-6 L3: tie spacing 180 mm matches A-102 R4.",
     "location_id": "P1:C-6:L3", "element": "column", "attribute": "rebar_spacing", "value_claimed": 180, "unit": "mm",
     "drawing_id": "A-102@R4", "revision_claimed": "R4", "contradiction_flag": 0, "contradiction_kinds": "[]",
     "clarification_asked": None, "final_decision": "log_observation", "linked_rfi_id": "RFI-047",
     "linked_template_id": "QC-SPW-REG-004", "created_at": "2026-09-08T09:40:00+05:30"},
]

OBSERVATIONS += [
    {"observation_id": "OBS-000103", "project_id": "P1", "session_id": None,
     "spoken_text": "OPD E-1 column ties measured 150 mm centre to centre before the rain.",
     "structured_summary": "Pithoragarh OPD Block, Column E-1 L1: tie spacing 150 mm verified against A-201 R1.",
     "location_id": "P1:E-1:L1", "element": "column", "attribute": "rebar_spacing", "value_claimed": 150, "unit": "mm",
     "drawing_id": "A-201@R1", "revision_claimed": "R1", "contradiction_flag": 0, "contradiction_kinds": "[]",
     "clarification_asked": None, "final_decision": "log_observation", "linked_rfi_id": None,
     "linked_template_id": "QC-SPW-REG-004", "created_at": "2026-09-11T11:20:00+05:30"},
    {"observation_id": "OBS-000104", "project_id": "P1", "session_id": None,
     "spoken_text": "Ambulance road retaining wall work stopped pending the revised geotechnical detail.",
     "structured_summary": "RW-1 retaining wall: excavation remains suspended; C-401 R2 and RFI-060 require drainage detail before restart.",
     "location_id": "P1:RW-1:GL", "element": "wall", "attribute": "thickness", "value_claimed": 350, "unit": "mm",
     "drawing_id": "C-401@R2", "revision_claimed": "R2", "contradiction_flag": 0, "contradiction_kinds": "[]",
     "clarification_asked": None, "final_decision": "stop_work", "linked_rfi_id": "RFI-060",
     "linked_template_id": "QC-SPW-REG-004", "created_at": "2026-09-11T16:05:00+05:30"},
]

# Short paraphrased code-clause notes for retrieval (not verbatim code text).
CODE_CLAUSES = [
    ("IS 456 Cl. 26.4", "IS 456 Cl. 26.4 — Nominal cover to reinforcement: depends on exposure condition (Table 16). Columns: not less than 40 mm for longitudinal bars (or bar dia, whichever greater). Actual cover should not deviate from nominal by more than +10 / 0 mm. Site pre-pour tolerance used on P1: column 40 ±5 mm, beam 25 ±5, slab 20 ±5."),
    ("IS 456 Cl. 26.5.3.2", "IS 456 Cl. 26.5.3.2 — Transverse reinforcement (ties/links) in columns: pitch not more than least lateral dimension, 16 × smallest longitudinal bar dia, or 300 mm. Tie dia not less than 1/4 of largest longitudinal bar and not less than 6 mm. Project P1 uses 8 mm ties; C-5/C-6 at 180 c/c per A-102 R4."),
    ("IS 456 Cl. 26.3.3", "IS 456 Cl. 26.3.3 — Maximum distance between bars in tension (slabs): main bars not more than 3d or 300 mm; distribution bars not more than 5d or 450 mm. Minimum clear spacing: bar dia or 5 mm more than nominal max aggregate size."),
    ("IS 456 Cl. 24.1", "IS 456 Cl. 24.1 — Slab thickness governed by span/depth ratios (Cl. 23.2) for deflection control; minimum practical 125 mm for residential floors. L4 slab on P1 is 150 mm per S-301 R2 (RFI-052)."),
    ("IS 456 Cl. 11", "IS 456 Cl. 11 — Formwork: shall be rigid, tight and conform to shape, lines and dimensions; tolerances on cross-sectional dimensions of columns/beams typically +12 / −6 mm; slab thickness per specification."),
    ("IS 13920 Cl. 7.4", "IS 13920 Cl. 7.4 — Special confining reinforcement in columns of ductile frames over length lo from each joint face; spacing not exceeding 1/4 of minimum member dimension and not more than 100 mm in confinement zone."),
    ("IS 14489", "IS 14489 — Occupational health & safety in construction: hot work requires a valid permit, removal/protection of combustibles, a dedicated trained fire watcher during and after the work, and fire extinguishers at the work location. No fire watch → stop hot work."),
    ("BOCW Act 1996", "BOCW Act 1996 & Central Rules 1998 — building workers' safety: permits for work at height, confined space, excavation; safety nets/harness above 2 m; shoring for excavations deeper than 1.5 m."),
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
