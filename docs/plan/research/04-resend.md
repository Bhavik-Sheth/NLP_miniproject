# 04 — Resend (W2)

SDK: `resend` **2.45.0** (PyPI), installed in backend/.venv. Call: `resend.Emails.send(params, {"idempotency_key": key})`.

## Sending by template (what `backend/emails/send.py` does when a template id env var is set)

```python
resend.Emails.send({
  "from": "Vesper <onboarding@resend.dev>",
  "to": ["someone@example.com"],
  "subject": "…",                         # optional, overrides the template default
  "template": {"id": "<template id or alias>", "variables": {"PROJECT_NAME": "…"}},
}, {"idempotency_key": "project_created/prj_ab12"})
```

- The template must be **published**. Don't send `html`, `text` or `react` together with `template`; the API returns a validation error.
- Variable keys can only use ASCII letters, digits and `_`, up to 50 characters. `FIRST_NAME`, `LAST_NAME`,
  `EMAIL` and `UNSUBSCRIBE_URL` are reserved. Values must be strings or numbers.
- Idempotency keys can be up to 256 characters and last 24 h. Ours are `<kind>/<entity id>`.
- `onboarding@resend.dev` only delivers to the Resend account owner's address. Verify a domain and set `RESEND_FROM` before inviting anyone else.

## Env vars

| Var | Meaning |
| --- | --- |
| `RESEND_API_KEY` | required, or emails are skipped (logged `skipped`) |
| `RESEND_FROM` | default `Vesper <onboarding@resend.dev>` |
| `RESEND_REPLY_TO` | optional |
| `RESEND_TEMPLATE_WELCOME` | template id for `welcome_org` |
| `RESEND_TEMPLATE_PROJECT_CREATED` | template id for `project_created` (e.g. `20ad030e-0b80-444a-a1a3-6f60a1cd9aee` once published) |
| `RESEND_TEMPLATE_INVITE` | template id for `project_invite` |
| `RESEND_TEMPLATE_INGEST` | template id for `ingest_complete` |
| `APP_URL` | base for links, default `http://localhost:3000` |
| `EMAIL_DISABLED=1` | skip all sends (tests) |

If a template env var is unset, the inline fallback HTML in `backend/emails/templates/<kind>.html` is used, wrapped in `_layout.html`.

## Template variables. Use exactly these names in the Resend editor as `{{{VAR}}}`

| kind | subject we send | variables |
| --- | --- | --- |
| `welcome_org` | `Welcome to Vesper, {ORG_NAME}` | `USER_NAME`, `ORG_NAME`, `DASHBOARD_URL` |
| `project_created` | `{PROJECT_NAME} is set up in Vesper` | `USER_NAME`, `ORG_NAME`, `PROJECT_NAME`, `PROJECT_CODE`, `PROJECT_TYPE` (label, e.g. "Hospital / healthcare"), `PROJECT_CITY` ("City, State"), `CLIENT_NAME`, `START_DATE` (YYYY-MM-DD), `MEMORY_STATUS` (queued/pending/done/error), `PROJECT_URL` |
| `project_invite` | `{INVITER_NAME} invited you to {PROJECT_NAME} on Vesper` | `INVITER_NAME`, `ORG_NAME`, `PROJECT_NAME`, `ROLE` (manager/engineer/viewer/member), `INVITE_URL` (`APP_URL/onboarding/invite?token=…`) |
| `ingest_complete` | `{DOCUMENT_TITLE} is now in {PROJECT_NAME} memory` | `PROJECT_NAME`, `DOCUMENT_TITLE`, `CHUNKS`, `STATUS`, `PROJECT_URL` |

`ingest_complete` is for W1: `from emails.send import send_email; send_email(to, "ingest_complete", {...}, f"ingest/{job_id}")`.

## Logging

Every attempt writes a row to `app.db.email_log(to_hash=sha256(lower(email)), template="<kind>:template|inline|none", status, provider_id, error)`.
The key is redacted from error strings. Sends run in FastAPI `BackgroundTasks`, so a failure never blocks or fails the request.

## URLs

- https://resend.com/docs/api-reference/emails/send-email
- https://resend.com/changelog/idempotency-keys
- https://resend.com/blog/engineering-idempotency-keys
- https://pypi.org/project/resend/
