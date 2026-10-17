"""Identity for every v2 route (PLAN §3).

Deployment: verifies the Clerk session JWT (RS256 via JWKS, issuer CLERK_JWT_ISSUER). Active
organization comes from the v2 claim ``o`` ({id, rol, slg, per, fpm}; ``rol`` has no ``org:`` prefix)
or the deprecated v1 claims ``org_id`` / ``org_role`` (``org:admin``). Email is read from an ``email``
custom session claim if the Clerk dashboard adds one.

Local dev (CLERK_JWT_ISSUER empty): headers X-Vesper-User (default ``local-demo``), X-Vesper-Org
(default ``org_local_demo``; send an empty value for "no active org"), X-Vesper-Role (default
``admin``), X-Vesper-Email (optional).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

import jwt
from fastapi import HTTPException, Request
from jwt import PyJWKClient

import config

from .appdb import DEMO_PROJECT_ID, connect


@dataclass
class Identity:
    user_id: str
    org_id: str | None
    org_role: str | None
    email: str | None


_jwks_client: PyJWKClient | None = None
_cache: dict[str, tuple[dict, float]] = {}


def _jwks() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(f"{config.CLERK_JWT_ISSUER}/.well-known/jwks.json", cache_keys=True, lifespan=3600)
    return _jwks_client


def _norm_role(role: str | None) -> str | None:
    if not role:
        return None
    return str(role).removeprefix("org:")


def identity_from_claims(claims: dict) -> Identity:
    """Pure mapping, unit-tested: supports Clerk session token v2 (`o`) and v1 (`org_id`)."""
    sub = str(claims.get("sub") or "")
    if not sub:
        raise HTTPException(401, "invalid sign-in token")
    o = claims.get("o")
    if isinstance(o, str):  # defensive: some templates stringify
        try:
            o = json.loads(o)
        except ValueError:
            o = None
    org_id = org_role = None
    if isinstance(o, dict) and o.get("id"):
        org_id, org_role = str(o["id"]), _norm_role(o.get("rol"))
    elif claims.get("org_id"):
        org_id, org_role = str(claims["org_id"]), _norm_role(claims.get("org_role"))
    email = claims.get("email") or claims.get("primary_email") or None
    return Identity(user_id=sub, org_id=org_id, org_role=org_role, email=str(email).lower() if email else None)


def get_identity(request: Request) -> Identity:
    """FastAPI dependency: `ident: Identity = Depends(get_identity)`."""
    if not config.CLERK_JWT_ISSUER:
        h = request.headers
        org = h.get("X-Vesper-Org")
        org = "org_local_demo" if org is None else (org.strip() or None)
        email = (h.get("X-Vesper-Email") or "").strip().lower() or None
        return Identity(user_id=h.get("X-Vesper-User", "local-demo"), org_id=org,
                        org_role=_norm_role(h.get("X-Vesper-Role", "admin")) if org else None, email=email)
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "sign in is required")
    now = time.time()
    hit = _cache.get(token)
    if hit and hit[1] > now:
        return identity_from_claims(hit[0])
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], issuer=config.CLERK_JWT_ISSUER,
                            options={"verify_aud": False}, leeway=5)
    except jwt.PyJWTError as exc:
        # The client only ever sees "invalid sign-in token"; the reason (expired, wrong issuer,
        # unknown signing key) belongs in the server log, where it is the difference between
        # "sign in again" and "the issuer is misconfigured".
        print(f"clerk auth rejected: {type(exc).__name__}: {exc}", flush=True)
        raise HTTPException(401, "invalid sign-in token") from exc
    parties = [p.strip() for p in os.getenv("CLERK_AUTHORIZED_PARTIES", "").split(",") if p.strip()]
    if parties and claims.get("azp") and claims["azp"] not in parties:
        raise HTTPException(401, "invalid sign-in token")
    if len(_cache) > 2048:
        _cache.clear()
    _cache[token] = (claims, float(claims.get("exp") or now + 30))
    return identity_from_claims(claims)


def project_access(project: dict, ident: Identity, conn=None) -> str | None:
    """Returns 'admin' | 'member' | 'demo' (read-only) | None (no access)."""
    if ident.org_id and project["org_id"] == ident.org_id:
        if project["id"] == DEMO_PROJECT_ID:
            return "demo"
        return "admin" if ident.org_role == "admin" else "member"
    own = conn or connect()
    try:
        row = own.execute("SELECT role FROM project_members WHERE project_id = ? AND (user_id = ? OR (email <> '' AND email = ?))",
                          (project["id"], ident.user_id, ident.email or "\x00")).fetchone()
    finally:
        if conn is None:
            own.close()
    if row:
        return "admin" if row["role"] in ("owner", "manager") else "member"
    if project["id"] == DEMO_PROJECT_ID:
        return "demo"
    return None


def require_project(project_id: str, ident: Identity, write: bool = False) -> dict:
    """404 if the project does not exist or is invisible to the caller (no existence leak across orgs);
    403 if visible but read-only and `write` is requested. Returns the row as a dict with `profile`
    (parsed) and `access`."""
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            raise HTTPException(404, "project not found")
        project = dict(row)
        access = project_access(project, ident, conn)
    finally:
        conn.close()
    if access is None:
        raise HTTPException(404, "project not found")
    if write and access == "demo":
        raise HTTPException(403, "the demo project is read-only")
    project["access"] = access
    try:
        project["profile"] = json.loads(project.pop("profile_json") or "{}")
    except ValueError:
        project["profile"] = {}
    return project
