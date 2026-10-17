#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# A machine-local venv (the tracked .venv may come from another OS and not run here).
VENV="${VOICEID_VENV:-.venv-local}"
PY="${PYTHON:-$(command -v python3.12 || command -v python3)}"
if ! "$VENV/bin/python" -c "" >/dev/null 2>&1; then
    echo "Creating $VENV with $PY..."
    rm -rf "$VENV"
    "$PY" -m venv "$VENV"
fi

echo "Upgrading pip..."
"$VENV/bin/pip" install --upgrade pip

echo "Installing requirements..."
"$VENV/bin/pip" install -r requirements.txt

# Pre-download model
echo "Pre-downloading ECAPA-TDNN model..."
mkdir -p models
"$VENV/bin/python" -c "from speechbrain.inference.speaker import EncoderClassifier; EncoderClassifier.from_hparams(source='speechbrain/spkrec-ecapa-voxceleb', savedir='models/ecapa', run_opts={'device':'cpu'})"

echo "Setup complete!"
