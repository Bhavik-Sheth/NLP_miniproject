-- Vesper.ai — Site Memory schema (SQLite 3.38+, FTS5)
-- Shared contract between: data/scraper (writes), data/seed (writes), app/ (reads + writes field_observations)
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ============================================================================
-- 1. TEMPLATE LIBRARY (scraped from infralens.in)
-- ============================================================================
CREATE TABLE IF NOT EXISTS template_sources (
  source_id     TEXT PRIMARY KEY,           -- 'formats' | 'qaqc' | 'pmc'
  base_url      TEXT NOT NULL,
  scraped_at    TEXT
);

CREATE TABLE IF NOT EXISTS templates (
  template_id   TEXT PRIMARY KEY,           -- FMT-TND-005, QC-CON-CHK-001, PMC-SAF-PMT-001
  source_id     TEXT NOT NULL REFERENCES template_sources(source_id),
  family        TEXT NOT NULL,              -- 'Tendering & Contracts', 'Concrete & RCC', 'Safety' ...
  family_code   TEXT,                       -- TND, CON, SAF ...
  title         TEXT NOT NULL,
  type          TEXT NOT NULL,              -- Form|Checklist|Register|Test Report|Plan|Permit|Schedule|Report|Log|Matrix|Document|Certificate|Chart|Billing|MOM
  description   TEXT,
  page_url      TEXT,
  download_xlsx TEXT,
  download_pdf  TEXT,
  raw_markdown  TEXT,                       -- full scraped page body (for RAG)
  scraped_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_templates_family ON templates(family_code);
CREATE INDEX IF NOT EXISTS idx_templates_type   ON templates(type);

-- IS / IRC / CPWD / FIDIC / RERA / BOCW / NBC / ISO references, normalised
CREATE TABLE IF NOT EXISTS template_codes (
  template_id   TEXT NOT NULL REFERENCES templates(template_id) ON DELETE CASCADE,
  code          TEXT NOT NULL,              -- 'IS 456', 'CPWD Works Manual 2019'
  PRIMARY KEY (template_id, code)
);
CREATE INDEX IF NOT EXISTS idx_template_codes_code ON template_codes(code);

-- Column headings / checklist rows / permit fields extracted from the page (and xlsx if available)
CREATE TABLE IF NOT EXISTS template_fields (
  field_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  template_id   TEXT NOT NULL REFERENCES templates(template_id) ON DELETE CASCADE,
  section       TEXT,                       -- 'Header', 'Pre-pour checks', 'Sign-off' ...
  ordinal       INTEGER NOT NULL,
  label         TEXT NOT NULL,              -- 'Cover blocks placed as per drawing'
  field_kind    TEXT NOT NULL DEFAULT 'text', -- text|number|date|yes_no|signature|select|check_item
  unit          TEXT,
  is_mandatory  INTEGER NOT NULL DEFAULT 0,
  is_hold_point INTEGER NOT NULL DEFAULT 0, -- QA/QC hold point / permit blocker
  code_ref      TEXT,                       -- 'IS 456 Cl. 26.4'
  -- [added by data layer] extra detail from the site's embedded template JSON
  item_ref      TEXT,                       -- site item/field id: 'B3', 'permit_no'
  requirement   TEXT,                       -- code requirement text: 'Cl. 26.4.1 — Minimum cover ...'
  acceptance    TEXT                        -- acceptance criteria / select options
);
CREATE INDEX IF NOT EXISTS idx_template_fields_tpl ON template_fields(template_id);

-- ============================================================================
-- 2. PROJECT OPERATIONAL DATA (demo project seeded in data/seed)
-- ============================================================================
CREATE TABLE IF NOT EXISTS projects (
  project_id    TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  client        TEXT,
  location      TEXT,
  contract_type TEXT,                       -- 'Item Rate (CPWD)', 'EPC' ...
  start_date    TEXT
);

-- Grid lines / zones / levels the manager speaks about ("C-5", "Level 3", "Zone B")
CREATE TABLE IF NOT EXISTS locations (
  location_id   TEXT PRIMARY KEY,           -- 'P1:C-5:L3'
  project_id    TEXT NOT NULL REFERENCES projects(project_id),
  grid          TEXT,                       -- 'C-5'
  level         TEXT,                       -- 'L3', 'Plinth', 'Basement'
  zone          TEXT,
  aliases       TEXT                        -- JSON array: ["C5","see five","सी पांच"]
);

CREATE TABLE IF NOT EXISTS boq_items (
  boq_id        TEXT PRIMARY KEY,           -- 'P1-BOQ-5.1.2'
  project_id    TEXT NOT NULL REFERENCES projects(project_id),
  item_code     TEXT NOT NULL,              -- CPWD DSR code '5.22.6'
  description   TEXT NOT NULL,
  unit          TEXT NOT NULL,              -- cum, kg, sqm
  qty_tendered  REAL,
  rate          REAL,
  amount        REAL,
  spec_ref      TEXT,                       -- 'IS 456', 'CPWD Spec 5.3'
  template_id   TEXT REFERENCES templates(template_id)  -- e.g. FMT-TND-005
);

-- One row per drawing revision. is_latest=1 exactly once per drawing_number among status='For Construction'
CREATE TABLE IF NOT EXISTS drawings (
  drawing_id    TEXT PRIMARY KEY,           -- 'A-102@R4'
  project_id    TEXT NOT NULL REFERENCES projects(project_id),
  drawing_number TEXT NOT NULL,             -- 'A-102'
  revision      TEXT NOT NULL,              -- 'R4'
  rev_ordinal   INTEGER NOT NULL,           -- 4 (for ordering)
  title         TEXT,
  discipline    TEXT,                       -- Architectural|Structural|MEP|Civil
  status        TEXT NOT NULL,              -- 'For Construction'|'Superseded'|'For Approval'|'For Information'
  issued_on     TEXT,                       -- ISO date
  zone          TEXT,
  level         TEXT,
  is_latest     INTEGER NOT NULL DEFAULT 0,
  superseded_by TEXT REFERENCES drawings(drawing_id),
  change_note   TEXT,
  UNIQUE (project_id, drawing_number, revision)
);
CREATE INDEX IF NOT EXISTS idx_drawings_num ON drawings(project_id, drawing_number, rev_ordinal);

-- Atomic, checkable facts per drawing revision. This is what contradiction checks compare against.
CREATE TABLE IF NOT EXISTS drawing_facts (
  fact_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  drawing_id    TEXT NOT NULL REFERENCES drawings(drawing_id) ON DELETE CASCADE,
  location_id   TEXT REFERENCES locations(location_id),
  element       TEXT NOT NULL,              -- column|beam|slab|footing|wall|pipe|duct
  element_mark  TEXT,                       -- 'C12', 'B-205'
  attribute     TEXT NOT NULL,              -- rebar_spacing|rebar_dia|cover|size|thickness|grade|level|bar_count
  value_num     REAL,
  value_text    TEXT,
  unit          TEXT,                       -- mm|m|nos|MPa
  tolerance     REAL,                       -- allowed +/- in unit
  code_ref      TEXT                        -- 'IS 456 Cl. 26.4.2'
);
CREATE INDEX IF NOT EXISTS idx_facts_lookup ON drawing_facts(location_id, element, attribute);

CREATE TABLE IF NOT EXISTS rfis (
  rfi_id        TEXT PRIMARY KEY,           -- 'RFI-047'
  project_id    TEXT NOT NULL REFERENCES projects(project_id),
  subject       TEXT NOT NULL,
  location_id   TEXT REFERENCES locations(location_id),
  drawing_ref   TEXT,                       -- 'A-102'
  spec_ref      TEXT,
  question      TEXT,
  response      TEXT,
  status        TEXT NOT NULL,              -- Open|Answered|Closed
  raised_on     TEXT,
  answered_on   TEXT,
  impact        TEXT,                       -- 'Revision issued: A-102 R4'
  resulting_drawing_id TEXT REFERENCES drawings(drawing_id),
  template_id   TEXT REFERENCES templates(template_id)  -- PMC-DSN-LOG-003
);

CREATE TABLE IF NOT EXISTS submittals (
  submittal_id  TEXT PRIMARY KEY,
  project_id    TEXT NOT NULL REFERENCES projects(project_id),
  type          TEXT,                       -- Material|Shop Drawing|Method Statement|MTC
  material      TEXT,
  spec_section  TEXT,
  status        TEXT,                       -- Approved|Approved as Noted|Rejected|Under Review
  reviewer_comments TEXT,
  submitted_on  TEXT,
  reviewed_on   TEXT,
  template_id   TEXT REFERENCES templates(template_id)
);

CREATE TABLE IF NOT EXISTS daily_logs (
  log_id        TEXT PRIMARY KEY,           -- 'DPR-2026-09-09'
  project_id    TEXT NOT NULL REFERENCES projects(project_id),
  log_date      TEXT NOT NULL,
  weather       TEXT,
  manpower_json TEXT,                       -- {"mason":12,"bar_bender":8,...}
  work_done     TEXT,
  materials_json TEXT,
  equipment_json TEXT,
  safety_incidents TEXT,
  template_id   TEXT REFERENCES templates(template_id)  -- FMT-SIT-016 / QC-RPT-REG-001
);

CREATE TABLE IF NOT EXISTS permits (
  permit_id     TEXT PRIMARY KEY,           -- 'HWP-0112'
  project_id    TEXT NOT NULL REFERENCES projects(project_id),
  permit_type   TEXT NOT NULL,              -- hot_work|height|confined_space|excavation|electrical|lifting
  location_id   TEXT REFERENCES locations(location_id),
  valid_from    TEXT,
  valid_to      TEXT,
  status        TEXT NOT NULL,              -- Draft|Active|Suspended|Closed
  issued_by     TEXT,
  template_id   TEXT REFERENCES templates(template_id)  -- PMC-SAF-PMT-001 / QC-HSE-PRM-002
);

-- Per-permit checklist state (fields come from template_fields of the permit template)
CREATE TABLE IF NOT EXISTS permit_checks (
  permit_id     TEXT NOT NULL REFERENCES permits(permit_id) ON DELETE CASCADE,
  field_id      INTEGER NOT NULL REFERENCES template_fields(field_id),
  label         TEXT NOT NULL,
  is_mandatory  INTEGER NOT NULL DEFAULT 1,
  satisfied     INTEGER NOT NULL DEFAULT 0,
  confirmed_by  TEXT,
  confirmed_at  TEXT,
  PRIMARY KEY (permit_id, field_id)
);

-- [added by data layer] QA/QC checklist state per element (e.g. QC-CON-CHK-001 pre-pour for L4 slab).
-- hold_point_released=0 on an instance => any planned_activity at that location is a hold_point_blocker.
CREATE TABLE IF NOT EXISTS checklist_instances (
  instance_id   TEXT PRIMARY KEY,           -- 'CL-PP-L4-001'
  project_id    TEXT NOT NULL REFERENCES projects(project_id),
  template_id   TEXT NOT NULL REFERENCES templates(template_id),
  location_id   TEXT REFERENCES locations(location_id),
  element       TEXT,                       -- slab|column|beam ...
  element_mark  TEXT,
  drawing_id    TEXT REFERENCES drawings(drawing_id),
  planned_activity TEXT,                    -- 'concrete_pour'
  planned_for   TEXT,                       -- ISO date
  status        TEXT NOT NULL,              -- Open|Hold|Released|Rejected
  hold_point_released INTEGER NOT NULL DEFAULT 0,
  inspected_by  TEXT,
  inspected_on  TEXT,
  released_by   TEXT,
  released_at   TEXT,
  notes         TEXT
);
CREATE INDEX IF NOT EXISTS idx_checklist_loc ON checklist_instances(location_id, status);

CREATE TABLE IF NOT EXISTS checklist_items (
  instance_id   TEXT NOT NULL REFERENCES checklist_instances(instance_id) ON DELETE CASCADE,
  field_id      INTEGER NOT NULL REFERENCES template_fields(field_id),
  item_ref      TEXT,                       -- 'B3'
  section       TEXT,
  label         TEXT NOT NULL,
  is_mandatory  INTEGER NOT NULL DEFAULT 0,
  is_hold_point INTEGER NOT NULL DEFAULT 0,
  status        TEXT NOT NULL DEFAULT 'pending', -- OK|NC|NA|HOLD|pending (sign-off rows: verdict text)
  remarks       TEXT,
  checked_by    TEXT,
  checked_at    TEXT,
  PRIMARY KEY (instance_id, field_id)
);

-- ============================================================================
-- 3. VOICE LAYER OUTPUT
-- ============================================================================
CREATE TABLE IF NOT EXISTS voice_sessions (
  session_id    TEXT PRIMARY KEY,
  project_id    TEXT NOT NULL REFERENCES projects(project_id),
  user_name     TEXT,
  started_at    TEXT NOT NULL,
  ended_at      TEXT,
  lang          TEXT DEFAULT 'hi-en'        -- code-mixed Hinglish
);

-- Every turn: user ASR text + agent spoken reply. Used for audit + acceptance tests.
CREATE TABLE IF NOT EXISTS voice_turns (
  turn_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id    TEXT NOT NULL REFERENCES voice_sessions(session_id),
  role          TEXT NOT NULL,              -- user|agent
  text          TEXT NOT NULL,
  entities_json TEXT,                       -- extracted entities after this turn
  state         TEXT,                       -- capturing|checking|challenging|confirming|logged|blocked
  was_barge_in  INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS field_observations (
  observation_id TEXT PRIMARY KEY,          -- 'OBS-000123'
  project_id    TEXT NOT NULL REFERENCES projects(project_id),
  session_id    TEXT REFERENCES voice_sessions(session_id),
  spoken_text   TEXT NOT NULL,              -- final corrected utterance(s)
  structured_summary TEXT NOT NULL,
  location_id   TEXT REFERENCES locations(location_id),
  element       TEXT,
  attribute     TEXT,
  value_claimed REAL,
  unit          TEXT,
  drawing_id    TEXT REFERENCES drawings(drawing_id),   -- ALWAYS the verified latest revision
  revision_claimed TEXT,
  contradiction_flag INTEGER NOT NULL DEFAULT 0,
  contradiction_kinds TEXT,                 -- JSON: ["revision_mismatch","dimension_mismatch"]
  clarification_asked TEXT,                 -- what agent said
  final_decision TEXT NOT NULL,             -- log_observation|raise_rfi|raise_ncr|stop_work|cancelled
  linked_rfi_id TEXT REFERENCES rfis(rfi_id),
  linked_template_id TEXT REFERENCES templates(template_id), -- QC-SPW-REG-004 Site Observation Register
  audio_url     TEXT,
  photo_url     TEXT,
  gps_lat       REAL,
  gps_lng       REAL,
  created_at    TEXT NOT NULL
);

-- ============================================================================
-- 4. RETRIEVAL INDEX (template-aware; FTS5 now, embeddings optional)
-- ============================================================================
CREATE TABLE IF NOT EXISTS doc_chunks (
  chunk_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_type      TEXT NOT NULL,              -- template|drawing|rfi|boq|submittal|dpr|permit|code_clause
  doc_ref       TEXT NOT NULL,              -- template_id / drawing_id / rfi_id ...
  project_id    TEXT,
  drawing_number TEXT,
  revision      TEXT,
  clause_id     TEXT,
  content       TEXT NOT NULL,
  embedding     BLOB                        -- optional float32 vector
);
CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks_fts USING fts5(
  content, doc_type UNINDEXED, doc_ref UNINDEXED,
  content='doc_chunks', content_rowid='chunk_id', tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS doc_chunks_ai AFTER INSERT ON doc_chunks BEGIN
  INSERT INTO doc_chunks_fts(rowid, content, doc_type, doc_ref) VALUES (new.chunk_id, new.content, new.doc_type, new.doc_ref);
END;
CREATE TRIGGER IF NOT EXISTS doc_chunks_ad AFTER DELETE ON doc_chunks BEGIN
  INSERT INTO doc_chunks_fts(doc_chunks_fts, rowid, content, doc_type, doc_ref) VALUES ('delete', old.chunk_id, old.content, old.doc_type, old.doc_ref);
END;

-- ============================================================================
-- 5. VIEWS the voice layer uses directly
-- ============================================================================
CREATE VIEW IF NOT EXISTS v_latest_drawings AS
  SELECT * FROM drawings WHERE is_latest = 1 AND status = 'For Construction';

-- Latest-revision fact per (location, element, attribute), with the RFI that caused it (if any)
CREATE VIEW IF NOT EXISTS v_current_facts AS
  SELECT f.*, d.drawing_number, d.revision, d.issued_on, d.project_id,
         (SELECT r.rfi_id FROM rfis r WHERE r.resulting_drawing_id = d.drawing_id LIMIT 1) AS via_rfi
  FROM drawing_facts f JOIN drawings d ON d.drawing_id = f.drawing_id
  WHERE d.is_latest = 1 AND d.status = 'For Construction';

-- [added by data layer] Active permits with an unsatisfied mandatory check => permit_blocker
CREATE VIEW IF NOT EXISTS v_permit_blockers AS
  SELECT p.permit_id, p.permit_type, p.location_id, p.status, p.valid_from, p.valid_to, p.template_id,
         c.field_id, c.label AS check_label
  FROM permits p JOIN permit_checks c ON c.permit_id = p.permit_id
  WHERE p.status = 'Active' AND c.is_mandatory = 1 AND c.satisfied = 0;

-- [added by data layer] Checklist instances whose hold point is not released => hold_point_blocker
CREATE VIEW IF NOT EXISTS v_open_hold_points AS
  SELECT ci.instance_id, ci.template_id, ci.location_id, ci.element, ci.drawing_id, ci.planned_activity,
         ci.planned_for, ci.status, ci.notes,
         (SELECT COUNT(*) FROM checklist_items i WHERE i.instance_id = ci.instance_id AND i.status LIKE 'HOLD%') AS items_on_hold
  FROM checklist_instances ci
  WHERE ci.hold_point_released = 0;
