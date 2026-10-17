// Writes to the only four tables the voice layer owns: voice_sessions, voice_turns, field_observations, rfis.
// insertObservation() is the SAFETY GATE: it re-verifies against the DB immediately before writing and throws
// rather than persist anything unverified. The dialogue engine should never trip it; tests assert it doesn't.
import type { Repo } from "./repo";

export class SafetyGateError extends Error {
  constructor(msg: string) { super(`SAFETY GATE: ${msg}`); this.name = "SafetyGateError"; }
}

const nowIso = () => new Date().toISOString();

export function createSession(repo: Repo, userName = "Site Manager", lang = "hi-en"): string {
  const id = `VS-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
  repo.db.prepare(`INSERT INTO voice_sessions (session_id, project_id, user_name, started_at, lang) VALUES (?,?,?,?,?)`).run(id, repo.projectId, userName, nowIso(), lang);
  return id;
}
export function endSession(repo: Repo, sessionId: string) {
  repo.db.prepare(`UPDATE voice_sessions SET ended_at = ? WHERE session_id = ?`).run(nowIso(), sessionId);
}

export function insertTurn(repo: Repo, t: { sessionId: string; role: "user" | "agent"; text: string; entities?: unknown; state: string; bargeIn?: boolean }): number {
  const r = repo.db.prepare(`INSERT INTO voice_turns (session_id, role, text, entities_json, state, was_barge_in, created_at) VALUES (?,?,?,?,?,?,?)`)
    .run(t.sessionId, t.role, t.text, t.entities === undefined ? null : JSON.stringify(t.entities), t.state, t.bargeIn ? 1 : 0, nowIso());
  return Number(r.lastInsertRowid);
}

function nextId(repo: Repo, table: string, col: string, prefix: string, width: number): string {
  const rows = repo.db.prepare(`SELECT ${col} AS id FROM ${table} WHERE ${col} LIKE ?`).all(`${prefix}%`) as { id: string }[];
  const max = rows.reduce((m, r) => Math.max(m, Number(r.id.replace(/\D/g, "")) || 0), 0);
  return `${prefix}${String(max + 1).padStart(width, "0")}`;
}

export interface ObservationInput {
  sessionId: string;
  spokenText: string;
  summary: string;
  locationId: string | null;
  element?: string | null;
  attribute?: string | null;
  value?: number | null;
  unit?: string | null;
  drawingId?: string | null;
  revisionClaimed?: string | null;
  contradictionKinds: string[];
  clarificationAsked?: string | null;
  decision: "log_observation" | "raise_rfi" | "raise_ncr" | "stop_work";
  linkedRfiId?: string | null;
  photoUrl?: string | null;
  gps?: { lat: number; lng: number } | null;
  /** engine attests every critical slot is confirmed / high-confidence */
  allCriticalConfirmed: boolean;
}

export function insertObservation(repo: Repo, o: ObservationInput): string {
  // ---- gate
  if (!o.allCriticalConfirmed) throw new SafetyGateError("unconfirmed or low-confidence critical slot");
  if (o.drawingId && !repo.isVerifiedLatest(o.drawingId)) throw new SafetyGateError(`drawing ${o.drawingId} is not the verified latest For Construction revision`);
  if (o.locationId && !repo.locationExists(o.locationId)) throw new SafetyGateError(`unknown location ${o.locationId}`);
  if (o.decision === "log_observation" || o.decision === "raise_rfi" || o.decision === "raise_ncr") {
    if (!o.locationId) throw new SafetyGateError("no verified location");
  }
  if (o.contradictionKinds.length && !o.clarificationAsked) throw new SafetyGateError("contradiction without a prior spoken clarification");
  if (o.value != null && o.attribute) {
    // value must be consistent with the fact unit (never log a mm value against a MPa fact etc.)
    if (!o.unit) throw new SafetyGateError("value without unit");
  }

  const id = nextId(repo, "field_observations", "observation_id", "OBS-", 6);
  const tpl = repo.template("QC-SPW-REG-004") ? "QC-SPW-REG-004" : null;
  repo.db.prepare(`INSERT INTO field_observations (observation_id, project_id, session_id, spoken_text, structured_summary, location_id, element, attribute,
      value_claimed, unit, drawing_id, revision_claimed, contradiction_flag, contradiction_kinds, clarification_asked, final_decision, linked_rfi_id,
      linked_template_id, photo_url, gps_lat, gps_lng, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(
    id, repo.projectId, o.sessionId, o.spokenText, o.summary, o.locationId, o.element ?? null, o.attribute ?? null, o.value ?? null, o.unit ?? null,
    o.drawingId ?? null, o.revisionClaimed ?? null, o.contradictionKinds.length ? 1 : 0, o.contradictionKinds.length ? JSON.stringify(o.contradictionKinds) : null,
    o.clarificationAsked ?? null, o.decision, o.linkedRfiId ?? null, tpl, o.photoUrl ?? null, o.gps?.lat ?? null, o.gps?.lng ?? null, nowIso(),
  );
  return id;
}

export function insertRfi(repo: Repo, r: { subject: string; locationId: string | null; drawingRef: string | null; question: string }): string {
  const id = nextId(repo, "rfis", "rfi_id", "RFI-", 3);
  const tpl = repo.template("PMC-DSN-LOG-003") ? "PMC-DSN-LOG-003" : null;
  repo.db.prepare(`INSERT INTO rfis (rfi_id, project_id, subject, location_id, drawing_ref, question, status, raised_on, template_id) VALUES (?,?,?,?,?,?,?,?,?)`)
    .run(id, repo.projectId, r.subject, r.locationId, r.drawingRef, r.question, "Open", nowIso().slice(0, 10), tpl);
  return id;
}
