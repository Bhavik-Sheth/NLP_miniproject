"""Ingest API (W1) — PLAN §4. Writes need project write access (the P1 demo is read-only -> 403).

Small files and text are parsed, chunked, embedded and indexed inside the request (searchable on return);
the knowledge graph (Cognee) is built in the background and the job moves graph -> done.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from memory import api as mem
from tenancy.auth import Identity, get_identity, require_project

router = APIRouter()
MAX_UPLOAD = 50 * 1024 * 1024
MAX_AUDIO = 25 * 1024 * 1024


class TextBody(BaseModel):
    projectId: str
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=2_000_000)
    category: str | None = None


@router.post("/api/ingest/file")
async def ingest_file(file: UploadFile = File(...), projectId: str = Form(...), category: str | None = Form(None),
                      ident: Identity = Depends(get_identity)) -> dict:
    p = require_project(projectId, ident, write=True)
    data = await file.read()
    if not data:
        raise HTTPException(422, "empty file")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "file too large (50 MB max)")
    try:
        return await run_in_threadpool(lambda: mem.ingest_file(
            org_id=p["org_id"], project_id=p["id"], filename=file.filename or "upload.txt", data=data,
            category=category, added_by=ident.user_id, email=ident.email))
    except ValueError as e:
        raise HTTPException(415, str(e)) from e


@router.post("/api/ingest/text")
async def ingest_text(body: TextBody, ident: Identity = Depends(get_identity)) -> dict:
    p = require_project(body.projectId, ident, write=True)
    try:
        return await run_in_threadpool(lambda: mem.ingest_text(
            org_id=p["org_id"], project_id=p["id"], title=body.title, text=body.text, category=body.category,
            added_by=ident.user_id, email=ident.email))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/api/ingest/voice")
async def ingest_voice(audio: UploadFile = File(...), projectId: str = Form(...), title: str | None = Form(None),
                       ident: Identity = Depends(get_identity)) -> dict:
    p = require_project(projectId, ident, write=True)
    data = await audio.read()
    if not data:
        raise HTTPException(422, "empty audio")
    if len(data) > MAX_AUDIO:
        raise HTTPException(413, "audio too large")
    try:
        return await run_in_threadpool(lambda: mem.ingest_voice(
            org_id=p["org_id"], project_id=p["id"], audio=data, filename=audio.filename or "note.webm",
            title=title, content_type=audio.content_type, added_by=ident.user_id, email=ident.email))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except RuntimeError as e:  # provider not configured / upstream failure; message carries no secrets
        raise HTTPException(502, str(e)[:200]) from e


@router.get("/api/ingest/jobs")
def ingest_jobs(projectId: str = Query(...), ident: Identity = Depends(get_identity)) -> list[dict]:
    p = require_project(projectId, ident)
    return mem.jobs(org_id=p["org_id"], project_id=p["id"])
