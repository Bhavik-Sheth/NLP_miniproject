#!/usr/bin/env bash
# vesper-ai voice agent worker (LiveKit).
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  PYTHON_BIN="${PYTHON:-$HOME/.local/bin/python3.12}"
  if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(command -v python3)"
  fi
  "$PYTHON_BIN" -m venv .venv
  .venv/bin/pip -q install --upgrade pip
  .venv/bin/pip -q install -r requirements.txt
fi

# 'dev' = connect to LIVEKIT_URL and wait for room dispatch. 'download-files' preloads models.
exec .venv/bin/python worker.py "${1:-dev}"
