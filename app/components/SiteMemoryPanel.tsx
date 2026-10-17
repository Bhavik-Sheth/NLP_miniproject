"use client";

import { useState } from "react";
import { Card, Chip } from "@/components/ui";

function slotText(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "object") {
    const o = v as Record<string, unknown>;
    if ("value" in o) return slotText(o.value);
    return JSON.stringify(o);
  }
  return String(v);
}

// ---- site brief / memory data-message shape (topic "vesper") ----
type BriefProject = {
  name?: string;
  client?: string;
  location?: string;
  contract_type?: string;
  start_date?: string;
};
type BriefDailyLog = { log_date?: string; weather?: string; work_done?: string; safety?: string };
type BriefObservation = {
  observation_id?: string;
  on_date?: string;
  location_id?: string;
  element?: string;
  attribute?: string;
  value_claimed?: unknown;
  unit?: string;
  drawing_id?: string;
  final_decision?: string;
};
type BriefRfi = {
  rfi_id?: string;
  subject?: string;
  location_id?: string;
  drawing_ref?: string;
  status?: string;
  impact?: string;
};
type BriefPermit = {
  permit_id?: string;
  permit_type?: string;
  location_id?: string;
  status?: string;
  unsatisfied_mandatory_checks?: string[];
};
type BriefHoldPoint = {
  instance_id?: string;
  template_id?: string;
  location_id?: string;
  element?: string;
  planned_activity?: string;
  planned_for?: string;
  status?: string;
  notes?: string;
};
type BriefSubmittal = { submittal_id?: string; material?: string; status?: string; comments?: string };
type BriefDrawing = { drawing_number?: string; revision?: string; issued_on?: string; title?: string };

export type SiteBrief = {
  project?: BriefProject;
  today_is?: string;
  recent_daily_logs?: BriefDailyLog[];
  recent_observations?: BriefObservation[];
  open_rfis?: BriefRfi[];
  active_permits?: BriefPermit[];
  open_hold_points?: BriefHoldPoint[];
  pending_submittals?: BriefSubmittal[];
  current_drawings?: BriefDrawing[];
};

function truncate(s: string | undefined, n: number): string {
  if (!s) return "";
  return s.length > n ? `${s.slice(0, n).trimEnd()}…` : s;
}

export default function SiteMemoryPanel({ brief }: { brief: SiteBrief | null }) {
  const [open, setOpen] = useState(false);
  const [logsExpanded, setLogsExpanded] = useState<Record<number, boolean>>({});

  if (!brief) return null;

  const project = brief.project ?? {};
  const holdPoints = brief.open_hold_points ?? [];
  const permitsBlocked = (brief.active_permits ?? []).filter(
    (p) => (p.unsatisfied_mandatory_checks ?? []).length > 0
  );
  const openRfis = (brief.open_rfis ?? []).filter(
    (r) => (r.status ?? "").toLowerCase() === "open"
  );
  const dailyLogs = brief.recent_daily_logs ?? [];
  const observations = brief.recent_observations ?? [];
  const drawings = brief.current_drawings ?? [];
  const submittals = brief.pending_submittals ?? [];

  const attentionCount = holdPoints.length + permitsBlocked.length + openRfis.length;

  const summaryParts = [
    openRfis.length ? `${openRfis.length} open RFI${openRfis.length === 1 ? "" : "s"}` : null,
    holdPoints.length
      ? `${holdPoints.length} hold point${holdPoints.length === 1 ? "" : "s"}`
      : null,
    permitsBlocked.length
      ? `${permitsBlocked.length} permit${permitsBlocked.length === 1 ? "" : "s"} blocked`
      : null,
  ].filter(Boolean);

  return (
    <div className="flex flex-col gap-2">
      {/* Always-visible summary strip */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="glass-panel px-3 py-2 flex items-center justify-between gap-2 text-left w-full"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className={`p-live-dot ${attentionCount ? "dot-amber" : ""}`} />
          <span className="text-xs text-zinc-300 truncate">
            {summaryParts.length ? (
              summaryParts.join(" · ")
            ) : (
              <span className="text-zinc-500">Site memory loaded</span>
            )}
          </span>
        </div>
        <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 shrink-0">
          {open ? "Hide" : "Site memory"}
        </span>
      </button>

      {open ? (
        <Card title="Site Memory">
          <div className="flex flex-col gap-3">
            {/* Header line */}
            <div>
              <p className="text-sm font-medium text-white">
                {project.name ?? "Project"}
              </p>
              {brief.today_is ? (
                <p className="text-[10.5px] font-mono text-zinc-500">
                  as of {brief.today_is}
                </p>
              ) : null}
            </div>

            {/* Needs attention */}
            {attentionCount ? (
              <div className="flex flex-col gap-1.5">
                <p className="text-[10.5px] font-mono uppercase tracking-wider text-amber-300/80">
                  Needs attention
                </p>
                <div className="flex flex-col gap-1.5">
                  {holdPoints.map((h, i) => (
                    <div
                      key={`hp-${i}`}
                      className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5"
                    >
                      <p className="text-xs text-amber-100 font-mono">
                        {h.instance_id ?? "hold point"} · {h.location_id ?? "—"} ·{" "}
                        {h.planned_activity ?? "—"} planned {h.planned_for ?? "—"}
                      </p>
                      {h.notes ? (
                        <p className="text-[11px] text-amber-200/80 mt-0.5">{h.notes}</p>
                      ) : null}
                    </div>
                  ))}
                  {permitsBlocked.map((p, i) => (
                    <div
                      key={`pm-${i}`}
                      className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5"
                    >
                      <p className="text-xs text-amber-100 font-mono">
                        {p.permit_id ?? "permit"} ({p.permit_type ?? "—"}) at{" "}
                        {p.location_id ?? "—"}
                      </p>
                      <p className="text-[11px] text-amber-200/80 mt-0.5">
                        {(p.unsatisfied_mandatory_checks ?? []).join(" · ")}
                      </p>
                    </div>
                  ))}
                  {openRfis.map((r, i) => (
                    <div
                      key={`rfi-${i}`}
                      className="rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5"
                    >
                      <p className="text-xs text-zinc-200 font-mono">
                        {r.rfi_id ?? "RFI"} — {r.subject ?? "—"}
                      </p>
                      {r.impact ? (
                        <p className="text-[11px] text-zinc-400 mt-0.5">{r.impact}</p>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {/* Recent work */}
            {dailyLogs.length ? (
              <div className="flex flex-col gap-1.5">
                <p className="text-[10.5px] font-mono uppercase tracking-wider text-zinc-500">
                  Recent work
                </p>
                <div className="flex flex-col gap-1">
                  {dailyLogs.map((l, i) => {
                    const expanded = !!logsExpanded[i];
                    const full = l.work_done ?? "";
                    const isLong = full.length > 160;
                    return (
                      <div key={`log-${i}`} className="text-xs">
                        <span className="text-zinc-500 font-mono">{l.log_date ?? "—"}</span>{" "}
                        <span className="text-zinc-300">
                          {expanded ? full : truncate(full, 160)}
                        </span>
                        {isLong ? (
                          <button
                            type="button"
                            onClick={() =>
                              setLogsExpanded((s) => ({ ...s, [i]: !s[i] }))
                            }
                            className="ml-1 text-[10.5px] text-zinc-500 underline underline-offset-2"
                          >
                            {expanded ? "less" : "more"}
                          </button>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}

            {/* Last logged observations */}
            {observations.length ? (
              <div className="flex flex-col gap-1.5">
                <p className="text-[10.5px] font-mono uppercase tracking-wider text-zinc-500">
                  Last logged observations
                </p>
                <div className="flex flex-col gap-1">
                  {observations.map((o, i) => (
                    <p key={`obs-${i}`} className="text-xs text-zinc-300">
                      {o.location_id ?? "—"} {o.element ?? ""} {o.attribute ?? ""}{" "}
                      {slotText(o.value_claimed)}
                      {o.unit ?? ""} → {o.drawing_id ?? "—"}{" "}
                      <span className="text-zinc-500 font-mono">
                        ({o.observation_id ?? "—"}
                        {o.on_date ? `, ${o.on_date}` : ""})
                      </span>
                    </p>
                  ))}
                </div>
              </div>
            ) : null}

            {/* Current drawings */}
            {drawings.length ? (
              <div className="flex flex-col gap-1.5">
                <p className="text-[10.5px] font-mono uppercase tracking-wider text-zinc-500">
                  Current drawings
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {drawings.map((d, i) => (
                    <Chip
                      key={`dwg-${i}`}
                      label={`${d.drawing_number ?? "—"} ${d.revision ?? ""}`.trim()}
                    />
                  ))}
                </div>
              </div>
            ) : null}

            {/* Pending submittals */}
            {submittals.length ? (
              <div className="flex flex-col gap-1.5">
                <p className="text-[10.5px] font-mono uppercase tracking-wider text-zinc-500">
                  Pending submittals
                </p>
                <div className="flex flex-col gap-0.5">
                  {submittals.map((s, i) => (
                    <p key={`sub-${i}`} className="text-xs text-zinc-300">
                      {s.material ?? "—"}{" "}
                      <span className="text-zinc-500">
                        ({s.status ?? "—"}
                        {s.comments ? ` — ${s.comments}` : ""})
                      </span>
                    </p>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </Card>
      ) : null}
    </div>
  );
}
