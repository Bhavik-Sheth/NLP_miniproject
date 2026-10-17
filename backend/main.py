"""vesper-ai backend API. See backend/CONTRACT.md for the frozen contract."""
from __future__ import annotations

import base64
import io
import json
import os
import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

import config
import db as dbmod
from engine.speech import speakable
from tenancy.auth import get_identity, require_project

# --- engine (WS-A). Defensive import so the server still boots for frontend dev. -----
try:
    from engine.dialogue import DialogueSession  # type: ignore
    from engine.llm import make_llm_assist  # type: ignore
    ENGINE_READY = True
except Exception as _e:  # pragma: no cover - scaffold only
    ENGINE_READY = False
    _ENGINE_ERR = repr(_e)

    class DialogueSession:  # minimal stub: echoes, never logs
        def __init__(self, repo, session_id, llm=None, persist_turns=True):
            self.session_id = session_id
            self.state = "capturing"

        def handle(self, *, text="", barge_in=False, noise="none", decision=None, speaker=None):
            return {
                "sessionId": self.session_id, "state": "capturing",
                "reply": {"text": f"(engine not loaded) {text}", "speech": ""},
                "entities": [], "contradictions": [], "blockers": [], "missing": [],
                "allowedDecisions": ["cancel"], "slots": {}, "resolved": {},
                "clarifiedKinds": [], "events": ["engine_stub"],
            }

    def make_llm_assist():
        return None

app = FastAPI(title="vesper-ai backend")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

_conn = dbmod.connect()
_repo = dbmod.Repo(_conn, config.PROJECT_ID)
_llm = make_llm_assist()
_sessions: dict[str, DialogueSession] = {}


_jwks_client: PyJWKClient | None = None
_claims_cache: dict[str, tuple[str, float]] = {}  # token -> (subject, exp)


def _jwks() -> PyJWKClient:
    """One JWKS client per process. PyJWKClient caches signing keys, so after the first request
    verification is a local RSA check instead of an HTTPS round-trip to Clerk every call."""
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(f"{config.CLERK_JWT_ISSUER}/.well-known/jwks.json",
                                   cache_keys=True, lifespan=3600)
    return _jwks_client


def _user_id(request: Request) -> str:
    """Verify the Clerk session token in deployment; local development has a safe demo identity."""
    if not config.CLERK_JWT_ISSUER:
        return request.headers.get("X-Vesper-User", "local-demo")
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "sign in is required")
    now = time.time()
    hit = _claims_cache.get(token)
    if hit and hit[1] > now:
        return hit[0]
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], issuer=config.CLERK_JWT_ISSUER,
                            options={"verify_aud": False}, leeway=5)
    except jwt.PyJWTError as exc:
        # Mirrors tenancy/auth.py: the caller sees a generic message, the log says why
        # (expired, wrong issuer, unknown signing key).
        print(f"clerk auth rejected (v1): {type(exc).__name__}: {exc}", flush=True)
        raise HTTPException(401, "invalid sign-in token") from exc
    subject = str(claims.get("sub") or "")
    if not subject:
        raise HTTPException(401, "invalid sign-in token")
    if len(_claims_cache) > 2048:
        _claims_cache.clear()
    _claims_cache[token] = (subject, float(claims.get("exp") or now + 30))
    return subject


def _reserve_or_limit(request: Request) -> int:
    user_id = _user_id(request)
    if not config.ENFORCE_FREE_COMMAND_LIMIT:
        return 0
    ok, used = dbmod.reserve_command(_repo, user_id, config.FREE_COMMAND_LIMIT)
    if not ok:
        raise HTTPException(429, detail={"code": "free_command_limit_reached", "message": "Your three complimentary Vesper commands are complete.", "limit": config.FREE_COMMAND_LIMIT, "used": used})
    return used


def _stt_error_response(upstream_status: int, detail: str) -> JSONResponse:
    """Translate Groq failures into useful API failures.

    Groq returns 400 for an undecodable WebM (for example, a recording stopped
    before its container has been finalised).  Returning 502 in that case made
    a browser recording problem look like an upstream outage.
    """
    body = {"error": "STT transcription failed", "detail": detail[:300]}
    if upstream_status in (400, 413, 415, 422):
        body["error"] = "invalid or unsupported audio"
        return JSONResponse(body, status_code=422)
    if upstream_status in (401, 403):
        # Do not expose provider authentication diagnostics to browsers.
        return JSONResponse({"error": "STT provider is not configured"}, status_code=503)
    if upstream_status == 429:
        return JSONResponse({"error": "STT provider is temporarily busy"}, status_code=503)
    return JSONResponse(body, status_code=502)


def _project_repo(request: Request, project_id: str | None = None) -> dbmod.Repo:
    """Authorize and bind a deterministic site-record repository to one project."""
    pid = str(project_id or config.PROJECT_ID).strip() or config.PROJECT_ID
    require_project(pid, get_identity(request))
    repo = dbmod.Repo(_conn, pid)
    if not repo._one("SELECT 1 FROM projects WHERE project_id = ?", (pid,)):
        raise HTTPException(404, "project has no operational site record")
    return repo


def _session(sid: str, user: str, request: Request, project_id: str | None = None) -> DialogueSession:
    """Return the caller's dialogue session. Sessions live in memory for speed but are
    restored from voice_sessions after a backend restart, so the console never loses its
    session memory to a 404; another user's session id is refused."""
    row = _repo._one("SELECT user_name, project_id FROM voice_sessions WHERE session_id = ?", (sid,))
    if not row:
        _sessions.pop(sid, None)
        raise HTTPException(404, "unknown session")
    if row["user_name"] != user:
        raise HTTPException(403, "session belongs to another user")
    if project_id and str(project_id) != row["project_id"]:
        raise HTTPException(409, "session belongs to a different project")
    repo = _project_repo(request, row["project_id"])
    s = _sessions.get(sid)
    if not s:
        s = DialogueSession(repo, sid, _llm)
        _sessions[sid] = s
    return s


# ---------------------------------------------------------------- health
@app.get("/api/health")
def health() -> dict:
    voiceid_ok = False
    if config.SPEAKER_ID_ENABLED:
        try:
            r = httpx.get(f"{config.SPEAKER_ID_URL}/health", timeout=1.5)
            voiceid_ok = r.status_code == 200
        except Exception:
            voiceid_ok = False
    return {
        "db": os.path.exists(config.SITE_DB_PATH),
        "llm": config.llm_provider(),
        "rime": config.RIME_ENABLED,
        "voiceid": voiceid_ok,
        "engine": ENGINE_READY,
    }


# ---------------------------------------------------------------- LiveKit room token
@app.post("/api/rtc/token")
async def rtc_token(request: Request) -> dict:
    """Mint a LiveKit access token so the browser can join a room. The agent worker
    joins the same room automatically (dispatched by the LiveKit server)."""
    lk_url = os.getenv("LIVEKIT_URL", "").strip()
    lk_key = os.getenv("LIVEKIT_API_KEY", "").strip()
    lk_secret = os.getenv("LIVEKIT_API_SECRET", "").strip()
    if not (lk_url and lk_key and lk_secret) or lk_url.startswith("<"):
        raise HTTPException(503, "LiveKit not configured (LIVEKIT_URL/API_KEY/API_SECRET)")
    user = _user_id(request)
    _reserve_or_limit(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    project_id = str((body or {}).get("projectId") or config.PROJECT_ID)
    _project_repo(request, project_id)
    import uuid as _uuid

    from livekit.api import AccessToken, VideoGrants

    identity = f"{user}#{_uuid.uuid4().hex[:6]}"  # never client-chosen: the agent trusts it
    room = (body or {}).get("room") or f"{os.getenv('AGENT_ROOM_PREFIX', 'vesper')}-{_uuid.uuid4().hex[:8]}"
    tok = (
        AccessToken(lk_key, lk_secret)
        .with_identity(identity)
        .with_name((body or {}).get("name") or "Site Manager")
        .with_metadata(json.dumps({"user_id": user, "language": (body or {}).get("language", "en-IN"),
                                  "projectId": project_id}))
        .with_grants(VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True))
    )
    return {"url": lk_url, "token": tok.to_jwt(), "room": room, "identity": identity}


# ---------------------------------------------------------------- STT (Sarvam, Groq Whisper fallback)
@app.post("/api/stt")
async def stt(file: UploadFile = File(...), language: str = Form("")):
    """Server-side speech-to-text. Browser webkitSpeechRecognition fails on most Linux
    Chromium builds ('network' error); the frontend records with MediaRecorder and posts
    the blob here. Sarvam saaras:v3 REST first (Indian English / Hinglish), Groq Whisper
    large-v3 as automatic fallback (backend/stt_sarvam.py). Response shape: {"text": str}."""
    import stt_sarvam

    if not stt_sarvam.providers():
        return JSONResponse({"error": "no STT provider (SARVAM_API_KEY / GROQ_API_KEY missing)"},
                            status_code=503)
    raw = await file.read()
    if not raw:
        raise HTTPException(422, "empty audio")
    language = language if isinstance(language, str) else ""  # direct calls pass the Form default
    try:
        out = await stt_sarvam.transcribe(raw, file.filename or "turn.webm",
                                          file.content_type or "audio/webm", language)
        return {"text": out["text"]}
    except stt_sarvam.SttError as e:  # every configured provider failed; map the last one
        if e.status == 0:
            return JSONResponse({"error": "STT provider timed out"}, status_code=504)
        if e.status == -1:
            return JSONResponse({"error": "STT provider is unavailable"}, status_code=503)
        if e.detail == "invalid provider response":
            return JSONResponse({"error": "invalid STT provider response"}, status_code=502)
        return _stt_error_response(e.status, e.detail)


# ---------------------------------------------------------------- speaker enrollment
@app.get("/api/voice/status")
async def voice_status(request: Request) -> dict:
    if not config.SPEAKER_ID_ENABLED:
        return {"enabled": False, "enrolled": False, "reachable": False}
    user = _user_id(request)
    try:
        async with httpx.AsyncClient(timeout=2.0) as cx:
            r = await cx.get(f"{config.SPEAKER_ID_URL}/health", params={"user_id": user})
        j = r.json() if r.status_code == 200 else {}
        return {"enabled": True, "reachable": r.status_code == 200,
                "enrolled": bool(j.get("enrolled")), "threshold": j.get("threshold")}
    except Exception as e:
        return {"enabled": True, "reachable": False, "enrolled": False, "error": str(e)}


@app.post("/api/voice/enroll")
async def voice_enroll(request: Request):
    """Forward N live audio clips to the voiceid sidecar to (re)enroll the site manager."""
    if not config.SPEAKER_ID_ENABLED:
        raise HTTPException(409, "speaker id disabled")
    user = _user_id(request)
    form = await request.form()
    files = form.getlist("files") or ([form["file"]] if "file" in form else [])
    if not files:
        raise HTTPException(422, "no audio clips")
    payload = []
    for f in files:
        raw = await f.read()
        payload.append(("files", (getattr(f, "filename", "clip.webm"), raw,
                                  getattr(f, "content_type", None) or "application/octet-stream")))
    try:
        async with httpx.AsyncClient(timeout=30.0) as cx:
            r = await cx.post(f"{config.SPEAKER_ID_URL}/enroll", files=payload, data={"user_id": user})
        return JSONResponse(r.json(), status_code=r.status_code)
    except Exception as e:
        raise HTTPException(502, f"voiceid enroll failed: {e}")


# ---------------------------------------------------------------- session
@app.post("/api/session")
async def new_session(request: Request) -> dict:
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    user = _user_id(request)
    repo = _project_repo(request, body.get("projectId"))
    sid = dbmod.create_session(repo, user)
    _sessions[sid] = DialogueSession(repo, sid, _llm)
    return {"sessionId": sid, "commandLimit": config.FREE_COMMAND_LIMIT if config.ENFORCE_FREE_COMMAND_LIMIT else None,
            "commandsUsed": dbmod.command_usage(_repo, user) if config.ENFORCE_FREE_COMMAND_LIMIT else 0}


@app.post("/api/bootstrap-demo")
async def bootstrap_demo(request: Request) -> dict:
    """Give the named demo account a small, clearly-labelled conversation archive once."""
    user = _user_id(request)
    body = await request.json()
    if str(body.get("email", "")).strip().lower() != config.DEMO_SEED_EMAIL:
        return {"seeded": False}
    if dbmod.sessions_for_user(_repo, user, limit=1):
        return {"seeded": False}
    sid = dbmod.create_session(_repo, user)
    dbmod.insert_turn(_repo, {"sessionId": sid, "role": "user", "text": "What should I check before today’s L4 slab pour?", "state": "capturing"})
    dbmod.insert_turn(_repo, {"sessionId": sid, "role": "agent", "text": "Start with the L4 pre-pour hold point and RFI-050. Confirm the latest S-301 revision and the cover requirement before logging.", "state": "challenging"})
    return {"seeded": True}


# ---------------------------------------------------------------- turn
async def _verify_speaker(audio: UploadFile | None, user: str) -> dict | None:
    """Fail closed: an unreachable sidecar, a missing enrolment or an undecodable clip all
    return match=False, which locks every write decision for that voice turn."""
    if not audio or not config.SPEAKER_ID_ENABLED:
        return None
    try:
        raw = await audio.read()
        async with httpx.AsyncClient(timeout=8.0) as cx:
            r = await cx.post(f"{config.SPEAKER_ID_URL}/verify", data={"user_id": user},
                              files={"file": (audio.filename or "turn.webm", raw,
                                              audio.content_type or "application/octet-stream")})
        if r.status_code == 200:
            return r.json()
        if r.status_code == 409:
            return {"match": False, "score": 0.0, "error": "not_enrolled"}
        return {"match": False, "score": 0.0, "error": f"voiceid {r.status_code}"}
    except Exception:
        return {"match": False, "score": 0.0, "error": "voiceid_unreachable"}


@app.post("/api/turn")
async def turn(
    request: Request,
    sessionId: str = Form(None),
    text: str = Form(""),
    bargeIn: str = Form(""),
    noise: str = Form("none"),
    decision: str = Form(None),
    language: str = Form("en-IN"),
    projectId: str = Form(None),
    audio: UploadFile | None = None,
) -> dict:
    # accept JSON too (typed fallback path)
    if sessionId is None:
        try:
            body = await request.json()
            sessionId = body["sessionId"]
            text = body.get("text", "")
            bargeIn = body.get("bargeIn", False)
            noise = body.get("noise", "none")
            decision = body.get("decision")
            language = body.get("language", "en-IN")
            projectId = body.get("projectId")
        except Exception:
            raise HTTPException(422, "sessionId required")

    user = _user_id(request)
    sess = _session(sessionId, user, request, projectId)
    _reserve_or_limit(request)
    speaker = await _verify_speaker(audio, user)
    if speaker is not None:
        sess.voice_speaker = speaker  # last VOICE turn's verdict gates decisions
    barge = str(bargeIn).lower() in ("1", "true", "yes", "on")

    # an unverified voice cannot trigger a write — neither by button nor by saying "log it"
    sess.writes_locked = _speaker_locked(sess)
    out: dict = sess.handle(text=text or "", barge_in=barge, noise=noise or "none",
                            decision=decision, speaker=speaker, language=language)
    out = dict(out)
    out["speaker"] = speaker

    # speaker gate
    if any(e.startswith("decision_refused:speaker_gate") for e in out.get("events", [])):
        msg = "Logging is locked: your voice is not verified as the enrolled site manager. "
        out["reply"] = {"text": msg + out["reply"]["text"], "speech": msg + out["reply"].get("speech", "")}
    if _speaker_locked(sess):
        out["allowedDecisions"] = [d for d in out.get("allowedDecisions", []) if d == "cancel"]
        out.setdefault("blockers", []).append({
            "kind": "speaker_gate", "severity": "blocker",
            "detail": "Speaker not recognised as the enrolled site manager; logging is locked.",
            "evidence": {"score": (sess.voice_speaker or {}).get("score"),
                         "reason": (sess.voice_speaker or {}).get("error")},
        })
    return out


# ---------------------------------------------------------------- decision
_WRITE_DECISIONS = ("log_observation", "raise_rfi", "raise_ncr", "stop_work")


def _speaker_locked(sess) -> bool:
    """Once a session has spoken through the mic, writes need that voice to match the
    signed-in user's enrolled profile. Typed turns are covered by the Clerk account alone."""
    v = getattr(sess, "voice_speaker", None)
    return bool(config.SPEAKER_ID_ENABLED and v is not None and not v.get("match"))


@app.post("/api/decision")
async def decide(request: Request) -> dict:
    body = await request.json()
    user = _user_id(request)
    sess = _session(body["sessionId"], user, request, body.get("projectId"))
    dec = body["decision"]
    if dec in _WRITE_DECISIONS and _speaker_locked(sess):
        raise HTTPException(403, "speaker not verified; logging locked")
    return dict(sess.handle(text="", decision=dec, language=body.get("language")))


@app.get("/api/conversations")
async def conversations(request: Request, projectId: str = config.PROJECT_ID) -> dict:
    user = _user_id(request)
    repo = _project_repo(request, projectId)
    sessions = dbmod.sessions_for_user(repo, user)
    for session in sessions:
        session["turns"] = dbmod.turns_for_session(repo, session["session_id"])
    return {"sessions": sessions, "commandLimit": config.FREE_COMMAND_LIMIT if config.ENFORCE_FREE_COMMAND_LIMIT else None,
            "commandsUsed": dbmod.command_usage(_repo, user) if config.ENFORCE_FREE_COMMAND_LIMIT else 0}


# ---------------------------------------------------------------- observations
@app.get("/api/observations")
def observations(request: Request, projectId: str = config.PROJECT_ID) -> list[dict]:
    _user_id(request)
    repo = _project_repo(request, projectId)
    rows = repo._all(
        "SELECT observation_id, created_at, location_id, element, attribute, value_claimed, unit, "
        "drawing_id, revision_claimed, contradiction_flag, contradiction_kinds, final_decision, linked_rfi_id "
        "FROM field_observations WHERE project_id = ? ORDER BY created_at DESC", (repo.project_id,))
    for r in rows:
        r["contradiction_kinds"] = json.loads(r["contradiction_kinds"]) if r.get("contradiction_kinds") else []
    return rows


@app.get("/api/observations/{obs_id}")
def observation(request: Request, obs_id: str, projectId: str = config.PROJECT_ID) -> dict:
    _user_id(request)
    repo = _project_repo(request, projectId)
    row = repo._one("SELECT * FROM field_observations WHERE project_id = ? AND observation_id = ?",
                    (repo.project_id, obs_id))
    if not row:
        raise HTTPException(404, "not found")
    row["contradiction_kinds"] = json.loads(row["contradiction_kinds"]) if row.get("contradiction_kinds") else []
    evidence: dict[str, Any] = {}
    if row.get("drawing_id"):
        evidence["drawing"] = repo.drawing_by_id(row["drawing_id"])
    if row.get("linked_rfi_id"):
        evidence["rfi"] = repo._one("SELECT * FROM rfis WHERE project_id = ? AND rfi_id = ?",
                                    (repo.project_id, row["linked_rfi_id"]))
    row["evidence"] = evidence
    return row


# ---------------------------------------------------------------- scenarios
@app.get("/api/scenarios")
def scenarios(request: Request, projectId: str = config.PROJECT_ID) -> list[dict]:
    try:
        from scenarios import load_scenarios
        repo = _project_repo(request, projectId)
        return [{"id": s["id"], "title": s["title"]} for s in load_scenarios(repo.project_id)]
    except Exception:
        return []


@app.post("/api/scenarios/run")
async def scenarios_run(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        from scenarios import run_all
        repo = _project_repo(request, body.get("projectId"))
        return run_all(body.get("ids"), project_id=repo.project_id)
    except Exception as e:
        raise HTTPException(501, f"scenario runner not ready: {e}")


# ---------------------------------------------------------------- Rime TTS proxy
_tts_cache: dict[str, bytes] = {}


@app.post("/api/tts")
async def tts(request: Request):
    _user_id(request)
    body = await request.json()
    text = speakable((body.get("text") or "").strip()[:600])  # same ear-shaping as the live agent
    language = str(body.get("language") or "en-IN").strip().lower()
    if not text:
        raise HTTPException(422, "text required")
    # Sarvam bulbul first: its Indian English and Hindi voices read as local, where Rime's English
    # sounds foreign to the site managers this is for. Any Sarvam failure falls through to Rime
    # rather than returning silence; TTS_PROVIDER=rime skips Sarvam entirely.
    if os.getenv("TTS_PROVIDER", "sarvam").strip().lower() == "sarvam" and config.SARVAM_ENABLED:
        sv_lang = "hi-IN" if language.startswith("hi") else "en-IN"
        sv_model = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
        sv_speaker = os.getenv("SARVAM_TTS_SPEAKER", "ritu")
        sv_key = f"sarvam:{sv_model}:{sv_speaker}:{sv_lang}:{text}"
        if sv_key in _tts_cache:
            return StreamingResponse(io.BytesIO(_tts_cache[sv_key]), media_type="audio/wav")
        try:
            async with httpx.AsyncClient(timeout=30.0) as cx:
                sr = await cx.post(
                    "https://api.sarvam.ai/text-to-speech",
                    headers={"api-subscription-key": config.SARVAM_API_KEY,
                             "Content-Type": "application/json"},
                    json={"text": text, "target_language_code": sv_lang,
                          "model": sv_model, "speaker": sv_speaker})
            if sr.status_code == 200:
                b64 = (sr.json().get("audios") or [None])[0]
                if b64:
                    audio = base64.b64decode(b64)
                    if len(_tts_cache) < 64:
                        _tts_cache[sv_key] = audio
                    return StreamingResponse(io.BytesIO(audio), media_type="audio/wav")
        except Exception:
            pass  # fall through to Rime

    if not config.RIME_ENABLED:
        return JSONResponse({"error": "rime key missing"}, status_code=503)
    use_hinglish = language.startswith("hi")
    speaker = config.RIME_SPEAKER if use_hinglish else config.RIME_SPEAKER_EN
    rime_lang = config.RIME_LANG if use_hinglish else config.RIME_LANG_EN
    model = config.RIME_MODEL if use_hinglish else config.RIME_MODEL_EN
    cache_key = f"{model}:{speaker}:{rime_lang}:{text}"
    if cache_key in _tts_cache:
        return StreamingResponse(io.BytesIO(_tts_cache[cache_key]), media_type="audio/mpeg")
    try:
        async with httpx.AsyncClient(timeout=20.0) as cx:
            r = await cx.post(
                "https://users.rime.ai/v1/rime-tts",
                headers={"Authorization": f"Bearer {config.RIME_API_KEY}",
                         "Accept": "audio/mp3", "Content-Type": "application/json"},
                json={"text": text, "speaker": speaker,
                      "modelId": model, "lang": rime_lang})
        if r.status_code != 200:
            return JSONResponse({"error": f"rime {r.status_code}", "detail": r.text[:300]},
                                status_code=502)
        audio = r.content
        if len(_tts_cache) < 64:
            _tts_cache[cache_key] = audio
        return StreamingResponse(io.BytesIO(audio), media_type="audio/mpeg")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


# ---------------------------------------------------------------- Memory (thin)
@app.get("/api/drawings")
def drawings(request: Request, projectId: str = config.PROJECT_ID) -> list[dict]:
    _user_id(request)
    repo = _project_repo(request, projectId)
    return repo._all("SELECT * FROM drawings WHERE project_id = ? ORDER BY drawing_number, rev_ordinal",
                     (repo.project_id,))


@app.get("/api/rfis")
def rfis(request: Request, projectId: str = config.PROJECT_ID) -> list[dict]:
    _user_id(request)
    repo = _project_repo(request, projectId)
    return repo._all("SELECT * FROM rfis WHERE project_id = ? ORDER BY rfi_id", (repo.project_id,))


@app.get("/api/permits")
def permits(request: Request, projectId: str = config.PROJECT_ID) -> list[dict]:
    _user_id(request)
    return _project_repo(request, projectId).permits_with_checks()


# ---------------------------------------------------------------- v2 routers
# Memory layer, ingestion and tenancy/onboarding live in routes/*. Each import is optional so
# the v1 API above still boots while a module is being built; the failure is printed, not hidden.
import importlib as _importlib

V2_ROUTERS: dict[str, str] = {}
for _mod in ("routes.memory", "routes.ingest", "routes.tenancy", "routes.tools"):
    try:
        app.include_router(_importlib.import_module(_mod).router)
        V2_ROUTERS[_mod] = "ok"
    except Exception as _exc:  # noqa: BLE001
        V2_ROUTERS[_mod] = repr(_exc)[:200]
        print(f"[v2] {_mod} not loaded: {_exc!r}")


@app.get("/api/v2/status")
def v2_status() -> dict:
    return {"routers": V2_ROUTERS}
