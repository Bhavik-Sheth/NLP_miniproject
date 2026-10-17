#!/usr/bin/env python3
"""Validate Vesper's Rime configuration without ever printing a secret.

Usage:
  python3 scripts/rime_preflight.py
  python3 scripts/rime_preflight.py --env-file backend/.env.local --request
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json

ENDPOINT = "https://users.rime.ai/v1/rime-tts"
EXPECTED = {"RIME_MODEL": "arcana", "RIME_SPEAKER": "astra", "RIME_LANG": "hin"}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Rime configuration and optional audio preflight")
    parser.add_argument("--env-file", default="backend/.env.local", help="ignored local env file to read")
    parser.add_argument("--request", action="store_true", help="make one short TTS request")
    args = parser.parse_args()
    load_env_file(Path(args.env_file))

    key = os.getenv("RIME_API_KEY", "").strip()
    missing = [] if key and not key.startswith("replace_with_") else ["RIME_API_KEY"]
    mismatched = [
        f"{name}={os.getenv(name, '<missing>')} (expected {value})"
        for name, value in EXPECTED.items()
        if os.getenv(name) != value
    ]
    if missing or mismatched:
        if missing:
            print("Rime preflight failed: missing " + ", ".join(missing))
        if mismatched:
            print("Rime preflight failed: " + "; ".join(mismatched))
        return 1

    print("Rime configuration: OK (arcana / astra / hin; secret present)")
    if not args.request:
        return 0

    payload = json.dumps({
        "text": "Vesper Rime preflight.",
        "speaker": EXPECTED["RIME_SPEAKER"],
        "modelId": EXPECTED["RIME_MODEL"],
        "lang": EXPECTED["RIME_LANG"],
    }).encode("utf-8")
    request = Request(
        ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "audio/mp3",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            audio = response.read()
            content_type = response.headers.get_content_type()
    except HTTPError as exc:
        print(f"Rime request failed: HTTP {exc.code}")
        return 1
    except URLError as exc:
        print(f"Rime request failed: {exc.reason}")
        return 1

    if not audio or not content_type.startswith("audio/"):
        print("Rime request failed: no audio returned")
        return 1
    print(f"Rime request: OK ({content_type}, {len(audio)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
