"use client";

import { useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { driver, type Driver } from "driver.js";
import { useUser } from "@clerk/nextjs";
import "driver.js/dist/driver.css";

const KEY = "vesper-dash-tour-v2";
const STATIC_DEMO = process.env.NEXT_PUBLIC_STATIC_DEMO === "1";

type Step = { href?: string; element?: string; kicker: string; title: string; body: string; side?: "top" | "bottom" | "left" | "right" };

const STEPS: Step[] = [
  { kicker: "Welcome", title: "Your project, on one screen", body: "Vesper checks every spoken site observation against the current drawings, RFIs, permits and hold points before anything is logged. This is the laptop view of that record." },
  { href: "/app", element: "#tour-dash-kpis", side: "bottom", kicker: "Overview", title: "What needs you today", body: "Open RFIs, active permits, hold points and memory size at a glance — every tile links to the full table." },
  { href: "/app", element: "#tour-dash-blockers", side: "top", kicker: "Blockers", title: "Nothing pours past a hold point", body: "Permits with unmet <b>mandatory</b> checks and unreleased hold points are listed here. The voice agent refuses to log work that ignores them." },
  { element: "#tour-dash-nav", side: "right", kicker: "Navigate", title: "Everything is two keys away", body: "Press <b>G</b> then a letter — <b>G L</b> for live voice, <b>G A</b> to ask the memory. Press <b>[</b> to collapse the sidebar." },
  { element: "#tour-dash-search", side: "bottom", kicker: "⌘K", title: "Search or just ask", body: "The command palette jumps anywhere, switches projects and themes — or type a question and send it straight to the project memory." },
  { href: "/app/live", element: "#tour-live-stage", side: "bottom", kicker: "Live voice", title: "Talk to the site record", body: "Start a hands-free call — Sarvam hears Hinglish, Rime speaks back. The transcript, contradiction evidence and a raw engine event log stream side by side." },
  { href: "/app/ask", element: "#tour-ask-box", side: "top", kicker: "Ask memory", title: "Answers with citations — or an honest no", body: "Every answer cites the IS clause, template, drawing or document it came from. If retrieval is too weak Vesper <b>abstains</b> instead of guessing." },
  { href: "/app/memory", element: "#tour-memory-models", side: "bottom", kicker: "Memory layer", title: "Local-first memory", body: "bge-m3 embeddings, a cross-encoder reranker, LanceDB vectors, BM25 and a Cognee knowledge graph — IS codes, 550 QA/QC templates, prices and this project’s own documents." },
  { href: "/app/memory", element: "#tour-memory-graph", side: "top", kicker: "Retrieval", title: "See why an answer was chosen", body: "Explore the knowledge graph, or probe the retriever: vector, BM25, fusion and rerank scores with latency for every leg." },
  { href: "/app/documents", element: "#tour-ingest", side: "right", kicker: "Ingest", title: "Upload, paste or just speak", body: "Drawing registers, specs, BOQs, method statements or a voice briefing — parsed, chunked, embedded and searchable in seconds." },
  { href: "/app/scenarios", element: "#tour-dash-scenarios", side: "top", kicker: "Proof", title: "Zero wrong logs, every run", body: "Ten scripted site conversations with deliberate errors and mid-sentence corrections. The bar is not “sounds right” — it is <b>0 wrong logs</b>." },
  { element: "#tour-dash-status", side: "bottom", kicker: "Status", title: "Always observable", body: "Backend, voice and memory health are live here. New client? Onboarding sets up the organization and project in minutes. Replay this tour from ⌘K any time." },
];

// The static export uses trailing slashes (/app/ask/), the dev server doesn't (/app/ask).
const here = () => window.location.pathname.replace(/\/+$/, "") || "/";

async function waitFor(sel?: string, ms = 4000) {
  if (!sel) return;
  const t0 = performance.now();
  while (!document.querySelector(sel) && performance.now() - t0 < ms) await new Promise((r) => setTimeout(r, 80));
}

export default function DashTour() {
  const router = useRouter();
  const { user } = useUser();
  const ref = useRef<Driver | null>(null);
  const storageKey = `${KEY}-${user?.id ?? "anon"}`;

  const start = useCallback(() => {
    ref.current?.destroy();
    const visible = STEPS.filter((s) => !s.element || s.element !== "#tour-dash-nav" || window.innerWidth >= 1024);
    const go = async (i: number, d: Driver) => {
      const s = visible[i];
      if (!s) return d.destroy();
      if (s.href && here() !== s.href) {
        router.push(s.href);
        await new Promise((r) => setTimeout(r, 250));
      }
      await waitFor(s.element);
      d.moveTo(i);
    };
    const tour = driver({
      animate: true,
      allowClose: true,
      smoothScroll: false,
      overlayColor: "#000",
      overlayOpacity: 0.55,
      stagePadding: 6,
      stageRadius: 12,
      popoverClass: "vesper-tour",
      nextBtnText: "Next →",
      prevBtnText: "←",
      doneBtnText: "Done",
      steps: visible.map((s, i) => ({
        element: s.element,
        popover: {
          title: `<div class="tour-kicker"><span>${s.kicker}</span><span>${i + 1} / ${visible.length}</span></div>${s.title}`,
          description: `<p class="tour-body">${s.body}</p><div class="tour-bar"><i style="width:${((i + 1) / visible.length) * 100}%"></i></div>`,
          side: s.side,
          align: "center",
          showButtons: i === 0 ? ["next", "close"] : ["previous", "next", "close"],
        },
      })),
      onNextClick: (_e, _s, { driver: d }) => {
        const i = d.getActiveIndex() ?? 0;
        if (i >= visible.length - 1) return d.destroy();
        void go(i + 1, d);
      },
      onPrevClick: (_e, _s, { driver: d }) => void go(Math.max(0, (d.getActiveIndex() ?? 1) - 1), d),
      onDestroyed: () => {
        try {
          localStorage.setItem(storageKey, "1");
        } catch {
          /* ignore */
        }
      },
    });
    ref.current = tour;
    if (here() !== "/app") router.push("/app");
    window.setTimeout(() => tour.drive(0), 300);
  }, [router, storageKey]);

  useEffect(() => {
    const on = () => start();
    window.addEventListener("vesper-dash-tour", on);
    return () => window.removeEventListener("vesper-dash-tour", on);
  }, [start]);

  useEffect(() => {
    // Signed-in users, the public static demo, and the local dev preview all get the first-visit tour.
    const devPreview = typeof document !== "undefined" && document.cookie.includes("vesper_dev_preview=1");
    if (!user && !STATIC_DEMO && !devPreview) return;
    // First-visit tour only auto-starts on Overview; deep links to other pages are never hijacked.
    if (here() !== "/app") return;
    try {
      if (localStorage.getItem(storageKey)) return;
    } catch {
      return;
    }
    const t = window.setTimeout(start, 1200);
    return () => window.clearTimeout(t);
  }, [user, storageKey, start]);

  return null;
}
