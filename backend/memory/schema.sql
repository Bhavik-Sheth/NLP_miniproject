-- Vesper memory tables in data/app.db (W1). Idempotent: run on every connect.
-- Tenancy tables live in data/app_schema.sql (W2).

CREATE TABLE IF NOT EXISTS documents (
  doc_id          TEXT PRIMARY KEY,               -- uuid5(dataset:content_hash)
  scope           TEXT NOT NULL,                  -- global | project
  org_id          TEXT,
  project_id      TEXT,
  dataset         TEXT NOT NULL,                  -- kb_templates | org_<org>__proj_<project> ...
  source_key      TEXT,                           -- stable identity across versions (template id, filename ...)
  title           TEXT NOT NULL,
  category        TEXT,
  source          TEXT,                           -- site.db:templates | upload | text | voice | infralens:<section>
  url             TEXT,
  mime            TEXT,
  content_hash    TEXT NOT NULL,                  -- sha256 of the source bytes / text
  version         INTEGER NOT NULL DEFAULT 1,
  status          TEXT NOT NULL DEFAULT 'queued', -- queued|parsing|embedding|graph|done|error
  chunks          INTEGER NOT NULL DEFAULT 0,
  graph_status    TEXT NOT NULL DEFAULT 'skipped',-- pending|done|skipped|error
  graph_attempts  INTEGER NOT NULL DEFAULT 0,
  graph_error     TEXT,
  added_by        TEXT,
  meta            TEXT,                           -- JSON
  error           TEXT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  UNIQUE (dataset, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_mem_documents_dataset ON documents(dataset, status);
CREATE INDEX IF NOT EXISTS idx_mem_documents_graph ON documents(graph_status, scope);
CREATE INDEX IF NOT EXISTS idx_mem_documents_key ON documents(dataset, source_key);

CREATE TABLE IF NOT EXISTS chunks (
  rid               INTEGER PRIMARY KEY AUTOINCREMENT, -- stable rowid for the FTS external content
  chunk_id          TEXT NOT NULL UNIQUE,              -- <doc_id>:<n>
  doc_id            TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  n                 INTEGER NOT NULL,
  scope             TEXT NOT NULL,
  org_id            TEXT,
  project_id        TEXT,
  dataset           TEXT NOT NULL,
  title             TEXT,
  section           TEXT,
  page              INTEGER,
  category          TEXT,
  source            TEXT,
  url               TEXT,
  kind              TEXT,                              -- text|table|template|clause|record|profile
  text              TEXT NOT NULL,                     -- what the answerer reads (full table markdown)
  embed_text        TEXT,                              -- what was embedded (table summary, heading path + text)
  entities          TEXT,                              -- space-joined normalised ids: RFI-050 A-102 C-5 IS456 CL26.4
  citation          TEXT,                              -- spoken citation: "per IS 456 clause 26.4"
  meta              TEXT,                              -- JSON
  content_hash      TEXT,
  embedding_version TEXT,
  chunking_version  TEXT,
  created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mem_chunks_doc ON chunks(doc_id, n);
CREATE INDEX IF NOT EXISTS idx_mem_chunks_dataset ON chunks(dataset);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  text, title, section, entities,
  content='chunks', content_rowid='rid', tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text, title, section, entities)
  VALUES (new.rid, new.text, new.title, new.section, new.entities);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text, title, section, entities)
  VALUES ('delete', old.rid, old.text, old.title, old.section, old.entities);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text, title, section, entities)
  VALUES ('delete', old.rid, old.text, old.title, old.section, old.entities);
  INSERT INTO chunks_fts(rowid, text, title, section, entities)
  VALUES (new.rid, new.text, new.title, new.section, new.entities);
END;

CREATE TABLE IF NOT EXISTS ingest_jobs (
  job_id      TEXT PRIMARY KEY,
  doc_id      TEXT,
  org_id      TEXT,
  project_id  TEXT,
  dataset     TEXT NOT NULL,
  title       TEXT,
  source      TEXT,
  category    TEXT,
  status      TEXT NOT NULL DEFAULT 'queued',   -- queued|parsing|embedding|graph|done|error
  progress    REAL NOT NULL DEFAULT 0,
  error       TEXT,
  payload     TEXT,                             -- JSON: upload path, mime ... (never secrets)
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mem_jobs_project ON ingest_jobs(org_id, project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_mem_jobs_status ON ingest_jobs(status);
