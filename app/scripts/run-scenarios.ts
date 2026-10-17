// npm run test:scenarios — headless acceptance runner. Exit code 1 on any failure.
// Usage: tsx scripts/run-scenarios.ts [--fixture] [--db path] [--verbose]
import fs from "node:fs";
import path from "node:path";
import { config } from "dotenv";
import { loadScenarios, runAll } from "../lib/scenarios";

const appDir = path.resolve(__dirname, "..");
config({ path: path.resolve(appDir, "../.env"), quiet: true });
delete process.env.ANTHROPIC_API_KEY; // acceptance must pass with the deterministic parser alone

const args = process.argv.slice(2);
const verbose = args.includes("--verbose") || args.includes("-v");
const useFixture = args.includes("--fixture");
const dbArg = args.includes("--db") ? args[args.indexOf("--db") + 1] : undefined;

async function main() {
  let dbPath = dbArg ? path.resolve(dbArg) : path.resolve(appDir, process.env.SITE_DB_PATH || "../data/site.db");
  if (useFixture || !fs.existsSync(dbPath)) {
    dbPath = path.resolve(appDir, "dev-fixture/site.db");
    if (!fs.existsSync(dbPath)) {
      const { buildFixture } = await import("./build-fixture.mjs" as string);
      buildFixture(dbPath);
    }
  }
  if (useFixture) process.env.SCENARIOS_PATH = path.resolve(appDir, "dev-fixture/scenarios.json");
  const { file, scenarios } = loadScenarios(appDir);
  if (!scenarios.length) { console.error("No scenarios found"); process.exit(1); }
  console.log(`DB:        ${path.relative(appDir, dbPath)} (temp copy)`);
  console.log(`Scenarios: ${path.relative(appDir, file)} (${scenarios.length})\n`);

  const results = await runAll(dbPath, scenarios);
  const w = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s.padEnd(n));
  console.log(`${w("ID", 5)} ${w("RESULT", 7)} ${w("TITLE", 44)} ${w("KINDS SEEN", 44)} ${w("CLARIFIED", 9)} ${w("DECISION", 16)} LOGGED`);
  console.log("-".repeat(150));
  for (const r of results) {
    const row = r.logged[r.logged.length - 1];
    const logged = row ? `${row.drawing_id ?? "-"} ${row.location_id ?? "-"} ${row.attribute ?? "-"} ${row.value_claimed ?? ""}${row.unit ?? ""}` : "(none)";
    console.log(`${w(r.id, 5)} ${w(r.pass ? "PASS" : "FAIL", 7)} ${w(r.title, 44)} ${w(r.kindsSeen.join(",") || "-", 44)} ${w(r.clarified ? "yes" : "no", 9)} ${w(r.finalDecision, 16)} ${logged}`);
    for (const f of r.failures) console.log(`        ✗ ${f}`);
    if (verbose || !r.pass) {
      for (const t of r.transcript) console.log(`        ${t.role === "user" ? "USER " : "AGENT"} ${t.bargeIn ? "[barge-in] " : ""}${t.text}${t.turn ? `  [${t.turn.state}]` : ""}`);
    }
  }
  const passed = results.filter((r) => r.pass).length;
  const wrongLogs = results.flatMap((r) => r.failures.filter((f) => /non-latest|unknown location|logged (drawing_id|location_id|value)/.test(f)));
  console.log("-".repeat(150));
  console.log(`${passed}/${results.length} passed · wrong drawing/dimension/location logs: ${wrongLogs.length} · all contradictions clarified before logging: ${results.every((r) => !r.failures.some((f) => /never clarified|no clarification/.test(f))) ? "yes" : "NO"}`);
  process.exit(passed === results.length ? 0 : 1);
}
main().catch((e) => { console.error(e); process.exit(1); });
