// Loads the repo-root .env (RIME_API_KEY, ANTHROPIC_API_KEY, …) into process.env on the server only.
// Never import this from client components. Values are never logged.
import { config } from "dotenv";
import path from "node:path";

let loaded = false;
export function loadEnv() {
  if (loaded) return;
  loaded = true;
  config({ path: path.resolve(process.cwd(), "../.env"), quiet: true });
  config({ path: path.resolve(process.cwd(), ".env.local"), quiet: true });
}

export function envStatus() {
  loadEnv();
  return {
    rime: !!process.env.RIME_API_KEY,
    llm: !!process.env.ANTHROPIC_API_KEY,
    rimeModel: process.env.RIME_MODEL || "coda",
    rimeSpeaker: process.env.RIME_SPEAKER || "nadi",
    rimeLang: process.env.RIME_LANG || "hi",
  };
}
