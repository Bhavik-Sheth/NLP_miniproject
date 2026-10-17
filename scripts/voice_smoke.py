"""End-to-end live-voice smoke test with no human and no microphone.

Joins a real LiveKit room as a synthetic participant, publishes a WAV fixture as a microphone
track in real time, and prints everything the agent sends back on the `vesper` data topic
(engine results, briefs, speaker state). This exercises the whole path — LiveKit transport,
Sarvam streaming STT, the deterministic engine and Rime — without anybody speaking.

    agent/.venv/bin/python scripts/voice_smoke.py
    agent/.venv/bin/python scripts/voice_smoke.py --wav evidence/fixtures/q_cover_e2.wav --project P1

Needs LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET (read from .env), which is how the
backend mints tokens too. The room name is chosen here so the worker dispatches a job for it.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import time
import uuid
import wave

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "backend" / ".env.local", override=True)

from livekit import api, rtc  # noqa: E402

FRAME_MS = 20


def build_token(room: str, identity: str, meta: dict) -> str:
    return (
        api.AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
        .with_identity(identity)
        .with_name("Smoke Test")
        .with_metadata(json.dumps(meta))
        .with_grants(api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True))
        .to_jwt()
    )


async def publish_wav(source: rtc.AudioSource, path: pathlib.Path, rate: int, channels: int) -> None:
    """Push the file in real time; STT endpointing depends on wall-clock pacing."""
    with wave.open(str(path)) as w:
        pcm = w.readframes(w.getnframes())
    per_frame = int(rate * channels * 2 * FRAME_MS / 1000)  # int16
    # Pure digital silence is not what a real room sounds like, and a hard cut from 0 straight into
    # speech can make server-side VAD miss the onset and clip the first word. Use very low-level
    # dither instead: audible to VAD as "room tone", far below the speech gate.
    import random
    silence = bytes(b for _ in range(per_frame // 2)
                    for b in int(random.randint(-12, 12)).to_bytes(2, "little", signed=True))

    async def send(chunk: bytes) -> None:
        frame = rtc.AudioFrame(
            data=chunk, sample_rate=rate, num_channels=channels,
            samples_per_channel=len(chunk) // (2 * channels),
        )
        await source.capture_frame(frame)

    # lead-in silence lets the agent settle and its AEC warm-up expire
    for _ in range(int(1500 / FRAME_MS)):
        await send(silence)
        await asyncio.sleep(FRAME_MS / 1000)

    for i in range(0, len(pcm) - per_frame, per_frame):
        await send(pcm[i:i + per_frame])
        await asyncio.sleep(FRAME_MS / 1000)

    # trailing silence triggers end-of-utterance
    for _ in range(int(2500 / FRAME_MS)):
        await send(silence)
        await asyncio.sleep(FRAME_MS / 1000)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", default="evidence/fixtures/q_rfis.wav")
    ap.add_argument("--project", default="P1")
    ap.add_argument("--user", default="smoke-test-user")
    ap.add_argument("--wait", type=float, default=12.0, help="seconds to keep listening after the audio")
    args = ap.parse_args()

    wav = (ROOT / args.wav) if not os.path.isabs(args.wav) else pathlib.Path(args.wav)
    if not wav.exists():
        print(f"no such fixture: {wav}", file=sys.stderr)
        return 2
    with wave.open(str(wav)) as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        seconds = w.getnframes() / rate
    if width != 2:
        print(f"need 16-bit PCM, got {width * 8}-bit", file=sys.stderr)
        return 2

    url = os.environ["LIVEKIT_URL"]
    room_name = f"vesper-smoke-{uuid.uuid4().hex[:8]}"
    meta = {"user_id": args.user, "projectId": args.project, "language": "en-IN"}
    token = build_token(room_name, f"{args.user}#{uuid.uuid4().hex[:6]}", meta)

    room = rtc.Room()
    events: list[dict] = []

    @room.on("data_received")
    def _on_data(packet: rtc.DataPacket) -> None:
        try:
            payload = json.loads(packet.data.decode())
        except ValueError:
            return
        events.append(payload)
        kind = payload.get("type")
        if kind == "engine":
            r = payload.get("result") or {}
            print(f"  [engine] state={r.get('state')} kind={r.get('kind')} "
                  f"user_text={payload.get('user_text')!r}")
            reply = (r.get("reply") or {}).get("text") or r.get("spoken_reply")
            if reply:
                print(f"  [reply ] {reply[:200]}")
        elif kind == "stt":
            print(f"  [stt   ] normalized={payload.get('normalized')!r}")
        elif kind == "speaker":
            print(f"  [voice ] match={payload.get('match')} score={payload.get('score')}")
        elif kind == "session":
            print(f"  [session] stt={json.dumps(payload.get('stt'))}")
            print(f"  [session] tts={json.dumps(payload.get('tts'))}")
        elif kind == "brief":
            b = payload.get("brief") or {}
            print(f"  [brief ] {len(b.get('open_rfis') or [])} RFIs, "
                  f"{len(b.get('open_hold_points') or [])} hold points")

    print(f"room     : {room_name}")
    print(f"fixture  : {wav.name}  ({seconds:.1f}s, {rate} Hz, {channels}ch)")
    await room.connect(url, token)
    print(f"connected: {url}")

    source = rtc.AudioSource(rate, channels)
    track = rtc.LocalAudioTrack.create_audio_track("smoke-mic", source)
    await room.local_participant.publish_track(
        track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
    print("published: microphone track")

    started = time.monotonic()
    await publish_wav(source, wav, rate, channels)
    print(f"sent     : {time.monotonic() - started:.1f}s of audio; listening {args.wait:.0f}s more")
    await asyncio.sleep(args.wait)
    await room.disconnect()

    engine = [e for e in events if e.get("type") == "engine"]
    print(f"\nRESULT: {len(events)} data events, {len(engine)} engine turn(s)")
    if not engine:
        print("FAIL: the agent never produced an engine turn — nothing was transcribed.")
        return 1
    print("PASS: the pipeline transcribed the audio and the engine answered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
