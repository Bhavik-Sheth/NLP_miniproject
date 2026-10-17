"""Server-side speech-to-text for /api/stt: Sarvam saaras:v3 REST primary, Groq Whisper fallback.

Returns plain dicts / raises SttError so main.py keeps its existing error mapping
(`_stt_error_response`). Keys come from config and are never logged.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import httpx

import config

logger = logging.getLogger("vesper.stt")

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
_SARVAM_LANGS = {"unknown", "hi-IN", "bn-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN",
                 "te-IN", "en-IN", "gu-IN", "as-IN", "ur-IN", "ne-IN"}

# Same biasing text and post-STT normaliser as the live agent (agent/worker_prompts.py,
# agent/stt_normalize.py). Optional: /api/stt still works if the agent folder is absent.
_AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"
try:
    if str(_AGENT_DIR) not in sys.path:
        sys.path.append(str(_AGENT_DIR))
    from stt_normalize import normalize as _normalize  # type: ignore
    from worker_prompts import STT_PROMPT as _WHISPER_PROMPT, sarvam_keyterms as _keyterms  # type: ignore
except Exception:  # pragma: no cover - agent folder missing
    _normalize = None
    _keyterms = None
    _WHISPER_PROMPT = ("Column line C-5, rebar spacing 180 millimetres, drawing A-102 revision R4. "
                       "Cover at E-1 column is 40 millimetres per IS 456. RFI-050 still open.")


class SttError(Exception):
    """Upstream failure. status: provider HTTP status (0 = timeout, -1 = network)."""

    def __init__(self, provider: str, status: int, detail: str = "") -> None:
        super().__init__(f"{provider} {status}")
        self.provider = provider
        self.status = status
        self.detail = detail


def _sarvam_language(hint: str) -> str:
    """Browser hints are loose ("en", "hi", "en-IN"). The Talk console sends "en-IN" by default,
    but its speakers mix Hindi in: forcing en-IN lost the grid in "सी पांच pe spacing" (A/B,
    2026-09-15), so any English hint keeps auto-detection. Other Indian locales are honoured."""
    h = (hint or "").strip()
    if h.lower().startswith("hi"):
        return "hi-IN"
    if h in _SARVAM_LANGS and not h.lower().startswith("en"):
        return h
    return config.SARVAM_STT_LANGUAGE if config.SARVAM_STT_LANGUAGE in _SARVAM_LANGS else "unknown"


async def sarvam_transcribe(raw: bytes, filename: str, content_type: str, language: str = "") -> str:
    data: dict[str, str] = {"model": config.SARVAM_STT_MODEL, "mode": config.SARVAM_STT_MODE,
                            "language_code": _sarvam_language(language)}
    # Sarvam rejects keyterms on saaras:v3 ("only supported by model 'saaras:v4'", 2026-09-15)
    if config.SARVAM_STT_KEYTERMS and _keyterms and config.SARVAM_STT_MODEL.startswith("saaras:v4"):
        data["keyterms"] = json.dumps(_keyterms())
    try:
        async with httpx.AsyncClient(timeout=30.0) as cx:
            r = await cx.post(SARVAM_STT_URL, headers={"api-subscription-key": config.SARVAM_API_KEY},
                              data=data, files={"file": (filename, raw, content_type)})
    except httpx.TimeoutException as e:
        raise SttError("sarvam", 0, "timeout") from e
    except httpx.HTTPError as e:
        raise SttError("sarvam", -1, "unavailable") from e
    if r.status_code != 200:
        raise SttError("sarvam", r.status_code, r.text)
    try:
        return (r.json().get("transcript") or "").strip()
    except (ValueError, AttributeError) as e:
        raise SttError("sarvam", 502, "invalid provider response") from e


async def groq_transcribe(raw: bytes, filename: str, content_type: str, language: str = "") -> str:
    data = {"model": config.GROQ_STT_MODEL, "response_format": "json", "temperature": "0",
            "prompt": _WHISPER_PROMPT}
    if language:
        data["language"] = language.split("-")[0]
    try:
        async with httpx.AsyncClient(timeout=30.0) as cx:
            r = await cx.post(f"{config.GROQ_BASE_URL}/audio/transcriptions",
                              headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                              data=data, files={"file": (filename, raw, content_type)})
    except httpx.TimeoutException as e:
        raise SttError("groq", 0, "timeout") from e
    except httpx.HTTPError as e:
        raise SttError("groq", -1, "unavailable") from e
    if r.status_code != 200:
        raise SttError("groq", r.status_code, r.text)
    try:
        return (r.json().get("text") or "").strip()
    except (ValueError, AttributeError) as e:
        raise SttError("groq", 502, "invalid provider response") from e


def providers() -> list[str]:
    order: list[str] = []
    if config.STT_PROVIDER == "sarvam" and config.SARVAM_ENABLED:
        order.append("sarvam")
    if config.GROQ_ENABLED:
        order.append("groq")
    if config.STT_PROVIDER != "sarvam" and config.SARVAM_ENABLED:
        order.append("sarvam")
    return order


async def transcribe(raw: bytes, filename: str, content_type: str, language: str = "") -> dict:
    """Try each configured provider in order. Returns {"text", "provider"}; raises the LAST
    SttError when every provider failed, or SttError("none", 503) when none is configured."""
    order = providers()
    if not order:
        raise SttError("none", 503, "no STT provider configured")
    last: SttError | None = None
    for name in order:
        t0 = time.perf_counter()
        fn = sarvam_transcribe if name == "sarvam" else groq_transcribe
        try:
            text = await fn(raw, filename, content_type, language)
        except SttError as e:
            logger.warning("stt %s failed: status %s", name, e.status)
            last = e
            continue
        changes: list[str] = []
        if _normalize is not None:
            norm = _normalize(text)
            text, changes = norm.text, norm.changes
        logger.info("stt %s ok in %d ms%s", name, (time.perf_counter() - t0) * 1000,
                    f" (normalised: {'; '.join(changes)})" if changes else "")
        return {"text": text, "provider": name}
    assert last is not None
    raise last
