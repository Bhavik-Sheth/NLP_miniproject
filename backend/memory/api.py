"""Public surface of the memory layer — used by routes/memory.py, routes/ingest.py, tenancy (W2) and the engine.

Scope isolation: a project search reads exactly its own dataset `org_<org>__proj_<project>` plus the
global datasets. The caller (route) resolves org_id from the verified project row, never from the body.
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from datetime import datetime, timezone

import httpx

from . import answer as answer_mod
from . import chunkers, config, embed, ingest, rerank, retrieve, store

_sessions: dict[str, deque] = {}
_sess_lock = threading.Lock()


def datasets_for(org_id: str | None, project_id: str | None, scopes: list[str] | None = None) -> list[str]:
    scopes = scopes or ["global", "project"]
    ds: list[str] = []
    if "project" in scopes and project_id:
        ds.append(config.project_dataset(org_id, project_id))
    if "global" in scopes:
        ds += config.GLOBAL_DATASETS
    return ds


def _history(org_id, project_id, session_id) -> tuple[str | None, list[dict]]:
    if not session_id:
        return None, []
    key = f"{org_id}:{project_id}:{session_id}"
    with _sess_lock:
        return key, list(_sessions.get(key, []))


def _remember(key: str | None, query: str, rewritten: str) -> None:
    if not key:
        return
    with _sess_lock:
        d = _sessions.setdefault(key, deque(maxlen=6))
        d.append({"query": query, "rewritten": rewritten, "at": time.time()})
        if len(_sessions) > 5000:
            _sessions.pop(next(iter(_sessions)))


# a site-record NOUN is required ("today" / "open" alone must not pull live status into "today's bitcoin price")
_STATUS_RX = __import__("re").compile(
    r"\b(permits?|hold[ -]?points?|rfis?|blockers?|blocking|blocked|pour(?:ing)?|stop work|checks? before|"
    r"what should i check|site status|submittals?)\b", __import__("re").I)


def _live_site_hit(org_id: str | None, project_id: str | None, query: str) -> dict | None:
    """An operational site record is live in site.db: status questions get a
    passage built by the deterministic engine at query time instead of a stale indexed snapshot."""
    if not project_id or (org_id and org_id != config.DEMO_ORG) or not _STATUS_RX.search(query or ""):
        return None
    try:
        import db as dbmod  # backend/db.py (site.db)
        from engine import answer as eng

        conn = dbmod.connect()
        repo = dbmod.Repo(conn, project_id)
        if not repo._one("SELECT 1 FROM projects WHERE project_id = ?", (project_id,)):
            conn.close()
            return None
        q = (query or "").lower()
        labels = {"permit": "PERMITS", "hold": "HOLD POINTS", "rfi": "OPEN RFIs", "blockers": "ALL BLOCKERS"}
        sections = {k: eng._topic_answer(repo, k) for k in labels}  # noqa: SLF001
        focus = {"permit": "permit" in q, "hold": any(w in q for w in ("hold", "pour", "check")), "rfi": "rfi" in q,
                 "blockers": "block" in q}
        # the section the question is about comes first, so the answer leads with it
        order = sorted(labels, key=lambda k: (0 if focus[k] else 1, list(labels).index(k)))
        text = "\n".join(f"{labels[k]}: {sections[k]}" for k in order if sections.get(k))
        conn.close()
    except Exception as e:  # noqa: BLE001
        print(f"[memory] live site status unavailable: {e!r}"[:200])
        return None
    if not text:
        return None
    return {"chunkId": "live:site-status", "docId": "live:site-status", "title": "Live site status (site record)",
            "section": "Blockers, permits, hold points, open RFIs", "source": "site.db", "url": None,
            "category": "site_status", "dataset": config.project_dataset(config.DEMO_ORG, project_id),
            "scope": "project", "kind": "record", "text": text, "vectorScore": None, "bm25Rank": None,
            "rrfScore": None, "rerankScore": None, "citation": "per the live site record"}


def _with_live(res: dict, org_id, project_id, query) -> dict:
    live = _live_site_hit(org_id, project_id, query)
    if live:
        res["hits"] = [live] + [h for h in res["hits"]][:max(0, config.KEEP_K - 1)]
        if res.get("abstain") and not str(res.get("abstainReason") or "").startswith("entity_missing"):
            res["abstain"], res["abstainReason"] = False, None
            res["confidence"] = max(float(res.get("confidence") or 0), 0.6)
        res["liveRecord"] = True
    return res


def search(query: str, *, org_id: str | None, project_id: str | None = None, scopes: list[str] | None = None,
           k: int = 8, session_id: str | None = None, rerank_mode: str = "auto") -> dict:
    key, hist = _history(org_id, project_id, session_id)
    res = retrieve.search(query, datasets_for(org_id, project_id, scopes), k=min(max(int(k or 8), 1), 20),
                          history=hist, rerank_mode=rerank_mode)
    _remember(key, query, res["rewrittenQuery"])
    return _with_live(res, org_id, project_id, query) if "project" in (scopes or ["project"]) else res


def ask(query: str, *, org_id: str | None, project_id: str | None, session_id: str | None = None,
        scopes: list[str] | None = None) -> dict:
    t0 = time.perf_counter()
    key, hist = _history(org_id, project_id, session_id)
    ret = retrieve.search(query, datasets_for(org_id, project_id, scopes), k=config.KEEP_K, history=hist,
                          allow_llm_rewrite=True)
    _remember(key, query, ret["rewrittenQuery"])
    if "project" in (scopes or ["project"]):
        ret = _with_live(ret, org_id, project_id, query)
    ans = answer_mod.answer(query, ret)
    timings = dict(ret.get("timings") or {})
    timings["llm_ms"] = round(ans.get("llm_ms") or 0.0, 1)
    timings["ask_total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    timings_ms = dict(ret.get("timingsMs") or {})
    timings_ms["llm"] = timings["llm_ms"]
    timings_ms["total"] = timings["ask_total_ms"]
    return {"answer": ans["answer"], "speech": ans["speech"], "abstain": ans["abstain"],
            "abstainReason": ret.get("abstainReason") if ans["abstain"] else None,
            "confidence": 0.0 if ans["abstain"] else ret.get("confidence"),
            "citations": ans["citations"], "rewrittenQuery": ret["rewrittenQuery"], "provider": ans.get("provider"),
            "hits": ret["hits"], "timingsMs": timings_ms, "timings": timings}


# ============================================================== stats / documents / graph
_graph_cache: dict = {"mtime": 0.0, "data": None}


def _snapshot() -> dict | None:
    p = config.GRAPH_SNAPSHOT_DIR / "graph.json"
    if not p.exists():
        return None
    m = p.stat().st_mtime
    if _graph_cache["mtime"] != m:
        try:
            _graph_cache.update(mtime=m, data=json.loads(p.read_text()))
        except Exception:  # noqa: BLE001
            return _graph_cache["data"]
    return _graph_cache["data"]


def _snapshot_subgraph(datasets: list[str]) -> tuple[list[dict], list[dict]]:
    snap = _snapshot()
    if not snap:
        return [], []
    ids: set = set()
    for ds in datasets:
        ids |= set(snap.get("datasets", {}).get(ds, []))
    nodes = [n for n in snap["nodes"] if n["id"] in ids]
    edges = [e for e in snap["edges"] if e["source"] in ids and e["target"] in ids]
    return nodes, edges


def stats(*, org_id: str | None, project_id: str | None = None) -> dict:
    ds = datasets_for(org_id, project_id)
    rows = {r["dataset"]: r for r in store.dataset_stats(ds)}
    corpora = []
    for d in ds:
        r = rows.get(d) or {}
        corpora.append({"scope": "project" if d.startswith("org_") else "global", "name": d,
                        "documents": r.get("documents") or 0, "chunks": r.get("chunks") or 0,
                        "graphDocuments": r.get("graphDocs") or 0, "lastIngested": r.get("lastIngested")})
    nodes, edges = _snapshot_subgraph(ds)
    return {"corpora": corpora, "graph": {"nodes": len(nodes), "edges": len(edges)},
            "models": {"embedding": f"{config.EMBED_MODEL} (Ollama, {config.EMBED_DIM}d)",
                       "reranker": config.RERANK_MODEL, "llm": f"groq:{config.LLM_MODEL} -> cerebras:{config.CEREBRAS_MODEL}",
                       "vectorStore": "LanceDB (data/memory/lancedb)", "graphStore": "Cognee + Kuzu/Ladybug (data/memory/cognee)",
                       "keywordIndex": "SQLite FTS5 BM25 (data/app.db)"},
            "vectors": store.vector_count(), "reranker": rerank.status(), "abstainThreshold": config.ABSTAIN_THRESHOLD}


def documents(*, org_id: str | None, project_id: str) -> list[dict]:
    ds = [config.project_dataset(org_id, project_id)]
    return [{"docId": r["doc_id"], "title": r["title"], "category": r["category"], "source": r["source"],
             "url": r.get("url"), "chunks": r["chunks"], "status": r["status"], "graphStatus": r["graph_status"],
             "version": r["version"], "createdAt": r["created_at"]} for r in store.list_documents(ds)]


def jobs(*, org_id: str | None, project_id: str) -> list[dict]:
    ds = [config.project_dataset(org_id, project_id)]
    return [{"jobId": j["job_id"], "docId": j["doc_id"], "title": j["title"], "status": j["status"],
             "progress": j["progress"], "error": j["error"], "category": j["category"], "source": j["source"],
             "createdAt": j["created_at"], "updatedAt": j["updated_at"]} for j in store.list_jobs(ds)]


_ENT_TYPE = [("rfi", r"^RFI\d+$"), ("template", r"^(QC|PMC|FMT)[A-Z]+\d{3}$"), ("permit", r"^(HWP|WAH|EXC|ELP|LFT|CSP|PTW)\d+$"),
             ("checklist", r"^CL[A-Z0-9]+$"), ("code", r"^(IS|IRC|SP|NBC)\d+$"), ("clause", r"^CL\d+$"),
             ("drawing", r"^[A-Z]\d{3}$"), ("grid", r"^[A-H]\d{1,2}$"), ("grade", r"^(M|Fe)\d+$"), ("level", r"^L\d+$")]


def _etype(tok: str) -> str:
    import re

    for t, rx in _ENT_TYPE:
        if re.match(rx, tok):
            return t
    return "entity"


def graph(*, org_id: str | None, project_id: str | None = None, q: str | None = None, limit: int = 150) -> dict:
    """Cognee graph snapshot for the caller's datasets; falls back to an entity co-mention graph
    (document -> RFI / drawing / grid / code / clause ids) built from the chunk index."""
    limit = max(10, min(int(limit or 150), 600))
    ds = datasets_for(org_id, project_id)
    nodes, edges = _snapshot_subgraph(ds)
    source = "cognee"
    if q and nodes:
        ql = q.lower()
        seed = {n["id"] for n in nodes if ql in (n["label"] or "").lower()}
        keep = set(seed)
        for e in edges:
            if e["source"] in seed or e["target"] in seed:
                keep |= {e["source"], e["target"]}
        nodes = [n for n in nodes if n["id"] in keep]
        edges = [e for e in edges if e["source"] in keep and e["target"] in keep]
    if not nodes:
        source = "entities"
        if q:
            res = store.fts_search(retrieve.fts_match(chunkers.normalize_query_ids(q)), ds, 60)
            by_id = store.chunks_by_ids([r["chunk_id"] for r in res])
            rows = [by_id[r["chunk_id"]] for r in res if r["chunk_id"] in by_id]
        else:
            pds = [d for d in ds if d.startswith("org_")] or ds
            rows = store._rows(  # noqa: SLF001
                f"SELECT doc_id, title, category, entities FROM chunks WHERE dataset IN ({','.join('?' for _ in pds)}) "
                f"AND entities != '' LIMIT 400", pds)
        nmap: dict[str, dict] = {}
        eset: set = set()
        for r in rows:
            did = f"doc:{r['doc_id']}"
            nmap.setdefault(did, {"id": did, "label": (r.get("title") or "")[:80], "type": r.get("category") or "document"})
            for tok in (r.get("entities") or "").split():
                if _etype(tok) in ("grade", "level"):
                    continue
                eid = f"ent:{tok}"
                nmap.setdefault(eid, {"id": eid, "label": tok, "type": _etype(tok)})
                eset.add((did, eid))
            if len(nmap) > limit * 2:
                break
        nodes = list(nmap.values())
        edges = [{"source": a, "target": b, "label": "mentions"} for a, b in eset]
    if len(nodes) > limit:
        deg: dict[str, int] = {}
        for e in edges:
            deg[e["source"]] = deg.get(e["source"], 0) + 1
            deg[e["target"]] = deg.get(e["target"], 0) + 1
        nodes = sorted(nodes, key=lambda n: -deg.get(n["id"], 0))[:limit]
        ids = {n["id"] for n in nodes}
        edges = [e for e in edges if e["source"] in ids and e["target"] in ids]
    return {"nodes": nodes, "edges": edges, "source": source}


# ============================================================== ingestion entry points
def _job_payload_file(org_id, project_id, filename, data, category, added_by, email) -> tuple[str, str, dict]:
    ds = config.project_dataset(org_id, project_id)
    digest = chunkers.sha256_bytes(data)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    dest = config.UPLOAD_DIR / ds / f"{digest}.{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(data)
    return ds, digest, {"kind": "file", "path": str(dest), "filename": filename, "hash": digest, "added_by": added_by,
                        "email": email, "size": len(data)}


def _finish(job_id: str, ds: str, digest: str, sync: bool) -> dict:
    doc_id = chunkers.doc_id_for(ds, digest)
    if sync:
        try:
            out = ingest.process_job(job_id)
            return {"jobId": job_id, "docId": out.get("docId") or doc_id, "status": out["status"],
                    "chunks": out.get("chunks")}
        except Exception as e:  # noqa: BLE001
            store.update_job(job_id, status="error", error=repr(e)[:300])
            return {"jobId": job_id, "docId": doc_id, "status": "error", "error": repr(e)[:200]}
    ingest.enqueue(job_id)
    return {"jobId": job_id, "docId": doc_id, "status": "queued"}


SUPPORTED = {"pdf", "docx", "xlsx", "xlsm", "xls", "csv", "tsv", "txt", "md", "markdown", "html", "htm", "json"}


def ingest_file(*, org_id: str | None, project_id: str, filename: str, data: bytes, category: str | None = None,
                added_by: str | None = None, email: str | None = None, sync: bool | None = None) -> dict:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED:
        raise ValueError(f"unsupported file type .{ext or '?'} (images need OCR, which is not installed)")
    ds, digest, payload = _job_payload_file(org_id, project_id, filename, data, category, added_by, email)
    existing = store.find_document(ds, digest)
    if existing and existing["status"] == "done":
        return {"jobId": None, "docId": existing["doc_id"], "status": "done", "duplicate": True,
                "chunks": existing["chunks"]}
    job_id = store.create_job(ds, filename, org_id=org_id, project_id=project_id, source="upload",
                              category=category or "other", payload=payload)
    return _finish(job_id, ds, digest, len(data) <= ingest.SYNC_MAX_BYTES if sync is None else sync)


def ingest_text(*, org_id: str | None, project_id: str, title: str, text: str, category: str | None = None,
                added_by: str | None = None, email: str | None = None, source: str = "text",
                sync: bool | None = None) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("text is empty")
    ds = config.project_dataset(org_id, project_id)
    digest = chunkers.sha256_text(f"{title}\n{text}")
    existing = store.find_document(ds, digest)
    if existing and existing["status"] == "done":
        return {"jobId": None, "docId": existing["doc_id"], "status": "done", "duplicate": True,
                "chunks": existing["chunks"]}
    job_id = store.create_job(ds, title or "Note", org_id=org_id, project_id=project_id, source=source,
                              category=category or "note",
                              payload={"kind": "text", "text": text, "hash": digest, "added_by": added_by, "email": email})
    return _finish(job_id, ds, digest, len(text) <= 400_000 if sync is None else sync)


def ingest_project_profile(org_id: str | None, project_id: str, profile: dict, email: str | None = None) -> dict:
    """Called by W2 inside POST /api/projects: enqueue and return immediately; indexing takes ~1 s."""
    ds = config.project_dataset(org_id, project_id)
    digest = chunkers.sha256_text(json.dumps(profile or {}, sort_keys=True, default=str))
    existing = store.find_document(ds, digest)
    if existing and existing["status"] == "done":
        return {"status": "done", "jobId": None, "docId": existing["doc_id"], "dataset": ds, "duplicate": True}
    job_id = store.create_job(ds, f"Project fact sheet — {(profile or {}).get('name') or project_id}", org_id=org_id,
                              project_id=project_id, source="onboarding", category="project_profile",
                              payload={"kind": "profile", "profile": profile or {}, "hash": digest, "email": email})
    ingest.enqueue(job_id)
    return {"status": "queued", "jobId": job_id, "docId": chunkers.doc_id_for(ds, digest), "dataset": ds}


def transcribe_sarvam(audio: bytes, filename: str, content_type: str | None = None,
                      language_code: str = "unknown") -> dict:
    if not config.SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is not configured")
    r = httpx.post(config.SARVAM_STT_URL, headers={"api-subscription-key": config.SARVAM_API_KEY},
                   files={"file": (filename or "note.webm", audio, content_type or "application/octet-stream")},
                   data={"model": config.SARVAM_STT_MODEL, "mode": "transcribe", "language_code": language_code},
                   timeout=90.0)
    if r.status_code != 200:
        raise RuntimeError(f"Sarvam STT HTTP {r.status_code}: {r.text[:200]}")
    j = r.json()
    return {"transcript": (j.get("transcript") or "").strip(), "languageCode": j.get("language_code"),
            "requestId": j.get("request_id")}


def ingest_voice(*, org_id: str | None, project_id: str, audio: bytes, filename: str, title: str | None = None,
                 content_type: str | None = None, added_by: str | None = None, email: str | None = None) -> dict:
    stt = transcribe_sarvam(audio, filename, content_type)
    if not stt["transcript"]:
        raise ValueError("no speech recognised")
    title = title or f"Voice note {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"
    out = ingest_text(org_id=org_id, project_id=project_id, title=title, text=stt["transcript"],
                      category="voice_note", added_by=added_by, email=email, source="voice")
    return {"transcript": stt["transcript"], "languageCode": stt.get("languageCode"), **out}


# ============================================================== lifecycle
_warm = {"done": False}


def warmup(background: bool = True) -> None:
    def run():
        try:
            if embed.health().get("ok"):
                embed.embed_query("warm up vesper memory")
            store._table(create=False)  # noqa: SLF001
            rerank.score("warm up", ["warm up passage"] * 4)
            ingest.resume_pending()
            _warm["done"] = True
        except Exception as e:  # noqa: BLE001
            print(f"[memory] warmup: {e!r}"[:200])

    if background:
        threading.Thread(target=run, name="memory-warmup", daemon=True).start()
    else:
        run()
