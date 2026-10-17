# 01 — Cognee (W1 findings, 2026-09-15)

Sources: https://github.com/topoteretes/cognee (README, CLAUDE.md, cognee/skill.md), https://docs.cognee.ai,
PyPI https://pypi.org/project/cognee/ , installed source of cognee 1.5.4.

## Version / install
- Latest: **cognee 1.5.4**, `requires_python >=3.10,<3.15` → Python 3.13 OK.
- Pins that conflict with our backend venv: `openai` (litellm 1.96 → openai 2.x, backend has 3.11), `websockets<16`,
  `starlette>=0.48`, `uvicorn<1`. **Decision:** install in `backend/.venv-cognee`; Vesper runs Cognee as a
  subprocess worker (`backend/memory/cognee_worker.py`) and never imports it in the API process.
- Graph DB default is now **Ladybug** (the maintained Kuzu fork). `GRAPH_DATABASE_PROVIDER=kuzu` maps to the same
  adapter (`get_graph_engine.py`: `provider in ("ladybug","kuzu")`). Wheel `ladybug==0.19.0` on Darwin ≥24.

## Local config (env, read by pydantic settings before `import cognee`)
| Setting | Value used |
|---|---|
| `SYSTEM_ROOT_DIRECTORY` / `DATA_ROOT_DIRECTORY` | `data/memory/cognee/system`, `data/memory/cognee/data` (also `cognee.config.system_root_directory()`) |
| `DB_PROVIDER` | `sqlite` |
| `VECTOR_DB_PROVIDER` | `lancedb` (default) |
| `GRAPH_DATABASE_PROVIDER` | `kuzu` (→ Ladybug) |
| `LLM_PROVIDER=custom`, `LLM_MODEL=groq/openai/gpt-oss-120b`, `LLM_ENDPOINT=https://api.groq.com/openai/v1`, `LLM_API_KEY` | custom = LiteLLM with `api_base` (GenericAPIAdapter) |
| `FALLBACK_MODEL=cerebras/gpt-oss-120b`, `FALLBACK_ENDPOINT`, `FALLBACK_API_KEY` | LLMConfig fallback fields |
| `LLM_RATE_LIMIT_ENABLED/REQUESTS/INTERVAL` | `true / 20 / 60` (Groq free-tier friendly) |
| `EMBEDDING_PROVIDER=ollama`, `EMBEDDING_MODEL=bge-m3:latest`, `EMBEDDING_ENDPOINT=http://localhost:11434/api/embed`, `EMBEDDING_DIMENSIONS=1024`, `HUGGINGFACE_TOKENIZER=BAAI/bge-m3` | same engine as Vesper's own index |
| `STRUCTURED_OUTPUT_FRAMEWORK` | default `litellm_native` (no instructor) |
| `TELEMETRY_DISABLED=1` | |
| `ENABLE_BACKEND_ACCESS_CONTROL` | default = on when vector+graph support it (lancedb+kuzu do) → one DB per dataset/user. We set `false` (single graph) and enforce scope in Vesper; datasets are tagged with `node_set=[dataset, category]` |

## API surface used
- `await cognee.add(data, dataset_name="kb_is_codes", node_set=["kb_is_codes","is_code"])` — text, file path, URL, lists.
- `await cognee.cognify(datasets=[...])` — `incremental_loading=True` (only new data), `data_per_batch=20`,
  `chunk_size`, `run_in_background`.
- `await cognee.search(query_text, query_type=SearchType.X, datasets=[...], node_name=[...], top_k, session_id)`.
  Types: `GRAPH_COMPLETION` (default), `RAG_COMPLETION`, `CHUNKS`, `SUMMARIES`, `TEMPORAL`, `INSIGHTS`-style graph,
  plus auto-routing `cognee.recall()`; `cognee.remember()` = add+cognify+improve.
- Sessions: `session_id=` on search/remember → session cache (`CACHE_BACKEND=sqlite|redis|fs`), synced to graph later.
- Datasets: `cognee.datasets.list_datasets()`, `empty_dataset`, `cognee.forget(dataset=...)`, `cognee.update(data_id=...)`.
- Permissions (multi-user mode): datasets are owned by users; grant read/write/share per dataset (fastapi-users
  based). Not used — Vesper's tenancy is Clerk orgs.
- Graph export: `(await get_graph_engine()).get_graph_data()` → `([(id, props)], [(src, dst, rel, props)])`.

## How Vesper uses it
- Hybrid retrieval (LanceDB + FTS5 + reranker) is Vesper's own and does **not** depend on Cognee (latency).
- Cognee builds the knowledge graph in the background for: project datasets (all), curated globals (IS 456/800/1893/
  13920/875 pages + site.db clauses, thumb rules, handbook, templates with hold points). Tabular datasets
  (prices/steel/SOR/rate analysis/DCR) are never cognified.
- Worker is bounded (`MEMORY_COGNIFY_MAX_DOCS`), resumable (`documents.graph_status` in app.db), backs off on 429,
  switches to Cerebras, and exports `data/memory/graph/graph.json` for `GET /api/memory/graph`.
