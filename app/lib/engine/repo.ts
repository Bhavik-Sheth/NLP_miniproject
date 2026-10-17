// Read-side access to site.db (plus the four tables the voice layer may write).
// Every query here is defensive: optional tables (checklists) are introspected before use.
import type Database from "better-sqlite3";

export type DB = Database.Database;

export interface LocationRow { location_id: string; project_id: string; grid: string | null; level: string | null; zone: string | null; aliases: string | null }
export interface DrawingRow {
  drawing_id: string; project_id: string; drawing_number: string; revision: string; rev_ordinal: number; title: string | null;
  discipline: string | null; status: string; issued_on: string | null; zone: string | null; level: string | null; is_latest: number;
  superseded_by: string | null; change_note: string | null;
}
export interface FactRow {
  fact_id: number; drawing_id: string; location_id: string | null; element: string; element_mark: string | null; attribute: string;
  value_num: number | null; value_text: string | null; unit: string | null; tolerance: number | null; code_ref: string | null;
  drawing_number: string; revision: string; issued_on: string | null; via_rfi?: string | null;
}
export interface PermitBlock {
  permit_id: string; permit_type: string; location_id: string | null; status: string;
  unsatisfied: { label: string; field_id: number }[];
}
export interface HoldPointBlock { source: string; ref: string; template_id: string | null; location_id: string | null; notes?: string | null; items: { label: string; code_ref?: string | null }[] }

const norm = (s: string | null | undefined) => (s ?? "").toLowerCase().replace(/[\s\-_/]/g, "");

export class Repo {
  private tableCache = new Map<string, string[] | null>();
  constructor(public db: DB, public projectId = "P1") {}

  columns(table: string): string[] | null {
    if (this.tableCache.has(table)) return this.tableCache.get(table)!;
    const rows = this.db.prepare(`SELECT name FROM pragma_table_info(?)`).all(table) as { name: string }[];
    const cols = rows.length ? rows.map((r) => r.name) : null;
    this.tableCache.set(table, cols);
    return cols;
  }

  // ------------------------------------------------------------ locations
  locations(): LocationRow[] {
    return this.db.prepare(`SELECT * FROM locations WHERE project_id = ?`).all(this.projectId) as LocationRow[];
  }

  /**
   * Resolve spoken grid/level/zone (+element hint) to location rows.
   * Returns all candidates; caller decides whether it's unique.
   */
  resolveLocation(q: { grid?: string; level?: string; zone?: string; element?: string; raw?: string }): LocationRow[] {
    const locs = this.locations();
    const aliasHit = (l: LocationRow, s?: string) => {
      if (!s || !l.aliases) return false;
      try { return (JSON.parse(l.aliases) as string[]).some((a) => norm(a) === norm(s)); } catch { return false; }
    };
    let c = locs;
    if (q.grid) {
      c = c.filter((l) => norm(l.grid) === norm(q.grid) || aliasHit(l, q.grid) || norm(l.location_id.split(":")[1]) === norm(q.grid));
    } else if (q.zone) {
      // prefer the zone-level location row (grid NULL, e.g. P1:ZoneB:L3) over every grid inside the zone
      const inZone = c.filter((l) => norm(l.zone) === norm(q.zone) || aliasHit(l, q.zone) || norm(l.location_id.split(":")[1]) === norm(q.zone));
      const zoneRows = inZone.filter((l) => !l.grid || norm(l.location_id.split(":")[1]) === norm(q.zone));
      c = zoneRows.length ? zoneRows : inZone;
    } else if (q.element === "slab") {
      c = c.filter((l) => norm(l.grid) === "slab" || /slab/i.test(l.location_id));
    } else {
      c = [];
    }
    if (q.level) {
      const withLevel = c.filter((l) => norm(l.level) === norm(q.level));
      c = withLevel;
    }
    return c;
  }

  // ------------------------------------------------------------ drawings
  drawingRevisions(drawingNumber: string): DrawingRow[] {
    return this.db.prepare(`SELECT * FROM drawings WHERE project_id = ? AND drawing_number = ? ORDER BY rev_ordinal`).all(this.projectId, drawingNumber) as DrawingRow[];
  }
  drawingNumbers(): string[] {
    return (this.db.prepare(`SELECT DISTINCT drawing_number FROM drawings WHERE project_id = ?`).all(this.projectId) as { drawing_number: string }[]).map((r) => r.drawing_number);
  }
  /** Resolve "102" → "A-102" when unique. */
  resolveDrawingNumber(spoken: string): string | null {
    const all = this.drawingNumbers();
    const exact = all.find((d) => norm(d) === norm(spoken));
    if (exact) return exact;
    const suffix = all.filter((d) => d.replace(/\D/g, "") === spoken.replace(/\D/g, "") && /^\d+$/.test(spoken));
    return suffix.length === 1 ? suffix[0] : null;
  }
  latestDrawing(drawingNumber: string): DrawingRow | undefined {
    return this.db.prepare(`SELECT * FROM v_latest_drawings WHERE project_id = ? AND drawing_number = ? ORDER BY rev_ordinal DESC LIMIT 1`).get(this.projectId, drawingNumber) as DrawingRow | undefined;
  }
  drawingById(id: string): DrawingRow | undefined {
    return this.db.prepare(`SELECT * FROM drawings WHERE drawing_id = ?`).get(id) as DrawingRow | undefined;
  }
  /** Hard verification used by the persistence gate. */
  isVerifiedLatest(drawingId: string): boolean {
    const r = this.db.prepare(`SELECT 1 FROM v_latest_drawings WHERE drawing_id = ?`).get(drawingId);
    return !!r;
  }
  /** Latest drawing that covers a location (by facts, else by level). */
  latestDrawingForLocation(locationId: string, level?: string | null): DrawingRow | undefined {
    const byFact = this.db.prepare(
      `SELECT d.* FROM v_latest_drawings d JOIN drawing_facts f ON f.drawing_id = d.drawing_id WHERE f.location_id = ? ORDER BY d.issued_on DESC LIMIT 1`
    ).get(locationId) as DrawingRow | undefined;
    if (byFact) return byFact;
    if (level) {
      const byLevel = this.db.prepare(`SELECT * FROM v_latest_drawings WHERE project_id = ? AND level = ? ORDER BY issued_on DESC`).all(this.projectId, level) as DrawingRow[];
      if (byLevel.length === 1) return byLevel[0];
    }
    return undefined;
  }

  // ------------------------------------------------------------ facts
  currentFacts(locationId: string, attribute?: string, element?: string): FactRow[] {
    let sql = `SELECT * FROM v_current_facts WHERE location_id = ?`;
    const args: unknown[] = [locationId];
    if (attribute) { sql += ` AND attribute = ?`; args.push(attribute); }
    if (element) { sql += ` AND element = ?`; args.push(element); }
    return this.db.prepare(sql).all(...args) as FactRow[];
  }
  /** Facts for the same location/attribute on a specific (possibly superseded) revision. */
  factOnRevision(drawingNumber: string, revision: string, locationId: string, attribute: string): FactRow | undefined {
    return this.db.prepare(
      `SELECT f.*, d.drawing_number, d.revision, d.issued_on FROM drawing_facts f JOIN drawings d ON d.drawing_id = f.drawing_id
       WHERE d.project_id = ? AND d.drawing_number = ? AND d.revision = ? AND f.location_id = ? AND f.attribute = ? LIMIT 1`
    ).get(this.projectId, drawingNumber, revision, locationId, attribute) as FactRow | undefined;
  }
  factsAnyRevision(drawingNumber: string, locationId: string, attribute: string): FactRow[] {
    return this.db.prepare(
      `SELECT f.*, d.drawing_number, d.revision, d.issued_on FROM drawing_facts f JOIN drawings d ON d.drawing_id = f.drawing_id
       WHERE d.project_id = ? AND d.drawing_number = ? AND f.location_id = ? AND f.attribute = ? ORDER BY d.rev_ordinal`
    ).all(this.projectId, drawingNumber, locationId, attribute) as FactRow[];
  }
  rfiForDrawing(drawingId: string): { rfi_id: string; subject: string; answered_on: string | null } | undefined {
    return this.db.prepare(`SELECT rfi_id, subject, answered_on FROM rfis WHERE resulting_drawing_id = ? LIMIT 1`).get(drawingId) as never;
  }

  // ------------------------------------------------------------ permits
  /** A location plus the zone-level location that contains it (P1:C-5:L3 → P1:ZoneB:L3). */
  relatedLocationIds(locationId: string): string[] {
    const l = this.db.prepare(`SELECT * FROM locations WHERE location_id = ?`).get(locationId) as LocationRow | undefined;
    const ids = [locationId];
    if (l?.zone && l.level) {
      const z = this.db.prepare(`SELECT location_id FROM locations WHERE project_id = ? AND grid IS NULL AND zone = ? AND level = ?`).all(this.projectId, l.zone, l.level) as { location_id: string }[];
      for (const r of z) if (!ids.includes(r.location_id)) ids.push(r.location_id);
    }
    return ids;
  }

  permitBlockers(locationId: string, activity: string): { blocks: PermitBlock[]; activePermits: string[]; noPermit: boolean } {
    const ids = this.relatedLocationIds(locationId);
    const permits = this.db.prepare(
      `SELECT * FROM permits WHERE project_id = ? AND permit_type = ? AND (location_id IN (${ids.map(() => "?").join(",")}) OR location_id IS NULL)`
    ).all(this.projectId, activity, ...ids) as { permit_id: string; permit_type: string; location_id: string | null; status: string }[];
    const active = permits.filter((p) => p.status === "Active");
    const blocks: PermitBlock[] = [];
    for (const p of active) {
      const un = this.db.prepare(`SELECT field_id, label FROM permit_checks WHERE permit_id = ? AND is_mandatory = 1 AND satisfied = 0`).all(p.permit_id) as { field_id: number; label: string }[];
      if (un.length) blocks.push({ ...p, unsatisfied: un });
    }
    // Suspended permits also block
    for (const p of permits.filter((p) => p.status === "Suspended")) blocks.push({ ...p, unsatisfied: [{ field_id: -1, label: "Permit suspended" }] });
    return { blocks, activePermits: active.map((p) => p.permit_id), noPermit: active.length === 0 };
  }
  permitsWithChecks() {
    const permits = this.db.prepare(`SELECT * FROM permits WHERE project_id = ? ORDER BY permit_id`).all(this.projectId) as Record<string, unknown>[];
    const checks = this.db.prepare(`SELECT * FROM permit_checks WHERE permit_id = ?`);
    return permits.map((p) => ({ ...p, checks: checks.all(p.permit_id as string) }));
  }

  // ------------------------------------------------------------ hold points (optional tables; introspected)
  holdPointBlockers(locationId: string): HoldPointBlock[] {
    const out: HoldPointBlock[] = [];
    const inst = this.columns("checklist_instances");
    const items = this.columns("checklist_items");
    if (inst && items) {
      const idCol = ["instance_id", "checklist_id", "id"].find((c) => inst.includes(c));
      const itemFk = ["instance_id", "checklist_id"].find((c) => items.includes(c));
      if (idCol && itemFk) {
        const locCol = inst.includes("location_id") ? "location_id" : null;
        const ids = this.relatedLocationIds(locationId);
        const rows = (locCol
          ? this.db.prepare(`SELECT * FROM checklist_instances WHERE ${locCol} IN (${ids.map(() => "?").join(",")})`).all(...ids)
          : this.db.prepare(`SELECT * FROM checklist_instances`).all()) as Record<string, unknown>[];
        const holdCol = items.includes("is_hold_point") ? "is_hold_point" : null;
        const releaseExpr = this.releaseExpr(items);
        for (const r of rows) {
          const status = String(r.status ?? "").toLowerCase();
          if (["released", "closed", "approved", "complete", "completed"].includes(status)) continue;
          if (inst.includes("hold_point_released") && Number(r.hold_point_released) === 1) continue;
          const its = this.db.prepare(
            `SELECT * FROM checklist_items WHERE ${itemFk} = ? ${holdCol ? `AND ${holdCol} = 1` : ""} AND NOT (${releaseExpr})`
          ).all(r[idCol]) as Record<string, unknown>[];
          if (its.length) {
            out.push({
              source: "checklist", ref: String(r[idCol]), template_id: (r.template_id as string) ?? null, location_id: (r.location_id as string) ?? null,
              notes: (r.notes as string) ?? null,
              items: its
                .sort((a, b) => Number(/^hold/i.test(String(b.status ?? ""))) - Number(/^hold/i.test(String(a.status ?? ""))))
                .map((i) => ({ label: String(i.label ?? i.item ?? i.description ?? "Hold point"), code_ref: (i.code_ref as string) ?? null })),
            });
          }
        }
      }
    }
    return out;
  }
  private releaseExpr(cols: string[]): string {
    const parts: string[] = [];
    for (const c of ["released", "satisfied", "is_released", "checked", "ok", "done"]) if (cols.includes(c)) parts.push(`COALESCE(${c},0) = 1`);
    if (cols.includes("status")) parts.push(`LOWER(COALESCE(status,'')) IN ('released','ok','done','yes','pass','passed','approved','complete','completed','satisfied','na','n/a')`);
    if (cols.includes("released_at")) parts.push(`released_at IS NOT NULL AND released_at <> ''`);
    return parts.length ? parts.join(" OR ") : "0";
  }

  template(id: string): { template_id: string; title: string } | undefined {
    return this.db.prepare(`SELECT template_id, title FROM templates WHERE template_id = ?`).get(id) as never;
  }
  locationExists(id: string): boolean {
    return !!this.db.prepare(`SELECT 1 FROM locations WHERE location_id = ?`).get(id);
  }
}
