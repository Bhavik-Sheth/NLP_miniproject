"""Acceptance-scenario runner. Python port of app/lib/scenarios.ts.

Always runs against a temp COPY of site.db, never the live one.
Used by  POST /api/scenarios/run  and by  python -m scenarios  (CLI).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import config
import db as dbmod

_STD_NOISE = {"none", "low", "medium", "high"}
SEED_DIR = Path(config.BACKEND_DIR).parent / "data" / "seed"
SCENARIOS_JSON = SEED_DIR / "scenarios.json"


def _scenario_path(project_id: str) -> Path:
    """Return the suite for a project while keeping the original P1 filename stable."""
    project = (project_id or "P1").strip().upper()
    if not re.fullmatch(r"[A-Z0-9_-]+", project):
        raise ValueError(f"invalid project id: {project_id!r}")
    return SCENARIOS_JSON if project == "P1" else SEED_DIR / f"scenarios_{project.lower()}.json"


def load_scenarios(project_id: str | None = None) -> list[dict]:
    project = project_id or config.PROJECT_ID
    path = Path(os.getenv("SCENARIOS_PATH") or _scenario_path(project))
    if not path.is_file():
        raise FileNotFoundError(f"scenario suite for project {project!r} not found: {path}")
    raw = json.loads(path.read_text("utf-8"))
    return raw if isinstance(raw, list) else raw.get("scenarios", [])


def _temp_db_copy(src: str) -> str:
    d = tempfile.mkdtemp(prefix="vesper-scn-")
    dst = os.path.join(d, "site.db")
    s = sqlite3.connect(src)
    s.execute(f"VACUUM INTO '{dst.replace(chr(39), chr(39)*2)}'")
    s.close()
    return dst


def _norm_decision(d: str | None) -> str:
    return "cancelled" if d == "cancel" else (d or "none")


def run_scenario(repo: dbmod.Repo, sc: dict) -> dict:
    from engine.dialogue import DialogueSession

    session_id = dbmod.create_session(repo, f"scenario {sc['id']}")
    session = DialogueSession(repo, session_id, llm=None, persist_turns=True)

    transcript: list[dict] = []
    failures: list[str] = []
    kinds_seen: set[str] = set()
    clarified_kinds: set[str] = set()
    clarified = False
    final_decision = "none"

    for t in sc.get("turns", []):
        noise = t.get("noise") if t.get("noise") in _STD_NOISE else "none"
        transcript.append({"role": "user", "text": t["user"],
                           "bargeIn": bool(t.get("barge_in")), "noise": t.get("noise")})
        turn = session.handle(text=t["user"], barge_in=bool(t.get("barge_in")), noise=noise)
        transcript.append({"role": "agent", "text": turn["reply"]["text"], "state": turn["state"]})

        for k in list(turn.get("contradictions", [])) + list(turn.get("blockers", [])) + list(turn.get("missing", [])):
            kinds_seen.add(k["kind"])
        logged = turn.get("logged")
        low_conf = turn.get("lowConfidence", [])
        if not logged and (turn.get("clarifiedKinds") or turn["state"] in ("challenging", "blocked")
                           or (turn["state"] == "confirming" and low_conf)):
            clarified = True
            for k in turn.get("clarifiedKinds", []):
                clarified_kinds.add(k)
        if logged:
            final_decision = _norm_decision(logged.get("decision"))
            for k in [x["kind"] for x in list(turn.get("contradictions", [])) + list(turn.get("blockers", []))]:
                if k not in clarified_kinds:
                    failures.append(f"logged with {k} that was never clarified first")

    rows = repo._all(
        "SELECT * FROM field_observations WHERE session_id = ? ORDER BY created_at", (session_id,))

    # ---- global safety invariants
    for r in rows:
        if r.get("drawing_id") and not repo.is_verified_latest(str(r["drawing_id"])):
            failures.append(f"logged non-latest drawing {r['drawing_id']}")
        if r.get("location_id") and not repo.location_exists(str(r["location_id"])):
            failures.append(f"logged unknown location {r['location_id']}")
        if int(r.get("contradiction_flag") or 0) == 1 and not r.get("clarification_asked"):
            failures.append(f"{r['observation_id']} flagged but no clarification_asked")

    e = sc.get("expect", {}) or {}
    kinds = sorted(kinds_seen)
    flag_kinds = [k for k in kinds if k != "missing_critical_field"]
    if e.get("contradiction") is True and not kinds:
        failures.append("expected a contradiction, none detected")
    if e.get("contradiction") is False and flag_kinds:
        failures.append(f"unexpected contradictions: {','.join(flag_kinds)}")
    for k in e.get("kinds", []) or []:
        if k not in kinds_seen:
            failures.append(f"missing kind {k} (saw {','.join(kinds) or 'none'})")
    if e.get("must_ask_clarification") and not clarified:
        failures.append("no clarification was asked")
    if e.get("no_log") and rows:
        failures.append(f"no_log expected but {len(rows)} row(s) written")

    last = rows[-1] if rows else None
    got_decision = str(last["final_decision"]) if last else final_decision
    if e.get("final_decision"):
        accept = e.get("accept_final_decisions") or [e["final_decision"]]
        if got_decision not in {_norm_decision(x) for x in accept} | set(accept):
            failures.append(f"final_decision {got_decision} != expected {e['final_decision']}")
    if e.get("must_not_log_decision") and last and str(last["final_decision"]) == e["must_not_log_decision"]:
        failures.append(f"logged forbidden decision {e['must_not_log_decision']}")

    if e.get("logged") and not e.get("no_log"):
        if not last:
            failures.append("expected a logged row, none written")
        else:
            colmap = {"drawing_id": "drawing_id", "location_id": "location_id", "element": "element",
                      "attribute": "attribute", "value": "value_claimed", "unit": "unit",
                      "revision_claimed": "revision_claimed"}
            for k, col in colmap.items():
                want = e["logged"].get(k)
                if want is None:
                    continue
                got = last.get(col)
                ok = (abs(float(got) - want) < 1e-6) if isinstance(want, (int, float)) and got is not None else (want == got)
                if not ok:
                    failures.append(f"logged {k}={got} != expected {want}")
    if e.get("forbidden_logged") and last:
        for k, bad in e["forbidden_logged"].items():
            col = {"drawing_id": "drawing_id", "location_id": "location_id"}.get(k, k)
            if str(last.get(col) or "").startswith(str(bad)):
                failures.append(f"logged {k}={last.get(col)} is forbidden ({bad})")

    return {
        "id": sc["id"], "title": sc["title"], "pass": not failures, "failures": failures,
        "kindsSeen": kinds, "clarified": clarified,
        "finalDecision": got_decision, "logged": rows, "transcript": transcript,
    }


def run_all(ids: list[str] | None = None, project_id: str | None = None) -> dict:
    project = (project_id or config.PROJECT_ID).strip().upper()
    scs = load_scenarios(project)
    if ids:
        scs = [s for s in scs if s["id"] in ids]
    copy = _temp_db_copy(config.SITE_DB_PATH)
    conn = dbmod.connect(copy)
    repo = dbmod.Repo(conn, project)
    results = []
    try:
        for sc in scs:
            results.append(run_scenario(repo, sc))
    finally:
        conn.close()
        shutil.rmtree(os.path.dirname(copy), ignore_errors=True)
    passed = sum(1 for r in results if r["pass"])
    wrong = sum(1 for r in results for f in r["failures"]
                if "non-latest" in f or "unknown location" in f or f.startswith("logged "))
    return {"projectId": project, "passed": passed, "total": len(results),
            "wrongLogs": wrong, "results": results}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run deterministic voice acceptance scenarios")
    parser.add_argument("ids", nargs="*", help="optional scenario IDs (default: all)")
    parser.add_argument("--project", default=config.PROJECT_ID,
                        help="project suite and database scope (default: PROJECT_ID or P1)")
    args = parser.parse_args()
    out = run_all(args.ids or None, project_id=args.project)
    w = lambda s, n: (s[: n - 1] + "…") if len(s) > n else s.ljust(n)
    print(f"{w('ID',5)} {w('RESULT',7)} {w('TITLE',46)} {w('KINDS SEEN',40)} {w('DECISION',14)}")
    print("-" * 120)
    for r in out["results"]:
        print(f"{w(r['id'],5)} {w('PASS' if r['pass'] else 'FAIL',7)} {w(r['title'],46)} "
              f"{w(','.join(r['kindsSeen']) or '-',40)} {w(r['finalDecision'],14)}")
        for f in r["failures"]:
            print(f"      x {f}")
    print("-" * 120)
    print(f"{out['passed']}/{out['total']} passed  ·  wrong drawing/dimension/location logs: {out['wrongLogs']}")
    sys.exit(0 if out["passed"] == out["total"] else 1)
