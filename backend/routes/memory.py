"""Memory API (W1) — PLAN §4. Auth: tenancy.auth.get_identity; project access: tenancy.auth.require_project.

A project-scoped call reads that project's dataset (org taken from the verified project row, never from
the request) plus the global knowledge datasets. Without projectId only global datasets are searched.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from memory import api as mem
from tenancy.auth import Identity, get_identity, require_project

router = APIRouter()
mem.warmup(background=True)  # load bge-m3 query path + reranker once, resume unfinished ingest jobs


class SearchBody(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    projectId: str | None = None
    scopes: list[str] | None = None
    k: int | None = 8
    sessionId: str | None = None


class AskBody(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    projectId: str | None = None
    sessionId: str | None = None


def _resolve(project_id: str | None, ident: Identity) -> tuple[str | None, str | None]:
    if not project_id:
        return ident.org_id, None
    p = require_project(project_id, ident)  # 404 when invisible to this caller
    return p["org_id"], p["id"]


def _scopes(scopes: list[str] | None, project_id: str | None) -> list[str]:
    allowed = [s for s in (scopes or ["global", "project"]) if s in ("global", "project")]
    if not project_id:
        allowed = [s for s in allowed if s == "global"]
    if not allowed:
        raise HTTPException(422, "scopes must include 'global' or (with projectId) 'project'")
    return allowed


@router.post("/api/memory/search")
def memory_search(body: SearchBody, ident: Identity = Depends(get_identity)) -> dict:
    org_id, pid = _resolve(body.projectId, ident)
    return mem.search(body.query, org_id=org_id, project_id=pid, scopes=_scopes(body.scopes, pid), k=body.k or 8,
                      session_id=body.sessionId)


@router.post("/api/memory/ask")
def memory_ask(body: AskBody, ident: Identity = Depends(get_identity)) -> dict:
    org_id, pid = _resolve(body.projectId, ident)
    session = f"{ident.user_id}:{body.sessionId}" if body.sessionId else None
    return mem.ask(body.query, org_id=org_id, project_id=pid, session_id=session,
                   scopes=_scopes(None, pid))


@router.get("/api/memory/stats")
def memory_stats(projectId: str | None = Query(None), ident: Identity = Depends(get_identity)) -> dict:
    org_id, pid = _resolve(projectId, ident)
    return mem.stats(org_id=org_id, project_id=pid)


@router.get("/api/memory/graph")
def memory_graph(projectId: str | None = Query(None), q: str | None = Query(None, max_length=200),
                 limit: int = Query(150, ge=10, le=600), ident: Identity = Depends(get_identity)) -> dict:
    org_id, pid = _resolve(projectId, ident)
    return mem.graph(org_id=org_id, project_id=pid, q=q, limit=limit)


@router.get("/api/memory/documents")
def memory_documents(projectId: str = Query(...), ident: Identity = Depends(get_identity)) -> list[dict]:
    org_id, pid = _resolve(projectId, ident)
    return mem.documents(org_id=org_id, project_id=pid)
