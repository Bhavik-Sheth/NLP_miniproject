"""Storage for the memory layer.

SQLite (data/app.db): documents, chunks, chunks_fts (FTS5, synced by triggers), ingest_jobs.
LanceDB (data/memory/lancedb): one `chunks` table of bge-m3 vectors carrying scope/org/project/
dataset metadata so every vector query is pre-filtered to the caller's datasets.

Write order per document (bd-agent): vectors first, chunk rows next, document row `done` last —
a crash leaves a document that is not `done`, and a retry deletes by doc_id before rewriting.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

import numpy as np

from . import config

_local = threading.local()
_write_lock = threading.RLock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ============================================================== SQLite
def _open() -> sqlite3.Connection:
    conn = None
    try:  # W2's shared helper, when it exists
        from tenancy.appdb import connect as appdb_connect  # type: ignore

        conn = appdb_connect()
    except Exception:  # noqa: BLE001
        conn = None
    if conn is None:
        path = config.app_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(config.SCHEMA_PATH.read_text())
    return conn


def db() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        c = _open()
        _local.conn = c
    return c


def _rows(sql: str, args: Iterable[Any] = ()) -> list[dict]:
    return [dict(r) for r in db().execute(sql, tuple(args)).fetchall()]


def _one(sql: str, args: Iterable[Any] = ()) -> dict | None:
    r = db().execute(sql, tuple(args)).fetchone()
    return dict(r) if r else None


def _in(values: list[str]) -> str:
    return ",".join("?" for _ in values) or "NULL"


# -------------------------------------------------------------- documents
def find_document(dataset: str, content_hash: str) -> dict | None:
    return _one("SELECT * FROM documents WHERE dataset = ? AND content_hash = ?", (dataset, content_hash))


def find_by_source_key(dataset: str, source_key: str) -> list[dict]:
    return _rows("SELECT * FROM documents WHERE dataset = ? AND source_key = ? ORDER BY version DESC",
                 (dataset, source_key))


def get_document(doc_id: str) -> dict | None:
    return _one("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))


_DOC_COLS = ["doc_id", "scope", "org_id", "project_id", "dataset", "source_key", "title", "category", "source",
             "url", "mime", "content_hash", "version", "status", "chunks", "graph_status", "added_by", "meta",
             "error", "created_at", "updated_at"]


def upsert_document(doc: dict) -> None:
    d = dict(doc)
    ts = now_iso()
    d.setdefault("created_at", ts)
    d["updated_at"] = ts
    d.setdefault("version", 1)
    d.setdefault("status", "queued")
    d.setdefault("chunks", 0)
    d.setdefault("graph_status", "skipped")
    if isinstance(d.get("meta"), (dict, list)):
        d["meta"] = json.dumps(d["meta"], ensure_ascii=False)
    cols = [c for c in _DOC_COLS if c in d]
    upd = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in ("doc_id", "created_at"))
    with _write_lock:
        db().execute(f"INSERT INTO documents ({', '.join(cols)}) VALUES ({_in(cols)}) "
                     f"ON CONFLICT(doc_id) DO UPDATE SET {upd}", [d[c] for c in cols])
        db().commit()


def update_document(doc_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = now_iso()
    sets = ", ".join(f"{k} = ?" for k in fields)
    with _write_lock:
        db().execute(f"UPDATE documents SET {sets} WHERE doc_id = ?", [*fields.values(), doc_id])
        db().commit()


def delete_document(doc_id: str) -> None:
    vectors_delete([doc_id])
    with _write_lock:
        db().execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        db().execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        db().commit()


def delete_document_rows(doc_id: str) -> None:
    """SQLite side only (vectors are deleted separately in bulk)."""
    with _write_lock:
        db().execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        db().execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        db().commit()


def replace_chunks(doc_id: str, rows: list[dict]) -> None:
    replace_chunks_many([doc_id], rows)


def replace_chunks_many(doc_ids: list[str], rows: list[dict]) -> None:
    cols = ["chunk_id", "doc_id", "n", "scope", "org_id", "project_id", "dataset", "title", "section", "page",
            "category", "source", "url", "kind", "text", "embed_text", "entities", "citation", "meta",
            "content_hash", "embedding_version", "chunking_version", "created_at"]
    ts = now_iso()
    data = []
    for r in rows:
        r = dict(r)
        r.setdefault("created_at", ts)
        if isinstance(r.get("meta"), (dict, list)):
            r["meta"] = json.dumps(r["meta"], ensure_ascii=False)
        data.append([r.get(c) for c in cols])
    with _write_lock:
        c = db()
        for i in range(0, len(doc_ids), 500):
            part = doc_ids[i:i + 500]
            c.execute(f"DELETE FROM chunks WHERE doc_id IN ({_in(part)})", part)
        c.executemany(f"INSERT INTO chunks ({', '.join(cols)}) VALUES ({_in(cols)})", data)
        c.commit()


def list_documents(datasets: list[str], limit: int = 500) -> list[dict]:
    return _rows(f"SELECT doc_id, title, category, source, url, dataset, scope, chunks, status, graph_status, "
                 f"version, created_at, updated_at FROM documents WHERE dataset IN ({_in(datasets)}) "
                 f"ORDER BY created_at DESC LIMIT ?", [*datasets, limit])


def dataset_stats(datasets: list[str]) -> list[dict]:
    return _rows(f"SELECT dataset, MIN(scope) AS scope, COUNT(*) AS documents, SUM(chunks) AS chunks, "
                 f"MAX(updated_at) AS lastIngested, SUM(graph_status = 'done') AS graphDocs "
                 f"FROM documents WHERE dataset IN ({_in(datasets)}) AND status IN ('done','graph') "
                 f"GROUP BY dataset", datasets)


# -------------------------------------------------------------- chunks
def chunks_by_ids(chunk_ids: list[str]) -> dict[str, dict]:
    if not chunk_ids:
        return {}
    out: dict[str, dict] = {}
    for i in range(0, len(chunk_ids), 500):
        part = chunk_ids[i:i + 500]
        for r in _rows(f"SELECT * FROM chunks WHERE chunk_id IN ({_in(part)})", part):
            out[r["chunk_id"]] = r
    return out


def neighbours(doc_id: str, n: int, radius: int = 1) -> list[dict]:
    return _rows("SELECT chunk_id, n, section, text FROM chunks WHERE doc_id = ? AND n BETWEEN ? AND ? "
                 "AND n != ? ORDER BY n", (doc_id, n - radius, n + radius, n))


def doc_chunks(doc_id: str) -> list[dict]:
    return _rows("SELECT * FROM chunks WHERE doc_id = ? ORDER BY n", (doc_id,))


def fts_search(match: str, datasets: list[str], k: int) -> list[dict]:
    """BM25 over text/title/section/entities. Column weights favour entity and title hits."""
    if not match or not datasets:
        return []
    sql = (f"SELECT c.chunk_id, bm25(chunks_fts, 1.0, 2.0, 1.5, 4.0) AS bm25 FROM chunks_fts "
           f"JOIN chunks c ON c.rid = chunks_fts.rowid WHERE chunks_fts MATCH ? "
           f"AND c.dataset IN ({_in(datasets)}) ORDER BY bm25 LIMIT ?")
    try:
        return _rows(sql, [match, *datasets, k])
    except sqlite3.OperationalError:
        return []


# -------------------------------------------------------------- jobs
def create_job(dataset: str, title: str, *, org_id: str | None, project_id: str | None, source: str,
               category: str | None = None, doc_id: str | None = None, payload: dict | None = None,
               status: str = "queued") -> str:
    job_id = "job_" + uuid.uuid4().hex[:16]
    ts = now_iso()
    with _write_lock:
        db().execute("INSERT INTO ingest_jobs (job_id, doc_id, org_id, project_id, dataset, title, source, category, "
                     "status, progress, payload, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (job_id, doc_id, org_id, project_id, dataset, title, source, category, status, 0.0,
                      json.dumps(payload or {}), ts, ts))
        db().commit()
    return job_id


def update_job(job_id: str | None, **fields: Any) -> None:
    if not job_id or not fields:
        return
    fields["updated_at"] = now_iso()
    sets = ", ".join(f"{k} = ?" for k in fields)
    with _write_lock:
        db().execute(f"UPDATE ingest_jobs SET {sets} WHERE job_id = ?", [*fields.values(), job_id])
        db().commit()


def get_job(job_id: str) -> dict | None:
    return _one("SELECT * FROM ingest_jobs WHERE job_id = ?", (job_id,))


def list_jobs(datasets: list[str], limit: int = 100) -> list[dict]:
    return _rows(f"SELECT job_id, doc_id, title, status, progress, error, dataset, category, source, created_at, "
                 f"updated_at FROM ingest_jobs WHERE dataset IN ({_in(datasets)}) ORDER BY created_at DESC LIMIT ?",
                 [*datasets, limit])


def pending_jobs(limit: int = 50) -> list[dict]:
    return _rows("SELECT * FROM ingest_jobs WHERE status IN ('queued','parsing','embedding') "
                 "ORDER BY created_at LIMIT ?", (limit,))


# ============================================================== LanceDB
_lance: dict[str, Any] = {"db": None, "tbl": None, "opened": 0.0}
_lance_lock = threading.RLock()


def _schema():
    import pyarrow as pa

    return pa.schema([
        ("chunk_id", pa.string()), ("doc_id", pa.string()), ("dataset", pa.string()), ("scope", pa.string()),
        ("org_id", pa.string()), ("project_id", pa.string()), ("category", pa.string()),
        ("vector", pa.list_(pa.float32(), config.EMBED_DIM)),
    ])


def _table(create: bool = True, fresh_after: float = 3.0):
    import lancedb

    with _lance_lock:
        if _lance["db"] is None:
            _lance["db"] = lancedb.connect(str(config.LANCEDB_DIR))
        if _lance["tbl"] is None or time.time() - _lance["opened"] > fresh_after:
            try:
                _lance["tbl"] = _lance["db"].open_table(config.LANCE_TABLE)
            except Exception:  # noqa: BLE001
                if not create:
                    return None
                _lance["tbl"] = _lance["db"].create_table(config.LANCE_TABLE, schema=_schema(), exist_ok=True)
            _lance["opened"] = time.time()
        return _lance["tbl"]


def _q(s: str | None) -> str:
    return "'" + str(s or "").replace("'", "''") + "'"


def vectors_delete(doc_ids: list[str]) -> None:
    if not doc_ids:
        return
    tbl = _table(create=False, fresh_after=0)
    if tbl is None:
        return
    with _lance_lock:
        for i in range(0, len(doc_ids), 200):
            tbl.delete(f"doc_id IN ({', '.join(_q(d) for d in doc_ids[i:i + 200])})")


def vectors_add(rows: list[dict], matrix: np.ndarray) -> None:
    import pyarrow as pa

    if not rows:
        return
    tbl = _table(create=True, fresh_after=0)
    cols = {k: [str(r.get(k) or "") for r in rows] for k in
            ("chunk_id", "doc_id", "dataset", "scope", "org_id", "project_id", "category")}
    flat = pa.array(matrix.astype(np.float32).reshape(-1), type=pa.float32())
    cols["vector"] = pa.FixedSizeListArray.from_arrays(flat, config.EMBED_DIM)
    batch = pa.table(cols, schema=_schema())
    with _lance_lock:
        tbl.add(batch)


def vector_search(vec: np.ndarray, datasets: list[str], k: int) -> list[dict]:
    tbl = _table(create=False)
    if tbl is None or not datasets:
        return []
    q = tbl.search(vec.astype(np.float32), vector_column_name="vector")
    try:
        q = q.distance_type("cosine")
    except AttributeError:
        q = q.metric("cosine")
    where = f"dataset IN ({', '.join(_q(d) for d in datasets)})"
    try:
        q = q.where(where, prefilter=True)
    except TypeError:
        q = q.where(where)
    rows = q.select(["chunk_id", "doc_id", "dataset", "_distance"]).limit(k).to_list()
    return [{"chunk_id": r["chunk_id"], "doc_id": r["doc_id"], "dataset": r["dataset"],
             "vector_score": 1.0 - float(r.get("_distance", 1.0))} for r in rows]


def vectors_optimize() -> None:
    tbl = _table(create=False, fresh_after=0)
    if tbl is not None:
        try:
            tbl.optimize()
        except Exception as e:  # noqa: BLE001
            print(f"[memory] lance optimize skipped: {e!r}"[:200])


def build_indexes(min_rows_for_ann: int = 5000) -> dict:
    """Scalar BITMAP index on dataset (pre-filter) + ANN (IVF_HNSW_SQ, cosine) once the table is big enough.
    Rows appended after the build are still searched (flat) until the next rebuild."""
    out: dict = {}
    tbl = _table(create=False, fresh_after=0)
    if tbl is None:
        return {"error": "no table"}
    n = int(tbl.count_rows())
    out["rows"] = n
    for col, kind in (("dataset", "BITMAP"), ("doc_id", "BTREE")):
        try:
            tbl.create_scalar_index(col, index_type=kind, replace=True)
            out[f"scalar_{col}"] = kind
        except Exception as e:  # noqa: BLE001
            out[f"scalar_{col}"] = repr(e)[:160]
    if n >= min_rows_for_ann:
        t0 = time.time()
        try:
            tbl.create_index(metric="cosine", vector_column_name="vector", index_type="IVF_HNSW_SQ",
                             num_partitions=max(1, int(n ** 0.5 / 4)), replace=True)
            out["ann"] = f"IVF_HNSW_SQ in {time.time() - t0:.1f}s"
        except Exception as e:  # noqa: BLE001
            out["ann"] = repr(e)[:200]
    vectors_optimize()
    return out


def vector_count() -> int:
    tbl = _table(create=False)
    try:
        return int(tbl.count_rows()) if tbl is not None else 0
    except Exception:  # noqa: BLE001
        return 0
