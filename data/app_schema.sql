-- data/app.db tenancy tables (W2). Idempotent: run on every connect.
-- W1's memory tables live in backend/memory/schema.sql against the same file.

CREATE TABLE IF NOT EXISTS orgs (
  id           TEXT PRIMARY KEY,              -- Clerk organization id (org_...) or org_local_demo
  name         TEXT NOT NULL,
  profile_json TEXT NOT NULL DEFAULT '{}',
  created_by   TEXT,
  created_at   TEXT NOT NULL,
  updated_at   TEXT
);

CREATE TABLE IF NOT EXISTS org_members (
  org_id   TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  user_id  TEXT NOT NULL,
  role     TEXT NOT NULL DEFAULT 'member',   -- admin | member (Clerk role without the org: prefix)
  email    TEXT,
  PRIMARY KEY (org_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_org_members_user ON org_members(user_id);

CREATE TABLE IF NOT EXISTS projects (
  id           TEXT PRIMARY KEY,              -- P1 (seeded demo) or prj_<hex>
  org_id       TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  code         TEXT,
  type         TEXT,
  city         TEXT,
  state        TEXT,
  status       TEXT NOT NULL DEFAULT 'active',
  profile_json TEXT NOT NULL DEFAULT '{}',
  created_by   TEXT,
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_org ON projects(org_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_org_code ON projects(org_id, code);

CREATE TABLE IF NOT EXISTS project_members (
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id    TEXT NOT NULL DEFAULT '',        -- '' until an invited email signs in
  email      TEXT NOT NULL DEFAULT '',
  role       TEXT NOT NULL DEFAULT 'member',  -- owner | manager | engineer | viewer | member
  PRIMARY KEY (project_id, user_id, email)
);
CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members(user_id);
CREATE INDEX IF NOT EXISTS idx_project_members_email ON project_members(email);

CREATE TABLE IF NOT EXISTS invites (
  id         TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  email      TEXT NOT NULL,
  role       TEXT NOT NULL DEFAULT 'member',
  token      TEXT NOT NULL UNIQUE,
  status     TEXT NOT NULL DEFAULT 'pending', -- pending | accepted | revoked
  invited_by TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_invites_project ON invites(project_id);

CREATE TABLE IF NOT EXISTS activity (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  org_id     TEXT,
  project_id TEXT,
  actor      TEXT,
  kind       TEXT NOT NULL,                   -- org_created | project_created | project_updated | invite_sent | ...
  summary    TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_project ON activity(project_id, created_at);

CREATE TABLE IF NOT EXISTS email_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  to_hash     TEXT NOT NULL,                  -- sha256 of lower-cased recipient, never the address
  template    TEXT NOT NULL,                  -- kind + ':template' | ':inline'
  status      TEXT NOT NULL,                  -- sent | failed | skipped
  provider_id TEXT,
  error       TEXT,
  created_at  TEXT NOT NULL
);
