"""Cognee knowledge-graph worker — runs under backend/.venv-cognee (Cognee pins openai<3 / websockets<16,
which would break the main backend venv), as a separate process holding data/memory/cognee.lock.

    backend/.venv-cognee/bin/python backend/memory/cognee_worker.py [--max-docs 40]

Picks documents with graph_status='pending' (project datasets first), `cognee.add`s their chunk text
into the same-named Cognee dataset with node_set=[dataset, category], runs `cognee.cognify` per dataset,
marks documents done / retries later, and exports the graph to data/memory/graph/graph.json for the API.
Bounded per run; resumable (state lives in app.db). Groq gpt-oss-120b with backoff, Cerebras fallback.
Local stores under data/memory/cognee: SQLite (relational), LanceDB (vectors), Kuzu/Ladybug (graph).
"""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import sys
import time
import traceback
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from memory import config  # noqa: E402  (loads .env files; values are never printed)


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}", flush=True)


def configure_env(use_cerebras: bool = False) -> None:
    sys_dir = config.COGNEE_DIR / "system"
    sys_dir.mkdir(parents=True, exist_ok=True)
    config.COGNEE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    bundled_lbug = BACKEND.parent / "data" / "vendor" / "ladybug" / "v0.19.0" / "liblbug.dylib"
    if bundled_lbug.is_file():
        # Cognee 1.5.4 pins Ladybug 0.19.0. Use the matching, digest-verified C API
        # release locally and bypass the macOS wheel's optional pybind extension.
        os.environ.setdefault("LBUG_C_API_LIB_PATH", str(bundled_lbug))
        os.environ.setdefault("LBUG_PYTHON_BACKEND", "capi")
    graph_provider = os.getenv("COGNEE_GRAPH_PROVIDER", "ladybug" if bundled_lbug.is_file() else "turso")
    graph_suffix = "ladybug" if graph_provider in ("ladybug", "kuzu") else "libsql"
    env = {
        "SYSTEM_ROOT_DIRECTORY": str(sys_dir), "DATA_ROOT_DIRECTORY": str(config.COGNEE_DATA_DIR),
        "DB_PROVIDER": "sqlite", "DB_NAME": "cognee_db", "VECTOR_DB_PROVIDER": "lancedb",
        "GRAPH_DATABASE_PROVIDER": graph_provider,
        "GRAPH_DATABASE_URL": os.getenv("COGNEE_GRAPH_URL", str(config.COGNEE_DIR / "system" / f"graph.{graph_suffix}")),
        "GRAPH_DATASET_DATABASE_HANDLER": os.getenv("COGNEE_GRAPH_HANDLER", graph_provider),
        # auto Alembic migrations import the Ladybug C-API on this wheel and fail; tables are created on first use
        "ENABLE_AUTO_MIGRATIONS": os.getenv("COGNEE_AUTO_MIGRATIONS", "false"),
        "ENABLE_BACKEND_ACCESS_CONTROL": "false",  # scoping is enforced by Vesper; one shared graph, node sets per dataset
        "TELEMETRY_DISABLED": "1",
        "EMBEDDING_PROVIDER": "ollama", "EMBEDDING_MODEL": f"{config.EMBED_MODEL}:latest",
        "EMBEDDING_ENDPOINT": f"{config.OLLAMA_URL}/api/embed", "EMBEDDING_DIMENSIONS": str(config.EMBED_DIM),
        "HUGGINGFACE_TOKENIZER": "BAAI/bge-m3",
        "LLM_RATE_LIMIT_ENABLED": "true", "LLM_RATE_LIMIT_REQUESTS": os.getenv("COGNEE_LLM_RPM", "20"),
        "LLM_RATE_LIMIT_INTERVAL": "60",
    }
    primary_groq = bool(config.GROQ_API_KEY) and not use_cerebras
    if primary_groq:
        env.update({"LLM_PROVIDER": "custom", "LLM_MODEL": f"groq/{config.LLM_MODEL}",
                    "LLM_ENDPOINT": config.GROQ_BASE_URL, "LLM_API_KEY": config.GROQ_API_KEY})
        if config.CEREBRAS_API_KEY:
            env.update({"FALLBACK_MODEL": f"cerebras/{config.CEREBRAS_MODEL}", "FALLBACK_ENDPOINT": config.CEREBRAS_BASE_URL,
                        "FALLBACK_API_KEY": config.CEREBRAS_API_KEY})
    elif config.CEREBRAS_API_KEY:
        env.update({"LLM_PROVIDER": "custom", "LLM_MODEL": f"cerebras/{config.CEREBRAS_MODEL}",
                    "LLM_ENDPOINT": config.CEREBRAS_BASE_URL, "LLM_API_KEY": config.CEREBRAS_API_KEY})
    os.environ.update(env)


def _is_rate_limit(e: BaseException) -> bool:
    s = repr(e).lower()
    return "429" in s or "rate limit" in s or "ratelimit" in s or "too many requests" in s


async def cognify_with_retry(cognee, ds: str, state: dict) -> tuple[bool, str | None]:
    last = None
    for attempt in range(5):
        try:
            await cognee.cognify(datasets=[ds])
            return True, None
        except Exception as e:  # noqa: BLE001
            last = repr(e)[:300]
            log(f"cognify {ds} attempt {attempt + 1} failed: {last}")
            if _is_rate_limit(e):
                if attempt >= 1 and config.CEREBRAS_API_KEY and not state.get("cerebras"):
                    log("switching cognify LLM to Cerebras fallback")
                    state["cerebras"] = True
                    configure_env(use_cerebras=True)
                    try:
                        cognee.config.set_llm_config({"llm_provider": "custom",
                                                      "llm_model": f"cerebras/{config.CEREBRAS_MODEL}",
                                                      "llm_endpoint": config.CEREBRAS_BASE_URL,
                                                      "llm_api_key": config.CEREBRAS_API_KEY})
                    except Exception:  # noqa: BLE001
                        pass
                    continue
                await asyncio.sleep(min(120, 15 * 2 ** attempt))
            else:
                if attempt >= 1:
                    break
                await asyncio.sleep(5)
    return False, last


async def _setup(cognee) -> None:
    """With auto-migrations off, create Cognee's relational tables and default user explicitly (idempotent)."""
    try:
        from cognee.infrastructure.databases.relational import create_db_and_tables

        await create_db_and_tables()
        log("cognee relational tables ensured")
    except Exception as e:  # noqa: BLE001
        log(f"create_db_and_tables failed: {e!r}"[:300])
    try:
        from cognee.modules.users.methods import create_default_user, get_default_user

        try:
            await get_default_user()
        except Exception:  # noqa: BLE001
            await create_default_user()
            log("cognee default user created")
    except Exception as e:  # noqa: BLE001
        log(f"default user setup failed: {e!r}"[:300])
    for path in ("cognee.modules.engine.operations.setup", "cognee.infrastructure.databases.relational"):
        try:
            mod = __import__(path, fromlist=["setup", "create_db_and_tables"])
            fn = getattr(mod, "setup", None) or getattr(mod, "create_db_and_tables", None)
            if fn:
                await fn()
                log(f"cognee setup via {path}")
                return
        except Exception as e:  # noqa: BLE001
            log(f"cognee setup via {path} failed: {e!r}"[:300])
    if hasattr(cognee, "setup"):
        await cognee.setup()


async def export_snapshot() -> dict:
    from cognee.infrastructure.databases.graph import get_graph_engine

    ge = await get_graph_engine()
    nodes, edges = await ge.get_graph_data()
    out_nodes, names = [], {}
    for nid, props in nodes:
        label = str(props.get("name") or props.get("text") or props.get("type") or nid)[:80]
        typ = str(props.get("type") or "")
        names[nid] = (label, typ)
        out_nodes.append({"id": nid, "label": label, "type": typ})
    out_edges = [{"source": s, "target": t, "label": r} for s, t, r, *_ in edges]
    # dataset membership: NodeSet nodes carry the dataset name; members link to them, entities hang off members
    sets = {nid for nid, (lab, typ) in names.items() if typ == "NodeSet"}
    by_ds: dict[str, set] = {}
    adj: dict[str, set] = {}
    for e in out_edges:
        adj.setdefault(e["source"], set()).add(e["target"])
        adj.setdefault(e["target"], set()).add(e["source"])
    for sid in sets:
        ds = names[sid][0]
        members = set(adj.get(sid, set()))
        for m in list(members):
            members |= adj.get(m, set())
        by_ds[ds] = members | {sid}
    snap = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "nodes": out_nodes, "edges": out_edges,
            "datasets": {k: sorted(v) for k, v in by_ds.items()}}
    config.GRAPH_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = config.GRAPH_SNAPSHOT_DIR / "graph.json.tmp"
    tmp.write_text(json.dumps(snap))
    tmp.replace(config.GRAPH_SNAPSHOT_DIR / "graph.json")
    return {"nodes": len(out_nodes), "edges": len(out_edges)}


async def run(max_docs: int, datasets: list[str] | None) -> None:
    from memory import store  # app.db helpers (sqlite only here)

    configure_env()
    import cognee

    await _setup(cognee)
    state: dict = {}
    processed = 0
    while processed < max_docs:
        sql = ("SELECT doc_id, dataset, title, category FROM documents WHERE graph_status = 'pending' AND status = 'done' "
               "AND graph_attempts < 4")
        args: list = []
        if datasets:
            sql += f" AND dataset IN ({','.join('?' for _ in datasets)})"
            args += datasets
        sql += " ORDER BY (scope = 'project') DESC, graph_attempts, created_at LIMIT ?"
        docs = [dict(r) for r in store.db().execute(sql, [*args, min(config.COGNEE_BATCH_DOCS, max_docs - processed)])]
        if not docs:
            break
        by_ds: dict[str, list[dict]] = {}
        for d in docs:
            by_ds.setdefault(d["dataset"], []).append(d)
        for ds, group in by_ds.items():
            t0 = time.time()
            try:
                for d in group:
                    text = "\n\n".join(c["text"] for c in store.doc_chunks(d["doc_id"]))[:config.COGNEE_DOC_CHARS]
                    await cognee.add(f"{d['title']}\n\n{text}", dataset_name=ds,
                                     node_set=[ds, d.get("category") or "other"])
                ok, err = await cognify_with_retry(cognee, ds, state)
            except Exception as e:  # noqa: BLE001
                ok, err = False, repr(e)[:300]
                log(traceback.format_exc()[-1200:])
            conn = store.db()
            for d in group:
                if ok:
                    conn.execute("UPDATE documents SET graph_status='done', graph_error=NULL, updated_at=? WHERE doc_id=?",
                                 (store.now_iso(), d["doc_id"]))
                else:
                    conn.execute("UPDATE documents SET graph_attempts = graph_attempts + 1, graph_error = ?, "
                                 "graph_status = CASE WHEN graph_attempts + 1 >= 4 THEN 'error' ELSE 'pending' END, "
                                 "updated_at = ? WHERE doc_id = ?", (err, store.now_iso(), d["doc_id"]))
                # the searchable part finished long ago; a graph failure never leaves a job hanging
                conn.execute("UPDATE ingest_jobs SET status='done', progress=1.0, updated_at=? "
                             "WHERE doc_id=? AND status='graph'", (store.now_iso(), d["doc_id"]))
            conn.commit()
            processed += len(group)
            log(f"{ds}: {len(group)} docs {'cognified' if ok else 'FAILED'} in {time.time() - t0:.1f}s "
                f"(run total {processed}/{max_docs})")
        try:
            log(f"graph snapshot {await export_snapshot()}")
        except Exception as e:  # noqa: BLE001
            log(f"snapshot failed: {e!r}"[:300])
    log(f"worker exit: processed {processed}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-docs", type=int, default=config.COGNEE_MAX_DOCS_PER_RUN)
    ap.add_argument("--datasets", default="")
    ap.add_argument("--snapshot-only", action="store_true")
    a = ap.parse_args()
    fd = os.open(config.COGNEE_LOCK, os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("another cognee worker holds the lock — exiting")
        return
    try:
        if a.snapshot_only:
            configure_env()
            import cognee  # noqa: F401

            log(f"graph snapshot {asyncio.run(export_snapshot())}")
            return
        ds = [x for x in a.datasets.split(",") if x] or None
        asyncio.run(run(a.max_docs, ds))
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


if __name__ == "__main__":
    main()
