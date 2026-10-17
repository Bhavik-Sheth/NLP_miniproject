# Vesper as an MCP server

Vesper exposes its site record, project memory and contradiction engine as **tools** that any agent can call.
The same tools are available two ways, served by the backend (`backend/routes/tools.py`):

| Surface | Endpoint | Use it for |
|---|---|---|
| MCP (JSON-RPC 2.0, Streamable HTTP) | `POST /mcp` | Claude Desktop / Claude Code / Cursor / any MCP client |
| Plain REST | `GET /api/tools`, `POST /api/tools/{name}` | Scripts, webhooks, other agent frameworks |

Every tool is a thin in-process call to an existing REST endpoint, so **auth, tenancy, project scoping, abstention
and logging rules are identical** to the dashboard and the voice agent. Nothing new to secure.

## Tools

| Tool | Read-only | Arguments | Backed by |
|---|---|---|---|
| `list_projects` | yes | — | `GET /api/me` |
| `project_overview` | yes | `projectId` | `GET /api/projects/{id}/overview` |
| `search_memory` | yes | `query`, `projectId?`, `k?` (1–20) | `POST /api/memory/search` |
| `ask_memory` | yes | `query`, `projectId?` | `POST /api/memory/ask` |
| `list_drawings` | yes | `projectId` | `GET /api/drawings` |
| `list_rfis` | yes | `projectId` | `GET /api/rfis` |
| `list_permits` | yes | `projectId` | `GET /api/permits` |
| `list_observations` | yes | `projectId` | `GET /api/observations` |
| `get_observation` | yes | `projectId`, `id` | `GET /api/observations/{id}` |
| `memory_graph` | yes | `projectId`, `q?`, `limit?` | `GET /api/memory/graph` |
| `check_site_statement` | **no** | `projectId`, `text`, `sessionId?`, `language?` | `POST /api/session` + `POST /api/turn` |

`check_site_statement` runs a spoken or typed statement (English or Hinglish) through the contradiction engine
(revisions, tolerances, permits, hold points). It returns a `sessionId`; pass it back for follow-ups and
corrections. It can create a pending observation when the user confirms a log, so it is annotated
`readOnlyHint: false`. Full JSON Schemas: `GET /api/tools`.

Seeded projects: `P1` (Pithoragarh District Hospital) and `NSK` (Nashik Civil Hospital).

## Protocol

`POST /mcp` implements protocol version `2025-06-18`, single JSON responses (no SSE stream, no batching):

| Method | Result |
|---|---|
| `initialize` | `protocolVersion`, `serverInfo`, `capabilities.tools`, `instructions` |
| `notifications/initialized` (any message without `id`) | `202 Accepted` |
| `ping` | `{}` |
| `tools/list` | `{ tools: [...] }` |
| `tools/call` | `{ content: [{type:"text", text}], structuredContent, isError }` |

Errors: unknown method `-32601`, unknown tool `-32602`, parse error `-32700`. Tool failures (403, 404 project not
found, 422 missing argument) come back as `isError: true` with the HTTP status in the text, per MCP.

## Auth

| Mode | When | Send |
|---|---|---|
| Local dev | `CLERK_JWT_ISSUER` empty | nothing, or `X-Vesper-User` / `X-Vesper-Org` / `X-Vesper-Role` headers |
| Production | `CLERK_JWT_ISSUER` set | `Authorization: Bearer <Clerk session JWT>` |

The forwarded headers are exactly `Authorization` and `X-Vesper-*`. The org is always taken from the verified
project row, never from tool arguments, so a caller cannot read another org's project by guessing an id.

## Try it

```bash
curl -s localhost:8000/mcp -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

```bash
curl -s localhost:8000/mcp -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"ask_memory","arguments":{"query":"Who is the structural consultant?","projectId":"NSK"}}}'
```

```bash
curl -s localhost:8000/api/tools/check_site_statement -H 'Content-Type: application/json' -d '{"projectId":"NSK","text":"Zone C level 4 lift core mein welding chal rahi hai, hot work okay log kar do"}'
```

Verified 2026-09-16: `ask_memory` on NSK → "Sthapatya Structural Engineers"; `check_site_statement` → `state: blocked`
(HWP-2031 fire watcher pending); unknown project → `isError: true`, `404: project not found`.

## Connect a client

**Claude Code** (local backend):

```bash
claude mcp add --transport http vesper http://127.0.0.1:8000/mcp
```

**Claude Desktop / Cursor** (`mcpServers` config):

```json
{ "mcpServers": { "vesper": { "type": "http", "url": "http://127.0.0.1:8000/mcp" } } }
```

## Going live tomorrow — checklist

1. Deploy the backend behind HTTPS (the static Cloudflare demo has no backend; `/mcp` needs the FastAPI app).
2. Set `CLERK_JWT_ISSUER` so every call needs a Clerk JWT; issue the MCP client a long-lived token or put an
   OAuth 2.1 proxy in front (MCP authorization spec) — the backend only needs the resulting Bearer JWT.
3. Add the public origin to CORS if a browser-based client will call it.
4. Rate-limit `/mcp` and `/api/tools/*` at the proxy (memory ask ≈ 0.5 s; rerank is the cost).
5. If a client needs SSE (`Accept: text/event-stream`) or batching, wrap `run_tool()` with the official
   `mcp` Python SDK (`FastMCP`) — tool names, schemas and handlers stay the same.
6. Register in the client with the public URL, then run `tools/list` and one `ask_memory` call as a smoke test.
