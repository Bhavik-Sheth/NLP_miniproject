# Data layer — `data/site.db`

Voice-agent project memory for construction site P1. Built offline from cached scrape
data. **This DB is the contract for the core logic — build against it, do not change the
schema without updating `schema.sql` + `build_db.py` + this file.**

## How to build

```bash
cd data
python3 build_db.py           # drops + recreates site.db from raw/ + seed/
python3 build_db.py           # run twice — output must be identical (repeatable)
```

Inputs:
- `data/raw/*__index.json` — template lists for the 3 InfraLens libraries (formats / qaqc / pmc)
- `data/raw/html/*.html.gz` — cached template detail pages (embedded JSON parsed for fields)
- `data/seed/project_p1.json`, `data/seed/seed_p1.py` — the P1 project world (locations,
  drawings, RFIs, permits, checklists, DPRs, BOQ, doc chunks)
- `data/seed/scenarios.json` — S01–S10 acceptance scenarios

`build_db.py` ends with `sanity: OK` when the invariants below hold; it prints the
permit-blocker summary as it goes.

No network needed. The scraper (`data/scraper/scrape_infralens.py`, Firecrawl) only
refreshes `raw/`; rotate the Firecrawl key after the hackathon.

## Row counts (current build, 2026-09-15)

All 550 template pages are now cached (the Firecrawl run stopped at ~297; the rest were fetched
with `scrape_infralens.py --http-only`), so every template has its full field list.

| table | rows | | table | rows |
|---|---:|---|---|---:|
| projects | 1 | | templates | 550 (all with fields) |
| locations | 32 | | template_fields | 19,133 |
| drawings | 18 | | template_sources | 3 |
| drawing_facts | 576 | | template_codes | 1,341 |
| rfis | 13 | | checklist_items | 124 |
| submittals | 8 | | doc_chunks | 6,947 |
| permits | 5 | | daily_logs | 7 |
| permit_checks | 79 | | boq_items | 26 |

## Beyond `site.db` (v2)

| Store | What | Built by |
| --- | --- | --- |
| `data/raw/sections/<section>/*.json` | 6,690 crawled infralens.in pages, parsed to text + structured fields: IS code 4,391 · prices 869 · glossary 394 · steel 220 · thumb rules 151 · knowledge 120 · SOR 118 · rate analysis 118 · handbook 98 · DCR 78 · GATE 76 · CPHEEO 48 · IRC 9 | `data/scraper/crawl_sections.py` (resumable; `--offline` coverage, `--reparse` rebuilds JSON from cached HTML). Formats: `docs/plan/research/05-infralens-sections.md` |
| `data/onboarding_schema.json` | Org (3 steps) + project (12 steps, 92 fields) onboarding schema — the single source of truth for the wizard and backend validation | hand-authored (W2) |
| `data/app.db` | Tenancy (orgs, members, projects, invites, activity, email log) and memory tables (documents, chunks, `chunks_fts` FTS5, ingest_jobs) | `data/app_schema.sql` + `backend/memory/schema.sql`, created by `backend/tenancy/appdb.py` |
| `data/memory/` | LanceDB vectors, Cognee system/graph dirs, embedding cache, ingest logs | `scripts/ingest_knowledge.py`, upload/text/voice ingest |

Memory datasets: `kb_templates`, `kb_is_codes`, `kb_prices_sor`, `kb_handbook` (global) and
`org_<orgId>__proj_<projectId>` per project. A project's search sees only its own dataset plus
the global ones.

Templates by `source_id`: **formats 100 · qaqc 300 · pmc 150** ✓ (target 100 / 300 / 150)

## Views (the core logic reads these, not raw tables)

- `v_latest_drawings` — one row per drawing number = its latest **For Construction** revision
- `v_current_facts` — `(location_id, element, attribute) → value_num, unit, tolerance,
  drawing_id, revision, via_rfi, code_ref` for the latest revision only
- `v_permit_blockers` — active permit × each unsatisfied **mandatory** check
- `v_open_hold_points` — checklist instances still on Hold, with `items_on_hold` count

## Sanity checks (all passing)

```
templates by source ............ formats 100 · qaqc 300 · pmc 150
DB rebuild ..................... identical output on 2nd run
S01 fact path .................. P1:C-5:L3 / rebar_spacing
                                 → A-102@R4 | 180 mm | ±10 | R4 | RFI-047 | IS 456 Cl. 26.5.3.2(c)
FTS 'fire watch' .............. hits QC-HSE-PRM-002 (hot-work) + permit HWP-0112
HWP-0112 mandatory checks ..... "Fire watcher assigned…" satisfied=0  (drives S05 block)
                                "Fire watch continues 60 min…"       satisfied=0
S08 L4 slab pre-pour .......... CL-PP-L4-001 @ P1:Slab:L4, QC-CON-CHK-001,
                                 status Hold, hold_point_released=0, 7 items on hold
                                 → v_open_hold_points returns it
scenarios.json ................ 10 entries S01–S10
```

Key templates (all have full field lists):

| template_id | name | fields | hold pts | mandatory |
|---|---|---:|---:|---:|
| QC-CON-CHK-001 | Pre-Pour Inspection | 70 | 12 | 16 |
| QC-HSE-PRM-002 | Hot Work Permit | 36 | 7 | 25 |
| PMC-SAF-PMT-001 | Hot Work Permit (PMC) | 38 | 4 | 29 |
| FMT-SIT-016 | Daily Progress Report | 21 | 0 | 5 |
| PMC-DSN-LOG-003 | RFI Log | 30 | 0 | 12 |
| QC-SPW-REG-004 | Site Observation Register | 35 | 0 | 7 |

Drawings — latest **For Construction**: A-101 R2 · **A-102 R4** · A-103 R1 · M-401 R1 ·
S-201 R2 · S-301 R2 · S-302 R1. (`A-102` R1–R3 are Superseded — never link an observation
to them.)

## FTS note

`doc_chunks_fts` columns are `content, doc_type, doc_ref` (query `content`, not `text`).
`MATCH` covers templates, permits, RFIs, drawing facts and DPRs.

## Known gaps (acceptable for MVP)

- **Detail-page scrape stopped at ~200 / 523** (Firecrawl run interrupted). So ~311 of the
  550 templates exist as header rows only (id / name / family / source) with **no
  `template_fields`**. Every template the 10 scenarios or the demo touch has full fields —
  verified above. To fill the rest: rerun `python3 data/scraper/scrape_infralens.py`
  (resumes, skips cached), then `python3 data/build_db.py`.
- `voice_sessions` / `voice_turns` empty until the app writes them.
- `field_observations` has 2 seed rows for the Memory screen; the app appends real ones.
