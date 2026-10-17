"use client";

// /onboarding/project — schema-driven project wizard → POST /api/projects → uploads → success.
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ingestApi,
  TenancyError,
  tenancyApi,
  type CreateProjectResponse,
  type FieldError,
  type Me,
  type ProfileValues,
  setTenancyActiveOrg,
} from "@/lib/api-tenancy";
import { IngestPanel } from "./IngestPanel";
import { LOCAL_ORG_KEY } from "./OrgOnboarding";
import { setOnboardingCookie } from "./OnboardingGate";
import { Callout, OIcon, OnboardingShell, Spin, useTenancyAuth } from "./primitives";
import { fileCategory, splitFiles, useOnboardingSchema } from "./schema";
import { Wizard } from "./Wizard";
import { prefillProject } from "./prefill";

type Upload = { key: string; label: string; name: string; status: "uploading" | "queued" | "linked" | "error"; error?: string };

const MEMORY_COPY: Record<string, { tone: "ok" | "info" | "warn" | "danger"; title: string; body: string }> = {
  done: { tone: "ok", title: "Profile is in project memory", body: "Vesper can already answer and challenge using these details." },
  queued: { tone: "info", title: "Indexing the profile into memory", body: "Usually a few seconds. Progress appears below." },
  running: { tone: "info", title: "Indexing the profile into memory", body: "Usually a few seconds. Progress appears below." },
  pending: { tone: "warn", title: "Memory service not connected yet", body: "The profile is saved; it will be indexed as soon as the memory layer is running." },
  error: { tone: "danger", title: "Memory ingestion failed", body: "The project is saved. Re-save the profile from settings to retry." },
};

export default function ProjectOnboarding() {
  const router = useRouter();
  const { orgId, isLoaded } = useTenancyAuth();
  const { schema, notice } = useOnboardingSchema();
  const [me, setMe] = useState<Me | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [serverErrors, setServerErrors] = useState<FieldError[]>([]);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [created, setCreated] = useState<CreateProjectResponse | null>(null);
  const [uploads, setUploads] = useState<Upload[]>([]);

  // personal-workspace fallback (Clerk orgs off, local auth)
  useEffect(() => {
    if (!isLoaded || orgId) return;
    try {
      const local = localStorage.getItem(LOCAL_ORG_KEY);
      if (local) setTenancyActiveOrg(local);
    } catch {
      /* ignore */
    }
  }, [isLoaded, orgId]);

  useEffect(() => {
    if (!isLoaded) return;
    tenancyApi
      .me()
      .then((m) => {
        setMe(m);
        if (m.authMode !== "local" && !m.onboarding.orgDone) router.replace("/onboarding/org");
      })
      .catch((e: TenancyError) =>
        setMeError(e.status === 404 ? "The tenancy API isn't loaded on the backend (GET /api/me → 404). Restart the backend to include routes.tenancy — you can fill the form meanwhile; it autosaves." : e.status === 0 ? "The Vesper backend isn't reachable. Your draft autosaves on this device." : e.message),
      );
  }, [isLoaded, orgId, router]);

  const storageOrg = orgId ?? (typeof window !== "undefined" ? (() => { try { return localStorage.getItem(LOCAL_ORG_KEY); } catch { return null; } })() : null) ?? "personal";

  const submit = useCallback(
    async (values: ProfileValues) => {
      if (!schema) return;
      setServerErrors([]);
      setSubmitError(null);
      const { profile, files } = splitFiles(schema.project.steps, values);
      let res: CreateProjectResponse;
      try {
        res = await tenancyApi.createProject(profile);
      } catch (e) {
        const err = e as TenancyError;
        if (err.fieldErrors?.length) {
          setServerErrors(err.fieldErrors);
          setSubmitError(err.status === 409 ? err.fieldErrors[0].message : "Some fields need attention — they're highlighted on their steps.");
        } else if (err.status === 409) setSubmitError(`${err.message}. Finish the organization step first.`);
        else setSubmitError(err.message);
        return;
      }

      try {
        localStorage.removeItem(`vesper-onb:project:${storageOrg}`);
      } catch {
        /* ignore */
      }
      setOnboardingCookie("done");
      setCreated(res);
      window.scrollTo({ top: 0, behavior: "smooth" });

      // upload wizard files now that a projectId exists, then link refs on the profile
      const pid = res.project.id;
      const initial: Upload[] = files.flatMap(({ field, files: fl }) => fl.map((f) => ({ key: field.key, label: field.label, name: f.name, status: "uploading" as const })));
      setUploads(initial);
      const refs: ProfileValues = {};
      await Promise.all(
        files.flatMap(({ field, files: fl }) =>
          fl.map(async (file) => {
            const mark = (p: Partial<Upload>) => setUploads((u) => u.map((x) => (x.key === field.key && x.name === file.name ? { ...x, ...p } : x)));
            try {
              const r = await ingestApi.file({ projectId: pid, file, category: fileCategory(field) });
              if (!refs[field.key]) refs[field.key] = { name: file.name, docId: r.docId };
              mark({ status: "queued" });
            } catch (e) {
              mark({ status: "error", error: (e as Error).message });
            }
          }),
        ),
      );
      if (Object.keys(refs).length) {
        try {
          await tenancyApi.updateProject(pid, { profile: refs });
          setUploads((u) => u.map((x) => (x.status === "queued" && refs[x.key] && (refs[x.key] as { name: string }).name === x.name ? { ...x, status: "linked" } : x)));
        } catch {
          /* uploads still ingested; refs just not on the profile */
        }
      }
    },
    [schema, storageOrg],
  );

  if (created) return <Success res={created} uploads={uploads} />;

  const orgName = me?.org?.name;

  return (
    <OnboardingShell wide>
      {schema ? (
        <Wizard
          eyebrow={orgName ? `${orgName} · New project` : "New project"}
          steps={schema.project.steps}
          storageKey={`vesper-onb:project:${storageOrg}`}
          submitLabel="Create project"
          onSubmit={submit}
          samplePrefill={prefillProject}
          serverErrors={serverErrors}
          submitError={submitError}
          intro={
            <div className="vo-enter">
              <h1 className="vo-h1 text-[30px] sm:text-[34px]">
                Tell Vesper about <span className="vo-serif">the project</span>.
              </h1>
              <p className="vo-muted mt-2 max-w-2xl text-[14.5px] leading-relaxed">
                Only a handful of fields are required. Anything marked <span className="vo-voice-badge mx-0.5 inline-flex !cursor-default align-middle">used by voice</span> becomes context Vesper uses to challenge a spoken observation — the more you add, the sharper it gets.
              </p>
            </div>
          }
          notice={meError || notice ? <Callout tone="warn">{meError ?? notice}</Callout> : null}
        />
      ) : (
        <div className="grid min-h-[60dvh] place-items-center">
          <Spin size={20} />
        </div>
      )}
    </OnboardingShell>
  );
}

export function ProjectSuccess(props: { res: CreateProjectResponse; uploads?: Upload[] }) {
  return <Success res={props.res} uploads={props.uploads ?? []} />;
}

function Success({ res, uploads }: { res: CreateProjectResponse; uploads: Upload[] }) {
  const p = res.project;
  const mem = res.memory?.status ?? "pending";
  const copy = MEMORY_COPY[mem] ?? { tone: "info" as const, title: `Memory: ${mem}`, body: res.memory?.detail ?? "" };
  const [showIngest, setShowIngest] = useState(false);

  return (
    <OnboardingShell>
      <section className="py-10 sm:py-16">
        <div className="vo-enter flex flex-col items-start">
          <span className="grid h-14 w-14 place-items-center rounded-full" style={{ background: "color-mix(in srgb, var(--vo-ok) 16%, transparent)", color: "var(--vo-ok)" }}>
            <svg className="vo-check-draw" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="m5 12.5 4.5 4.5L19 7.5" />
            </svg>
          </span>
          <div className="vo-eyebrow mt-6">Project created</div>
          <h1 className="vo-h1 mt-3">{p.name}</h1>
          <div className="vo-muted mt-2 flex flex-wrap items-center gap-2 text-[13.5px]">
            {p.code ? <span className="vo-card px-2 py-0.5 font-mono text-[12px]">{p.code}</span> : null}
            {[p.type, p.city].filter(Boolean).join(" · ")}
          </div>
        </div>

        <div className="vo-glass vo-enter mt-8 p-5 sm:p-6" style={{ animationDelay: "120ms" }}>
          <div className="flex items-center gap-2">
            <OIcon name="brain" size={16} style={{ color: "var(--vo-accent)" }} />
            <span className="text-[14px] font-medium">Project memory</span>
          </div>
          <div className="mt-3">
            <Callout tone={copy.tone} title={copy.title} icon={copy.tone === "info" ? "sparkle" : undefined}>
              {copy.body}
              {res.memory?.detail && mem !== "done" ? <span className="vo-faint mt-1 block text-[12px]">{res.memory.detail}</span> : null}
            </Callout>
          </div>

          {uploads.length ? (
            <ul className="mt-4 flex flex-col gap-1.5">
              {uploads.map((u) => (
                <li key={`${u.key}-${u.name}`} className="vo-card flex items-center gap-2.5 px-3 py-2 text-[13px]">
                  <span className="grid h-5 w-5 place-items-center" style={{ color: u.status === "error" ? "var(--vo-danger)" : u.status === "uploading" ? "var(--vo-text-2)" : "var(--vo-ok)" }}>
                    {u.status === "uploading" ? <Spin size={13} /> : u.status === "error" ? <OIcon name="alert" size={14} /> : <OIcon name="check" size={14} />}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{u.name}</span>
                  <span className="vo-faint hidden text-[11.5px] sm:inline">{u.label}</span>
                  <span className="vo-faint font-mono text-[11px]">{u.status === "error" ? "failed" : u.status === "uploading" ? "uploading" : "queued"}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {uploads.some((u) => u.error) ? <p className="mt-2 text-[12px]" style={{ color: "var(--vo-danger)" }}>{uploads.find((u) => u.error)?.error}</p> : null}
        </div>

        <div className="vo-enter mt-4" style={{ animationDelay: "200ms" }}>
          {showIngest ? (
            <IngestPanel projectId={p.id} />
          ) : (
            <button type="button" className="vo-card flex w-full items-center gap-3 px-4 py-3.5 text-left transition hover:border-[var(--vo-accent)]" onClick={() => setShowIngest(true)}>
              <span className="grid h-9 w-9 place-items-center rounded-full" style={{ background: "var(--vo-surface-2)", color: "var(--vo-accent)" }}>
                <OIcon name="upload" size={16} />
              </span>
              <span className="flex-1">
                <span className="block text-[14px] font-medium">Add documents, notes or a voice briefing</span>
                <span className="vo-faint text-[12.5px]">Drawing register, specs, method statements, RFIs, permits, DPRs</span>
              </span>
              <OIcon name="arrowRight" size={15} className="vo-faint" />
            </button>
          )}
        </div>

        <div className="vo-enter mt-8 flex flex-col gap-3 sm:flex-row sm:items-center" style={{ animationDelay: "260ms" }}>
          <Link href="/app" className="vo-btn vo-btn-primary h-11 px-6 text-[14.5px]">
            Open dashboard <OIcon name="arrowRight" size={15} />
          </Link>
          <Link href="/onboarding/project" className="vo-btn vo-btn-quiet h-11" onClick={() => window.location.reload()}>
            Set up another project
          </Link>
        </div>
      </section>
    </OnboardingShell>
  );
}
