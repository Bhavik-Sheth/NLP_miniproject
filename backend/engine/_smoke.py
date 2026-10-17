"""Throwaway smoke test for the ported dialogue engine. Run from backend/:

    .venv/bin/python -m engine._smoke
"""
from __future__ import annotations

import db as dbmod
from engine.dialogue import DialogueSession


def _kinds(turn):
    return [c["kind"] for c in turn.get("contradictions", [])] + [b["kind"] for b in turn.get("blockers", [])]


def run_case(name, utterance, checks):
    conn = dbmod.connect()
    repo = dbmod.Repo(conn)
    # read-only: no create_session, no turn persistence -> leaves site.db untouched
    sess = DialogueSession(repo, "SMOKE-TEST", llm=None, persist_turns=False)
    turn = sess.handle(text=utterance)
    failures = []
    for label, ok in checks(turn):
        if not ok:
            failures.append(label)
    status = "PASS" if not failures else "FAIL"
    print(f"[{status}] {name}")
    print(f"       state={turn['state']} kinds={_kinds(turn)}")
    print(f"       reply={turn['reply']['text']!r}")
    if failures:
        print(f"       failed checks: {failures}")
    return not failures


def main():
    results = []

    results.append(run_case(
        "S01 revision mismatch",
        "haan toh column line C-5 pe rebar spacing 180 mm hai, drawing A 102 rev teen mein 200 mm dikh raha hai",
        lambda t: [
            ("state == challenging", t["state"] == "challenging"),
            ("revision_mismatch present", "revision_mismatch" in _kinds(t)),
            ("reply mentions R4", "R4" in t["reply"]["text"]),
            ("reply mentions RFI-047", "RFI-047" in t["reply"]["text"]),
        ],
    ))

    results.append(run_case(
        "S05 permit blocker",
        "Zone B level 3 mein welding chal rahi hai, sab theek hai, work ok log kar do",
        lambda t: [
            ("state == blocked", t["state"] == "blocked"),
            ("permit_blocker present", "permit_blocker" in _kinds(t)),
            ("allowedDecisions == stop_work/raise_ncr/cancel",
             t["allowedDecisions"] == ["stop_work", "raise_ncr", "cancel"]),
        ],
    ))

    results.append(run_case(
        "S10 unknown drawing",
        "C-4 column pe tie spacing 200 hai, drawing A-109 mein bhi 200 hi hai",
        lambda t: [
            ("unknown_drawing present", "unknown_drawing" in _kinds(t)),
            ("nothing logged", t.get("logged") is None
             and not any(e.startswith("observation_logged") for e in t.get("events", []))),
        ],
    ))

    print()
    print("ALL PASS" if all(results) else "SOME FAILED")
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
