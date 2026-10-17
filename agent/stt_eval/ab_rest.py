"""STT A/B: Groq Whisper large-v3 (the old path) vs Sarvam saaras:v3 REST modes.

Usage:  agent/.venv/bin/python agent/stt_eval/ab_rest.py [--out results.json]
Clips:  evidence/fixtures/*.wav (Samantha, US English) + agent/stt_eval/clips/*.wav
        (Rishi/Tara en-IN, Lekha hi-IN, Sarvam bulbul:v3 Hinglish).
Keys are read from .env / backend/.env.local and never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "backend" / ".env.local", override=True)
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "backend"))

from stt_normalize import normalize  # noqa: E402
from engine.extract import extract  # noqa: E402
from worker_prompts import STT_PROMPT, sarvam_keyterms  # noqa: E402

CLIPS = [
    ("q_cover_e1", ROOT / "evidence/fixtures/q_cover_e1.wav", "What is the cover at E one?"),
    ("q_cover_e1_drill5db", ROOT / "evidence/fixtures/q_cover_e1_drill5db.wav", "What is the cover at E one? (5 dB drill)"),
    ("obs_e1_30", ROOT / "evidence/fixtures/obs_e1_30.wav", "E one column cover measured thirty millimetres."),
    ("barge_e2_38", ROOT / "evidence/fixtures/barge_e2_38.wav", "Wait, not E one. E two. Cover is thirty eight millimetres."),
    ("q_rfis", ROOT / "evidence/fixtures/q_rfis.wav", "Any open R F I s?"),
    ("pith_opd", ROOT / "agent/stt_eval/clips/pith_opd.wav", "Pithoragarh OPD block, column E-1 cover measured thirty millimetres."),
    ("rw_c401", ROOT / "agent/stt_eval/clips/rw_c401.wav", "Retaining wall RW-1 is on drawing C-401 revision R2. Excavation permit EXC-0041."),
    ("rfi_e2", ROOT / "agent/stt_eval/clips/rfi_e2.wav", "What is the cover at E two in the maternity wing? Is RFI 050 still open?"),
    ("hi_c5", ROOT / "agent/stt_eval/clips/hi_c5.wav", "C-5 pe spacing 180 mm hai, teesri manzil par. (Hindi voice)"),
    ("bulbul_hinglish_e1", ROOT / "agent/stt_eval/clips/bulbul_hinglish_e1.wav", "E-1 column ka cover tees millimetre aaya hai, Pithoragarh OPD block mein."),
    ("bulbul_hinglish_l3", ROOT / "agent/stt_eval/clips/bulbul_hinglish_l3.wav", "Teesri manzil pe C-5 column ki stirrup spacing do sau bees hai."),
]


def groq(cx: httpx.Client, wav: bytes) -> tuple[str, int]:
    t = time.perf_counter()
    r = cx.post(f"{os.getenv('GROQ_BASE_URL', 'https://api.groq.com/openai/v1')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY'].strip()}"},
                data={"model": "whisper-large-v3", "language": "en", "temperature": "0",
                      "response_format": "json", "prompt": STT_PROMPT},
                files={"file": ("a.wav", wav, "audio/wav")})
    ms = round((time.perf_counter() - t) * 1000)
    return (r.json().get("text", "").strip() if r.status_code == 200 else f"<HTTP {r.status_code}>"), ms


def sarvam(cx: httpx.Client, wav: bytes, mode: str, lang: str, prompt: bool,
           model: str = "saaras:v3") -> tuple[str, int]:
    data: dict = {"model": model, "mode": mode, "language_code": lang}
    if prompt and model.startswith("saaras:v4"):  # keyterms are v4-only
        data["keyterms"] = json.dumps(sarvam_keyterms())
    t = time.perf_counter()
    r = cx.post("https://api.sarvam.ai/speech-to-text",
                headers={"api-subscription-key": os.environ["SARVAM_API_KEY"].strip()},
                data=data, files={"file": ("a.wav", wav, "audio/wav")})
    ms = round((time.perf_counter() - t) * 1000)
    return (r.json().get("transcript", "").strip() if r.status_code == 200 else f"<HTTP {r.status_code} {r.text[:80]}>"), ms


def slots(text: str) -> str:
    ex = extract(text)
    parts = [f"{k}={getattr(ex, k)['value']}" for k in ("grid", "level", "attribute", "value", "unit",
                                                        "drawingNumber", "revisionClaimed") if getattr(ex, k)]
    return " ".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "agent/stt_eval/results.json"))
    ap.add_argument("--prompt", action="store_true", help="send the site prompt to Sarvam too")
    args = ap.parse_args()
    systems = [("whisper", None, None), ("sarvam_transcribe_unknown", "transcribe", "unknown"),
               ("sarvam_translate_unknown", "translate", "unknown"), ("sarvam_codemix_unknown", "codemix", "unknown"),
               ("sarvam_transcribe_en", "transcribe", "en-IN"),
               ("sarvam_v4_transcribe_keyterms", "transcribe", "unknown")]
    rows = []
    with httpx.Client(timeout=30) as cx:
        # warm both connections so latency is not dominated by TLS setup
        warm = CLIPS[0][1].read_bytes()
        groq(cx, warm), sarvam(cx, warm, "transcribe", "unknown", False)
        for name, path, ref in CLIPS:
            wav = path.read_bytes()
            row = {"clip": name, "reference": ref, "results": {}}
            for sys_name, mode, lang in systems:
                text, ms = groq(cx, wav) if mode is None else sarvam(
                    cx, wav, mode, lang, args.prompt or "v4" in sys_name,
                    "saaras:v4" if "v4" in sys_name else "saaras:v3")
                norm = normalize(text)
                row["results"][sys_name] = {"text": text, "ms": ms, "normalized": norm.text,
                                            "norm_changes": norm.changes, "slots": slots(norm.text)}
                print(f"{name:22s} {sys_name:26s} {ms:5d} ms  {text!r} -> {norm.text!r}  [{slots(norm.text)}]")
            rows.append(row)
    Path(args.out).write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
