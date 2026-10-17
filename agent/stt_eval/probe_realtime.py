"""Probe Sarvam realtime streaming STT (saaras:v3-realtime) through the LiveKit plugin.

Streams each clip in real time (10 ms frames) followed by silence and records:
  first interim, final text, and latency from end of audio -> FINAL_TRANSCRIPT.
Usage: agent/.venv/bin/python agent/stt_eval/probe_realtime.py [--mode transcribe] [--lang auto]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
import wave
from pathlib import Path

import aiohttp
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import stt as lkstt

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "backend" / ".env.local", override=True)
sys.path.insert(0, str(ROOT / "agent"))

from livekit.plugins import sarvam  # noqa: E402
from worker_prompts import SARVAM_STT_PROMPT  # noqa: E402

CLIPS = ["evidence/fixtures/q_cover_e1.wav", "evidence/fixtures/q_cover_e1_drill5db.wav",
         "evidence/fixtures/barge_e2_38.wav", "agent/stt_eval/clips/pith_opd.wav",
         "agent/stt_eval/clips/rw_c401.wav", "agent/stt_eval/clips/bulbul_hinglish_e1.wav",
         "agent/stt_eval/clips/bulbul_hinglish_l3.wav", "agent/stt_eval/clips/hi_c5.wav"]


async def run_clip(engine: sarvam.STTRealtime, path: Path) -> dict:
    with wave.open(str(path)) as w:
        sr = w.getframerate()
        pcm = w.readframes(w.getnframes())
    stream = engine.stream()
    out = {"clip": path.stem, "interim": None, "final": [], "eos_ms": None, "final_ms": None}
    end_of_audio = 0.0

    async def reader() -> None:
        async for ev in stream:
            now = time.perf_counter()
            if ev.type == lkstt.SpeechEventType.INTERIM_TRANSCRIPT and out["interim"] is None:
                out["interim"] = ev.alternatives[0].text
            elif ev.type == lkstt.SpeechEventType.END_OF_SPEECH and end_of_audio and out["eos_ms"] is None:
                out["eos_ms"] = round((now - end_of_audio) * 1000)
            elif ev.type == lkstt.SpeechEventType.FINAL_TRANSCRIPT:
                out["final"].append(ev.alternatives[0].text)
                if end_of_audio and out["final_ms"] is None:
                    out["final_ms"] = round((now - end_of_audio) * 1000)

    task = asyncio.create_task(reader())
    step = sr // 100 * 2
    for i in range(0, len(pcm), step):
        chunk = pcm[i:i + step]
        stream.push_frame(rtc.AudioFrame(chunk, sr, 1, len(chunk) // 2))
        await asyncio.sleep(0.01)
    end_of_audio = time.perf_counter()
    silence = b"\x00\x00" * (sr // 100)
    for _ in range(150):  # 1.5 s of silence so server VAD can close the utterance
        stream.push_frame(rtc.AudioFrame(silence, sr, 1, sr // 100))
        await asyncio.sleep(0.01)
    stream.end_input()
    try:
        await asyncio.wait_for(task, 8)
    except asyncio.TimeoutError:
        task.cancel()
    await stream.aclose()
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="transcribe")
    ap.add_argument("--lang", default="auto")
    ap.add_argument("--stream-type", default="fast")
    ap.add_argument("--silence-ms", type=int, default=350)
    ap.add_argument("--prompt", action="store_true")
    a = ap.parse_args()
    async with aiohttp.ClientSession() as http:
        engine = sarvam.STTRealtime(language=a.lang, mode=a.mode, stream_type=a.stream_type,
                                    http_session=http, vad_min_silence_ms=a.silence_ms,
                                    prompt=SARVAM_STT_PROMPT if a.prompt else None)
        for c in CLIPS:
            r = await run_clip(engine, ROOT / c)
            print(f"{r['clip']:22s} eos {r['eos_ms']} ms  final {r['final_ms']} ms  "
                  f"interim={r['interim']!r} final={r['final']!r}")


if __name__ == "__main__":
    asyncio.run(main())
