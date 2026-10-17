"""Send a product-update broadcast through Resend — the one email kind with no automatic trigger.

The transactional kinds (welcome_org, project_created, project_invite, ingest_complete) are sent by
the app when the event happens. A product update is something you decide to send, so it gets a CLI.

    # write the copy once
    scripts/product_update.json
    {
      "TAG": "Release · September",
      "HEADLINE": "Vesper now answers from your PDFs",
      "INTRO": "This month: document memory, an MCP server and a faster voice loop.",
      "ITEM_1_TITLE": "...", "ITEM_1_BODY": "...",
      "ITEM_2_TITLE": "...", "ITEM_2_BODY": "...",
      "ITEM_3_TITLE": "...", "ITEM_3_BODY": "...",
      "CTA_LABEL": "See what changed",
      "CTA_URL": "https://vesper-ai.pages.dev/docs/index.html"
    }

    # look before you send: renders to an HTML file, sends nothing
    backend/.venv/bin/python scripts/send_product_update.py --content scripts/product_update.json --preview

    # who would receive it
    backend/.venv/bin/python scripts/send_product_update.py --content ... --audience org-members --dry-run

    # send
    backend/.venv/bin/python scripts/send_product_update.py --content ... --audience org-members
    backend/.venv/bin/python scripts/send_product_update.py --content ... --to a@x.com --to b@y.com

Every send is rate-limited, idempotent per (recipient, headline) so a rerun cannot double-send, and
logged to app.db email_log with only a SHA-256 of the address.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

REQUIRED = ("HEADLINE", "INTRO", "CTA_LABEL", "CTA_URL")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def load_content(path: pathlib.Path) -> dict:
    data = json.loads(path.read_text())
    missing = [k for k in REQUIRED if not str(data.get(k) or "").strip()]
    if missing:
        raise SystemExit(f"content file is missing required keys: {', '.join(missing)}")
    return data


def audience_from_db(kind: str) -> list[tuple[str, str]]:
    """[(email, name)] from app.db. Demo rows and blank addresses are skipped."""
    from tenancy.appdb import DEMO_ORG_ID, connect

    conn = connect()
    try:
        if kind == "org-members":
            rows = conn.execute(
                "SELECT DISTINCT email, user_id FROM org_members WHERE email IS NOT NULL AND email != '' "
                "AND org_id != ?", (DEMO_ORG_ID,)).fetchall()
        elif kind == "project-members":
            rows = conn.execute(
                "SELECT DISTINCT email, user_id FROM project_members WHERE email IS NOT NULL AND email != ''"
            ).fetchall()
        else:
            raise SystemExit(f"unknown audience {kind}")
        # Seeded and test rows use reserved example domains; Resend rejects them outright, so a
        # real broadcast should never try. Filter them out rather than collecting failures.
        placeholder = ("example.com", "example.org", "example.net", "test.com")
        out = []
        for r in rows:
            email = (r[0] or "").strip()
            if not EMAIL_RE.match(email) or email.lower().rsplit("@", 1)[-1] in placeholder:
                continue
            out.append((email, r[1] or "there"))
        return out
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", required=True, type=pathlib.Path, help="JSON file with the copy")
    ap.add_argument("--to", action="append", default=[], help="explicit recipient (repeatable)")
    ap.add_argument("--audience", choices=["org-members", "project-members"], help="pull recipients from app.db")
    ap.add_argument("--preview", action="store_true", help="render to an HTML file and exit; sends nothing")
    ap.add_argument("--dry-run", action="store_true", help="list recipients and exit; sends nothing")
    ap.add_argument("--delay", type=float, default=0.6, help="seconds between sends (default 0.6)")
    args = ap.parse_args()

    content = load_content(args.content)

    from emails.send import render_inline, send_email

    if args.preview:
        out = args.content.with_name(args.content.stem + "_preview.html")
        subject, page = render_inline("product_update", {**content, "USER_NAME": "there"})
        out.write_text(page)
        print(f"subject: {subject}")
        print(f"preview: {out}")
        return 0

    recipients: list[tuple[str, str]] = [(e.strip(), "there") for e in args.to if EMAIL_RE.match(e.strip())]
    bad = [e for e in args.to if not EMAIL_RE.match(e.strip())]
    if bad:
        raise SystemExit(f"not valid addresses: {', '.join(bad)}")
    if args.audience:
        recipients += audience_from_db(args.audience)
    # de-duplicate, keeping the first name seen for an address
    seen: dict[str, str] = {}
    for email, name in recipients:
        seen.setdefault(email.lower(), name)
    recipients = sorted(seen.items())

    if not recipients:
        raise SystemExit("no recipients — pass --to or --audience")

    print(f"{len(recipients)} recipient(s) for: {content['HEADLINE']}")
    if args.dry_run:
        for email, _ in recipients:
            print("  ", email)
        print("dry run — nothing sent")
        return 0

    # The idempotency key is stable for a given headline, so re-running after a partial failure
    # resends only what Resend has not already accepted.
    tag = hashlib.sha256(str(content["HEADLINE"]).encode()).hexdigest()[:12]
    sent = failed = skipped = 0
    for i, (email, name) in enumerate(recipients):
        res = send_email(email, "product_update", {**content, "USER_NAME": name},
                         idempotency_key=f"product_update/{tag}/{hashlib.sha256(email.encode()).hexdigest()[:12]}")
        status = res.get("status")
        sent += status == "sent"
        failed += status == "failed"
        skipped += status == "skipped"
        print(f"  [{i + 1}/{len(recipients)}] {email} -> {status}" + (f" ({res.get('error')})" if res.get("error") else ""))
        if i + 1 < len(recipients):
            time.sleep(args.delay)

    print(f"done: {sent} sent, {failed} failed, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
