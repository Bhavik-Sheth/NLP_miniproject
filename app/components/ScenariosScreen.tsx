"use client";

import { Fragment, useState } from "react";
import { ApiError, api, type ScenarioRunResponse } from "@/lib/api";
import { Card, ErrorBanner, Button } from "@/components/ui";

export default function ScenariosScreen() {
  const [data, setData] = useState<ScenarioRunResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [notReady, setNotReady] = useState(false);
  const [running, setRunning] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setErr(null);
    setNotReady(false);
    setData(null);
    try {
      setData(await api.runScenarios());
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) setNotReady(true);
      else setErr((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between px-1">
        <div>
          <span className="text-[10px] font-mono tracking-wider uppercase text-zinc-400">
            Regression & Benchmark Suite
          </span>
          <h2 className="text-lg font-medium text-white tracking-tight">
            Scenario <span className="editorial-em">Evaluator</span>
          </h2>
        </div>
        <Button
          id="tour-scenarios-run"
          variant="solid"
          size="sm"
          onClick={run}
          disabled={running}
        >
          {running ? "Executing…" : "Run All Scenarios"}
        </Button>
      </div>

      {notReady ? (
        <div className="glass-panel glass-panel-amber p-3 text-xs text-amber-200">
          Scenario runner not ready yet on server.
        </div>
      ) : null}

      <ErrorBanner msg={err} />

      {/* Summary Scorecard Cards */}
      {data ? (
        <div id="tour-scenarios" className="grid grid-cols-3 gap-2">
          <Card tone={data.passed === data.total ? "green" : "neutral"} className="text-center p-3">
            <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 block mb-1">
              Passed
            </span>
            <span className="text-lg font-mono font-semibold text-white">
              {data.passed} <span className="text-zinc-500 text-xs">/ {data.total}</span>
            </span>
          </Card>

          <Card tone={data.wrongLogs > 0 ? "red" : "green"} className="text-center p-3">
            <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 block mb-1">
              Wrong Logs
            </span>
            <span className={`text-lg font-mono font-semibold ${data.wrongLogs > 0 ? "text-red-400" : "text-emerald-400"}`}>
              {data.wrongLogs}
            </span>
          </Card>

          <Card className="text-center p-3">
            <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 block mb-1">
              Pass Rate
            </span>
            <span className="text-lg font-mono font-semibold text-white">
              {data.total > 0 ? Math.round((data.passed / data.total) * 100) : 0}%
            </span>
          </Card>
        </div>
      ) : null}

      {/* Scenarios List */}
      {data ? (
        <div className="space-y-2">
          {data.results.map((r) => {
            const isOpen = openId === r.id;
            return (
              <div key={r.id} className="flex flex-col gap-1">
                <div
                  onClick={() => setOpenId(isOpen ? null : r.id)}
                  className="cursor-pointer"
                >
                  <Card
                    tone={r.pass ? "neutral" : "red"}
                    hoverable={true}
                    className="p-3"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="font-mono text-xs font-semibold text-zinc-400">
                          {r.id}
                        </span>
                        <span className="text-xs text-white font-medium truncate">
                          {r.title}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <span
                          className={`font-mono text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded border ${
                            r.pass
                              ? "bg-emerald-950/70 border-emerald-500/40 text-emerald-300"
                              : "bg-red-950/70 border-red-500/40 text-red-300"
                          }`}
                        >
                          {r.pass ? "PASS" : "FAIL"}
                        </span>
                        <svg
                          className={`w-3.5 h-3.5 text-zinc-500 transition-transform ${
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

                    <div className="mt-2 flex items-center gap-3 text-[11px] font-mono text-zinc-400">
                      <span>Decision: {r.finalDecision || "—"}</span>
                      {r.kindsSeen?.length ? (
                        <>
                          <span className="text-zinc-600">|</span>
                          <span>Kinds: {r.kindsSeen.join(", ")}</span>
                        </>
                      ) : null}
                    </div>
                  </Card>
                </div>

                {/* Expanded Scenario Drawer */}
                {isOpen ? (
                  <div className="pl-2 border-l border-white/10 ml-2">
                    <Card title={`Execution Trace · ${r.id}`}>
                      {r.failures?.length ? (
                        <div className="mb-3 p-2 rounded bg-red-950/50 border border-red-500/30 text-xs text-red-200 font-mono">
                          <span className="font-semibold block mb-0.5">Failures:</span>
                          {r.failures.join("; ")}
                        </div>
                      ) : null}

                      <div className="flex flex-col gap-2">
                        <span className="text-[10.5px] font-mono uppercase tracking-wider text-zinc-500">
                          Turn Transcript
                        </span>
                        {r.transcript?.map((t, i) => (
                          <div
                            key={i}
                            className={`p-2 rounded-lg text-xs leading-relaxed ${
                              t.role === "agent"
                                ? "bg-white/5 border border-white/10 text-zinc-200"
                                : "bg-zinc-900 border border-zinc-700 text-white"
                            }`}
                          >
                            <div className="flex items-center gap-2 mb-1 text-[10px] font-mono text-zinc-400">
                              <span className="uppercase font-semibold">{t.role}</span>
                              {t.bargeIn ? <span className="text-amber-400">(barge-in)</span> : null}
                              {t.state ? <span className="text-zinc-500">[{t.state}]</span> : null}
                            </div>
                            <p>{t.text}</p>
                          </div>
                        ))}
                      </div>
                    </Card>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
