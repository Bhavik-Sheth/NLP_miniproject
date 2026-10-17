"use client";

import type { SearchHit, Timings } from "@/lib/api-v2";
import { Icon } from "./icons";
import { Badge, Empty } from "./primitives";

const LEG_ORDER = ["rewrite", "embed", "vector", "bm25", "fts", "rrf", "fuse", "rerank", "graph", "llm", "answer", "total"];

/** Horizontal waterfall of latency legs. `clientMs` = measured browser round trip. */
export function LatencyBars({ timings, clientMs }: { timings?: Timings | null; clientMs?: number | null }) {
  const legs = Object.entries(timings ?? {})
    .filter(([k, v]) => typeof v === "number" && k.toLowerCase() !== "total")
    .sort((a, b) => {
      const ia = LEG_ORDER.findIndex((l) => a[0].toLowerCase().includes(l));
      const ib = LEG_ORDER.findIndex((l) => b[0].toLowerCase().includes(l));
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
  const total = (timings && (timings.total ?? timings.totalMs)) ?? legs.reduce((a, [, v]) => a + v, 0);
  const max = Math.max(total || 0, ...legs.map(([, v]) => v), 1);
  let offset = 0;
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline gap-3">
        <span className="text-[22px] font-semibold tabular-nums tracking-[-0.03em] text-ink">{total ? Math.round(total) : clientMs != null ? Math.round(clientMs) : "—"}</span>
        <span className="text-[12px] text-ink-3">ms {total ? "server" : "round trip"}</span>
        {clientMs != null && total ? <span className="ml-auto text-[11.5px] tabular-nums text-ink-3">{Math.round(clientMs)} ms round trip</span> : null}
      </div>
      {legs.length === 0 ? (
        <p className="text-[11.5px] text-ink-3">The backend did not report per-leg timings for this call.</p>
      ) : (
        legs.map(([k, v], i) => {
          const left = (offset / max) * 100;
          offset += v;
          return (
            <div key={k} className="grid grid-cols-[64px_1fr_52px] items-center gap-2 text-[11.5px]">
              <span className="truncate font-mono text-ink-3">{k.replace(/Ms$/, "")}</span>
              <div className="relative h-2 rounded-full bg-[color-mix(in_oklab,var(--text)_6%,transparent)]">
                <div
                  className="dash-row-in absolute top-0 h-2 rounded-full"
                  style={{
                    left: `${Math.min(left, 99)}%`,
                    width: `${Math.max((v / max) * 100, 1.2)}%`,
                    background: "linear-gradient(90deg, var(--accent), var(--accent-2))",
                    animationDelay: `${i * 60}ms`,
                  }}
                />
              </div>
              <span className="text-right font-mono tabular-nums text-ink">{v < 10 ? v.toFixed(1) : Math.round(v)}</span>
            </div>
          );
        })
      )}
    </div>
  );
}

function Score({ label, value, digits = 3, max = 1 }: { label: string; value?: number | null; digits?: number; max?: number }) {
  const pct = value == null ? 0 : Math.max(0, Math.min(1, value / max)) * 100;
  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-1 text-[10.5px]">
        <span className="text-ink-3">{label}</span>
        <span className="font-mono tabular-nums text-ink">{value == null ? "—" : Number.isInteger(value) ? value : value.toFixed(digits)}</span>
      </div>
      <div className="mt-1 h-1 rounded-full bg-[color-mix(in_oklab,var(--text)_7%,transparent)]">
        <div className="h-1 rounded-full bg-accent transition-all duration-700" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function HitList({ hits, rewrittenQuery, abstain }: { hits: SearchHit[]; rewrittenQuery?: string; abstain?: boolean }) {
  if (!hits.length) return <Empty icon="search" title="No hits" body="Retrieval returned nothing above threshold." />;
  const maxRrf = Math.max(...hits.map((h) => h.rrfScore ?? 0), 0.0001);
  return (
    <div className="space-y-2.5">
      {rewrittenQuery || abstain != null ? (
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-ink-2">
          {rewrittenQuery ? (
            <>
              <span className="text-ink-3">Rewritten</span>
              <span className="rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[11.5px] text-ink">{rewrittenQuery}</span>
            </>
          ) : null}
          {abstain ? <Badge tone="warn">below threshold · abstain</Badge> : <Badge tone="ok">confident</Badge>}
        </div>
      ) : null}
      {hits.map((h, i) => (
        <article key={`${h.chunkId}-${i}`} className="card dash-row-in p-3" style={{ animationDelay: `${i * 40}ms` }}>
          <div className="flex items-start gap-2">
            <span className="grid h-5 w-5 shrink-0 place-items-center rounded-md bg-surface-2 font-mono text-[10.5px] text-ink-2">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[12.5px] font-medium text-ink">{h.title}</p>
              <p className="truncate text-[11px] text-ink-3">{[h.section, h.category, h.source].filter(Boolean).join(" · ")}</p>
            </div>
            {h.url ? (
              <a href={h.url} target="_blank" rel="noreferrer" className="text-ink-3 hover:text-ink" aria-label="Open source">
                <Icon name="arrowUpRight" size={13} />
              </a>
            ) : null}
          </div>
          <p className="mt-2 line-clamp-3 text-[12px] leading-relaxed text-ink-2">{h.text}</p>
          <div className="mt-2.5 grid grid-cols-4 gap-3">
            <Score label="vector" value={h.vectorScore} />
            <Score label="bm25 rank" value={h.bm25Rank} digits={0} max={Math.max(...hits.map((x) => x.bm25Rank ?? 0), 1)} />
            <Score label="rrf" value={h.rrfScore} digits={4} max={maxRrf} />
            <Score label="rerank" value={h.rerankScore} />
          </div>
        </article>
      ))}
    </div>
  );
}
