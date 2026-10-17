"use client";

import { useEffect, useRef, useState } from "react";
import type { GraphData } from "@/lib/api-v2";

type N = { id: string; label: string; type: string; x: number; y: number; vx: number; vy: number; deg: number; fixed?: boolean };

const TYPE_COLORS = ["#6d8dff", "#a58bff", "#34c6b3", "#f0a94a", "#ef6b8a", "#62b0ff", "#9bc55a", "#c98cf0", "#8a93a6"];

export function typeColor(type: string, types: string[]) {
  if (type === "superseded") return "#8a93a6";
  return TYPE_COLORS[Math.max(0, types.indexOf(type)) % TYPE_COLORS.length];
}

/** Canvas force-directed graph: pan (drag background), zoom (wheel), drag nodes, hover to highlight neighbours. */
export default function KnowledgeGraph({ data, height = 460, onSelect }: { data: GraphData; height?: number; onSelect?: (id: string | null) => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ n: N; x: number; y: number } | null>(null);
  const types = [...new Set(data.nodes.map((n) => n.type).filter((t) => t !== "superseded"))];

  useEffect(() => {
    const canvas = canvasRef.current!;
    const wrap = wrapRef.current!;
    const ctx = canvas.getContext("2d")!;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let W = wrap.clientWidth;
    const H = height;
    const resize = () => {
      W = wrap.clientWidth;
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      canvas.style.width = `${W}px`;
      canvas.style.height = `${H}px`;
      alpha = Math.max(alpha, 0.05);
    };

    const nodes: N[] = data.nodes.map((n, i) => {
      const a = (i / Math.max(1, data.nodes.length)) * Math.PI * 2;
      const r = 80 + (i % 7) * 18;
      return { ...n, x: Math.cos(a) * r, y: Math.sin(a) * r, vx: 0, vy: 0, deg: 0 };
    });
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const edges = data.edges.map((e) => ({ s: byId.get(e.source)!, t: byId.get(e.target)!, label: e.label })).filter((e) => e.s && e.t);
    edges.forEach((e) => {
      e.s.deg++;
      e.t.deg++;
    });
    const neighbours = new Map<string, Set<string>>();
    edges.forEach((e) => {
      if (!neighbours.has(e.s.id)) neighbours.set(e.s.id, new Set());
      if (!neighbours.has(e.t.id)) neighbours.set(e.t.id, new Set());
      neighbours.get(e.s.id)!.add(e.t.id);
      neighbours.get(e.t.id)!.add(e.s.id);
    });

    let view = { x: 0, y: 0, k: 1 };
    let alpha = 1;
    let hovered: N | null = null;
    let dragging: N | null = null;
    let panning: { x: number; y: number; vx: number; vy: number } | null = null;
    let raf = 0;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const radius = (n: N) => 3.5 + Math.min(9, Math.sqrt(n.deg) * 2.2);

    const tick = () => {
      // repulsion (O(n²) is fine for ≤ 300 nodes)
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          let dx = a.x - b.x;
          let dy = a.y - b.y;
          let d2 = dx * dx + dy * dy;
          if (d2 < 0.01) {
            dx = Math.random() - 0.5;
            dy = Math.random() - 0.5;
            d2 = 0.25;
          }
          if (d2 > 90000) continue;
          const f = (900 / d2) * alpha;
          const d = Math.sqrt(d2);
          a.vx += (dx / d) * f;
          a.vy += (dy / d) * f;
          b.vx -= (dx / d) * f;
          b.vy -= (dy / d) * f;
        }
      }
      for (const e of edges) {
        const dx = e.t.x - e.s.x;
        const dy = e.t.y - e.s.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 1;
        const f = (d - 46) * 0.04 * alpha;
        e.s.vx += (dx / d) * f;
        e.s.vy += (dy / d) * f;
        e.t.vx -= (dx / d) * f;
        e.t.vy -= (dy / d) * f;
      }
      for (const n of nodes) {
        n.vx -= n.x * 0.004 * alpha;
        n.vy -= n.y * 0.004 * alpha;
        if (n.fixed) {
          n.vx = n.vy = 0;
          continue;
        }
        n.vx *= 0.6;
        n.vy *= 0.6;
        n.x += n.vx;
        n.y += n.vy;
      }
      alpha = Math.max(0, alpha * 0.985);
    };

    const css = getComputedStyle(wrap);
    const draw = () => {
      const text = css.getPropertyValue("--text").trim() || "#fff";
      const text3 = css.getPropertyValue("--text-3").trim() || "#888";
      const border = css.getPropertyValue("--border-strong").trim() || "rgba(128,128,128,.3)";
      const bg = css.getPropertyValue("--surface").trim() || "#111";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.translate(W / 2 + view.x, H / 2 + view.y);
      ctx.scale(view.k, view.k);
      const hl = hovered ? neighbours.get(hovered.id) ?? new Set() : null;
      ctx.lineWidth = 1 / view.k;
      for (const e of edges) {
        const on = hovered && (e.s === hovered || e.t === hovered);
        ctx.strokeStyle = on ? typeColor(hovered!.type, types) : border;
        ctx.globalAlpha = hovered ? (on ? 0.95 : 0.12) : 0.55;
        ctx.beginPath();
        ctx.moveTo(e.s.x, e.s.y);
        ctx.lineTo(e.t.x, e.t.y);
        ctx.stroke();
      }
      for (const n of nodes) {
        const dim = hovered && n !== hovered && !hl!.has(n.id);
        ctx.globalAlpha = dim ? 0.2 : 1;
        const r = radius(n);
        ctx.fillStyle = typeColor(n.type, types);
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.lineWidth = 1.5 / view.k;
        ctx.strokeStyle = bg;
        ctx.stroke();
        if (n.type === "superseded") {
          ctx.strokeStyle = text3;
          ctx.beginPath();
          ctx.moveTo(n.x - r, n.y);
          ctx.lineTo(n.x + r, n.y);
          ctx.stroke();
        }
        if (view.k > 0.85 && (n.deg > 2 || n === hovered || (hl && hl.has(n.id)) || view.k > 1.6)) {
          ctx.font = `${11 / Math.max(view.k, 1)}px var(--font-inter), system-ui, sans-serif`;
          ctx.fillStyle = n === hovered ? text : text3;
          ctx.fillText(n.label, n.x + r + 3, n.y + 3.5);
        }
      }
      ctx.globalAlpha = 1;
    };

    const loop = () => {
      if (alpha > 0.002 && !reduce) tick();
      draw();
      raf = requestAnimationFrame(loop);
    };
    resize();
    if (reduce) for (let i = 0; i < 300; i++) tick();
    loop();

    const toWorld = (cx: number, cy: number) => {
      const r = canvas.getBoundingClientRect();
      return { x: (cx - r.left - W / 2 - view.x) / view.k, y: (cy - r.top - H / 2 - view.y) / view.k };
    };
    const pick = (cx: number, cy: number) => {
      const p = toWorld(cx, cy);
      let best: N | null = null;
      let bd = Infinity;
      for (const n of nodes) {
        const d = Math.hypot(n.x - p.x, n.y - p.y);
        if (d < radius(n) + 5 / view.k && d < bd) {
          best = n;
          bd = d;
        }
      }
      return best;
    };
    const onDown = (e: PointerEvent) => {
      canvas.setPointerCapture(e.pointerId);
      const n = pick(e.clientX, e.clientY);
      if (n) {
        dragging = n;
        n.fixed = true;
        alpha = Math.max(alpha, 0.3);
      } else panning = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
    };
    const onMove = (e: PointerEvent) => {
      if (dragging) {
        const p = toWorld(e.clientX, e.clientY);
        dragging.x = p.x;
        dragging.y = p.y;
        alpha = Math.max(alpha, 0.15);
      } else if (panning) {
        view = { ...view, x: panning.vx + e.clientX - panning.x, y: panning.vy + e.clientY - panning.y };
      } else {
        const n = pick(e.clientX, e.clientY);
        hovered = n;
        canvas.style.cursor = n ? "pointer" : "grab";
        const r = canvas.getBoundingClientRect();
        setHover(n ? { n, x: e.clientX - r.left, y: e.clientY - r.top } : null);
      }
    };
    const onUp = () => {
      if (dragging) {
        onSelect?.(dragging.id);
        dragging.fixed = false;
      }
      dragging = null;
      panning = null;
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = canvas.getBoundingClientRect();
      const mx = e.clientX - r.left - W / 2;
      const my = e.clientY - r.top - H / 2;
      const k = Math.min(4, Math.max(0.3, view.k * Math.exp(-e.deltaY * 0.0015)));
      view = { k, x: mx - ((mx - view.x) * k) / view.k, y: my - ((my - view.y) * k) / view.k };
    };
    const onLeave = () => {
      hovered = null;
      setHover(null);
    };
    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerup", onUp);
    canvas.addEventListener("pointerleave", onLeave);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    const ro = new ResizeObserver(resize);
    ro.observe(wrap);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("pointerleave", onLeave);
      canvas.removeEventListener("wheel", onWheel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, height]);

  return (
    <div ref={wrapRef} className="relative w-full select-none overflow-hidden" style={{ height }}>
      <canvas ref={canvasRef} className="block touch-none" style={{ cursor: "grab" }} />
      {hover ? (
        <div className="glass-strong pointer-events-none absolute z-10 px-2.5 py-1.5 text-[12px]" style={{ left: Math.min(hover.x + 12, (wrapRef.current?.clientWidth ?? 400) - 200), top: hover.y + 12, borderRadius: 10 }}>
          <p className="font-medium text-ink">{hover.n.label}</p>
          <p className="text-[11px] text-ink-3">
            {hover.n.type} · {hover.n.deg} link{hover.n.deg === 1 ? "" : "s"}
          </p>
        </div>
      ) : null}
      <div className="absolute bottom-2.5 left-3 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-ink-3">
        {[...types, ...(data.nodes.some((n) => n.type === "superseded") ? ["superseded"] : [])].map((t) => (
          <span key={t} className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: typeColor(t, types) }} />
            {t}
          </span>
        ))}
      </div>
      <p className="absolute bottom-2.5 right-3 hidden text-[11px] text-ink-3 sm:block">drag · scroll to zoom</p>
    </div>
  );
}
