"""Tenancy tests. Run: cd backend && .venv/bin/python test_tenancy.py   (or .venv/bin/pytest test_tenancy.py)

Uses a throwaway app.db, local-dev header auth and EMAIL_DISABLED=1, and mounts only the tenancy router."""
from __future__ import annotations

import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="vesper-tenancy-")
os.environ["APP_DB_PATH"] = os.path.join(_tmp, "app.db")
os.environ["EMAIL_DISABLED"] = "1"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402

config.CLERK_JWT_ISSUER = ""  # force local header auth

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from routes.tenancy import router  # noqa: E402
from tenancy.auth import identity_from_claims  # noqa: E402
from tenancy.validate import validate  # noqa: E402

app = FastAPI()
app.include_router(router)
client = TestClient(app)

ORG_PROFILE = {"legalName": "Alpha Constructions Pvt Ltd", "companyType": "contractor", "city": "Pune", "state": "Maharashtra",
               "primaryContactName": "Asha", "primaryContactEmail": "asha@example.com", "gstin": "27AABCA1234B1Z5", "pan": "AABCA1234B"}
PROJECT = {"name": "Hinjewadi Tower A", "code": "HTA-01", "projectType": "commercial", "city": "Pune", "state": "Maharashtra",
           "clientName": "Alpha Realty", "startDate": "2026-10-01", "scheduledCompletion": "2028-03-31", "siteLeadName": "Ravi Kulkarni",
           "governingCodes": ["IS 456", "IS 1893"], "drawingConvention": "A-101, S-201", "pincode": "411057",
           "stakeholders": [{"role": "pmc", "company": "PMC Co", "email": "pm@example.com"}],
           "concreteGrades": [{"element": "Columns", "grade": "M30"}], "geo": {"lat": 18.59, "lng": 73.74}}


def H(user: str, org: str | None, role: str = "admin", email: str | None = None) -> dict:
    h = {"X-Vesper-User": user, "X-Vesper-Org": org or "", "X-Vesper-Role": role}
    if email:
        h["X-Vesper-Email"] = email
    return h


A = H("user_a", "org_A")
B = H("user_b", "org_B")


def test_claims_v1_v2():
    v2 = identity_from_claims({"sub": "user_1", "v": 2, "o": {"id": "org_2x", "rol": "admin", "slg": "acme"}})
    assert (v2.org_id, v2.org_role) == ("org_2x", "admin")
    v1 = identity_from_claims({"sub": "user_1", "org_id": "org_1x", "org_role": "org:member"})
    assert (v1.org_id, v1.org_role) == ("org_1x", "member")
    none = identity_from_claims({"sub": "user_1"})
    assert none.org_id is None and none.org_role is None


def test_auth_fallback_defaults():
    r = client.get("/api/me")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["user"]["id"] == "local-demo" and j["org"]["id"] == "org_local_demo" and j["authMode"] == "local"
    assert any(p["id"] == "P1" and p["readOnly"] for p in j["projects"])
    r = client.get("/api/me", headers=H("new_user", None))
    assert r.json()["org"] is None and r.json()["onboarding"] == {"orgDone": False, "projectDone": False}


def test_schema_endpoint():
    j = client.get("/api/onboarding/schema").json()
    assert j["org"]["steps"] and len(j["project"]["steps"]) >= 8


def test_org_create_and_validation():
    bad = client.post("/api/orgs", headers=A, json={"clerkOrgId": "org_A", "profile": {**ORG_PROFILE, "gstin": "BAD", "legalName": ""}})
    assert bad.status_code == 422
    keys = {e["key"] for e in bad.json()["errors"]}
    assert {"gstin", "legalName"} <= keys
    mismatch = client.post("/api/orgs", headers=A, json={"clerkOrgId": "org_A", "profile": {**ORG_PROFILE, "pan": "ZZZZZ9999Z"}})
    assert mismatch.status_code == 422
    r = client.post("/api/orgs", headers=A, json={"clerkOrgId": "org_A", "profile": ORG_PROFILE})
    assert r.status_code == 201, r.text
    assert r.json()["org"]["id"] == "org_A"
    r = client.post("/api/orgs", headers=B, json={"clerkOrgId": "org_B", "profile": {**ORG_PROFILE, "legalName": "Beta Infra", "gstin": "", "pan": ""}})
    assert r.status_code == 201, r.text
    assert client.get("/api/me", headers=A).json()["onboarding"]["orgDone"] is True
    assert client.get("/api/orgs/org_B", headers=A).status_code == 404


def test_project_create_validation():
    r = client.post("/api/projects", headers=A, json={"profile": {"name": "X"}})
    assert r.status_code == 422
    keys = {e["key"] for e in r.json()["errors"]}
    assert {"code", "projectType", "city", "state", "clientName", "startDate", "siteLeadName", "governingCodes", "drawingConvention"} <= keys
    r = client.post("/api/projects", headers=A, json={"profile": {**PROJECT, "pincode": "01234", "projectType": "spaceship",
                                                                  "scheduledCompletion": "2025-01-01", "stakeholders": [{"role": "pmc"}]}})
    keys = {e["key"] for e in r.json()["errors"]}
    assert {"pincode", "projectType", "scheduledCompletion", "stakeholders[0].company"} <= keys, keys
    assert client.post("/api/projects", headers=H("lonely", None), json={"profile": PROJECT}).status_code == 409
    # step-nested shape + label for a select are accepted
    clean, errs = validate("project", {"basics": {"name": "Nubra Clinic", "code": "N-1", "projectType": "Hospital / healthcare"},
                                       "location": {"city": "Leh", "state": "Ladakh"}}, partial=True)
    assert not errs and clean["projectType"] == "hospital"


def test_project_create_and_isolation():
    r = client.post("/api/projects", headers=A, json={"profile": PROJECT})
    assert r.status_code == 201, r.text
    body = r.json()
    pid = body["project"]["id"]
    assert body["memory"]["status"] in ("pending", "queued", "done", "error")
    assert client.post("/api/projects", headers=A, json={"profile": PROJECT}).status_code == 409  # duplicate code
    assert client.get(f"/api/projects/{pid}", headers=A).status_code == 200
    # org B cannot read, patch, invite or see org A's project
    assert client.get(f"/api/projects/{pid}", headers=B).status_code == 404
    assert client.get(f"/api/projects/{pid}/overview", headers=B).status_code == 404
    assert client.patch(f"/api/projects/{pid}", headers=B, json={"profile": {"name": "pwned"}}).status_code == 404
    assert client.post(f"/api/projects/{pid}/invites", headers=B, json={"email": "x@y.com"}).status_code == 404
    assert all(p["id"] != pid for p in client.get("/api/projects", headers=B).json())
    # another org_B user with admin role still cannot see it; the creator keeps owner access via membership
    assert client.get(f"/api/projects/{pid}", headers=H("user_x", "org_B")).status_code == 404
    assert client.get(f"/api/projects/{pid}", headers=H("user_a", "org_B")).status_code == 200
    # patch + overview
    r = client.patch(f"/api/projects/{pid}", headers=A, json={"profile": {"status": "on_hold", "seismicZone": "III"}})
    assert r.status_code == 200 and r.json()["project"]["status"] == "on_hold", r.text
    ov = client.get(f"/api/projects/{pid}/overview", headers=A).json()
    assert ov["counts"]["drawings"] == 0 and any(a["kind"] == "project_created" for a in ov["recent"])
    # invite -> accept by a user from another org grants access
    r = client.post(f"/api/projects/{pid}/invites", headers=A, json={"email": "eng@example.com", "role": "engineer"})
    assert r.status_code == 201, r.text
    from tenancy.appdb import connect
    token = connect().execute("SELECT token FROM invites WHERE id = ?", (r.json()["invite"]["id"],)).fetchone()[0]
    assert client.post("/api/invites/accept", headers=B, json={"token": token}).status_code == 200
    assert client.get(f"/api/projects/{pid}", headers=B).status_code == 200
    assert client.patch(f"/api/projects/{pid}", headers=H("user_c", "org_C"), json={"status": "active"}).status_code == 404


def test_demo_project_read_only():
    ov = client.get("/api/projects/P1/overview", headers=B)
    assert ov.status_code == 200, ov.text
    c = ov.json()["counts"]
    assert c["drawings"] > 0 and c["rfisOpen"] >= 1 and c["holdPoints"] >= 1
    assert client.patch("/api/projects/P1", headers=B, json={"name": "x"}).status_code == 403
    assert client.post("/api/projects/P1/invites", headers=H("local-demo", "org_local_demo"), json={"email": "a@b.co"}).status_code == 403


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {exc!r}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
