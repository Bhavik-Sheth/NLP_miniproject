"use client";

// /onboarding and /onboarding/org — welcome → client organization (Clerk) → org profile → POST /api/orgs.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth, useClerk, useOrganizationList, useUser } from "@clerk/nextjs";
import { TenancyError, tenancyApi, type FieldError, type Me, type ProfileValues, setTenancyActiveOrg, setTenancyTokenGetter } from "@/lib/api-tenancy";
import { onboardingTarget, setOnboardingCookie, skipOnboarding } from "./OnboardingGate";
import { Callout, OIcon, OnboardingShell, Spin, useTenancyAuth } from "./primitives";
import { splitFiles, useOnboardingSchema } from "./schema";
import { Wizard } from "./Wizard";
import { prefillOrg } from "./prefill";

type Stage = "welcome" | "workspace" | "profile";

export const LOCAL_ORG_KEY = "vesper-local-org";

function orgsDisabledError(e: unknown): boolean {
  const err = e as { errors?: { code?: string; message?: string; longMessage?: string }[]; message?: string };
  const text = [err.message, ...(err.errors ?? []).flatMap((x) => [x.code, x.message, x.longMessage])].filter(Boolean).join(" ");
  return /not_enabled|organi[sz]ations?\b.*\b(not enabled|disabled|turned off|feature)/i.test(text);
}

function clerkMessage(e: unknown): string {
  const err = e as { errors?: { longMessage?: string; message?: string }[]; message?: string };
  return err.errors?.[0]?.longMessage ?? err.errors?.[0]?.message ?? err.message ?? "Something went wrong.";
}

export default function OrgOnboarding() {
  const router = useRouter();
  const clerk = useClerk();
  const { user } = useUser();
  const { getToken } = useAuth();
  const { orgId, userId, isLoaded } = useTenancyAuth();
  const { schema, notice } = useOnboardingSchema();
  const orgList = useOrganizationList({ userMemberships: { infinite: true } });

  const [stage, setStage] = useState<Stage>("welcome");
  const [me, setMe] = useState<Me | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [orgName, setOrgName] = useState("");
  const [creating, setCreating] = useState(false);
  const [wsError, setWsError] = useState<string | null>(null);
  const [orgsOff, setOrgsOff] = useState(false);
  const [personal, setPersonal] = useState(false);
  const [serverErrors, setServerErrors] = useState<FieldError[]>([]);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Clerk exposes instance settings on the environment; undefined → unknown, find out on create.
  useEffect(() => {
    const env = (clerk as unknown as { __unstable__environment?: { organizationSettings?: { enabled?: boolean } } }).__unstable__environment;
    if (env?.organizationSettings?.enabled === false) setOrgsOff(true);
  }, [clerk, clerk.loaded]);

  const loadMe = useCallback(async () => {
    try {
      const m = await tenancyApi.me();
      setMe(m);
      setMeError(null);
      return m;
    } catch (e) {
      const s = (e as TenancyError).status;
      setMeError(s === 404 ? "The tenancy API isn't loaded on the backend (GET /api/me → 404). Restart the backend so routes.tenancy is included." : s === 0 ? "The Vesper backend isn't reachable on " + (process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000") + "." : (e as Error).message);
      return null;
    }
  }, []);

  // Already onboarded? Route onward (not in local auth mode, where everyone sits in the demo org).
  useEffect(() => {
    if (!isLoaded) return;
    void loadMe().then((m) => {
      if (!m || m.authMode === "local") return;
      if (m.onboarding.orgDone && orgId) {
        const t = onboardingTarget(m);
        setOnboardingCookie(t ? "pending" : "done");
        router.replace(t ?? "/app");
      }
    });
  }, [isLoaded, orgId, loadMe, router]);

  useEffect(() => {
    if (!orgName && orgList.isLoaded && user) {
      const domain = user.primaryEmailAddress?.emailAddress.split("@")[1];
      if (domain && !/gmail|yahoo|outlook|hotmail|icloud|proton/.test(domain)) {
        const base = domain.split(".")[0];
        setOrgName(base.charAt(0).toUpperCase() + base.slice(1));
      }
    }
  }, [orgList.isLoaded, user, orgName]);

  const memberships = orgList.isLoaded ? orgList.userMemberships.data ?? [] : [];
  const localMode = me?.authMode === "local";

  const pickOrg = async (id: string) => {
    if (!orgList.isLoaded) return;
    setWsError(null);
    setCreating(true);
    try {
      await orgList.setActive({ organization: id });
      setTenancyActiveOrg(id);
      setPersonal(false);
      const m = await loadMe();
      if (m?.onboarding.orgDone && m.authMode !== "local") {
        const t = onboardingTarget(m);
        setOnboardingCookie(t ? "pending" : "done");
        router.replace(t ?? "/app");
        return;
      }
      setStage("profile");
    } catch (e) {
      setWsError(clerkMessage(e));
    } finally {
      setCreating(false);
    }
  };

  const createOrg = async () => {
    const name = orgName.trim();
    if (name.length < 2) return setWsError("Give the organization a name (at least 2 characters).");
    if (!orgList.isLoaded) return;
    setCreating(true);
    setWsError(null);
    try {
      const org = await orgList.createOrganization({ name });
      await orgList.setActive({ organization: org.id });
      setTenancyActiveOrg(org.id);
      setPersonal(false);
      setStage("profile");
    } catch (e) {
      if (orgsDisabledError(e)) setOrgsOff(true);
      else setWsError(clerkMessage(e));
    } finally {
      setCreating(false);
    }
  };

  const continuePersonal = () => {
    const id = `org_personal_${(userId ?? "local").replace(/^user_/, "").toLowerCase()}`;
    try {
      localStorage.setItem(LOCAL_ORG_KEY, id);
    } catch {
      /* ignore */
    }
    setTenancyActiveOrg(id);
    setPersonal(true);
    setStage("profile");
  };

  const submitProfile = async (values: ProfileValues) => {
    if (!schema) return;
    setServerErrors([]);
    setSubmitError(null);
    const { profile } = splitFiles(schema.org.steps, values);
    const clerkOrgId = personal ? `org_personal_${(userId ?? "local").replace(/^user_/, "").toLowerCase()}` : (orgId ?? null);
    // fresh token so the org claim from setActive() is present
    setTenancyTokenGetter(() => getToken({ skipCache: true }));
    try {
      await tenancyApi.createOrg({ clerkOrgId, profile });
      try {
        localStorage.removeItem(`vesper-onb:org:${clerkOrgId ?? "personal"}`);
      } catch {
        /* ignore */
      }
      const m = await loadMe();
      const target = m && m.authMode !== "local" ? onboardingTarget(m) : "/onboarding/project";
      setOnboardingCookie(target ? "pending" : "done");
      router.push(target ?? "/app");
    } catch (e) {
      const err = e as TenancyError;
      if (err.fieldErrors?.length) {
        setServerErrors(err.fieldErrors);
        setSubmitError("Some fields need attention.");
      } else if (err.status === 400 && personal) {
        setSubmitError("This backend uses Clerk auth, which needs a real organization. Enable Organizations in the Clerk dashboard → Organizations settings, then create one here.");
      } else setSubmitError(err.message);
    } finally {
      setTenancyTokenGetter(() => getToken());
    }
  };

  const initial = useMemo<ProfileValues>(
    () => ({
      legalName: orgList.isLoaded ? memberships.find((m) => m.organization.id === orgId)?.organization.name ?? orgName : orgName,
      primaryContactName: user?.fullName ?? "",
      primaryContactEmail: user?.primaryEmailAddress?.emailAddress ?? "",
      primaryContactPhone: user?.primaryPhoneNumber?.phoneNumber ?? "",
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [orgId, user?.id, stage],
  );

  const backendNotice = meError ? (
    <Callout tone="warn" title="Backend not ready">
      {meError}
    </Callout>
  ) : null;

  return (
    <OnboardingShell wide={stage === "profile"}>
      {stage === "welcome" ? (
        <section className="flex min-h-[calc(100dvh-8rem)] flex-col justify-center py-10">
          <div className="vo-enter">
            <div className="vo-eyebrow">Welcome{user?.firstName ? `, ${user.firstName}` : ""}</div>
            <h1 className="vo-h1 mt-4">
              Set up the memory <span className="vo-serif">your site</span> will speak to.
            </h1>
            <p className="vo-muted mt-4 max-w-xl text-[15.5px] leading-relaxed">
              Vesper verifies every spoken observation against your drawings, permits and hold points before it&apos;s logged. Two short steps give it the context to push back when something is wrong.
            </p>
          </div>

          <ol className="mt-9 grid grid-cols-1 gap-3 sm:grid-cols-3">
            {[
              { icon: "building", t: "Your organization", d: "The client company that owns projects. ~2 min." },
              { icon: "file", t: "First project", d: "Grids, grades, drawing rules, hold points. ~8 min, save as you go." },
              { icon: "brain", t: "Project memory", d: "Upload registers, BOQ and ITP — or just talk." },
            ].map((s, i) => (
              <li key={s.t} className="vo-glass vo-enter p-4" style={{ animationDelay: `${80 + i * 70}ms` }}>
                <div className="flex items-center justify-between">
                  <span className="grid h-8 w-8 place-items-center rounded-full" style={{ background: "var(--vo-surface-2)", color: "var(--vo-accent)" }}>
                    <OIcon name={s.icon} size={15} />
                  </span>
                  <span className="vo-faint font-mono text-[11px]">0{i + 1}</span>
                </div>
                <div className="mt-3 text-[14px] font-medium">{s.t}</div>
                <p className="vo-faint mt-1 text-[12.5px] leading-relaxed">{s.d}</p>
              </li>
            ))}
          </ol>

          {backendNotice ? <div className="mt-6">{backendNotice}</div> : null}
          {localMode ? (
            <div className="mt-6">
              <Callout title="Local auth mode">
                The backend has no <code>CLERK_JWT_ISSUER</code>, so every request is treated as the seeded demo org and P1 is already available. You can still walk through onboarding; data is saved under a local org id.
              </Callout>
            </div>
          ) : null}

          <div className="vo-enter mt-9 flex flex-col gap-3 sm:flex-row sm:items-center" style={{ animationDelay: "320ms" }}>
            <button type="button" className="vo-btn vo-btn-primary h-11 px-6 text-[14.5px]" onClick={() => setStage(orgId && !me?.onboarding.orgDone ? "profile" : "workspace")} autoFocus>
              Get started <OIcon name="arrowRight" size={15} />
            </button>
            <button
              type="button"
              className="vo-btn vo-btn-quiet h-11"
              onClick={() => {
                skipOnboarding();
                router.push("/app");
              }}
            >
              Explore the demo project first
            </button>
          </div>
        </section>
      ) : null}

      {stage === "workspace" ? (
        <section className="py-10 sm:py-16">
          <button type="button" className="vo-btn vo-btn-quiet vo-btn-sm -ml-2" onClick={() => setStage("welcome")}>
            <OIcon name="arrowLeft" size={14} /> Back
          </button>
          <div className="vo-enter mt-4">
            <div className="vo-eyebrow">Step 1 · Organization</div>
            <h1 className="vo-h1 mt-3 text-[32px]">Who is the client organization?</h1>
            <p className="vo-muted mt-3 max-w-lg text-[14.5px] leading-relaxed">Projects, members and memory belong to an organization. Invite teammates to it later.</p>
          </div>

          {memberships.length ? (
            <div className="vo-enter mt-7">
              <div className="vo-faint mb-2 text-[12.5px]">Continue with an existing organization</div>
              <ul className="flex flex-col gap-2">
                {memberships.map((m) => (
                  <li key={m.id}>
                    <button type="button" className="vo-card flex w-full items-center gap-3 px-4 py-3 text-left transition hover:border-[var(--vo-accent)]" onClick={() => void pickOrg(m.organization.id)} disabled={creating}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      {m.organization.imageUrl ? <img src={m.organization.imageUrl} alt="" className="h-8 w-8 rounded-lg" /> : <span className="grid h-8 w-8 place-items-center rounded-lg" style={{ background: "var(--vo-surface-2)" }}><OIcon name="building" size={15} /></span>}
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[14px] font-medium">{m.organization.name}</span>
                        <span className="vo-faint text-[12px]">{m.role.replace(/^org:/, "")}</span>
                      </span>
                      {m.organization.id === orgId ? <span className="vo-faint text-[11.5px]">active</span> : null}
                      <OIcon name="arrowRight" size={15} className="vo-faint" />
                    </button>
                  </li>
                ))}
              </ul>
              <div className="vo-faint my-6 flex items-center gap-3 text-[12px]">
                <hr className="flex-1" /> or create a new one <hr className="flex-1" />
              </div>
            </div>
          ) : null}

          <form
            className="vo-glass vo-enter mt-7 p-5 sm:p-7"
            onSubmit={(e) => {
              e.preventDefault();
              void createOrg();
            }}
          >
            <label htmlFor="org-name" className="vo-label">
              Organization name
            </label>
            <div className="mt-2 flex flex-col gap-2 sm:flex-row">
              <input id="org-name" className="vo-input h-11" placeholder="Uttarakhand Infra Builders" value={orgName} onChange={(e) => setOrgName(e.target.value)} autoFocus disabled={orgsOff} autoComplete="organization" />
              <button type="submit" className="vo-btn vo-btn-primary h-11 px-5" disabled={creating || orgsOff || !orgList.isLoaded}>
                {creating ? <Spin /> : <OIcon name="plus" size={15} />} Create organization
              </button>
            </div>
            <p className="vo-faint mt-2 text-[12.5px]">Use the name people on site use. Legal details come next.</p>
            {wsError ? (
              <div className="mt-4">
                <Callout tone="danger">{wsError}</Callout>
              </div>
            ) : null}
          </form>

          {orgsOff ? (
            <div className="vo-enter mt-4 flex flex-col gap-3">
              <Callout tone="warn" title="Organizations are turned off for this Clerk instance">
                Enable Organizations in <strong>Clerk dashboard → Organizations settings</strong> (turn on &ldquo;Enable organizations&rdquo; and allow members to create them), then reload this page. Until then you can continue with a personal workspace
                {localMode ? "." : " — note that a backend running with Clerk auth needs a real organization to save the profile."}
              </Callout>
              <button type="button" className="vo-btn vo-btn-ghost w-fit" onClick={continuePersonal}>
                Continue with a personal workspace <OIcon name="arrowRight" size={14} />
              </button>
            </div>
          ) : null}
          {backendNotice ? <div className="mt-4">{backendNotice}</div> : null}
        </section>
      ) : null}

      {stage === "profile" ? (
        schema ? (
          <Wizard
            eyebrow={personal ? "Personal workspace · profile" : "Organization profile"}
            steps={schema.org.steps}
            storageKey={`vesper-onb:org:${personal ? "personal" : (orgId ?? "personal")}`}
            submitLabel="Save organization"
            onSubmit={submitProfile}
            samplePrefill={prefillOrg}
            serverErrors={serverErrors}
            submitError={submitError}
            initialValues={initial}
            notice={notice || meError ? <Callout tone="warn">{meError ?? notice}</Callout> : null}
          />
        ) : (
          <div className="grid min-h-[50dvh] place-items-center">
            <Spin size={20} />
          </div>
        )
      ) : null}
    </OnboardingShell>
  );
}
