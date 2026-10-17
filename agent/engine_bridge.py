"""Bridge from the LiveKit agent to the deterministic engine in backend/.

The tested engine (extract -> DB retrieval -> answers / contradiction rules -> guarded state
machine -> safety-gated persist) is the source of truth. Every finished user turn goes
straight through it; the LLM only sees the COMPACT result when the engine could not resolve
a question on its own.
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import config  # noqa: E402
import db as dbmod  # noqa: E402
from engine import memory  # noqa: E402
from engine.dialogue import DialogueSession  # noqa: E402

WRITE_DECISIONS = ("log_observation", "raise_rfi", "raise_ncr", "stop_work")


def _compact(turn: dict) -> dict:
    """Everything the LLM is allowed to speak from — and nothing else. Kept small on purpose:
    evidence candidate lists (every drawing / location) only slowed the model down."""
    res = turn.get("resolved", {}) or {}
    ev_keys = ("drawing_number", "revision", "issued_on", "via_rfi", "code_ref", "expected",
               "claimed", "tolerance", "unit", "permit_id", "checks", "items")
    slim = lambda k: {"kind": k["kind"], "detail": k["detail"],  # noqa: E731
                      "evidence": {e: v for e, v in (k.get("evidence") or {}).items() if e in ev_keys and v is not None}}
    return {
        "state": turn["state"],
        "kind": turn.get("kind", "observation"),
        "unresolved": bool(turn.get("unresolved")),
        "spoken_reply": (turn.get("reply") or {}).get("text", ""),
        "contradictions": [slim(k) for k in turn.get("contradictions", [])],
        "blockers": [slim(k) for k in turn.get("blockers", [])],
        "missing": [{"detail": k["detail"]} for k in turn.get("missing", [])],
        "resolved": {
            "location_id": res.get("location_id"),
            "drawing": res.get("drawing_label"),
            "drawing_id": res.get("drawing_id"),
            "fact": res.get("fact"),
        },
        "slots": {k: v.get("value") for k, v in (turn.get("slots") or {}).items()},
        "allowed_decisions": turn.get("allowedDecisions", []),
        "logged": turn.get("logged"),
    }


class Brain:
    """One per LiveKit room. Holds the DialogueSession so slots accumulate across turns, and
    records the session under the signed-in user so it appears in their history."""

    def __init__(self, user_id: str = "Site Manager (voice)", language: str = "en-IN",
                 project_id: str | None = None) -> None:
        self.repo = dbmod.Repo(dbmod.connect(), project_id or config.PROJECT_ID)
        self.user_id = user_id
        self.language = language
        self.session_id = dbmod.create_session(self.repo, user_id, lang=language)
        self._dlg = DialogueSession(self.repo, self.session_id, llm=None, persist_turns=True)
        # Fail closed: when speaker ID is on, nothing is written until the live voice has been
        # verified against this user's enrolled profile (updated by voiceprofile.VoiceProfiler).
        self.speaker_required = config.SPEAKER_ID_ENABLED
        self.speaker_ok = not self.speaker_required
        self.speaker_score: float | None = None
        self.speaker_reason: str | None = "not verified yet" if self.speaker_required else None

    def _locked(self) -> bool:
        return self.speaker_required and not self.speaker_ok

    def observe(self, utterance: str) -> dict:
        self._dlg.writes_locked = self._locked()
        out = _compact(self._dlg.handle(text=utterance or "", noise="none", language=self.language))
        if self._locked() and out["allowed_decisions"]:
            out["allowed_decisions"] = [d for d in out["allowed_decisions"] if d == "cancel"]
            out["speaker_locked"] = self.lock_reason()
        return out

    def lock_reason(self) -> str:
        if self.speaker_score is not None:
            return f"voice not matched to the enrolled manager (score {self.speaker_score:.2f})"
        return f"voice not verified ({self.speaker_reason or 'pending'})"

    def site_brief(self) -> dict:
        """Structured situation report — what has already happened on this site."""
        return memory.site_brief(self.repo)

    def brief_text(self) -> str:
        """Prose form of the brief, for the agent's system prompt."""
        return memory.brief_text(self.site_brief())

    def recall(self, query: str, limit: int = 5) -> dict:
        """Search real project history (facts, observations, DPRs, RFIs, submittals,
        permits, drawings) before the scraped template library."""
        return memory.recall(self.repo, query, limit)

    def decide(self, decision: str) -> dict:
        """decision: log_observation | raise_rfi | raise_ncr | stop_work | cancel."""
        if decision in WRITE_DECISIONS and self._locked():
            return {"refused": True, "state": self._dlg.state,
                    "spoken_reply": f"I can't do that yet — {self.lock_reason()}. Nothing has been logged.",
                    "reason": self.lock_reason()}
        self._dlg.writes_locked = False
        return _compact(self._dlg.handle(text="", decision=decision, language=self.language))
