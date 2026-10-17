"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type ScenarioResult, type ScenarioRunResponse } from "@/lib/api";
import { Icon } from "../icons";
import { Badge, DataTable, Kpi, Notice, PageHeader, Sheet, useAsync } from "../primitives";

export default function Scenarios() {
  const meta = useAsync(() => api.scenarios(), []);
  const [run, setRun] = useState<ScenarioRunResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<ScenarioResult | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState<number | null>(null);

  const go = async () => {
    setRunning(true);
    setErr(null);
    setRun(null);
    const t0 = performance.now();
    setStartedAt(Date.now());
    try {
      setRun(await api.runScenarios());
      setElapsed(performance.now() - t0);
    } catch (e) {
      setErr(e instanceof ApiError && e.status === 501 ? "The scenario runner is not enabled on this backend." : (e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("run") === "1") void go();
  }, []);

  const rows = run
    ? run.results
    : (meta.data ?? []).map((m) => ({ id: m.id, title: m.title, pass: false, failures: [], kindsSeen: [], clarified: false, finalDecision: "", logged: [], transcript: [] }) as ScenarioResult);

  return (
    <div id="tour-dash-scenarios">
      <PageHeader
        eyebrow="Project"
        title="Scenarios"
        description="Scripted site conversations with deliberate errors, garbled fields and mid-sentence corrections. The bar is zero wrong logs, every run."
        actions={
          <button className="dash-btn dash-btn-primary" onClick={go} disabled={running}>
            {running ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <Icon name="play" size={12} />}
            {running ? "Running suite…" : run ? "Run again" : "Run suite"}
          </button>
        }
      />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Kpi label="Passed" icon="check" tone="ok" value={run ? `${run.passed}/${run.total}` : "—"} sub={run ? `${Math.round((run.passed / run.total) * 100)}%` : "run the suite"} />
        <Kpi label="Wrong logs" icon="alert" tone={run?.wrongLogs ? "danger" : "ok"} value={run ? run.wrongLogs : "—"} sub="must stay at zero" delay={40} />
        <Kpi label="Scenarios" icon="flask" value={meta.data?.length ?? "—"} loading={meta.loading} delay={80} />
        <Kpi label="Duration" icon="clock" value={elapsed != null ? `${(elapsed / 1000).toFixed(1)}s` : "—"} sub={startedAt ? new Date(startedAt).toLocaleTimeString() : null} delay={120} />
      </div>
      {err ? (
        <div className="mb-4">
          <Notice tone="danger" title="Suite failed">
            <span className="font-mono text-[11.5px]">{err}</span>
          </Notice>
        </div>
      ) : null}
      <DataTable
        rows={rows}
        loading={meta.loading && !run}
        rowKey={(r) => r.id}
        activeKey={sel?.id}
        onRowClick={run ? setSel : undefined}
        searchText={(r) => `${r.id} ${r.title} ${r.finalDecision}`}
        columns={[
          {
            key: "result",
            header: "",
            width: 44,
            cell: (r) => {
              const i = rows.indexOf(r);
              if (running) return <span className="dash-skel block h-5 w-5 rounded-full" style={{ animationDelay: `${i * 80}ms` }} />;
              if (!run) return <span className="block h-5 w-5 rounded-full border border-dashed border-line" />;
              return (
                <span className="dash-row-in grid h-5 w-5 place-items-center rounded-full text-white" style={{ background: r.pass ? "var(--ok)" : "var(--danger)", animationDelay: `${i * 90}ms` }}>
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" className="dash-check">
                    <path d={r.pass ? "M20 6 9 17l-5-5" : "M18 6 6 18M6 6l12 12"} style={{ animationDelay: `${i * 90 + 150}ms` }} />
                  </svg>
                </span>
              );
            },
          },
          { key: "id", header: "ID", cell: (r) => <span className="font-mono text-[12px]">{r.id}</span>, sort: (r) => r.id, width: 64 },
          { key: "title", header: "Scenario", cell: (r) => <span className="line-clamp-1">{r.title}</span> },
          { key: "kinds", header: "Caught", hideBelow: "lg", cell: (r) => <span className="flex flex-wrap gap-1">{r.kindsSeen.slice(0, 3).map((k) => <Badge key={k}>{k.replace(/_/g, " ")}</Badge>)}</span> },
          { key: "decision", header: "Final decision", hideBelow: "md", cell: (r) => (r.finalDecision ? <span className="font-mono text-[12px] text-ink-2">{r.finalDecision}</span> : <span className="text-ink-3">—</span>) },
          { key: "status", header: "Result", sort: (r) => (r.pass ? 1 : 0), cell: (r) => (run ? <Badge tone={r.pass ? "ok" : "danger"} dot>{r.pass ? "pass" : `fail · ${r.failures.length}`}</Badge> : <span className="text-ink-3">not run</span>) },
        ]}
      />
      <Sheet open={!!sel} onClose={() => setSel(null)} title={sel ? `${sel.id} · ${sel.title}` : ""} subtitle={sel ? <Badge tone={sel.pass ? "ok" : "danger"} dot>{sel.pass ? "pass" : "fail"}</Badge> : null}>
        {sel ? (
          <div className="space-y-4">
            {sel.failures.length ? (
              <Notice tone="danger" title="Failures">
                <ul className="list-disc pl-4">
                  {sel.failures.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </Notice>
            ) : null}
            <div className="space-y-2.5">
              {sel.transcript.map((t, i) => (
                <div key={i} className={`flex ${t.role === "user" ? "justify-end" : ""}`}>
                  <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-[12.5px] leading-relaxed ${t.role === "user" ? "bg-surface-2 text-ink" : "border border-line bg-surface text-ink"}`}>
                    {t.bargeIn ? <Badge tone="warn">barge-in</Badge> : null} {t.text}
                    {t.state ? <span className="mt-1 block font-mono text-[10.5px] text-ink-3">{t.state}</span> : null}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </Sheet>
    </div>
  );
}
