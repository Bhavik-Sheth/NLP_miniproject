#!/usr/bin/env python3
"""
CLI tool to enroll speaker samples with the voiceid service.

Usage:
  python enroll.py clip1.wav clip2.wav ...
"""
import sys
import requests
from pathlib import Path

def enroll(filepaths: list[str]) -> None:
    if not filepaths:
        print("Usage: python enroll.py clip1.wav clip2.wav ...")
        print("\nEnroll one or more audio clips to the voiceid service.")
        sys.exit(1)

    url = "http://127.0.0.1:8788/enroll"

    files = []
    for filepath in filepaths:
        p = Path(filepath)
        if not p.exists():
            print(f"Error: {filepath} not found", file=sys.stderr)
            sys.exit(1)
        files.append(("files", open(p, "rb")))

    try:
        response = requests.post(url, files=files)
        response.raise_for_status()
        import json
        print(json.dumps(response.json(), indent=2))
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to voiceid service at http://127.0.0.1:8788", file=sys.stderr)
        print("Make sure to start it with: ./run.sh", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        for _, f in files:
            f.close()

if __name__ == "__main__":
    enroll(sys.argv[1:])
