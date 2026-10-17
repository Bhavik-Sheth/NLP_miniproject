// Small fetch helper — all backend calls go through here (or to the /demo mock).
import { isDemo, mockReq } from "./demo";
// Base URL from env, default to local backend.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

// Clerk session tokens live ~60 s, so a token captured once at mount goes stale and every
// later call fails auth. Keep the getter instead: Clerk caches and refreshes it in memory,
// so asking per request costs nothing on the hot path.
type TokenGetter = () => Promise<string | null>;
let tokenGetter: TokenGetter | null = null;

export function setApiTokenGetter(getter: TokenGetter | null) {
  tokenGetter = getter;
}

async function authHeaders(init?: HeadersInit): Promise<Headers> {
  const headers = new Headers(init);
  const token = tokenGetter ? await tokenGetter().catch(() => null) : null;
  if (token) headers.set("authorization", `Bearer ${token}`);
  return headers;
}

export type Health = {
  db: boolean;
  llm: "cerebras" | "nvidia" | "groq" | "off";
  rime: boolean;
  voiceid: boolean;
};

export type Entity = { kind: string; label: string; confidence: number };
export type Contradiction = {
  kind: string;
  severity: string;
  detail: string;
  evidence?: unknown;
};
export type Blocker = Contradiction;
export type Missing = { kind: string; detail: string; evidence?: unknown };

export type DecisionKey =
  | "log_observation"
  | "raise_rfi"
  | "raise_ncr"
  | "stop_work"
  | "cancel";

export type Reply = { text: string; speech?: string };

export type Speaker = { match: boolean; score: number } | null;

export type TurnResponse = {
  kind?: "answer" | "observation";
  lowConfidence?: string[];
  state:
    | "capturing"
    | "checking"
    | "challenging"
    | "confirming"
    | "blocked"
    | "logged"
    | "cancelled";
  entities: Entity[];
  contradictions: Contradiction[];
  blockers: Blocker[];
  missing: Missing[];
  reply: Reply;
  allowedDecisions: DecisionKey[];
  slots?: Record<
    string,
    { value: unknown; confidence: number; source: string; confirmed: boolean }
  >;
  resolved?: Record<string, unknown>;
  speaker?: Speaker;
  clarifiedKinds?: string[];
  events?: string[];
};

export type DecisionResponse = {
  state: string;
  reply: Reply;
  logged: { observation_id?: string; rfi_id?: string; decision: string } | null;
  allowedDecisions: DecisionKey[];
};

export type ObservationRow = {
  observation_id: string;
  created_at: string;
  location_id: string;
  element: string;
  attribute: string;
  value_claimed: string | number;
  unit: string;
  drawing_id: string;
  revision_claimed: string;
  contradiction_flag: boolean;
  contradiction_kinds: string[];
  final_decision: string;
  linked_rfi_id: string | null;
};

export type ObservationDetail = ObservationRow &
  Record<string, unknown> & {
    evidence?: {
      drawing?: Record<string, unknown> | null;
      rfi?: Record<string, unknown> | null;
      code_ref?: Record<string, unknown> | null;
    };
  };

export type ScenarioMeta = { id: string; title: string };

export type ScenarioResult = {
  id: string;
  title: string;
  pass: boolean;
  failures: string[];
  kindsSeen: string[];
  clarified: boolean;
  finalDecision: string;
  logged: unknown[];
  transcript: { role: string; text: string; bargeIn?: boolean; state?: string }[];
};

export type ScenarioRunResponse = {
  passed: number;
  total: number;
  wrongLogs: number;
  results: ScenarioResult[];
};

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  if (isDemo()) {
    try {
      return (await mockReq(path, init)) as T;
    } catch (e) {
      throw new ApiError((e as Error).message, (e as { status?: number }).status ?? 500);
    }
  }
  let res: Response;
  try {
    const headers = await authHeaders(init?.headers);
    res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch (e) {
    throw new ApiError(
      `Network error calling ${path}: ${(e as Error).message}`,
      0,
    );
  }
  const ct = res.headers.get("content-type") || "";
  if (!res.ok) {
    let detail = "";
    try {
      detail = ct.includes("json")
        ? JSON.stringify(await res.json())
        : await res.text();
    } catch {
      /* ignore */
    }
    throw new ApiError(`${path} -> ${res.status} ${detail}`.trim(), res.status);
  }
  if (ct.includes("json")) return (await res.json()) as T;
  return (await res.text()) as unknown as T;
}

export { ApiError };

export type RtcToken = {
  url: string;
  token: string;
  room: string;
  identity: string;
};

export const api = {
  health: () => req<Health>("/api/health"),

  // LiveKit real-time token. 503 until LIVEKIT_* is configured on the backend.
  rtcToken: (body?: { name?: string; language?: "en-IN" | "hi-IN"; projectId?: string }) =>
    req<RtcToken>("/api/rtc/token", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body ?? {}),
    }),

  createSession: (userName?: string) =>
    req<{ sessionId: string; commandLimit: number | null; commandsUsed: number }>("/api/session", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(userName ? { userName } : {}),
    }),

  bootstrapDemo: (email: string) =>
    req<{ seeded: boolean }>("/api/bootstrap-demo", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email }),
    }),

  // JSON turn (typed input, no audio)
  turnJson: (body: {
    sessionId: string;
    text: string;
    bargeIn?: boolean;
    noise?: "none" | "low" | "medium" | "high";
    language?: "en-IN" | "hi-IN";
  }) =>
    req<TurnResponse>("/api/turn", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }),

  // Multipart turn (mic + audio blob)
  turnMultipart: (opts: {
    sessionId: string;
    text: string;
    bargeIn?: boolean;
    noise?: string;
    language?: "en-IN" | "hi-IN";
    audio?: Blob;
  }) => {
    const fd = new FormData();
    fd.set("sessionId", opts.sessionId);
    fd.set("text", opts.text);
    if (opts.bargeIn != null) fd.set("bargeIn", String(opts.bargeIn));
    if (opts.noise) fd.set("noise", opts.noise);
    if (opts.language) fd.set("language", opts.language);
    if (opts.audio) fd.set("audio", opts.audio, "utterance.webm");
    return req<TurnResponse>("/api/turn", { method: "POST", body: fd });
  },

  decision: (sessionId: string, decision: DecisionKey, language?: "en-IN" | "hi-IN") =>
    req<DecisionResponse>("/api/decision", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sessionId, decision, language }),
    }),

  voiceStatus: () =>
    req<{
      enabled: boolean;
      reachable: boolean;
      enrolled: boolean;
      threshold: number;
    }>("/api/voice/status"),

  voiceEnroll: (blobs: Blob[]) => {
    const fd = new FormData();
    blobs.forEach((b, i) => fd.append("files", b, `enroll_${i}.webm`));
    return req<{
      enrolled: boolean;
      samples: number;
      dims: number;
      cohesion: number;
    }>("/api/voice/enroll", { method: "POST", body: fd });
  },

  // Server-side STT (Groq Whisper). Used when the browser Web Speech API is unavailable
  // or errors ('network' on Linux Chromium).
  stt: (blob: Blob, language?: string) => {
    const fd = new FormData();
    fd.set("file", blob, "turn.webm");
    if (language) fd.set("language", language);
    return req<{ text: string }>("/api/stt", { method: "POST", body: fd });
  },

  observations: (projectId?: string) =>
    req<ObservationRow[]>(`/api/observations${projectId ? `?projectId=${encodeURIComponent(projectId)}` : ""}`),

  conversations: () =>
    req<{
      sessions: Array<{
        session_id: string;
        started_at: string;
        ended_at: string | null;
        lang: string;
        turns: Array<{ role: "user" | "agent"; text: string; state: string; created_at: string }>;
      }>;
      commandLimit: number | null;
      commandsUsed: number;
    }>("/api/conversations"),
  observation: (id: string, projectId?: string) =>
    req<ObservationDetail>(
      `/api/observations/${encodeURIComponent(id)}${projectId ? `?projectId=${encodeURIComponent(projectId)}` : ""}`,
    ),

  scenarios: () => req<ScenarioMeta[]>("/api/scenarios"),
  runScenarios: (ids?: string[]) =>
    req<ScenarioRunResponse>("/api/scenarios/run", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(ids ? { ids } : {}),
    }),

  // TTS: returns {ok:true, blob} on audio, {ok:false} on 503 rime-missing.
  async tts(
    text: string,
    language: "en-IN" | "hi-IN" = "en-IN",
  ): Promise<{ ok: true; blob: Blob } | { ok: false; reason: string }> {
    if (isDemo()) {
      // The demo carries no key: it plays Rime clips pre-rendered at build time
      // (scripts/build_demo_audio.py). Unknown text -> browser voice fallback.
      try {
        const manifest = (await (await fetch("/demo-audio/manifest.json")).json()) as Record<string, string>;
        const path = manifest[text];
        if (path) return { ok: true, blob: await (await fetch(`/${path}`)).blob() };
      } catch {
        /* no manifest in this build */
      }
      return { ok: false, reason: "demo" };
    }
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/api/tts`, {
        method: "POST",
        headers: await authHeaders({ "content-type": "application/json" }),
        body: JSON.stringify({ text, language }),
        signal: AbortSignal.timeout(15_000),
      });
    } catch (e) {
      return { ok: false, reason: (e as Error).message };
    }
    if (res.status === 503) return { ok: false, reason: "rime key missing" };
    if (!res.ok) return { ok: false, reason: `tts ${res.status}` };
    return { ok: true, blob: await res.blob() };
  },
};
