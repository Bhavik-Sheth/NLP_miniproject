# Vesper v2 — current-state note

Recorded: 2026-09-16

## Authoritative close-out state

The project is marked **closed for feature work** in [PROGRESS.md](PROGRESS.md) and [README.md](../../README.md).
`main` is at `a646b96` (Neo4j documentation correction), following `9972bbb` (write-only Neo4j
graph backup). The only working-tree change at the time of this note is `data/site.db`; it is a
binary database change and has not been attributed or committed here.

## What is complete

- **Safety engine and data:** 550 template records, P1 plus the synthetic Nashik `NSK` project,
  deterministic drawing/RFI/permit/hold-point checks, and zero wrong logs in P1 10/10 and NSK 8/8 scenarios.
- **Multi-project operation:** `projectId` is enforced through backend routes, LiveKit metadata and
  `Brain(project_id)`, the dashboard cache/voice UI, site-record storage and project-scoped memory.
- **Memory:** local hybrid retrieval using bge-m3/LanceDB, SQLite FTS5, RRF, reranking and abstention;
  close-out reports 20,734 chunks / 7,365 documents, recall@8 1.000 and no project-scope leaks.
- **Graph and mirrors:** local Cognee/Ladybug graph; Supabase Postgres/pgvector/FTS mirror with
  `scripts/export_to_supabase.py`; Neo4j Aura is a write-only backup via
  `scripts/export_graph_to_neo4j.py`. Local SQLite + LanceDB remain authoritative.
- **Product surface:** Clerk organization tenancy, 12-step project onboarding, uploads/text/voice
  ingestion, dashboard/Ask-memory UI, Sarvam STT + normaliser, Sarvam/Rime TTS fallback, SpeechBrain
  write gate, Resend templates, MCP JSON-RPC/API tools, and a static public demo.

## Evidence and source-of-truth documents

| Area | Primary evidence |
| --- | --- |
| Overall status and known follow-ups | [PROGRESS.md](PROGRESS.md) |
| Product, architecture and local runbook | [README.md](../../README.md), [ARCHITECTURE.md](../../ARCHITECTURE.md) |
| Nashik seed, scoping and spoken acceptance lines | [W8.md](reports/W8.md) |
| Retrieval quality and scope isolation | [W1.md](reports/W1.md) |
| Supabase mirror | [export_to_supabase.py](../../scripts/export_to_supabase.py) |
| Neo4j backup | [export_graph_to_neo4j.py](../../scripts/export_graph_to_neo4j.py) |

## Deliberate follow-ups, not release blockers

- Rotate the Supabase password and any credentials previously shared in chat.
- Complete a human live-microphone NSK call using the 15 lines in W8.
- Re-measure post-Sarvam voice latency and publish the W5 STT report.
- Configure a verified Resend sender domain for mail beyond the account owner.
- Optional: improve the non-blocking dashboard hook lint findings, tenancy revocation/webhook support,
  and Neo4j operational monitoring.

## Documentation reconciliation

The final sentence in [W8.md](reports/W8.md) says Cognee/Supabase were future W9/W10 work. That line
predates the 2026-09-16 close-out. The later README, PROGRESS board, Supabase exporter and Neo4j exporter
are the current record; the W8 footer should not be used as a status signal.
