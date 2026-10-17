"""Upload the local SQLite site record, memory index and bge-m3 vectors to Supabase Postgres.

Schemas are created by the migrations `app_schema_orgs_projects_memory` and `site_record_schema`
(schemas `vesper` and `site`). This script only moves rows.

    export SUPABASE_DB_URL='postgresql://postgres.<ref>:<password>@<host>:6543/postgres?sslmode=require'
    backend/.venv/bin/python scripts/export_to_supabase.py            # everything
    backend/.venv/bin/python scripts/export_to_supabase.py --only chunks
    backend/.venv/bin/python scripts/export_to_supabase.py --verify   # counts only, no writes

Idempotent: every table is truncated (in dependency order) before it is refilled, so a rerun after a
failure is safe. Vectors come from LanceDB (data/memory/lancedb, table `chunks`), joined to the
SQLite `chunks` rows on chunk_id; a chunk with no vector is still uploaded, with embedding NULL.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
APP_DB = ROOT / "data" / "app.db"
SITE_DB = ROOT / "data" / "site.db"
LANCE_DIR = ROOT / "data" / "memory" / "lancedb"
BATCH = 500

# (sqlite db, sqlite table, postgres table, bool columns, json columns)
SPEC: list[tuple[str, str, str, tuple[str, ...], tuple[str, ...]]] = [
    ("app", "orgs", "vesper.orgs", (), ("profile_json",)),
    ("app", "org_members", "vesper.org_members", (), ()),
    ("app", "projects", "vesper.projects", (), ("profile_json",)),
    ("app", "project_members", "vesper.project_members", (), ()),
    ("app", "invites", "vesper.invites", (), ()),
    ("app", "activity", "vesper.activity", (), ()),
    ("app", "email_log", "vesper.email_log", (), ()),
    ("app", "documents", "vesper.documents", (), ("meta",)),
    ("app", "ingest_jobs", "vesper.ingest_jobs", (), ("payload",)),
    ("app", "chunks", "vesper.chunks", (), ("meta",)),
    ("site", "template_sources", "site.template_sources", (), ()),
    ("site", "templates", "site.templates", (), ()),
    ("site", "template_codes", "site.template_codes", (), ()),
    ("site", "template_fields", "site.template_fields", ("is_mandatory", "is_hold_point"), ()),
    ("site", "projects", "site.projects", (), ()),
    ("site", "locations", "site.locations", (), ("aliases",)),
    ("site", "boq_items", "site.boq_items", (), ()),
    ("site", "drawings", "site.drawings", ("is_latest",), ()),
    ("site", "drawing_facts", "site.drawing_facts", (), ()),
    ("site", "rfis", "site.rfis", (), ()),
    ("site", "submittals", "site.submittals", (), ()),
    ("site", "daily_logs", "site.daily_logs", (), ("manpower_json", "materials_json", "equipment_json")),
    ("site", "permits", "site.permits", (), ()),
    ("site", "permit_checks", "site.permit_checks", ("is_mandatory", "satisfied"), ()),
    ("site", "checklist_instances", "site.checklist_instances", ("hold_point_released",), ()),
    ("site", "checklist_items", "site.checklist_items", ("is_mandatory", "is_hold_point"), ()),
    ("site", "voice_sessions", "site.voice_sessions", (), ()),
    ("site", "voice_turns", "site.voice_turns", ("was_barge_in",), ("entities_json",)),
    ("site", "field_observations", "site.field_observations", ("contradiction_flag",), ("contradiction_kinds",)),
    ("site", "doc_chunks", "site.doc_chunks", (), ()),
    ("site", "user_usage", "site.user_usage", (), ()),
]

# site.db drawings.superseded_by is a self-reference; the app.db chunks->documents FK is respected by
# the order above. Truncate runs in reverse with CASCADE, so order only matters for the insert pass.
SKIP_COLUMNS = {"site.doc_chunks": {"embedding"}}  # legacy unused BLOB column


def sqlite_conn(which: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{APP_DB if which == 'app' else SITE_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_vectors() -> dict[str, list[float]]:
    import lancedb

    tbl = lancedb.connect(str(LANCE_DIR)).open_table("chunks")
    try:  # zero-copy scan when pylance is installed
        batches = tbl.to_lance().to_batches(columns=["chunk_id", "vector"])
    except ImportError:  # plain Arrow read — ~85 MB for 20.7k x 1024 float32, fine in memory
        batches = tbl.to_arrow().select(["chunk_id", "vector"]).to_batches()
    out: dict[str, list[float]] = {}
    for batch in batches:
        ids = batch.column("chunk_id").to_pylist()
        vecs = batch.column("vector").to_pylist()
        out.update(zip(ids, vecs))
    return out


def coerce(value, column: str, bools: tuple[str, ...], jsons: tuple[str, ...]):
    if value is None:
        return None
    if column in bools:
        return bool(value)
    if column in jsons:
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        text = str(value).strip()
        if not text:
            return None
        try:
            json.loads(text)
        except ValueError:
            return json.dumps(text)  # store the raw string as a JSON scalar rather than failing
        return text
    return value


def copy_table(pg: psycopg.Connection, spec, vectors: dict[str, list[float]] | None) -> int:
    which, src, dst, bools, jsons = spec
    with sqlite_conn(which) as lite:
        cols = [r[1] for r in lite.execute(f'PRAGMA table_info("{src}")')
                if r[1] not in SKIP_COLUMNS.get(dst, set())]
        rows = lite.execute(f'SELECT {", ".join(chr(34) + c + chr(34) for c in cols)} FROM "{src}"')

        out_cols = list(cols)
        if dst == "vesper.chunks":
            out_cols.append("embedding")
        placeholders = ", ".join(["%s"] * len(out_cols))
        stmt = f'INSERT INTO {dst} ({", ".join(out_cols)}) VALUES ({placeholders})'

        total, batch = 0, []
        with pg.cursor() as cur:
            while True:
                chunk = rows.fetchmany(BATCH)
                if not chunk:
                    break
                batch = []
                for row in chunk:
                    values = [coerce(row[c], c, bools, jsons) for c in cols]
                    if dst == "vesper.chunks":
                        vec = (vectors or {}).get(row["chunk_id"])
                        values.append("[" + ",".join(f"{v:.6g}" for v in vec) + "]" if vec else None)
                    batch.append(values)
                cur.executemany(stmt, batch)
                total += len(batch)
                print(f"  {dst}: {total}", end="\r", flush=True)
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="sqlite table names to move (default: all)")
    ap.add_argument("--verify", action="store_true", help="print row counts on both sides, write nothing")
    args = ap.parse_args()

    url = os.getenv("SUPABASE_DB_URL", "").strip()
    if not url:
        print("SUPABASE_DB_URL is not set (Supabase dashboard -> Project Settings -> Database).", file=sys.stderr)
        return 2

    specs = [s for s in SPEC if not args.only or s[1] in args.only]
    with psycopg.connect(url, autocommit=False) as pg:
        if args.verify:
            for which, src, dst, *_ in specs:
                with sqlite_conn(which) as lite:
                    local = lite.execute(f'SELECT COUNT(*) FROM "{src}"').fetchone()[0]
                remote = pg.execute(f"SELECT COUNT(*) FROM {dst}").fetchone()[0]
                flag = "ok " if local == remote else "DIFF"
                print(f"{flag} {dst:<28} local={local:<8} supabase={remote}")
            embedded = pg.execute("SELECT COUNT(*) FROM vesper.chunks WHERE embedding IS NOT NULL").fetchone()[0]
            print(f"     vectors in vesper.chunks: {embedded}")
            return 0

        for _, _, dst, *_ in reversed(specs):
            pg.execute(f"TRUNCATE {dst} CASCADE")

        vectors = None
        if any(s[2] == "vesper.chunks" for s in specs):
            print("loading vectors from LanceDB ...")
            vectors = load_vectors()
            print(f"  {len(vectors)} vectors")

        for spec in specs:
            print(f"copying {spec[1]} -> {spec[2]}")
            n = copy_table(pg, spec, vectors)
            print(f"  {spec[2]}: {n} rows        ")
        pg.commit()
    print("done. Re-run with --verify to compare counts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
