// Dialogue state machine: capturing → checking → challenging → confirming → logged | blocked | cancelled.
// Safety invariants (enforced here AND re-checked in persist.insertObservation):
//  1. Never log with a drawing_id that is not the verified latest For Construction revision.
//  2. Never log a value/location that is unconfirmed or low-confidence (incl. anything only the LLM suggested).
//  3. Every contradiction is spoken as a clarification in an EARLIER agent turn before any write.
//  4. Blockers (permit / hold point) → only stop_work / raise_ncr / cancel.
import { chips, extract, type Decision, type Extraction, type Slot } from "../parser/extract";
import { check, type CheckResult, type Contradiction, type SlotName, type Slots } from "./contradictions";
import type { LlmAssist } from "./llm";
import { insertObservation, insertRfi, insertTurn, SafetyGateError } from "./persist";
import {
  attrLabel, blockerReply, challengeReply, confirmSlotsReply, doneReply, locLabel, missingReply, readbackReply, REFUSE, reply,
  unknownDrawingReply, type Reply,
} from "./replies";
import type { Repo } from "./repo";

export type DState = "capturing" | "checking" | "challenging" | "confirming" | "logged" | "blocked" | "cancelled";
export type Noise = "none" | "low" | "medium" | "high";

export interface TurnInput {
  text: string;
  bargeIn?: boolean;
  noise?: Noise;
  decision?: Decision; // from a UI button
  photoUrl?: string | null;
  gps?: { lat: number; lng: number } | null;
}

export interface SlotView { value: string | number; confidence: number; source: string; confirmed: boolean }
export interface AgentTurn {
  sessionId: string;
  reply: string;
  speech: string;
  state: DState;
  contradictions: Contradiction[];
  blockers: Contradiction[];
  missing: Contradiction[];
  lowConfidence: SlotName[];
  allowedDecisions: Decision[];
  slots: Record<string, SlotView>;
  chips: ReturnType<typeof chips>;
  clarifiedKinds: string[]; // contradiction kinds this reply spoke (for the acceptance runner)
  resolved: {
    location_id?: string; drawing_id?: string; drawing_label?: string; location_inferred?: boolean;
    fact?: { value: number | null; unit: string | null; tolerance: number | null; revision: string; issued_on: string | null; via_rfi?: string | null; code_ref?: string | null };
  };
  logged?: { observation_id?: string; rfi_id?: string; decision: Decision | "cancelled" };
  events: string[];
  userTurnId?: number;
  agentTurnId?: number;
}

const SLOT_KEYS: SlotName[] = ["grid", "level", "zone", "element", "attribute", "value", "unit", "drawingNumber", "revisionClaimed", "drawingValueClaimed", "activity", "defect"] as SlotName[];
const NOISE_FACTOR: Record<Noise, number> = { none: 1, low: 0.95, medium: 0.8, high: 0.65 };
const DECISION_LABEL: Record<Decision, string> = {
  log_observation: "Observation log karna", raise_rfi: "RFI raise karna", raise_ncr: "NCR", stop_work: "Kaam rokna", cancel: "Cancel",
};

export class DialogueSession {
  state: DState = "capturing";
  slots: Slots = {};
  confirmed = new Set<SlotName>();
  pendingConfirm: SlotName[] = [];
  spokenSig: string | null = null; // signature of the last challenge / readback / blocker the agent SPOKE
  spokenKinds: string[] = [];
  clarificationText: string | null = null;
  lastOffer: "log" | "log_or_rfi" | "blocker" | null = null;
  utterances: string[] = [];
  photoUrl: string | null = null;
  gps: { lat: number; lng: number } | null = null;
  lastCheck?: CheckResult;

  constructor(public repo: Repo, public sessionId: string, private llm?: LlmAssist, public persistTurns = true) {}

  private resetObservation() {
    this.state = "capturing"; this.slots = {}; this.confirmed = new Set(); this.pendingConfirm = [];
    this.spokenSig = null; this.spokenKinds = []; this.clarificationText = null; this.lastOffer = null; this.utterances = [];
    this.photoUrl = null; this.gps = null; this.lastCheck = undefined;
  }

  async handle(input: TurnInput): Promise<AgentTurn> {
    if (this.state === "logged" || this.state === "cancelled") this.resetObservation();
    const events: string[] = [];
    if (input.bargeIn) events.push("barge_in");
    if (input.photoUrl) this.photoUrl = input.photoUrl;
    if (input.gps) this.gps = input.gps;
    const text = (input.text ?? "").trim();
    const prevState = this.state;
    if (text) this.utterances.push(text);

    // ---------------------------------------------------------------- extract (+ optional LLM suggestions)
    const ex: Extraction = extract(text);
    const f = NOISE_FACTOR[input.noise ?? "none"];
    if (f !== 1) for (const k of SLOT_KEYS) { const s = (ex as unknown as Record<string, Slot<unknown> | undefined>)[k]; if (s) s.confidence = +(s.confidence * f).toFixed(2); }
    if (this.llm && text.split(/\s+/).length >= 4) {
      const sug = await this.llm(text, ex);
      for (const [k, v] of Object.entries(sug)) {
        if (v && !(ex as unknown as Record<string, unknown>)[k] && !(this.slots as Record<string, unknown>)[k]) {
          (ex as unknown as Record<string, unknown>)[k] = v; events.push(`llm_suggested:${k}`);
        }
      }
    }

    // ---------------------------------------------------------------- merge (later speech overwrites → corrections)
    const changed: SlotName[] = [];
    for (const k of SLOT_KEYS) {
      const s = (ex as unknown as Record<string, Slot<string | number> | undefined>)[k];
      if (!s) continue;
      const cur = (this.slots as Record<string, Slot<string | number> | undefined>)[k];
      if (!cur || cur.value !== s.value) {
        if (cur) events.push(`correction:${k} ${cur.value}→${s.value}`);
        changed.push(k); this.confirmed.delete(k);
        (this.slots as Record<string, Slot<string | number>>)[k] = s;
      } else if (s.confidence > cur.confidence) {
        (this.slots as Record<string, Slot<string | number>>)[k] = s;
      }
    }
    if (this.slots.grid && ex.negatedGrids.includes(this.slots.grid.value) && !ex.grid) {
      events.push(`correction:grid ${this.slots.grid.value}→(cleared)`); delete this.slots.grid; changed.push("grid");
    }
    if (this.slots.value && ex.negatedValues.includes(this.slots.value.value) && !ex.value) {
      events.push(`correction:value ${this.slots.value.value}→(cleared)`); delete this.slots.value; changed.push("value");
    }
    // corrections to the observed value are the user's words → keep but they will be re-read back

    // ---------------------------------------------------------------- voice confirmation of pending low-confidence slots
    const hadPending = this.pendingConfirm.length > 0;
    if (hadPending) {
      const pendingChanged = this.pendingConfirm.some((p) => changed.includes(p));
      if (ex.affirm && !pendingChanged) {
        for (const p of this.pendingConfirm) {
          this.confirmed.add(p);
          const s = (this.slots as Record<string, Slot<unknown> | undefined>)[p];
          if (s) { s.confidence = 1; s.source = "user_confirmed"; }
        }
        events.push(`confirmed:${this.pendingConfirm.join(",")}`);
        this.pendingConfirm = [];
      } else if (ex.deny && !changed.length) {
        for (const p of this.pendingConfirm) delete (this.slots as Record<string, unknown>)[p];
        events.push(`rejected:${this.pendingConfirm.join(",")}`);
        this.pendingConfirm = [];
      }
    }

    // ---------------------------------------------------------------- decision
    let decision: Decision | undefined = input.decision ?? ex.decision;
    let ambiguousYes = false;
    if (!decision && ex.affirm && !hadPending && !changed.length) {
      if (this.lastOffer === "log") decision = "log_observation";
      else if (this.lastOffer === "log_or_rfi") ambiguousYes = true;
    }
    if (decision) events.push(`decision:${decision}`);

    const userTurnId = this.persistTurns ? insertTurn(this.repo, {
      sessionId: this.sessionId, role: "user", text: text || (decision ? `[button] ${decision}` : ""),
      entities: { extracted: chips(ex), normalized: ex.normalized, noise: input.noise ?? "none" }, state: prevState, bargeIn: input.bargeIn,
    }) : undefined;

    // ---------------------------------------------------------------- check
    this.state = "checking";
    const c = check(this.slots, this.repo, this.confirmed);
    this.lastCheck = c;
    const clarifyDrawing = c.contradictions.find((k) => k.kind === "unknown_drawing" && !k.evidence.drawing_id);
    const flags = c.contradictions.filter((k) => k !== clarifyDrawing);
    const sig = JSON.stringify({
      loc: c.location?.location_id, attr: c.attribute, v: c.value, u: c.unit, d: c.drawing?.drawing_id, act: this.slots.activity?.value,
      rev: this.slots.revisionClaimed?.value, dv: this.slots.drawingValueClaimed?.value, defect: this.slots.defect?.value,
      kinds: [...flags, ...c.blockers].map((k) => k.kind).sort(),
    });
    const alreadySpoken = this.spokenSig === sig;

    let out: Reply;
    let allowed: Decision[] = ["cancel"];
    let clarifiedKinds: string[] = [];
    let logged: AgentTurn["logged"];

    const speak = (r: Reply, kinds: string[], offer: DialogueSession["lastOffer"]) => {
      out = r; this.spokenSig = sig; this.spokenKinds = kinds; clarifiedKinds = kinds; this.lastOffer = offer;
      if (kinds.length) this.clarificationText = r.text;
    };

    if (decision === "cancel") {
      this.state = "cancelled"; out = doneReply("cancel"); logged = { decision: "cancelled" };
    } else if (!text && !decision) {
      out = reply(REFUSE.nothing); this.state = prevState === "checking" ? "capturing" : prevState;
    } else if (c.blockers.length) {
      // ---------------- BLOCKED: only stop_work / raise_ncr / cancel
      allowed = ["stop_work", "raise_ncr", "cancel"];
      if ((decision === "stop_work" || decision === "raise_ncr") && alreadySpoken) {
        ({ out, logged } = this.execute(decision, c, c.blockers.map((b) => b.kind), events));
      } else {
        this.state = "blocked";
        speak(blockerReply(c, this.slots, decision && decision !== "stop_work" && decision !== "raise_ncr" ? DECISION_LABEL[decision] : undefined), c.blockers.map((b) => b.kind), "blocker");
        if (decision === "stop_work" || decision === "raise_ncr") events.push("decision_deferred_until_blocker_spoken");
      }
    } else if (clarifyDrawing) {
      this.state = "challenging";
      speak(unknownDrawingReply(clarifyDrawing), ["unknown_drawing"], null);
      if (decision) events.push("decision_refused:unknown_drawing");
    } else if (c.missing.length) {
      this.state = "capturing";
      out = missingReply(c, this.slots);
      if (decision) { out = reply(`Log karne ke liye detail chahiye. ${out.text}`); events.push("decision_refused:missing_field"); }
      clarifiedKinds = ["missing_critical_field"];
    } else if (c.lowConfidence.length) {
      this.state = "confirming";
      this.pendingConfirm = c.lowConfidence;
      out = confirmSlotsReply(c.lowConfidence, this.slots, c.drawing?.drawing_number);
      if (decision) { out = reply(`${REFUSE.confirmFirst} ${out.text}`); events.push("decision_refused:low_confidence"); }
      this.lastOffer = null;
    } else if (flags.length) {
      // ---------------- contradictions: must be spoken before any decision is executed
      allowed = ["log_observation", "raise_rfi", "raise_ncr", "cancel"];
      if (decision && alreadySpoken) {
        ({ out, logged } = this.execute(decision, c, flags.map((k) => k.kind), events));
      } else if (ambiguousYes && alreadySpoken) {
        this.state = "challenging"; out = reply(REFUSE.ambiguousYes);
      } else if (ex.rfiDeclined && alreadySpoken && !decision) {
        this.state = "confirming"; out = reply(REFUSE.rfiDeclined); this.lastOffer = "log";
      } else {
        this.state = "challenging";
        speak(challengeReply(c, this.slots, decision ? REFUSE.clarifyFirst : ""), flags.map((k) => k.kind), "log_or_rfi");
        if (decision) events.push("decision_deferred_until_clarified");
      }
    } else {
      // ---------------- clean: read back, or execute an explicit decision if nothing is inferred
      allowed = ["log_observation", "raise_rfi", "raise_ncr", "cancel"];
      const explicitOk = decision && (alreadySpoken || !c.locationInferred);
      if (decision && explicitOk) {
        ({ out, logged } = this.execute(decision, c, [], events));
      } else if (ex.rfiDeclined && !decision) {
        this.state = "confirming"; speak(readbackReply(c, this.slots, "Theek hai, RFI nahi."), [], "log");
      } else {
        this.state = "confirming";
        speak(readbackReply(c, this.slots), [], "log");
      }
    }

    const reply_ = out!;
    const turn: AgentTurn = {
      sessionId: this.sessionId, reply: reply_.text, speech: reply_.speech, state: this.state,
      contradictions: flags.concat(clarifyDrawing ? [clarifyDrawing] : []), blockers: c.blockers, missing: c.missing, lowConfidence: c.lowConfidence,
      allowedDecisions: this.state === "logged" || this.state === "cancelled" ? [] : allowed,
      slots: this.slotView(), chips: chips(ex), clarifiedKinds, events, userTurnId, logged,
      resolved: {
        location_id: c.location?.location_id, drawing_id: c.drawing?.drawing_id, location_inferred: c.locationInferred,
        drawing_label: c.drawing ? `${c.drawing.drawing_number} ${c.drawing.revision}` : undefined,
        fact: c.fact ? { value: c.fact.value_num, unit: c.fact.unit, tolerance: c.fact.tolerance, revision: c.fact.revision, issued_on: c.fact.issued_on, via_rfi: c.fact.via_rfi, code_ref: c.fact.code_ref } : undefined,
      },
    };
    if (this.persistTurns) {
      turn.agentTurnId = insertTurn(this.repo, {
        sessionId: this.sessionId, role: "agent", text: reply_.text, state: this.state,
        entities: { slots: turn.slots, resolved: turn.resolved, contradictions: turn.contradictions.map((k) => k.kind), blockers: c.blockers.map((k) => k.kind), events },
      });
    }
    return turn;
  }

  private execute(decision: Decision, c: CheckResult, kinds: string[], events: string[]): { out: Reply; logged: AgentTurn["logged"] } {
    if (decision === "cancel") { this.state = "cancelled"; return { out: doneReply("cancel"), logged: { decision: "cancelled" } }; }
    const loc = locLabel(c, this.slots);
    const attr = attrLabel(c.attribute);
    const drawingId = c.drawing && this.repo.isVerifiedLatest(c.drawing.drawing_id) ? c.drawing.drawing_id : null;
    const summaryParts = [
      c.location?.location_id ?? loc,
      c.mode === "activity" ? `activity ${this.slots.activity?.value}` : c.mode === "defect" ? `${this.slots.element?.value ?? ""} ${this.slots.defect?.value}`.trim() : `${c.element ?? ""} ${c.attribute ?? ""} = ${c.value ?? "?"} ${c.unit ?? ""}`.trim(),
      drawingId ? `linked ${drawingId}${c.fact ? ` (latest ${c.fact.value_num}${c.fact.unit ?? ""}${c.fact.tolerance != null ? ` ±${c.fact.tolerance}` : ""})` : ""}` : "no drawing link",
      kinds.length ? `flags: ${kinds.join(", ")}` : "no contradictions",
    ];
    try {
      let rfiId: string | undefined;
      if (decision === "raise_rfi") {
        rfiId = insertRfi(this.repo, {
          subject: `${loc} ${attr || this.slots.activity?.value || "site"} clarification`,
          locationId: c.location?.location_id ?? null,
          drawingRef: c.drawing?.drawing_number ?? this.slots.drawingNumber?.value ?? null,
          question: `Site observed ${attr} ${c.value ?? ""} ${c.unit ?? ""} at ${loc}.` +
            (c.fact ? ` Latest ${c.fact.drawing_number} ${c.fact.revision} shows ${c.fact.value_num} ${c.fact.unit ?? ""}.` : "") +
            (kinds.length ? ` Flags: ${kinds.join(", ")}.` : "") + " Please confirm.",
        });
        events.push(`rfi_raised:${rfiId}`);
      }
      const obsId = insertObservation(this.repo, {
        sessionId: this.sessionId,
        spokenText: this.utterances.join(" | "),
        summary: summaryParts.join(" · "),
        locationId: c.location?.location_id ?? null,
        element: c.element ?? this.slots.element?.value ?? null,
        attribute: c.mode === "measurement" ? c.attribute ?? null : c.mode === "defect" ? `defect:${this.slots.defect?.value}` : c.mode === "activity" ? `activity:${this.slots.activity?.value}` : null,
        value: c.mode === "measurement" ? c.value ?? null : null,
        unit: c.mode === "measurement" ? c.unit ?? null : null,
        drawingId,
        revisionClaimed: this.slots.revisionClaimed?.value ?? null,
        contradictionKinds: kinds,
        clarificationAsked: kinds.length ? this.clarificationText : null,
        decision,
        linkedRfiId: rfiId ?? null,
        photoUrl: this.photoUrl, gps: this.gps,
        allCriticalConfirmed: c.lowConfidence.length === 0,
      });
      events.push(`observation_logged:${obsId}`);
      this.state = "logged";
      return { out: doneReply(decision, obsId, rfiId, c.drawing ? `${c.drawing.drawing_number} ${c.drawing.revision}` : undefined), logged: { observation_id: obsId, rfi_id: rfiId, decision } };
    } catch (e) {
      if (e instanceof SafetyGateError) {
        events.push(`safety_gate_refused:${e.message}`);
        this.state = "challenging";
        return { out: reply(`Safety check ne log rok diya: ${e.message.replace("SAFETY GATE: ", "")}. Kripya details dobara confirm kijiye.`), logged: undefined };
      }
      throw e;
    }
  }

  slotView(): Record<string, SlotView> {
    const o: Record<string, SlotView> = {};
    for (const k of SLOT_KEYS) {
      const s = (this.slots as Record<string, Slot<string | number> | undefined>)[k];
      if (s) o[k] = { value: s.value, confidence: s.confidence, source: s.source, confirmed: this.confirmed.has(k) || s.source === "user_confirmed" };
    }
    return o;
  }
}
