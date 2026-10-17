"""Live voice profiling for the agent.

Subscribes to the manager's mic track, keeps a rolling ~6 s PCM buffer, and verifies
it against the enrolled speaker (voiceid sidecar = SpeechBrain ECAPA-TDNN, open source).
Updates Brain.speaker_ok / speaker_score, which the decision tools gate on.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import struct
import time

import httpx
from livekit import rtc

logger = logging.getLogger("vesper.voice")

SR = 16000
WINDOW_SEC = 6
VERIFY_EVERY_SEC = 4.0
SPEAKER_ID_URL = os.getenv("SPEAKER_ID_URL", "http://localhost:8788").rstrip("/")
ENABLED = os.getenv("SPEAKER_ID_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
# Only verify while the manager is actually speaking: silence and background hum make poor
# voiceprints and caused false locks. RMS threshold on int16 PCM.
SPEECH_RMS = int(os.getenv("SPEAKER_ID_MIN_RMS", "450"))
SEGMENT_GAP_SEC = 0.5  # silence that separates one utterance from the next


def _pcm16_to_wav(pcm: bytes, sample_rate: int = SR) -> bytes:
    n = len(pcm)
    hdr = b"RIFF" + struct.pack("<I", 36 + n) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    hdr += b"data" + struct.pack("<I", n)
    return hdr + pcm


def _rms(pcm: bytes) -> float:
    n = len(pcm) // 2
    if not n:
        return 0.0
    samples = struct.unpack(f"<{n}h", pcm[: n * 2])
    return (sum(x * x for x in samples) / n) ** 0.5


class VoiceProfiler:
    def __init__(self, brain, on_update=None) -> None:
        self.brain = brain
        self.on_update = on_update            # async callable(dict) -> publish to browser
        self._buf = bytearray()
        self._max = SR * 2 * WINDOW_SEC       # int16
        self._task: asyncio.Task | None = None
        self._last_verify = 0.0
        self._closed = False
        self._seg = bytearray()          # voiced audio of the utterance in progress / just finished
        self._last_voiced = 0.0

    def attach(self, room: rtc.Room) -> None:
        if not ENABLED:
            logger.info("voice profiling disabled")
            return

        @room.on("track_subscribed")
        def _on_track(track, pub, participant):
            if isinstance(track, rtc.RemoteAudioTrack):
                logger.info("voice profiling: capturing %s", participant.identity)
                self._task = asyncio.create_task(self._consume(track))

    async def _consume(self, track: rtc.Track) -> None:
        stream = rtc.AudioStream(track, sample_rate=SR, num_channels=1)
        last_report, peak, frames = 0.0, 0, 0
        try:
            async for ev in stream:
                if self._closed:
                    break
                pcm = ev.frame.data.tobytes()
                level = _rms(pcm)
                # Without this, a muted mic, a wrong input device and a silent room are
                # indistinguishable from working audio: every sub-threshold frame is dropped
                # below without a trace, so "nothing was transcribed" cannot be told apart from
                # "nothing ever arrived". Report the observed level periodically.
                peak = max(peak, level)
                frames += 1
                tnow = time.monotonic()
                if tnow - last_report >= 3.0:
                    logger.info("mic level: peak rms %d over %d frames (speech gate %d)",
                                peak, frames, SPEECH_RMS)
                    last_report, peak, frames = tnow, 0, 0
                if level < SPEECH_RMS:
                    continue  # skip silence / muted mic so the window holds voiced audio
                now_v = time.monotonic()
                if now_v - self._last_voiced > SEGMENT_GAP_SEC:
                    self._seg = bytearray()  # a pause starts a new utterance
                self._last_voiced = now_v
                self._seg.extend(pcm)
                self._buf.extend(pcm)
                if len(self._buf) > self._max:
                    del self._buf[: len(self._buf) - self._max]
                now = time.monotonic()
                if now - self._last_verify >= VERIFY_EVERY_SEC and len(self._buf) >= SR * 2 * 2:
                    self._last_verify = now
                    asyncio.create_task(self.verify_now())
        finally:
            await stream.aclose()

    async def verify_recent(self) -> bool:
        """Verify ONLY the utterance that carried the command, right before a write. The rolling
        4 s check alone could let a stranger's "log it" inherit the manager's earlier pass, and a
        fixed tail window would blend the manager's previous sentence into the stranger's."""
        if not ENABLED:
            return True
        self._last_verify = time.monotonic()
        await self.verify_now(pcm=bytes(self._seg), min_bytes=int(SR * 2 * 0.5))
        return bool(self.brain.speaker_ok)

    async def verify_now(self, pcm: bytes | None = None, min_bytes: int = SR * 2) -> None:
        strict = pcm is not None
        pcm = pcm if strict else bytes(self._buf)
        if len(pcm) < min_bytes:  # too little voiced audio to judge
            if strict:
                self.brain.speaker_ok = False
                self.brain.speaker_reason = "command too short to verify"
            return
        wav = _pcm16_to_wav(pcm)
        try:
            async with httpx.AsyncClient(timeout=6.0) as cx:
                r = await cx.post(f"{SPEAKER_ID_URL}/verify", data={"user_id": self.brain.user_id},
                                  files={"file": ("turn.wav", wav, "audio/wav")})
            if r.status_code == 200:
                j = r.json()
                self.brain.speaker_ok = bool(j.get("match"))
                self.brain.speaker_score = float(j.get("score", 0.0))
                self.brain.speaker_reason = None
                logger.info("voiceprint %s: score %.3f match=%s (%.1fs voiced)",
                            "command" if strict else "rolling", self.brain.speaker_score,
                            self.brain.speaker_ok, len(pcm) / (SR * 2))
            else:
                # Fail closed: not enrolled (409), bad audio or sidecar error all lock writes.
                self.brain.speaker_ok = False
                self.brain.speaker_score = None
                self.brain.speaker_reason = "voice not enrolled" if r.status_code == 409 else f"voiceid {r.status_code}"
        except Exception as e:
            logger.warning("verify failed: %s", e)
            self.brain.speaker_ok = False
            self.brain.speaker_score = None
            self.brain.speaker_reason = "speaker-ID service unreachable"
        if self.on_update:
            try:
                await self.on_update({
                    "type": "speaker",
                    "match": self.brain.speaker_ok,
                    "score": self.brain.speaker_score,
                    "reason": self.brain.speaker_reason,
                })
            except Exception:
                pass

    async def aclose(self) -> None:
        self._closed = True
        if self._task:
            self._task.cancel()
