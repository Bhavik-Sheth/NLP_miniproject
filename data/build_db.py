#!/usr/bin/env python3
"""
Build data/site.db from scratch (drop + rebuild; idempotent; offline once data/raw/ is cached).

  python3 data/build_db.py            # build + sanity checks
  python3 data/build_db.py --quiet

Inputs:
  data/schema.sql                      shared contract
  data/raw/*.json + data/raw/html/*    Firecrawl cache written by data/scraper/scrape_infralens.py
  data/seed/project_*.json             demo project records (P1 is regenerated from seed_p1.py)
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sqlite3
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent
RAW = DATA / "raw"
DB = DATA / "site.db"
sys.path.insert(0, str(DATA / "scraper"))
sys.path.insert(0, str(DATA / "seed"))

from parse_infralens import (decode_rsc, extract_codes, extract_families, extract_template,  # noqa: E402
                             norm_type, render_template_text, template_fields, trim_markdown)
import seed_p1  # noqa: E402

LIBS = {
    "formats": "https://infralens.in/formats",
    "qaqc": "https://infralens.in/qaqc",
    "pmc": "https://infralens.in/pmc",
}
EXPECTED = {"formats": 100, "qaqc": 300, "pmc": 150}
CHUNK = 800

# Curated hold-point overrides for quality-bar templates (the site marks every row with a HOLD status
# option but does not flag which rows are formal hold points). Matched against item label.
HOLD_OVERRIDES = {
    "QC-CON-CHK-001": [r"bar spacing", r"concrete cover", r"stirrup spacing", r"cover blocks", r"hold point",
                       r"bar diameter and grade", r"embedded|conduit|sleeve"],
    "QC-CON-CHK-005": [r"spacing", r"cover", r"diameter|grade", r"lap", r"hold"],
    "QC-STL-CHK-003": [r"spacing", r"cover", r"diameter|grade", r"lap", r"hold"],
}
# Permit templates: rows that are always mandatory + blocking regardless of wording
PERMIT_BLOCKING = re.compile(r"fire[\s-]?watch|gas test|LEL|oxygen|isolation|lock[\s-]?out|LOTO|harness|anchor|"
                             r"shoring|benching|sloping|standby|attendant|rescue|extinguisher", re.I)


def log(*a):
    if not ARGS.quiet:
        print(*a)


def read_raw(name: str):
    p = RAW / f"{name}.json"
    h = RAW / "html" / f"{name}.html.gz"
    if not p.exists() or not h.exists():
        return None, None
    rec = json.loads(p.read_text())
    with gzip.open(h, "rt", encoding="utf-8") as fh:
        html = fh.read()
    return rec, html


def chunks_of(text: str, size: int = CHUNK) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    paras = [p for p in re.split(r"\n\s*\n|\n(?=[-*#|] )|\n(?=[A-Z]\d{1,2} )", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        p = p.strip()
        while len(p) > size:  # hard split very long paragraphs on sentence/space boundary
            cut = max(p.rfind(". ", 0, size), p.rfind("\n", 0, size), p.rfind(" ", 0, size))
            cut = cut if cut > size * 0.5 else size
            if cur:
                out.append(cur)
                cur = ""
            out.append(p[:cut + 1].strip())
            p = p[cut + 1:].strip()
        if len(cur) + len(p) + 1 > size and cur:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur}\n{p}" if cur else p
    if cur:
        out.append(cur)
    return out


# ================================================================================================
# 1. Templates
# ================================================================================================
def load_templates(con: sqlite3.Connection) -> dict:
    stats = {}
    for lib, url in LIBS.items():
        rec, html = read_raw(f"{lib}__index")
        con.execute("INSERT INTO template_sources VALUES (?,?,?)", (lib, url, rec and rec.get("fetched_at")))
        if not rec:
            log(f"[{lib}] index not cached — run data/scraper/scrape_infralens.py")
            stats[lib] = {"index": 0, "pages": 0, "fields": 0, "families": {}}
            continue
        fams = extract_families(decode_rsc(html))
        st = {"index": 0, "pages": 0, "fields": 0, "families": {}, "no_fields": [], "via": {}}
        for fam in fams:
            fam_name = fam.get("family_name") or fam["family_id"]
            for it in fam["templates"]:
                tid = it["template_id"]
                fam_code = tid.split("-")[1]  # TND, CON, SAF, DSN/DES ...
                page_url = f"https://infralens.in/{lib}/{fam['family_id']}/{it['slug']}"
                name = f"{lib}__{fam['family_id']}__{it['slug']}"
                prec, phtml = read_raw(name)
                tpl = extract_template(decode_rsc(phtml), tid) if phtml else None
                if tpl is None and phtml:  # page id may differ from index id (e.g. PMC-DES vs PMC-DSN)
                    tpl = extract_template(decode_rsc(phtml))
                title = (tpl or {}).get("template_name") or it.get("template_name")
                ttype = norm_type((tpl or {}).get("template_type") or it.get("template_type"), tid)
                desc_parts = []
                if tpl:
                    md = tpl.get("metadata") or {}
                    hdr = tpl.get("header") or {}
                    for x in (tpl.get("description"), md.get("when_to_use"), hdr.get("subtitle")):
                        if x and x not in desc_parts:
                            desc_parts.append(x)
                    if md.get("frequency"):
                        desc_parts.append(f"Frequency: {md['frequency']}")
                    if md.get("who_uses"):
                        desc_parts.append("Used by: " + ", ".join(md["who_uses"]))
                if not desc_parts and prec:
                    desc_parts.append((prec.get("metadata") or {}).get("description") or "")
                markdown = trim_markdown((prec or {}).get("markdown", ""))
                if prec and not markdown:  # http-fallback pages have no markdown: render from JSON
                    markdown = f"# {title}\n\n" + "\n\n".join(f"## {t}\n{b}" for t, b in render_template_text(tpl or {}))
                con.execute(
                    "INSERT INTO templates (template_id, source_id, family, family_code, title, type, description, "
                    "page_url, download_xlsx, download_pdf, raw_markdown, scraped_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (tid, lib, fam_name, fam_code, title, ttype, "\n".join(d for d in desc_parts if d) or None,
                     page_url, None, None, markdown or None, prec and prec.get("fetched_at")))
                st["index"] += 1
                st["families"].setdefault(fam_code, [0, 0])
                st["families"][fam_code][0] += 1
                # ---- codes
                codes = []
                code_text = []
                if tpl:
                    for c in tpl.get("applicable_codes") or []:
                        code_text.append(c.get("code", "") + " " + str(c.get("title", "")) if isinstance(c, dict) else str(c))
                    code_text.append((tpl.get("header") or {}).get("reference_line") or "")
                    for c in tpl.get("related_codes") or []:
                        code_text.append(str(c))
                    for s in tpl.get("sections") or []:
                        for i2 in (s.get("items") or []) if isinstance(s, dict) else []:
                            if isinstance(i2, dict):
                                code_text.append(str(i2.get("is_code_ref") or ""))
                if not tpl:  # page not cached: fall back to the family's primary codes from the index listing
                    code_text.extend(str(c) for c in fam.get("primary_codes") or [])
                for c in extract_codes(" ; ".join(code_text)):
                    if c not in codes:
                        codes.append(c)
                for c in codes:
                    con.execute("INSERT OR IGNORE INTO template_codes VALUES (?,?)", (tid, c))
                # ---- fields
                rows = template_fields(tpl, tid) if tpl else []
                overrides = [re.compile(p, re.I) for p in HOLD_OVERRIDES.get(tid, [])]
                for r in rows:
                    if r["field_kind"] == "check_item" and any(p.search(r["label"]) for p in overrides):
                        r["is_hold_point"] = 1
                        r["is_mandatory"] = 1
                    if ttype == "Permit" and PERMIT_BLOCKING.search(r["label"] + " " + (r["acceptance"] or "")):
                        r["is_mandatory"] = 1
                        r["is_hold_point"] = 1
                    con.execute(
                        "INSERT INTO template_fields (template_id, section, ordinal, label, field_kind, unit, "
                        "is_mandatory, is_hold_point, code_ref, item_ref, requirement, acceptance) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (tid, r["section"], r["ordinal"], r["label"], r["field_kind"], r["unit"], r["is_mandatory"],
                         r["is_hold_point"], r["code_ref"], r["item_ref"], r["requirement"], r["acceptance"]))
                if prec:
                    st["pages"] += 1
                    st["families"][fam_code][1] += 1
                    st["via"][prec.get("fetched_via")] = st["via"].get(prec.get("fetched_via"), 0) + 1
                st["fields"] += len(rows)
                if not rows:
                    st["no_fields"].append(tid)
                # ---- retrieval chunks
                summary = (f"TEMPLATE {tid} — {title} [{ttype}] · {lib.upper()} library · family {fam_name} ({fam_code}).\n"
                           f"Codes: {', '.join(codes) or '—'}\n{' '.join(desc_parts)[:600]}\n"
                           f"Fields: " + "; ".join(r["label"] + (" [HOLD POINT]" if r["is_hold_point"] else "")
                                                   + (" [mandatory]" if r["is_mandatory"] and not r["is_hold_point"] else "")
                                                   for r in rows)[:1200])
                add_chunk(con, "template", tid, None, clause=None, content=summary)
                blocks = render_template_text(tpl) if tpl else []
                for t, b in blocks:
                    for c in chunks_of(b):
                        add_chunk(con, "template", tid, None, clause=None, content=f"{tid} {title} — {t}\n{c}")
                if not blocks and markdown:
                    for c in chunks_of(markdown):
                        add_chunk(con, "template", tid, None, clause=None, content=f"{tid} {title}\n{c}")
        stats[lib] = st
    return stats


def add_chunk(con, doc_type, doc_ref, project_id, content, drawing_number=None, revision=None, clause=None):
    con.execute("INSERT INTO doc_chunks (doc_type, doc_ref, project_id, drawing_number, revision, clause_id, content) "
                "VALUES (?,?,?,?,?,?,?)", (doc_type, doc_ref, project_id, drawing_number, revision, clause, content))


def template_exists(con, tid):
    return tid and con.execute("SELECT 1 FROM templates WHERE template_id=?", (tid,)).fetchone() is not None


def ensure_template(con, tid, title, ttype, family, family_code, source):
    """Only used when a contract-referenced template is missing from the cache (should not happen once
    the index is cached — all 550 index rows are created from the site's own listing)."""
    if not template_exists(con, tid):
        log(f"  ! template {tid} missing from cache; inserting placeholder from seed reference")
        con.execute("INSERT INTO templates (template_id, source_id, family, family_code, title, type, description) "
                    "VALUES (?,?,?,?,?,?,?)", (tid, source, family, family_code, title, ttype,
                                               "Placeholder — page not yet scraped"))


# ================================================================================================
# 2. Seed
# ================================================================================================
def load_project_seed(con: sqlite3.Connection, S: dict) -> dict:
    P = S["project"]
    pid = P["project_id"]
    con.execute("INSERT INTO projects VALUES (:project_id,:name,:client,:location,:contract_type,:start_date)", P)
    for l in S["locations"]:
        con.execute("INSERT INTO locations VALUES (?,?,?,?,?,?)",
                    (l["location_id"], pid, l["grid"], l["level"], l["zone"], json.dumps(l["aliases"], ensure_ascii=False)))

    for tid, title, ttype, fam, fc, src in [
        ("FMT-TND-005", "BOQ Format (CPWD)", "Form", "Tendering & Contracts", "TND", "formats"),
        ("FMT-SIT-016", "Daily Progress Report (DPR) — Site", "Register", "Site Execution", "SIT", "formats"),
        ("PMC-DSN-LOG-003", "RFI (Request for Information) Log", "Log", "Design Coordination", "DSN", "pmc"),
        ("QC-SPW-REG-004", "Site Observation Register", "Register", "Site Paperwork & Coordination", "SPW", "qaqc"),
        ("QC-CON-CHK-001", "Pre-Pour Inspection Checklist", "Checklist", "Concrete & RCC", "CON", "qaqc"),
    ]:
        ensure_template(con, tid, title, ttype, fam, fc, src)

    for b in S["boq_items"]:
        con.execute("INSERT INTO boq_items VALUES (:boq_id,:project_id,:item_code,:description,:unit,:qty_tendered,"
                    ":rate,:amount,:spec_ref,:template_id)", b)
        add_chunk(con, "boq", b["boq_id"], pid,
                  f"BOQ item {b['item_code']} (CPWD DSR) — {b['description']}. Unit {b['unit']}, tendered qty "
                  f"{b['qty_tendered']:g}, rate ₹{b['rate']:g}/{b['unit']}, amount ₹{b['amount']:,.0f}. Spec: {b['spec_ref']}.")

    for d in S["drawings"]:
        con.execute("INSERT INTO drawings VALUES (:drawing_id,:project_id,:drawing_number,:revision,:rev_ordinal,:title,"
                    ":discipline,:status,:issued_on,:zone,:level,:is_latest,:superseded_by,:change_note)", d)
    facts_by_dwg: dict[str, list] = {}
    for f in S["drawing_facts"]:
        con.execute("INSERT INTO drawing_facts (drawing_id, location_id, element, element_mark, attribute, value_num, "
                    "value_text, unit, tolerance, code_ref) VALUES (:drawing_id,:location_id,:element,:element_mark,"
                    ":attribute,:value_num,:value_text,:unit,:tolerance,:code_ref)", f)
        facts_by_dwg.setdefault(f["drawing_id"], []).append(f)

    for r in S["rfis"]:
        con.execute("INSERT INTO rfis VALUES (:rfi_id,:project_id,:subject,:location_id,:drawing_ref,:spec_ref,:question,"
                    ":response,:status,:raised_on,:answered_on,:impact,:resulting_drawing_id,'PMC-DSN-LOG-003')",
                    {**r, "project_id": pid})
        add_chunk(con, "rfi", r["rfi_id"], pid,
                  f"{r['rfi_id']} [{r['status']}] {r['subject']}. Location {r['location_id']}, drawing {r['drawing_ref']}. "
                  f"Raised {r['raised_on']}" + (f", answered {r['answered_on']}" if r["answered_on"] else "") + ". "
                  f"Q: {r['question']} " + (f"A: {r['response']} " if r["response"] else "") +
                  f"Impact: {r['impact']}." + (f" Resulting drawing {r['resulting_drawing_id']}." if r["resulting_drawing_id"] else ""),
                  drawing_number=r["drawing_ref"],
                  revision=r["resulting_drawing_id"].split("@")[1] if r["resulting_drawing_id"] else None,
                  clause=r["spec_ref"])

    # drawing chunks (after RFIs so we can mention them)
    rfi_by_dwg = {r["resulting_drawing_id"]: r["rfi_id"] for r in S["rfis"] if r["resulting_drawing_id"]}
    for d in S["drawings"]:
        facts = facts_by_dwg.get(d["drawing_id"], [])
        lines = [f"DRAWING {d['drawing_number']} Rev {d['revision']} ({d['drawing_id']}) — {d['title']}. {d['discipline']}. "
                 f"Status: {d['status']}" + (" — LATEST for construction" if d["is_latest"] else "") +
                 f". Issued {d['issued_on']}." + (f" Superseded by {d['superseded_by']}." if d["superseded_by"] else "") +
                 (f" Issued via {rfi_by_dwg[d['drawing_id']]}." if d["drawing_id"] in rfi_by_dwg else "") +
                 f" Change note: {d['change_note']}"]
        for f in facts:
            v = f["value_text"] if f["value_text"] else f"{f['value_num']:g}"
            lines.append(f"- {f['location_id']} {f['element']} {f['element_mark']}: {f['attribute']} = {v} {f['unit'] or ''}"
                         + (f" (±{f['tolerance']:g})" if f["tolerance"] else "") + (f" [{f['code_ref']}]" if f["code_ref"] else ""))
        for c in chunks_of("\n".join(lines)):
            add_chunk(con, "drawing", d["drawing_id"], pid, c, drawing_number=d["drawing_number"], revision=d["revision"])

    for s in S["submittals"]:
        tid = s["template_hint"] if template_exists(con, s["template_hint"]) else None
        con.execute("INSERT INTO submittals VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (s["submittal_id"], pid, s["type"], s["material"], s["spec_section"], s["status"],
                     s["reviewer_comments"], s["submitted_on"], s["reviewed_on"], tid))
        add_chunk(con, "submittal", s["submittal_id"], pid,
                  f"SUBMITTAL {s['submittal_id']} [{s['status']}] {s['type']}: {s['material']}. Spec {s['spec_section']}. "
                  f"Submitted {s['submitted_on']}" + (f", reviewed {s['reviewed_on']}" if s["reviewed_on"] else "") +
                  f". Comments: {s['reviewer_comments']}", clause=s["spec_section"])

    for d in S["daily_logs"]:
        # Preserve the established P1 identifiers; prefix additional projects to avoid PK collisions.
        lid = f"DPR-{d['log_date']}" if pid == "P1" else f"DPR-{pid}-{d['log_date']}"
        con.execute("INSERT INTO daily_logs VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (lid, pid, d["log_date"], d["weather"], json.dumps(d["manpower"]), d["work_done"],
                     json.dumps(d["materials"], ensure_ascii=False), json.dumps(d["equipment"]), d["safety"], "FMT-SIT-016"))
        add_chunk(con, "dpr", lid, pid,
                  f"DPR {d['log_date']} ({pid}). Weather: {d['weather']}. Manpower: "
                  + ", ".join(f"{k} {v}" for k, v in d["manpower"].items()) + f" (total {sum(d['manpower'].values())}). "
                  f"Work done: {d['work_done']} Materials: " + ", ".join(f"{k} {v}" for k, v in d["materials"].items())
                  + f". Safety: {d['safety']}")

    # permits + checks derived from the permit template's fields
    permit_stats = {}
    for p in S["permits"]:
        tid = next((t for t in p["template_pref"]
                    if con.execute("SELECT COUNT(*) FROM template_fields WHERE template_id=? AND field_kind='check_item'",
                                   (t,)).fetchone()[0]), None) or next((t for t in p["template_pref"] if template_exists(con, t)), None)
        con.execute("INSERT INTO permits VALUES (?,?,?,?,?,?,?,?,?)",
                    (p["permit_id"], pid, p["permit_type"], p["location_id"], p["valid_from"], p["valid_to"],
                     p["status"], p["issued_by"], tid))
        rows = con.execute("SELECT field_id, label, is_mandatory, is_hold_point, acceptance FROM template_fields "
                           "WHERE template_id=? AND field_kind='check_item' AND section NOT IN ('Header','Details','Sign-off') "
                           "ORDER BY ordinal", (tid,)).fetchall() if tid else []
        kws = [k.lower() for k in p["unsatisfied_keywords"]]
        unsat = []
        for fid, label, mand, hold, acc in rows:
            bad = any(k in label.lower() for k in kws)
            sat = 0 if bad else 1
            if p["status"] == "Closed":
                sat = 1
            if sat == 0:
                unsat.append(label)
            con.execute("INSERT INTO permit_checks VALUES (?,?,?,?,?,?,?)",
                        (p["permit_id"], fid, label, 1 if (mand or hold) else 0, sat,
                         p["issued_by"].split(" (")[0] if sat else None,
                         (p["valid_from"] + ":00+05:30") if sat else None))
        permit_stats[p["permit_id"]] = (tid, len(rows), unsat)
        add_chunk(con, "permit", p["permit_id"], pid,
                  f"PERMIT {p['permit_id']} ({p['permit_type']}) at {p['location_id']} — status {p['status']}, valid "
                  f"{p['valid_from']} to {p['valid_to']}, issued by {p['issued_by']}. Template {tid}. "
                  f"{len(rows)} checks; UNSATISFIED: {'; '.join(unsat) if unsat else 'none'}."
                  + (" Work must STOP until these mandatory checks are satisfied." if unsat and p["status"] == "Active" else ""))

    # checklist instances
    for c in S["checklists"]:
        con.execute("INSERT INTO checklist_instances VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (c["instance_id"], pid, c["template_id"], c["location_id"], c["element"], c["element_mark"],
                     c["drawing_id"], c["planned_activity"], c["planned_for"], c["status"], c["hold_point_released"],
                     c["inspected_by"], c["inspected_on"],
                     c["inspected_by"] if c["hold_point_released"] else None,
                     (c["inspected_on"] + "T10:40:00+05:30") if c["hold_point_released"] else None, c["notes"]))
        rows = con.execute("SELECT field_id, item_ref, section, label, is_mandatory, is_hold_point, field_kind "
                           "FROM template_fields WHERE template_id=? AND section NOT IN ('Header','Details') ORDER BY ordinal",
                           (c["template_id"],)).fetchall()
        holds = []
        for fid, ref, sec, label, mand, hold, kind in rows:
            status, remarks = "OK", None
            if kind != "check_item":
                status = "pending" if not c["hold_point_released"] else "signed"
            for ov in c["item_overrides"]:
                if any(m in label.lower() for m in ov["match"]):
                    status, remarks = ov["status"], ov["remarks"]
                    break
            if c["hold_point_released"] and kind == "check_item":
                status, remarks = "OK", None
            if status.startswith("HOLD"):
                holds.append(f"{ref or ''} {label}".strip())
            con.execute("INSERT INTO checklist_items VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (c["instance_id"], fid, ref, sec, label, mand, hold, status, remarks,
                         c["inspected_by"].split(" (")[0], c["inspected_on"]))
        add_chunk(con, "checklist", c["instance_id"], pid,
                  f"CHECKLIST {c['instance_id']} ({c['template_id']} Pre-Pour Inspection) for {c['location_id']} "
                  f"{c['element']} {c['element_mark']} per {c['drawing_id']}. Planned {c['planned_activity']} on "
                  f"{c['planned_for']}. Status {c['status']}; hold point released: "
                  f"{'YES' if c['hold_point_released'] else 'NO — pour is BLOCKED'}. {c['notes']} "
                  + (f"Items on HOLD: {'; '.join(holds)}." if holds else ""),
                  drawing_number=c["drawing_id"].split("@")[0], revision=c["drawing_id"].split("@")[1])

    for o in S["observations"]:
        cols = list(o.keys())
        con.execute(f"INSERT INTO field_observations ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [o[k] for k in cols])

    for clause, text in S["code_clauses"]:
        # P1 keeps its legacy global-looking doc_ref. Other site-specific notes must stay scoped.
        add_chunk(con, "code_clause", clause if pid == "P1" else f"{pid}:{clause}",
                  None if pid == "P1" else pid, text, clause=clause)
    return {"permits": permit_stats}


def load_seeds(con: sqlite3.Connection) -> dict[str, dict]:
    """Regenerate canonical P1, then load every project seed through the same path."""
    p1_path = DATA / "seed" / "project_p1.json"
    p1_path.write_text(json.dumps(seed_p1.build_seed(), ensure_ascii=False, indent=1))
    stats: dict[str, dict] = {}
    for path in sorted((DATA / "seed").glob("project_*.json")):
        seed = json.loads(path.read_text())
        pid = str((seed.get("project") or {}).get("project_id") or "").strip()
        if not pid:
            raise ValueError(f"{path.name}: missing project.project_id")
        if pid in stats:
            raise ValueError(f"duplicate project_id {pid} in {path.name}")
        stats[pid] = load_project_seed(con, seed)
    return stats


# ================================================================================================
# 3. Sanity checks
# ================================================================================================
def sanity(con) -> list[str]:
    errs = []
    q = lambda sql, *a: con.execute(sql, a).fetchall()  # noqa: E731
    r = q("SELECT value_num, unit, drawing_id, via_rfi FROM v_current_facts WHERE location_id='P1:C-5:L3' "
          "AND element='column' AND attribute='rebar_spacing'")
    if r != [(180.0, "mm", "A-102@R4", "RFI-047")]:
        errs.append(f"v_current_facts C-5 spacing unexpected: {r}")
    for _, num in q("SELECT project_id, drawing_number FROM drawings WHERE status='For Construction' GROUP BY project_id, drawing_number "
                  "HAVING SUM(is_latest)<>1"):
        errs.append(f"drawing {num}: is_latest not exactly once")
    if not q("SELECT 1 FROM v_current_facts WHERE project_id='NSK' AND location_id='NSK:C-7:L3' "
             "AND drawing_id='SSB-STR-L3-201@R2' AND attribute='cover' AND value_num=40"):
        errs.append("NSK C-7 L3 latest cover fact missing")
    if not q("SELECT 1 FROM v_permit_blockers WHERE permit_id='HWP-2031' AND lower(check_label) LIKE '%fire watch%'"):
        errs.append("NSK HWP-2031 has no unsatisfied fire-watch check")
    if not q("SELECT 1 FROM v_open_hold_points WHERE location_id='NSK:Slab:L3' AND instance_id='CL-PP-SSB-L3-001'"):
        errs.append("NSK L3 slab pre-pour hold point not present")
    if not q("SELECT 1 FROM v_permit_blockers WHERE permit_id='HWP-0112' AND lower(check_label) LIKE '%fire watch%'"):
        errs.append("HWP-0112 has no unsatisfied fire-watch check")
    if not q("SELECT 1 FROM v_open_hold_points WHERE location_id='P1:Slab:L4' AND template_id='QC-CON-CHK-001'"):
        errs.append("L4 slab pre-pour hold point not present")
    hits = [x[0] for x in q("SELECT doc_ref FROM doc_chunks_fts WHERE doc_chunks_fts MATCH 'fire watch' LIMIT 5")]
    if not hits:
        errs.append("FTS 'fire watch' returned nothing")
    fk = q("PRAGMA foreign_key_check")
    if fk:
        errs.append(f"foreign key violations: {fk[:5]}")
    if q("SELECT 1 FROM drawings WHERE drawing_number='A-109'"):
        errs.append("A-109 must not exist (scenario S10)")
    # scenarios.json expectations must be consistent with the seeded facts
    for sc in json.loads((DATA / "seed" / "scenarios.json").read_text()):
        lg = (sc["expect"].get("logged") or {})
        if not lg.get("drawing_id") or not lg.get("attribute"):
            continue
        rows = q("SELECT value_num, tolerance FROM v_current_facts WHERE drawing_id=? AND location_id=? AND attribute=? "
                 "AND element=?", lg["drawing_id"], lg["location_id"], lg["attribute"], lg.get("element", "column"))
        if len(rows) != 1:
            errs.append(f"{sc['id']}: expected exactly one latest fact, got {rows}")
            continue
        within = abs(rows[0][0] - lg["value"]) <= (rows[0][1] or 0)
        if within == ("dimension_mismatch" in sc["expect"]["kinds"]):
            errs.append(f"{sc['id']}: value {lg['value']} vs fact {rows[0]} inconsistent with kinds {sc['expect']['kinds']}")
    return errs


def main():
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = Path(str(DB) + suffix)
        if p.exists():
            p.unlink()
    con = sqlite3.connect(DB)
    con.executescript((DATA / "schema.sql").read_text())
    con.execute("PRAGMA foreign_keys=OFF")  # bulk load (self-referencing drawings); verified by foreign_key_check
    with con:
        tstats = load_templates(con)
        sstats = load_seeds(con)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("INSERT INTO doc_chunks_fts(doc_chunks_fts) VALUES ('optimize')")
    con.commit()

    # ---- report
    log("\n== templates per source (index rows / scraped pages / expected)")
    for lib, st in tstats.items():
        log(f"  {lib:8s} {st['index']:4d} / {st['pages']:4d} / {EXPECTED[lib]}   fields={st['fields']}  via={st.get('via')}")
        log("     " + "  ".join(f"{k}:{v[0]}/{v[1]}" for k, v in sorted(st["families"].items())))
        if st.get("no_fields"):
            log(f"     templates without fields ({len(st['no_fields'])}): {', '.join(st['no_fields'][:15])}"
                + (" ..." if len(st["no_fields"]) > 15 else ""))
    for t in ("templates", "template_codes", "template_fields", "locations", "boq_items", "drawings", "drawing_facts",
              "rfis", "submittals", "daily_logs", "permits", "permit_checks", "checklist_instances", "checklist_items",
              "field_observations", "doc_chunks"):
        log(f"  {t:20s} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
    for project_id, project_stats in sstats.items():
        for permit_id, (tid, n, unsat) in project_stats["permits"].items():
            log(f"  permit {project_id}/{permit_id}: template={tid} checks={n} unsatisfied={unsat}")
    errs = sanity(con)
    con.execute("PRAGMA journal_mode=DELETE")  # single-file db for the app
    con.close()
    if errs:
        print("\nSANITY FAILURES:\n  " + "\n  ".join(errs))
        sys.exit(1)
    log("\nsanity: OK  ->", DB)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    ARGS = ap.parse_args()
    main()
