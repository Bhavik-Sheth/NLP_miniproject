"""Smoke test for the post-STT normaliser. Run before (re)starting the worker:

    agent/.venv/bin/python agent/stt_eval/test_normalize.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import stt_normalize  # noqa: E402  (compiles every regex at import)
import worker_prompts  # noqa: E402

CASES = [
    (".", ""),
    ("...", ""),
    ("Thank you.", ""),
    ("pit-thoroughly, do-pity block", "Pithoragarh, OPD block"),
    ("Pithorgad OPD block column even cover", "Pithoragarh OPD block column E-1 cover"),
    ("What is the cover at even?", "What is the cover at E-1?"),
    ("What is the cover, everyone?", "What is the cover, E-1?"),
    ("Is RFI 50 still open", "Is RFI-050 still open"),
    ("excavation permit EXC 41", "excavation permit EXC-0041"),
    ("O P D block", "OPD block"),
    ("R W 1 retaining wall", "RW-1 retaining wall"),
    ("Pithoragar OPD block", "Pithoragarh OPD block"),
    ("Teesari Manzil pe C5 Column", "teesri Manzil pe C5 Column"),
    ("tisri manjil par", "tisri manzil par"),
    # must NOT change
    ("I have an even number of bars", "I have an even number of bars"),
    ("Pittsburgh", "Pittsburgh"),
    ("Everyone clear the slab", "Everyone clear the slab"),
    ("E1 column cover measured 30 millimeters.", "E1 column cover measured 30 millimeters."),
]


def main() -> int:
    bad = 0
    for raw, want in CASES:
        got = stt_normalize.normalize(raw).text
        if got != want:
            bad += 1
            print(f"FAIL {raw!r}: got {got!r}, want {want!r}")
    assert worker_prompts.sarvam_keyterms(), "empty keyterms"
    print(f"{len(CASES) - bad}/{len(CASES)} normaliser cases pass")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
