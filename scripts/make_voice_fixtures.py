#!/usr/bin/env python3
"""Build the spoken fixtures for the full-duplex acceptance test (evidence/fixtures/*.wav).

The committed WAVs are what the test replays, so the run is reproducible on any OS; this script
only regenerates them (macOS `say` + ffmpeg). All audio is synthetic — no real person's voice.

  manager voice  : macOS "Samantha"  (enrolled as the site manager for the test)
  intruder voice : macOS "Daniel"    (a different speaker who tries to log)
  site noise     : synthetic drill — band-limited noise with 18 Hz hammer impulses, mixed at 5 dB SNR
"""
from __future__ import annotations

import math
import random
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "evidence" / "fixtures"
SR = 16000

LINES = {
    # id: (voice, text)
    "enroll_1": ("Samantha", "Morning. I am checking the O P D block columns before the rain comes in."),
    "enroll_2": ("Samantha", "The retaining wall shuttering on the ambulance road looks straight today."),
    "enroll_3": ("Samantha", "Please keep the pre pour inspection notes for the level four slab ready."),
    "q_cover_e1": ("Samantha", "What is the cover at E one?"),
    "q_rfis": ("Samantha", "Any open R F I s?"),
    "q_cover_e2": ("Samantha", "What is the cover at E two?"),
    "obs_e1_30": ("Samantha", "E one column cover measured thirty millimetres."),
    "barge_e2_38": ("Samantha", "Wait, not E one. E two. Cover is thirty eight millimetres."),
    "log_it_manager": ("Samantha", "Okay, log that observation."),
    "log_it_intruder": ("Daniel", "Okay, log that observation."),
}


def say_to_pcm(voice: str, text: str) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        aiff = Path(d) / "x.aiff"
        subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True)
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(aiff), "-f", "s16le", "-ac", "1",
                              "-ar", str(SR), "pipe:1"], check=True, capture_output=True).stdout
    return raw


def drill(n: int, seed: int = 7) -> list[float]:
    rnd = random.Random(seed)
    out, lp = [], 0.0
    for i in range(n):
        lp = 0.85 * lp + 0.15 * rnd.uniform(-1, 1)          # low-passed rumble
        hammer = 1.0 if (i % (SR // 18)) < 90 else 0.25       # 18 Hz impact envelope
        out.append((lp * 0.6 + rnd.uniform(-1, 1) * 0.4) * hammer)
    return out


def mix(pcm: bytes, snr_db: float) -> bytes:
    sig = struct.unpack(f"<{len(pcm)//2}h", pcm)
    noise = drill(len(sig))
    ps = sum(x * x for x in sig) / len(sig)
    pn = sum(x * x for x in noise) / len(noise)
    k = math.sqrt(ps / (pn * 10 ** (snr_db / 10)))
    mixed = [max(-32768, min(32767, int(s + k * v))) for s, v in zip(sig, noise)]
    return struct.pack(f"<{len(mixed)}h", *mixed)


def write(name: str, pcm: bytes) -> None:
    with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    print(f"  {name}.wav  {len(pcm) / 2 / SR:.2f}s")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (voice, text) in LINES.items():
        pcm = say_to_pcm(voice, text)
        write(name, pcm)
        if name == "q_cover_e1":
            write("q_cover_e1_drill5db", mix(pcm, 5.0))
    (OUT / "LINES.txt").write_text("".join(f"{k}\t{v}\t{t}\n" for k, (v, t) in LINES.items())
                                   + "q_cover_e1_drill5db\tSamantha+drill\tq_cover_e1 mixed with synthetic drill at 5 dB SNR\n")
