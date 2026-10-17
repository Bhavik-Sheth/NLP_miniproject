// Public static build (STATIC_DEMO=1): the laptop dashboard and onboarding run with no backend and no
// keys. Requests that would go to the v2 / tenancy / ingest APIs are answered from
// lib/demo-dashboard.json, recorded from a real backend by scripts/build_dashboard_demo.py, so every
// memory answer shown is one the product actually produced. Nothing is sent anywhere.
import recorded from "./demo-dashboard.json";

export const STATIC_DEMO = process.env.NEXT_PUBLIC_STATIC_DEMO === "1";

type Json = Record<string, unknown>;
type Ask = { query: string; ask: Json; search: Json };

const data = recorded as unknown as {
  me: Json;
  overview: Json;
  stats: Json;
  graph: Json;
  documents: Json[];
  drawings: Json[];
  rfis: Json[];
  permits: Json[];
  schema: Json;
  asks: Ask[];
};

/** Questions the demo plays into Ask memory one by one. */
export const DEMO_QUESTIONS = data.asks.map((a) => a.query);

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));
const norm = (t: string) => t.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

function closest(query: string): Ask | null {
  const q = norm(query);
  const exact = data.asks.find((a) => norm(a.query) === q);
  if (exact) return exact;
  const words = new Set(q.split(" ").filter((w) => w.length > 2));
  let best: Ask | null = null;
  let score = 0;
  for (const a of data.asks) {
    const overlap = norm(a.query).split(" ").filter((w) => words.has(w)).length;
    if (overlap > score) {
      best = a;
      score = overlap;
    }
  }
  return score >= 2 ? best : null;
}

const ABSTAIN = (query: string) => ({
  answer: "This is the recorded public demo, so only the suggested questions have recorded answers. Sign in to ask the live memory anything.",
  speech: "",
  abstain: true,
  confidence: 0,
  citations: [],
  rewrittenQuery: query,
  hits: [],
});

// ingest jobs advance on a timer so the progress UI animates like the real pipeline
type Job = { jobId: string; docId: string; title: string; startedAt: number };
const jobs: Job[] = [];
const STAGES = ["queued", "parsing", "embedding", "graph", "done"] as const;

function jobView(j: Job) {
  const i = Math.min(STAGES.length - 1, Math.floor((Date.now() - j.startedAt) / 1400));
  return { jobId: j.jobId, docId: j.docId, title: j.title, status: STAGES[i], progress: i / (STAGES.length - 1), error: null };
}

function addJob(title: string) {
  const id = Math.random().toString(36).slice(2, 10);
  const j = { jobId: `job_demo_${id}`, docId: `doc_demo_${id}`, title, startedAt: Date.now() };
  jobs.unshift(j);
  return { jobId: j.jobId, docId: j.docId, status: "queued" };
}

function bodyOf(init?: RequestInit & { json?: unknown }): Json {
  if (init?.json !== undefined) return init.json as Json;
  if (typeof init?.body === "string") {
    try {
      return JSON.parse(init.body) as Json;
    } catch {
      return {};
    }
  }
  if (init?.body instanceof FormData) return Object.fromEntries(init.body.entries()) as Json;
  return {};
}

export async function mockStatic(path: string, init?: RequestInit & { json?: unknown }): Promise<unknown> {
  const route = path.split("?")[0];
  const method = (init?.method ?? (init?.json !== undefined ? "POST" : "GET")).toUpperCase();
  const body = bodyOf(init);

  if (route === "/api/memory/ask") {
    await delay(900 + Math.random() * 700);
    const hit = closest(String(body.query ?? ""));
    return hit ? hit.ask : ABSTAIN(String(body.query ?? ""));
  }
  if (route === "/api/memory/search") {
    await delay(350 + Math.random() * 250);
    const hit = closest(String(body.query ?? ""));
    return hit ? hit.search : { rewrittenQuery: body.query ?? "", abstain: true, hits: [] };
  }

  await delay(120);
  switch (route) {
    case "/api/v2/status":
      return { routers: { "routes.memory": "ok", "routes.ingest": "ok", "routes.tenancy": "ok" } };
    case "/api/me":
      return data.me;
    case "/api/projects":
      if (method === "POST") {
        const p = (body.profile ?? {}) as Json;
        addJob(`Project fact sheet — ${String(p.name ?? "New project")}`);
        return { project: { id: "P1", name: p.name ?? "New project", code: p.code ?? "DEMO", type: p.projectType ?? null, city: p.city ?? null, status: "active" }, memory: { status: "queued" } };
      }
      return (data.me.projects as Json[]) ?? [];
    case "/api/orgs":
      return { org: { id: "org_local_demo", name: String(((body.profile ?? {}) as Json).legalName ?? "Demo organization") } };
    case "/api/onboarding/schema":
      return data.schema;
    case "/api/memory/stats":
      return data.stats;
    case "/api/memory/graph":
      return data.graph;
    case "/api/memory/documents":
      return [...jobs.filter((j) => jobView(j).status === "done").map((j) => ({ docId: j.docId, title: j.title, category: "upload", source: "demo upload", chunks: 12, status: "done", createdAt: new Date(j.startedAt).toISOString() })), ...data.documents];
    case "/api/drawings":
      return data.drawings;
    case "/api/rfis":
      return data.rfis;
    case "/api/permits":
      return data.permits;
    case "/api/ingest/file":
      return addJob(String((body.file as File | undefined)?.name ?? "Uploaded document"));
    case "/api/ingest/text":
      return addJob(String(body.title ?? "Pasted note"));
    case "/api/ingest/voice":
      return { ...addJob(String(body.title ?? "Voice briefing")), transcript: "L4 slab pour stays on hold until RFI-050 closes the cover shortfall at three locations." };
    case "/api/ingest/jobs":
      return jobs.map(jobView);
    case "/api/stt":
      return { text: "Pour of the L4 slab is on hold until RFI-050 is closed." };
    default:
      if (/^\/api\/projects\/[^/]+\/overview$/.test(route)) return data.overview;
      if (/^\/api\/projects\/[^/]+\/invites$/.test(route)) return { ok: true, invite: { email: body.email, role: body.role, status: "demo — not sent" } };
      if (/^\/api\/projects\/[^/]+$/.test(route)) return { project: (data.overview as Json).project, ...((data.overview as Json).project as Json) };
      if (/^\/api\/orgs\/[^/]+$/.test(route)) return { org: data.me.org };
      return null;
  }
}
