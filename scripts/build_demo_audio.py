#!/usr/bin/env python3
"""Pre-render every reply the /demo console can say with Rime -> app/public/demo-audio/.

The public demo has no backend and no keys, so Vesper's voice there is real Rime audio rendered
once at build time on the same configuration as the live agent (mistv3 / cove / eng), after the
same ear-shaping (engine.speech.speakable). manifest.json maps the exact reply text shown on
screen to its clip. The Rime key is read from the local, ignored env and never shipped.

    backend/.venv/bin/python scripts/build_demo_audio.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "backend" / ".env.local", override=True)
from engine.speech import speakable  # noqa: E402

OUT = ROOT / "app" / "public" / "demo-audio"
MODEL, SPEAKER, LANG = "mistv3", os.getenv("RIME_SPEAKER_EN", "cove"), "eng"


def texts() -> list[str]:
    d = json.loads((ROOT / "app" / "lib" / "demo-data.json").read_text())
    out = [r["text"] for r in d["live"]["script"] if r["who"] == "Vesper"]
    for flow in d["flows"].values():
        out += [s["response"]["reply"]["text"] for s in flow if s["response"].get("reply", {}).get("text")]
    return list(dict.fromkeys(out))


def aliases() -> dict[str, str]:
    """Talk plays reply.speech (number-expanded) — map it to the same clip as reply.text."""
    d = json.loads((ROOT / "app" / "lib" / "demo-data.json").read_text())
    return {s["response"]["reply"]["speech"]: s["response"]["reply"]["text"]
            for flow in d["flows"].values() for s in flow
            if s["response"].get("reply", {}).get("speech")}


def render(text: str) -> bytes:
    req = Request("https://users.rime.ai/v1/rime-tts", method="POST",
                  data=json.dumps({"text": speakable(text), "speaker": SPEAKER, "modelId": MODEL,
                                   "lang": LANG}).encode(),
                  headers={"Authorization": f"Bearer {os.environ['RIME_API_KEY']}",
                           "Accept": "audio/mp3", "Content-Type": "application/json"})
    with urlopen(req, timeout=60) as r:
        raw = r.read()
    # 48 kbps mono is plenty for speech and keeps the static site small
    import subprocess
    return subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-b:a", "48k",
                           "-f", "mp3", "pipe:1"], input=raw, capture_output=True, check=True).stdout


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    for t in texts():
        name = hashlib.sha1(f"{MODEL}|{SPEAKER}|{speakable(t)}".encode()).hexdigest()[:16] + ".mp3"
        path = OUT / name
        if not path.exists():
            for attempt in range(3):
                try:
                    path.write_bytes(render(t))
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"  retry {attempt + 1}: {e}")
                    time.sleep(2)
        if path.exists():
            manifest[t] = f"demo-audio/{name}"
            print(f"  {name}  {path.stat().st_size // 1024:>4} KB  {t[:70]}")
    for speech, text in aliases().items():
        if text in manifest:
            manifest.setdefault(speech, manifest[text])
    keep = set(v.split("/")[-1] for v in manifest.values())
    for f in OUT.glob("*.mp3"):
        if f.name not in keep:
            f.unlink()
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(f"{len(manifest)} clips · model={MODEL} speaker={SPEAKER} lang={LANG}")
