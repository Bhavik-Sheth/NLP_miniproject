# app/ — Vesper frontend (Next.js)

Mobile-first (~390 px) dark UI. Talks only to the backend HTTP API — see `../backend/CONTRACT.md`.

## Run
```bash
npm install         # once
npm run dev         # :3000   (needs backend on :8000 — see ../run-all.sh)
npm run build       # production build (must pass)
```
API base: `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`).

## Screens (bottom tab bar)
- **Talk** — push-to-talk mic (`webkitSpeechRecognition`, en-IN / hi-IN toggle) + always-visible
  typed fallback. Parallel `MediaRecorder` sends the utterance audio to `/api/turn` for the
  speaker gate. Barge-in: first speech while the reply is playing pauses `<audio>` and marks
  `bargeIn:true`. Renders transcript, entity chips (dim = low confidence), red contradiction card,
  amber blocker card, reply bubble, decision buttons → `/api/decision`. TTS via `/api/tts`
  (`speechSynthesis` hi-IN fallback + "Rime key missing" badge on 503). "🔒 logging locked"
  banner when `speaker.match === false`.
- **Observations** — `/api/observations` list → detail (drawing revision, linked RFI, contradiction
  kinds, clarification asked).
- **Scenarios** — "Run all" → `/api/scenarios/run`, pass/fail table + per-scenario transcript.
- **Enroll** — records 3 live voice samples and POSTs to `/api/voice/enroll` to enrol the site
  manager. `/api/voice/status` shows enrolled state.

## Notes
- STT is the browser Web Speech API over WebRTC mic capture (`getUserMedia`). No server STT,
  no LiveKit. Chrome/Edge only for `webkitSpeechRecognition`; the typed box works everywhere.
- Mic + speech need `https://` or `localhost`.
- `app/lib/` (the old TypeScript engine) is dead reference code — not imported, excluded from
  type-checking in `tsconfig.json`. The engine is `../backend/engine/` (Python).
- `app/lib/api.ts` is the only fetch layer; every non-2xx throws `ApiError`.
