#!/bin/bash
# Uses the first virtualenv whose interpreter actually runs on this machine (the tracked
# .venv was created on another OS). Create one with ./setup.sh.
cd "$(dirname "$0")"
for v in "${VOICEID_VENV:-}" .venv-local .venv; do
  if [ -n "$v" ] && "$v/bin/python" -c "import uvicorn" >/dev/null 2>&1; then
    exec "$v/bin/python" -m uvicorn app:app --host 127.0.0.1 --port "${SPEAKER_ID_PORT:-8788}"
  fi
done
echo "voiceid: no working virtualenv; run ./setup.sh" >&2
exit 1
