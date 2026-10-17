"""BAAI/bge-reranker-v2-m3 cross-encoder (sentence-transformers) on MPS — lazy singleton.

Scores are sigmoid(logit) in [0, 1]; the abstention threshold in config is on this scale.
If the model cannot load (no weights, no torch) `score` returns None and retrieval falls back
to fused RRF order with entity-based abstention only.
"""
from __future__ import annotations

import math
import threading
import time

from . import config

_model = None
_load_error: str | None = None
_load_lock = threading.Lock()
_infer_lock = threading.Lock()  # MPS kernels are not re-entrant across threads
_device = "cpu"


def _pick_device() -> str:
    import torch

    if config.RERANK_DEVICE != "auto":
        return config.RERANK_DEVICE
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def get_model():
    global _model, _load_error, _device
    if _model is not None or _load_error is not None or not config.RERANK_ENABLED:
        return _model
    with _load_lock:
        if _model is not None or _load_error is not None:
            return _model
        try:
            import torch
            from sentence_transformers import CrossEncoder

            _device = _pick_device()
            t0 = time.time()
            try:
                m = CrossEncoder(config.RERANK_MODEL, device=_device, max_length=384,
                                 activation_fn=torch.nn.Identity(),
                                 model_kwargs={"dtype": torch.float16} if _device in ("mps", "cuda") else {})
            except TypeError:  # older signature: torch_dtype / no activation_fn
                m = CrossEncoder(config.RERANK_MODEL, device=_device, max_length=384,
                                 model_kwargs={"torch_dtype": torch.float16} if _device in ("mps", "cuda") else {})
            if _device in ("mps", "cuda"):
                try:
                    m.model.half()  # guarantee fp16 weights (~1.1 GB instead of 2.2 GB)
                except Exception:  # noqa: BLE001
                    pass
            m.predict([("warm up", "warm up")], batch_size=1, show_progress_bar=False)
            _model = m
            print(f"[memory] reranker {config.RERANK_MODEL} on {_device} in {time.time() - t0:.1f}s")
        except Exception as e:  # noqa: BLE001
            _load_error = repr(e)[:300]
            print(f"[memory] reranker unavailable: {_load_error}")
    return _model


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x)) if x > -60 else 0.0


def score(query: str, passages: list[str]) -> list[float] | None:
    m = get_model()
    if m is None or not passages:
        return None if m is None else []
    pairs = [(query, (p or "")[:config.RERANK_MAX_CHARS]) for p in passages]
    with _infer_lock:
        raw = m.predict(pairs, batch_size=16, show_progress_bar=False, convert_to_numpy=True)
    # Identity activation -> raw logits (bge-reranker spans roughly -11..+8); sigmoid them here.
    return [_sigmoid(float(v)) for v in list(raw)]


def status() -> dict:
    return {"model": config.RERANK_MODEL, "loaded": _model is not None, "device": _device, "error": _load_error}
