// Deterministic contradiction + blocker rules. Pure function of (slots, DB). Unit-tested.
import { LOW_CONFIDENCE, type Slot } from "../parser/extract";
import type { DrawingRow, FactRow, LocationRow, Repo } from "./repo";

export type ContradictionKind =
  | "revision_mismatch" | "dimension_mismatch" | "unknown_drawing" | "missing_critical_field"
  | "permit_blocker" | "hold_point_blocker";

export interface Evidence {
  drawing_id?: string; drawing_number?: string; revision?: string; issued_on?: string | null; via_rfi?: string | null;
  code_ref?: string | null; expected?: number | null; claimed?: number | string | null; tolerance?: number | null; unit?: string | null;
  claimed_revision?: string; claimed_revision_value?: number | null; permit_id?: string; checks?: string[];
  checklist?: string; template_id?: string | null; items?: string[]; field?: string; candidates?: string[];
}
export interface Contradiction { kind: ContradictionKind; severity: "flag" | "blocker" | "clarify"; detail: string; evidence: Evidence }

export interface Slots {
  grid?: Slot<string>; level?: Slot<string>; zone?: Slot<string>; element?: Slot<string>; attribute?: Slot<string>;
  value?: Slot<number>; unit?: Slot<string>; drawingNumber?: Slot<string>; revisionClaimed?: Slot<string>;
  drawingValueClaimed?: Slot<number>; activity?: Slot<string>; defect?: Slot<string>;
}
export type SlotName = keyof Slots;
export const CRITICAL_SLOTS: SlotName[] = ["grid", "level", "zone", "attribute", "value", "drawingNumber", "element", "activity"];

export type Mode = "measurement" | "activity" | "defect" | "unknown";

export interface CheckResult {
  mode: Mode;
  location?: LocationRow;
  locationInferred: boolean;
  locationCandidates: LocationRow[];
  fact?: FactRow;
  drawing?: DrawingRow; // verified latest drawing to link (never a superseded one)
  element?: string;
  attribute?: string;
  unit?: string;
  value?: number;
  contradictions: Contradiction[]; // flags (revision/dimension/unknown_drawing)
  blockers: Contradiction[]; // permit / hold point
  missing: Contradiction[]; // missing_critical_field
  lowConfidence: SlotName[];
}

function toUnit(v: number, from: string | undefined, to: string | null | undefined): number {
  if (!from || !to || from === to) return v;
  const mm: Record<string, number> = { mm: 1, cm: 10, m: 1000 };
  if (from in mm && to in mm) return (v * mm[from]) / mm[to];
  return v;
}

export function check(slots: Slots, repo: Repo, confirmed: Set<SlotName> = new Set()): CheckResult {
  const r: CheckResult = { mode: "unknown", locationInferred: false, locationCandidates: [], contradictions: [], blockers: [], missing: [], lowConfidence: [] };

  // ------------------------------------------------ low confidence (ASR-garbled or LLM-only)
  for (const k of CRITICAL_SLOTS) {
    const s = slots[k];
    if (!s || confirmed.has(k)) continue;
    if (s.confidence < LOW_CONFIDENCE || s.source === "llm") r.lowConfidence.push(k);
  }

  r.mode = slots.activity ? "activity" : slots.value || slots.attribute ? "measurement" : slots.defect ? "defect" : "unknown";

  // ------------------------------------------------ drawing (spoken)
  let spokenDrawing: string | null = null;
  if (slots.drawingNumber) {
    spokenDrawing = repo.resolveDrawingNumber(slots.drawingNumber.value);
    const latest = spokenDrawing ? repo.latestDrawing(spokenDrawing) : undefined;
    if (!spokenDrawing || !latest) {
      r.contradictions.push({
        kind: "unknown_drawing", severity: "clarify",
        detail: `Drawing ${slots.drawingNumber.value} not in the register${spokenDrawing ? " (no For Construction revision)" : ""}`,
        evidence: { drawing_number: slots.drawingNumber.value, candidates: repo.drawingNumbers() },
      });
      spokenDrawing = null;
    }
  }

  // ------------------------------------------------ location
  let level = slots.level?.value;
  let cands = repo.resolveLocation({ grid: slots.grid?.value, level, zone: slots.zone?.value, element: slots.element?.value });
  if (!level && cands.length > 1 && spokenDrawing) {
    const dl = repo.latestDrawing(spokenDrawing)?.level;
    if (dl) { const f = cands.filter((c) => c.level === dl); if (f.length) cands = f; }
  }
  r.locationCandidates = cands;
  if (cands.length === 1) {
    r.location = cands[0];
    r.locationInferred = !slots.level && !!cands[0].level;
    level = cands[0].level ?? undefined;
  }
  const hasLocWords = !!(slots.grid || slots.zone || (slots.element?.value === "slab" && slots.level));
  if (!r.location) {
    if (!hasLocWords) {
      r.missing.push({ kind: "missing_critical_field", severity: "clarify", detail: "location missing", evidence: { field: "location" } });
    } else if (cands.length > 1) {
      r.missing.push({ kind: "missing_critical_field", severity: "clarify", detail: "level ambiguous", evidence: { field: "level", candidates: cands.map((c) => c.location_id) } });
    } else {
      r.missing.push({
        kind: "missing_critical_field", severity: "clarify", detail: "location not in register",
        evidence: { field: "location_unknown", claimed: slots.grid?.value ?? slots.zone?.value ?? null, candidates: repo.locations().map((l) => l.grid ?? l.zone ?? l.location_id).filter(Boolean) as string[] },
      });
    }
  }

  // ------------------------------------------------ activity mode → blockers
  if (r.mode === "activity" && r.location) {
    const act = slots.activity!.value;
    if (act === "pour") {
      for (const hp of repo.holdPointBlockers(r.location.location_id)) {
        r.blockers.push({
          kind: "hold_point_blocker", severity: "blocker", detail: `Hold point not released on ${hp.ref}`,
          evidence: { checklist: hp.ref, template_id: hp.template_id, items: hp.items.map((i) => i.label), code_ref: hp.items[0]?.code_ref ?? null },
        });
      }
    } else {
      const pb = repo.permitBlockers(r.location.location_id, act);
      for (const b of pb.blocks) {
        r.blockers.push({ kind: "permit_blocker", severity: "blocker", detail: `Permit ${b.permit_id} has unsatisfied mandatory checks`, evidence: { permit_id: b.permit_id, checks: b.unsatisfied.map((u) => u.label) } });
      }
      if (pb.noPermit && !pb.blocks.length) {
        r.blockers.push({ kind: "permit_blocker", severity: "blocker", detail: `No active ${act} permit`, evidence: { permit_id: undefined, checks: [`No active ${act.replace("_", " ")} permit`] } });
      }
    }
    // link the latest drawing covering the location if any (informational)
    r.drawing = repo.latestDrawingForLocation(r.location.location_id, level);
    return r;
  }

  // ------------------------------------------------ measurement: attribute + value required
  if (r.mode === "measurement" || r.mode === "unknown") {
    if (!slots.attribute) r.missing.push({ kind: "missing_critical_field", severity: "clarify", detail: "attribute missing", evidence: { field: "attribute" } });
    if (!slots.value) r.missing.push({ kind: "missing_critical_field", severity: "clarify", detail: "value missing", evidence: { field: "value" } });
  }
  if (r.mode === "unknown" && !slots.attribute && !slots.value) {
    // nothing observable yet → the missing list already asks
  }

  // ------------------------------------------------ fact lookup (latest For Construction revision only)
  if (r.location && slots.attribute) {
    let attr = slots.attribute.value;
    let facts = repo.currentFacts(r.location.location_id, attr, slots.element?.value);
    if (!facts.length && slots.element) facts = repo.currentFacts(r.location.location_id, attr);
    if (!facts.length && attr === "stirrup_spacing") { attr = "rebar_spacing"; facts = repo.currentFacts(r.location.location_id, attr); }
    if (spokenDrawing && facts.length > 1) facts = facts.filter((f) => f.drawing_number === spokenDrawing).concat(facts.filter((f) => f.drawing_number !== spokenDrawing));
    r.attribute = attr;
    const elements = [...new Set(facts.map((f) => f.element))];
    if (!slots.element && elements.length > 1) {
      r.missing.push({ kind: "missing_critical_field", severity: "clarify", detail: "element ambiguous", evidence: { field: "element", candidates: elements } });
      facts = [];
    }
    if (facts.length) {
      const f = facts[0];
      r.fact = f;
      r.element = f.element;
      r.unit = f.unit ?? undefined;
      r.drawing = repo.drawingById(f.drawing_id);
    } else {
      r.element = slots.element?.value;
      r.drawing = spokenDrawing ? repo.latestDrawing(spokenDrawing) : repo.latestDrawingForLocation(r.location.location_id, level);
    }
  } else if (r.location) {
    r.element = slots.element?.value;
    r.drawing = spokenDrawing ? repo.latestDrawing(spokenDrawing) : repo.latestDrawingForLocation(r.location.location_id, level);
  }
  if (!r.unit) r.unit = slots.unit?.value ?? (slots.attribute && ["rebar_spacing", "stirrup_spacing", "cover", "thickness", "rebar_dia", "size"].includes(slots.attribute.value) ? "mm" : undefined);
  if (slots.value) r.value = toUnit(slots.value.value, slots.unit?.value, r.unit);

  const f = r.fact;
  const d = r.drawing;
  // spoken drawing that doesn't govern this location/attribute
  if (f && spokenDrawing && spokenDrawing !== f.drawing_number) {
    r.contradictions.push({
      kind: "unknown_drawing", severity: "clarify", detail: `${spokenDrawing} does not govern this element; ${f.drawing_number} ${f.revision} does`,
      evidence: { drawing_number: slots.drawingNumber?.value, drawing_id: f.drawing_id, revision: f.revision, issued_on: f.issued_on, candidates: [f.drawing_number] },
    });
  }

  // ------------------------------------------------ revision_mismatch
  if (d && slots.revisionClaimed && slots.revisionClaimed.value !== d.revision) {
    const old = f ? repo.factOnRevision(d.drawing_number, slots.revisionClaimed.value, f.location_id!, f.attribute) : undefined;
    r.contradictions.push({
      kind: "revision_mismatch", severity: "flag",
      detail: `Claimed ${d.drawing_number} ${slots.revisionClaimed.value}; latest For Construction is ${d.revision}`,
      evidence: {
        drawing_id: d.drawing_id, drawing_number: d.drawing_number, revision: d.revision, issued_on: d.issued_on,
        via_rfi: f?.via_rfi ?? repo.rfiForDrawing(d.drawing_id)?.rfi_id ?? null, code_ref: f?.code_ref ?? null,
        expected: f?.value_num ?? null, unit: f?.unit ?? null, claimed_revision: slots.revisionClaimed.value,
        claimed_revision_value: old?.value_num ?? slots.drawingValueClaimed?.value ?? null,
      },
    });
  } else if (f && slots.drawingValueClaimed && f.value_num != null && Math.abs(toUnit(slots.drawingValueClaimed.value, slots.unit?.value, f.unit) - f.value_num) > (f.tolerance ?? 0)) {
    // "drawing mein 200 likha hai" with no revision → find which old revision says that
    const older = repo.factsAnyRevision(f.drawing_number, f.location_id!, f.attribute).find((o) => o.value_num === slots.drawingValueClaimed!.value && o.revision !== f.revision);
    r.contradictions.push({
      kind: older ? "revision_mismatch" : "dimension_mismatch", severity: "flag",
      detail: older ? `Value ${slots.drawingValueClaimed.value} is from superseded ${older.revision}` : `Drawing value claimed ${slots.drawingValueClaimed.value} ≠ latest ${f.value_num}`,
      evidence: {
        drawing_id: f.drawing_id, drawing_number: f.drawing_number, revision: f.revision, issued_on: f.issued_on, via_rfi: f.via_rfi ?? null,
        code_ref: f.code_ref, expected: f.value_num, unit: f.unit, tolerance: f.tolerance, claimed: slots.drawingValueClaimed.value,
        claimed_revision: older?.revision, claimed_revision_value: older?.value_num ?? null,
      },
    });
  }

  // ------------------------------------------------ dimension_mismatch (observed vs latest fact)
  if (f && r.value != null && f.value_num != null) {
    const diff = Math.abs(r.value - f.value_num);
    const tol = f.tolerance ?? 0;
    if (diff > tol) {
      r.contradictions.push({
        kind: "dimension_mismatch", severity: "flag", detail: `Observed ${r.value} ${f.unit} vs ${f.value_num} ±${tol}`,
        evidence: { drawing_id: f.drawing_id, drawing_number: f.drawing_number, revision: f.revision, issued_on: f.issued_on, via_rfi: f.via_rfi ?? null, code_ref: f.code_ref, expected: f.value_num, claimed: r.value, tolerance: tol, unit: f.unit },
      });
    }
  }

  // de-duplicate kinds (keep first of each kind)
  const seen = new Set<string>();
  r.contradictions = r.contradictions.filter((c) => (seen.has(c.kind) ? false : (seen.add(c.kind), true)));
  return r;
}
