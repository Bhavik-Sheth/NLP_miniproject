"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { UserButton, useAuth, useUser } from "@clerk/nextjs";
import { api, setApiTokenGetter, type Health } from "@/lib/api";
import { setDemoMode } from "@/lib/demo";
import DemoLive from "@/components/DemoLive";
import TalkScreen from "@/components/TalkScreen";
import ObservationsScreen from "@/components/ObservationsScreen";
import ScenariosScreen from "@/components/ScenariosScreen";
import EnrollScreen from "@/components/EnrollScreen";
import WorkflowIntro from "@/components/WorkflowIntro";
import { VesperLogo, LiveBadge } from "@/components/ui";

const ConversationScreen = dynamic(
  () => import("@/components/ConversationScreen"),
  {
    ssr: false,
    loading: () => (
      <div className="flex flex-col items-center justify-center p-12 text-sm text-zinc-400 gap-3">
        <svg
          className="animate-spin h-5 w-5 text-zinc-300"
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8v8H4z"
          />
        </svg>
        <span>Connecting live voice pipeline…</span>
      </div>
    ),
  },
);

export type Tab = "talk" | "live" | "observations" | "scenarios" | "enroll";

const TABS: { key: Tab; label: string }[] = [
  { key: "live", label: "Live" },
  { key: "talk", label: "Talk" },
  { key: "observations", label: "Logs" },
  { key: "scenarios", label: "Scenarios" },
  { key: "enroll", label: "Enroll" },
];

/** The operational console. `/app` runs it against the backend for a signed-in user;
 *  `/demo` runs it on recorded engine output (lib/demo.ts) with no sign-in and no writes. */
export default function Console({ demo = false }: { demo?: boolean }) {
  setDemoMode(demo); // before any effect issues an API call
  const { getToken, userId: clerkUserId } = useAuth();
  const userId = demo ? "demo" : (clerkUserId || "local-demo");
  const { user } = useUser();
  // Live voice is the product's primary surface; typed Talk is the dependable fallback.
  const [tab, setTab] = useState<Tab>("live");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [voiceEnrolled, setVoiceEnrolled] = useState<boolean | null>(null);
  const [commandsUsed, setCommandsUsed] = useState(0);
  const [commandLimit, setCommandLimit] = useState<number | null>(null);

  // Every API call asks Clerk for a fresh (cached) token rather than reusing a stale one.
  useEffect(() => {
    if (demo) return;
    setApiTokenGetter(() => getToken());
    return () => setApiTokenGetter(null);
  }, [getToken, demo]);

  // One session per signed-in user. The effect used to depend on the Clerk `user` object,
  // whose identity changes on every profile refresh, so it kept minting new sessions and the
  // console lost its conversation memory mid-flow.
  const email = user?.primaryEmailAddress?.emailAddress;
  const startedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!userId || startedFor.current === userId) return;
    startedFor.current = userId;
    const seed = email && !demo ? api.bootstrapDemo(email).catch(() => undefined) : Promise.resolve();
    void seed
      .then(() => api.createSession())
      .then((r) => {
        setSessionId(r.sessionId);
        setCommandsUsed(r.commandsUsed);
        setCommandLimit(r.commandLimit);
      })
      .catch((e: Error) => {
        startedFor.current = null;
        setSessionError(`Session start failed: ${e.message}`);
      });
    api.health().then(setHealth).catch(() => undefined);
    api.voiceStatus().then((s) => setVoiceEnrolled(s.enrolled)).catch(() => undefined);
  }, [userId, email, demo]);

  const onEnrolledChange = useCallback(
    (enrolled: boolean) => setVoiceEnrolled(enrolled),
    [],
  );

  const getSystemStatus = (): { state: "ok" | "check" | "alert"; label: string } => {
    if (sessionError) return { state: "alert", label: "OFFLINE" };
    if (!sessionId) return { state: "check", label: "CONNECTING" };
    return { state: "ok", label: "LIVE MEMORY" };
  };

  const status = getSystemStatus();

  return (
    <>
      {/* Animated Film Grain Overlay */}
      <div className="grain" aria-hidden="true" />

      {/* Subtle Ambient Background Light */}
      <div
        className="fixed top-0 left-1/2 -translate-x-1/2 w-[500px] h-[240px] pointer-events-none opacity-20 -z-10"
        style={{
          background:
            "radial-gradient(ellipse at 50% 0%, rgba(186, 208, 255, 0.25), transparent 70%)",
        }}
      />

      <div className="app-shell px-3 pt-3">
        {/* Top App Header Bar */}
        <header className="sticky top-0 z-40 mb-3 flex items-center justify-between rounded-xl px-3.5 py-2.5 backdrop-blur-xl border border-white/10 bg-black/60 shadow-[0_4px_20px_rgba(0,0,0,0.5)]">
          <div className="flex items-center gap-2.5">
            <Link href="/" className="hover:opacity-80 transition-opacity">
              <VesperLogo size={20} />
            </Link>
          </div>

          <div className="flex items-center gap-2.5">
            <WorkflowIntro setTab={setTab} demo={demo} />
            {demo && !clerkUserId && !process.env.NEXT_PUBLIC_STATIC_DEMO ? (
              <Link href="/sign-in" className="rounded border border-white/20 bg-white px-2 py-1 text-[11px] font-medium text-black">
                Sign in
              </Link>
            ) : null}
            <UserButton
              appearance={{
                elements: { avatarBox: "h-7 w-7" },
              }}
            />
            <LiveBadge state={status.state} label={status.label} />
          </div>
        </header>

        {demo ? (
          <div className="mb-3 rounded-lg border border-sky-300/20 bg-sky-300/[0.06] px-3 py-2 text-[11px] leading-relaxed text-sky-100/90">
            <span className="font-medium text-white">Recorded demo.</span> Every reply is real engine output on the
            Pithoragarh hospital project, and Vesper&apos;s voice is real Rime audio. Nothing is sent or saved.
          </div>
        ) : null}

        {/* Main App Content View */}
        <main className="flex-1 pb-24">
          {tab === "talk" ? (
            <TalkScreen
              sessionId={sessionId}
              health={health}
              sessionError={sessionError}
              voiceEnrolled={voiceEnrolled}
              onGoToEnroll={() => setTab("enroll")}
              commandsRemaining={commandLimit === null ? undefined : Math.max(0, commandLimit - commandsUsed)}
              onCommandUsed={() => setCommandsUsed((used) => commandLimit === null ? used : Math.min(commandLimit, used + 1))}
            />
          ) : null}
          {tab === "live" ? (demo ? <DemoLive /> : <ConversationScreen />) : null}
          {tab === "observations" ? <ObservationsScreen /> : null}
          {tab === "scenarios" ? <ScenariosScreen /> : null}
          {tab === "enroll" ? (
            <EnrollScreen onEnrolledChange={onEnrolledChange} />
          ) : null}
        </main>

        {/* Floating Liquid-Metal Dock Navigation */}
        <nav
          id="workflow-navigation"
          aria-label="Primary Navigation"
          className="fixed inset-x-0 bottom-3 z-40 mx-auto w-[calc(100%-24px)] max-w-[430px]"
        >
          <div className="flex items-center justify-between gap-1 rounded-xl border border-white/15 bg-black/75 p-1.5 backdrop-blur-2xl shadow-[0_12px_36px_rgba(0,0,0,0.85),inset_0_1px_0_rgba(255,255,255,0.12)]">
            {TABS.map((t) => {
              const active = tab === t.key;
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  aria-current={active ? "page" : undefined}
                  className={`nav-pill flex-1 text-center transition-all ${
                    active
                      ? "nav-pill-active font-medium"
                      : "opacity-70 hover:opacity-100"
                  }`}
                >
                  <span>{t.label}</span>
                </button>
              );
            })}
          </div>
        </nav>
      </div>
    </>
  );
}
