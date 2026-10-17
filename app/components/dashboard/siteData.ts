"use client";
// Project-scoped v1 site records with a short module cache so moving between pages is instant,
// plus pure derivations the dashboard uses when v2 endpoints aren't live yet.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ObservationRow } from "@/lib/api";
import { apiV2, type Activity, type Drawing, type GraphData, type Permit, type Rfi } from "@/lib/api-v2";
import { useDash } from "./context";

export type SiteRecord = { drawings: Drawing[]; rfis: Rfi[]; permits: Permit[]; observations: ObservationRow[] };

type CacheEntry = { at: number; promise: Promise<SiteRecord> };
const cache = new Map<string, CacheEntry>();

export function loadSiteRecord(force?: boolean): Promise<SiteRecord>;
export function loadSiteRecord(projectId?: string, force?: boolean): Promise<SiteRecord>;
export function loadSiteRecord(projectIdOrForce: string | boolean = "P1", force = false): Promise<SiteRecord> {
  // Keep loadSiteRecord(true) working for callers from before project switching existed.
  const projectId = typeof projectIdOrForce === "string" ? projectIdOrForce : "P1";
  const shouldForce = typeof projectIdOrForce === "boolean" ? projectIdOrForce : force;
  const existing = cache.get(projectId);
  if (!shouldForce && existing && Date.now() - existing.at < 30_000) return existing.promise;
  const promise = Promise.all([
    apiV2.drawings(projectId),
    apiV2.rfis(projectId),
    apiV2.permits(projectId),
    api.observations(projectId),
  ]).then(
    ([drawings, rfis, permits, observations]) => ({ drawings, rfis, permits, observations }),
  );
  cache.set(projectId, { at: Date.now(), promise });
  promise.catch(() => {
    if (cache.get(projectId)?.promise === promise) cache.delete(projectId);
  });
  return promise;
}

export function useSiteRecord(projectIdOverride?: string) {
  const { project } = useDash();
  const projectId = projectIdOverride ?? project.id;
  const [data, setData] = useState<SiteRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const requestId = useRef(0);
  const run = useCallback((force: boolean) => {
    const currentRequest = ++requestId.current;
    setLoading(true);
    loadSiteRecord(projectId, force)
      .then((d) => {
        if (requestId.current !== currentRequest) return;
        setData(d);
        setError(null);
      })
      .catch((e) => {
        if (requestId.current === currentRequest) setError((e as Error).message);
      })
      .finally(() => {
        if (requestId.current === currentRequest) setLoading(false);
      });
  }, [projectId]);
  useEffect(() => {
    const timer = window.setTimeout(() => run(false), 0);
    return () => window.clearTimeout(timer);
  }, [run]);
  return { data, error, loading, reload: () => run(true) };
}

// ------------------------------------------------------------------ derivations
export const unsatisfied = (p: Permit) => p.checks.filter((c) => c.is_mandatory && !c.satisfied);

export type BlockerItem = { id: string; kind: "permit" | "hold"; title: string; detail: string; tone: "danger" | "warn"; location?: string | null; href: string };

export type HoldPoint = {
  instance_id?: string;
  location_id?: string;
  element?: string;
  planned_activity?: string;
  planned_for?: string;
  status?: string;
  notes?: string;
};

export function deriveBlockers(rec: SiteRecord, holds: HoldPoint[]): BlockerItem[] {
  const out: BlockerItem[] = [];
  for (const p of rec.permits) {
    if (p.status === "Closed") continue;
    const miss = unsatisfied(p);
    if (p.status === "Suspended" || miss.length) {
      out.push({
        id: p.permit_id,
        kind: "permit",
        title: `${p.permit_id} · ${p.permit_type.replace(/_/g, " ")}`,
        detail: miss.length ? `${miss.length} mandatory check${miss.length > 1 ? "s" : ""} unmet — ${miss[0].label}` : `Permit ${p.status.toLowerCase()}`,
        tone: miss.length && p.status === "Active" ? "danger" : "warn",
        location: p.location_id,
        href: "/app/permits",
      });
    }
  }
  for (const h of holds) {
    out.push({
      id: h.instance_id ?? "hold",
      kind: "hold",
      title: `${h.instance_id ?? "Hold point"} · ${(h.planned_activity ?? "").replace(/_/g, " ")}`,
      detail: h.notes ?? `Status ${h.status ?? "Hold"}`,
      tone: "danger",
      location: h.location_id,
      href: "/app/permits",
    });
  }
  return out;
}

export function deriveActivity(rec: SiteRecord): Activity[] {
  const a: Activity[] = [];
  for (const o of rec.observations)
    a.push({
      kind: "observation",
      id: o.observation_id,
      title: `${o.observation_id} · ${o.element} ${o.attribute} ${o.value_claimed}${o.unit ?? ""}`,
      detail: `${o.location_id.replace(/^[^:]+:/, "")} → ${o.drawing_id} · ${o.final_decision.replace(/_/g, " ")}`,
      at: o.created_at,
      tone: o.final_decision === "log_observation" ? "ok" : o.final_decision === "raise_rfi" ? "warn" : "danger",
    });
  for (const r of rec.rfis) {
    if (r.raised_on) a.push({ kind: "rfi", id: r.rfi_id, title: `${r.rfi_id} raised`, detail: r.subject, at: r.raised_on, tone: "warn" });
    if (r.answered_on) a.push({ kind: "rfi", id: r.rfi_id, title: `${r.rfi_id} ${r.status.toLowerCase()}`, detail: r.impact ?? r.subject, at: r.answered_on, tone: "ok" });
  }
  for (const d of rec.drawings)
    a.push({ kind: "drawing", id: d.drawing_id, title: `${d.drawing_number} ${d.revision} issued`, detail: d.change_note ?? d.title, at: d.issued_on, tone: "info" });
  for (const p of rec.permits)
    if (p.valid_from) a.push({ kind: "permit", id: p.permit_id, title: `${p.permit_id} ${p.status.toLowerCase()}`, detail: `${p.permit_type.replace(/_/g, " ")} · ${p.location_id ?? ""}`, at: p.valid_from, tone: p.status === "Active" ? "ok" : "warn" });
  return a.sort((x, y) => new Date(y.at).getTime() - new Date(x.at).getTime());
}

/** A knowledge graph assembled from the deterministic record when the memory graph is unavailable. */
export function deriveGraph(rec: SiteRecord): GraphData {
  const nodes = new Map<string, { id: string; label: string; type: string }>();
  const edges: { source: string; target: string; label?: string }[] = [];
  const node = (id: string, label: string, type: string) => {
    if (!nodes.has(id)) nodes.set(id, { id, label, type });
    return id;
  };
  const projectId =
    rec.drawings[0]?.project_id ?? rec.rfis[0]?.project_id ?? rec.permits[0]?.project_id ?? "project";
  const loc = (l?: string | null) => {
    if (!l) return null;
    const prefix = `${projectId}:`;
    return node(`loc:${l}`, l.startsWith(prefix) ? l.slice(prefix.length) : l, "location");
  };
  const proj = node(`project:${projectId}`, projectId, "project");
  for (const d of rec.drawings) {
    const sheet = node(`dwg:${d.drawing_number}`, d.drawing_number, "drawing");
    const rev = node(`rev:${d.drawing_id}`, `${d.drawing_number} ${d.revision}`, d.is_latest ? "revision" : "superseded");
    edges.push({ source: sheet, target: rev, label: "revision" });
    if (d.superseded_by) edges.push({ source: rev, target: `rev:${d.superseded_by}`, label: "superseded by" });
    if (d.is_latest) edges.push({ source: proj, target: sheet, label: d.discipline });
  }
  for (const r of rec.rfis) {
    const id = node(`rfi:${r.rfi_id}`, r.rfi_id, "rfi");
    if (r.drawing_ref && nodes.has(`dwg:${r.drawing_ref}`)) edges.push({ source: id, target: `dwg:${r.drawing_ref}`, label: "about" });
    const l = loc(r.location_id);
    if (l) edges.push({ source: id, target: l, label: "at" });
    if (r.resulting_drawing_id && nodes.has(`rev:${r.resulting_drawing_id}`)) edges.push({ source: id, target: `rev:${r.resulting_drawing_id}`, label: "resulted in" });
  }
  for (const p of rec.permits) {
    const id = node(`permit:${p.permit_id}`, p.permit_id, "permit");
    const l = loc(p.location_id);
    if (l) edges.push({ source: id, target: l, label: "covers" });
  }
  for (const o of rec.observations) {
    const id = node(`obs:${o.observation_id}`, o.observation_id, "observation");
    const l = loc(o.location_id);
    if (l) edges.push({ source: id, target: l, label: "at" });
    const rev = `rev:${o.drawing_id}`;
    if (nodes.has(rev)) edges.push({ source: id, target: rev, label: "checked against" });
    if (o.linked_rfi_id && nodes.has(`rfi:${o.linked_rfi_id}`)) edges.push({ source: id, target: `rfi:${o.linked_rfi_id}`, label: "linked" });
  }
  const ids = new Set(nodes.keys());
  return { nodes: [...nodes.values()], edges: edges.filter((e) => ids.has(e.source) && ids.has(e.target)) };
}

export const isToday = (s?: string | null) => !!s && new Date(s).toDateString() === new Date().toDateString();
