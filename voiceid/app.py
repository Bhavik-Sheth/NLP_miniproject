# vesper-ai speaker-ID sidecar.
# Reference: github.com/Inference-LAB/VocalID. For the MVP we use its core model
# (SpeechBrain ECAPA-TDNN, speechbrain/spkrec-ecapa-voxceleb) directly with cosine
# similarity against one enrolled speaker — no negative-sample collection, no training step.
#
#   GET  /health            -> {status, enrolled, threshold, model_cached}
#   POST /enroll  files=[]   -> average the embeddings of N clips, persist as the reference
#   POST /verify  file=      -> {match: bool, score: float, threshold: float}
#
# Audio in may be any container ffmpeg can read (webm/opus from MediaRecorder, wav, mp3).
import hashlib
import os
import subprocess

import numpy as np
import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

try:  # speechbrain >= 1.0
    from speechbrain.inference.speaker import EncoderClassifier
except ImportError:  # speechbrain 0.5.x
    from speechbrain.pretrained import EncoderClassifier  # type: ignore

MODEL_DIR = os.environ.get("SPEAKER_ID_MODEL_DIR", "./models")
ECAPA_DIR = os.path.join(MODEL_DIR, "ecapa")
ENROLL_PATH = os.path.join(MODEL_DIR, "enrolled.npy")   # legacy single-speaker profile
PROFILE_DIR = os.path.join(MODEL_DIR, "profiles")
os.makedirs(PROFILE_DIR, exist_ok=True)


def profile_path(user_id: str | None) -> str:
    """One voiceprint per signed-in account (Clerk user id). No id -> legacy profile."""
    if not user_id:
        return ENROLL_PATH
    return os.path.join(PROFILE_DIR, hashlib.sha256(user_id.encode()).hexdigest()[:32] + ".npy")
THRESHOLD = float(os.environ.get("SPEAKER_ID_THRESHOLD", "0.70"))
os.makedirs(MODEL_DIR, exist_ok=True)

_model = None


def model() -> "EncoderClassifier":
    global _model
    if _model is None:
        _model = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=ECAPA_DIR,
            run_opts={"device": "cpu"},
        )
    return _model


def _decode(raw: bytes) -> torch.Tensor:
    """Any audio container -> mono 16 kHz float32 tensor (1, T) via ffmpeg."""
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
         "-f", "f32le", "-ac", "1", "-ar", "16000", "pipe:1"],
        input=raw, capture_output=True,
    )
    if p.returncode != 0 or not p.stdout:
        raise HTTPException(400, f"ffmpeg decode failed: {p.stderr.decode()[-300:]}")
    audio = np.frombuffer(p.stdout, dtype=np.float32).copy()
    if audio.size < 16000 * 0.5:
        raise HTTPException(400, "clip shorter than 0.5s after decode")
    return torch.from_numpy(audio).unsqueeze(0)


def embed(raw: bytes) -> np.ndarray:
    sig = _decode(raw)
    with torch.no_grad():
        emb = model().encode_batch(sig).squeeze().cpu().numpy().astype(np.float64)
    n = np.linalg.norm(emb)
    return emb / n if n else emb


app = FastAPI(title="vesper voiceid")


@app.get("/health")
def health(user_id: str = "") -> dict:
    return {
        "status": "ok",
        "enrolled": os.path.exists(profile_path(user_id)),
        "threshold": THRESHOLD,
        "model_cached": os.path.isdir(ECAPA_DIR),
    }


@app.post("/enroll")
async def enroll(files: list[UploadFile] = File(...), user_id: str = Form("")) -> dict:
    if not files:
        raise HTTPException(400, "no files")
    embs = [embed(await f.read()) for f in files]
    mean = np.mean(np.stack(embs), axis=0)
    mean = mean / (np.linalg.norm(mean) or 1.0)
    np.save(profile_path(user_id), mean)
    # self-consistency: how tightly the clips cluster (sanity signal, not a gate)
    cohesion = float(np.mean([np.dot(mean, e) for e in embs]))
    return {"enrolled": True, "samples": len(embs), "dims": int(mean.shape[0]),
            "cohesion": round(cohesion, 4)}


@app.post("/verify")
async def verify(file: UploadFile = File(...), user_id: str = Form("")) -> dict:
    path = profile_path(user_id)
    if not os.path.exists(path):
        raise HTTPException(409, "no enrolled speaker; call /enroll first")
    ref = np.load(path)
    emb = embed(await file.read())
    score = float(np.dot(ref, emb))  # cosine; both unit-norm
    return {"match": score >= THRESHOLD, "score": round(score, 4), "threshold": THRESHOLD}
