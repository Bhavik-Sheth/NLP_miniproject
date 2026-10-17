// Typed client for the tenancy (W2) and ingest (W1) endpoints — PLAN §4.
// Shares API_BASE and ApiError with lib/api.ts. The token getter in api.ts is module-private,
// so this module keeps its own; `setTenancyTokenGetter` also forwards to api.ts so one call wires both.
import { API_BASE, ApiError, setApiTokenGetter } from "./api";
import { STATIC_DEMO, mockStatic } from "./static-demo";

type TokenGetter = () => Promise<string | null>;
let tokenGetter: TokenGetter | null = null;
let activeOrgId: string | null = null;

export function setTenancyTokenGetter(getter: TokenGetter | null) {
  tokenGetter = getter;
  setApiTokenGetter(getter);
}

let activeUserId: string | null = null;

/** Local dev (no CLERK_JWT_ISSUER on the backend) reads identity from X-Vesper-User / X-Vesper-Org.
 *  With Clerk auth on, the backend ignores these and trusts the token. */
export function setTenancyActiveOrg(orgId: string | null) {
  activeOrgId = orgId;
}
export function setTenancyUser(userId: string | null) {
  activeUserId = userId;
}

async function headers(init?: HeadersInit): Promise<Headers> {
  const h = new Headers(init);
  const token = tokenGetter ? await tokenGetter().catch(() => null) : null;
  if (token) h.set("authorization", `Bearer ${token}`);
  if (activeOrgId) h.set("x-vesper-org", activeOrgId);
  if (activeUserId) h.set("x-vesper-user", activeUserId);
  return h;
}

async function req<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  if (STATIC_DEMO) return (await mockStatic(path, init)) as T;
  const { json, ...rest } = init ?? {};
  let res: Response;
  try {
    const h = await headers(rest.headers);
    if (json !== undefined) h.set("content-type", "application/json");
    res = await fetch(`${API_BASE}${path}`, {
      ...rest,
      headers: h,
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  } catch (e) {
    throw new ApiError(`Can't reach the Vesper backend (${(e as Error).message})`, 0);
  }
  const ct = res.headers.get("content-type") || "";
  if (!res.ok) {
    let detail = "";
    let fieldErrors: FieldError[] = [];
    try {
      if (ct.includes("json")) {
        const body = (await res.json()) as { detail?: unknown; error?: unknown; errors?: FieldError[] };
        if (Array.isArray(body.errors)) fieldErrors = body.errors;
        const d = body.detail ?? body.error ?? body;
        detail = typeof d === "string" ? d : JSON.stringify(d);
      } else {
        detail = await res.text();
      }
    } catch {
      /* ignore */
    }
    throw new TenancyError(detail || `${path} failed (${res.status})`, res.status, fieldErrors);
  }
  return (ct.includes("json") ? await res.json() : await res.text()) as T;
}

// ---------- types ----------

export type FieldError = { key: string; message: string };

/** ApiError plus the per-field errors W2 returns on 409/422 ({errors:[{key,message}]}). */
export class TenancyError extends ApiError {
  fieldErrors: FieldError[];
  constructor(message: string, status: number, fieldErrors: FieldError[] = []) {
    super(message, status);
    this.name = "TenancyError";
    this.fieldErrors = fieldErrors;
  }
}

export type OrgRole = string;

export type OrgSummary = { id: string; name: string; role?: OrgRole | null };

export type ProjectSummary = {
  id: string;
  name: string;
  code?: string | null;
  type?: string | null;
  city?: string | null;
  status?: string | null;
  role?: string | null;
  orgId?: string | null;
  isDemo?: boolean;
};

export type Me = {
  user: { id: string; email?: string | null };
  org: OrgSummary | null;
  orgs: OrgSummary[];
  projects: ProjectSummary[];
  onboarding: { orgDone: boolean; projectDone: boolean };
  authMode?: "clerk" | "local";
};

export type FieldType =
  | "text"
  | "textarea"
  | "number"
  | "date"
  | "select"
  | "multiselect"
  | "phone"
  | "email"
  | "gstin"
  | "pan"
  | "pincode"
  | "currency"
  | "file"
  | "repeater"
  | "toggle"
  | "geo";

export type FieldOption = string | { value: string; label?: string };

export type FieldValidation = {
  pattern?: string;
  message?: string;
  min?: number;
  max?: number;
  minLength?: number;
  maxLength?: number;
  minItems?: number;
  maxItems?: number;
  afterField?: string;
};

export type SchemaField = {
  key: string;
  label: string;
  type: FieldType | string;
  required?: boolean;
  options?: FieldOption[];
  help?: string;
  placeholder?: string;
  /** true, or a string explaining which voice check uses it. */
  usedByVoice?: boolean | string;
  /** Why/how the answer becomes memory — shown in the "used by voice" tooltip. */
  memoryHint?: string;
  validation?: FieldValidation;
  /** e.g. "templates?type=Checklist" — richer option list from the backend; `options` is the offline subset. */
  optionsSource?: string;
  /** legacy top-level forms, still honoured */
  pattern?: string;
  min?: number;
  max?: number;
  unit?: string;
  accept?: string;
  multiple?: boolean;
  /** ingest category for file fields (drawing_register, boq, itp …). */
  category?: string;
  /** repeater item fields. */
  fields?: SchemaField[];
  itemLabel?: string;
  default?: unknown;
};

export type SchemaStep = {
  id: string;
  title: string;
  description?: string;
  fields: SchemaField[];
};

export type OnboardingSchema = {
  version?: string | number;
  org: { steps: SchemaStep[] };
  project: { steps: SchemaStep[] };
};

export type ProfileValues = Record<string, unknown>;

export type OrgRecord = { id: string; clerkOrgId?: string; name?: string; profile?: ProfileValues } & Record<string, unknown>;

export type ProjectRecord = ProjectSummary & { profile?: ProfileValues } & Record<string, unknown>;

export type CreateProjectResponse = {
  project: ProjectRecord;
  memory?: { status: string; detail?: string; jobId?: string; chunks?: number } | null;
};

export type IngestCategory =
  | "drawing_register"
  | "spec"
  | "method_statement"
  | "rfi"
  | "permit"
  | "dpr"
  | "boq"
  | "contract"
  | "itp"
  | "other";

export type IngestStatus = "queued" | "parsing" | "embedding" | "graph" | "done" | "error";

export type IngestJob = {
  jobId: string;
  docId?: string | null;
  title?: string | null;
  status: IngestStatus | string;
  progress?: number | null;
  error?: string | null;
  category?: string | null;
  createdAt?: string | null;
};

export type IngestAccepted = { jobId: string; docId?: string; status: IngestStatus | string };

export type VoiceIngestResponse = { transcript: string; jobId: string; docId?: string };

// ---------- client ----------

export const tenancyApi = {
  me: () => req<Me>("/api/me"),

  schema: () => req<OnboardingSchema>("/api/onboarding/schema"),

  createOrg: (body: { clerkOrgId: string | null; profile: ProfileValues }) =>
    req<{ org: OrgRecord }>("/api/orgs", { method: "POST", json: body }),
  getOrg: (orgId: string) => req<{ org: OrgRecord }>(`/api/orgs/${encodeURIComponent(orgId)}`),
  updateOrg: (orgId: string, body: { profile: ProfileValues }) =>
    req<{ org: OrgRecord }>(`/api/orgs/${encodeURIComponent(orgId)}`, { method: "PUT", json: body }),

  createProject: (profile: ProfileValues) =>
    req<CreateProjectResponse>("/api/projects", { method: "POST", json: { profile } }),
  projects: () => req<ProjectSummary[]>("/api/projects"),
  project: (id: string) => req<{ project: ProjectRecord }>(`/api/projects/${encodeURIComponent(id)}`),
  /** PATCH merges into the stored profile (W2). */
  updateProject: (id: string, patch: { profile: ProfileValues }) =>
    req<{ project: ProjectRecord; memory?: CreateProjectResponse["memory"] }>(`/api/projects/${encodeURIComponent(id)}`, {
      method: "PATCH",
      json: patch,
    }),
  invite: (id: string, body: { email: string; role: string }) =>
    req<{ ok?: boolean } & Record<string, unknown>>(`/api/projects/${encodeURIComponent(id)}/invites`, {
      method: "POST",
      json: body,
    }),

  acceptInvite: (token: string) =>
    req<{ projectId: string; role: string }>("/api/invites/accept", { method: "POST", json: { token } }),

  stt: (blob: Blob, language?: string) => {
    const fd = new FormData();
    fd.set("file", blob, "dictation.webm");
    if (language) fd.set("language", language);
    return req<{ text: string }>("/api/stt", { method: "POST", body: fd });
  },
};

export const ingestApi = {
  file: (opts: { projectId: string; file: File | Blob; category?: string; filename?: string }) => {
    const fd = new FormData();
    const name = opts.filename ?? (opts.file instanceof File ? opts.file.name : "upload.bin");
    fd.set("file", opts.file, name);
    fd.set("projectId", opts.projectId);
    if (opts.category) fd.set("category", opts.category);
    return req<IngestAccepted>("/api/ingest/file", { method: "POST", body: fd });
  },

  text: (body: { projectId: string; title: string; text: string; category?: string }) =>
    req<IngestAccepted>("/api/ingest/text", { method: "POST", json: body }),

  voice: (opts: { projectId: string; audio: Blob; title?: string }) => {
    const fd = new FormData();
    fd.set("audio", opts.audio, "note.webm");
    fd.set("projectId", opts.projectId);
    if (opts.title) fd.set("title", opts.title);
    return req<VoiceIngestResponse>("/api/ingest/voice", { method: "POST", body: fd });
  },

  jobs: async (projectId: string) => {
    const r = await req<IngestJob[] | { jobs: IngestJob[] }>(
      `/api/ingest/jobs?projectId=${encodeURIComponent(projectId)}`,
    );
    return Array.isArray(r) ? r : r.jobs ?? [];
  },
};

export { ApiError };
