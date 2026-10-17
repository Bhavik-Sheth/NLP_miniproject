"use client";

import { useState } from "react";
import { OrganizationSwitcher, useOrganization, useUser } from "@clerk/nextjs";
import EnrollScreen from "@/components/EnrollScreen";
import { apiV2, isMissing } from "@/lib/api-v2";
import { useDash } from "../context";
import { Icon } from "../icons";
import { Badge, Empty, Field, Notice, PageHeader, Panel, Segmented, Skeleton, fmtDate, useAsync } from "../primitives";
import { useTheme, type ThemePref } from "../theme";

export function Team() {
  const { project, me } = useDash();
  const { user } = useUser();
  const { organization, memberships, isLoaded } = useOrganization({ memberships: { pageSize: 50 } });
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("engineer");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "ok" | "danger" | "neutral"; text: string } | null>(null);

  const invite = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await apiV2.invite(project.id, { email, role });
      setMsg({ tone: "ok", text: `Invite sent to ${email}.` });
      setEmail("");
    } catch (err) {
      setMsg(isMissing(err) ? { tone: "neutral", text: "Invites need POST /api/projects/{id}/invites (W2), which is not live on this backend yet." } : { tone: "danger", text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader eyebrow="Project" title="Team" description={`People who can talk to Vesper about ${project.name}. Only enrolled voices can write logs.`} />
      <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
        <Panel title={organization ? `${organization.name} members` : "Members"} icon="users" bodyClassName="p-0" action={<OrganizationSwitcher hidePersonal={false} afterSelectOrganizationUrl="/app/team" />}>
          {!isLoaded ? (
            <div className="space-y-2 p-4">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-10" />
              ))}
            </div>
          ) : organization && memberships?.data?.length ? (
            <ul className="divide-y divide-line">
              {memberships.data.map((m) => (
                <li key={m.id} className="flex items-center gap-3 px-4 py-3">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={m.publicUserData?.imageUrl} alt="" className="h-8 w-8 rounded-full bg-surface-2" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium text-ink">{[m.publicUserData?.firstName, m.publicUserData?.lastName].filter(Boolean).join(" ") || m.publicUserData?.identifier}</p>
                    <p className="truncate text-[12px] text-ink-3">{m.publicUserData?.identifier}</p>
                  </div>
                  <Badge tone={m.role.includes("admin") ? "accent" : "neutral"}>{m.role.replace("org:", "")}</Badge>
                  <span className="hidden text-[11.5px] text-ink-3 sm:inline">joined {fmtDate(m.createdAt.toISOString())}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div>
              <div className="flex items-center gap-3 border-b border-line px-4 py-3">
                {user?.imageUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={user.imageUrl} alt="" className="h-8 w-8 rounded-full" />
                ) : null}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium text-ink">{user?.fullName ?? me?.user.email ?? "You"}</p>
                  <p className="truncate text-[12px] text-ink-3">{user?.primaryEmailAddress?.emailAddress}</p>
                </div>
                <Badge tone="accent">{project.role ?? "owner"}</Badge>
              </div>
              <Empty icon="building" title="Personal workspace" body="Create or switch to an organization (top right) to share projects with your client company and site team." />
            </div>
          )}
        </Panel>

        <Panel title="Invite to project" icon="mail">
          <form className="space-y-3" onSubmit={invite}>
            <label className="block text-[12px] text-ink-2">
              Email
              <input type="email" required className="dash-input mt-1" placeholder="site.engineer@contractor.in" value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label className="block text-[12px] text-ink-2">
              Role
              <select className="dash-input mt-1" value={role} onChange={(e) => setRole(e.target.value)}>
                <option value="manager">Project manager</option>
                <option value="engineer">Site engineer</option>
                <option value="qa">QA / QC</option>
                <option value="viewer">Viewer</option>
              </select>
            </label>
            <button className="dash-btn dash-btn-primary w-full" disabled={busy || !email}>
              <Icon name="send" size={13} /> {busy ? "Sending…" : "Send invite"}
            </button>
            {msg ? <Notice tone={msg.tone} title={msg.text} /> : null}
          </form>
        </Panel>
      </div>
    </div>
  );
}

export function Settings() {
  const { project, health, v2 } = useDash();
  const { pref, setPref, resolved } = useTheme();
  const profile = useAsync(() => apiV2.project(project.id), [project.id]);
  const entries = profile.data ? Object.entries(profile.data).filter(([, v]) => v != null && v !== "" && typeof v !== "object") : [];
  return (
    <div>
      <PageHeader eyebrow="Project" title="Settings" />
      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <div className="flex flex-col gap-5">
          <Panel title="Appearance" icon="sun">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[13px] font-medium text-ink">Theme</p>
                <p className="text-[12px] text-ink-3">Currently {resolved}. Toggle anywhere with ⇧⌘L.</p>
              </div>
              <Segmented<ThemePref>
                value={pref}
                onChange={setPref}
                options={[
                  { value: "light", label: "Light", icon: "sun" },
                  { value: "dark", label: "Dark", icon: "moon" },
                  { value: "system", label: "System", icon: "monitor" },
                ]}
              />
            </div>
          </Panel>
          <Panel title="Project profile" icon="building">
            {profile.loading ? (
              <Skeleton className="h-32" />
            ) : entries.length ? (
              <dl className="divide-y divide-line">
                {entries.slice(0, 16).map(([k, v]) => (
                  <Field key={k} label={k.replace(/_/g, " ")}>{String(v)}</Field>
                ))}
              </dl>
            ) : (
              <>
                <dl className="divide-y divide-line">
                  <Field label="Name">{project.name}</Field>
                  <Field label="Code">{project.code ?? project.id}</Field>
                  <Field label="Type">{project.type}</Field>
                  <Field label="City">{project.city}</Field>
                  <Field label="Status">{project.status}</Field>
                </dl>
                {profile.missing ? <p className="mt-2 text-[11.5px] text-ink-3">Full onboarding profile appears once GET /api/projects/{"{id}"} is live.</p> : null}
              </>
            )}
          </Panel>
          <Panel title="System" icon="terminal">
            <dl className="divide-y divide-line font-mono text-[12px]">
              <Field label="database">{health ? (health.db ? <Badge tone="ok" dot>ok</Badge> : <Badge tone="danger">down</Badge>) : "…"}</Field>
              <Field label="llm">{health?.llm ?? "…"}</Field>
              <Field label="rime tts">{health ? String(health.rime) : "…"}</Field>
              <Field label="voice id">{health ? String(health.voiceid) : "…"}</Field>
              {v2
                ? Object.entries(v2.routers).map(([k, v]) => (
                    <Field key={k} label={k}>
                      {v === "ok" ? <Badge tone="ok" dot>loaded</Badge> : <span className="break-all text-[11px] text-ink-3">{v}</span>}
                    </Field>
                  ))
                : <Field label="v2 routers">unavailable</Field>}
            </dl>
          </Panel>
        </div>
        <Panel title="Voice enrolment" icon="mic" bodyClassName="p-3">
          <p className="mb-3 px-1 text-[12.5px] text-ink-2">Record three short samples. A local SpeechBrain model verifies every voice turn; an unknown voice can ask questions but cannot log, raise or stop work.</p>
          <div className="dash-legacy p-3">
            <EnrollScreen />
          </div>
        </Panel>
      </div>
    </div>
  );
}
