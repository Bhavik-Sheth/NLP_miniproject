"""data/app.db connection helper shared by tenancy (W2) and memory (W1).

connect() opens data/app.db (or APP_DB_PATH) in WAL mode with sqlite3.Row rows and applies
data/app_schema.sql and backend/memory/schema.sql (when present) idempotently. Schema files must
use CREATE ... IF NOT EXISTS. The seeded demo org + project P1 row is inserted once.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import threading
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
def db_path() -> str:
    """Resolved per call, not at import: a test that sets APP_DB_PATH must not be defeated by
    whichever module happened to import this one first (that pointed tests at the real data/app.db)."""
    raw = os.getenv("APP_DB_PATH", str(REPO_ROOT / "data" / "app.db"))
    return raw if os.path.isabs(raw) else str((BACKEND_DIR / raw).resolve())


APP_DB_PATH = db_path()  # import-time snapshot, kept for callers that read the constant
SCHEMA_FILES = (REPO_ROOT / "data" / "app_schema.sql", BACKEND_DIR / "memory" / "schema.sql")

DEMO_ORG_ID = "org_local_demo"
DEMO_PROJECT_ID = "P1"
NSK_PROJECT_ID = "NSK"

_lock = threading.Lock()
_applied: dict[str, tuple] = {}  # db path -> schema file mtimes already applied in this process


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _schema_signature() -> tuple:
    return tuple((str(p), p.stat().st_mtime) for p in SCHEMA_FILES if p.exists())


def connect(path: str | None = None) -> sqlite3.Connection:
    """New connection per call (cheap). Safe to use from FastAPI threadpool handlers."""
    target = path or db_path()
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    sig = _schema_signature()
    if _applied.get(db_path) != sig:
        with _lock:
            if _applied.get(db_path) != sig:
                for f in SCHEMA_FILES:
                    if f.exists():
                        conn.executescript(f.read_text())
                _seed_demo(conn)
                conn.commit()
                _applied[db_path] = sig
    return conn


def _seed_demo(conn: sqlite3.Connection) -> None:
    """Expose deterministic site.db projects in the local demo organization."""
    ts = now_iso()
    conn.execute("INSERT OR IGNORE INTO orgs(id, name, profile_json, created_by, created_at) VALUES (?,?,?,?,?)",
                 (DEMO_ORG_ID, "Vesper Demo", json.dumps({"legalName": "Vesper Demo", "companyType": "contractor",
                                                           "city": "Pithoragarh", "state": "Uttarakhand"}), "system", ts))
    profile: dict = {"name": "Pithoragarh District Hospital & Staff Quarters", "code": "P1", "projectType": "hospital",
                     "city": "Pithoragarh", "state": "Uttarakhand", "clientName": "Uttarakhand Health Infrastructure Development Agency",
                     "contractType": "item_rate", "startDate": "2026-03-02", "governingCodes": ["IS 456", "IS 1893", "IS 13920", "CPWD Specs"],
                     "drawingConvention": "A-102, S-301, M-401", "revisionScheme": "R0", "siteLanguages": ["English", "Hinglish"],
                     "levelNaming": "GF, L1, L2, L3, L4", "siteLeadName": "Site in-charge", "currentPhase": "superstructure"}
    try:  # prefer the live seed values
        import config  # type: ignore
        sconn = sqlite3.connect(f"file:{config.SITE_DB_PATH}?mode=ro", uri=True)
        sconn.row_factory = sqlite3.Row
        r = sconn.execute("SELECT * FROM projects WHERE project_id = ?", (DEMO_PROJECT_ID,)).fetchone()
        sconn.close()
        if r:
            r = dict(r)
            profile["name"] = r.get("name") or profile["name"]
            profile["clientName"] = r.get("client") or profile["clientName"]
            profile["startDate"] = r.get("start_date") or profile["startDate"]
    except Exception:
        pass
    conn.execute(
        "INSERT OR IGNORE INTO projects(id, org_id, name, code, type, city, state, status, profile_json, created_by, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (DEMO_PROJECT_ID, DEMO_ORG_ID, profile["name"], "P1", "hospital", "Pithoragarh", "Uttarakhand", "active",
         json.dumps(profile), "system", ts, ts))

    nsk_profile_path = REPO_ROOT / "data" / "seed" / "profile_nsk.json"
    if nsk_profile_path.exists():
        try:
            nsk = json.loads(nsk_profile_path.read_text())
        except (OSError, ValueError):
            nsk = {}
        if nsk:
            conn.execute(
                "INSERT OR IGNORE INTO projects(id, org_id, name, code, type, city, state, status, profile_json, created_by, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (NSK_PROJECT_ID, DEMO_ORG_ID, nsk.get("name") or "Nashik Civil Hospital — 300-bed Super Speciality Block",
                 "NSK", nsk.get("projectType") or "hospital", nsk.get("city") or "Nashik",
                 nsk.get("state") or "Maharashtra", nsk.get("status") or "active", json.dumps(nsk), "system", ts, ts))
