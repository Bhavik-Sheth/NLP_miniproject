#!/usr/bin/env bash
# vesper-ai backend — FastAPI on uvicorn.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${BACKEND_PORT:-8000}"
HOST="${BACKEND_HOST:-127.0.0.1}"

if [ ! -x .venv/bin/uvicorn ]; then
  echo "no venv — creating (python3.12) + installing deps"
  "${PYTHON:-$HOME/.local/bin/python3.12}" -m venv .venv
  .venv/bin/pip -q install --upgrade pip
  .venv/bin/pip -q install -r requirements.txt
fi

exec env PYTHONPATH=. .venv/bin/uvicorn main:app --host "$HOST" --port "$PORT" "$@"
