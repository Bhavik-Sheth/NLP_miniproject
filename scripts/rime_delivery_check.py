#!/usr/bin/env python3
"""Before/after delivery check: raw engine text vs engine.speech.speakable() on the live Rime path.

Holds model + voice constant (mistv3 / cove / eng, LiveKit Rime plugin over websocket — the
exact shipped live path), renders each variant, records time-to-first-audio and total time,
and saves the clips to evidence/delivery/ so they can be listened to.

    agent/.venv/bin/python scripts/rime_delivery_check.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "backend" / ".env.local", override=True)

import aiohttp  # noqa: E402
from livekit.plugins import rime  # noqa: E402

from engine.speech import speakable  # noqa: E402

OUT = ROOT / "evidence" / "delivery"
ITEMS = {
    "open_rfis": "Open RFIs: RFI-049, Plumbing sleeve clash with beam at Zone B; RFI-050, Electrical conduit "
                 "density in L4 slab near core; RFI-055, Staircase waist slab thickness at mid-landing L3–L4; "
                 "RFI-061, OPD block monsoon concrete-pour access.",
    "cover_answer": "At E-1, Level 1: column cover is 40 mm plus or minus 5, per A-201 R1 issued 26 August "
                    "(IS 456 Cl. 26.4). Open RFI-061 (OPD block monsoon concrete-pour access).",
    "challenge": "You reported cover at E-1, Level 1 as 30 mm, but A-201 R1 shows 40 mm, with a tolerance of "
                 "plus or minus 5. Would you like to log the observation, raise an RFI, or raise an NCR?",
}


async def render(tts, text: str, path: Path, timeout: float = 25) -> dict:
    t0, first, frames = time.perf_counter(), None, []
    try:
        s = tts.stream()
        s.push_text(text)
        s.end_input()

        async def pull():
            nonlocal first
            async for ev in s:
                first = first or time.perf_counter() - t0
                frames.append(ev.frame)
        await asyncio.wait_for(pull(), timeout)
        err = None
    except Exception as e:  # timeouts are the finding, not a crash
        err = type(e).__name__
    if frames:
        with wave.open(str(path), "wb") as w:
            w.setnchannels(frames[0].num_channels)
            w.setsampwidth(2)
            w.setframerate(frames[0].sample_rate)
            w.writeframes(b"".join(bytes(f.data) for f in frames))
    return {"first_audio_ms": round(first * 1000) if first else None,
            "total_ms": round((time.perf_counter() - t0) * 1000), "error": err, "chars": len(text),
            "clip": path.name if frames else None}


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    async with aiohttp.ClientSession() as http:
        tts = rime.TTS(model="mistv3", speaker="cove", lang="eng", api_key=os.getenv("RIME_API_KEY"),
                       use_websocket=True, http_session=http)
        await render(tts, "Warm up.", OUT / "_warm.wav")   # label: all rows below are warm-connection
        for name, raw in ITEMS.items():
            for variant, text in (("raw", raw), ("speakable", speakable(raw))):
                r = await render(tts, text, OUT / f"{name}.{variant}.wav")
                rows.append({"item": name, "variant": variant, **r, "text": text})
                print(f"{name:13} {variant:9} first {r['first_audio_ms']} ms  total {r['total_ms']} ms  err={r['error']}")
        await tts.aclose()
    (OUT / "_warm.wav").unlink(missing_ok=True)
    (OUT / "results.json").write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
