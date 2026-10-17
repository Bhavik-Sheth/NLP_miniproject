"""Vesper memory layer settings. Everything is overridable by env; secrets are read, never logged."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
load_dotenv(REPO_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env.local", override=True)


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v.strip() if v and v.strip() else default


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def _key(name: str) -> str:
    k = os.getenv(name, "").strip()
    return "" if k.startswith("<") else k


# ---------------------------------------------------------------- paths
DATA_DIR = Path(_env("VESPER_DATA_DIR", str(REPO_ROOT / "data")))
def app_db_path() -> Path:
    """Resolved per call so a test that sets APP_DB_PATH is not defeated by import order.
    MEMORY_APP_DB still wins, then the tenancy-wide APP_DB_PATH, then data/app.db."""
    return Path(_env("MEMORY_APP_DB", _env("APP_DB_PATH", str(DATA_DIR / "app.db"))))


APP_DB_PATH = app_db_path()  # import-time snapshot, kept for callers that read the constant
SITE_DB_PATH = Path(_env("MEMORY_SITE_DB", str(DATA_DIR / "site.db")))
MEMORY_DIR = Path(_env("MEMORY_DIR", str(DATA_DIR / "memory")))
LANCEDB_DIR = MEMORY_DIR / "lancedb"
LANCE_TABLE = "chunks"
COGNEE_DIR = MEMORY_DIR / "cognee"            # Cognee system_root_directory
COGNEE_DATA_DIR = COGNEE_DIR / "data"          # Cognee data_root_directory
GRAPH_SNAPSHOT_DIR = MEMORY_DIR / "graph"      # nodes/edges exported by the Cognee worker
UPLOAD_DIR = MEMORY_DIR / "uploads"
EMBED_CACHE_PATH = MEMORY_DIR / "embed_cache.sqlite"
INGEST_LOG = MEMORY_DIR / "ingest_log.txt"
COGNEE_LOG = MEMORY_DIR / "cognee_worker.log"
COGNEE_LOCK = MEMORY_DIR / "cognee.lock"
SECTIONS_DIR = DATA_DIR / "raw" / "sections"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# ---------------------------------------------------------------- models
OLLAMA_URL = _env("OLLAMA_URL", "http://localhost:11434").rstrip("/")
EMBED_MODEL = _env("MEMORY_EMBED_MODEL", "bge-m3")
EMBED_DIM = int(_env("MEMORY_EMBED_DIM", "1024"))
EMBED_BATCH = int(_env("MEMORY_EMBED_BATCH", "32"))
EMBEDDING_VERSION = f"{EMBED_MODEL}@ollama:v1"
CHUNKING_VERSION = "vesper-chunk-v1"

RERANK_MODEL = _env("MEMORY_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_DEVICE = _env("MEMORY_RERANK_DEVICE", "auto")  # auto|mps|cpu
RERANK_ENABLED = _bool("MEMORY_RERANK_ENABLED", True)
RERANK_MAX_CHARS = int(_env("MEMORY_RERANK_MAX_CHARS", "1400"))

GROQ_API_KEY = _key("GROQ_API_KEY")
GROQ_BASE_URL = _env("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = _env("MEMORY_LLM_MODEL", "openai/gpt-oss-120b")
CEREBRAS_API_KEY = _key("CEREBRAS_API_KEY")
CEREBRAS_BASE_URL = _env("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1")
CEREBRAS_MODEL = _env("MEMORY_CEREBRAS_MODEL", "gpt-oss-120b")
LLM_TIMEOUT = float(_env("MEMORY_LLM_TIMEOUT", "15"))

SARVAM_API_KEY = _key("SARVAM_API_KEY")
SARVAM_STT_URL = _env("SARVAM_STT_URL", "https://api.sarvam.ai/speech-to-text")
SARVAM_STT_MODEL = _env("SARVAM_STT_MODEL", "saaras:v3")

# ---------------------------------------------------------------- retrieval
VECTOR_K = int(_env("MEMORY_VECTOR_K", "30"))
FTS_K = int(_env("MEMORY_FTS_K", "15"))
RRF_K = int(_env("MEMORY_RRF_K", "60"))
RERANK_TOP = int(_env("MEMORY_RERANK_TOP", "20"))
KEEP_K = int(_env("MEMORY_KEEP_K", "8"))
MAX_PER_DOC = int(_env("MEMORY_MAX_PER_DOC", "3"))
# calibrated on data/memory/golden.json by scripts/eval_memory.py (see docs/plan/reports/W1.md)
ABSTAIN_THRESHOLD = float(_env("MEMORY_ABSTAIN_THRESHOLD", "0.03"))
# without the cross-encoder the fused score is on another scale; only entity/empty checks abstain
CONTEXT_CHAR_BUDGET = int(_env("MEMORY_CONTEXT_CHARS", "12000"))

# ---------------------------------------------------------------- scopes
GLOBAL_DATASETS = ["kb_templates", "kb_is_codes", "kb_prices_sor", "kb_handbook"]
TABULAR_DATASETS = {"kb_prices_sor"}            # BM25 + vector only, never LLM graph extraction
DEMO_ORG = _env("VESPER_DEMO_ORG", "org_local_demo")
DEMO_PROJECT = _env("VESPER_DEMO_PROJECT", "P1")

CATEGORIES = ["project_profile", "drawing", "rfi", "permit", "checklist", "daily_log", "boq", "submittal",
              "specification", "template", "is_code", "price_sor", "handbook", "voice_note", "note",
              "report", "contract", "other"]

# ---------------------------------------------------------------- Cognee (runs in its own venv)
COGNEE_PYTHON = Path(_env("COGNEE_PYTHON", str(BACKEND_DIR / ".venv-cognee" / "bin" / "python")))
# off by default: cognee 1.5.4 migrations need the Ladybug C-API dylib missing from the macOS wheel (see W1 report)
COGNEE_ENABLED = _bool("MEMORY_COGNEE_ENABLED", False) and COGNEE_PYTHON.exists()
COGNEE_MAX_DOCS_PER_RUN = int(_env("MEMORY_COGNIFY_MAX_DOCS", "40"))
COGNEE_BATCH_DOCS = int(_env("MEMORY_COGNIFY_BATCH", "5"))
COGNEE_DOC_CHARS = int(_env("MEMORY_COGNIFY_DOC_CHARS", "6000"))


def project_dataset(org_id: str | None, project_id: str) -> str:
    """`org_<orgId>__proj_<projectId>`; a Clerk id's own `org_` prefix is not doubled."""
    org = (org_id or DEMO_ORG).strip()
    org = org[4:] if org.startswith("org_") else org
    safe = lambda s: "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in s)  # noqa: E731
    return f"org_{safe(org)}__proj_{safe(project_id)}"


def llm_available() -> bool:
    return bool(GROQ_API_KEY or CEREBRAS_API_KEY)


for _d in (MEMORY_DIR, LANCEDB_DIR, COGNEE_DIR, GRAPH_SNAPSHOT_DIR, UPLOAD_DIR):
    _d.mkdir(parents=True, exist_ok=True)
