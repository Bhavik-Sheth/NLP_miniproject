"use client";

import Link from "next/link";
import { useMemo } from "react";
import { apiV2 } from "@/lib/api-v2";
import { DEMO_LIVE } from "@/lib/demo";
import { useDash } from "../context";
import { Icon } from "../icons";
import { Badge, Empty, Kpi, Notice, PageHeader, Panel, Skeleton, fmtDate, relTime, useAsync } from "../primitives";
import { deriveActivity, deriveBlockers, isToday, useSiteRecord, type HoldPoint } from "../siteData";

const SNAPSHOT_HOLDS = ((DEMO_LIVE.brief as { open_hold_points?: HoldPoint[] }).open_hold_points ?? []) as HoldPoint[];
const BRIEF_PROJECT = (DEMO_LIVE.brief as { project?: Record<string, string> }).project ?? {};

export default function Overview() {
  const { project, memoryLive, health } = useDash();
  const site = useSiteRecord();
  const ov = useAsync(() => apiV2.overview(project.id), [project.id]);
  const stats = useAsync(() => apiV2.stats(project.id), [project.id]);
  const rec = site.data;
  const isP1 = project.id === "P1";

  const counts = useMemo(() => {
    if (ov.data) return ov.data.counts;
    if (!rec) return null;
    return {
      drawings: rec.drawings.filter((d) => d.is_latest).length,
      rfisOpen: rec.rfis.filter((r) => r.status === "Open").length,
      permitsActive: rec.permits.filter((p) => p.status === "Active").length,
      holdPoints: SNAPSHOT_HOLDS.length,
      observations: rec.observations.length,
      documents: stats.data?.corpora.reduce((a, c) => a + c.documents, 0) ?? 0,
      chunks: stats.data?.corpora.reduce((a, c) => a + c.chunks, 0) ?? 0,
    };
  }, [ov.data, rec, stats.data]);

  const obsToday = rec?.observations.filter((o) => isToday(o.created_at)).length ?? 0;
  const blockers = useMemo(() => (rec ? deriveBlockers(rec, isP1 ? SNAPSHOT_HOLDS : []) : []), [rec, isP1]);
  const activity = useMemo(() => {
    // W2's overview returns {kind, id, summary, actor, createdAt}; normalise to the timeline shape.
    const live = (ov.data?.recent ?? []).map((r) => {
      const x = r as unknown as Record<string, unknown>;
      const actor = String(x.actor ?? "");
      return {
        kind: String(x.kind ?? "activity"),
        id: x.id as string | undefined,
        title: String(x.title ?? (x.id ? `${x.id}${actor ? ` · ${actor.replace(/_/g, " ")}` : ""}` : x.kind ?? "Activity")),
        detail: (x.detail ?? x.summary) as string | undefined,
        at: String(x.at ?? x.createdAt ?? ""),
        tone: (x.tone as "ok" | "warn" | "danger" | "info" | undefined) ?? (actor === "log_observation" ? "ok" : actor === "raise_rfi" ? "warn" : /stop|ncr/.test(actor) ? "danger" : "info"),
      };
    });
    return (live.length ? live : rec ? deriveActivity(rec) : []).slice(0, 9);
  }, [ov.data, rec]);
  const loading = site.loading && !ov.data;
  const memDocs = stats.data?.corpora.reduce((a, c) => a + c.documents, 0);
  const memChunks = stats.data?.corpora.reduce((a, c) => a + c.chunks, 0);

  return (
    <div>
      <PageHeader eyebrow={`${project.code ?? project.id} · Overview`} title="Good to see you." accent="Here’s the site." />

      {/* project header */}
      <section className="glass dash-rise relative mb-5 overflow-hidden p-5 sm:p-6">
        <div className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full opacity-70 blur-3xl" style={{ background: "radial-gradient(circle, color-mix(in oklab, var(--accent) 30%, transparent), transparent 70%)" }} />
        <div className="relative flex flex-wrap items-start gap-5">
          <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl border border-line bg-surface text-accent shadow-[var(--shadow-sm)]">
            <Icon name="building" size={22} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-[19px] font-semibold tracking-[-0.02em] text-ink">{project.name}</h2>
              <Badge tone="ok" dot>{project.status ?? "Active"}</Badge>
              {isP1 ? <Badge>Demo project · read-only</Badge> : null}
            </div>
            <p className="mt-1 text-[13px] text-ink-2">
              {[isP1 ? BRIEF_PROJECT.client : null, project.city, isP1 ? BRIEF_PROJECT.contract_type : project.type].filter(Boolean).join(" · ")}
            </p>
            <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[12px] text-ink-3">
              {isP1 && BRIEF_PROJECT.start_date ? <span>Started {fmtDate(BRIEF_PROJECT.start_date)}</span> : null}
              <span>{counts ? `${counts.drawings} current drawings` : "…"}</span>
              <span>Engine {health ? `online · LLM ${health.llm}` : "checking…"}</span>
            </div>
          </div>
          <div className="flex w-full flex-wrap gap-2 sm:w-auto">
            <Link href="/app/ask" className="dash-btn">
              <Icon name="sparkles" size={14} /> Ask memory
            </Link>
            <Link href="/app/live" className="dash-btn dash-btn-primary">
              <Icon name="mic" size={14} /> Start voice session
            </Link>
          </div>
        </div>
      </section>

      {site.error && !ov.data ? (
        <div className="mb-5">
          <Notice tone="danger" title="Could not reach the site record">
            <span className="font-mono text-[11.5px]">{site.error}</span>
          </Notice>
        </div>
      ) : null}

      <div id="tour-dash-kpis" className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <Kpi delay={0} label="Open RFIs" icon="help" tone="warn" loading={loading} value={counts?.rfisOpen ?? "—"} sub={rec ? `${rec.rfis.length} total` : null} href="/app/rfis" />
        <Kpi delay={40} label="Active permits" icon="shield" tone="ok" loading={loading} value={counts?.permitsActive ?? "—"} sub={blockers.filter((b) => b.kind === "permit").length ? `${blockers.filter((b) => b.kind === "permit").length} need attention` : "all checks met"} href="/app/permits" />
        <Kpi delay={80} label="Open hold points" icon="lock" tone="danger" loading={loading} value={counts?.holdPoints ?? "—"} sub={ov.data ? "live" : "from last site brief"} href="/app/permits" />
        <Kpi delay={120} label="Observations today" icon="eye" loading={loading} value={obsToday} sub={rec ? `${rec.observations.length} logged in total` : null} href="/app/observations" />
        <Kpi
          delay={160}
          label="Memory"
          icon="brain"
          tone="accent"
          loading={stats.loading && !ov.data}
          value={memChunks != null ? memChunks.toLocaleString() : counts?.chunks ? counts.chunks.toLocaleString() : "—"}
          sub={memDocs != null ? `chunks · ${memDocs} documents` : memoryLive ? "chunks" : "memory layer offline"}
          href="/app/memory"
        />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.25fr_1fr]">
        <Panel
          id="tour-dash-blockers"
          title="Blockers"
          icon="alert"
          action={blockers.length ? <Badge tone="danger">{blockers.length}</Badge> : null}
          bodyClassName="p-2"
        >
          {loading ? (
            <div className="space-y-2 p-2">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : blockers.length === 0 ? (
            <Empty icon="check" title="No blockers" body="Every active permit has its mandatory checks and no hold point is waiting for release." />
          ) : (
            <ul className="space-y-1">
              {blockers.map((b, i) => (
                <li key={b.id} className="dash-row-in" style={{ animationDelay: `${i * 50}ms` }}>
                  <Link href={b.href} className="group flex items-start gap-3 rounded-xl px-3 py-2.5 transition hover:bg-[color-mix(in_oklab,var(--text)_4%,transparent)]">
                    <span
                      className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg"
                      style={{ color: `var(--${b.tone})`, background: `color-mix(in oklab, var(--${b.tone}) 12%, transparent)` }}
                    >
                      <Icon name={b.kind === "hold" ? "lock" : "shield"} size={14} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[13px] font-medium capitalize text-ink">{b.title}</span>
                        <Badge tone={b.tone}>{b.kind === "hold" ? "Hold point" : "Permit"}</Badge>
                        {b.location ? <span className="font-mono text-[11px] text-ink-3">{b.location.replace(/^P1:/, "")}</span> : null}
                      </div>
                      <p className="mt-0.5 line-clamp-2 text-[12.5px] leading-relaxed text-ink-2">{b.detail}</p>
                    </div>
                    <Icon name="chevronRight" size={14} className="mt-1.5 text-ink-3 opacity-0 transition group-hover:opacity-100" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Recent activity" icon="clock" bodyClassName="px-4 py-3">
          {loading ? (
            <div className="space-y-3">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-9" />
              ))}
            </div>
          ) : activity.length === 0 ? (
            <Empty icon="clock" title="No activity yet" />
          ) : (
            <ol className="relative">
              <span className="absolute bottom-2 left-[5px] top-2 w-px bg-line" />
              {activity.map((a, i) => (
                <li key={`${a.kind}-${a.id}-${i}`} className="dash-row-in relative flex gap-3 pb-3.5 last:pb-0" style={{ animationDelay: `${i * 35}ms` }}>
                  <span
                    className="relative z-[1] mt-1.5 h-[11px] w-[11px] shrink-0 rounded-full border-2 border-surface"
                    style={{ background: a.tone === "info" || !a.tone ? "var(--accent)" : `var(--${a.tone})` }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <p className="truncate text-[12.5px] font-medium text-ink">{a.title}</p>
                      <span className="ml-auto shrink-0 text-[11px] tabular-nums text-ink-3">{relTime(a.at)}</span>
                    </div>
                    {a.detail ? <p className="truncate text-[12px] text-ink-3">{a.detail}</p> : null}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Panel>
      </div>

      {/* voice CTA */}
      <Link href="/app/live" className="glass card-hover group mt-5 flex flex-wrap items-center gap-5 p-5">
        <div className="relative grid h-14 w-14 place-items-center">
          <span className="dash-orb-core" style={{ inset: 0 }} />
          <Icon name="mic" size={20} className="relative text-white drop-shadow" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-semibold tracking-[-0.02em] text-ink">
            Walk the site with Vesper <span className="dash-serif font-normal text-ink-2">hands-free</span>
          </p>
          <p className="mt-0.5 text-[12.5px] text-ink-2">Speak observations; they are checked against the latest For-Construction revision before anything is written.</p>
        </div>
        <span className="dash-btn dash-btn-primary">
          Start session <Icon name="arrowRight" size={14} className="transition group-hover:translate-x-0.5" />
        </span>
      </Link>
    </div>
  );
}
