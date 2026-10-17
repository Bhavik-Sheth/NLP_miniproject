# 03 — Sarvam STT (saaras:v3) for Vesper voice

Researched 2026-09-15 for W5. Sources are linked inline. Measurements are in `docs/plan/reports/W5.md`.

## Summary

| Question | Answer |
| --- | --- |
| REST model | `saaras:v3` (default), `saaras:v4` |
| Streaming model | `saaras:v3-realtime` on the **Realtime** websocket. It streams partial and final transcripts and has server VAD. |
| Modes | `transcribe` (default), `translate` (to English), `verbatim`, `translit`, `codemix` |
| Language | REST `language_code`: `unknown` (auto) or `en-IN`, `hi-IN`, … Realtime `language_code` (required): `auto` or a BCP-47 code |
| Biasing | REST `keyterms` (≤ 50 terms, ≤ 64 chars each). Realtime `prompt` (free-text terminology hint) |
| REST limit | 30 s of audio per request |
| LiveKit plugin | **`livekit-plugins-sarvam` 1.8.0** requires `livekit-agents[codecs,openai]>=1.8.0`, which matches our pinned 1.8.0, so no upgrade is needed. It exports `STT` (REST / legacy ws), `STTRealtime` (realtime ws), `TTS` and `LLM`. |
| Python SDK | `sarvamai==0.1.31a4` (uploaded 2026-08-07; py ≥ 3.8; deps httpx, pydantic, websockets). In this version `speech_to_text.transcribe(file, model, mode, language_code, with_timestamps, input_audio_codec)` has **no keyterms/prompt argument**, so the backend calls REST with httpx directly. The latest stable SDK is 0.1.33 (2026-09-09). |

## REST — `POST https://api.sarvam.ai/speech-to-text`

Docs: https://docs.sarvam.ai/api-reference/speech-to-text/transcribe

- Auth header: `api-subscription-key: <key>`
- Multipart fields:
  - `file`: WAV, MP3, AAC, AIFF, OGG, OPUS, FLAC, MP4/M4A, AMR, WMA, **WebM**, PCM (PCM at 16 kHz only)
  - `model`
  - `mode`
  - `language_code`
  - `with_timestamps`
  - `input_audio_codec`: `pcm_s16le` / `pcm_l16` / `pcm_raw`; auto-detected otherwise
  - `keyterms`
- Response: `request_id`, `transcript`, `language_code`, `language_probability`, `timestamps`
- Max duration is 30 s. The batch API (`/speech-to-text/job/v1`) handles up to 2 h per file.
  Source: https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/which-api-to-use

## Realtime websocket — `wss://api.sarvam.ai/speech-to-text-realtime/ws`

Docs: https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/realtime-api ·
reference https://docs.sarvam.ai/api-reference/speech-to-text/transcribe/realtime/ws

**Query parameters**

| Parameter | Default | Values / meaning |
| --- | --- | --- |
| `language_code` | required | `auto` or a BCP-47 code |
| `model` | `saaras:v3-realtime` | `saaras:v3-realtime`, `saaras:v4` |
| `stream_type` | `balanced` | `fast`, `balanced`, `simulated` |
| `mode` | `transcribe` | any of the five modes |
| `endpointing` | `vad` | `vad`, `manual` |
| `encoding` | `linear16` | also `linear32`, `mulaw`, `alaw` |
| `sample_rate` | — | 8000 or 16000 |
| `threshold` | 0.3 | VAD sensitivity |
| `silence_duration_ms` | 500 | silence that ends a turn |
| `min_speech_duration_ms` | 250 | shortest speech that counts |
| `return_timestamps` | — | |
| `prompt` | — | terminology hint |

**Messages**

- Client → server:
  - `{"event":"audio_input","audio":"<base64>"}`
  - `speech_start` / `speech_end` / `flush` (manual endpointing)
  - `config.update` (live change of language, prompt, mode, VAD)
  - `end`, `ping`
- Server → client:
  - `session.begin`
  - `vad.speech_start` / `vad.speech_end`
  - `transcript.partial` (interim) and `transcript.final` (`text`, `language`, `language_confidence`, optional `start_s`/`end_s`)
  - `config.updated`, `pong`
  - `session.end` (`audio_duration_s`, which is billing-authoritative)
  - `error` (`code`, `is_fatal`, `message`)

**Close codes**

| Code | Meaning |
| --- | --- |
| 1003 | Rate limit, quota exceeded or invalid key |
| 1008 | Inactivity timeout (send `ping`) |
| 1011 | Internal error (retry with backoff) |
| 4000 | Invalid parameter, or account not enabled |

**LiveKit mapping** (`livekit/plugins/sarvam/stt_streaming.py`)

- `vad.speech_start` → `START_OF_SPEECH`
- `transcript.partial` → `INTERIM_TRANSCRIPT`
- `transcript.final` → `FINAL_TRANSCRIPT`
- `vad.speech_end` → `END_OF_SPEECH`
- Constructor:
  ```python
  STTRealtime(language="en-IN"|"auto", stream_type, mode, endpointing, encoding, sample_rate, prompt,
              api_key (or SARVAM_API_KEY), vad_sot_threshold, vad_min_speech_ms, vad_min_silence_ms,
              vad_prefix_padding_ms)
  ```
- Capabilities: `streaming=True, interim_results=True, offline_recognize=False`. That means no `recognize()`,
  so it cannot sit behind a non-streaming wrapper.

## Legacy streaming websocket — `wss://api.sarvam.ai/speech-to-text/ws` (`saaras:v3`)

Docs: https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/streaming-api

- Query parameters:
  - `model`
  - `mode`
  - `language-code` (note the hyphen)
  - `sample_rate`
  - `input_audio_codec`
  - `high_vad_sensitivity`
  - `vad_signals` (emits `START_SPEECH`/`END_SPEECH`)
  - `flush_signal` (client can force a final)
- Only one final per utterance, **no partials**. Accepts WAV/PCM only.
- The plugin's `sarvam.STT` uses this for `stream()` and REST for `recognize()`.
- Sarvam recommends the Realtime API for new voice-agent work.

## TTS (for test clips only)

`POST https://api.sarvam.ai/text-to-speech` — docs https://docs.sarvam.ai/api-reference/text-to-speech/convert

- Body fields: `text`, `language_code`, `model` (`bulbul:v3`), `speaker` (e.g. `rahul`), `speech_sample_rate`, `output_audio_codec`
- Response: `audios` is a list of base64 strings.

## Mode choice for Vesper

The deterministic parser needs Latin-script English IDs and digits: "E-1", "A-201", "C-401 R2", "30 mm".

- `transcribe` with `language_code=unknown/auto` keeps Hindi words in Devanagari. The engine's `devanagari_to_latin`
  handles digits and aliases, but Hindi numerals spoken as words ("tees") stay words.
- `translate` returns English for Hindi and Hinglish speech. Numbers come out as digits and IDs stay Latin, so it is
  the most parser-friendly.
- `codemix` returns English words in Latin script with Hindi in Devanagari.

The A/B in W5.md decides. The chosen mode is configurable with `SARVAM_STT_MODE`.
