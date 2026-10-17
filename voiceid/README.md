# Speaker Verification Sidecar

FastAPI service for speaker verification using SpeechBrain ECAPA-TDNN embeddings and cosine similarity.

## Quick Start

Setup the venv and model:
```bash
./setup.sh
```

Start the service:
```bash
./run.sh
```

The service runs on `http://127.0.0.1:8788` (override with `SPEAKER_ID_PORT` env var).

## Enrolling a Speaker

After the service is running, enroll one or more audio clips:
```bash
.venv/bin/python enroll.py samples/clip1.wav samples/clip2.wav
```

## API Endpoints

- `GET /health` - Service status, enrollment status, model cache status
- `POST /enroll` - Enroll speaker (multipart: `files=` audio clips in WAV, WebM, MP3, or other ffmpeg-compatible formats)
- `POST /verify` - Verify audio against enrolled speaker (multipart: `file=` single audio clip) -> `{match, score, threshold}`

## Configuration

- `SPEAKER_ID_PORT` - Port to run on (default: 8788)
- `SPEAKER_ID_THRESHOLD` - Cosine similarity threshold for match (default: 0.70)
- `SPEAKER_ID_MODEL_DIR` - Model cache directory (default: `./models`)
