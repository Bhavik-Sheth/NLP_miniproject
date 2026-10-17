"use client";

import { useMemo, useState } from "react";
import { api, type ObservationDetail, type ObservationRow } from "@/lib/api";
import type { Drawing, Permit, Rfi } from "@/lib/api-v2";
import { DEMO_LIVE } from "@/lib/demo";
import { Icon } from "../icons";
import { Badge, DataTable, Empty, Field, Mono, Notice, PageHeader, Panel, Sheet, Skeleton, fmtDate, humanize, statusTone, useAsync } from "../primitives";
import { unsatisfied, useSiteRecord, type HoldPoint } from "../siteData";

function RecordError({ error, reload }: { error: string | null; reload: () => void }) {
  if (!error) return null;
  return (
    <div className="mb-4">
      <Notice tone="danger" title="Could not load the site record" action={<button className="dash-btn dash-btn-sm" onClick={reload}>Retry</button>}>
        <span className="font-mono text-[11.5px]">{error}</span>
      </Notice>
    </div>
  );
}

const loc = (l?: string | null) => (l ? l.replace(/^P1:/, "") : "—");

// ------------------------------------------------------------------ observations
export function Observations() {
  const site = useSiteRecord();
  const [sel, setSel] = useState<ObservationRow | null>(null);
  const detail = useAsync(() => (sel ? api.observation(sel.observation_id) : Promise.resolve(null as ObservationDetail | null)), [sel?.observation_id]);
  return (
    <div>
      <PageHeader eyebrow="Site record" title="Observations" description="Every log is a foreign key to the verified drawing revision, location and decision — never free text." />
      <RecordError error={site.error} reload={site.reload} />
      <DataTable
        rows={site.data?.observations ?? null}
        loading={site.loading && !site.data}
        rowKey={(o) => o.observation_id}
        activeKey={sel?.observation_id}
        onRowClick={setSel}
        searchText={(o) => `${o.observation_id} ${o.location_id} ${o.element} ${o.attribute} ${o.drawing_id} ${o.final_decision} ${o.linked_rfi_id ?? ""}`}
        facet={{ label: "Decision", get: (o) => humanize(o.final_decision) }}
        initialSort={{ key: "at", dir: "desc" }}
        columns={[
          { key: "id", header: "ID", cell: (o) => <Mono>{o.observation_id}</Mono>, sort: (o) => o.observation_id, width: 120 },
          { key: "at", header: "When", cell: (o) => <span className="text-ink-2">{fmtDate(o.created_at, true)}</span>, sort: (o) => o.created_at, hideBelow: "md" },
          { key: "loc", header: "Location", cell: (o) => <Mono>{loc(o.location_id)}</Mono>, sort: (o) => o.location_id },
          { key: "what", header: "Claim", cell: (o) => <span>{o.element} {humanize(o.attribute).toLowerCase()} <b className="font-medium tabular-nums">{String(o.value_claimed)}{o.unit}</b></span> },
          { key: "dwg", header: "Drawing", cell: (o) => <Mono className="text-ink-2">{o.drawing_id}</Mono>, sort: (o) => o.drawing_id, hideBelow: "lg" },
          { key: "flag", header: "Check", cell: (o) => (o.contradiction_flag ? <Badge tone="danger">contradiction</Badge> : <Badge tone="ok">verified</Badge>), hideBelow: "md" },
          { key: "decision", header: "Decision", cell: (o) => <Badge tone={statusTone(o.final_decision)} dot>{humanize(o.final_decision)}</Badge>, sort: (o) => o.final_decision },
        ]}
      />
      <Sheet open={!!sel} onClose={() => setSel(null)} title={sel?.observation_id} subtitle={sel ? `${sel.element} ${sel.attribute} at ${loc(sel.location_id)}` : null}>
        {sel ? (
          <div>
            <dl className="divide-y divide-line">
              <Field label="Logged">{fmtDate(sel.created_at, true)}</Field>
              <Field label="Claimed">{String(sel.value_claimed)} {sel.unit}</Field>
              <Field label="Drawing"><Mono>{sel.drawing_id}</Mono> {sel.revision_claimed ? <span className="text-ink-3">claimed {sel.revision_claimed}</span> : null}</Field>
              <Field label="Decision"><Badge tone={statusTone(sel.final_decision)} dot>{humanize(sel.final_decision)}</Badge></Field>
              <Field label="Contradictions">{sel.contradiction_kinds?.length ? sel.contradiction_kinds.map((k) => <Badge key={k} tone="danger">{humanize(k)}</Badge>) : "None"}</Field>
              <Field label="Linked RFI">{sel.linked_rfi_id ?? "—"}</Field>
            </dl>
            <p className="dash-eyebrow mb-2 mt-5">Evidence</p>
            {detail.loading ? (
              <Skeleton className="h-24" />
            ) : detail.data?.evidence ? (
              <div className="space-y-2">
                {(["drawing", "rfi", "code_ref"] as const).map((k) =>
                  detail.data?.evidence?.[k] ? (
                    <div key={k} className="card p-3">
                      <p className="dash-eyebrow mb-1.5">{k.replace("_", " ")}</p>
                      <dl className="grid grid-cols-[110px_1fr] gap-x-2 gap-y-1 text-[12px]">
                        {Object.entries(detail.data.evidence[k]!).filter(([, v]) => v != null && typeof v !== "object").slice(0, 8).map(([kk, v]) => (
                          <div key={kk} className="contents">
                            <dt className="text-ink-3">{kk}</dt>
                            <dd className="break-words text-ink">{String(v)}</dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  ) : null,
                )}
              </div>
            ) : (
              <p className="text-[12.5px] text-ink-3">No linked evidence.</p>
            )}
          </div>
        ) : null}
      </Sheet>
    </div>
  );
}

// ------------------------------------------------------------------ drawings
type Sheetish = { number: string; title: string; discipline: string; level: string | null; revs: Drawing[]; latest: Drawing };

export function Drawings() {
  const site = useSiteRecord();
  const [sel, setSel] = useState<Sheetish | null>(null);
  const sheets = useMemo<Sheetish[] | null>(() => {
    if (!site.data) return null;
    const m = new Map<string, Drawing[]>();
    site.data.drawings.forEach((d) => m.set(d.drawing_number, [...(m.get(d.drawing_number) ?? []), d]));
    return [...m.entries()].map(([number, revs]) => {
      const sorted = [...revs].sort((a, b) => a.rev_ordinal - b.rev_ordinal);
      const latest = sorted.find((r) => r.is_latest) ?? sorted[sorted.length - 1];
      return { number, title: latest.title, discipline: latest.discipline, level: latest.level, revs: sorted, latest };
    });
  }, [site.data]);

  const chain = (s: Sheetish) => (
    <span className="flex flex-wrap items-center gap-1">
      {s.revs.map((r, i) => (
        <span key={r.drawing_id} className="inline-flex items-center gap-1">
          {i > 0 ? <Icon name="chevronRight" size={10} className="text-ink-3" /> : null}
          <span
            className={`rounded-md px-1.5 py-0.5 font-mono text-[11px] ${r.is_latest ? "font-semibold" : "text-ink-3 line-through"}`}
            style={r.is_latest ? { color: r.status === "For Construction" ? "var(--ok)" : "var(--warn)", background: `color-mix(in oklab, ${r.status === "For Construction" ? "var(--ok)" : "var(--warn)"} 12%, transparent)` } : undefined}
            title={`${r.revision} · ${r.status} · ${r.issued_on}`}
          >
            {r.revision}
          </span>
        </span>
      ))}
    </span>
  );

  return (
    <div>
      <PageHeader eyebrow="Site record" title="Drawings" description="Revision chains per sheet. The latest For-Construction revision is the only one Vesper will check a claim against; superseded revisions are struck through." />
      <RecordError error={site.error} reload={site.reload} />
      <DataTable
        rows={sheets}
        loading={site.loading && !site.data}
        rowKey={(s) => s.number}
        activeKey={sel?.number}
        onRowClick={setSel}
        searchText={(s) => `${s.number} ${s.title} ${s.discipline} ${s.level ?? ""} ${s.revs.map((r) => r.revision).join(" ")}`}
        facet={{ label: "Discipline", get: (s) => s.discipline }}
        initialSort={{ key: "number", dir: "asc" }}
        columns={[
          { key: "number", header: "Sheet", cell: (s) => <Mono className="font-medium text-ink">{s.number}</Mono>, sort: (s) => s.number, width: 90 },
          { key: "title", header: "Title", cell: (s) => <span className="line-clamp-1">{s.title}</span>, sort: (s) => s.title },
          { key: "chain", header: "Revisions", cell: chain },
          { key: "status", header: "Current", cell: (s) => <Badge tone={statusTone(s.latest.status)} dot>{s.latest.status}</Badge>, sort: (s) => s.latest.status },
          { key: "disc", header: "Discipline", cell: (s) => <span className="text-ink-2">{s.discipline}</span>, sort: (s) => s.discipline, hideBelow: "lg" },
          { key: "issued", header: "Issued", cell: (s) => <span className="text-ink-3">{fmtDate(s.latest.issued_on)}</span>, sort: (s) => s.latest.issued_on, hideBelow: "md" },
        ]}
      />
      <Sheet open={!!sel} onClose={() => setSel(null)} title={sel ? `${sel.number} · ${sel.title}` : ""} subtitle={sel ? `${sel.discipline}${sel.level ? ` · ${sel.level}` : ""}` : null}>
        {sel ? (
          <ol className="relative space-y-4">
            <span className="absolute bottom-3 left-[11px] top-3 w-px bg-line" />
            {[...sel.revs].reverse().map((r) => (
              <li key={r.drawing_id} className="relative flex gap-3">
                <span className="relative z-[1] mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border border-line bg-surface font-mono text-[10px]" style={r.is_latest ? { color: "var(--ok)", borderColor: "var(--ok)" } : { color: "var(--text-3)" }}>
                  {r.revision.replace("R", "")}
                </span>
                <div className={`card flex-1 p-3 ${r.is_latest ? "" : "opacity-70"}`}>
                  <div className="flex flex-wrap items-center gap-2">
                    <Mono className={`font-semibold ${r.is_latest ? "" : "line-through"}`}>{r.drawing_id}</Mono>
                    <Badge tone={statusTone(r.status)} dot>{r.status}</Badge>
                    {r.is_latest ? <Badge tone="accent">latest</Badge> : null}
                    <span className="ml-auto text-[11.5px] text-ink-3">{fmtDate(r.issued_on)}</span>
                  </div>
                  {r.change_note ? <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-2">{r.change_note}</p> : null}
                  {r.superseded_by ? <p className="mt-1 text-[11.5px] text-ink-3">superseded by <Mono>{r.superseded_by}</Mono></p> : null}
                </div>
              </li>
            ))}
          </ol>
        ) : null}
      </Sheet>
    </div>
  );
}

// ------------------------------------------------------------------ RFIs
export function Rfis() {
  const site = useSiteRecord();
  const [sel, setSel] = useState<Rfi | null>(null);
  return (
    <div>
      <PageHeader eyebrow="Site record" title="RFIs" description="Requests for information and the revisions they produced. Open RFIs are surfaced by Vesper whenever you work at the affected location." />
      <RecordError error={site.error} reload={site.reload} />
      <DataTable
        rows={site.data?.rfis ?? null}
        loading={site.loading && !site.data}
        rowKey={(r) => r.rfi_id}
        activeKey={sel?.rfi_id}
        onRowClick={setSel}
        searchText={(r) => `${r.rfi_id} ${r.subject} ${r.location_id ?? ""} ${r.drawing_ref ?? ""} ${r.spec_ref ?? ""} ${r.status}`}
        facet={{ label: "Status", get: (r) => r.status }}
        initialSort={{ key: "raised", dir: "desc" }}
        columns={[
          { key: "id", header: "RFI", cell: (r) => <Mono className="font-medium">{r.rfi_id}</Mono>, sort: (r) => r.rfi_id, width: 96 },
          { key: "subject", header: "Subject", cell: (r) => <span className="line-clamp-1">{r.subject}</span>, sort: (r) => r.subject },
          { key: "loc", header: "Location", cell: (r) => <Mono className="text-ink-2">{loc(r.location_id)}</Mono>, hideBelow: "lg" },
          { key: "dwg", header: "Drawing", cell: (r) => <Mono className="text-ink-2">{r.drawing_ref ?? "—"}</Mono>, sort: (r) => r.drawing_ref ?? "", hideBelow: "md" },
          { key: "status", header: "Status", cell: (r) => <Badge tone={statusTone(r.status)} dot>{r.status}</Badge>, sort: (r) => r.status },
          { key: "raised", header: "Raised", cell: (r) => <span className="text-ink-3">{fmtDate(r.raised_on)}</span>, sort: (r) => r.raised_on ?? "", hideBelow: "md" },
        ]}
      />
      <Sheet open={!!sel} onClose={() => setSel(null)} title={sel ? `${sel.rfi_id} · ${sel.subject}` : ""} subtitle={sel ? <Badge tone={statusTone(sel.status)} dot>{sel.status}</Badge> : null}>
        {sel ? (
          <div className="space-y-4">
            <div className="card p-3.5">
              <p className="dash-eyebrow mb-1.5">Question</p>
              <p className="text-[13px] leading-relaxed text-ink">{sel.question ?? "—"}</p>
            </div>
            <div className="card p-3.5" style={sel.response ? { borderColor: "color-mix(in oklab, var(--ok) 30%, var(--border))" } : undefined}>
              <p className="dash-eyebrow mb-1.5">Response</p>
              <p className="text-[13px] leading-relaxed text-ink">{sel.response ?? <span className="text-ink-3">Awaiting response</span>}</p>
            </div>
            <dl className="divide-y divide-line">
              <Field label="Location"><Mono>{loc(sel.location_id)}</Mono></Field>
              <Field label="Drawing">{sel.drawing_ref ?? "—"}</Field>
              <Field label="Spec / code">{sel.spec_ref ?? "—"}</Field>
              <Field label="Impact">{sel.impact ?? "—"}</Field>
              <Field label="Resulting rev.">{sel.resulting_drawing_id ?? "—"}</Field>
              <Field label="Raised">{fmtDate(sel.raised_on)}</Field>
              <Field label="Answered">{fmtDate(sel.answered_on)}</Field>
              <Field label="Template">{sel.template_id ?? "—"}</Field>
            </dl>
          </div>
        ) : null}
      </Sheet>
    </div>
  );
}

// ------------------------------------------------------------------ permits & hold points
const HOLDS = ((DEMO_LIVE.brief as { open_hold_points?: HoldPoint[] }).open_hold_points ?? []) as HoldPoint[];

export function Permits() {
  const site = useSiteRecord();
  const [sel, setSel] = useState<Permit | null>(null);
  return (
    <div>
      <PageHeader eyebrow="Site record" title="Permits" accent="& hold points" description="Work is blocked while a permit has an unmet mandatory check or a hold point is unreleased — the voice agent will only offer stop work, NCR or cancel." />
      <RecordError error={site.error} reload={site.reload} />

      <Panel title="Open hold points" icon="lock" className="mb-5" action={<span className="text-[11.5px] text-ink-3">from the latest site brief</span>}>
        {HOLDS.length === 0 ? (
          <Empty icon="check" title="No open hold points" />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {HOLDS.map((h) => (
              <div key={h.instance_id} className="rounded-xl border p-3.5" style={{ borderColor: "color-mix(in oklab, var(--danger) 28%, transparent)", background: "color-mix(in oklab, var(--danger) 5%, transparent)" }}>
                <div className="flex flex-wrap items-center gap-2">
                  <Mono className="font-semibold">{h.instance_id}</Mono>
                  <Badge tone="danger" dot>{h.status ?? "Hold"}</Badge>
                  <span className="ml-auto text-[11.5px] text-ink-3">planned {fmtDate(h.planned_for)}</span>
                </div>
                <p className="mt-1 text-[12.5px] text-ink-2">
                  {humanize(h.planned_activity)} · {h.element} · <Mono>{loc(h.location_id)}</Mono>
                </p>
                {h.notes ? <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink">{h.notes}</p> : null}
              </div>
            ))}
          </div>
        )}
      </Panel>

      <DataTable
        rows={site.data?.permits ?? null}
        loading={site.loading && !site.data}
        rowKey={(p) => p.permit_id}
        activeKey={sel?.permit_id}
        onRowClick={setSel}
        searchText={(p) => `${p.permit_id} ${p.permit_type} ${p.location_id ?? ""} ${p.status} ${p.issued_by ?? ""}`}
        facet={{ label: "Status", get: (p) => p.status }}
        initialSort={{ key: "status", dir: "asc" }}
        columns={[
          { key: "id", header: "Permit", cell: (p) => <Mono className="font-medium">{p.permit_id}</Mono>, sort: (p) => p.permit_id, width: 100 },
          { key: "type", header: "Type", cell: (p) => <span>{humanize(p.permit_type)}</span>, sort: (p) => p.permit_type },
          { key: "loc", header: "Location", cell: (p) => <Mono className="text-ink-2">{loc(p.location_id)}</Mono>, hideBelow: "md" },
          {
            key: "checks",
            header: "Mandatory checks",
            sort: (p) => unsatisfied(p).length,
            cell: (p) => {
              const mand = p.checks.filter((c) => c.is_mandatory);
              const ok = mand.length - unsatisfied(p).length;
              const bad = ok < mand.length;
              return (
                <span className="flex items-center gap-2">
                  <span className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-2">
                    <span className="block h-full rounded-full" style={{ width: `${mand.length ? (ok / mand.length) * 100 : 100}%`, background: bad ? "var(--danger)" : "var(--ok)" }} />
                  </span>
                  <span className={`tabular-nums text-[12px] ${bad ? "text-danger" : "text-ink-2"}`}>
                    {ok}/{mand.length}
                  </span>
                </span>
              );
            },
          },
          { key: "status", header: "Status", cell: (p) => <Badge tone={p.status === "Active" && unsatisfied(p).length ? "danger" : statusTone(p.status)} dot>{p.status === "Active" && unsatisfied(p).length ? "Blocked" : p.status}</Badge>, sort: (p) => p.status },
          { key: "valid", header: "Valid", cell: (p) => <span className="text-ink-3">{fmtDate(p.valid_from, true)} – {p.valid_to ? new Date(p.valid_to).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "—"}</span>, hideBelow: "lg" },
        ]}
      />
      <Sheet open={!!sel} onClose={() => setSel(null)} title={sel ? `${sel.permit_id} · ${humanize(sel.permit_type)}` : ""} subtitle={sel ? `${loc(sel.location_id)} · issued by ${sel.issued_by ?? "—"}` : null}>
        {sel ? (
          <div>
            <dl className="mb-4 divide-y divide-line">
              <Field label="Status"><Badge tone={statusTone(sel.status)} dot>{sel.status}</Badge></Field>
              <Field label="Valid from">{fmtDate(sel.valid_from, true)}</Field>
              <Field label="Valid to">{fmtDate(sel.valid_to, true)}</Field>
              <Field label="Template">{sel.template_id ?? "—"}</Field>
            </dl>
            <p className="dash-eyebrow mb-2">Checks</p>
            <ul className="space-y-1.5">
              {sel.checks.map((c) => (
                <li key={c.field_id} className="flex items-start gap-2.5 rounded-lg border border-line p-2.5">
                  <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full" style={{ background: c.satisfied ? "var(--ok)" : c.is_mandatory ? "var(--danger)" : "var(--text-3)", color: "#fff" }}>
                    <Icon name={c.satisfied ? "check" : "x"} size={10} strokeWidth={3} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[12.5px] leading-snug text-ink">{c.label}</p>
                    <p className="mt-0.5 text-[11px] text-ink-3">
                      {c.is_mandatory ? "mandatory" : "optional"}
                      {c.confirmed_by ? ` · ${c.confirmed_by}` : ""}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </Sheet>
    </div>
  );
}
