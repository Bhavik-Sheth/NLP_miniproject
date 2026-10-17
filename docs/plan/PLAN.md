# Vesper v2 — build plan and shared contract

Status: building — live status board in [PROGRESS.md](PROGRESS.md). No git commits until the user asks. Secrets live only in `.env` and
`backend/.env.local` (git-ignored) — never print, log, or write keys anywhere else.

Research docs: `docs/plan/research/02-bd-agent-rag.md` (RAG patterns to port — W1 must read). The
Cognee / Sarvam / onboarding / Resend research runs were cancelled, so each workstream looks up current
docs itself (WebSearch/WebFetch/Context7) and saves its findings to `docs/plan/research/<nn>-<topic>.md`.
Each workstream writes a final report to `docs/plan/reports/W<n>.md` (what was built, how to run, env
vars, known gaps).

## 1. Decisions (fixed)

| Area | Choice | Why |
| --- | --- | --- |
| Memory framework | **Cognee**, fully local (SQLite relational, **LanceDB** vectors, **Kuzu** graph) | Knowledge graph + vector memory, runs on the laptop |
| Retrieval | **Hybrid**: LanceDB vector + SQLite FTS5 BM25 → RRF (k=60) → cross-encoder rerank → **score threshold abstention**; Cognee graph for entity/relationship questions | bd-agent pattern; exact tokens (RFI-050, C-4, Cl. 26.4) need BM25 |
| Vector store | **LanceDB** (embedded, on-disk, Cognee default) at `data/memory/` | No server, fast, local |
| Embeddings | **BAAI/bge-m3** (1024d, multilingual incl. Hindi, 8k ctx, MIT) served by **Ollama** (`ollama pull bge-m3`) — same engine at ingest AND query | Hinglish queries over English technical text |
| Reranker | **BAAI/bge-reranker-v2-m3** via `sentence-transformers` CrossEncoder on MPS | Best local multilingual cross-encoder |
| LLM (reasoning, answer synthesis, cognify) | **Groq `openai/gpt-oss-120b`** primary → Cerebras `gpt-oss-120b` fallback | Verified working 2026-09-15 (0.42 s) |
| STT | **Sarvam `saaras:v3`** replaces Groq Whisper | Whisper mangles Indian names ("Pithoragarh" → "pit-thoroughly") |
| TTS | Rime (unchanged), English output | |
| Auth / tenancy | **Clerk Organizations** = client company; projects belong to an org | |
| Email | **Resend** (templates by id from env, inline HTML fallback) | |
| App DB | `data/app.db` (SQLite, new) for orgs, projects, profiles, members, documents, chunks, FTS, ingest jobs. `data/site.db` stays the deterministic P1 engine DB (rebuilt by `data/build_db.py`, never add tables there) | |

Safety invariant (unchanged): drawing facts, revisions, permits and hold points are decided by the
deterministic engine. The memory layer answers knowledge questions and supplies citations; it never
authorises a log.

## 2. Workstreams and file ownership (do not edit files you don't own)

| # | Workstream | Owns |
| --- | --- | --- |
| W1 | Memory layer + ingestion + fix "confident wrong answers" | `backend/memory/**`, `backend/routes/memory.py`, `backend/routes/ingest.py`, `scripts/ingest_*.py`, `scripts/eval_memory.py`, `data/memory/**`, `backend/engine/answer.py` (abstention only), append to `backend/requirements.txt` |
| W2 | Tenancy + onboarding API + Resend | `backend/tenancy/**`, `backend/routes/tenancy.py`, `backend/emails/**`, `data/app_schema.sql` (tenancy tables), `data/onboarding_schema.json` (field schema — single source of truth, written FIRST) |
| W3 | Laptop dashboard UI + theme | `app/app/app/**`, `app/components/dashboard/**`, `app/lib/api-v2.ts`, `app/app/globals.css`, `app/app/layout.tsx` (theme only) |
| W4 | Onboarding + ingest UI | `app/app/onboarding/**`, `app/components/onboarding/**`, `app/lib/api-tenancy.ts`, `app/proxy.ts` (onboarding redirect). Reads field schema from `GET /api/onboarding/schema` (fallback: import `data/onboarding_schema.json` at build time) |
| W5 | Voice: Sarvam STT, prompts, Groq primary | `agent/**`, `backend/stt_sarvam.py`, `/api/stt` handler in `backend/main.py`, `backend/engine/llm.py` |
| W6 | Crawl remaining InfraLens sections | `data/scraper/crawl_sections.py`, `data/raw/sections/**` |

`backend/main.py` already includes `routes.memory`, `routes.ingest`, `routes.tenancy` optionally
(`GET /api/v2/status` shows load errors). Routers use `APIRouter()` with full paths.

`data/app.db` schema: W2 creates tenancy tables via `data/app_schema.sql`; W1 creates its
memory tables (documents, chunks, chunks_fts, ingest_jobs) in `backend/memory/schema.sql` in the same
file. Both open it with `backend/tenancy/appdb.py::connect()` — W2 ships that helper first (tiny: path
`data/app.db`, WAL, row_factory, run both schema files idempotently if present).

## 3. Identity (W2 provides, everyone uses)

`backend/tenancy/auth.py`:

```python
@dataclass
class Identity: user_id: str; org_id: str | None; org_role: str | None; email: str | None
def get_identity(request: Request) -> Identity        # FastAPI dependency
def require_project(project_id: str, ident: Identity) -> dict   # 404/403, returns project row
```

- Verifies Clerk session JWT (RS256, JWKS, issuer `CLERK_JWT_ISSUER`) — same approach as `main._user_id`.
  Org from session token v2 claim `o` (`o.id`, `o.rol`) or v1 `org_id`/`org_role`.
- No `CLERK_JWT_ISSUER` (local dev): headers `X-Vesper-User` (default `local-demo`), `X-Vesper-Org`
  (default `org_local_demo`).
- The seeded P1 project is exposed as project `P1` in org `org_local_demo` (and readable by every
  signed-in user as a demo project, read-only).

## 4. HTTP API (JSON, `Authorization: Bearer <clerk token>`)

### Tenancy (W2)
- `GET /api/me` → `{user:{id,email}, org:{id,name,role}|null, orgs:[…], projects:[{id,name,code,type,city,status,role}], onboarding:{orgDone:bool, projectDone:bool}}`
- `POST /api/orgs` `{clerkOrgId, profile:{…org fields}}` → `{org}` (Clerk org is created client-side, backend stores profile)
- `GET|PUT /api/orgs/{orgId}`
- `GET /api/onboarding/schema` → the field schema (steps → fields with `key,label,type,required,options,help,usedByVoice`) — single source of truth; W4 renders it, W2 validates against it
- `POST /api/projects` `{profile:{…wizard answers}}` → `{project:{id,…}, memory:{status}}`; stores profile, then calls `memory.api.ingest_project_profile(org_id, project_id, profile)` (W1) so the profile becomes prime memory; sends "project created" email
- `GET /api/projects`, `GET|PATCH /api/projects/{id}`
- `POST /api/projects/{id}/invites` `{email, role}` → Resend invite email
- `GET /api/projects/{id}/overview` → `{project, counts:{drawings,rfisOpen,permitsActive,holdPoints,observations,documents,chunks}, recent:[…activity]}` (P1 counts from site.db; other projects from app.db)

### Memory (W1)
- `POST /api/memory/search` `{query, projectId?, scopes?:["global","project"], k?:8}` → `{rewrittenQuery, abstain, hits:[{chunkId, docId, title, section, source, url, category, text, vectorScore, bm25Rank, rrfScore, rerankScore, citation}]}`
- `POST /api/memory/ask` `{query, projectId, sessionId?}` → `{answer, speech, abstain, confidence, citations:[{title, section, citation, url}], rewrittenQuery, hits}`
- `GET /api/memory/stats?projectId=` → `{corpora:[{scope, name, documents, chunks, lastIngested}], graph:{nodes, edges}, models:{embedding, reranker, llm, vectorStore, graphStore}}`
- `GET /api/memory/graph?projectId=&q=&limit=150` → `{nodes:[{id,label,type}], edges:[{source,target,label}]}`
- `GET /api/memory/documents?projectId=` → `[{docId, title, category, source, chunks, status, createdAt}]`

### Ingest (W1)
- `POST /api/ingest/file` multipart `file, projectId, category?` (PDF, DOCX, XLSX/CSV, TXT/MD, images → OCR if available) → `{jobId, docId, status}`
- `POST /api/ingest/text` `{projectId, title, text, category?}` → same
- `POST /api/ingest/voice` multipart `audio, projectId, title?` → Sarvam STT → `{transcript, jobId, docId}`
- `GET /api/ingest/jobs?projectId=` → `[{jobId, docId, title, status:queued|parsing|embedding|graph|done|error, progress, error}]`

### Voice (W5)
- `POST /api/stt` unchanged request/response shape, now Sarvam.

## 5. Memory scopes
- `global` datasets: `kb_templates` (550 InfraLens QA/QC/PMC templates + fields), `kb_is_codes`,
  `kb_prices_sor` (prices, steel, SOR, rate analysis — tabular; BM25 + vector, **no** LLM graph extraction),
  `kb_handbook` (thumb rules, handbook, knowledge, glossary/term).
- Project datasets: `org_<orgId>__proj_<projectId>` (profile, uploaded docs, text, voice notes, observations).
- Every chunk row carries `scope, org_id, project_id, dataset, doc_id, source, url, category, section, page, content_hash, embedding_version`.
- Search for a project = its project dataset + global datasets; never another org's data.

## 6. Design tokens (W3 defines in globals.css; W4 uses the same names)

Theme via `data-theme="light|dark"` on `<html>` (default: system), toggle persisted in localStorage.
CSS variables: `--bg`, `--bg-elev`, `--surface`, `--surface-2`, `--glass` (translucent fill),
`--glass-border`, `--glass-highlight`, `--text`, `--text-2`, `--text-3`, `--border`, `--accent`,
`--accent-2`, `--ok`, `--warn`, `--danger`, `--ring`, `--shadow-lg`, `--radius`, `--radius-lg`,
`--ease`. Utility classes: `.glass` (Liquid-Glass panel: backdrop-filter blur+saturate, inner highlight,
hairline border), `.glass-strong`, `.card`, `.kbd`. Fonts stay Inter / Instrument Serif / Geist Mono.
Existing landing and `/demo` must keep working (they are dark; don't break them).

## 7. Order
1. W6 crawl (background) · W1 memory on current site.db corpus · W2 tenancy · W3 dashboard · W4 onboarding — parallel now.
2. W5 voice once Sarvam research lands.
3. W1 ingests IS codes / prices / handbook as W6 finishes.
4. Integration: run all services, golden eval (`scripts/eval_memory.py`), 10/10 scenarios, browser check light+dark.
