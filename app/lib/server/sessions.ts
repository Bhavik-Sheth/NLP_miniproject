import "server-only";
import { DialogueSession } from "../engine/dialogue";
import { makeClaudeAssist } from "../engine/llm";
import { createSession } from "../engine/persist";
import { getRepo } from "./db";
import { loadEnv } from "./env";

const g = globalThis as unknown as { __vesperSessions?: Map<string, DialogueSession> };
const sessions = (g.__vesperSessions ??= new Map());

export function newSession(userName?: string): DialogueSession {
  loadEnv();
  const repo = getRepo();
  const id = createSession(repo, userName);
  const s = new DialogueSession(repo, id, makeClaudeAssist());
  sessions.set(id, s);
  return s;
}

export function getSession(id: string): DialogueSession | undefined {
  const s = sessions.get(id);
  if (s) s.repo = getRepo(); // follow DB reopen after a rebuild
  return s;
}
