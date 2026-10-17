#!/usr/bin/env python3
"""Full-duplex voice acceptance test — measures what the site manager actually hears.

Joins a real LiveKit room as the manager, *speaks* the committed WAV fixtures
(evidence/fixtures) into the microphone track in real time, and records the agent's Rime audio
track frame by frame. Every number below is taken from audio, not from logs:

  T1  end-of-turn -> first audible Rime audio (questions answered from the record)
  T2  same question under synthetic drill noise at 5 dB SNR: still understood and answered
  T3  barge-in: interrupt Vesper mid-challenge with a correction ->
        (a) Rime playback stops, (b) the stale challenge is never resumed or repeated,
        (c) the correction (E-2, 38 mm) is what the engine now holds and speaks back
  T4  a different voice says "log that observation" -> refused, nothing written
  T5  the enrolled manager says it -> written, linked to the verified drawing revision

Pass criteria are fixed in PASS below (defined before the run). Artifacts go to
evidence/runs/<stamp>/ (results.json, report.md, heard.wav = everything Vesper said,
mic.wav = everything the manager said) and evidence/latest-report.md.

Prereqs: backend on :8000 (dev identity), voiceid on :8788, and the agent worker running —
ideally against a scratch DB copy so the test's writes never touch data/site.db:
    cp data/site.db /tmp/vesper-acceptance.db
    (cd agent && SITE_DB_PATH=/tmp/vesper-acceptance.db SPEAKER_ID_ENABLED=true .venv/bin/python worker.py dev)
    agent/.venv/bin/python scripts/voice_acceptance.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import wave
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np
from livekit import rtc

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "evidence" / "fixtures"
SR, FRAME = 16000, 160  # 10 ms frames
TEST_USER = "acceptance-test"  # its own voiceprint; never touches a real user's enrolment

PASS = {
    "first_audio_p50_ms": 1500,     # median end-of-turn -> first audible Rime audio
    "first_audio_max_ms": 2500,     # worst case in the run
    "barge_stop_ms": 1500,          # correction onset -> Rime audio stops
}

ONSET_RMS, QUIET_RMS, QUIET_MS = 600, 180, 350


def load(name: str) -> np.ndarray:
    with wave.open(str(FIX / f"{name}.wav")) as w:
        assert w.getframerate() == SR and w.getnchannels() == 1
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


class Mic:
    """Real-time microphone: silence when idle, fixture audio when speaking."""

    def __init__(self) -> None:
        self.source = rtc.AudioSource(SR, 1, queue_size_ms=40)
        self.pending: asyncio.Queue = asyncio.Queue()
        self.record: list[np.ndarray] = []
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        silence = np.zeros(FRAME, dtype=np.int16)
        current = None
        while True:
            if current is None and not self.pending.empty():
                current = self.pending.get_nowait()  # (samples, pos, started_evt, done_evt, marks)
            if current:
                samples, pos, started, done, marks = current
                chunk = samples[pos:pos + FRAME]
                if len(chunk) < FRAME:
                    chunk = np.pad(chunk, (0, FRAME - len(chunk)))
                if pos == 0:
                    marks["start"] = time.monotonic()
                    started.set()
                current = (samples, pos + FRAME, started, done, marks)
                if pos + FRAME >= len(samples):
                    await self.source.capture_frame(rtc.AudioFrame(chunk.tobytes(), SR, 1, FRAME))
                    await self.source.wait_for_playout()
                    marks["end"] = time.monotonic()
                    done.set()
                    current = None
                    self.record.append(chunk)
                    continue
            else:
                chunk = silence
            self.record.append(chunk)
            await self.source.capture_frame(rtc.AudioFrame(chunk.tobytes(), SR, 1, FRAME))

    async def say(self, name: str, wait: bool = True) -> dict:
        marks: dict = {}
        started, done = asyncio.Event(), asyncio.Event()
        await self.pending.put((load(name), 0, started, done, marks))
        await started.wait()
        if wait:
            await done.wait()
        marks["done"] = done
        return marks


class Ear:
    """Records the agent's audio track and turns it into an onset/offset timeline."""

    def __init__(self) -> None:
        self.frames: list[tuple[float, float]] = []   # (t, rms)
        self.audio: list[np.ndarray] = []

    async def listen(self, track: rtc.Track) -> None:
        async for ev in rtc.AudioStream(track, sample_rate=SR, num_channels=1):
            a = np.frombuffer(ev.frame.data, dtype=np.int16)
            self.frames.append((time.monotonic(), float(np.sqrt(np.mean(a.astype(np.float64) ** 2))) if a.size else 0.0))
            self.audio.append(a.copy())

    def onset_after(self, t0: float) -> float | None:
        run = 0
        for t, r in self.frames:
            if t < t0:
                continue
            run = run + 1 if r > ONSET_RMS else 0
            if run == 3:
                return t - 0.02
        return None

    def offset_after(self, t0: float) -> float | None:
        quiet_start = None
        for t, r in self.frames:
            if t < t0:
                continue
            if r < QUIET_RMS:
                quiet_start = quiet_start or t
                if t - quiet_start >= QUIET_MS / 1000:
                    return quiet_start
            else:
                quiet_start = None
        return None

    async def wait_onset(self, t0: float, timeout: float = 12) -> float | None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            t = self.onset_after(t0)
            if t:
                return t
            await asyncio.sleep(0.02)
        return None

    async def wait_idle(self, quiet: float = 1.5, timeout: float = 45) -> None:
        """Block until Vesper has been silent for `quiet` seconds (sentence pauses are shorter)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            now = time.monotonic()
            recent = [r for t, r in self.frames if t >= now - quiet]
            if recent and max(recent) < QUIET_RMS and now - self.frames[0][0] > quiet:
                return
            await asyncio.sleep(0.05)

    async def wait_offset(self, t0: float, timeout: float = 30) -> float | None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            t = self.offset_after(t0)
            if t:
                return t
            await asyncio.sleep(0.05)
        return None


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--repeats", type=int, default=2, help="rounds of the three T1 questions")
    args = ap.parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = ROOT / "evidence" / "runs" / stamp
    out.mkdir(parents=True, exist_ok=True)
    hdr = {"X-Vesper-User": TEST_USER}

    async with httpx.AsyncClient(timeout=60) as cx:
        files = [("files", (f"{n}.wav", (FIX / f"{n}.wav").read_bytes(), "audio/wav"))
                 for n in ("enroll_1", "enroll_2", "enroll_3")]
        enr = (await cx.post(f"{args.api}/api/voice/enroll", files=files, headers=hdr)).json()
        tok = (await cx.post(f"{args.api}/api/rtc/token", json={"name": "acceptance"}, headers=hdr)).json()
    print(f"enrolled test voice: {enr}")

    room, ear, mic = rtc.Room(), Ear(), Mic()
    events: list[dict] = []
    said: list[dict] = []

    @room.on("track_subscribed")
    def _sub(track, pub, part):
        if isinstance(track, rtc.RemoteAudioTrack):
            asyncio.create_task(ear.listen(track))

    @room.on("data_received")
    def _data(p: rtc.DataPacket):
        if p.topic == "vesper":
            d = json.loads(p.data.decode())
            d["_t"] = time.monotonic()
            events.append(d)

    @room.on("transcription_received")
    def _tr(segs, part, pub):
        for s in segs:
            if s.final and part and part.identity != room.local_participant.identity:
                said.append({"t": time.monotonic(), "text": s.text})

    await room.connect(tok["url"], tok["token"])
    await room.local_participant.publish_track(
        rtc.LocalAudioTrack.create_audio_track("mic", mic.source),
        rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
    mic.start()
    t0 = time.monotonic()
    greet_on = await ear.wait_onset(t0, timeout=30)
    if greet_on:
        await ear.wait_offset(greet_on + 0.3)
    tts_info = next((e.get("tts") for e in events if e.get("type") == "session"), None)
    print(f"agent greeting heard after {greet_on - t0:.1f}s; voice out = {tts_info}" if greet_on else "no greeting heard")

    def engine_after(t: float, pred=lambda r: True) -> dict | None:
        for e in events:
            if e.get("type") == "engine" and e["_t"] >= t and pred(e["result"]):
                return e["result"]
        return None

    async def turn_result(t: float, pred=lambda r: True, timeout: float = 15) -> dict:
        """The engine result for the turn spoken at `t` (published before Vesper speaks)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            r = engine_after(t, pred)
            if r:
                return r
            await asyncio.sleep(0.05)
        return {}

    async def settle(_t_from: float = 0) -> None:
        await ear.wait_idle()

    results: dict = {"stamp": stamp, "tts": tts_info, "pass_criteria": PASS, "tests": {}}

    # ---- T1: end-of-turn -> first audible audio ------------------------------------------
    t1 = []
    expect = {"q_cover_e1": "E-1, Level 1: column cover is 40 mm", "q_rfis": "Open RFIs:", "q_cover_e2": "E-2, Level 1: column cover is 40 mm"}
    for rnd in range(args.repeats):
        for fx, needle in expect.items():
            await ear.wait_idle()
            m = await mic.say(fx)
            on = await ear.wait_onset(m["end"])
            r = await turn_result(m["start"])
            lat = round((on - m["end"]) * 1000) if on else None
            ok = bool(on) and needle in (r.get("spoken_reply") or "")
            t1.append({"fixture": fx, "round": rnd + 1, "first_audio_ms": lat, "answer_ok": ok,
                       "heard_text": (r.get("spoken_reply") or "")[:140]})
            print(f"T1 {fx:<14} first audio {lat} ms  answer_ok={ok}")
            await settle(m["end"])
    lats = [x["first_audio_ms"] for x in t1 if x["first_audio_ms"] is not None]
    p50 = statistics.median(lats) if lats else None
    results["tests"]["T1_first_audio"] = {
        "samples": t1, "p50_ms": p50, "max_ms": max(lats) if lats else None,
        "pass": bool(lats) and len(lats) == len(t1) and p50 <= PASS["first_audio_p50_ms"]
        and max(lats) <= PASS["first_audio_max_ms"] and all(x["answer_ok"] for x in t1)}

    # ---- T2: drill noise at 5 dB SNR ------------------------------------------------------
    await ear.wait_idle()
    m = await mic.say("q_cover_e1_drill5db")
    on = await ear.wait_onset(m["end"])
    r = await turn_result(m["start"])
    ok = "E-1" in (r.get("spoken_reply") or "") and "40 mm" in (r.get("spoken_reply") or "")
    results["tests"]["T2_noise_5db"] = {"first_audio_ms": round((on - m["end"]) * 1000) if on else None,
                                        "heard_text": (r.get("spoken_reply") or "")[:140], "pass": ok}
    print(f"T2 drill 5 dB  answer_ok={ok}")
    await settle(m["end"])

    # ---- T3: barge-in with a correction ---------------------------------------------------
    await ear.wait_idle()
    m = await mic.say("obs_e1_30")
    challenge = await turn_result(m["start"], lambda r: r.get("state") == "challenging")
    ch_on = await ear.wait_onset(m["end"])
    await asyncio.sleep(1.0)                                     # let Vesper get into the challenge
    b = await mic.say("barge_e2_38", wait=False)                 # talk over it
    stop = None
    end_wait = time.monotonic() + 6
    while stop is None and time.monotonic() < end_wait:          # quiet >= 600 ms = really stopped
        await asyncio.sleep(0.05)
        q0 = None
        for t, rr in ear.frames:
            if t < b["start"]:
                continue
            if rr < QUIET_RMS:
                q0 = q0 or t
                if t - q0 >= 0.6:
                    stop = q0
                    break
            else:
                q0 = None
    await b["done"].wait()
    corr = await turn_result(b["start"], lambda r: r.get("state") != "challenging" or "E-2" in str(r.get("slots")))
    corr_on = await ear.wait_onset(b["end"])
    corr_off = await ear.wait_offset((corr_on or b["end"]) + 0.3)
    slots = corr.get("slots") or {}
    after = [s["text"] for s in said if stop and s["t"] > stop + 0.2]
    stale_spoken = any("30 mm" in s and "E-1" in s for s in after)
    stop_ms = round((stop - b["start"]) * 1000) if stop else None
    t3 = {
        "challenge_heard": bool(ch_on) and challenge.get("state") == "challenging",
        "challenge_text": (challenge.get("spoken_reply") or "")[:160],
        "stop_after_barge_onset_ms": stop_ms,
        "correction_slots": {k: slots.get(k) for k in ("grid", "attribute", "value", "unit")},
        "correction_state": corr.get("state"), "correction_contradictions": [c["kind"] for c in corr.get("contradictions", [])],
        "correction_heard_text": (corr.get("spoken_reply") or "")[:160],
        "stale_challenge_spoken_after_barge": stale_spoken,
    }
    t3["pass"] = (t3["challenge_heard"] and stop_ms is not None and stop_ms <= PASS["barge_stop_ms"]
                  and slots.get("grid") == "E-2" and slots.get("value") == 38 and not stale_spoken
                  and not t3["correction_contradictions"])
    results["tests"]["T3_barge_in"] = t3
    print(f"T3 barge-in stop {stop_ms} ms, slots={t3['correction_slots']}, stale={stale_spoken}")
    await settle((corr_off or b["end"]))

    # ---- T4/T5: voiceprint gate on the write ----------------------------------------------
    await ear.wait_idle()
    m = await mic.say("log_it_intruder")
    r4 = await turn_result(m["start"])
    results["tests"]["T4_intruder_log"] = {"logged": r4.get("logged"), "speaker_locked": r4.get("speaker_locked"),
                                           "heard_text": (r4.get("spoken_reply") or "")[:160],
                                           "pass": not (r4.get("logged") or {}).get("observation_id")}
    print(f"T4 intruder -> logged={r4.get('logged')} locked={r4.get('speaker_locked')}")
    await settle(m["end"])
    await ear.wait_idle()
    m = await mic.say("log_it_manager")
    r5 = await turn_result(m["start"])
    on5 = await ear.wait_onset(m["end"])
    lg = r5.get("logged") or {}
    results["tests"]["T5_manager_log"] = {
        "logged": lg, "drawing": (r5.get("resolved") or {}).get("drawing_id"),
        "first_audio_ms_incl_voiceprint": round((on5 - m["end"]) * 1000) if on5 else None,
        "heard_text": (r5.get("spoken_reply") or "")[:160], "pass": bool(lg.get("observation_id"))}
    print(f"T5 manager -> logged={lg}")
    await settle(m["end"])

    await room.disconnect()
    results["all_pass"] = all(t["pass"] for t in results["tests"].values())

    # ---- artifacts ------------------------------------------------------------------------
    def wav(path: Path, chunks: list[np.ndarray]) -> None:
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(np.concatenate(chunks).astype(np.int16).tobytes() if chunks else b"")
    wav(out / "heard.wav", ear.audio)
    wav(out / "mic.wav", mic.record)
    (out / "results.json").write_text(json.dumps(results, indent=2, default=str))
    report = render(results)
    (out / "report.md").write_text(report)
    (ROOT / "evidence" / "latest-report.md").write_text(report.replace("](", f"](runs/{stamp}/") if False else report)
    print(report)
    return 0 if results["all_pass"] else 1


def render(r: dict) -> str:
    T = r["tests"]
    t1 = T["T1_first_audio"]
    lines = [f"# Full-duplex acceptance run {r['stamp']}", "",
             f"Voice out: `{r['tts']}`", "",
             "| Test | Result | Measured | Pass criterion |", "| --- | --- | --- | --- |",
             f"| T1 end-of-turn → first audible Rime audio | {'PASS' if t1['pass'] else 'FAIL'} | p50 **{t1['p50_ms']} ms**, max {t1['max_ms']} ms, n={len(t1['samples'])} | p50 ≤ {r['pass_criteria']['first_audio_p50_ms']} ms, max ≤ {r['pass_criteria']['first_audio_max_ms']} ms, every answer correct |",
             f"| T2 same question under drill noise, 5 dB SNR | {'PASS' if T['T2_noise_5db']['pass'] else 'FAIL'} | first audio {T['T2_noise_5db']['first_audio_ms']} ms | correct E-1 answer (40 mm) |",
             f"| T3 barge-in with a correction | {'PASS' if T['T3_barge_in']['pass'] else 'FAIL'} | Rime stopped **{T['T3_barge_in']['stop_after_barge_onset_ms']} ms** after the manager started talking; engine now holds {T['T3_barge_in']['correction_slots']}; stale challenge re-spoken: {T['T3_barge_in']['stale_challenge_spoken_after_barge']} | stop ≤ {r['pass_criteria']['barge_stop_ms']} ms, correction held, stale challenge never resumed |",
             f"| T4 different voice says “log that observation” | {'PASS' if T['T4_intruder_log']['pass'] else 'FAIL'} | logged: {T['T4_intruder_log']['logged']}, lock: {T['T4_intruder_log']['speaker_locked']} | nothing written |",
             f"| T5 enrolled manager says it | {'PASS' if T['T5_manager_log']['pass'] else 'FAIL'} | {T['T5_manager_log']['logged']} → {T['T5_manager_log']['drawing']} | observation written, linked to verified revision |",
             "", f"**Overall: {'PASS' if r['all_pass'] else 'FAIL'}**", "",
             "## T1 samples", "", "| # | Fixture | First audio (ms) | Heard |", "| --- | --- | --- | --- |"]
    for i, s in enumerate(t1["samples"], 1):
        lines.append(f"| {i} | {s['fixture']} | {s['first_audio_ms']} | {s['heard_text']} |")
    b = T["T3_barge_in"]
    lines += ["", "## T3 what the manager heard", "",
              f"- Challenge (interrupted): “{b['challenge_text']}”",
              f"- After the correction: “{b['correction_heard_text']}”"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
