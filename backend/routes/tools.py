"""Agent tools API — the MCP-ready surface of Vesper. Docs: docs/MCP.md.

Two ways in, same tools, same auth and project scoping as the dashboard:

  GET  /api/tools              tool manifest (MCP `tools/list` shape: name, description, inputSchema, annotations)
  POST /api/tools/{name}       call one tool with a JSON body -> {"ok", "tool", "result"}
  POST /mcp                    MCP JSON-RPC 2.0 over Streamable HTTP (initialize, ping, tools/list, tools/call)

Every tool is a thin in-process call to an existing REST endpoint (httpx ASGI transport), so tenancy checks,
project scoping, abstention and logging rules are exactly the ones the voice agent and dashboard already use.
The caller's Authorization / X-Vesper-* headers are forwarded unchanged.
"""
from __future__ import annotations

import json
import sys
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

router = APIRouter()

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "vesper", "title": "Vesper site memory", "version": "2.0.0"}
FORWARD_HEADERS = ("authorization", "x-vesper-user", "x-vesper-org", "x-vesper-role", "x-vesper-email")

_PID = {"type": "string", "description": "Project id, e.g. P1 (Pithoragarh) or NSK (Nashik). See list_projects."}
_RO = {"readOnlyHint": True, "openWorldHint": False}

TOOLS: list[dict[str, Any]] = [
    {"name": "list_projects", "title": "List projects",
     "description": "Projects the caller can access, with ids, names and the caller's role.",
     "inputSchema": {"type": "object", "properties": {}}, "annotations": _RO},
    {"name": "project_overview", "title": "Project overview",
     "description": "KPIs, blockers (unmet permit checks, open hold points) and recent activity for one project.",
     "inputSchema": {"type": "object", "properties": {"projectId": _PID}, "required": ["projectId"]},
     "annotations": _RO},
    {"name": "search_memory", "title": "Search project memory",
     "description": "Hybrid retrieval (bge-m3 vectors + BM25, RRF fusion, cross-encoder rerank) over IS codes, "
                    "QA/QC templates, uploaded PDFs/documents and the project's site record. Returns cited passages.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "minLength": 1, "maxLength": 1000}, "projectId": _PID,
         "k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8}}, "required": ["query"]},
     "annotations": _RO},
    {"name": "ask_memory", "title": "Ask project memory",
     "description": "Grounded short answer with citations. Abstains ('not in the record') when retrieval is weak; "
                    "numbers not present in the sources are removed.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "minLength": 1, "maxLength": 1000}, "projectId": _PID}, "required": ["query"]},
     "annotations": _RO},
    {"name": "list_drawings", "title": "List drawings",
     "description": "Drawing register with every revision, status and which revision is latest For Construction.",
     "inputSchema": {"type": "object", "properties": {"projectId": _PID}, "required": ["projectId"]},
     "annotations": _RO},
    {"name": "list_rfis", "title": "List RFIs", "description": "RFIs with status, question, response and linked drawings.",
     "inputSchema": {"type": "object", "properties": {"projectId": _PID}, "required": ["projectId"]},
     "annotations": _RO},
    {"name": "list_permits", "title": "List permits",
     "description": "Work permits (hot work, excavation, lifting …) with mandatory checks and blocking status.",
     "inputSchema": {"type": "object", "properties": {"projectId": _PID}, "required": ["projectId"]},
     "annotations": _RO},
    {"name": "list_observations", "title": "List observations", "description": "Logged site observations, newest first.",
     "inputSchema": {"type": "object", "properties": {"projectId": _PID}, "required": ["projectId"]},
     "annotations": _RO},
    {"name": "get_observation", "title": "Get observation",
     "description": "One observation with its evidence trail (drawing revision, facts, permits checked).",
     "inputSchema": {"type": "object", "properties": {"projectId": _PID, "id": {"type": "string"}},
                     "required": ["projectId", "id"]}, "annotations": _RO},
    {"name": "memory_graph", "title": "Knowledge graph",
     "description": "Cognee knowledge-graph nodes and edges for a project, optionally filtered by a term.",
     "inputSchema": {"type": "object", "properties": {"projectId": _PID, "q": {"type": "string", "maxLength": 200},
                                                      "limit": {"type": "integer", "minimum": 10, "maximum": 600}},
                     "required": ["projectId"]}, "annotations": _RO},
    {"name": "check_site_statement", "title": "Check a site statement",
     "description": "Run a spoken/typed site statement (English or Hinglish) through the contradiction engine — "
                    "drawing revisions, tolerances, permits, hold points. Pass the returned sessionId back for "
                    "follow-ups and corrections. May create a pending observation when the user confirms a log.",
     "inputSchema": {"type": "object", "properties": {
         "projectId": _PID, "text": {"type": "string", "minLength": 1, "maxLength": 2000},
         "sessionId": {"type": "string", "description": "Omit to start a new conversation."},
         "language": {"type": "string", "default": "en-IN"}}, "required": ["projectId", "text"]},
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}},
]
_BY_NAME = {t["name"]: t for t in TOOLS}


def _app():
    main = sys.modules.get("main") or sys.modules.get("__main__")
    app = getattr(main, "app", None)
    if app is None:
        raise HTTPException(503, "tools API needs the Vesper backend app")
    return app


async def _call(request: Request, method: str, path: str, *, params: dict | None = None, body: dict | None = None):
    headers = {k: v for k, v in request.headers.items() if k.lower() in FORWARD_HEADERS}
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://vesper.local", timeout=180) as c:
        r = await c.request(method, path, params={k: v for k, v in (params or {}).items() if v is not None},
                            json=body, headers=headers)
    try:
        data = r.json()
    except ValueError:
        data = {"detail": r.text[:500]}
    if r.status_code >= 400:
        raise HTTPException(r.status_code, data.get("detail") if isinstance(data, dict) else data)
    return data


def _need(args: dict, *keys: str) -> None:
    missing = [k for k in keys if not str(args.get(k) or "").strip()]
    if missing:
        raise HTTPException(422, f"missing required argument(s): {', '.join(missing)}")


async def run_tool(request: Request, name: str, args: dict) -> Any:
    tool = _BY_NAME.get(name)
    if not tool:
        raise HTTPException(404, f"unknown tool '{name}'")
    _need(args, *tool["inputSchema"].get("required", []))
    pid = args.get("projectId")
    if name == "list_projects":
        me = await _call(request, "GET", "/api/me")
        return {"projects": me.get("projects", []), "user": me.get("user")}
    if name == "project_overview":
        return await _call(request, "GET", f"/api/projects/{pid}/overview")
    if name == "search_memory":
        return await _call(request, "POST", "/api/memory/search",
                           body={"query": args["query"], "projectId": pid, "k": int(args.get("k") or 8)})
    if name == "ask_memory":
        return await _call(request, "POST", "/api/memory/ask", body={"query": args["query"], "projectId": pid})
    if name in ("list_drawings", "list_rfis", "list_permits", "list_observations"):
        return await _call(request, "GET", "/api/" + name.removeprefix("list_"), params={"projectId": pid})
    if name == "get_observation":
        return await _call(request, "GET", f"/api/observations/{args['id']}", params={"projectId": pid})
    if name == "memory_graph":
        return await _call(request, "GET", "/api/memory/graph",
                           params={"projectId": pid, "q": args.get("q"), "limit": args.get("limit")})
    # check_site_statement
    sid = args.get("sessionId") or (await _call(request, "POST", "/api/session", body={"projectId": pid}))["sessionId"]
    res = await _call(request, "POST", "/api/turn", body={"sessionId": sid, "text": args["text"], "projectId": pid,
                                                           "language": args.get("language") or "en-IN"})
    return {"sessionId": sid, **(res if isinstance(res, dict) else {"result": res})}


@router.get("/api/tools")
def list_tools() -> dict:
    return {"server": SERVER_INFO, "protocolVersion": PROTOCOL_VERSION, "mcpEndpoint": "/mcp", "tools": TOOLS}


@router.post("/api/tools/{name}")
async def call_tool(name: str, request: Request) -> dict:
    try:
        args = await request.json()
    except ValueError:
        args = {}
    return {"ok": True, "tool": name, "result": await run_tool(request, name, args if isinstance(args, dict) else {})}


def _rpc(id_: Any, result: Any = None, error: dict | None = None) -> dict:
    return {"jsonrpc": "2.0", "id": id_, **({"error": error} if error else {"result": result})}


@router.post("/mcp")
async def mcp(request: Request):
    try:
        msg = await request.json()
    except ValueError:
        return JSONResponse(_rpc(None, error={"code": -32700, "message": "parse error"}), status_code=400)
    if isinstance(msg, list):
        return JSONResponse({"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32600, "message": "batching is not supported"}}, status_code=400)
    method, id_, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if id_ is None:  # notification (e.g. notifications/initialized)
        return JSONResponse(None, status_code=202)
    if method == "initialize":
        return _rpc(id_, {"protocolVersion": PROTOCOL_VERSION, "serverInfo": SERVER_INFO,
                          "capabilities": {"tools": {"listChanged": False}},
                          "instructions": "Vesper answers from a construction project's verified site record. "
                                          "Call list_projects first; pass projectId to every project tool."})
    if method == "ping":
        return _rpc(id_, {})
    if method == "tools/list":
        return _rpc(id_, {"tools": TOOLS})
    if method == "tools/call":
        try:
            out = await run_tool(request, params.get("name", ""), params.get("arguments") or {})
            text = json.dumps(out, ensure_ascii=False, default=str)
            return _rpc(id_, {"content": [{"type": "text", "text": text}],
                              "structuredContent": out if isinstance(out, dict) else {"result": out},
                              "isError": False})
        except HTTPException as e:
            if e.status_code == 404 and str(e.detail).startswith("unknown tool"):
                return _rpc(id_, error={"code": -32602, "message": str(e.detail)})
            return _rpc(id_, {"content": [{"type": "text", "text": f"{e.status_code}: {e.detail}"}], "isError": True})
    return _rpc(id_, error={"code": -32601, "message": f"method not found: {method}"})
