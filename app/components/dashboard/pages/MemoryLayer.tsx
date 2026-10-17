"use client";

import { useEffect, useMemo, useState } from "react";
import { apiV2, isMissing, type SearchResponse } from "@/lib/api-v2";
import { useDash } from "../context";
import { Icon, type IconName } from "../icons";
import { Badge, DataTable, EndpointNotice, Empty, Notice, PageHeader, Panel, Segmented, Skeleton, fmtDate, relTime, statusTone, useAsync } from "../primitives";
import KnowledgeGraph from "../KnowledgeGraph";
import { HitList, LatencyBars } from "../Retrieval";
import { deriveGraph, useSiteRecord } from "../siteData";

const MODEL_DEFAULTS: { key: "embedding" | "reranker" | "llm" | "vectorStore" | "graphStore"; label: string; icon: IconName; value: string; note: string }[] = [
  { key: "embedding", label: "Embedding", icon: "hash", value: "BAAI/bge-m3", note: "1024d · multilingual · Ollama" },
  { key: "reranker", label: "Reranker", icon: "sliders", value: "bge-reranker-v2-m3", note: "cross-encoder · MPS" },
  { key: "llm", label: "LLM", icon: "bolt", value: "gpt-oss-120b", note: "Groq → Cerebras fallback" },
  { key: "vectorStore", label: "Vectors", icon: "layers", value: "LanceDB", note: "embedded · data/memory" },
  { key: "graphStore", label: "Graph", icon: "graph", value: "Kuzu", note: "Cognee knowledge graph" },
];

export default function MemoryLayer() {
  const { project } = useDash();
  const stats = useAsync(() => apiV2.stats(project.id), [project.id]);
  const docs = useAsync(() => apiV2.documents(project.id), [project.id]);
  const [graphQ, setGraphQ] = useState("");
  const [graphQuery, setGraphQuery] = useState("");
  const graph = useAsync(() => apiV2.graph({ projectId: project.id, q: graphQuery || undefined, limit: 150 }), [project.id, graphQuery]);
  const site = useSiteRecord();
  const [graphSource, setGraphSource] = useState<"memory" | "record">("memory");

  const derived = useMemo(() => (site.data ? deriveGraph(site.data) : null), [site.data]);
  const useDerived = graphSource === "record" || (!!graph.error && !graph.loading) || (graph.data?.nodes.length === 0 && !graphQuery);
  const graphData = useDerived ? derived : graph.data;

  return (
    <div>
      <PageHeader
        eyebrow="Knowledge"
        title="Memory layer"
        accent="local-first"
        description="Everything Vesper can recall: global codes and templates plus this project’s documents, embedded locally and linked into a knowledge graph."
        actions={
          <button className="dash-btn dash-btn-sm" onClick={() => (stats.reload(), docs.reload(), graph.reload())}>
            <Icon name="refresh" size={13} /> Refresh
          </button>
        }
      />

      {/* models strip */}
      <div id="tour-memory-models" className="glass mb-5 grid grid-cols-2 divide-line overflow-hidden sm:grid-cols-3 lg:grid-cols-5 lg:divide-x">
        {MODEL_DEFAULTS.map((m, i) => (
          <div key={m.key} className="dash-rise flex items-center gap-3 px-4 py-3.5" style={{ animationDelay: `${i * 40}ms` }}>
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-line bg-surface text-accent">
              <Icon name={m.icon} size={15} />
            </span>
            <div className="min-w-0">
              <p className="dash-eyebrow">{m.label}</p>
              <p className="mt-1 truncate font-mono text-[12.5px] text-ink">{stats.data?.models?.[m.key] ?? m.value}</p>
              <p className="truncate text-[11px] text-ink-3">{m.note}</p>
            </div>
          </div>
        ))}
      </div>

      {/* corpora */}
      <div className="mb-2 flex items-center gap-2">
        <h2 className="text-[13px] font-medium text-ink">Corpora</h2>
        {stats.data ? (
          <span className="text-[12px] text-ink-3">
            graph {stats.data.graph.nodes.toLocaleString()} nodes · {stats.data.graph.edges.toLocaleString()} edges
          </span>
        ) : null}
      </div>
      <div className="mb-5">
        {stats.loading ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-[104px] rounded-2xl" />
            ))}
          </div>
        ) : stats.error ? (
          <EndpointNotice state={stats} endpoint="GET /api/memory/stats" fallback="Corpora (kb_templates, kb_is_codes, kb_prices_sor, kb_handbook and this project’s dataset) appear here once W1’s memory router is loaded." />
        ) : stats.data?.corpora.length ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {stats.data.corpora.map((c, i) => {
              const max = Math.max(...stats.data!.corpora.map((x) => x.chunks), 1);
              return (
                <div key={c.name} className="card card-hover dash-rise p-4" style={{ animationDelay: `${i * 40}ms` }}>
                  <div className="flex items-center gap-2">
                    <Badge tone={c.scope === "global" ? "accent" : "ok"}>{c.scope}</Badge>
                    <span className="truncate font-mono text-[12px] text-ink">{c.name}</span>
                  </div>
                  <div className="mt-3 flex items-baseline gap-3">
                    <span className="text-[22px] font-semibold tabular-nums tracking-[-0.03em] text-ink">{c.chunks.toLocaleString()}</span>
                    <span className="text-[12px] text-ink-3">chunks · {c.documents.toLocaleString()} docs</span>
                  </div>
                  <div className="mt-2 h-1 rounded-full bg-surface-2">
                    <div className="h-1 rounded-full" style={{ width: `${(c.chunks / max) * 100}%`, background: "linear-gradient(90deg, var(--accent), var(--accent-2))" }} />
                  </div>
                  <p className="mt-2 text-[11px] text-ink-3">{c.lastIngested ? `ingested ${relTime(c.lastIngested)}` : "not yet ingested"}</p>
                </div>
              );
            })}
          </div>
        ) : (
          <Empty icon="brain" title="No corpora yet" body="Ingest documents to build the memory." />
        )}
      </div>

      <div id="tour-memory-graph" className="mb-5 grid gap-5 xl:grid-cols-[1.4fr_1fr]">
        <Panel
          title="Knowledge graph"
          icon="graph"
          bodyClassName="p-0"
          action={
            <>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  setGraphSource("memory");
                  setGraphQuery(graphQ.trim());
                }}
                className="hidden sm:block"
              >
                <input className="dash-input h-7 w-44 text-[12px]" placeholder="Focus on entity…" value={graphQ} onChange={(e) => setGraphQ(e.target.value)} />
              </form>
              <Segmented
                size="sm"
                value={useDerived ? "record" : "memory"}
                onChange={setGraphSource}
                options={[
                  { value: "memory", label: "Memory" },
                  { value: "record", label: "Site record" },
                ]}
              />
            </>
          }
        >
          {useDerived && graph.error && graphSource === "memory" ? (
            <p className="border-b border-line px-4 py-2 text-[11.5px] text-ink-3">
              {isMissing({ status: 0 }) ? null : null}
              Kuzu graph endpoint {graph.missing ? "not live" : "unavailable"} — showing the graph derived from drawings, RFIs, permits and observations.
            </p>
          ) : null}
          {graph.loading && !useDerived ? (
            <Skeleton className="m-4 h-[420px]" />
          ) : graphData && graphData.nodes.length ? (
            <KnowledgeGraph data={graphData} height={460} />
          ) : (
            <Empty icon="graph" title={site.loading ? "Building graph…" : "No graph data"} />
          )}
        </Panel>

        <SearchPlayground />
      </div>

      <h2 className="mb-2 text-[13px] font-medium text-ink">Documents</h2>
      {docs.error ? (
        <EndpointNotice state={docs} endpoint="GET /api/memory/documents" />
      ) : (
        <DataTable
          rows={docs.data}
          loading={docs.loading}
          rowKey={(d) => d.docId}
          searchText={(d) => `${d.title} ${d.category ?? ""} ${d.source ?? ""}`}
          facet={{ label: "Category", get: (d) => d.category ?? "uncategorised" }}
          initialSort={{ key: "created", dir: "desc" }}
          empty={<Empty icon="file" title="No documents ingested" body="Upload drawings, specs, method statements or voice notes in Documents & ingest." />}
          columns={[
            { key: "title", header: "Title", cell: (d) => <span className="font-medium">{d.title}</span>, sort: (d) => d.title },
            { key: "category", header: "Category", cell: (d) => <Badge>{d.category ?? "—"}</Badge>, sort: (d) => d.category ?? "", hideBelow: "md" },
            { key: "source", header: "Source", cell: (d) => <span className="text-ink-3">{d.source ?? "—"}</span>, hideBelow: "lg" },
            { key: "chunks", header: "Chunks", cell: (d) => <span className="tabular-nums">{d.chunks}</span>, sort: (d) => d.chunks },
            { key: "status", header: "Status", cell: (d) => <Badge tone={statusTone(d.status)} dot>{d.status}</Badge>, sort: (d) => d.status },
            { key: "created", header: "Added", cell: (d) => <span className="text-ink-3">{fmtDate(d.createdAt)}</span>, sort: (d) => d.createdAt, hideBelow: "md" },
          ]}
        />
      )}
    </div>
  );
}

function SearchPlayground() {
  const { project } = useDash();
  const [q, setQ] = useState("");
  const [scopes, setScopes] = useState<"both" | "global" | "project">("both");
  const [state, setState] = useState<{ loading: boolean; res?: SearchResponse; error?: string; missing?: boolean; ms?: number } | null>(null);

  const run = async (query: string) => {
    if (!query.trim()) return;
    setState({ loading: true });
    const t0 = performance.now();
    try {
      const res = await apiV2.search({ query, projectId: project.id, k: 8, scopes: scopes === "both" ? ["global", "project"] : [scopes] });
      setState({ loading: false, res, ms: performance.now() - t0 });
    } catch (e) {
      setState({ loading: false, error: (e as Error).message, missing: isMissing(e) });
    }
  };

  useEffect(() => {
    const initial = new URLSearchParams(window.location.search).get("q");
    if (initial) {
      setQ(initial);
      void run(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Panel title="Search playground" icon="search" bodyClassName="flex min-h-0 flex-col p-4">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void run(q);
        }}
      >
        <input className="dash-input" placeholder="e.g. RFI-050 conduit reroute, Cl. 26.4 cover" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="dash-btn dash-btn-primary" disabled={!q.trim() || state?.loading}>
          Search
        </button>
      </form>
      <div className="mt-2.5">
        <Segmented
          size="sm"
          value={scopes}
          onChange={setScopes}
          options={[
            { value: "both", label: "Global + project" },
            { value: "global", label: "Global" },
            { value: "project", label: "Project" },
          ]}
        />
      </div>
      <div className="mt-4 max-h-[400px] min-h-0 flex-1 overflow-y-auto pr-1">
        {!state ? (
          <Empty icon="search" title="Probe the retriever" body="See vector, BM25, RRF and rerank scores for any query, with latency per leg." />
        ) : state.loading ? (
          <div className="space-y-2">
            <Skeleton className="h-16" />
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
          </div>
        ) : state.error ? (
          <Notice tone={state.missing ? "neutral" : "danger"} title={state.missing ? "/api/memory/search is not live yet" : "Search failed"}>
            {state.missing ? "Available once the memory router is loaded on the backend." : <span className="font-mono text-[11.5px]">{state.error}</span>}
          </Notice>
        ) : state.res ? (
          <div className="space-y-4">
            <LatencyBars timings={state.res.timings ?? state.res.timingsMs} clientMs={state.ms} />
            <HitList hits={state.res.hits} rewrittenQuery={state.res.rewrittenQuery} abstain={state.res.abstain} />
          </div>
        ) : null}
      </div>
    </Panel>
  );
}
