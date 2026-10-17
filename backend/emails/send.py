"""Transactional email via Resend.

send_email(to, kind, variables) never raises. If RESEND_TEMPLATE_<KIND> is set the email is sent by
template id with `variables`; otherwise an inline HTML fallback from templates/<kind>.html wrapped in
templates/_layout.html is sent. Every attempt is written to app.db email_log with a SHA-256 of the
recipient (never the address, never the key). Variable names per kind: docs/plan/research/04-resend.md.
"""
from __future__ import annotations

import hashlib
import html
import os
import re
from pathlib import Path
from typing import Any

import config  # noqa: F401  (loads .env and backend/.env.local)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

KINDS: dict[str, dict[str, Any]] = {
    "welcome_org": {
        "env": "RESEND_TEMPLATE_WELCOME",
        "subject": "Welcome to Vesper, {{ORG_NAME}}",
        "variables": ["USER_NAME", "ORG_NAME", "DASHBOARD_URL"],
    },
    "project_created": {
        "env": "RESEND_TEMPLATE_PROJECT_CREATED",
        "subject": "{{PROJECT_NAME}} is set up in Vesper",
        "variables": ["USER_NAME", "ORG_NAME", "PROJECT_NAME", "PROJECT_CODE", "PROJECT_TYPE", "PROJECT_CITY",
                      "CLIENT_NAME", "START_DATE", "MEMORY_STATUS", "PROJECT_URL"],
    },
    "project_invite": {
        "env": "RESEND_TEMPLATE_INVITE",
        "subject": "{{INVITER_NAME}} invited you to {{PROJECT_NAME}} on Vesper",
        "variables": ["INVITER_NAME", "ORG_NAME", "PROJECT_NAME", "ROLE", "INVITE_URL"],
    },
    "ingest_complete": {
        "env": "RESEND_TEMPLATE_INGEST",
        "subject": "{{DOCUMENT_TITLE}} is now in {{PROJECT_NAME}} memory",
        "variables": ["PROJECT_NAME", "DOCUMENT_TITLE", "CHUNKS", "STATUS", "PROJECT_URL"],
    },
    # Broadcast: product news and release notes. Three highlight slots; leave a slot's variables
    # empty and that card renders blank, so fill all three or trim the template for the send.
    "product_update": {
        "env": "RESEND_TEMPLATE_UPDATE",
        "subject": "{{HEADLINE}}",
        "variables": ["USER_NAME", "TAG", "HEADLINE", "INTRO",
                      "ITEM_1_TITLE", "ITEM_1_BODY", "ITEM_2_TITLE", "ITEM_2_BODY",
                      "ITEM_3_TITLE", "ITEM_3_BODY", "CTA_LABEL", "CTA_URL"],
    },
}

_VAR = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")


def app_url() -> str:
    return os.getenv("APP_URL", "http://localhost:3000").rstrip("/")


def _render(text: str, variables: dict[str, Any], escape: bool) -> str:
    def sub(m: re.Match) -> str:
        v = variables.get(m.group(1), "")
        v = "" if v is None else str(v)
        return html.escape(v) if escape else v
    return _VAR.sub(sub, text)


def render_inline(kind: str, variables: dict[str, Any]) -> tuple[str, str]:
    """(subject, html) for the inline fallback."""
    spec = KINDS[kind]
    body = _render((TEMPLATES_DIR / f"{kind}.html").read_text(), variables, escape=True)
    subject = _render(spec["subject"], variables, escape=False)
    layout = (TEMPLATES_DIR / "_layout.html").read_text()
    page = layout.replace("{{BODY}}", body).replace("{{SUBJECT}}", html.escape(subject))
    return subject, page


def _log(to: str, template: str, status: str, provider_id: str | None, error: str | None) -> None:
    try:
        from tenancy.appdb import connect, now_iso
        conn = connect()
        try:
            conn.execute("INSERT INTO email_log(to_hash, template, status, provider_id, error, created_at) VALUES (?,?,?,?,?,?)",
                         (hashlib.sha256(to.strip().lower().encode()).hexdigest(), template, status, provider_id,
                          (error or None) and error[:300], now_iso()))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def send_email(to: str, kind: str, variables: dict[str, Any], idempotency_key: str | None = None) -> dict:
    """Returns {status: sent|failed|skipped, providerId, mode: template|inline, error}. Never raises."""
    mode = "inline"
    try:
        if kind not in KINDS:
            raise ValueError(f"unknown email kind {kind}")
        spec = KINDS[kind]
        to = (to or "").strip()
        if not to or "@" not in to:
            _log(to or "-", f"{kind}:none", "skipped", None, "no recipient")
            return {"status": "skipped", "providerId": None, "mode": None, "error": "no recipient"}
        api_key = os.getenv("RESEND_API_KEY", "").strip()
        if not api_key or api_key.startswith("<") or os.getenv("EMAIL_DISABLED", "").lower() in ("1", "true", "yes"):
            _log(to, f"{kind}:none", "skipped", None, "email disabled or RESEND_API_KEY missing")
            return {"status": "skipped", "providerId": None, "mode": None, "error": "email disabled"}

        import resend
        resend.api_key = api_key
        clean = {k: ("" if v is None else v if isinstance(v, (int, float)) else str(v)[:2000]) for k, v in variables.items()}
        params: dict[str, Any] = {"from": os.getenv("RESEND_FROM", "Vesper <onboarding@resend.dev>"), "to": [to]}
        if os.getenv("RESEND_REPLY_TO"):
            params["reply_to"] = os.getenv("RESEND_REPLY_TO")
        template_id = os.getenv(spec["env"], "").strip()
        if template_id:
            mode = "template"
            params["subject"] = _render(spec["subject"], clean, escape=False)
            params["template"] = {"id": template_id, "variables": clean}
        else:
            params["subject"], params["html"] = render_inline(kind, clean)
        params["tags"] = [{"name": "kind", "value": kind}]
        options = {"idempotency_key": idempotency_key[:256]} if idempotency_key else None
        resp = resend.Emails.send(params, options) if options else resend.Emails.send(params)
        provider_id = (resp or {}).get("id") if isinstance(resp, dict) else getattr(resp, "id", None)
        _log(to, f"{kind}:{mode}", "sent", provider_id, None)
        return {"status": "sent", "providerId": provider_id, "mode": mode, "error": None}
    except Exception as exc:  # noqa: BLE001 - email must never break a request
        msg = type(exc).__name__ + ": " + str(exc)
        key = os.getenv("RESEND_API_KEY", "")
        if key:
            msg = msg.replace(key, "***")
        _log(to or "-", f"{kind}:{mode}", "failed", None, msg)
        return {"status": "failed", "providerId": None, "mode": mode, "error": msg[:300]}
