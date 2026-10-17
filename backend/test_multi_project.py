"""Focused regressions for deterministic multi-project parsing and isolation."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import db
from engine.answer import answer
from engine.extract import extract


ROOT = Path(__file__).resolve().parent.parent


def _repo(project_id: str) -> db.Repo:
    conn = sqlite3.connect(ROOT / "data" / "site.db")
    conn.row_factory = sqlite3.Row
    return db.Repo(conn, project_id)


def test_grid_before_explicit_level_is_not_consumed_as_level():
    ex = extract("What is the cover at C-7 level 3?")
    assert ex.grid["value"] == "C-7"
    assert ex.level["value"] == "L3"


def test_nashik_cover_answer_uses_nashik_current_fact():
    repo = _repo("NSK")
    try:
        raw = "What is the cover at C-7 level 3?"
        result = answer(repo, raw, extract(raw), {})
        assert result["location_id"] == "NSK:C-7:L3"
        assert "40 mm" in result["text"]
        assert "SSB-STR-L3-201" in result["text"]
        assert "OBS-" not in result["text"]
    finally:
        repo.db.close()


def test_project_repositories_do_not_cross_read_locations_or_drawings():
    p1 = _repo("P1")
    nsk = _repo("NSK")
    try:
        assert p1.resolve_location({"grid": "C-7", "level": "L3"}) == []
        assert nsk.resolve_location({"grid": "E-1", "level": "L4"}) == []
        assert p1.latest_drawing("SSB-STR-L3-201") is None
        assert nsk.latest_drawing("S-301") is None
    finally:
        p1.db.close()
        nsk.db.close()
