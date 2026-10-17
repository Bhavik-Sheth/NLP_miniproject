#!/usr/bin/env bash
# Launch all three vesper-ai processes. Ctrl-C stops all of them.
#   voiceid  (speaker ID)  -> :8788
#   backend  (FastAPI)     -> :8000
#   frontend (Next dev)    -> :3000
set -euo pipefail
cd "$(dirname "$0")"

pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "starting voiceid on :8788"
( cd voiceid && ./run.sh ) & pids+=($!)

echo "starting backend on :8000"
# The orchestration script starts VoiceID itself, so enforce its matching backend
# gate here. A standalone backend may still deliberately opt out via its own env.
( cd backend && SPEAKER_ID_ENABLED="${SPEAKER_ID_ENABLED:-true}" SPEAKER_ID_URL="${SPEAKER_ID_URL:-http://127.0.0.1:8788}" ./run.sh ) & pids+=($!)

echo "starting frontend on :3000"
( cd app && npm run dev ) & pids+=($!)

echo
echo "  frontend  http://localhost:3000"
echo "  backend   http://localhost:8000/api/health"
echo "  voiceid   http://localhost:8788/health"
echo
wait
