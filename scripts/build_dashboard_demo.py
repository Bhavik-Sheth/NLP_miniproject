#!/usr/bin/env python3
"""Record the dashboard's API responses from a running local backend -> app/lib/demo-dashboard.json.

The public static build (scripts/build_static_demo.sh) has no backend and no keys, so the laptop
dashboard replays these recorded responses: the P1 overview, drawings/RFIs/permits, memory stats,
graph, documents, the onboarding schema, and real /api/memory/ask + /search results for a set of
demo questions. Every answer shown in the demo is one the memory layer actually produced.

    ./run-all.sh   # backend on :8000 with memory + tenancy routers loaded
    python3 scripts/build_dashboard_demo.py [--base http://127.0.0.1:8000]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "lib" / "demo-dashboard.json"
PROJECT = "P1"

QUESTIONS = [
    "What cover does IS 456 require for columns?",
    "What should I check before the L4 slab pour?",
    "Which permits are blocking work today?",
    "What does the chiller commissioning checklist cover?",
    "What is the minimum curing period for slabs?",
    "What changed in C-401 revision R2?",
    "C-5 level 3 pe rebar spacing kitna hai?",
    "What is the thumb rule for steel quantity in an RCC slab?",
    "What is today's gold price?",
]

SECRET = re.compile(r"(sk_(test|live)_|pk_(test|live)_|csk-|gsk_|nvapi-|re_[A-Za-z0-9]{8}|api[_-]?key)", re.I)


def call(base: str, path: str, body: dict | None = None, timeout: float = 180.0):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        method="POST" if body is not None else "GET",
        headers={"Content-Type": "application/json", "X-Vesper-User": "local-demo", "X-Vesper-Org": "org_local_demo"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    b = args.base

    status = call(b, "/api/v2/status")
    if status.get("routers", {}).get("routes.memory") != "ok":
        print(f"memory router not loaded: {status}", file=sys.stderr)
        return 1

    me = call(b, "/api/me")
    # the public demo shows only the seeded project, under a neutral demo identity
    me["projects"] = [p for p in me.get("projects", []) if p.get("id") == PROJECT]
    me["user"] = {"id": "demo-visitor", "email": None}

    # Recent activity must match the recorded phone demo (app/lib/demo-data.json): observations logged
    # locally while testing (e.g. by hand in the console) are dropped, not published.
    overview = call(b, f"/api/projects/{PROJECT}/overview")
    seeded = {o.get("observation_id") for o in json.loads((ROOT / "app" / "lib" / "demo-data.json").read_text()).get("observations", [])}
    overview["recent"] = [
        r for r in overview.get("recent", [])
        if not str(r.get("id") or r.get("title") or "").startswith("OBS-") or str(r.get("id") or r.get("title", "").split(" ")[0]) in seeded
    ]

    data: dict = {
        "recordedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "me": me,
        "overview": overview,
        "stats": call(b, f"/api/memory/stats?projectId={PROJECT}"),
        "graph": call(b, f"/api/memory/graph?projectId={PROJECT}&limit=150"),
        "documents": call(b, f"/api/memory/documents?projectId={PROJECT}"),
        "drawings": call(b, "/api/drawings"),
        "rfis": call(b, "/api/rfis"),
        "permits": call(b, "/api/permits"),
        "schema": call(b, "/api/onboarding/schema"),
        "asks": [],
    }

    for q in QUESTIONS:
        t0 = time.time()
        ask = call(b, "/api/memory/ask", {"query": q, "projectId": PROJECT})
        search = call(b, "/api/memory/search", {"query": q, "projectId": PROJECT, "k": 8, "scopes": ["global", "project"]})
        for h in search.get("hits", []):
            h["text"] = (h.get("text") or "")[:900]
        for h in ask.get("hits", []) or []:
            h["text"] = (h.get("text") or "")[:900]
        data["asks"].append({"query": q, "ask": ask, "search": search})
        print(f"  {time.time() - t0:5.1f}s  abstain={ask.get('abstain')}  {q}")

    text = json.dumps(data, ensure_ascii=False, indent=1)
    if SECRET.search(text):
        print("refusing to write: secret-like string in recorded responses", file=sys.stderr)
        return 1
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(text) // 1024} KB, {len(data['asks'])} questions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
