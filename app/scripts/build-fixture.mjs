// Builds app/dev-fixture/site.db from ../data/schema.sql + the README demo-contract rows.
// Used only until the data agent ships data/site.db. Safe to re-run (recreates the file).
import Database from "better-sqlite3";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const appDir = path.resolve(here, "..");
const schemaPath = path.resolve(appDir, "../data/schema.sql");
const out = path.resolve(appDir, "dev-fixture/site.db");

export function buildFixture(target = out) {
  fs.mkdirSync(path.dirname(target), { recursive: true });
  for (const suffix of ["", "-wal", "-shm"]) fs.rmSync(target + suffix, { force: true });
  const db = new Database(target);
  db.exec(fs.readFileSync(schemaPath, "utf8"));

  // Dev-only extension (the data agent may ship something similar; the engine queries defensively)
  db.exec(`
    CREATE TABLE IF NOT EXISTS checklist_instances (
      instance_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, template_id TEXT, location_id TEXT,
      activity TEXT, status TEXT, created_on TEXT);
    CREATE TABLE IF NOT EXISTS checklist_items (
      instance_id TEXT NOT NULL, ordinal INTEGER, label TEXT NOT NULL, is_hold_point INTEGER DEFAULT 0,
      is_mandatory INTEGER DEFAULT 1, released INTEGER DEFAULT 0, released_by TEXT, released_at TEXT, code_ref TEXT);
  `);

  const run = (sql, rows) => { const st = db.prepare(sql); for (const r of rows) st.run(...r); };
  run(`INSERT INTO template_sources VALUES (?,?,?)`, [
    ["formats", "https://infralens.in/formats", null],
    ["qaqc", "https://infralens.in/qaqc", null],
    ["pmc", "https://infralens.in/pmc", null],
  ]);
  run(`INSERT INTO templates (template_id, source_id, family, family_code, title, type, description) VALUES (?,?,?,?,?,?,?)`, [
    ["QC-SPW-REG-004", "qaqc", "Site Progress & Work", "SPW", "Site Observation Register", "Register", "Register of site observations"],
    ["QC-CON-CHK-001", "qaqc", "Concrete & RCC", "CON", "Pre-Pour Checklist", "Checklist", "Checks before concrete pour"],
    ["PMC-SAF-PMT-001", "pmc", "Safety", "SAF", "Hot Work Permit", "Permit", "Hot work permit to work"],
    ["PMC-DSN-LOG-003", "pmc", "Design", "DSN", "RFI Log", "Log", "Request for information log"],
  ]);
  run(`INSERT INTO template_fields (field_id, template_id, section, ordinal, label, field_kind, is_mandatory, is_hold_point, code_ref) VALUES (?,?,?,?,?,?,?,?,?)`, [
    [1, "PMC-SAF-PMT-001", "Precautions", 1, "Fire watch arranged with extinguisher", "check_item", 1, 1, "IS 3016"],
    [2, "PMC-SAF-PMT-001", "Precautions", 2, "Combustibles removed within 11 m", "check_item", 1, 0, "IS 3016"],
    [3, "QC-CON-CHK-001", "Pre-pour checks", 1, "Cover blocks placed as per drawing", "check_item", 1, 0, "IS 456 Cl. 26.4"],
    [4, "QC-CON-CHK-001", "Sign-off", 2, "Engineer release of pour (hold point)", "check_item", 1, 1, "IS 456 Cl. 13"],
  ]);
  run(`INSERT INTO projects VALUES (?,?,?,?,?,?)`, [
    ["P1", "Tower B, Residential G+12, Hinjewadi, Pune", "Demo Client", "Hinjewadi, Pune", "Item Rate (CPWD)", "2026-01-15"],
  ]);
  run(`INSERT INTO locations VALUES (?,?,?,?,?,?)`, [
    ["P1:C-5:L3", "P1", "C-5", "L3", null, JSON.stringify(["C5", "C 5", "see five", "सी पांच"])],
    ["P1:C-6:L3", "P1", "C-6", "L3", null, JSON.stringify(["C6", "C 6", "see six", "सी छह"])],
    ["P1:B-4:L3", "P1", "B-4", "L3", null, JSON.stringify(["B4", "B 4", "bee four"])],
    ["P1:ZoneB:L3", "P1", null, "L3", "Zone B", JSON.stringify(["zone b", "zone bee", "ज़ोन बी"])],
    ["P1:Slab:L4", "P1", "Slab", "L4", null, JSON.stringify(["L4 slab", "level 4 slab", "chauthi manzil slab"])],
  ]);
  run(`INSERT INTO drawings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)`, [
    ["A-102@R4", "P1", "A-102", "R4", 4, "Column Reinforcement Details — Level 3", "Structural", "For Construction", "2026-08-12", null, "L3", 1, null, "C-5 spacing revised 200→180 mm per RFI-047"],
    ["A-102@R3", "P1", "A-102", "R3", 3, "Column Reinforcement Details — Level 3", "Structural", "Superseded", "2026-07-20", null, "L3", 0, "A-102@R4", "Initial issue for construction"],
    ["S-301@R2", "P1", "S-301", "R2", 2, "Level 4 Slab GA", "Structural", "For Construction", "2026-08-01", null, "L4", 1, null, null],
  ]);
  run(`INSERT INTO drawing_facts (drawing_id, location_id, element, attribute, value_num, unit, tolerance, code_ref) VALUES (?,?,?,?,?,?,?,?)`, [
    ["A-102@R3", "P1:C-5:L3", "column", "rebar_spacing", 200, "mm", 10, "IS 456 Cl. 26.5.3"],
    ["A-102@R4", "P1:C-5:L3", "column", "rebar_spacing", 180, "mm", 10, "IS 456 Cl. 26.5.3"],
    ["A-102@R4", "P1:C-6:L3", "column", "rebar_spacing", 180, "mm", 10, "IS 456 Cl. 26.5.3"],
    ["A-102@R4", "P1:C-5:L3", "column", "cover", 40, "mm", 5, "IS 456 Cl. 26.4"],
    ["A-102@R4", "P1:C-6:L3", "column", "cover", 40, "mm", 5, "IS 456 Cl. 26.4"],
    ["S-301@R2", "P1:Slab:L4", "slab", "thickness", 150, "mm", 5, "IS 456 Cl. 24"],
  ]);
  run(`INSERT INTO rfis (rfi_id, project_id, subject, location_id, drawing_ref, question, response, status, raised_on, answered_on, impact, resulting_drawing_id, template_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`, [
    ["RFI-047", "P1", "Column C-5 stirrup spacing clarification", "P1:C-5:L3", "A-102", "Confirm stirrup spacing at C-5", "Revise to 180 mm c/c", "Answered", "2026-08-02", "2026-08-10", "Revision issued: A-102 R4", "A-102@R4", "PMC-DSN-LOG-003"],
  ]);
  run(`INSERT INTO permits VALUES (?,?,?,?,?,?,?,?,?)`, [
    ["HWP-0112", "P1", "hot_work", "P1:ZoneB:L3", "2026-09-10T08:00", "2026-09-10T18:00", "Active", "Safety Officer", "PMC-SAF-PMT-001"],
  ]);
  run(`INSERT INTO permit_checks VALUES (?,?,?,?,?,?,?)`, [
    ["HWP-0112", 1, "Fire watch arranged with extinguisher", 1, 0, null, null],
    ["HWP-0112", 2, "Combustibles removed within 11 m", 1, 1, "Safety Officer", "2026-09-10T08:10"],
  ]);
  run(`INSERT INTO checklist_instances VALUES (?,?,?,?,?,?,?)`, [
    ["CHK-L4-PREPOUR", "P1", "QC-CON-CHK-001", "P1:Slab:L4", "pour", "Open", "2026-09-09"],
  ]);
  run(`INSERT INTO checklist_items VALUES (?,?,?,?,?,?,?,?,?)`, [
    ["CHK-L4-PREPOUR", 1, "Cover blocks placed as per drawing", 0, 1, 1, "QC Engineer", "2026-09-09", "IS 456 Cl. 26.4"],
    ["CHK-L4-PREPOUR", 2, "Engineer release of pour (hold point)", 1, 1, 0, null, null, "IS 456 Cl. 13"],
  ]);
  run(`INSERT INTO doc_chunks (doc_type, doc_ref, project_id, drawing_number, revision, content) VALUES (?,?,?,?,?,?)`, [
    ["drawing", "A-102@R4", "P1", "A-102", "R4", "A-102 R4 Column Reinforcement Details Level 3. Column C-5 and C-6 rebar spacing 180 mm c/c, clear cover 40 mm per IS 456 Cl. 26.4."],
    ["drawing", "A-102@R3", "P1", "A-102", "R3", "A-102 R3 (superseded) Column C-5 rebar spacing 200 mm c/c."],
    ["rfi", "RFI-047", "P1", "A-102", null, "RFI-047 Column C-5 stirrup spacing clarification. Answer: revise to 180 mm c/c. Resulted in A-102 R4."],
    ["permit", "HWP-0112", "P1", null, null, "Hot work permit HWP-0112 Zone B Level 3. Fire watch check not yet confirmed."],
    ["drawing", "S-301@R2", "P1", "S-301", "R2", "S-301 R2 Level 4 slab GA. Slab thickness 150 mm."],
    ["template", "QC-CON-CHK-001", null, null, null, "Pre-pour checklist: cover blocks, shuttering, engineer release hold point before concreting."],
  ]);
  db.close();
  return target;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  console.log("fixture written:", buildFixture(process.argv[2] ? path.resolve(process.argv[2]) : out));
}
