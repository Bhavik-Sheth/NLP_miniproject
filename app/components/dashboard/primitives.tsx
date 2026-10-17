"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { isMissing } from "@/lib/api-v2";
import { Icon, type IconName } from "./icons";

// ------------------------------------------------------------------ data hook
export type AsyncState<T> = {
  data: T | null;
  error: string | null;
  missing: boolean;
  loading: boolean;
  reload: () => void;
};

/** Runs `fn` on mount and whenever `deps` change. `missing` = endpoint not deployed (404/405/501). */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [state, setState] = useState<{ data: T | null; error: string | null; missing: boolean; loading: boolean }>({
    data: null,
    error: null,
    missing: false,
    loading: true,
  });
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    fnRef
      .current()
      .then((data) => alive && setState({ data, error: null, missing: false, loading: false }))
      .catch((e) => alive && setState({ data: null, error: (e as Error).message, missing: isMissing(e), loading: false }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}

// ------------------------------------------------------------------ formatting
export function fmtDate(s?: string | null, withTime = false) {
  if (!s) return "—";
  const d = new Date(s.length === 10 ? `${s}T00:00:00` : s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : { year: d.getFullYear() === new Date().getFullYear() ? undefined : "numeric" }),
  });
}

export function relTime(s?: string | null) {
  if (!s) return "";
  const t = new Date(s.length === 10 ? `${s}T00:00:00` : s).getTime();
  if (Number.isNaN(t)) return s;
  const diff = (Date.now() - t) / 1000;
  const abs = Math.abs(diff);
  const f = (n: number, u: string) => `${Math.round(n)}${u}${diff >= 0 ? " ago" : " ahead"}`;
  if (abs < 60) return "just now";
  if (abs < 3600) return f(abs / 60, "m");
  if (abs < 86400) return f(abs / 3600, "h");
  if (abs < 86400 * 30) return f(abs / 86400, "d");
  return fmtDate(s);
}

export type Tone = "ok" | "warn" | "danger" | "accent" | "neutral";

export function statusTone(status?: string | null): Tone {
  const s = (status ?? "").toLowerCase();
  if (/(for construction|closed|answered|done|pass|released|log_observation|approved|active)/.test(s)) return "ok";
  if (/(open|hold|suspended|pending|for approval|queued|parsing|embedding|graph|raise_rfi)/.test(s)) return "warn";
  if (/(superseded|error|fail|blocked|stop_work|raise_ncr|rejected)/.test(s)) return s.includes("superseded") ? "neutral" : "danger";
  return "neutral";
}

export const humanize = (s?: string | null) => (s ?? "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

// ------------------------------------------------------------------ atoms
export function Badge({ tone = "neutral", children, dot = false }: { tone?: Tone; children: ReactNode; dot?: boolean }) {
  return (
    <span className="dash-badge" data-tone={tone === "neutral" ? undefined : tone}>
      {dot ? <span className="dash-dot" data-tone={tone === "accent" || tone === "neutral" ? undefined : tone} style={{ width: 5, height: 5, boxShadow: "none" }} /> : null}
      {children}
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd">{children}</kbd>;
}

export function Skeleton({ className = "", style }: { className?: string; style?: React.CSSProperties }) {
  return <div className={`dash-skel ${className}`} style={style} />;
}

export function PageHeader({
  eyebrow,
  title,
  accent,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  accent?: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow ? <p className="dash-eyebrow mb-2">{eyebrow}</p> : null}
        <h1 className="text-[26px] font-semibold leading-tight tracking-[-0.03em] text-ink">
          {title}
          {accent ? <span className="dash-serif ml-2 text-[1.08em] font-normal text-ink-2">{accent}</span> : null}
        </h1>
        {description ? <p className="mt-1.5 max-w-2xl text-[13.5px] leading-relaxed text-ink-2">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function Panel({
  title,
  icon,
  action,
  children,
  className = "",
  bodyClassName = "p-4",
  glass = false,
  id,
}: {
  title?: ReactNode;
  icon?: IconName;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  glass?: boolean;
  id?: string;
}) {
  return (
    <section id={id} className={`${glass ? "glass" : "card"} flex min-w-0 flex-col ${className}`}>
      {title ? (
        <div className="flex h-11 shrink-0 items-center gap-2 border-b border-line px-4">
          {icon ? <Icon name={icon} size={14} className="text-ink-3" /> : null}
          <h2 className="truncate text-[13px] font-medium text-ink">{title}</h2>
          {action ? <div className="ml-auto flex items-center gap-1.5">{action}</div> : null}
        </div>
      ) : null}
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
}

export function Empty({ icon = "compass", title, body, action }: { icon?: IconName; title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-10 text-center">
      <div className="mb-3 grid h-10 w-10 place-items-center rounded-xl border border-line bg-surface-2 text-ink-3">
        <Icon name={icon} size={18} />
      </div>
      <p className="text-[13.5px] font-medium text-ink">{title}</p>
      {body ? <p className="mt-1 max-w-sm text-[12.5px] leading-relaxed text-ink-3">{body}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function Notice({ tone = "neutral", title, children, action }: { tone?: Tone; title: ReactNode; children?: ReactNode; action?: ReactNode }) {
  const color = tone === "danger" ? "var(--danger)" : tone === "warn" ? "var(--warn)" : tone === "ok" ? "var(--ok)" : "var(--accent)";
  return (
    <div
      className="flex items-start gap-3 rounded-xl border px-3.5 py-3 text-[12.5px]"
      style={{ borderColor: `color-mix(in oklab, ${color} 28%, transparent)`, background: `color-mix(in oklab, ${color} 7%, transparent)` }}
      role={tone === "danger" ? "alert" : "status"}
    >
      <Icon name={tone === "danger" || tone === "warn" ? "alert" : "bolt"} size={15} style={{ color, marginTop: 1, flexShrink: 0 }} />
      <div className="min-w-0 flex-1">
        <p className="font-medium text-ink">{title}</p>
        {children ? <div className="mt-0.5 break-words leading-relaxed text-ink-2">{children}</div> : null}
      </div>
      {action}
    </div>
  );
}

/** Shows "endpoint not live yet" vs a real error consistently. */
export function EndpointNotice({ state, endpoint, fallback }: { state: { error: string | null; missing: boolean }; endpoint: string; fallback?: string }) {
  if (!state.error) return null;
  if (state.missing)
    return (
      <Notice tone="neutral" title={`${endpoint} is not live on this backend yet`}>
        {fallback ?? "This panel fills in automatically once the v2 router is loaded."}
      </Notice>
    );
  return (
    <Notice tone="danger" title={`Could not load ${endpoint}`}>
      <span className="font-mono text-[11.5px]">{state.error}</span>
    </Notice>
  );
}

export function Kpi({
  label,
  value,
  sub,
  icon,
  tone,
  loading,
  href,
  delay = 0,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon: IconName;
  tone?: Tone;
  loading?: boolean;
  href?: string;
  delay?: number;
}) {
  const color = tone === "danger" ? "var(--danger)" : tone === "warn" ? "var(--warn)" : tone === "ok" ? "var(--ok)" : "var(--accent)";
  const body = (
    <div className="card card-hover dash-rise relative h-full overflow-hidden p-4" style={{ animationDelay: `${delay}ms` }}>
      <div
        className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full opacity-60 blur-2xl"
        style={{ background: `color-mix(in oklab, ${color} 22%, transparent)` }}
      />
      <div className="flex items-center gap-2 text-[12px] text-ink-2">
        <span className="grid h-6 w-6 place-items-center rounded-md border border-line bg-surface-2" style={{ color }}>
          <Icon name={icon} size={13} />
        </span>
        {label}
      </div>
      <div className="mt-3 text-[28px] font-semibold tabular-nums leading-none tracking-[-0.03em] text-ink">
        {loading ? <Skeleton className="h-7 w-14" /> : value}
      </div>
      <div className="mt-1.5 min-h-[16px] text-[11.5px] text-ink-3">{loading ? null : sub}</div>
    </div>
  );
  return href ? (
    <Link href={href} className="block h-full">
      {body}
    </Link>
  ) : (
    body
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  size = "md",
}: {
  options: { value: T; label: ReactNode; icon?: IconName }[];
  value: T;
  onChange: (v: T) => void;
  size?: "sm" | "md";
}) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-surface-2 p-0.5" role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={o.value === value}
          onClick={() => onChange(o.value)}
          className={`inline-flex items-center gap-1.5 rounded-md px-2.5 font-medium transition ${size === "sm" ? "h-6 text-[11.5px]" : "h-7 text-[12.5px]"} ${
            o.value === value ? "bg-surface text-ink shadow-[var(--shadow-sm)]" : "text-ink-3 hover:text-ink"
          }`}
        >
          {o.icon ? <Icon name={o.icon} size={13} /> : null}
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ side sheet
export function Sheet({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <>
      <div className="dash-overlay" onClick={onClose} />
      <aside className="dash-sheet glass-strong" role="dialog" aria-modal="true">
        <div className="flex items-start gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0 flex-1">
            <div className="text-[15px] font-semibold tracking-[-0.02em] text-ink">{title}</div>
            {subtitle ? <div className="mt-1 text-[12.5px] text-ink-3">{subtitle}</div> : null}
          </div>
          <button className="dash-btn dash-btn-ghost dash-btn-icon dash-btn-sm" onClick={onClose} aria-label="Close">
            <Icon name="x" size={15} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer ? <div className="border-t border-line px-5 py-3">{footer}</div> : null}
      </aside>
    </>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-3 py-2 text-[12.5px]">
      <dt className="text-ink-3">{label}</dt>
      <dd className="min-w-0 break-words text-ink">{children ?? "—"}</dd>
    </div>
  );
}

// ------------------------------------------------------------------ data table
export type Column<T> = {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
  sort?: (row: T) => string | number;
  className?: string;
  hideBelow?: "md" | "lg" | "xl";
  width?: number | string;
};

export type Facet<T> = { label: string; get: (row: T) => string };

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  onRowClick,
  activeKey,
  searchText,
  facet,
  loading,
  empty,
  toolbar,
  initialSort,
  placeholder = "Filter…",
}: {
  rows: T[] | null;
  columns: Column<T>[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  activeKey?: string | null;
  searchText: (row: T) => string;
  facet?: Facet<T>;
  loading?: boolean;
  empty?: ReactNode;
  toolbar?: ReactNode;
  initialSort?: { key: string; dir: "asc" | "desc" };
  placeholder?: string;
}) {
  const [q, setQ] = useState("");
  const [facetValue, setFacetValue] = useState<string>("__all");
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" } | null>(initialSort ?? null);

  const facetCounts = useMemo(() => {
    if (!facet || !rows) return [];
    const m = new Map<string, number>();
    rows.forEach((r) => m.set(facet.get(r), (m.get(facet.get(r)) ?? 0) + 1));
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [rows, facet]);

  const shown = useMemo(() => {
    if (!rows) return [];
    const needle = q.trim().toLowerCase();
    let out = rows.filter(
      (r) => (!needle || searchText(r).toLowerCase().includes(needle)) && (!facet || facetValue === "__all" || facet.get(r) === facetValue),
    );
    const col = sort && columns.find((c) => c.key === sort.key);
    if (col?.sort) {
      const get = col.sort;
      out = [...out].sort((a, b) => {
        const av = get(a);
        const bv = get(b);
        const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv), undefined, { numeric: true });
        return sort!.dir === "asc" ? cmp : -cmp;
      });
    }
    return out;
  }, [rows, q, facetValue, sort, columns, searchText, facet]);

  const hide = (c: Column<T>) => (c.hideBelow ? { md: "hidden md:table-cell", lg: "hidden lg:table-cell", xl: "hidden xl:table-cell" }[c.hideBelow] : "");

  return (
    <div className="card flex min-w-0 flex-col overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2.5">
        <div className="relative w-full sm:w-64">
          <Icon name="search" size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-3" />
          <input className="dash-input h-8 pl-8" placeholder={placeholder} value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        {facet && facetCounts.length > 1 ? (
          <div className="flex flex-wrap items-center gap-1">
            {[["__all", rows?.length ?? 0] as [string, number], ...facetCounts].map(([v, n]) => (
              <button
                key={v}
                onClick={() => setFacetValue(v)}
                className={`inline-flex h-7 items-center gap-1.5 rounded-md border px-2 text-[12px] transition ${
                  facetValue === v ? "border-line bg-surface-2 text-ink" : "border-transparent text-ink-3 hover:text-ink"
                }`}
              >
                {v === "__all" ? "All" : v}
                <span className="tabular-nums text-ink-3">{n}</span>
              </button>
            ))}
          </div>
        ) : null}
        <div className="ml-auto flex items-center gap-2">
          <span className="text-[11.5px] tabular-nums text-ink-3">
            {loading ? "" : `${shown.length} of ${rows?.length ?? 0}`}
          </span>
          {toolbar}
        </div>
      </div>
      <div className="max-h-[calc(100dvh-260px)] min-h-[200px] overflow-auto">
        <table className="dash-table">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={hide(c)} style={{ width: c.width }}>
                  {c.sort ? (
                    <button
                      className="inline-flex items-center gap-1 hover:text-ink"
                      onClick={() =>
                        setSort((s) => (s?.key === c.key ? { key: c.key, dir: s.dir === "asc" ? "desc" : "asc" } : { key: c.key, dir: "asc" }))
                      }
                    >
                      {c.header}
                      <Icon
                        name={sort?.key === c.key ? "chevronDown" : "chevronUpDown"}
                        size={11}
                        style={{ transform: sort?.key === c.key && sort.dir === "asc" ? "rotate(180deg)" : undefined, opacity: sort?.key === c.key ? 1 : 0.5 }}
                      />
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i}>
                    {columns.map((c) => (
                      <td key={c.key} className={hide(c)}>
                        <Skeleton className="h-3.5" style={{ width: `${40 + ((i * 17 + c.key.length * 11) % 50)}%` }} />
                      </td>
                    ))}
                  </tr>
                ))
              : shown.map((r) => {
                  const k = rowKey(r);
                  return (
                    <tr
                      key={k}
                      data-active={activeKey === k}
                      onClick={onRowClick ? () => onRowClick(r) : undefined}
                      className={onRowClick ? "cursor-pointer" : ""}
                    >
                      {columns.map((c) => (
                        <td key={c.key} className={`${hide(c)} ${c.className ?? ""}`}>
                          {c.cell(r)}
                        </td>
                      ))}
                    </tr>
                  );
                })}
          </tbody>
        </table>
        {!loading && shown.length === 0 ? (empty ?? <Empty icon="search" title="Nothing matches" body="Try a different filter." />) : null}
      </div>
    </div>
  );
}

export function Mono({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`font-mono text-[12px] ${className}`}>{children}</span>;
}
