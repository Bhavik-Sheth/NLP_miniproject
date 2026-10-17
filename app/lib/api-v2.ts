// Typed client for the Vesper v2 HTTP API (docs/plan/PLAN.md §4) plus the v1 site-record
// endpoints the dashboard falls back to. Shares API_BASE and the Clerk token getter with
// lib/api.ts: call setDashboardTokenGetter() once and both clients authenticate.
import { API_BASE, ApiError, setApiTokenGetter } from "./api";
import { STATIC_DEMO, mockStatic } from "./static-demo";

type TokenGetter = () => Promise<string | null>;
let getter: TokenGetter | null = null;

export function setDashboardTokenGetter(g: TokenGetter | null) {
  getter = g;
  setApiTokenGetter(g);
}

async function request<T>(path: string, init?: RequestInit & { timeoutMs?: number }): Promise<T> {
  if (STATIC_DEMO) return (await mockStatic(path, init)) as T;
  const headers = new Headers(init?.headers);
  const token = getter ? await getter().catch(() => null) : null;
  if (token) headers.set("authorization", `Bearer ${token}`);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      signal: init?.signal ?? AbortSignal.timeout(init?.timeoutMs ?? 30_000),
    });
  } catch (e) {
    throw new ApiError(`Network error calling ${path}: ${(e as Error).message}`, 0);
  }
  const ct = res.headers.get("content-type") || "";
  if (!res.ok) {
    let detail = "";
    try {
      detail = ct.includes("json") ? JSON.stringify(await res.json()) : await res.text();
    } catch {
      /* ignore */
    }
    throw new ApiError(`${path} → ${res.status} ${detail}`.trim(), res.status);
  }
  return (ct.includes("json") ? await res.json() : await res.text()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

const qs = (o: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v != null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

/** True when an error means "this endpoint is not deployed yet" rather than a real failure. */
export const isMissing = (e: unknown) =>
  e instanceof ApiError && (e.status === 404 || e.status === 405 || e.status === 501);

// ------------------------------------------------------------------ tenancy (W2)
export type OrgRef = { id: string; name: string; role?: string | null };
export type ProjectRef = {
  id: string;
  name: string;
  code?: string | null;
  type?: string | null;
  city?: string | null;
  status?: string | null;
  role?: string | null;
};
export type Me = {
  user: { id: string; email: string | null };
  org: OrgRef | null;
  orgs: OrgRef[];
  projects: ProjectRef[];
  onboarding: { orgDone: boolean; projectDone: boolean };
};
export type Activity = {
  kind: string;
  id?: string;
  title: string;
  detail?: string;
  at: string;
  tone?: "ok" | "warn" | "danger" | "info";
};
export type Overview = {
  project: ProjectRef & Record<string, unknown>;
  counts: {
    drawings: number;
    rfisOpen: number;
    permitsActive: number;
    holdPoints: number;
    observations: number;
    documents: number;
    chunks: number;
  };
  recent: Activity[];
};

// ------------------------------------------------------------------ memory (W1)
export type SearchHit = {
  chunkId: string;
  docId: string;
  title: string;
  section?: string | null;
  source?: string | null;
  url?: string | null;
  category?: string | null;
  text: string;
  vectorScore?: number | null;
  bm25Rank?: number | null;
  rrfScore?: number | null;
  rerankScore?: number | null;
  citation?: string | null;
};
/** Per-leg latency in milliseconds, if the backend reports it (e.g. rewrite, embed, vector, bm25, rrf, rerank, llm, total). */
export type Timings = Record<string, number>;
export type SearchResponse = { rewrittenQuery: string; abstain: boolean; hits: SearchHit[]; timings?: Timings; timingsMs?: Timings };
export type Citation = { title: string; section?: string | null; citation?: string | null; url?: string | null };
export type AskResponse = {
  answer: string;
  speech?: string;
  abstain: boolean;
  confidence: number;
  citations: Citation[];
  rewrittenQuery?: string;
  hits?: SearchHit[];
  timings?: Timings;
  timingsMs?: Timings;
};
export type Corpus = { scope: string; name: string; documents: number; chunks: number; lastIngested?: string | null };
export type MemoryStats = {
  corpora: Corpus[];
  graph: { nodes: number; edges: number };
  models: { embedding?: string; reranker?: string; llm?: string; vectorStore?: string; graphStore?: string };
};
export type GraphNode = { id: string; label: string; type: string };
export type GraphEdge = { source: string; target: string; label?: string };
export type GraphData = { nodes: GraphNode[]; edges: GraphEdge[] };
export type MemoryDocument = {
  docId: string;
  title: string;
  category?: string | null;
  source?: string | null;
  chunks: number;
  status: string;
  createdAt: string;
};
export type IngestJob = {
  jobId: string;
  docId?: string | null;
  title?: string | null;
  status: "queued" | "parsing" | "embedding" | "graph" | "done" | "error";
  progress?: number | null;
  error?: string | null;
};
export type IngestAccepted = { jobId: string; docId: string; status: string; transcript?: string };

// ------------------------------------------------------------------ v1 site record (P1)
export type Drawing = {
  drawing_id: string;
  project_id: string;
  drawing_number: string;
  revision: string;
  rev_ordinal: number;
  title: string;
  discipline: string;
  status: string;
  issued_on: string;
  zone: string | null;
  level: string | null;
  is_latest: number;
  superseded_by: string | null;
  change_note: string | null;
};
export type Rfi = {
  rfi_id: string;
  project_id: string;
  subject: string;
  location_id: string | null;
  drawing_ref: string | null;
  spec_ref: string | null;
  question: string | null;
  response: string | null;
  status: string;
  raised_on: string | null;
  answered_on: string | null;
  impact: string | null;
  resulting_drawing_id: string | null;
  template_id: string | null;
};
export type PermitCheck = {
  permit_id: string;
  field_id: number;
  label: string;
  is_mandatory: number;
  satisfied: number;
  confirmed_by: string | null;
  confirmed_at: string | null;
};
export type Permit = {
  permit_id: string;
  project_id: string;
  permit_type: string;
  location_id: string | null;
  valid_from: string | null;
  valid_to: string | null;
  status: string;
  issued_by: string | null;
  template_id: string | null;
  checks: PermitCheck[];
};
export type V2Status = { routers: Record<string, string> };

export const apiV2 = {
  // tenancy
  me: () => request<Me>("/api/me"),
  projects: () => request<ProjectRef[]>("/api/projects"),
  project: (id: string) => request<ProjectRef & Record<string, unknown>>(`/api/projects/${encodeURIComponent(id)}`),
  overview: (id: string) => request<Overview>(`/api/projects/${encodeURIComponent(id)}/overview`),
  invite: (projectId: string, body: { email: string; role: string }) =>
    request<{ ok?: boolean; invite?: unknown }>(`/api/projects/${encodeURIComponent(projectId)}/invites`, json(body)),

  // memory
  search: (body: { query: string; projectId?: string; scopes?: ("global" | "project")[]; k?: number }) =>
    request<SearchResponse>("/api/memory/search", json(body)),
  ask: (body: { query: string; projectId: string; sessionId?: string }) =>
    request<AskResponse>("/api/memory/ask", { ...json(body), timeoutMs: 60_000 }),
  stats: (projectId?: string) => request<MemoryStats>(`/api/memory/stats${qs({ projectId })}`),
  graph: (o: { projectId?: string; q?: string; limit?: number }) =>
    request<GraphData>(`/api/memory/graph${qs({ projectId: o.projectId, q: o.q, limit: o.limit ?? 150 })}`),
  documents: (projectId?: string) => request<MemoryDocument[]>(`/api/memory/documents${qs({ projectId })}`),

  // ingest
  ingestFile: (projectId: string, file: File, category?: string) => {
    const fd = new FormData();
    fd.set("file", file, file.name);
    fd.set("projectId", projectId);
    if (category) fd.set("category", category);
    return request<IngestAccepted>("/api/ingest/file", { method: "POST", body: fd, timeoutMs: 120_000 });
  },
  ingestText: (body: { projectId: string; title: string; text: string; category?: string }) =>
    request<IngestAccepted>("/api/ingest/text", json(body)),
  ingestVoice: (projectId: string, audio: Blob, title?: string) => {
    const fd = new FormData();
    fd.set("audio", audio, "voice-note.webm");
    fd.set("projectId", projectId);
    if (title) fd.set("title", title);
    return request<IngestAccepted>("/api/ingest/voice", { method: "POST", body: fd, timeoutMs: 120_000 });
  },
  ingestJobs: (projectId?: string) => request<IngestJob[]>(`/api/ingest/jobs${qs({ projectId })}`),

  // v1 deterministic site record + status. projectId remains optional for older servers/callers.
  drawings: (projectId?: string) => request<Drawing[]>(`/api/drawings${qs({ projectId })}`),
  rfis: (projectId?: string) => request<Rfi[]>(`/api/rfis${qs({ projectId })}`),
  permits: (projectId?: string) => request<Permit[]>(`/api/permits${qs({ projectId })}`),
  v2Status: () => request<V2Status>("/api/v2/status", { timeoutMs: 5_000 }),
};

export { ApiError };
