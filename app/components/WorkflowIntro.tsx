"use client";

import { useCallback, useEffect, useRef } from "react";
import { driver, type Driver, type DriveStep } from "driver.js";
import { useUser } from "@clerk/nextjs";
import "driver.js/dist/driver.css";
import type { Tab } from "@/components/Console";

const TOUR_KEY = "vesper-tour-v2";

type TourStep = {
  tab: Tab;
  element?: string;
  kicker: string;
  title: string;
  body: string;
  say?: string[];
  side?: "top" | "bottom" | "left" | "right";
  /** runs after the tab is shown, before the step is highlighted */
  before?: () => void;
};

const say = (lines: string[]) =>
  `<div class="tour-say">${lines.map((l) => `<span>“${l}”</span>`).join("")}</div>`;

function html(s: TourStep, i: number, total: number) {
  return `
    <p class="tour-body">${s.body}</p>
    ${s.say?.length ? say(s.say) : ""}
    <div class="tour-bar"><i style="width:${((i + 1) / total) * 100}%"></i></div>`;
}

function buildSteps(demo: boolean): TourStep[] {
  const liveConnected = demo || !!document.querySelector("#tour-live-controls");
  const live: TourStep[] = liveConnected
    ? [
        {
          tab: "live", element: "#tour-live-controls", kicker: "Live voice", side: "bottom",
          title: "Talk hands-free, like a radio",
          body: "Vesper listens continuously and answers out loud through Rime. The <b>mic button mutes <i>you</i></b> — tap it while you walk past a breaker or grinder so site noise is never transcribed or cuts Vesper off.",
          before: () => window.dispatchEvent(new Event("vesper-demo-finish")),
        },
        {
          tab: "live", element: "#tour-site-memory", kicker: "Site memory", side: "bottom",
          title: "It opens with memory, not a menu",
          body: "Before it says a word it has read the latest DPRs, open RFIs, hold points and permits. The greeting is the state of <i>your</i> job — here, the L4 slab pre-pour still on hold.",
        },
        {
          tab: "live", element: "#tour-live-transcript", kicker: "Ask or report", side: "top",
          title: "Questions get answers. Claims get checked.",
          body: "Ask anything the record knows — follow-ups keep context. Report a measurement and it is checked against the latest <b>For Construction</b> revision before anything is written.",
          say: ["What is the cover at E-1?", "and at E-2?", "E-1 column cover measured 30 mm"],
        },
        {
          tab: "live", element: "#tour-live-evidence", kicker: "The safety gate", side: "top",
          title: "It argues with you — with citations",
          body: "30 mm against 40 ± 5 on A-201 R1 is a contradiction. Vesper says so, names the drawing, revision, date and IS clause, and <b>refuses to log until you decide</b>. Every number comes from SQLite, not the model.",
        },
        {
          tab: "live", element: "#tour-live-decisions", kicker: "Decide", side: "top",
          title: "Tap it or say it",
          body: "Only the choices the rules allow are offered — a permit or hold-point blocker leaves just <i>stop work · NCR · cancel</i>. Writes also need your verified voiceprint.",
          say: ["Raise an NCR", "Log it", "Stop the work"],
        },
      ]
    : [
        {
          tab: "live", element: "#tour-live-start", kicker: "Live voice", side: "bottom",
          title: "Start a hands-free conversation",
          body: "Vesper greets you with the state of the site, answers questions, and challenges any observation that contradicts the latest drawings — out loud. Inside the room, the small mic button mutes <i>your</i> mic.",
          say: ["What should I check before the L4 slab pour?", "E-1 column cover measured 30 mm"],
        },
      ];
  return [
    {
      tab: "live", kicker: "Welcome", title: "Vesper checks before it logs",
      body: "A voice colleague that already knows this project. You speak, it cross-checks drawings, RFIs, permits and hold points, and nothing wrong gets written. Two minutes — let’s walk it.",
    },
    ...live,
    {
      tab: "talk", element: "#workflow-language", kicker: "Talk", side: "bottom",
      title: "Push-to-talk or type",
      body: "The dependable fallback when the network is patchy. English or Hinglish replies, same engine, same safety rules.",
    },
    {
      tab: "talk", element: "#workflow-suggestions", kicker: "Try it", side: "top",
      title: "One tap to try a real flow",
      body: "Each prompt runs the real engine: an answer from the record, a blocked pour, a revision mismatch.",
      before: demo ? () => window.dispatchEvent(new CustomEvent("vesper-demo-send", { detail: "E-1 column cover measured 30 mm" })) : undefined,
    },
    {
      tab: "talk", element: demo ? "#tour-talk-choose" : "#workflow-review-area", kicker: "Choose", side: "top",
      title: "Answer with a tap",
      body: "Whenever Vesper asks something — which level, is that right, log or RFI — the options appear as buttons. No need to speak a one-word reply on a noisy slab.",
    },
    {
      tab: "observations", element: "#tour-logs", kicker: "Logs", side: "top",
      title: "Every log is a foreign key, not a paragraph",
      body: "Each observation is linked to the verified drawing revision, location and decision — with the clarification Vesper spoke before it was allowed.",
    },
    {
      tab: "scenarios", element: "#tour-scenarios", kicker: "Proof", side: "bottom",
      before: () => (document.querySelector("#tour-scenarios-run") as HTMLButtonElement | null)?.click(),
      title: "Measurably safe",
      body: "Ten scripted site conversations with deliberate errors and mid-sentence corrections. The bar is <b>zero wrong logs</b>, every run.",
    },
    {
      tab: "enroll", element: "#tour-enroll", kicker: "Voiceprint", side: "bottom",
      title: "Only the enrolled manager can write",
      body: "Record three short samples. A local SpeechBrain model checks every voice turn; an unknown voice can ask questions but can’t log, raise or stop anything.",
    },
    {
      tab: "enroll", element: "#tour-guide", kicker: "Done", side: "bottom",
      title: "Replay this anytime",
      body: demo ? "That was the recorded demo. Sign in to talk to Vesper live on this project." : "You’re set. Enroll your voice, then open Live and say what you’re looking at.",
    },
  ];
}

async function waitFor(selector: string | undefined, ms = 4000) {
  if (!selector) return;
  const t0 = performance.now();
  while (!document.querySelector(selector) && performance.now() - t0 < ms) {
    await new Promise((r) => setTimeout(r, 60));
  }
}

/** Guided, tab-hopping walkthrough of the whole console. Auto-runs once per user. */
export default function WorkflowIntro({ setTab, demo = false }: { setTab: (t: Tab) => void; demo?: boolean }) {
  const { user } = useUser();
  const tourRef = useRef<Driver | null>(null);
  const tourKey = `${TOUR_KEY}-${demo ? "demo" : user?.id ?? "anonymous"}`;

  const startTour = useCallback(() => {
    tourRef.current?.destroy();
    const steps = buildSteps(demo);
    let current: Tab | null = null;

    const go = async (i: number, d: Driver) => {
      const s = steps[i];
      if (!s) return d.destroy();
      if (s.tab !== current) {
        setTab(s.tab);
        current = s.tab;
        await new Promise((r) => setTimeout(r, 120));
      }
      s.before?.();
      await waitFor(s.element);
      d.moveTo(i);
    };

    const driveSteps: DriveStep[] = steps.map((s, i) => ({
      element: s.element,
      popover: {
        title: `<div class="tour-kicker"><span>${s.kicker}</span><span>${i + 1} / ${steps.length}</span></div>${s.title}`,
        description: html(s, i, steps.length),
        side: s.side,
        align: "center",
        showButtons: i === 0 ? ["next", "close"] : ["previous", "next", "close"],
      },
    }));

    const tour = driver({
      animate: true,
      allowClose: true,
      smoothScroll: false, // smooth scrolling left popovers positioned against a moving target
      overlayColor: "#000",
      overlayOpacity: 0.72,
      stagePadding: 6,
      stageRadius: 12,
      showProgress: false,
      popoverClass: "vesper-tour",
      nextBtnText: "Next →",
      prevBtnText: "←",
      doneBtnText: demo ? "Explore the demo" : "Start",
      steps: driveSteps,
      onNextClick: (_el, _step, { driver: d }) => {
        const i = d.getActiveIndex() ?? 0;
        if (i >= steps.length - 1) return d.destroy();
        void go(i + 1, d);
      },
      onPrevClick: (_el, _step, { driver: d }) => void go(Math.max(0, (d.getActiveIndex() ?? 1) - 1), d),
      onDestroyed: () => {
        try {
          window.localStorage.setItem(tourKey, "true");
        } catch {
          /* private mode */
        }
      },
    });
    tourRef.current = tour;
    setTab("live");
    current = "live";
    window.setTimeout(() => tour.drive(0), 150);
  }, [demo, setTab, tourKey]);

  useEffect(() => {
    if (!demo && !user) return;
    let seen = false;
    try {
      seen = !!window.localStorage.getItem(tourKey);
    } catch {
      /* private mode */
    }
    if (seen) return;
    const timeout = window.setTimeout(startTour, 600);
    return () => {
      window.clearTimeout(timeout);
      tourRef.current?.destroy();
    };
  }, [startTour, tourKey, user, demo]);

  return (
    <button
      id="tour-guide"
      type="button"
      onClick={startTour}
      className="rounded border border-white/10 bg-white/5 px-2 py-1 text-[11px] font-mono text-zinc-400 transition-colors hover:border-white/30 hover:text-white"
      aria-label="Show the guided tour"
    >
      Guide
    </button>
  );
}
