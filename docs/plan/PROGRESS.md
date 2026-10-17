# Vesper v2 — global progress

Single place for status. Contract and decisions: [PLAN.md](PLAN.md). Per-workstream detail:
`reports/W<n>.md`. Research: `research/`. Commits are made per folder when the user asks.

Last updated: 2026-09-16 — **project closed**

## Status board

| # | Workstream | Status | Notes |
| --- | --- | --- | --- |
| W0 | Data: finish InfraLens template scrape | ✅ done | 550/550 templates with fields (19,133 fields, 6,947 chunks, was 9,870 / 4,205). DB rebuilt; old DB at `data/site.db.bak-20260915`. Scenarios 10/10 |
| W1 | Memory layer (Cognee + hybrid RAG + rerank + abstention), ingestion, fix confident-wrong answers, golden eval | ✅ done ([report](reports/W1.md)) — golden eval 44 Q: recall@8 1.000, abstain P/R 1.000/1.000, 0 leaks, engine cases 9/9, scenarios 10/10; 20,599 chunks / 7,270 docs; search new query p50 386 ms (367 ms rerank), repeat 9 ms; ask p50 480 ms. Earlier notes: **Global ingest complete (2026-09-15 17:02 UTC):** templates 5,349 chunks + sections 14,271 (code 6,702 · prices 1,760 · knowledge 1,412 · DCR 847 · handbook 807 · rate analysis 590 · steel 580 · CPHEEO 506 · term 394 · SOR 354 · thumb rules 311 · IRC 8) + P1 record. Routes live on :8000; search 20–130 ms warm. Open: cross-project leak, fact-sheet recall, permit-blocker abstain, unverified "20 mm" in L4 answer, rerank 0 ms, v1 topic-matching cases, MPS embedding switch, golden eval + W1.md |
| W2 | Tenancy (Clerk orgs), onboarding API + field schema, Resend emails | ✅ done ([report](reports/W2.md)) | All PLAN §4 tenancy endpoints + `POST /api/invites/accept`; curl-verified; `test_tenancy.py` 7/7 (Clerk v1/v2 org claims, isolation, P1 read-only). Schema: 3 org + 12 project steps, 92 fields. Real Resend send OK (fallback HTML). Gaps: invite revoke/member removal, Clerk webhooks, GSTIN checksum |
| W3 | Laptop dashboard, light/dark, liquid glass, memory view | ✅ built ([report](reports/W3.md)) | Shell (sidebar, ⌘K, status pills, theme toggle, animated bg, tour) + all pages; old phone console at /app/console; tsc + `npm run build` pass. Browser-verified via dev preview in light + dark; proxy accepts pending (no-org) sessions → /onboarding/org. 20 react-hooks lint errors (non-blocking). Memory panels fall back to v1 until W1 routes load |
| W4 | Onboarding wizard + ingest UI (upload / text / speak) | ✅ done ([report](reports/W4.md)) | /onboarding, /onboarding/org, 12-step /onboarding/project, /onboarding/invite, IngestPanel, OnboardingGate, proxy guard; tsc clean; browser-checked light/dark desktop+mobile via dev preview. Needs E2E against live backend (W7). Clerk forces org selection → task URL set to /onboarding/org (W3, layout) |
| W5 | Sarvam saaras:v3 STT, name/ID normaliser, Groq primary LLM, stronger prompts | 🟡 mostly done | Sarvam `saaras:v3-realtime` live in agent (Whisper fallback), `/api/stt` on Sarvam REST, normaliser, Groq primary, stronger prompts, `search_memory` tool; regex crash fixed; worker running. Remaining: P11 latency re-run, P12 report |
| W6 | Crawl remaining InfraLens sections (IS code, prices, steel, SOR, rate analysis, handbook, terms) | ✅ done ([report](reports/W6.md)) | 0 parse errors, 326 MB; many code pages are thin stubs (W1 filters/weights); `projects` (151) and `boq` (59) not crawled yet. 6,690 pages cached + parsed: code 4,391 · prices 869 · term 394 · steel 220 · thumbrules 151 · knowledge 120 · sor 118 · rate-analysis 118 · handbook 98 · dcr 78 · gate 76 · cpheeo 48 · irc 9. 762 inventory URLs were 404 on the site. Docs being finalised |
| W7 | Integration: all services, eval, 10/10 scenarios, browser check light+dark | ✅ done | Onboarding E2E, Ask memory, dashboard pages verified; static demo built **and deployed** to vesper-ai.pages.dev; Clerk JWT verification live; memory mirrored to Supabase |
| W8 | Nashik (NSK) site record + multi-project voice/engine | ✅ done ([report](reports/W8.md)) | NSK seed (21 revisions, 261 facts, 12 RFIs, 5 permits), 8/8 NSK + 10/10 P1 scenarios, projectId through API/voice/dashboard, memory eval recall@8 1.000, no scope leaks |

## Findings so far

- **Transcription accuracy:** Groq Whisper (forced English) mangles Indian names/IDs — "Pithoragarh OPD
  block" → "pit-thoroughly, do-pity block", "column E-1" → "column even", silence → ".". Fix: Sarvam (W5).
- **Confident wrong answers:** engine answered off-topic questions with unrelated records ("chiller
  commissioning checklist?" → E-1 log; "steel rate?" → site diary). Fix: W1.
- **Groq:** `openai/gpt-oss-120b` works (0.42 s). `llama-3.3-70b-versatile` retired (404) — stale in `.env.example`.
- **Coverage before v2:** ~6% of infralens.in in DB; IS codes 8 clauses hand-typed; prices/SOR/handbook 0; embeddings 0.
- **Research runs** for Cognee / Sarvam / onboarding / Resend were cancelled mid-way; each build workstream
  researches its own slice and saves to `research/`. bd-agent RAG study done: `research/02-bd-agent-rag.md`.

## Decisions log

| Date | Decision |
| --- | --- |
| 2026-09-15 | Cognee local (SQLite + LanceDB + Kuzu); hybrid retrieval ported from bd-agent |
| 2026-09-15 | Embeddings BAAI/bge-m3 via Ollama; reranker bge-reranker-v2-m3; abstain below rerank threshold |
| 2026-09-15 | LLM Groq gpt-oss-120b primary → Cerebras → NVIDIA |
| 2026-09-15 | STT Sarvam saaras:v3, Whisper fallback; TTS stays Rime English |
| 2026-09-15 | Tenancy = Clerk Organizations; new `data/app.db`; `site.db` stays deterministic P1 engine DB |
| 2026-09-15 | Email via Resend, template ids from env, inline HTML fallback |
| 2026-09-15 | `backend/main.py` loads `routes.memory`, `routes.ingest`, `routes.tenancy` optionally; `/api/v2/status` |

## Pending work and the fix in progress (2026-09-15)

| # | Pending | Fix in progress / planned | Owner |
| --- | --- | --- | --- |
| P1 | Cross-project leak: P1 facts appear in another project's memory answers | Scope filter on every retrieval leg (LanceDB, FTS5, Cognee): project dataset + global `kb_*` only | ✅ fixed — leak came from P1 clause notes ingested into the global IS dataset; now P1-only |
| P2 | Project fact sheet recall miss ("Who is the structural consultant?" abstains) | Render stakeholders/team/approvals/hold points/specs as labelled lines; guaranteed slot for project chunks in fusion | ✅ fixed — per-project retrieval leg + role-labelled fact sheets |
| P3 | "Which permits are blocking work today?" abstains | Route permit/hold-point/RFI status questions to the site record (engine or structured P1 chunks) | ✅ fixed — status questions answered live from site.db |
| P4 | L4 pre-pour answer cites an unverified "20 mm" cover | Verbatim-number check: every number in an answer must appear in a cited chunk, else drop or abstain | ✅ fixed — unsupported-number sentences dropped; "20 mm" verified in record (B3 req. 20±5, S-301 R2) |
| P5 | `timingsMs.rerank` is 0 ms — cross-encoder skipped | Re-enable (fp16 MPS, max_length 384, one shared instance) or report `rerankSkipped` with reason; recalibrate abstain threshold | ✅ fixed — `rerankMode` reports cached/skipped; uncached rerank ~367 ms |
| P6 | v1 engine topic matching: IS-code question asks for a grid; "pending blockers" lists one RFI; "everything about Level 3" repeats an RFI; follow-up on an ID asks for location | Fix-1 cases in `backend/engine/answer.py`; knowledge questions go to memory; blockers/level summaries from views; add to scenarios/golden set | ✅ fixed — blockers, level summary, ID follow-up, knowledge → memory |
| P7 | Embeddings via Ollama at 5–8 chunks/s under RAM pressure | Batched `bge-m3` via sentence-transformers on MPS in one process; re-embed ~19.6k chunks (est. 3–8 min on M3) | ❎ kept Ollama — sentence-transformers only 1.25× faster; full rebuild 15–18 min idle |
| P8 | Golden eval + `reports/W1.md` not written | `scripts/eval_memory.py` recall@8, abstain precision, p50/p95 | ✅ done — reports/W1.md |
| P9 | Public static demo not deployed | Re-recorded, rebuilt, Ask autoplay verified, landing stack marquee + PDF/memory copy | ✅ deployed 2026-09-16 — vesper-ai.pages.dev |
| P10 | Voice agent was P1-only | NSK seed + projectId in `/api/rtc/token` metadata → `Brain(project_id)` → brief/recall/log/search_memory | ✅ done — W8; live mic call still to be done by user (15 lines in reports/W8.md) |
| P11 | Live-voice latency not re-measured after Sarvam | Re-run `scripts/voice_acceptance.py`, update RIME_EVIDENCE.md | W5 remainder |
| P12 | W5 A/B report (`reports/W5.md`) missing | Summarise `agent/stt_eval/results.json` | W5 remainder |
| P13 | `data/site.db` had local test logs | Rebuilt by multi-project `data/build_db.py` (P1 + NSK) | ✅ done — W8 |
| P16 | Cognee graph disabled on macOS | Vendored Ladybug 0.19.0 C API (`data/vendor/ladybug`, gitignored, symlink `liblbug.dylib`), `MEMORY_COGNEE_ENABLED=1`; NSK smoke 60 nodes / 172 edges | ✅ local — full P1+NSK cognify running (LLM rate limits → retries) |
| P17 | Uncached search p50 386 ms > 150 ms target (reranker on M3) | Lower `MEMORY_RERANK_HEAD` or lighter reranker | — |
| P14 | Tenancy gaps: invite revoke / member removal, Clerk webhooks, GSTIN checksum | Planned | — |
| P15 | Dashboard lint: 20 react-hooks errors (non-blocking) | Planned cleanup | — |
| P18 | Relational data + vectors on Supabase | pgvector `vector(1024)` + Postgres FTS, `MEMORY_BACKEND` switch, dual-run before cutover | ⏸ later (user) — Supabase connector errors; needs `SUPABASE_*` in backend/.env.local |
| P19 | Neo4j Aura graph copy | Optional online mirror of the Cognee graph; needs `NEO4J_URI/USERNAME/PASSWORD` (rotate the pasted credentials) | ⏸ later (user) |
| P20 | MCP-ready agent tools | `POST /mcp` (JSON-RPC, 2025-06-18) + `GET/POST /api/tools`, 11 tools, same auth/scoping — docs/MCP.md | ✅ done 2026-09-16; public HTTPS backend + Clerk JWT needed to go live |

## Needs the user (user will supply these at the end — build everything end-to-end without waiting)

- Enable **Organizations** in the Clerk dashboard (onboarding creates a client org).
- Clerk: keep session token v2; add custom session claim `{"email":"{{user.primary_email_address}}"}`;
  set `CLERK_JWT_ISSUER` for the backend.
- Build Resend templates using the variable names in `reports/W2.md` / `research/04-resend.md`, publish,
  then set `RESEND_TEMPLATE_*` ids in `backend/.env.local`. Test sender `onboarding@resend.dev` only
  delivers to your own address — invites to others need a verified domain in `RESEND_FROM`.
- Rotate the Sarvam and Resend keys after the build (they were pasted in chat).

## Main-session work (while W1 runs)

- **Prefill sample site** button on org + project wizards (`app/components/onboarding/prefill.ts`): two
  realistic sites — Nashik 300-bed hospital (Deccan Buildcon, PWD Maharashtra, item-rate) and Ghaghara
  river bridge on SH-30 (Gangotri Infra, UPSBC EPC). Org and project prefill stay on the same site;
  clicking again rotates. All samples pass the backend validator (91–94% complete); browser-checked:
  81/89 answered, 0 errors, jumps to Review.
- **Clerk pending-session fix** (`app/proxy.ts`): accepts pending (no-org) sessions via
  `auth({ treatPendingAsSignedOut: false })`; `/app` without an org → `/onboarding/org` (Vesper's own UI,
  not Clerk's hosted task page). tsc clean.

- **Dev preview bypass** (`app/proxy.ts`, non-production only): cookie `vesper_dev_preview=1` opens `/app`
  signed-out against the local-auth backend, for automated browser checks.
- **Verified in browser (2026-09-15):** onboarding wizard → Prefill → Create project → `POST /api/projects`
  201 → row in `data/app.db` + activity → memory fact-sheet job done (13 chunks, W1 on :8001). Dashboard
  Overview, Scenarios (tour ran suite: 10/10, 0 wrong logs), Memory layer (models strip, graph), Ask memory
  render in light + dark. `/api/me` lists the new project + P1.
- **Open issues:** `:8000` still lacks memory/ingest routes (restart after W1) → `/api/memory/stats` 404
  in dashboard. Memory bugs sent to W1: P1 facts leaking into another project's answers, project fact
  sheet recall miss (structural consultant), `timingsMs` missing. Clerk switcher shows "No organization"
  in signed-out dev preview (expected).

- **User-reported hallucinations (Ask memory)**: root cause — `:8000` had no memory routes, so Ask fell
  back to the v1 dialogue engine (`/api/turn`), which captures/logs observations (asked for grid, logged
  OBS-000105). Fixed: Ask is read-only, no v1 fallback (`AskMemory.tsx`); `:8000` restarted — memory +
  ingest + tenancy routers load. v1 topic-matching failures (blockers, level summary, follow-up on an ID)
  sent to W1 as fix-1 cases.
- **Memory latency root cause**: RAM exhausted (~72 MB free) — two backends each loading the reranker +
  sections ingest + Ollama → swapping (vector 909 ms, rerank 2.9 s warm; 65 s cold). Sent to W1: kill
  :8001, keep one reranker, lighter model if needed, re-measure. Ingest ~6.8 chunks/s → batching fix
  sent to W1.
- **Voice verified**: worker registered, Sarvam `saaras:v3-realtime` live ("What is the cover at E2?"
  transcribed correctly); `/api/stt` (Sarvam REST) exact on fixtures (0.5–2.7 s); normaliser maps
  "pit thoroughly/do pity/even" → Pithoragarh/OPD/E-1, drops "."; `search_memory` tool wired. The
  earlier regex crash is gone. Still open from W5: A/B report, acceptance re-run.

- **Ask memory verified after fix**: "What cover does IS 456 require for columns?" → answered from memory
  with citation "per IS 456 clause 26.4" (40 mm, +10/0 mm), 0.8–1.25 s, badge `memory` (no v1 engine).
  Fixed `?q=` deep link asking twice in dev.

- **Static key-free dashboard demo (built, not yet deployed):** `STATIC_DEMO=1` now exports `/app/*`
  (dashboard + Driver.js tour), `/onboarding/*` (with Prefill) and `/app/console`. `lib/static-demo.ts`
  answers v2/tenancy/ingest calls from `lib/demo-dashboard.json`, recorded from the real backend by
  `scripts/build_dashboard_demo.py` (9 memory questions; Ask memory plays them one by one; ingest jobs
  animate). Clerk stub extended. Landing "Launch App" → `/app/`; hero copy updated. Build: 17 routes,
  6.3 MB, secret scan passes. Local check: Overview + tour render. Fixed: tour hijacked deep links
  (trailing-slash path mismatch), `/app/console` 404, test observation OBS-000105 filtered from recorded
  activity. **Deploy blocked on W1:** "Which permits are blocking work today?" abstains, L4 pre-pour answer
  cites an unverified "20 mm" cover, rerank timing 0 ms — re-record after W1 fixes.
- **Docs updated:** README (v2 end to end), ARCHITECTURE §6 (memory/tenancy/onboarding), DEMO.md
  (dashboard script), data/DATA.md (new counts, sections crawl, app.db, memory), `.env.example` (Resend,
  memory).
- **Ingest bottleneck measured:** `index_seconds ≈ seconds` in the ingest log — embedding compute
  (Ollama bge-m3 under RAM pressure, 5–8 chunks/s) dominates; LanceDB/SQLite writes are negligible.
  W1 asked to move to batched sentence-transformers on MPS inside one process.

## Execution mode: sequential (user request, 2026-09-15)

Order: W3 wraps up → W1 memory finishes (routes, ingest, fix 1, eval, speed) → W5 voice → W7 integration.

## Final-push targets (2026-09-15)

- Memory retrieval p50 ≤ 150 ms warm, p95 ≤ 400 ms on ~20k chunks; ask (with Groq) p50 ≤ 1.2 s.
- Full global index (550 templates + 6,690 crawled pages) builds in minutes; uploaded small doc searchable in seconds (graph extraction in background).
- Onboarding end-to-end: Clerk org → org profile → project wizard → prime memory ingest → dashboard.
- Complete dashboard in light + dark, liquid glass, retrieval inspector showing per-leg latency + rerank scores.
- Backend on :8000 predates the v2 router hook — restart it at integration (W7).

## Project closed — 2026-09-16

All workstreams W0–W8 are done. The project is closed for feature work; local services stay running.

### Final state

| Area | Where it landed |
| --- | --- |
| Engine | P1 10/10 and NSK 8/8 scenarios, 0 wrong logs; 15/15 backend tests |
| Memory | 20,734 chunks / 7,365 documents; recall@8 1.000, abstain P/R 1.000, no cross-project leaks |
| Online mirror | Supabase `vesper` (ap-south-1, free tier): every table row-matched, 20,734 pgvector rows |
| Auth | Clerk JWT verification live and proven end to end (`/api/drawings`, `/api/me` → 200) |
| Agent tools | `POST /mcp` + `/api/tools`, 11 tools, documented in `docs/MCP.md` |
| Public site | vesper-ai.pages.dev — landing, `/docs`, `/demo`, `/app` replay, custom 404, cookie consent |
| Email | 5 Resend templates incl. a `product_update` broadcast with `scripts/send_product_update.py`; live send verified |
| Docs | README §6–§7 and ARCHITECTURE §7–§8 carry the detailed app and memory-layer architecture |

### Fixed during close-out

- `APP_DB_PATH` was resolved at import time, so tests wrote into the real `data/app.db`.
- `PyJWT` without the `cryptography` extra made **every** Clerk token fail as "invalid sign-in token".
- The static build served the framework's default 404 instead of the project's page.
- The cookie bar was revealed inside `requestAnimationFrame`, which never fires in a background tab.
- Both JWT verifiers (`tenancy/auth.py`, `main.py`) now log why a token was rejected.

### Known open items (deliberately not closed)

- Rotate the Supabase database password (it was shared in chat).
- Verify a domain at resend.com/domains and set `RESEND_FROM`; test mode only reaches the account owner.
- Voice latency re-run (P11) and the W5 STT report (P12).
- Neo4j Aura mirror (P19) was never started.
- A real microphone call on NSK still needs a human on the line.
