"""bge-m3 embeddings served by Ollama — the SAME engine at ingest and at query time.

Query embeddings are cached twice: an in-process LRU and an on-disk SQLite cache keyed by
sha256(model:text), so a repeated voice question costs no Ollama round-trip after a restart.
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from collections import OrderedDict

import httpx
import numpy as np

from . import config

_client = httpx.Client(timeout=httpx.Timeout(120.0, connect=3.0))
_lru: OrderedDict[str, np.ndarray] = OrderedDict()
_LRU_MAX = 4096
_lock = threading.Lock()
_disk: sqlite3.Connection | None = None
_TTL = 14 * 86400
MAX_CHARS = 6000  # bge-m3 has 8k tokens of context; long chunks are truncated client-side too


class EmbeddingUnavailable(RuntimeError):
    pass


def _normalize(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (m / n).astype(np.float32)


def _post(batch: list[str]) -> list[list[float]]:
    last: Exception | None = None
    for attempt in range(4):
        try:
            r = _client.post(f"{config.OLLAMA_URL}/api/embed",
                             json={"model": config.EMBED_MODEL, "input": batch, "truncate": True,
                                   "keep_alive": "60m"})
            if r.status_code == 200:
                emb = r.json().get("embeddings") or []
                if len(emb) == len(batch):
                    return emb
                last = RuntimeError(f"ollama returned {len(emb)} vectors for {len(batch)} inputs")
            else:
                last = RuntimeError(f"ollama embed HTTP {r.status_code}: {r.text[:200]}")
        except httpx.HTTPError as e:
            last = e
        time.sleep(0.5 * (2 ** attempt))
    raise EmbeddingUnavailable(f"embedding failed: {last!r}")


def embed_texts(texts: list[str], batch_size: int | None = None) -> np.ndarray:
    """Embed documents. Returns an (n, dim) float32 L2-normalised matrix."""
    if not texts:
        return np.zeros((0, config.EMBED_DIM), dtype=np.float32)
    bs = batch_size or config.EMBED_BATCH
    out: list[list[float]] = []
    for i in range(0, len(texts), bs):
        out += _post([(t or " ")[:MAX_CHARS] for t in texts[i:i + bs]])
    m = np.asarray(out, dtype=np.float32)
    if m.shape[1] != config.EMBED_DIM:
        raise EmbeddingUnavailable(f"expected dim {config.EMBED_DIM}, got {m.shape[1]}")
    return _normalize(m)


def _disk_conn() -> sqlite3.Connection:
    global _disk
    if _disk is None:
        _disk = sqlite3.connect(str(config.EMBED_CACHE_PATH), check_same_thread=False, timeout=10)
        _disk.execute("PRAGMA journal_mode=WAL")
        _disk.execute("CREATE TABLE IF NOT EXISTS qcache (k TEXT PRIMARY KEY, v BLOB NOT NULL, ts REAL NOT NULL)")
    return _disk


def embed_query(text: str) -> np.ndarray:
    q = " ".join((text or "").split())
    key = hashlib.sha256(f"{config.EMBEDDING_VERSION}:{q}".encode()).hexdigest()
    with _lock:
        if key in _lru:
            _lru.move_to_end(key)
            return _lru[key]
        try:
            row = _disk_conn().execute("SELECT v, ts FROM qcache WHERE k = ?", (key,)).fetchone()
        except sqlite3.Error:
            row = None
    if row and time.time() - row[1] < _TTL:
        vec = np.frombuffer(row[0], dtype=np.float32).copy()
    else:
        vec = embed_texts([q])[0]
        with _lock:
            try:
                _disk_conn().execute("INSERT OR REPLACE INTO qcache (k, v, ts) VALUES (?, ?, ?)",
                                     (key, vec.tobytes(), time.time()))
                _disk_conn().commit()
            except sqlite3.Error:
                pass
    with _lock:
        _lru[key] = vec
        if len(_lru) > _LRU_MAX:
            _lru.popitem(last=False)
    return vec


def health() -> dict:
    try:
        r = _client.get(f"{config.OLLAMA_URL}/api/tags", timeout=2.0)
        names = [m.get("name", "") for m in r.json().get("models", [])]
        return {"ok": any(n.split(":")[0] == config.EMBED_MODEL for n in names), "models": names}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": repr(e)[:120]}
