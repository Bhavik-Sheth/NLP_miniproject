// Acceptance-scenario runner shared by `npm run test:scenarios` (CLI) and the in-app Scenarios tab (API).
// Always runs against a temp COPY of the DB, never the live one.
import Database from "better-sqlite3";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { DialogueSession, type AgentTurn, type Noise } from "./engine/dialogue";
import { createSession } from "./engine/persist";
import { Repo } from "./engine/repo";

export interface ScenarioTurn { user: string; barge_in?: boolean; noise?: Noise | string }
export interface Scenario {
  id: string;
  title: string;
  turns: ScenarioTurn[];
  expect: {
    contradiction?: boolean;
    kinds?: string[];
    must_ask_clarification?: boolean;
    final_decision?: string;
    no_log?: boolean;
    logged?: { drawing_id?: string | null; location_id?: string | null; attribute?: string | null; value?: number | null; unit?: string | null };
  };
  [k: string]: unknown;
}
export interface TranscriptItem { role: "user" | "agent"; text: string; bargeIn?: boolean; noise?: string; turn?: AgentTurn }
export interface ScenarioResult {
  id: string; title: string; pass: boolean; failures: string[];
  kindsSeen: string[]; clarified: boolean; finalDecision: string; logged: Record<string, unknown>[];
  transcript: TranscriptItem[];
}

export function loadScenarios(appDir: string): { file: string; scenarios: Scenario[] } {
  const candidates = [process.env.SCENARIOS_PATH, path.resolve(appDir, "../data/seed/scenarios.json"), path.resolve(appDir, "dev-fixture/scenarios.json")].filter(Boolean) as string[];
  for (const f of candidates) {
    if (fs.existsSync(f)) {
      const raw = JSON.parse(fs.readFileSync(f, "utf8"));
      const scenarios: Scenario[] = Array.isArray(raw) ? raw : raw.scenarios;
      return { file: f, scenarios };
    }
  }
  return { file: "", scenarios: [] };
}

export function tempDbCopy(src: string): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "vesper-scn-"));
  const dst = path.join(dir, "site.db");
  // use SQLite backup semantics via VACUUM INTO so WAL content is included
  const s = new Database(src, { readonly: true });
  s.exec(`VACUUM INTO '${dst.replace(/'/g, "''")}'`);
  s.close();
  return dst;
}

const normDecision = (d?: string | null) => (d === "cancel" ? "cancelled" : d ?? "none");

export async function runScenario(repo: Repo, sc: Scenario): Promise<ScenarioResult> {
  const sessionId = createSession(repo, `scenario ${sc.id}`);
  const session = new DialogueSession(repo, sessionId, undefined, true);
  const transcript: TranscriptItem[] = [];
  const failures: string[] = [];
  const kindsSeen = new Set<string>();
  const clarifiedKinds = new Set<string>();
  let clarified = false;
  let finalDecision = "none";

  for (const t of sc.turns) {
    transcript.push({ role: "user", text: t.user, bargeIn: !!t.barge_in, noise: t.noise });
    const turn = await session.handle({ text: t.user, bargeIn: !!t.barge_in, noise: (["none", "low", "medium", "high"].includes(String(t.noise)) ? t.noise : "none") as Noise });
    transcript.push({ role: "agent", text: turn.reply, turn });
    for (const k of [...turn.contradictions, ...turn.blockers]) kindsSeen.add(k.kind);
    for (const k of turn.missing) kindsSeen.add(k.kind);
    // a clarification = agent spoke about the contradiction/blocker/missing field before any write
    if (!turn.logged && (turn.clarifiedKinds.length || turn.state === "challenging" || turn.state === "blocked" || turn.state === "confirming" && turn.lowConfidence.length)) {
      clarified = true;
      turn.clarifiedKinds.forEach((k) => clarifiedKinds.add(k));
    }
    if (turn.logged) {
      finalDecision = normDecision(turn.logged.decision);
      // invariant: every flag on the logged row was clarified in an EARLIER agent turn
      for (const k of [...turn.contradictions, ...turn.blockers].map((x) => x.kind)) {
        if (!clarifiedKinds.has(k)) failures.push(`logged with ${k} that was never clarified first`);
      }
    }
  }

  const rows = repo.db.prepare(`SELECT * FROM field_observations WHERE session_id = ? ORDER BY created_at`).all(sessionId) as Record<string, unknown>[];
  // ---- global safety invariants
  for (const r of rows) {
    if (r.drawing_id && !repo.isVerifiedLatest(String(r.drawing_id))) failures.push(`logged non-latest drawing ${r.drawing_id}`);
    if (r.location_id && !repo.locationExists(String(r.location_id))) failures.push(`logged unknown location ${r.location_id}`);
    if (Number(r.contradiction_flag) === 1 && !r.clarification_asked) failures.push(`${r.observation_id} flagged but no clarification_asked`);
  }
  const e = sc.expect ?? {};
  const kinds = [...kindsSeen];
  const flagKinds = kinds.filter((k) => k !== "missing_critical_field");
  if (e.contradiction === true && !kinds.length) failures.push("expected a contradiction, none detected");
  if (e.contradiction === false && flagKinds.length) failures.push(`unexpected contradictions: ${flagKinds.join(",")}`);
  for (const k of e.kinds ?? []) if (!kindsSeen.has(k)) failures.push(`missing kind ${k} (saw ${kinds.join(",") || "none"})`);
  if (e.must_ask_clarification && !clarified) failures.push("no clarification was asked");
  if (e.no_log && rows.length) failures.push(`no_log expected but ${rows.length} row(s) written`);
  if (e.final_decision) {
    const want = normDecision(e.final_decision);
    const got = rows.length ? String(rows[rows.length - 1].final_decision) : finalDecision;
    if (want !== got) failures.push(`final_decision ${got} ≠ expected ${want}`);
  }
  if (e.logged && !e.no_log) {
    const r = rows[rows.length - 1];
    if (!r) failures.push("expected a logged row, none written");
    else {
      const map: Record<string, string> = { drawing_id: "drawing_id", location_id: "location_id", attribute: "attribute", value: "value_claimed", unit: "unit" };
      for (const [k, col] of Object.entries(map)) {
        const want = (e.logged as Record<string, unknown>)[k];
        if (want === undefined) continue;
        const got = r[col];
        const eq = typeof want === "number" ? Math.abs(Number(got) - want) < 1e-6 : want === got;
        if (!eq) failures.push(`logged ${k}=${got} ≠ expected ${want}`);
      }
    }
  }
  return { id: sc.id, title: sc.title, pass: failures.length === 0, failures, kindsSeen: kinds, clarified, finalDecision: rows.length ? String(rows[rows.length - 1].final_decision) : finalDecision, logged: rows, transcript };
}

export async function runAll(dbPath: string, scenarios: Scenario[]): Promise<ScenarioResult[]> {
  const copy = tempDbCopy(dbPath);
  const db = new Database(copy);
  db.pragma("foreign_keys = ON");
  const repo = new Repo(db, "P1");
  const out: ScenarioResult[] = [];
  try {
    for (const sc of scenarios) out.push(await runScenario(repo, sc));
  } finally {
    db.close();
    fs.rmSync(path.dirname(copy), { recursive: true, force: true });
  }
  return out;
}
