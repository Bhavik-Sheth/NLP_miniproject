#!/usr/bin/env python3
"""Generate app/lib/demo-data.json — the scripted conversations behind the public /demo console.

Every reply, contradiction, blocker and logged row is REAL engine output: the flows below run
through backend/engine against a throw-away copy of data/site.db, so the demo can never show
a number the product would not say. Re-run after changing the engine or the seed:

    backend/.venv/bin/python scripts/build_demo_data.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp()) / "demo.db"
shutil.copy(ROOT / "data" / "site.db", tmp)
os.environ["SITE_DB_PATH"] = str(tmp)
sys.path.insert(0, str(ROOT / "backend"))

import config  # noqa: E402
import db as dbmod  # noqa: E402
from engine import memory  # noqa: E402
from engine.dialogue import DialogueSession  # noqa: E402

repo = dbmod.Repo(dbmod.connect(str(tmp)), config.PROJECT_ID)
DEMO_USER = "demo"

# Each flow: steps of {"text"} or {"decision"}. The first text step starts the flow in the UI.
FLOWS = {
    "pre_pour": [{"text": "What should I check before the L4 slab pour?"}],
    "cover_q": [{"text": "What is the cover at E-1?"}, {"text": "and at E-2?"}],
    "rfis": [{"text": "Any open RFIs?"}],
    "cover_ncr": [{"text": "E-1 column cover measured 30 mm"}, {"text": "what is the tolerance there?"},
                  {"decision": "raise_ncr"}],
    "revision": [{"text": "RW-1 wall thickness 350 mm as per C-401 revision R1"}, {"decision": "log_observation"}],
    "pour_block": [{"text": "Start the L4 slab pour now"}, {"decision": "stop_work"}],
    "hot_work": [{"text": "Welding at Zone B level 3, everything looks fine, log it"}, {"decision": "stop_work"}],
    "level_pick": [{"text": "C-5 column rebar spacing 180 mm"}, {"text": "yes"}],
}


def run_flow(steps: list[dict]) -> tuple[str, list[dict]]:
    sid = dbmod.create_session(repo, DEMO_USER, lang="en-IN")
    s = DialogueSession(repo, sid)
    out = []
    for st in steps:
        r = (s.handle(text=st["text"], language="en-IN") if "text" in st
             else s.handle(text="", decision=st["decision"], language="en-IN"))
        out.append({**st, "response": r})
    return sid, out


flows = {name: run_flow(steps)[1] for name, steps in FLOWS.items()}

# The Live screen replays one continuous conversation (greeting + a challenge + a question).
live_sid = dbmod.create_session(repo, DEMO_USER, lang="en-IN")
live = DialogueSession(repo, live_sid)
brief = memory.site_brief(repo)
greet = memory.greeting(brief)
live_script = [{"who": "Vesper", "text": greet}]
last = None
for utter in ["What is the cover at E-1?", "E-1 column cover measured 30 mm", "what is the tolerance there?"]:
    r = live.handle(text=utter, language="en-IN")
    live_script += [{"who": "You", "text": utter}, {"who": "Vesper", "text": r["reply"]["text"]}]
    if r.get("kind") != "answer":
        last = r

obs = repo._all("SELECT observation_id, created_at, location_id, element, attribute, value_claimed, unit, "
                "drawing_id, revision_claimed, contradiction_flag, contradiction_kinds, final_decision, "
                "linked_rfi_id, spoken_text, structured_summary, clarification_asked FROM field_observations "
                "WHERE project_id = ? ORDER BY created_at DESC LIMIT 12", (config.PROJECT_ID,))
for o in obs:
    o["contradiction_kinds"] = json.loads(o["contradiction_kinds"]) if o.get("contradiction_kinds") else []
    o["evidence"] = {"drawing": repo.drawing_by_id(o["drawing_id"]) if o.get("drawing_id") else None,
                     "rfi": repo._one("SELECT * FROM rfis WHERE rfi_id = ?", (o["linked_rfi_id"],))
                     if o.get("linked_rfi_id") else None}

sessions = dbmod.sessions_for_user(repo, DEMO_USER, limit=6)
for s in sessions:
    s["turns"] = dbmod.turns_for_session(repo, s["session_id"])

from scenarios import run_all  # noqa: E402

scen = run_all(None)

data = {
    "flows": flows,
    "live": {"script": live_script, "engine": last, "brief": brief},
    "observations": obs,
    "conversations": sessions,
    "scenarios": scen,
    "health": {"db": True, "llm": "cerebras", "rime": True, "voiceid": True, "engine": True},
}
dest = ROOT / "app" / "lib" / "demo-data.json"
dest.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str))
print(f"wrote {dest.relative_to(ROOT)} · flows={len(flows)} obs={len(obs)} "
      f"scenarios={scen['passed']}/{scen['total']}")
