"""Read/write access to data/site.db. Python port of app/lib/engine/repo.ts + persist.ts.

The engine only ever touches `Repo` (reads) and the module-level persist functions
(writes to the four voice-owned tables: voice_sessions, voice_turns, field_observations,
rfis). `insert_observation` is the SAFETY GATE — it re-verifies against the DB right
before writing and raises rather than persist anything unverified.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import re
import sqlite3
import time
from typing import Any

from config import PROJECT_ID, SITE_DB_PATH


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or SITE_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 3000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("CREATE TABLE IF NOT EXISTS user_usage (user_id TEXT PRIMARY KEY, command_count INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL)")
    return conn


def _norm(s: Any) -> str:
    return re.sub(r"[\s\-_/]", "", (s or "")).lower() if s is not None else ""


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class SafetyGateError(Exception):
    def __init__(self, msg: str) -> None:
        super().__init__(f"SAFETY GATE: {msg}")


class Repo:
    def __init__(self, conn: sqlite3.Connection, project_id: str = PROJECT_ID) -> None:
        self.db = conn
        self.project_id = project_id
        self._table_cache: dict[str, list[str] | None] = {}

    # ---- helpers -------------------------------------------------------
    def _all(self, sql: str, args: tuple = ()) -> list[dict]:
        return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def _one(self, sql: str, args: tuple = ()) -> dict | None:
        r = self.db.execute(sql, args).fetchone()
        return dict(r) if r else None

    def columns(self, table: str) -> list[str] | None:
        if table in self._table_cache:
            return self._table_cache[table]
        rows = self.db.execute(f"SELECT name FROM pragma_table_info(?)", (table,)).fetchall()
        cols = [r["name"] for r in rows] or None
        self._table_cache[table] = cols
        return cols

    # ---- locations ---------------------------------------------------
    def locations(self) -> list[dict]:
        return self._all("SELECT * FROM locations WHERE project_id = ?", (self.project_id,))

    def resolve_location(self, q: dict) -> list[dict]:
        locs = self.locations()

        def alias_hit(l: dict, s: str | None) -> bool:
            if not s or not l.get("aliases"):
                return False
            try:
                return any(_norm(a) == _norm(s) for a in json.loads(l["aliases"]))
            except Exception:
                return False

        c = locs
        grid, zone, level, element = q.get("grid"), q.get("zone"), q.get("level"), q.get("element")
        if grid:
            c = [l for l in c if _norm(l.get("grid")) == _norm(grid) or alias_hit(l, grid)
                 or _norm(l["location_id"].split(":")[1]) == _norm(grid)]
        elif zone:
            in_zone = [l for l in c if _norm(l.get("zone")) == _norm(zone) or alias_hit(l, zone)
                       or _norm(l["location_id"].split(":")[1]) == _norm(zone)]
            zone_rows = [l for l in in_zone if not l.get("grid")
                         or _norm(l["location_id"].split(":")[1]) == _norm(zone)]
            c = zone_rows or in_zone
        elif element == "slab":
            c = [l for l in c if _norm(l.get("grid")) == "slab" or "slab" in l["location_id"].lower()]
        else:
            c = []
        if level:
            c = [l for l in c if _norm(l.get("level")) == _norm(level)]
        return c

    def location_exists(self, location_id: str) -> bool:
        return self._one("SELECT 1 FROM locations WHERE project_id = ? AND location_id = ?",
                         (self.project_id, location_id)) is not None

    def related_location_ids(self, location_id: str) -> list[str]:
        l = self._one("SELECT * FROM locations WHERE project_id = ? AND location_id = ?",
                      (self.project_id, location_id))
        ids = [location_id]
        if l and l.get("zone") and l.get("level"):
            rows = self._all(
                "SELECT location_id FROM locations WHERE project_id = ? AND grid IS NULL AND zone = ? AND level = ?",
                (self.project_id, l["zone"], l["level"]),
            )
            for r in rows:
                if r["location_id"] not in ids:
                    ids.append(r["location_id"])
        return ids

    # ---- drawings --------------------------------------------------
    def drawing_revisions(self, drawing_number: str) -> list[dict]:
        return self._all(
            "SELECT * FROM drawings WHERE project_id = ? AND drawing_number = ? ORDER BY rev_ordinal",
            (self.project_id, drawing_number),
        )

    def drawing_numbers(self) -> list[str]:
        return [r["drawing_number"] for r in self._all(
            "SELECT DISTINCT drawing_number FROM drawings WHERE project_id = ?", (self.project_id,))]

    def resolve_drawing_number(self, spoken: str) -> str | None:
        alln = self.drawing_numbers()
        for d in alln:
            if _norm(d) == _norm(spoken):
                return d
        if re.fullmatch(r"\d+", spoken or ""):
            # "102" -> A-102; "201" -> SSB-STR-L3-201 (sheet number = last digit group)
            suffix = [d for d in alln if re.sub(r"\D", "", d) == spoken
                      or (re.findall(r"\d+", d) or [""])[-1] == spoken]
            if len(suffix) == 1:
                return suffix[0]
        return None

    def latest_drawing(self, drawing_number: str) -> dict | None:
        return self._one(
            "SELECT * FROM v_latest_drawings WHERE project_id = ? AND drawing_number = ? "
            "ORDER BY rev_ordinal DESC LIMIT 1", (self.project_id, drawing_number))

    def drawing_by_id(self, drawing_id: str) -> dict | None:
        return self._one("SELECT * FROM drawings WHERE project_id = ? AND drawing_id = ?",
                         (self.project_id, drawing_id))

    def is_verified_latest(self, drawing_id: str) -> bool:
        return self._one("SELECT 1 FROM v_latest_drawings WHERE project_id = ? AND drawing_id = ?",
                         (self.project_id, drawing_id)) is not None

    def latest_drawing_for_location(self, location_id: str, level: str | None = None) -> dict | None:
        by_fact = self._one(
            "SELECT d.* FROM v_latest_drawings d JOIN drawing_facts f ON f.drawing_id = d.drawing_id "
            "WHERE f.location_id = ? ORDER BY d.issued_on DESC LIMIT 1", (location_id,))
        if by_fact:
            return by_fact
        if level:
            by_level = self._all(
                "SELECT * FROM v_latest_drawings WHERE project_id = ? AND level = ? ORDER BY issued_on DESC",
                (self.project_id, level))
            if len(by_level) == 1:
                return by_level[0]
        return None

    # ---- facts ---------------------------------------------------
    def current_facts(self, location_id: str, attribute: str | None = None,
                      element: str | None = None) -> list[dict]:
        sql = "SELECT * FROM v_current_facts WHERE location_id = ?"
        args: list[Any] = [location_id]
        if attribute:
            sql += " AND attribute = ?"
            args.append(attribute)
        if element:
            sql += " AND element = ?"
            args.append(element)
        return self._all(sql, tuple(args))

    def fact_on_revision(self, drawing_number: str, revision: str, location_id: str,
                         attribute: str) -> dict | None:
        return self._one(
            "SELECT f.*, d.drawing_number, d.revision, d.issued_on FROM drawing_facts f "
            "JOIN drawings d ON d.drawing_id = f.drawing_id WHERE d.project_id = ? AND d.drawing_number = ? "
            "AND d.revision = ? AND f.location_id = ? AND f.attribute = ? LIMIT 1",
            (self.project_id, drawing_number, revision, location_id, attribute))

    def facts_any_revision(self, drawing_number: str, location_id: str, attribute: str) -> list[dict]:
        return self._all(
            "SELECT f.*, d.drawing_number, d.revision, d.issued_on FROM drawing_facts f "
            "JOIN drawings d ON d.drawing_id = f.drawing_id WHERE d.project_id = ? AND d.drawing_number = ? "
            "AND f.location_id = ? AND f.attribute = ? ORDER BY d.rev_ordinal",
            (self.project_id, drawing_number, location_id, attribute))

    def rfi_for_drawing(self, drawing_id: str) -> dict | None:
        return self._one(
            "SELECT rfi_id, subject, answered_on FROM rfis WHERE project_id = ? AND resulting_drawing_id = ? LIMIT 1",
            (self.project_id, drawing_id))

    # ---- permits ------------------------------------------------
    def permit_blockers(self, location_id: str, activity: str) -> dict:
        ids = self.related_location_ids(location_id)
        ph = ",".join("?" for _ in ids)
        permits = self._all(
            f"SELECT * FROM permits WHERE project_id = ? AND permit_type = ? "
            f"AND (location_id IN ({ph}) OR location_id IS NULL)",
            (self.project_id, activity, *ids))
        active = [p for p in permits if p["status"] == "Active"]
        blocks = []
        for p in active:
            un = self._all(
                "SELECT field_id, label FROM permit_checks WHERE permit_id = ? AND is_mandatory = 1 AND satisfied = 0",
                (p["permit_id"],))
            if un:
                blocks.append({**p, "unsatisfied": un})
        for p in [p for p in permits if p["status"] == "Suspended"]:
            blocks.append({**p, "unsatisfied": [{"field_id": -1, "label": "Permit suspended"}]})
        return {"blocks": blocks, "activePermits": [p["permit_id"] for p in active],
                "noPermit": len(active) == 0}

    def permits_with_checks(self) -> list[dict]:
        permits = self._all("SELECT * FROM permits WHERE project_id = ? ORDER BY permit_id", (self.project_id,))
        for p in permits:
            p["checks"] = self._all("SELECT * FROM permit_checks WHERE permit_id = ?", (p["permit_id"],))
        return permits

    # ---- hold points (optional tables; introspected) ----------
    def hold_point_blockers(self, location_id: str) -> list[dict]:
        out: list[dict] = []
        inst = self.columns("checklist_instances")
        items = self.columns("checklist_items")
        if not (inst and items):
            return out
        id_col = next((c for c in ("instance_id", "checklist_id", "id") if c in inst), None)
        item_fk = next((c for c in ("instance_id", "checklist_id") if c in items), None)
        if not (id_col and item_fk):
            return out
        ids = self.related_location_ids(location_id)
        if "location_id" in inst:
            ph = ",".join("?" for _ in ids)
            rows = self._all(f"SELECT * FROM checklist_instances WHERE location_id IN ({ph})", tuple(ids))
        else:
            rows = self._all("SELECT * FROM checklist_instances")
        hold_col = "is_hold_point" if "is_hold_point" in items else None
        release_expr = self._release_expr(items)
        for r in rows:
            status = str(r.get("status") or "").lower()
            if status in ("released", "closed", "approved", "complete", "completed"):
                continue
            if "hold_point_released" in inst and int(r.get("hold_point_released") or 0) == 1:
                continue
            its = self._all(
                f"SELECT * FROM checklist_items WHERE {item_fk} = ? "
                f"{('AND ' + hold_col + ' = 1') if hold_col else ''} AND NOT ({release_expr})",
                (r[id_col],))
            if its:
                its.sort(key=lambda i: bool(re.match(r"^hold", str(i.get("status") or ""), re.I)), reverse=True)
                out.append({
                    "source": "checklist", "ref": str(r[id_col]),
                    "template_id": r.get("template_id"), "location_id": r.get("location_id"),
                    "notes": r.get("notes"),
                    "items": [{"label": str(i.get("label") or i.get("item") or i.get("description") or "Hold point"),
                               "code_ref": i.get("code_ref")} for i in its],
                })
        return out

    @staticmethod
    def _release_expr(cols: list[str]) -> str:
        parts = []
        for c in ("released", "satisfied", "is_released", "checked", "ok", "done"):
            if c in cols:
                parts.append(f"COALESCE({c},0) = 1")
        if "status" in cols:
            parts.append("LOWER(COALESCE(status,'')) IN "
                         "('released','ok','done','yes','pass','passed','approved','complete','completed','satisfied','na','n/a')")
        if "released_at" in cols:
            parts.append("released_at IS NOT NULL AND released_at <> ''")
        return " OR ".join(parts) if parts else "0"

    # ---- misc ------------------------------------------------
    def template(self, template_id: str) -> dict | None:
        return self._one("SELECT template_id, title FROM templates WHERE template_id = ?", (template_id,))


# ---------------------------------------------------------------- persist (writes)
def create_session(repo: Repo, user_name: str = "Site Manager", lang: str = "hi-en") -> str:
    sid = f"VS-{int(time.time()*1000):x}-{random.randbytes(3).hex()}"
    repo.db.execute(
        "INSERT INTO voice_sessions (session_id, project_id, user_name, started_at, lang) VALUES (?,?,?,?,?)",
        (sid, repo.project_id, user_name, _now_iso(), lang))
    repo.db.commit()
    return sid


def end_session(repo: Repo, session_id: str) -> None:
    repo.db.execute("UPDATE voice_sessions SET ended_at = ? WHERE session_id = ?", (_now_iso(), session_id))
    repo.db.commit()


def command_usage(repo: Repo, user_id: str) -> int:
    row = repo.db.execute("SELECT command_count FROM user_usage WHERE user_id = ?", (user_id,)).fetchone()
    return int(row["command_count"]) if row else 0


def reserve_command(repo: Repo, user_id: str, limit: int) -> tuple[bool, int]:
    """Atomically reserve one command; prevents concurrent tabs exceeding the allowance."""
    now = _now_iso()
    with repo.db:
        repo.db.execute("INSERT OR IGNORE INTO user_usage (user_id, command_count, updated_at) VALUES (?, 0, ?)", (user_id, now))
        cur = repo.db.execute("UPDATE user_usage SET command_count = command_count + 1, updated_at = ? WHERE user_id = ? AND command_count < ?", (now, user_id, limit))
    return cur.rowcount == 1, command_usage(repo, user_id)


def sessions_for_user(repo: Repo, user_name: str, limit: int = 12) -> list[dict]:
    return repo._all("SELECT session_id, project_id, started_at, ended_at, lang FROM voice_sessions "
                     "WHERE user_name = ? AND project_id = ? ORDER BY started_at DESC LIMIT ?",
                     (user_name, repo.project_id, limit))


def turns_for_session(repo: Repo, session_id: str) -> list[dict]:
    return repo._all("SELECT role, text, state, created_at FROM voice_turns WHERE session_id = ? ORDER BY turn_id ASC", (session_id,))


def insert_turn(repo: Repo, t: dict) -> int:
    cur = repo.db.execute(
        "INSERT INTO voice_turns (session_id, role, text, entities_json, state, was_barge_in, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (t["sessionId"], t["role"], t.get("text", ""),
         None if t.get("entities") is None else json.dumps(t["entities"]),
         t.get("state", ""), 1 if t.get("bargeIn") else 0, _now_iso()))
    repo.db.commit()
    return int(cur.lastrowid)


def _next_id(repo: Repo, table: str, col: str, prefix: str, width: int, *, project_scoped: bool = False) -> str:
    if project_scoped:
        rows = repo.db.execute(f"SELECT {col} AS id FROM {table} WHERE project_id = ? AND {col} LIKE ?",
                               (repo.project_id, f"{prefix}%")).fetchall()
    else:
        rows = repo.db.execute(f"SELECT {col} AS id FROM {table} WHERE {col} LIKE ?", (f"{prefix}%",)).fetchall()
    mx = 0
    for r in rows:
        n = re.sub(r"\D", "", r["id"])
        mx = max(mx, int(n) if n else 0)
    return f"{prefix}{str(mx + 1).zfill(width)}"


def insert_observation(repo: Repo, o: dict) -> str:
    """SAFETY GATE. `o` keys: sessionId, spokenText, summary, locationId, element, attribute,
    value, unit, drawingId, revisionClaimed, contradictionKinds(list), clarificationAsked,
    decision, linkedRfiId, photoUrl, gps({lat,lng}), allCriticalConfirmed(bool)."""
    kinds = o.get("contradictionKinds") or []
    if not o.get("allCriticalConfirmed"):
        raise SafetyGateError("unconfirmed or low-confidence critical slot")
    if o.get("drawingId") and not repo.is_verified_latest(o["drawingId"]):
        raise SafetyGateError(f"drawing {o['drawingId']} is not the verified latest For Construction revision")
    if o.get("locationId") and not repo.location_exists(o["locationId"]):
        raise SafetyGateError(f"unknown location {o['locationId']}")
    if o.get("decision") in ("log_observation", "raise_rfi", "raise_ncr") and not o.get("locationId"):
        raise SafetyGateError("no verified location")
    if kinds and not o.get("clarificationAsked"):
        raise SafetyGateError("contradiction without a prior spoken clarification")
    if o.get("value") is not None and o.get("attribute") and not o.get("unit"):
        raise SafetyGateError("value without unit")

    oid = _next_id(repo, "field_observations", "observation_id", "OBS-", 6)
    tpl = "QC-SPW-REG-004" if repo.template("QC-SPW-REG-004") else None
    gps = o.get("gps") or {}
    repo.db.execute(
        "INSERT INTO field_observations (observation_id, project_id, session_id, spoken_text, structured_summary, "
        "location_id, element, attribute, value_claimed, unit, drawing_id, revision_claimed, contradiction_flag, "
        "contradiction_kinds, clarification_asked, final_decision, linked_rfi_id, linked_template_id, photo_url, "
        "gps_lat, gps_lng, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (oid, repo.project_id, o["sessionId"], o.get("spokenText", ""), o.get("summary", ""),
         o.get("locationId"), o.get("element"), o.get("attribute"), o.get("value"), o.get("unit"),
         o.get("drawingId"), o.get("revisionClaimed"), 1 if kinds else 0,
         json.dumps(kinds) if kinds else None, o.get("clarificationAsked"), o["decision"],
         o.get("linkedRfiId"), tpl, o.get("photoUrl"), gps.get("lat"), gps.get("lng"), _now_iso()))
    repo.db.commit()
    return oid


def insert_rfi(repo: Repo, r: dict) -> str:
    """`r` keys: subject, locationId, drawingRef, question."""
    # keep the project's own numbering (P1 RFI-062, NSK RFI-SSB-013)
    last = repo._one("SELECT rfi_id FROM rfis WHERE project_id = ? ORDER BY rfi_id DESC LIMIT 1", (repo.project_id,))
    m = re.match(r"^(.*?-)(\d+)$", (last or {}).get("rfi_id") or "")
    prefix, width = (m.group(1), len(m.group(2))) if m else ("RFI-", 3)
    rid = _next_id(repo, "rfis", "rfi_id", prefix, width, project_scoped=True)
    tpl = "PMC-DSN-LOG-003" if repo.template("PMC-DSN-LOG-003") else None
    repo.db.execute(
        "INSERT INTO rfis (rfi_id, project_id, subject, location_id, drawing_ref, question, status, raised_on, template_id) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (rid, repo.project_id, r["subject"], r.get("locationId"), r.get("drawingRef"), r.get("question"),
         "Open", _now_iso()[:10], tpl))
    repo.db.commit()
    return rid
