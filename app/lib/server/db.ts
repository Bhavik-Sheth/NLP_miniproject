import "server-only";
import Database from "better-sqlite3";
import fs from "node:fs";
import path from "node:path";
import { Repo } from "../engine/repo";
import { loadEnv } from "./env";

loadEnv();

const APP_DIR = process.cwd();
export const FIXTURE_DB = path.resolve(APP_DIR, "dev-fixture/site.db");

export function resolveDbPath(): { path: string; source: "site.db" | "dev-fixture" } {
  const p = path.resolve(APP_DIR, process.env.SITE_DB_PATH || "../data/site.db");
  if (fs.existsSync(p)) return { path: p, source: "site.db" };
  return { path: FIXTURE_DB, source: "dev-fixture" };
}

interface Handle { db: Database.Database; repo: Repo; path: string; ino: number; mtimeMs: number; source: string }
const g = globalThis as unknown as { __vesperDb?: Handle };

/** Shared read/write connection. Reopens automatically if the data agent rebuilds site.db underneath us. */
export function getRepo(): Repo {
  const { path: p, source } = resolveDbPath();
  const st = fs.statSync(p);
  const h = g.__vesperDb;
  if (h && h.path === p && h.ino === st.ino) return h.repo;
  try { h?.db.close(); } catch { /* ignore */ }
  const db = new Database(p);
  db.pragma("busy_timeout = 3000");
  db.pragma("foreign_keys = ON");
  const repo = new Repo(db, "P1");
  g.__vesperDb = { db, repo, path: p, ino: st.ino, mtimeMs: st.mtimeMs, source };
  return repo;
}

export function dbInfo() {
  const { path: p, source } = resolveDbPath();
  return { path: path.relative(path.resolve(APP_DIR, ".."), p), source };
}
