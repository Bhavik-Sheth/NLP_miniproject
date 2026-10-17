#!/usr/bin/env bash
set -e
cd /mnt/c/College/Academics/Sem5/NLP_MiniProject/vesper-ai
HOST_IP=$(ip route | grep default | awk '{print $3}')
export OLLAMA_URL="http://${HOST_IP}:11434"
export MEMORY_EMBED_MODEL="nomic-embed-text"
export MEMORY_EMBED_DIM="768"
echo "Ollama URL: $OLLAMA_URL"
echo "Starting ingest for projects P1 and NSK..."
backend/.venv/bin/python scripts/ingest_knowledge.py --only projects --project P1,NSK --no-cognee
echo "Ingest completed successfully."
