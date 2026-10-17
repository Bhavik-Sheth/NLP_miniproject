#!/usr/bin/env python
"""Build Vesper's memory index: global knowledge + project site records.

    backend/.venv/bin/python scripts/ingest_knowledge.py                 # everything present
    backend/.venv/bin/python scripts/ingest_knowledge.py --only projects --project P1,NSK
    backend/.venv/bin/python scripts/ingest_knowledge.py --sections code,prices --no-cognee

Resumable: every document is keyed by sha256(content + chunking version) per dataset, so a rerun skips what
is already indexed. Progress -> data/memory/ingest_log.txt; timings -> data/memory/index_build.json.

Sources
  data/site.db   templates + template_fields (kb_templates), code_clause chunks (kb_is_codes),
                 project record: drawings+facts, RFIs, permits+checks, checklists+items, DPRs, BOQ,
                 submittals, observations -> one org/project dataset
  data/raw/sections/<section>/*.json (W6 crawler)
                 code, irc -> kb_is_codes · prices, steel, sor, rate-analysis, dcr -> kb_prices_sor
                 thumbrules, handbook, knowledge, term, cpheeo, gate -> kb_handbook
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from memory import chunkers, config, ingest, store  # noqa: E402
from memory.chunkers import Chunk  # noqa: E402
from memory.ingest import DocSpec, log  # noqa: E402

SECTION_DATASET = {
    "code": "kb_is_codes", "irc": "kb_is_codes",
    "prices": "kb_prices_sor", "steel": "kb_prices_sor", "sor": "kb_prices_sor", "rate-analysis": "kb_prices_sor",
    "dcr": "kb_prices_sor",
    "thumbrules": "kb_handbook", "handbook": "kb_handbook", "knowledge": "kb_handbook", "term": "kb_handbook",
    "cpheeo": "kb_handbook", "gate": "kb_handbook",
}
CATEGORY = {"kb_is_codes": "is_code", "kb_prices_sor": "price_sor", "kb_handbook": "handbook"}
SECTION_ORDER = ["code", "thumbrules", "handbook", "knowledge", "term", "irc", "cpheeo", "prices", "steel", "sor",
                 "rate-analysis", "dcr", "gate"]
CURATED_CODES = {"IS 456", "IS 800", "IS 1893", "IS 13920", "IS 875"}
CURATED_SECTIONS = {"thumbrules", "handbook"}      # cognified (graph) in the background, bounded
FLUSH_CHUNKS = 600

STATS: dict = {"phases": {}, "started_at": store.now_iso()}


class Batcher:
    def __init__(self, phase: str, total: int):
        self.phase, self.total = phase, total
        self.specs: list[DocSpec] = []
        self.pending_chunks = 0
        self.seen = self.indexed = self.skipped = self.chunks = 0
        self.t0 = time.time()
        self.embed_s = 0.0

    def add(self, spec: DocSpec | None) -> None:
        self.seen += 1
        if spec is None:
            return
        if store.find_document(spec.dataset, spec.content_hash) and \
                store.find_document(spec.dataset, spec.content_hash)["status"] == "done":
            self.skipped += 1
            return
        if not spec.chunks:
            return
        self.specs.append(spec)
        self.pending_chunks += len(spec.chunks)
        if self.pending_chunks >= FLUSH_CHUNKS:
            self.flush()

    def flush(self) -> None:
        if not self.specs:
            return
        t = time.time()
        res = ingest.ingest_docs(self.specs)
        self.embed_s += time.time() - t
        self.indexed += sum(1 for r in res if r["status"] == "done")
        self.skipped += sum(1 for r in res if r["status"] == "skipped")
        self.chunks += sum(r["chunks"] for r in res if r["status"] == "done")
        self.specs, self.pending_chunks = [], 0
        el = time.time() - self.t0
        log(f"[{self.phase}] {self.seen}/{self.total} docs · indexed {self.indexed} · skipped {self.skipped} · "
            f"chunks {self.chunks} · {self.chunks / max(el, 1e-6):.1f} chunks/s · {el:.0f}s")

    def done(self) -> dict:
        self.flush()
        el = time.time() - self.t0
        out = {"docs_seen": self.seen, "indexed": self.indexed, "skipped": self.skipped, "chunks": self.chunks,
               "seconds": round(el, 1), "index_seconds": round(self.embed_s, 1)}
        STATS["phases"][self.phase] = out
        log(f"[{self.phase}] DONE {out}")
        return out


def h(*parts) -> str:
    return chunkers.sha256_text(json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
                                + config.CHUNKING_VERSION)


# ============================================================== site.db: templates
def site() -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{config.SITE_DB_PATH}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def ingest_templates() -> None:
    c = site()
    tpls = [dict(r) for r in c.execute("SELECT * FROM templates ORDER BY template_id")]
    fields: dict[str, list[dict]] = {}
    for r in c.execute("SELECT * FROM template_fields ORDER BY template_id, ordinal"):
        fields.setdefault(r["template_id"], []).append(dict(r))
    codes: dict[str, list[str]] = {}
    for r in c.execute("SELECT template_id, code FROM template_codes ORDER BY code"):
        codes.setdefault(r["template_id"], []).append(r["code"])
    overview = {}
    for r in c.execute("SELECT doc_ref, content FROM doc_chunks WHERE doc_type = 'template' AND content LIKE '%— Overview%'"):
        overview[r["doc_ref"]] = "\n".join(r["content"].splitlines()[1:])
    b = Batcher("templates", len(tpls))
    for t in tpls:
        tid = t["template_id"]
        f = fields.get(tid, [])
        chunks = chunkers.template_chunks(t, f, codes.get(tid, []), overview.get(tid, ""))
        if not f and t.get("raw_markdown"):
            chunks += chunkers.split_text_chunks(t["raw_markdown"], f"{tid} {t['title']}",
                                                 citation=f"per template {tid}")[:12]
        b.add(DocSpec(dataset="kb_templates", title=f"{tid} {t['title']}", chunks=chunks,
                      content_hash=h({k: v for k, v in t.items() if k != "scraped_at"}, f, codes.get(tid)),
                      category="template", source=f"infralens:{t['source_id']}", url=t.get("page_url"),
                      source_key=tid, graph=any(x.get("is_hold_point") for x in f),
                      meta={"template_id": tid, "family": t.get("family"), "type": t.get("type")}))
    b.done()


# ============================================================== site.db: project record
def ingest_project(project_id: str, org_id: str | None = None) -> None:
    c = site()
    org, pid = org_id or config.DEMO_ORG, project_id.strip().upper()
    ds = config.project_dataset(org, pid)
    rows = lambda sql, a=(): [dict(r) for r in c.execute(sql, a)]  # noqa: E731
    specs: list[DocSpec] = []

    def spec(title, chunks, key, category, content, source="site.db"):
        return DocSpec(dataset=ds, title=title, chunks=chunks, content_hash=h(content), org_id=org, project_id=pid,
                       category=category, source=source, source_key=key, graph=True)

    projects = rows("SELECT * FROM projects WHERE project_id = ?", (pid,))
    if not projects:
        raise ValueError(f"project {pid!r} is not present in site.db")
    p = projects[0]
    locs = rows("SELECT location_id, grid, level, zone FROM locations WHERE project_id = ? ORDER BY location_id", (pid,))
    dwgs = rows("SELECT drawing_number, revision, title, discipline, issued_on FROM v_latest_drawings "
                "WHERE project_id = ? ORDER BY drawing_number", (pid,))
    fact = (f"PROJECT FACT SHEET — {p['name']} (project {pid})\nClient: {p.get('client')}\nLocation: {p.get('location')}\n"
            f"Contract type: {p.get('contract_type')}\nStart date: {p.get('start_date')}\n"
            f"Locations on record: " + ", ".join(l["location_id"].split(":", 1)[1] for l in locs) + "\n"
            "Current For-Construction drawings: " + "; ".join(
                f"{d['drawing_number']} {d['revision']} {d.get('title') or ''} ({d.get('discipline')}, issued {d.get('issued_on')})"
                for d in dwgs))
    specs.append(spec(f"Project fact sheet — {p['name']}", chunkers.split_text_chunks(
        fact, "Project fact sheet", citation="per the project profile", kind="profile"), "p1_fact_sheet",
        "project_profile", fact))

    cat = {"drawing": "drawing", "rfi": "rfi", "boq": "boq", "submittal": "submittal"}
    grouped: dict[tuple, list[dict]] = {}
    for r in rows("SELECT doc_type, doc_ref, drawing_number, revision, content FROM doc_chunks "
                  "WHERE project_id = ? AND doc_type IN ('drawing','rfi','boq','submittal') ORDER BY chunk_id",
                  (pid,)):
        grouped.setdefault((r["doc_type"], r["doc_ref"]), []).append(r)
    for (dt, ref), items in grouped.items():
        content = "\n".join(i["content"] for i in items)
        first = content.splitlines()[0][:160]
        cite = (f"per drawing {items[0]['drawing_number']} {items[0]['revision']}" if dt == "drawing"
                else f"per {ref}" if dt in ("rfi", "submittal") else f"per BOQ item {ref}")
        specs.append(spec(first, chunkers.split_text_chunks(content, first, citation=cite, kind="record"),
                          f"{dt}:{ref}", cat[dt], content))

    for pm in rows("SELECT * FROM permits WHERE project_id = ?", (pid,)):
        checks = rows("SELECT label, is_mandatory, satisfied FROM permit_checks WHERE permit_id = ?", (pm["permit_id"],))
        txt = (f"PERMIT {pm['permit_id']} — {pm['permit_type'].replace('_', ' ')} permit at {pm['location_id']}, status "
               f"{pm['status']}, valid {pm.get('valid_from')} to {pm.get('valid_to')}, issued by {pm.get('issued_by')}, "
               f"template {pm.get('template_id')}.\nChecks:\n" + "\n".join(
                   f"- {k['label']} [{'MANDATORY' if k['is_mandatory'] else 'optional'}] "
                   f"{'satisfied' if k['satisfied'] else 'NOT satisfied'}" for k in checks))
        specs.append(spec(f"Permit {pm['permit_id']} ({pm['permit_type']})", chunkers.split_text_chunks(
            txt, f"Permit {pm['permit_id']}", citation=f"per permit {pm['permit_id']}", kind="record"),
            f"permit:{pm['permit_id']}", "permit", txt))

    for ci in rows("SELECT * FROM checklist_instances WHERE project_id = ?", (pid,)):
        items = rows("SELECT item_ref, section, label, is_mandatory, is_hold_point, status, remarks FROM checklist_items "
                     "WHERE instance_id = ? ORDER BY section, item_ref", (ci["instance_id"],))
        txt = (f"CHECKLIST {ci['instance_id']} ({ci['template_id']}) at {ci['location_id']} for {ci.get('element')} "
               f"{ci.get('element_mark') or ''}, drawing {ci.get('drawing_id')}, planned {ci.get('planned_activity')} on "
               f"{ci.get('planned_for')}. Status {ci['status']}; hold point released: "
               f"{'yes' if ci['hold_point_released'] else 'NO'}. Notes: {ci.get('notes') or '-'}\nItems:\n" + "\n".join(
                   f"- {i['item_ref']} {i['label']}{' [HOLD POINT]' if i['is_hold_point'] else ''} — {i['status']}"
                   + (f" ({i['remarks']})" if i.get("remarks") else "") for i in items))
        specs.append(spec(f"Checklist {ci['instance_id']} at {ci['location_id']}", chunkers.split_text_chunks(
            txt, f"Checklist {ci['instance_id']}", citation=f"per checklist {ci['instance_id']}", kind="record"),
            f"checklist:{ci['instance_id']}", "checklist", txt))

    for d in rows("SELECT * FROM daily_logs WHERE project_id = ? ORDER BY log_date", (pid,)):
        txt = (f"DAILY PROGRESS REPORT {d['log_id']} — {d['log_date']}. Weather: {d.get('weather')}.\nWork done: "
               f"{d.get('work_done')}\nManpower: {d.get('manpower_json')}\nMaterials: {d.get('materials_json')}\n"
               f"Equipment: {d.get('equipment_json')}\nSafety: {d.get('safety_incidents') or 'none'}")
        specs.append(spec(f"Daily progress report {d['log_date']}", chunkers.split_text_chunks(
            txt, f"DPR {d['log_date']}", citation=f"per the daily progress report of {d['log_date']}", kind="record"),
            f"dpr:{d['log_id']}", "daily_log", txt))

    for o in rows("SELECT * FROM field_observations WHERE project_id = ? ORDER BY created_at", (pid,)):
        txt = (f"OBSERVATION {o['observation_id']} on {o['created_at'][:10]} at {o.get('location_id')}: "
               f"{o.get('structured_summary')}. Spoken: {o.get('spoken_text')}. Decision: {o.get('final_decision')}"
               + (f", linked {o['linked_rfi_id']}" if o.get("linked_rfi_id") else ""))
        specs.append(spec(f"Observation {o['observation_id']}", [Chunk(text=txt, kind="record",
                                                                        citation=f"per observation {o['observation_id']}")],
                          f"obs:{o['observation_id']}", "observation", txt))

    b = Batcher(f"project_{pid.lower()}_record", len(specs))
    for s in specs:
        b.add(s)
    b.done()

    # Site-specific code notes belong only to the project that owns the chunk.
    cl = rows("SELECT doc_ref, content FROM doc_chunks WHERE doc_type = 'code_clause' AND project_id = ?", (pid,))
    b = Batcher(f"project_{pid.lower()}_code_clauses", len(cl))
    for r in cl:
        m = re.match(r"(IS \d+)\s+Cl\.\s*([\d.]+\w*(?:\([a-z]\))?)", r["doc_ref"])
        code, clause = (m.group(1), m.group(2)) if m else (r["doc_ref"], "")
        # These notes may carry site-specific tolerances, so they are project data, never global.
        b.add(DocSpec(dataset=ds, title=r["doc_ref"], content_hash=h(r["content"]), category="is_code",
                      org_id=org, project_id=pid,
                      source="site.db:code_clause", source_key=f"site:{r['doc_ref']}", graph=True,
                      chunks=[Chunk(text=r["content"], section=r["doc_ref"], kind="clause",
                                    citation=f"per {code} clause {clause}", meta={"code": code, "clause": clause})]))
    b.done()


def ingest_p1() -> None:
    """Backward-compatible entrypoint retained for existing scripts/tests."""
    ingest_project(config.DEMO_PROJECT, config.DEMO_ORG)


# ============================================================== crawled sections
_NOISE = re.compile(r"^#{1,6}\s*(Related|More related|QA/QC Inspection Templates|Frequently Asked Questions|"
                    r"Tools that use|Other SOR publishers|Related reading|Related codes|See also|Want a live|"
                    r"Disclaimer|International Equivalents|📋|📘|📖|🗺)", re.I | re.M)
_JUNK_LINE = re.compile(r"^(PDF Google Compare BIS Portal|Link points to Internet Archive.*|Download.*|Expand all.*|"
                        r"See also .*|Share.*|Print.*)$", re.I)


def clean_text(text: str) -> str:
    m = _NOISE.search(text or "")
    if m and m.start() > 200:
        text = text[:m.start()]
    return "\n".join(ln for ln in (text or "").splitlines() if not _JUNK_LINE.match(ln.strip()))


def load_page(path: Path) -> tuple[dict, dict]:
    d = json.loads(path.read_text())
    s = d.get("structured") or {}
    if isinstance(s, str):
        try:
            s = ast.literal_eval(s)
        except Exception:  # noqa: BLE001
            s = {}
    return d, s if isinstance(s, dict) else {}


def code_norm(code_number: str | None, fallback: str) -> str:
    c = re.sub(r"\s*:\s*\d{4}.*$", "", (code_number or "").strip()) or fallback
    return re.sub(r"\s+", " ", c)


def faq_chunk(s: dict, title: str, citation: str) -> list[Chunk]:
    faq = [f for f in s.get("faq") or [] if isinstance(f, dict) and f.get("q")]
    if not faq:
        return []
    txt = f"{title} — frequently asked\n" + "\n".join(f"Q: {f['q']}\nA: {f.get('a', '')}" for f in faq[:12])
    return chunkers.split_text_chunks(txt, title, citation=citation, kind="text")[:3]


def page_spec(section: str, path: Path) -> DocSpec | None:
    d, s = load_page(path)
    if d.get("parse_error") and not d.get("text"):
        return None
    ds = SECTION_DATASET[section]
    title = (d.get("title") or path.stem).strip()[:200]
    text = d.get("text") or ""
    chunks: list[Chunk] = []
    graph = section in CURATED_SECTIONS
    meta: dict = {"section": section, "slug": d.get("slug")}
    if section in ("code", "irc"):
        ptype = s.get("page_type") or "code"
        if ptype == "clauses":
            return None
        code = code_norm(s.get("code_number"), title.split(":")[0])
        meta["code"] = code
        graph = code in CURATED_CODES
        if ptype == "clause":
            cid = str(s.get("clause_id") or "").strip()
            ctitle = s.get("clause_title") or ""
            body = s.get("clause_text") or clean_text(text)
            sec = f"{code} Cl. {cid} {ctitle}".strip()
            for piece in chunkers.split_text_chunks(body, sec, citation=f"per {code} clause {cid}", kind="clause")[:10]:
                piece.section = sec if not piece.section else f"{sec} > {piece.section}"
                piece.text = f"{sec}\n{piece.text}"
                piece.meta.update({"code": code, "clause": cid})
                chunks.append(piece)
            for t in (s.get("tables") or [])[:4]:
                if t and len(t) > 1:
                    chunks += chunkers.table_chunks(t[0], t[1:], title=title, section=sec,
                                                    citation=f"per {code} clause {cid}")
            meta["clause"] = cid
        else:
            kv = s.get("key_values") or {}
            if isinstance(kv, list):
                kv = {(str(i.get('label') or i.get('name') or i.get('key') or n) if isinstance(i, dict) else str(n)):
                      (i.get('value', '') if isinstance(i, dict) else i) for n, i in enumerate(kv)}
            elif not isinstance(kv, dict):
                kv = {}
            qr = [q for q in s.get("quick_ref") or [] if isinstance(q, dict)]
            clauses = [x for x in s.get("clauses") or [] if isinstance(x, dict)]
            # thin stubs (overview + FAQ) get <=3 chunks and are down-weighted at query time
            rich = len(qr) >= 8 or len(clauses) >= 5 or len(text) > 15000 or code in CURATED_CODES
            meta["thin"] = not rich
            summ = [f"{s.get('code_number') or code} — {s.get('code_title') or title}", s.get("description") or ""]
            if kv:
                summ.append("Key values: " + "; ".join(f"{k}: {v}" for k, v in kv.items()))
            for label, key in (("Key clauses", "key_clauses"), ("Key tables", "key_tables"),
                               ("Formulas", "key_formulas"), ("Practical notes", "practical_notes"),
                               ("Amendments", "amendments")):
                if s.get(key):
                    summ.append(f"{label}: " + "; ".join(map(str, s[key])))
            chunks += chunkers.split_text_chunks("\n".join(x for x in summ if x), title, citation=f"per {code}",
                                                 kind="clause")[:4 if code in CURATED_CODES else 2]
            if qr:
                rows = [[q.get("label", ""), q.get("value", ""), q.get("clause", ""), q.get("note", "")] for q in qr]
                chunks += chunkers.table_chunks(["Parameter", "Value", "Clause", "Note"], rows, title=title,
                                                section=f"{code} quick reference", citation=f"per {code}")
            curated = code in CURATED_CODES
            if not rich:  # thin stub: one chunk (overview + key values + up to 3 FAQs)
                faq = [f for f in s.get("faq") or [] if isinstance(f, dict) and f.get("q")][:3]
                txt = "\n".join(x for x in summ if x) + (
                    "\nFAQ: " + " ".join(f"Q: {f['q']} A: {f.get('a', '')}" for f in faq) if faq else "")
                chunks = [Chunk(text=txt[:1600], section=title, kind="clause", citation=f"per {code}",
                                meta={"code": code, "thin": True})]
            else:
                cards = clauses[:30] if curated else clauses[:15]
                if curated:
                    for x in cards:
                        cid = str(x.get("clause_id") or "")
                        chunks.append(Chunk(text=f"{code} Cl. {cid} {x.get('clause_title', '')}\n{x.get('summary', '')}",
                                            section=f"{code} Cl. {cid} {x.get('clause_title', '')}", kind="clause",
                                            citation=f"per {code} clause {cid}", meta={"code": code, "clause": cid}))
                else:
                    for i in range(0, len(cards), 5):
                        txt = "\n".join(f"{code} Cl. {x.get('clause_id', '')} {x.get('clause_title', '')}: "
                                        f"{x.get('summary', '')}" for x in cards[i:i + 5])
                        chunks.append(Chunk(text=txt, section=f"{code} clauses", kind="clause", citation=f"per {code}",
                                            meta={"code": code}))
                chunks += faq_chunk(s, title, f"per {code}")[:3 if curated else 1]
                if curated:
                    chunks += chunkers.split_text_chunks(clean_text(text), title, citation=f"per {code}",
                                                         kind="clause")[:12]
    elif section == "prices":
        items = [i for i in s.get("items") or [] if isinstance(i, dict)]
        where = s.get("city_slug") or ""
        date = s.get("date") or ""
        cite = f"per InfraLens material prices{', ' + where if where else ''}{', ' + str(date) if date else ''}"
        if items:
            rows = [[i.get("item", ""), i.get("spec", ""), i.get("unit", ""), i.get("rate", "")] for i in items]
            chunks += chunkers.table_chunks(["Item", "Spec", "Unit", "Rate"], rows, title=title,
                                            section=f"{s.get('material') or 'Materials'} — {where} {date}".strip(),
                                            citation=cite)
        if s.get("description"):
            chunks.append(Chunk(text=f"{title}\n{s['description']}", section=title, citation=cite))
        if not items:
            chunks += chunkers.split_text_chunks(clean_text(text), title, citation=cite)[:4]
        meta.update({"material": s.get("material"), "city": where, "date": date})
    elif section == "steel":
        props = [p for p in s.get("properties") or [] if isinstance(p, dict)]
        cite = f"per {s.get('standard') or 'IS 808'} section properties"
        if props:
            chunks += chunkers.table_chunks(["Property", "Value", "Unit"],
                                            [[p.get("name", ""), p.get("value", ""), p.get("unit", "")] for p in props],
                                            title=title, section=s.get("section_name") or title, citation=cite)
        chunks += chunkers.split_text_chunks(clean_text(text), title, citation=cite)[:2]
    elif section in ("sor", "rate-analysis"):
        cite = f"per {s.get('authority') or 'InfraLens rate analysis'}{' ' + s['item_code'] if s.get('item_code') else ''}"
        head = (f"{title}\n{s.get('item_description') or ''}\nUnit: {s.get('unit')} · Rate: {s.get('rate')}"
                f"{' (' + str(s['rate_city']) + ')' if s.get('rate_city') else ''}\n{s.get('description') or ''}")
        chunks.append(Chunk(text=head.strip(), section=title, citation=cite))
        comps = [x for x in s.get("components") or [] if isinstance(x, dict)]
        if comps:
            chunks += chunkers.table_chunks(["Group", "Component", "Qty", "Unit", "Rate", "Amount"],
                                            [[x.get("group", ""), x.get("component", ""), x.get("quantity", ""),
                                              x.get("unit", ""), x.get("rate", ""), x.get("amount", "")] for x in comps],
                                            title=title, section=f"{title} components", citation=cite)
        chunks += chunkers.split_text_chunks(clean_text(text), title, citation=cite)[:3]
    elif section == "term":
        term = s.get("term") or title
        txt = (f"{term}: {s.get('definition') or s.get('short_definition') or s.get('description') or ''}"
               + (f"\nAlso called: {', '.join(map(str, s['aliases']))}" if s.get("aliases") else "")
               + (f"\nCategory: {s['category']}" if s.get("category") else ""))
        chunks.append(Chunk(text=txt, section=f"Glossary — {term}", citation=f"per the glossary entry for {term}"))
    else:  # thumbrules, handbook, knowledge, cpheeo, gate, dcr
        cite = f"per InfraLens {section.replace('-', ' ')}: {title}"
        cap = {"knowledge": 12, "handbook": 14, "dcr": 8, "cpheeo": 10, "gate": 6}.get(section, 10)
        chunks += chunkers.split_text_chunks(clean_text(text), title, citation=cite)[:cap]
        chunks += faq_chunk(s, title, cite)
        if s.get("codes_referenced"):
            meta["codes"] = s["codes_referenced"][:10]
    if not chunks:
        return None
    return DocSpec(dataset=ds, title=title, chunks=chunks, content_hash=h(text, s), category=CATEGORY[ds],
                   source=f"infralens:{section}", url=d.get("url"), source_key=f"{section}/{d.get('slug') or path.stem}",
                   graph=graph if ds not in config.TABULAR_DATASETS else False, meta=meta)


def ingest_sections(only: list[str] | None) -> None:
    base = config.SECTIONS_DIR
    if not base.exists():
        log("[sections] data/raw/sections missing — skipped")
        return
    for section in SECTION_ORDER:
        if only and section not in only:
            continue
        d = base / section
        if not d.is_dir():
            log(f"[{section}] not present — skipped")
            continue
        files = sorted(p for p in d.glob("*.json") if not p.name.startswith("_"))
        if section == "code":  # curated major codes first, so the useful part is searchable early
            key = lambda p: (0 if re.match(r"IS-(456|800|1893|13920|875)\b", p.name) else 1, p.name)  # noqa: E731
            files.sort(key=key)
        b = Batcher(section, len(files))
        for p in files:
            try:
                b.add(page_spec(section, p))
            except Exception as e:  # noqa: BLE001
                log(f"[{section}] {p.name} failed: {e!r}"[:300])
        b.done()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="templates,projects,sections")
    ap.add_argument("--project", default=config.DEMO_PROJECT,
                    help="comma-separated site-record project IDs (default: demo project)")
    ap.add_argument("--sections", default="")
    ap.add_argument("--no-cognee", action="store_true")
    ap.add_argument("--no-index", action="store_true")
    ap.add_argument("--cognify-max", type=int, default=config.COGNEE_MAX_DOCS_PER_RUN)
    a = ap.parse_args()
    only = [x.strip() for x in a.only.split(",") if x.strip()]
    projects = list(dict.fromkeys(x.strip().upper() for x in a.project.split(",") if x.strip()))
    secs = [x.strip() for x in a.sections.split(",") if x.strip()] or None
    t0 = time.time()
    log(f"=== ingest_knowledge start only={only} projects={projects} sections={secs or 'all'}")
    from memory import embed
    if not embed.health().get("ok"):
        log("ollama/bge-m3 not reachable — aborting")
        sys.exit(2)
    if "templates" in only:
        ingest_templates()
    if "projects" in only or "p1" in only:
        selected = [config.DEMO_PROJECT] if "p1" in only and "projects" not in only else projects
        for project_id in selected:
            ingest_project(project_id)
    if "sections" in only:
        ingest_sections(secs)
    if not a.no_index:
        t = time.time()
        STATS["index"] = store.build_indexes()
        STATS["index"]["seconds"] = round(time.time() - t, 1)
        log(f"[index] {STATS['index']}")
    STATS["total_seconds"] = round(time.time() - t0, 1)
    STATS["vectors"] = store.vector_count()
    STATS["finished_at"] = store.now_iso()
    prev = {}
    out = config.MEMORY_DIR / "index_build.json"
    if out.exists():
        try:
            prev = json.loads(out.read_text())
        except Exception:  # noqa: BLE001
            prev = {}
    prev.setdefault("runs", []).append(STATS)
    prev["runs"] = prev["runs"][-10:]
    out.write_text(json.dumps(prev, indent=1))
    log(f"=== ingest_knowledge done in {STATS['total_seconds']}s · vectors {STATS['vectors']}")
    if not a.no_cognee and ingest.ensure_cognee_worker(max_docs=a.cognify_max):
        log(f"cognee worker started (max {a.cognify_max} docs) -> {config.COGNEE_LOG}")


if __name__ == "__main__":
    main()
