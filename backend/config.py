"""Loads the repo-root .env and exposes settings. Server-side only; never logged."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent

load_dotenv(REPO_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env.local", override=True)  # optional local override


def _bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


_raw_db = os.getenv("SITE_DB_PATH", "../data/site.db")
SITE_DB_PATH = _raw_db if os.path.isabs(_raw_db) else str((BACKEND_DIR / _raw_db).resolve())

PROJECT_ID = os.getenv("PROJECT_ID", "P1")
CRITICAL_FIELDS = [s.strip() for s in os.getenv(
    "CRITICAL_FIELDS", "location,drawing_number,dimension_claimed").split(",") if s.strip()]

# ---- Rime TTS ----
RIME_API_KEY = os.getenv("RIME_API_KEY", "").strip()
RIME_MODEL = os.getenv("RIME_MODEL", "arcana")
RIME_SPEAKER = os.getenv("RIME_SPEAKER", "").strip()
# The Talk console is English by default. Hinglish is an explicit user selection,
# rather than an accidental fallback caused by a deployment's legacy Rime settings.
RIME_LANG = os.getenv("RIME_LANG", "hin")
RIME_SPEAKER_EN = os.getenv("RIME_SPEAKER_EN", "cove").strip()
RIME_LANG_EN = os.getenv("RIME_LANG_EN", "eng")
RIME_MODEL_EN = os.getenv("RIME_MODEL_EN", "mistv3")
RIME_ENABLED = bool(RIME_API_KEY) and not RIME_API_KEY.startswith("<")

# ---- LLM (Groq gpt-oss-120b primary -> Cerebras gpt-oss-120b -> NVIDIA) ----
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "").strip()
CEREBRAS_BASE_URL = os.getenv("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1")
CEREBRAS_LLM_MODEL = os.getenv("CEREBRAS_LLM_MODEL", "gpt-oss-120b")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_LLM_MODEL = os.getenv("NVIDIA_LLM_MODEL", "openai/gpt-oss-120b")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
# llama-3.3-70b-versatile is retired on Groq; gpt-oss-120b verified 2026-09-15.
GROQ_LLM_MODEL = os.getenv("GROQ_LLM_MODEL", "openai/gpt-oss-120b")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3")

# ---- STT (Sarvam saaras:v3 primary -> Groq Whisper fallback) ----
STT_PROVIDER = os.getenv("STT_PROVIDER", "sarvam").strip().lower()
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "").strip()
SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3").strip()
SARVAM_STT_MODE = os.getenv("SARVAM_STT_MODE", "transcribe").strip()
# REST uses "unknown" for auto-detect; the realtime websocket calls the same thing "auto".
SARVAM_STT_LANGUAGE = os.getenv("SARVAM_STT_LANGUAGE", "unknown").strip().replace("auto", "unknown")
SARVAM_STT_KEYTERMS = _bool(os.getenv("SARVAM_STT_KEYTERMS"), True)  # site vocabulary biasing (REST)


def _key_ok(k: str) -> bool:
    return bool(k) and not k.startswith("<")


CEREBRAS_ENABLED = _key_ok(CEREBRAS_API_KEY)
NVIDIA_ENABLED = _key_ok(NVIDIA_API_KEY)
GROQ_ENABLED = _key_ok(GROQ_API_KEY)
SARVAM_ENABLED = _key_ok(SARVAM_API_KEY)


def llm_provider() -> str:
    if GROQ_ENABLED:
        return "groq"
    if CEREBRAS_ENABLED:
        return "cerebras"
    if NVIDIA_ENABLED:
        return "nvidia"
    return "off"


# ---- Speaker ID ----
SPEAKER_ID_ENABLED = _bool(os.getenv("SPEAKER_ID_ENABLED"), True)  # voice writes need a verified voiceprint
SPEAKER_ID_URL = os.getenv("SPEAKER_ID_URL", "http://localhost:8788").rstrip("/")
SPEAKER_ID_THRESHOLD = float(os.getenv("SPEAKER_ID_THRESHOLD", "0.70"))

# Required in deployment. Empty keeps localhost development friction-free.
CLERK_JWT_ISSUER = os.getenv("CLERK_JWT_ISSUER", "").rstrip("/")
FREE_COMMAND_LIMIT = int(os.getenv("FREE_COMMAND_LIMIT", "3"))
# The cap protects public deployments from unbounded provider usage. Local development is
# deliberately unlimited so a developer can exercise LiveKit and the safety scenarios without
# consuming a browser session during every restart. Set this explicitly in any deployed runtime.
ENFORCE_FREE_COMMAND_LIMIT = _bool(
    os.getenv("ENFORCE_FREE_COMMAND_LIMIT"),
    os.getenv("APP_ENV", "development").strip().lower() in {"production", "staging"},
)
DEMO_SEED_EMAIL = os.getenv("DEMO_SEED_EMAIL", "atharva.v.deo@gmail.com").strip().lower()
