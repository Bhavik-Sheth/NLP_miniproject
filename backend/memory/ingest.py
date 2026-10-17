"""Ingestion pipeline: parse -> chunk -> embed -> index (LanceDB + FTS5) -> graph (Cognee, background).

Job status: queued -> parsing -> embedding -> graph -> done | error. Idempotent: a document whose
(dataset, sha256) is already `done` is skipped; a new version of the same `source_key` replaces the old one.
Small uploads are indexed synchronously (searchable when the HTTP call returns); the knowledge graph is
always built in the background by `memory/cognee_worker.py` (own venv, bounded, resumable).
"""
from __future__ import annotations

import fcntl
import json
import os
import queue
import re
import subprocess
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from . import chunkers, config, embed, store
from .chunkers import Chunk

EMBED_CHARS = int(os.getenv("MEMORY_EMBED_CHARS", "900"))
SYNC_MAX_BYTES = int(os.getenv("MEMORY_SYNC_MAX_BYTES", str(3_000_000)))
_log_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"{store.now_iso()} {msg}"
    with _log_lock:
        with open(config.INGEST_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")


@dataclass
class DocSpec:
    dataset: str
    title: str
    chunks: list[Chunk]
    content_hash: str
    org_id: str | None = None
    project_id: str | None = None
    category: str | None = None
    source: str | None = None
    url: str | None = None
    source_key: str | None = None
    mime: str | None = None
    added_by: str | None = None
    meta: dict = field(default_factory=dict)
    graph: bool | None = None          # None -> project datasets yes, global no


def scope_of(dataset: str) -> str:
    return "global" if dataset in config.GLOBAL_DATASETS else "project"


def graph_eligible(s: DocSpec) -> bool:
    if s.dataset in config.TABULAR_DATASETS:
        return False
    return bool(s.graph) if s.graph is not None else scope_of(s.dataset) == "project"


def _rows_for(s: DocSpec, doc_id: str) -> list[dict]:
    rows: list[dict] = []
    scope = scope_of(s.dataset)
    for c in s.chunks:
        text = (c.text or "").strip()
        if len(text) < 8:
            continue
        section = c.section or ""
        n = len(rows)
        rows.append({
            "chunk_id": f"{doc_id}:{n}", "doc_id": doc_id, "n": n, "scope": scope, "org_id": s.org_id,
            "project_id": s.project_id, "dataset": s.dataset, "title": s.title, "section": section,
            "page": c.page, "category": s.category, "source": s.source, "url": s.url, "kind": c.kind,
            "text": text, "embed_text": (c.embed_text or f"{s.title}\n{section}\n{text}")[:EMBED_CHARS],
            "entities": chunkers.entity_string(f"{s.title}\n{section}\n{text}"),
            "citation": c.citation or f"per {s.title}", "meta": c.meta or None,
            "content_hash": chunkers.sha256_text(text), "embedding_version": config.EMBEDDING_VERSION,
            "chunking_version": config.CHUNKING_VERSION,
        })
    return rows


def ingest_docs(specs: list[DocSpec], *, force: bool = False) -> list[dict]:
    """Index many documents with one embedding pass and one LanceDB append (fast bulk path)."""
    results: list[dict] = []
    work = []
    seen_keys: set[tuple[str, str]] = set()
    for s in specs:
        if (s.dataset, s.content_hash) in seen_keys:  # identical pages in one batch -> same doc id; index once
            results.append({"docId": chunkers.doc_id_for(s.dataset, s.content_hash), "status": "skipped",
                            "chunks": 0, "title": s.title})
            continue
        seen_keys.add((s.dataset, s.content_hash))
        ex = store.find_document(s.dataset, s.content_hash)
        if ex and ex["status"] == "done" and not force:
            results.append({"docId": ex["doc_id"], "status": "skipped", "chunks": ex["chunks"], "title": ex["title"]})
            continue
        doc_id = chunkers.doc_id_for(s.dataset, s.content_hash)
        olds = [d for d in store.find_by_source_key(s.dataset, s.source_key) if d["doc_id"] != doc_id] \
            if s.source_key else []
        version = max([d["version"] for d in olds] or [0]) + 1
        work.append((s, doc_id, olds, version, _rows_for(s, doc_id)))
    if not work:
        return results
    for s, doc_id, _olds, version, _rows in work:
        store.upsert_document({
            "doc_id": doc_id, "scope": scope_of(s.dataset), "org_id": s.org_id, "project_id": s.project_id,
            "dataset": s.dataset, "source_key": s.source_key, "title": s.title[:300], "category": s.category,
            "source": s.source, "url": s.url, "mime": s.mime, "content_hash": s.content_hash, "version": version,
            "status": "embedding", "chunks": 0, "graph_status": "skipped", "added_by": s.added_by,
            "meta": s.meta or None, "error": None})
    all_rows = [r for w in work for r in w[4]]
    try:
        matrix = embed.embed_texts([r["embed_text"] for r in all_rows], batch_size=64)
        store.vectors_delete([w[1] for w in work] + [o["doc_id"] for w in work for o in w[2]])
        store.vectors_add(all_rows, matrix)
        store.replace_chunks_many([w[1] for w in work], all_rows)
    except Exception as e:  # noqa: BLE001
        for w in work:
            store.update_document(w[1], status="error", error=repr(e)[:300])
        raise
    for s, doc_id, olds, _version, rows in work:
        for o in olds:
            store.delete_document_rows(o["doc_id"])
        store.update_document(doc_id, status="done", chunks=len(rows),
                              graph_status="pending" if graph_eligible(s) and rows else "skipped")
        results.append({"docId": doc_id, "status": "done", "chunks": len(rows), "title": s.title})
    return results


# ============================================================== project profile -> prime memory
_schema_cache: dict | None = None


def _onboarding_schema() -> dict:
    global _schema_cache
    if _schema_cache is None:
        try:
            _schema_cache = json.loads((config.DATA_DIR / "onboarding_schema.json").read_text())
        except Exception:  # noqa: BLE001
            _schema_cache = {}
    return _schema_cache


def _humanize(key: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", key).replace("_", " ").strip().capitalize()


def _fmt(v, field_def: dict | None = None) -> str:
    opts = {str(o.get("value")): o.get("label") for o in (field_def or {}).get("options", []) or [] if isinstance(o, dict)}
    subs = {f["key"]: f for f in (field_def or {}).get("fields", []) or [] if isinstance(f, dict) and "key" in f}
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, dict):
        if {"lat", "lng"} <= set(v):
            return f"{v['lat']}, {v['lng']}"
        if "name" in v and ("docId" in v or "url" in v):
            return str(v["name"])
        return "; ".join(f"{(subs.get(k) or {}).get('label') or _humanize(k)}: {_fmt(x, subs.get(k))}"
                         for k, x in v.items() if x not in (None, "", [], {}))
    if isinstance(v, list):
        if v and all(isinstance(x, dict) for x in v):
            return "\n" + "\n".join(f"  - {_fmt(x, field_def)}" for x in v)
        return ", ".join(str(opts.get(str(x), x)) for x in v)
    return str(opts.get(str(v), v))


_ROLE_WORDS = {"structural": "Structural consultant", "architect": "Architect", "mep": "MEP consultant",
               "pmc": "PMC", "client": "Client", "contractor": "Contractor", "subcontractor": "Subcontractor",
               "geotech": "Geotechnical consultant", "testing_lab": "Testing laboratory", "supplier": "Supplier",
               "surveyor": "Surveyor", "safety": "Safety officer", "qa_qc": "QA/QC engineer"}


def _repeater_lines(field_def: dict, items: list) -> list[str]:
    """One explicit, role-labelled line per repeater row:
    'Structural consultant: Sthapatya Structural Engineers — Dr. V. N. Rao, +91…, scope: RCC design'."""
    subs = {f["key"]: f for f in field_def.get("fields", []) or [] if isinstance(f, dict) and "key" in f}
    group = field_def.get("label") or _humanize(field_def.get("key", "Item"))
    out = []
    for it in items:
        if not isinstance(it, dict):
            out.append(f"{group}: {_fmt(it)}")
            continue
        role_v = it.get("role") or it.get("element") or it.get("name")
        role_def = subs.get("role") or subs.get("element") or {}
        opts = {str(o.get("value")): o.get("label") for o in role_def.get("options", []) or [] if isinstance(o, dict)}
        role = opts.get(str(role_v)) or _ROLE_WORDS.get(str(role_v)) or (_humanize(str(role_v)) if role_v else group)
        main = [str(it[k]) for k in ("company", "name", "person") if it.get(k) and str(it[k]) != str(role_v)]
        rest = [f"{(subs.get(k) or {}).get('label') or _humanize(k)}: {_fmt(v, subs.get(k))}" for k, v in it.items()
                if k not in ("role", "company", "name", "person") and v not in (None, "", [], {})
                and not (k == "element" and v == role_v)]
        line = f"{role}: " + " — ".join(main) if main else f"{role}"
        if rest:
            line += (", " if main else ": ") + ", ".join(rest)
        out.append(f"{line} ({group.lower()})")
    return out


def profile_chunks(profile: dict, scope_key: str = "project") -> tuple[str, list[Chunk]]:
    """Project onboarding answers -> small, explicit fact-sheet passages (<= ~5 lines each) so a spoken
    question ('who is the structural consultant?') lands on a short passage the reranker reads in full."""
    sch = _onboarding_schema().get(scope_key) or {}
    steps = sch.get("steps") or []
    seen: set[str] = set()
    name = profile.get("name") or profile.get("code") or "Project"
    title = f"Project fact sheet — {name}"
    chunks: list[Chunk] = []

    def add(sec: str, lines: list[str], step: str | None, per: int = 5):
        for i in range(0, len(lines), per):
            part = lines[i:i + per]
            chunks.append(Chunk(text=f"{name} ({profile.get('code') or ''}) — {sec}\n" + "\n".join(part),
                                section=sec, kind="profile", citation="per the project profile",
                                meta={"step": step}))

    fdefs = {f["key"]: f for st in steps for f in st.get("fields", []) or [] if "key" in f}
    for st in steps:
        sec = st.get("title") or _humanize(st.get("id", "Details"))
        lines = []
        for f in st.get("fields", []) or []:
            k = f.get("key")
            if not k or k not in profile or profile[k] in (None, "", [], {}):
                continue
            seen.add(k)
            v = profile[k]
            if f.get("type") == "repeater" and isinstance(v, list):
                add(f"{sec} — {f.get('label') or _humanize(k)}", _repeater_lines(f, v), st.get("id"), per=4)
                continue
            lines.append(f"{f.get('label') or _humanize(k)} ({_humanize(k).lower()}): {_fmt(v, f)}")
        if lines:
            add(sec, lines, st.get("id"))
    rest = []
    for k, v in profile.items():
        if k in seen or v in (None, "", [], {}):
            continue
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            add(_humanize(k), _repeater_lines({"key": k, "label": _humanize(k)}, v), None, per=4)
        else:
            rest.append(f"{_humanize(k)}: {_fmt(v)}")
    if rest:
        add("Other details", rest, None)
    # a compact identity passage so "which project / client / codes / site lead" questions hit one short chunk
    ident_keys = ["name", "code", "projectType", "city", "clientName", "contractType", "startDate",
                  "currentPhase", "siteLeadName", "governingCodes"]
    ident = [f"{(fdefs.get(k) or {}).get('label') or _humanize(k)} ({_humanize(k).lower()}): "
             f"{_fmt(profile[k], fdefs.get(k))}" for k in ident_keys if profile.get(k) not in (None, "", [], {})]
    if ident:
        chunks.insert(0, Chunk(text=f"PROJECT FACT SHEET — {name}\n" + "\n".join(ident), section="Summary",
                               kind="profile", citation="per the project profile"))
    return title, chunks


# ============================================================== jobs + background worker
_q: queue.Queue[str] = queue.Queue()
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()


def _ensure_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run_worker, name="memory-ingest", daemon=True)
            _worker.start()


def _run_worker() -> None:
    while True:
        job_id = _q.get()
        try:
            process_job(job_id)
        except Exception as e:  # noqa: BLE001
            store.update_job(job_id, status="error", error=repr(e)[:300])
            log(f"job {job_id} error {e!r}\n{traceback.format_exc()[-800:]}")


def enqueue(job_id: str) -> None:
    _ensure_worker()
    _q.put(job_id)


def resume_pending() -> int:
    jobs = store.pending_jobs(200)
    for j in jobs:
        enqueue(j["job_id"])
    return len(jobs)


def process_job(job_id: str) -> dict:
    j = store.get_job(job_id)
    if not j:
        raise ValueError("unknown job")
    if j["status"] in ("done", "graph"):
        return {"jobId": job_id, "docId": j["doc_id"], "status": j["status"]}
    p = json.loads(j.get("payload") or "{}")
    store.update_job(job_id, status="parsing", progress=0.15)
    title = j["title"] or "Untitled"
    kind = p.get("kind")
    mime = None
    if kind == "file":
        data = Path(p["path"]).read_bytes()
        blocks = chunkers.parse_any(p["filename"], data)
        chunks = chunkers.blocks_to_chunks(blocks, title)
        chash, mime, source_key = p["hash"], p.get("mime"), p["filename"]
    elif kind == "text":
        chunks = chunkers.split_text_chunks(p["text"], title, kind="text")
        chash, source_key = p["hash"], p.get("source_key")
    elif kind == "profile":
        title, chunks = profile_chunks(p["profile"])
        chash, source_key = p["hash"], "project_profile"
    else:
        raise ValueError(f"unknown job kind {kind}")
    if not chunks:
        store.update_job(job_id, status="error", progress=1.0, error="no text could be extracted")
        return {"jobId": job_id, "status": "error"}
    store.update_job(job_id, status="embedding", progress=0.45)
    spec = DocSpec(dataset=j["dataset"], title=title, chunks=chunks, content_hash=chash, org_id=j["org_id"],
                   project_id=j["project_id"], category=j["category"], source=j["source"], mime=mime,
                   source_key=source_key, added_by=p.get("added_by"), meta={"jobId": job_id})
    res = ingest_docs([spec])[0]
    doc = store.get_document(res["docId"]) or {}
    graph_wait = doc.get("graph_status") == "pending" and config.COGNEE_ENABLED
    store.update_job(job_id, doc_id=res["docId"], status="graph" if graph_wait else "done",
                     progress=0.9 if graph_wait else 1.0)
    log(f"job {job_id} {j['dataset']} '{title}' -> {res['status']} {res['chunks']} chunks")
    if graph_wait:
        ensure_cognee_worker()
    _notify(j, p, res)
    return {"jobId": job_id, "docId": res["docId"], "status": "graph" if graph_wait else "done",
            "chunks": res["chunks"]}


def _notify(job: dict, payload: dict, res: dict) -> None:
    to = payload.get("email")
    if not to:
        return

    def send():
        try:
            from emails.send import send_email  # type: ignore

            name = job.get("project_id") or ""
            try:
                row = store.db().execute("SELECT name FROM projects WHERE id = ?", (job.get("project_id"),)).fetchone()
                name = row["name"] if row else name
            except Exception:  # noqa: BLE001
                pass
            send_email(to, "ingest_complete", {
                "PROJECT_NAME": name, "DOCUMENT_TITLE": res.get("title") or job.get("title"),
                "CHUNKS": res.get("chunks", 0), "STATUS": "indexed",
                "PROJECT_URL": f"{os.getenv('APP_URL', 'http://localhost:3000')}/app/projects/{job.get('project_id')}"},
                f"ingest/{job['job_id']}")
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=send, daemon=True).start()


# ============================================================== Cognee worker process
_last_spawn = 0.0


def cognee_worker_running() -> bool:
    try:
        fd = os.open(config.COGNEE_LOCK, os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        except OSError:
            return True
        finally:
            os.close(fd)
    except OSError:
        return False


def ensure_cognee_worker(max_docs: int | None = None) -> bool:
    global _last_spawn
    if not config.COGNEE_ENABLED:
        return False
    if cognee_worker_running():
        return True
    if time.time() - _last_spawn < 10:
        return True
    _last_spawn = time.time()
    args = [str(config.COGNEE_PYTHON), str(Path(__file__).with_name("cognee_worker.py"))]
    if max_docs:
        args += ["--max-docs", str(max_docs)]
    logf = open(config.COGNEE_LOG, "a")  # noqa: SIM115
    subprocess.Popen(args, cwd=str(config.BACKEND_DIR), stdout=logf, stderr=subprocess.STDOUT,
                     start_new_session=True)
    return True
