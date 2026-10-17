"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type ObservationDetail,
  type ObservationRow,
} from "@/lib/api";
import { Card, ErrorBanner, Button, Chip } from "@/components/ui";

export default function ObservationsScreen() {
  const [rows, setRows] = useState<ObservationRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ObservationDetail | null>(null);
  const [detailErr, setDetailErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setRows(await api.observations());
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    // LiveKit decisions are written by the room worker, outside this component's
    // React state. Poll lightly while Logs is open so the audit trail reflects
    // a just-logged NCR or observation without requiring a page refresh.
    const refresh = window.setInterval(() => void load(), 8_000);
    return () => window.clearInterval(refresh);
  }, [load]);

  const openDetail = async (id: string) => {
    if (openId === id) {
      setOpenId(null);
      setDetail(null);
      return;
    }
    setOpenId(id);
    setDetail(null);
    setDetailErr(null);
    try {
      setDetail(await api.observation(id));
    } catch (e) {
      setDetailErr((e as Error).message);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between px-1">
        <div>
          <span className="text-[10px] font-mono tracking-wider uppercase text-zinc-400">
            Audit Trail & History
          </span>
          <h2 className="text-lg font-medium text-white tracking-tight">
            Site <span className="editorial-em">Observations</span>
          </h2>
        </div>
        <Button variant="ghost" size="sm" onClick={load} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      <ErrorBanner msg={err} />

      {loading && !rows ? (
        <div className="glass-panel p-6 text-center text-xs text-zinc-400 flex items-center justify-center gap-2">
          <svg className="animate-spin h-3.5 w-3.5 text-zinc-300" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <span>Fetching site log entries…</span>
        </div>
      ) : null}

      {rows && rows.length === 0 ? (
        <div className="glass-panel p-8 text-center text-xs text-zinc-500">
          No observations recorded in this session yet.
        </div>
      ) : null}

      <div className="space-y-2.5">
        {rows?.map((r, i) => {
          const isOpen = openId === r.observation_id;
          return (
            <div key={r.observation_id} id={i === 0 ? "tour-logs" : undefined} className="flex flex-col gap-1.5">
              <div
                onClick={() => openDetail(r.observation_id)}
                className="cursor-pointer"
              >
                <Card
                  tone={r.contradiction_flag ? "red" : "neutral"}
                  hoverable={true}
                  className="transition-all"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-mono text-xs font-semibold text-white tracking-tight">
                          {r.location_id}
                        </span>
                        <span className="text-zinc-500 text-[11px]">·</span>
                        <span className="text-xs text-zinc-300 font-medium truncate">
                          {r.element} {r.attribute}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
                        <span className="font-mono text-white/90 font-medium">
                          {String(r.value_claimed)}
                          {r.unit ? ` ${r.unit}` : ""}
                        </span>
                        <span className="text-zinc-600">|</span>
                        <span className="font-mono text-[11px] text-zinc-400">
                          {r.drawing_id}
                        </span>
                      </div>

                      <div className="mt-2 flex items-center gap-2">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider bg-white/5 border border-white/10 text-zinc-300">
                          {r.final_decision}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {r.contradiction_flag ? (
                        <span className="flex items-center gap-1 text-[10px] font-mono text-red-300 bg-red-950/70 border border-red-500/50 px-1.5 py-0.5 rounded">
                          <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
                          CONFLICT
                        </span>
                      ) : null}
                      <svg
                        className={`w-4 h-4 text-zinc-500 transition-transform ${
                          isOpen ? "rotate-180 text-white" : ""
                        }`}
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                      >
                        <polyline points="6 9 12 15 18 9" />
                      </svg>
                    </div>
                  </div>
                </Card>
              </div>

              {/* Accordion Detail Drawer */}
              {isOpen ? (
                <div className="pl-2 border-l border-white/10 ml-2">
                  <ErrorBanner msg={detailErr} />
                  {!detail && !detailErr ? (
                    <div className="glass-panel p-3 text-center text-xs text-zinc-400">
                      Loading verification evidence…
                    </div>
                  ) : null}
                  {detail ? (
                    <Card title="Observation Evidence · Audit Details">
                      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs font-mono">
                        <dt className="text-zinc-500">Drawing Rev:</dt>
                        <dd className="text-zinc-200">
                          {String(
                            detail.revision_claimed ??
                              (detail.evidence?.drawing as Record<string, unknown>)
                                ?.revision ??
                              "—",
                          )}
                        </dd>
                        <dt className="text-zinc-500">Linked RFI:</dt>
                        <dd className="text-zinc-200">{detail.linked_rfi_id ?? "—"}</dd>
                        <dt className="text-zinc-500">Conflicts:</dt>
                        <dd className="text-red-300">
                          {detail.contradiction_kinds?.length
                            ? detail.contradiction_kinds.join(", ")
                            : "None"}
                        </dd>
                        <dt className="text-zinc-500">Clarification:</dt>
                        <dd className="text-zinc-200">
                          {String(
                            detail.clarification_asked ??
                              detail.clarified ??
                              "—",
                          )}
                        </dd>
                      </dl>

                      <details className="mt-3 pt-2 border-t border-white/10">
                        <summary className="cursor-pointer text-[10.5px] font-mono text-zinc-400 hover:text-white">
                          View Raw Record Payload
                        </summary>
                        <pre className="mt-2 overflow-x-auto rounded-lg bg-black/60 p-2.5 text-[10.5px] font-mono text-zinc-300 border border-white/10">
                          {JSON.stringify(detail, null, 2)}
                        </pre>
                      </details>
                    </Card>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
