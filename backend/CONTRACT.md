# backend/ — frozen interface contract

Everything in `backend/` and `app/` builds against this. Do not change signatures
without updating this file.

## Processes

| process | port | start |
|---|---|---|
| voiceid sidecar | 8788 | `voiceid/run.sh` |
| backend API | 8000 | `cd backend && .venv/bin/uvicorn main:app --port 8000` |
| frontend (Next) | 3000 | `cd app && npm run dev` |

Python: `~/.local/bin/python3.12` (system `python3` is 3.14, no torch wheels).

## Backend HTTP API (`http://localhost:8000`)

```
GET  /api/health
  -> {db:bool, llm:"nvidia"|"groq"|"off", rime:bool, voiceid:bool}

POST /api/session            body {userName?}
  -> {sessionId}

POST /api/turn               multipart/form-data OR json
  fields: sessionId (str), text (str), bargeIn (bool, opt),
          noise ("none"|"low"|"medium"|"high", opt), audio (file, opt wav/webm)
  -> {
       state: "capturing"|"checking"|"challenging"|"confirming"|"blocked"|"logged"|"cancelled",
       entities: [{kind,label,confidence}],
       contradictions: [{kind,severity,detail,evidence}],
       blockers: [{kind,severity,detail,evidence}],
       missing: [{kind,detail,evidence}],
       reply: {text, speech},
       allowedDecisions: ["log_observation"|"raise_rfi"|"raise_ncr"|"stop_work"|"cancel"],
       slots: {name: {value, confidence, source, confirmed}},
       resolved: {location_id?, drawing_id?, drawing_label?, location_inferred?, fact?},
       speaker: {match:bool, score:float} | null,
       clarifiedKinds: [str],
       events: [str]
     }

POST /api/decision           json {sessionId, decision}
  -> {state, reply:{text,speech},
      logged: {observation_id?, rfi_id?, decision} | null,
      allowedDecisions:[...]}

GET  /api/observations
  -> [{observation_id, created_at, location_id, element, attribute, value_claimed, unit,
       drawing_id, revision_claimed, contradiction_flag, contradiction_kinds:[str],
       final_decision, linked_rfi_id}]

GET  /api/observations/{id}
  -> full field_observations row + {evidence:{drawing,rfi,code_ref}}

GET  /api/scenarios
  -> [{id, title}]

POST /api/scenarios/run      json {ids?: [str]}   (default: all 10)
  -> {passed:int, total:int, wrongLogs:int, results:[
        {id,title,pass:bool,failures:[str],kindsSeen:[str],clarified:bool,
         finalDecision:str, logged:[{...}], transcript:[{role,text,bargeIn?,state?}]}
     ]}

POST /api/tts                json {text}
  -> audio/mpeg stream        (503 {error:"rime key missing"} -> frontend uses SpeechSynthesis)

GET  /api/drawings  /api/rfis  /api/permits
  -> list rows (Memory screen; thin)

GET  /api/voice/status
  -> {enabled:bool, reachable:bool, enrolled:bool, threshold?:float}

POST /api/voice/enroll        multipart/form-data, field `files` repeated (>=1 audio blob)
  -> {enrolled:bool, samples:int, dims:int, cohesion:float}   (proxied to voiceid /enroll)
```

STT: browser Web Speech API (`webkitSpeechRecognition`) over the WebRTC mic capture
(`getUserMedia`/`MediaRecorder`). No server-side STT, no LiveKit.

Gate: `/api/turn` with `audio` -> backend POSTs it to voiceid `/verify`. If
`SPEAKER_ID_ENABLED=true` and `match=false`: response `allowedDecisions=[]` and a
`{kind:"speaker_gate",severity:"blocker",...}` entry in `blockers`; `/api/decision`
returns HTTP 403 for any logging decision. Turns with no `audio` skip the gate.

## Python engine interface (`backend/engine/`)  — WS-A owns

```python
# engine/dialogue.py
class DialogueSession:
    def __init__(self, repo: Repo, session_id: str, llm=None, persist_turns: bool = True): ...
    def handle(self, *, text: str, barge_in: bool = False, noise: str = "none",
               decision: str | None = None, speaker: dict | None = None) -> AgentTurn: ...
    # AgentTurn is a dict/dataclass with exactly the /api/turn response keys above
    #   (minus `speaker`, which main.py attaches).

# engine/extract.py
def extract(raw: str) -> Extraction        # slots + confidence, deterministic, no network
def chips(ex: Extraction) -> list[dict]    # [{kind,label,confidence}]

# engine/contradictions.py
def check(slots, repo: Repo, confirmed: set[str]) -> CheckResult

# engine/replies.py
# challenge_reply / blocker_reply / missing_reply / confirm_slots_reply /
# readback_reply / unknown_drawing_reply / done_reply  -> {"text":..., "speech":...}

# engine/llm.py
def make_llm_assist() -> callable | None   # NVIDIA NIM (OpenAI-compat) -> Groq -> None
```

Port faithfully from the TypeScript reference:
`app/lib/parser/extract.ts`, `app/lib/engine/{contradictions,dialogue,replies}.ts`.
Use `app/lib/engine/repo.ts` / `persist.ts` only to understand `backend/db.py` (already ported).
Secondary reference for the FastAPI/session shape only: `../DataForge-Rime/agent/`.

## DB layer (`backend/db.py`)  — DONE, frozen

`Repo(conn, project_id="P1")` mirrors `repo.ts`:
`locations() resolve_location(q) drawing_revisions(n) drawing_numbers()
resolve_drawing_number(s) latest_drawing(n) drawing_by_id(id) is_verified_latest(id)
latest_drawing_for_location(loc, level) current_facts(loc, attr?, elem?)
fact_on_revision(dn,rev,loc,attr) facts_any_revision(dn,loc,attr) rfi_for_drawing(id)
related_location_ids(loc) permit_blockers(loc, activity) permits_with_checks()
hold_point_blockers(loc) template(id) location_exists(id)`

Module fns mirror `persist.ts`:
`create_session(repo,user_name?) end_session(repo,sid)
insert_turn(repo, {...}) -> int
insert_observation(repo, ObservationInput) -> str   # SAFETY GATE, raises SafetyGateError
insert_rfi(repo, {...}) -> str`

Rows returned as plain dicts (`conn.row_factory = sqlite3.Row` -> `dict(row)`).

## Hard rules (dialogue.py AND re-checked in db.insert_observation)

1. Never log without first SPEAKING the challenge for every contradiction.
2. Never log an unconfirmed / low-confidence slot (incl. LLM-only suggestions).
3. Logged `drawing_id` MUST be the verified latest For-Construction revision.
4. While a permit / hold-point blocker is open: only stop_work / raise_ncr / cancel.
