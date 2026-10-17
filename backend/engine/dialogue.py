"""Dialogue state machine: capturing -> checking -> challenging -> confirming -> logged | blocked | cancelled.

Faithful 1:1 port of app/lib/engine/dialogue.ts.

Safety invariants (enforced here AND re-checked in db.insert_observation):
 1. Never log with a drawing_id that is not the verified latest For Construction revision.
 2. Never log a value/location that is unconfirmed or low-confidence (incl. LLM-only).
 3. Every contradiction is spoken as a clarification in an EARLIER agent turn before any write.
 4. Blockers (permit / hold point) -> only stop_work / raise_ncr / cancel.
"""
from __future__ import annotations

import json

from db import SafetyGateError, insert_observation, insert_rfi, insert_turn

from .answer import answer, is_question
from .contradictions import check
from .extract import chips, extract
from . import replies, replies_en

SLOT_KEYS = ["grid", "level", "zone", "element", "attribute", "value", "unit", "drawingNumber",
             "revisionClaimed", "drawingValueClaimed", "activity", "defect"]
NOISE_FACTOR = {"none": 1, "low": 0.95, "medium": 0.8, "high": 0.65}
class DialogueSession:
    def __init__(self, repo, session_id: str, llm=None, persist_turns: bool = True) -> None:
        self.repo = repo
        self.session_id = session_id
        self.sessionId = session_id
        self.llm = llm
        self.persist_turns = persist_turns

        self.state = "capturing"
        self.slots: dict = {}
        self.confirmed: set[str] = set()
        self.pendingConfirm: list[str] = []
        self.spokenSig = None
        self.spokenKinds: list[str] = []
        self.clarificationText = None
        self.lastOffer = None
        self.utterances: list[str] = []
        self.photoUrl = None
        self.gps = None
        self.lastCheck = None
        self.last_speaker = None
        self.question_ctx: dict = {}
        self._replies = replies

    def _reset_observation(self) -> None:
        self.state = "capturing"
        self.slots = {}
        self.confirmed = set()
        self.pendingConfirm = []
        self.spokenSig = None
        self.spokenKinds = []
        self.clarificationText = None
        self.lastOffer = None
        self.utterances = []
        self.photoUrl = None
        self.gps = None
        self.lastCheck = None

    def _sv(self, k):
        s = self.slots.get(k)
        return s["value"] if s else None

    def handle(self, *, text: str = "", barge_in: bool = False, noise: str = "none",
               decision: str | None = None, speaker: dict | None = None,
               language: str | None = None) -> dict:
        if language:
            self._replies = replies_en if language.lower().startswith("en") else replies
        r = self._replies
        self.last_speaker = speaker
        if self.state in ("logged", "cancelled"):
            self._reset_observation()
        events: list[str] = []
        if barge_in:
            events.append("barge_in")
        text = (text or "").strip()
        prev_state = self.state
        if text:
            self.utterances.append(text)

        # ---------------- extract (+ optional LLM suggestions)
        ex = extract(text)

        # ---------------- questions are answered from the record, never fed into the
        # observation slots (that turned "what is the cover at E-1?" into "give the cover in mm").
        if text and not decision and not self.pendingConfirm and is_question(text, ex):
            return self._answer_turn(text, ex, prev_state, barge_in, noise, events)
        # A direct reference to another named/grid location starts a fresh observation. Without
        # this, a completed OPD observation could leak E-1 into a following question about the
        # ambulance-road retaining wall. Spoken corrections and barge-ins remain part of the
        # current observation, preserving the safety flow for self-corrections.
        explicit_place = getattr(ex, "grid", None) or getattr(ex, "zone", None)
        current_grid = self._sv("grid")
        current_zone = self._sv("zone")
        changes_place = bool(
            explicit_place
            and ((getattr(ex, "grid", None) and current_grid != ex.grid["value"])
                 or (getattr(ex, "zone", None) and current_zone != ex.zone["value"]))
        )
        if changes_place and self.slots and not ex.isCorrection and not barge_in:
            events.append("new_observation:explicit_location")
            self._reset_observation()
        f = NOISE_FACTOR.get(noise or "none", 1)
        if f != 1:
            for k in SLOT_KEYS:
                s = getattr(ex, k, None)
                if s:
                    s["confidence"] = round(s["confidence"] * f, 2)
        if self.llm and len(text.split()) >= 4:
            try:
                sug = self.llm(text, ex) or {}
            except Exception:
                sug = {}
            for k, v in sug.items():
                if v and not getattr(ex, k, None) and not self.slots.get(k):
                    setattr(ex, k, v)
                    events.append(f"llm_suggested:{k}")

        # ---------------- merge (later speech overwrites -> corrections)
        changed: list[str] = []
        for k in SLOT_KEYS:
            s = getattr(ex, k, None)
            if not s:
                continue
            cur = self.slots.get(k)
            # Acknowledgment guard: once a revision_mismatch has been challenged, the user
            # echoing the correct revision back ("achha R4 aa gaya tha") must NOT overwrite
            # their original (stale) claim — the logged row records what they actually claimed.
            if k == "revisionClaimed" and cur and "revision_mismatch" in self.spokenKinds:
                continue
            if not cur or cur["value"] != s["value"]:
                if cur:
                    events.append(f"correction:{k} {cur['value']}→{s['value']}")
                changed.append(k)
                self.confirmed.discard(k)
                self.slots[k] = s
            elif s["confidence"] > cur["confidence"]:
                self.slots[k] = s
        if (self.slots.get("grid") and self.slots["grid"]["value"] in ex.negatedGrids
                and not getattr(ex, "grid", None)):
            events.append(f"correction:grid {self.slots['grid']['value']}→(cleared)")
            del self.slots["grid"]
            changed.append("grid")
        if (self.slots.get("value") and self.slots["value"]["value"] in ex.negatedValues
                and not getattr(ex, "value", None)):
            events.append(f"correction:value {self.slots['value']['value']}→(cleared)")
            del self.slots["value"]
            changed.append("value")

        # ---------------- voice confirmation of pending low-confidence slots
        had_pending = len(self.pendingConfirm) > 0
        if had_pending:
            pending_changed = any(p in changed for p in self.pendingConfirm)
            if ex.affirm and not pending_changed:
                for p in self.pendingConfirm:
                    self.confirmed.add(p)
                    s = self.slots.get(p)
                    if s:
                        s["confidence"] = 1
                        s["source"] = "user_confirmed"
                events.append(f"confirmed:{','.join(self.pendingConfirm)}")
                self.pendingConfirm = []
            elif ex.deny and not changed:
                for p in self.pendingConfirm:
                    self.slots.pop(p, None)
                events.append(f"rejected:{','.join(self.pendingConfirm)}")
                self.pendingConfirm = []

        # ---------------- decision
        decision = decision or ex.decision
        ambiguous_yes = False
        if not decision and ex.affirm and not had_pending and not changed:
            if self.lastOffer == "log":
                decision = "log_observation"
            elif self.lastOffer == "log_or_rfi":
                ambiguous_yes = True
        # Speaker gate AFTER every way a decision can arise (explicit, spoken, or an "okay/yes"
        # to an offered log) — checking before the affirm path let "OK, log that" slip through.
        if decision in ("log_observation", "raise_rfi", "raise_ncr", "stop_work") and getattr(self, "writes_locked", False):
            events.append(f"decision_refused:speaker_gate:{decision}")
            decision = None
        if decision:
            events.append(f"decision:{decision}")

        user_turn_id = None
        if self.persist_turns:
            user_turn_id = insert_turn(self.repo, {
                "sessionId": self.session_id, "role": "user",
                "text": text or (f"[button] {decision}" if decision else ""),
                "entities": {"extracted": chips(ex), "normalized": ex.normalized,
                             "noise": noise or "none"},
                "state": prev_state, "bargeIn": barge_in,
            })

        # ---------------- check
        self.state = "checking"
        c = check(self.slots, self.repo, self.confirmed)
        self.lastCheck = c
        clarify_drawing = next(
            (k for k in c.contradictions
             if k["kind"] == "unknown_drawing" and not k["evidence"].get("drawing_id")), None)
        flags = [k for k in c.contradictions if k is not clarify_drawing]
        sig = json.dumps({
            "loc": c.location["location_id"] if c.location else None,
            "attr": c.attribute, "v": c.value, "u": c.unit,
            "d": c.drawing["drawing_id"] if c.drawing else None,
            "act": self._sv("activity"), "defect": self._sv("defect"),
            # NOTE: revisionClaimed / drawingValueClaimed deliberately excluded — correcting the
            # spoken revision to the right one must not re-fire a challenge for the SAME
            # contradiction kind on the same fact (S01), it should let the pending decision run.
            "kinds": sorted(k["kind"] for k in (flags + c.blockers)),
        }, sort_keys=True)
        already_spoken = self.spokenSig == sig

        out = None
        allowed = ["cancel"]
        clarified_kinds: list[str] = []
        logged = None

        def speak(r, kinds, offer):
            nonlocal out, clarified_kinds
            out = r
            self.spokenSig = sig
            self.spokenKinds = kinds
            clarified_kinds = kinds
            self.lastOffer = offer
            if kinds:
                self.clarificationText = r["text"]

        if decision == "cancel":
            self.state = "cancelled"
            out = r.done_reply("cancel")
            logged = {"decision": "cancelled"}
        elif not text and not decision:
            out = r.R(r.REFUSE["nothing"])
            self.state = "capturing" if prev_state == "checking" else prev_state
        elif c.blockers:
            # ---------------- BLOCKED: only stop_work / raise_ncr / cancel
            allowed = ["stop_work", "raise_ncr", "cancel"]
            if decision in ("stop_work", "raise_ncr") and already_spoken:
                out, logged = self._execute(decision, c, [b["kind"] for b in c.blockers], events)
            else:
                self.state = "blocked"
                speak(
                    r.blocker_reply(c, self.slots,
                                  r.DECISION_LABEL[decision]
                                  if (decision and decision not in ("stop_work", "raise_ncr"))
                                  else None),
                    [b["kind"] for b in c.blockers], "blocker",
                )
                if decision in ("stop_work", "raise_ncr"):
                    events.append("decision_deferred_until_blocker_spoken")
        elif clarify_drawing:
            self.state = "challenging"
            speak(r.unknown_drawing_reply(clarify_drawing), ["unknown_drawing"], None)
            if decision:
                events.append("decision_refused:unknown_drawing")
        elif c.missing:
            self.state = "capturing"
            out = r.missing_reply(c, self.slots)
            if decision:
                out = r.R(f"I need those details before logging. {out['text']}")
                events.append("decision_refused:missing_field")
            clarified_kinds = ["missing_critical_field"]
        elif c.lowConfidence:
            self.state = "confirming"
            self.pendingConfirm = list(c.lowConfidence)
            out = r.confirm_slots_reply(c.lowConfidence, self.slots,
                                      (c.drawing or {}).get("drawing_number"))
            if decision:
                out = r.R(f"{r.REFUSE['confirmFirst']} {out['text']}")
                events.append("decision_refused:low_confidence")
            self.lastOffer = None
        elif flags:
            # ---------------- contradictions: must be spoken before any decision is executed
            allowed = ["log_observation", "raise_rfi", "raise_ncr", "cancel"]
            if decision and already_spoken:
                out, logged = self._execute(decision, c, [k["kind"] for k in flags], events)
            elif ambiguous_yes and already_spoken:
                self.state = "challenging"
                out = r.R(r.REFUSE["ambiguousYes"])
            elif ex.rfiDeclined and already_spoken and not decision:
                self.state = "confirming"
                out = r.R(r.REFUSE["rfiDeclined"])
                self.lastOffer = "log"
            else:
                self.state = "challenging"
                speak(r.challenge_reply(c, self.slots, r.REFUSE["clarifyFirst"] if decision else ""),
                      [k["kind"] for k in flags], "log_or_rfi")
                if decision:
                    events.append("decision_deferred_until_clarified")
        else:
            # ---------------- clean: read back, or execute an explicit decision.
            # This branch is only reached when nothing is wrong (no contradictions, blockers,
            # missing critical fields, or low-confidence slots). An explicit spoken decision
            # ("log kar do", "RFI raise karo") is therefore safe to run now — the persist
            # safety-gate re-verifies drawing/location/unit before any write.
            allowed = ["log_observation", "raise_rfi", "raise_ncr", "cancel"]
            if decision:
                out, logged = self._execute(decision, c, [], events)
            elif ex.rfiDeclined and not decision:
                self.state = "confirming"
                speak(r.readback_reply(c, self.slots, "Okay, no RFI."), [], "log")
            else:
                self.state = "confirming"
                speak(r.readback_reply(c, self.slots), [], "log")

        contradictions_out = flags + ([clarify_drawing] if clarify_drawing else [])
        turn = {
            "sessionId": self.session_id,
            "state": self.state,
            "reply": {"text": out["text"], "speech": out["speech"]},
            "entities": chips(ex),
            "contradictions": contradictions_out,
            "blockers": c.blockers,
            "missing": c.missing,
            "lowConfidence": c.lowConfidence,
            "allowedDecisions": [] if self.state in ("logged", "cancelled") else allowed,
            "slots": self.slot_view(),
            "clarifiedKinds": clarified_kinds,
            "events": events,
            "resolved": {
                "location_id": c.location["location_id"] if c.location else None,
                "drawing_id": c.drawing["drawing_id"] if c.drawing else None,
                "location_inferred": c.locationInferred,
                "drawing_label": (f"{c.drawing['drawing_number']} {c.drawing['revision']}"
                                  if c.drawing else None),
                "fact": ({"value": c.fact.get("value_num"), "unit": c.fact.get("unit"),
                          "tolerance": c.fact.get("tolerance"), "revision": c.fact["revision"],
                          "issued_on": c.fact.get("issued_on"), "via_rfi": c.fact.get("via_rfi"),
                          "code_ref": c.fact.get("code_ref")} if c.fact else None),
            },
            "logged": logged,
        }
        if self.persist_turns:
            insert_turn(self.repo, {
                "sessionId": self.session_id, "role": "agent", "text": out["text"],
                "state": self.state,
                "entities": {"slots": turn["slots"], "resolved": turn["resolved"],
                             "contradictions": [k["kind"] for k in contradictions_out],
                             "blockers": [k["kind"] for k in c.blockers], "events": events},
            })
        return turn

    def _answer_turn(self, text, ex, prev_state, barge_in, noise, events) -> dict:
        self.utterances.pop()  # a question is not part of the observation being logged
        # Follow-ups resolve against the observation being discussed first ("tolerance there?"),
        # then against the previous question ("and at E-2?").
        ctx = dict(self.question_ctx)
        for k in ("grid", "zone", "level", "element", "attribute"):
            if self._sv(k) is not None:
                ctx[k] = self._sv(k)
        res = answer(self.repo, text, ex, ctx)
        self.question_ctx = res["context"]
        events.append("answered_question")
        # the pending observation (if any) keeps its state and allowed decisions
        pending = self.lastCheck if prev_state in ("challenging", "blocked", "confirming") else None
        allowed = (["stop_work", "raise_ncr", "cancel"] if prev_state == "blocked"
                   else ["log_observation", "raise_rfi", "raise_ncr", "cancel"] if prev_state in ("challenging", "confirming")
                   else [])
        self.state = prev_state if pending else "capturing"
        out = self._replies.R(res["text"])
        if self.persist_turns:
            insert_turn(self.repo, {"sessionId": self.session_id, "role": "user", "text": text,
                                    "entities": {"extracted": chips(ex), "noise": noise or "none"},
                                    "state": prev_state, "bargeIn": barge_in})
            insert_turn(self.repo, {"sessionId": self.session_id, "role": "agent", "text": out["text"],
                                    "state": self.state, "entities": {"answer": res, "events": events}})
        return {
            "sessionId": self.session_id, "state": self.state, "kind": "answer",
            "unresolved": not res.get("resolved", True),
            "reply": {"text": out["text"], "speech": out["speech"]},
            "entities": chips(ex), "contradictions": [], "blockers": [], "missing": [],
            "lowConfidence": [], "allowedDecisions": allowed, "slots": self.slot_view(),
            "clarifiedKinds": [], "events": events,
            "resolved": {"location_id": res["location_id"], "drawing_id": None,
                         "location_inferred": False, "drawing_label": None, "fact": None},
            "logged": None,
        }

    def _execute(self, decision, c, kinds, events):
        r = self._replies
        if decision == "cancel":
            self.state = "cancelled"
            return r.done_reply("cancel"), {"decision": "cancelled"}
        loc = r.loc_label(c, self.slots)
        attr = r.attr_label(c.attribute)
        drawing_id = (c.drawing["drawing_id"]
                      if (c.drawing and self.repo.is_verified_latest(c.drawing["drawing_id"]))
                      else None)
        if c.mode == "activity":
            mid = f"activity {self._sv('activity')}"
        elif c.mode == "defect":
            mid = f"{self._sv('element') or ''} {self._sv('defect')}".strip()
        else:
            mid = (f"{c.element or ''} {c.attribute or ''} = "
                   f"{c.value if c.value is not None else '?'} {c.unit or ''}").strip()
        if drawing_id:
            link = f"linked {drawing_id}"
            if c.fact:
                link += (f" (latest {c.fact['value_num']}{c.fact.get('unit') or ''}"
                         + (f" ±{c.fact['tolerance']}" if c.fact.get("tolerance") is not None else "")
                         + ")")
        else:
            link = "no drawing link"
        summary_parts = [
            (c.location["location_id"] if c.location else loc),
            mid,
            link,
            (f"flags: {', '.join(kinds)}" if kinds else "no contradictions"),
        ]
        try:
            rfi_id = None
            if decision == "raise_rfi":
                rfi_id = insert_rfi(self.repo, {
                    "subject": f"{loc} {attr or self._sv('activity') or 'site'} clarification",
                    "locationId": c.location["location_id"] if c.location else None,
                    "drawingRef": (c.drawing or {}).get("drawing_number") or self._sv("drawingNumber"),
                    "question": (
                        f"Site observed {attr} {c.value if c.value is not None else ''} "
                        f"{c.unit or ''} at {loc}."
                        + (f" Latest {c.fact['drawing_number']} {c.fact['revision']} shows "
                           f"{c.fact['value_num']} {c.fact.get('unit') or ''}." if c.fact else "")
                        + (f" Flags: {', '.join(kinds)}." if kinds else "")
                        + " Please confirm."
                    ),
                })
                events.append(f"rfi_raised:{rfi_id}")
            obs_id = insert_observation(self.repo, {
                "sessionId": self.session_id,
                "spokenText": " | ".join(self.utterances),
                "summary": " · ".join(summary_parts),
                "locationId": c.location["location_id"] if c.location else None,
                "element": c.element or self._sv("element"),
                "attribute": (c.attribute if c.mode == "measurement"
                              else (f"defect:{self._sv('defect')}" if c.mode == "defect"
                                    else (f"activity:{self._sv('activity')}" if c.mode == "activity"
                                          else None))),
                "value": (c.value if c.mode == "measurement" else None),
                "unit": (c.unit if c.mode == "measurement" else None),
                "drawingId": drawing_id,
                "revisionClaimed": self._sv("revisionClaimed"),
                "contradictionKinds": kinds,
                "clarificationAsked": (self.clarificationText if kinds else None),
                "decision": decision,
                "linkedRfiId": rfi_id,
                "photoUrl": self.photoUrl,
                "gps": self.gps,
                "allCriticalConfirmed": len(c.lowConfidence) == 0,
            })
            events.append(f"observation_logged:{obs_id}")
            self.state = "logged"
            return (
                r.done_reply(decision, obs_id, rfi_id,
                           (f"{c.drawing['drawing_number']} {c.drawing['revision']}"
                            if c.drawing else None)),
                {"observation_id": obs_id, "rfi_id": rfi_id, "decision": decision},
            )
        except SafetyGateError as e:
            events.append(f"safety_gate_refused:{str(e)}")
            self.state = "challenging"
            return (
                r.R(f"Safety check prevented the log: "
                    f"{str(e).replace('SAFETY GATE: ', '')}. Please confirm the details again."),
                None,
            )

    def slot_view(self) -> dict:
        o: dict = {}
        for k in SLOT_KEYS:
            s = self.slots.get(k)
            if s:
                o[k] = {"value": s["value"], "confidence": s["confidence"], "source": s["source"],
                        "confirmed": (k in self.confirmed) or s["source"] == "user_confirmed"}
        return o
