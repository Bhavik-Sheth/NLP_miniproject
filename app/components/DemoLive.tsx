"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Card, WaveVisualizer } from "@/components/ui";
import SiteMemoryPanel, { type SiteBrief } from "@/components/SiteMemoryPanel";
import { DEMO_LIVE } from "@/lib/demo";
import { clipUrl, loadManifest, playClip, stopClip, unlockAudio } from "@/lib/demo-audio";
import data from "@/lib/demo-data.json";

type Evidence = { drawing_number?: string; revision?: string; issued_on?: string; expected?: number; tolerance?: number; claimed?: number; unit?: string; code_ref?: string };
type Issue = { kind: string; detail: string; evidence?: Evidence };

const LABELS: Record<string, string> = {
  log_observation: "Log observation",
  raise_rfi: "Raise RFI",
  raise_ncr: "Raise NCR",
  cancel: "Cancel",
};

const NCR_DONE = (data.flows as unknown as Record<string, { decision?: string; response: { reply: { text: string } } }[]>)
  .cover_ncr.find((s) => s.decision === "raise_ncr")?.response.reply.text;

const SCRIPT = DEMO_LIVE.script;
const ENGINE = (DEMO_LIVE.engine ?? {}) as { contradictions?: Issue[]; allowedDecisions?: string[] };
const ISSUES = ENGINE.contradictions ?? [];
const ALLOWED = ENGINE.allowedDecisions ?? [];
const EV = ISSUES[0]?.evidence;
/** the Vesper line that flags the contradiction; evidence cards appear once it has been spoken */
const FLAG_MARK = "You reported cover";

const WORDS = SCRIPT.map((r) => r.text.split(/\s+/).filter(Boolean));
const TOTAL_CHARS = SCRIPT.reduce((n, r) => n + r.text.length, 0);

const USER_WORD_MS = 1000 / 2.8; // live transcription pace of the manager speaking
const VESPER_WORD_MS = 55; // silent reveal pace
const CLIP_FALLBACK_WORD_MS = 60; // clip playing but no duration yet
const THINK_MS = 450;

type Activity = "ready" | "listening" | "user" | "thinking" | "speaking";
type View = {
  phase: "idle" | "running" | "done";
  /** fully spoken lines */
  shown: number;
  /** line currently being spoken and how many of its words are out */
  live: { idx: number; words: number } | null;
  activity: Activity;
  /** the current Vesper line is real Rime audio */
  voiced: boolean;
  evidence: boolean;
  /** waiting for the manager to unmute */
  held: boolean;
  /** the call played to the end (vs. being skipped to the end by the tour) */
  natural: boolean;
};

const IDLE: View = { phase: "idle", shown: 0, live: null, activity: "ready", voiced: false, evidence: false, held: false, natural: false };
const FINISHED: View = { ...IDLE, phase: "done", shown: SCRIPT.length, activity: "listening", evidence: true };

const prefersReducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/**
 * The Live screen for the public demo: replays a recorded live conversation (real engine output,
 * see scripts/build_demo_data.py) as a call — the manager's lines stream in like live
 * transcription, Vesper's replies play as pre-rendered Rime clips when they exist.
 */
export default function DemoLive() {
  const [view, setView] = useState<View>(IDLE);
  const [micOn, setMicOn] = useState(true);
  const [soundOn, setSoundOn] = useState(true);
  const [decided, setDecided] = useState<string | null>(null);
  const [ncrSpeaking, setNcrSpeaking] = useState(false);

  const runId = useRef(0);
  const timers = useRef(new Set<number>());
  const intervals = useRef(new Set<number>());
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const micRef = useRef(true);
  const soundRef = useRef(true);
  const reducedRef = useRef(false);
  const unmuteWaiters = useRef<(() => void)[]>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const evidenceRef = useRef<HTMLDivElement | null>(null);
  const decisionsRef = useRef<HTMLDivElement | null>(null);

  const patch = useCallback((p: Partial<View> | ((v: View) => Partial<View>)) => {
    setView((v) => ({ ...v, ...(typeof p === "function" ? p(v) : p) }));
  }, []);

  /** stop everything in flight: timeline, word timers, audio */
  const cancel = useCallback(() => {
    runId.current += 1;
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current.clear();
    intervals.current.forEach((t) => window.clearInterval(t));
    intervals.current.clear();
    stopClip(audioRef.current);
    const waiters = unmuteWaiters.current;
    unmuteWaiters.current = [];
    waiters.forEach((w) => w()); // let parked loops notice they're cancelled
  }, []);

  const finish = useCallback(() => {
    cancel();
    setNcrSpeaking(false);
    setView(FINISHED);
  }, [cancel]);

  const run = useCallback(
    async (id: number) => {
      const alive = () => runId.current === id;
      const sleep = (ms: number) =>
        new Promise<void>((res) => {
          const t = window.setTimeout(() => {
            timers.current.delete(t);
            res();
          }, ms);
          timers.current.add(t);
        });
      const micGate = async () => {
        if (micRef.current) return;
        patch({ held: true });
        await new Promise<void>((res) => unmuteWaiters.current.push(res));
        if (alive()) patch({ held: false });
      };
      const reduced = reducedRef.current;

      /** play a clip, revealing words in step with it; resolves with how many words got out */
      const speakClip = (url: string, idx: number) =>
        new Promise<{ ok: boolean; words: number }>((resolve) => {
          const n = WORDS[idx].length;
          let duration = 0;
          let words = reduced ? n : 0;
          let lastT = -1;
          let stalledSince = performance.now();
          let poll = 0;
          const end = (ok: boolean) => {
            window.clearInterval(poll);
            intervals.current.delete(poll);
            resolve({ ok, words });
          };
          const audio = playClip(url, {
            audio: audioRef.current,
            muted: !soundRef.current,
            onStart: (d) => {
              duration = d;
            },
            onEnd: (failed) => end(!failed),
          });
          audioRef.current = audio;
          poll = window.setInterval(() => {
            if (!alive()) {
              window.clearInterval(poll);
              intervals.current.delete(poll);
              return;
            }
            const t = audio.currentTime;
            const now = performance.now();
            if (t !== lastT) {
              lastT = t;
              stalledSince = now;
            } else if (now - stalledSince > 4000) {
              stopClip(audio); // stalled clip: finish the line silently
              end(false);
              return;
            }
            if (reduced) return;
            const d = duration || (Number.isFinite(audio.duration) ? audio.duration : 0);
            const next = Math.min(n, d > 0 ? Math.ceil((t / d) * n) : Math.floor((t * 1000) / CLIP_FALLBACK_WORD_MS));
            if (next > words) {
              words = next;
              patch({ live: { idx, words } });
            }
          }, 50);
          intervals.current.add(poll);
        });

      loadManifest(); // warm the cache while the greeting starts
      for (let i = 0; i < SCRIPT.length; i++) {
        if (!alive()) return;
        const row = SCRIPT[i];
        const n = WORDS[i].length;

        if (row.who === "You") {
          await micGate();
          if (!alive()) return;
          patch({ activity: "listening", live: null, voiced: false });
          await sleep(reduced ? 250 : 650);
          if (!reduced) {
            for (let w = 1; w <= n; w++) {
              await micGate(); // a muted manager can't speak: the line waits mid-sentence
              if (!alive()) return;
              patch({ activity: "user", live: { idx: i, words: w } });
              await sleep(USER_WORD_MS);
            }
          }
          if (!alive()) return;
          patch({ shown: i + 1, live: null, activity: "thinking" });
          await sleep(THINK_MS);
          continue;
        }

        // Vesper speaks
        const url = soundRef.current ? await clipUrl(row.text) : null;
        if (!alive()) return;
        patch({ activity: "speaking", voiced: !!url, live: { idx: i, words: reduced ? n : 0 } });
        let words = 0;
        if (url) {
          const r = await speakClip(url, i);
          if (!alive()) return;
          words = r.ok ? n : r.words;
          if (!r.ok) patch({ voiced: false });
        }
        if (reduced && words < n) await sleep(900);
        for (let w = words + 1; w <= n && !reduced; w++) {
          patch({ live: { idx: i, words: w } });
          await sleep(VESPER_WORD_MS);
          if (!alive()) return;
        }
        if (!alive()) return;
        const flags = row.text.includes(FLAG_MARK);
        patch((v) => ({ shown: i + 1, live: null, voiced: false, activity: "listening", evidence: v.evidence || flags }));
        await sleep(flags ? 700 : 400);
      }
      if (alive()) patch({ phase: "done", activity: "listening", live: null, held: false, natural: true });
    },
    [patch],
  );

  const start = useCallback(
    (withSound: boolean) => {
      cancel();
      reducedRef.current = prefersReducedMotion();
      soundRef.current = withSound;
      setSoundOn(withSound);
      // this click is the gesture that lets later clips play (iOS needs the element unlocked here)
      if (withSound && !audioRef.current) audioRef.current = unlockAudio();
      setDecided(null);
      setNcrSpeaking(false);
      setView({ ...IDLE, phase: "running", activity: "listening" });
      void run(runId.current);
    },
    [cancel, run],
  );

  const toggleMic = () => {
    const on = !micRef.current;
    micRef.current = on;
    setMicOn(on);
    if (on) {
      const waiters = unmuteWaiters.current;
      unmuteWaiters.current = [];
      waiters.forEach((w) => w());
    }
  };

  const toggleSound = () => {
    const on = !soundRef.current;
    soundRef.current = on;
    setSoundOn(on);
    if (on && !audioRef.current) audioRef.current = unlockAudio();
    if (audioRef.current) audioRef.current.muted = !on;
  };

  const decide = (d: string) => {
    if (d !== "raise_ncr") {
      setDecided(d === "cancel" ? "Cancelled. Nothing has been logged." : `${LABELS[d] ?? d} — in the live console this writes a linked record, tied to A-201 R1.`);
      return;
    }
    const text = NCR_DONE ?? "NCR raised.";
    setDecided(text);
    if (!soundRef.current || !NCR_DONE) return;
    if (!audioRef.current) audioRef.current = unlockAudio();
    const id = runId.current;
    void clipUrl(NCR_DONE).then((url) => {
      if (!url || runId.current !== id) return;
      setNcrSpeaking(true);
      audioRef.current = playClip(url, {
        audio: audioRef.current,
        muted: !soundRef.current,
        onEnd: () => setNcrSpeaking(false),
      });
    });
  };

  useEffect(() => {
    // the guided tour skips the replay so its later steps have something to point at
    window.addEventListener("vesper-demo-finish", finish);
    // remounted mid-tour (tab hop back to Live): land in the finished state straight away
    const t = window.setTimeout(() => {
      if (document.body.classList.contains("driver-active")) finish();
    }, 0);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("vesper-demo-finish", finish);
      cancel();
    };
  }, [finish, cancel]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, [view.shown, view.live, view.activity]);

  // mid-call, bring the evidence and then the decisions into view as they arrive
  const running = view.phase === "running";
  useEffect(() => {
    if (running && view.evidence) evidenceRef.current?.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "nearest" });
  }, [running, view.evidence]);
  const done = view.phase === "done";
  useEffect(() => {
    if (done && view.natural) decisionsRef.current?.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "nearest" });
  }, [done, view.natural]);

  if (view.phase === "idle") {
    return (
      <div className="flex flex-col gap-3">
        <div className="glass-panel flex flex-col items-center px-6 py-8 text-center">
          <span className="mb-1 font-mono text-[10px] uppercase tracking-widest text-zinc-400">Recorded live session</span>
          <h2 className="text-xl font-medium tracking-tight text-white">
            Hear a <span className="editorial-em">site call</span>
          </h2>
          <p className="mt-2 max-w-[290px] text-xs leading-relaxed text-zinc-400">
            Replays a real session — Vesper&apos;s voice is real Rime audio (mistv3 · cove)
          </p>
          <div className="mic-shell mt-7">
            <button type="button" onClick={() => start(true)} className="mic-circle" aria-label="Start demo call">
              <MicIcon className="h-8 w-8 text-black" />
            </button>
          </div>
          <span className="mt-3 text-sm font-medium text-white">Start demo call</span>
          <button
            type="button"
            onClick={() => start(false)}
            className="mt-2 font-mono text-[11px] text-zinc-500 underline-offset-4 transition-colors hover:text-zinc-200 hover:underline"
          >
            Play silently
          </button>
        </div>
        <div id="tour-site-memory">
          <SiteMemoryPanel brief={DEMO_LIVE.brief as SiteBrief} />
        </div>
      </div>
    );
  }

  const { live, activity } = view;
  const speaking = ncrSpeaking || activity === "speaking";
  const userTalking = activity === "user";
  const label = !micOn
    ? "mic off"
    : speaking
      ? ncrSpeaking || view.voiced
        ? "speaking · Rime"
        : "speaking"
      : userTalking
        ? "you're speaking"
        : activity === "thinking"
          ? "checking"
          : "listening";
  const liveChars = live ? (SCRIPT[live.idx].text.length * live.words) / WORDS[live.idx].length : 0;
  const progress = done ? 1 : (SCRIPT.slice(0, view.shown).reduce((n, r) => n + r.text.length, 0) + liveChars) / TOTAL_CHARS;
  const liveRow = live ? SCRIPT[live.idx] : null;
  const fadeIn = "transition-[opacity,transform] duration-500 ease-out starting:translate-y-3 starting:opacity-0 motion-reduce:transition-none";

  return (
    <div className="flex flex-col gap-3">
      <div id="tour-live-controls" className="glass-panel relative overflow-hidden px-3 py-2">
        <div className="flex items-center gap-3">
          <span className={`p-live-dot ${!micOn ? "dot-red" : activity === "thinking" ? "dot-amber" : ""}`} />
          <span className="w-[104px] shrink-0 truncate font-mono text-[10px] uppercase tracking-wide text-zinc-400" aria-live="polite">
            {label}
          </span>
          <div className={`flex h-7 min-w-0 flex-1 items-center ${speaking ? "text-emerald-200" : userTalking && micOn ? "text-white" : "text-zinc-500"}`}>
            <WaveVisualizer active={speaking || (userTalking && micOn)} />
          </div>
          <button
            type="button"
            onClick={toggleSound}
            aria-pressed={!soundOn}
            aria-label={soundOn ? "Mute Vesper's voice" : "Unmute Vesper's voice"}
            title={soundOn ? "Sound on" : "Sound off"}
            className={`grid h-7 w-7 shrink-0 place-items-center rounded-full border transition ${
              soundOn ? "border-white/15 text-zinc-300 hover:text-white" : "border-white/10 text-zinc-600 hover:text-zinc-300"
            }`}
          >
            <SpeakerIcon on={soundOn} />
          </button>
          <button
            type="button"
            onClick={toggleMic}
            aria-pressed={!micOn}
            aria-label={micOn ? "Mute my microphone" : "Unmute my microphone"}
            className={`grid h-8 w-8 shrink-0 place-items-center rounded-full border transition ${
              micOn ? "border-white/20 bg-white/5 text-zinc-200 hover:bg-white/10" : "border-red-400/60 bg-red-500/20 text-red-200"
            }`}
          >
            <MicIcon className="h-4 w-4" off={!micOn} />
          </button>
          <button
            type="button"
            onClick={() => start(soundRef.current)}
            className="shrink-0 rounded-full border border-white/15 px-2.5 py-1 text-[11px] text-zinc-300 hover:text-white"
          >
            Replay
          </button>
        </div>
        <div className="absolute inset-x-0 bottom-0 h-px bg-white/5" aria-hidden>
          <div
            className="h-full bg-gradient-to-r from-white/30 to-emerald-300/80 transition-[width] duration-300 ease-linear motion-reduce:transition-none"
            style={{ width: `${Math.round(progress * 1000) / 10}%` }}
          />
        </div>
      </div>

      <p className="px-1 font-mono text-[10px] text-zinc-500">voice out: rime mistv3 · cove · websocket (pre-rendered clips in this demo)</p>

      <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 font-mono text-[11px] text-emerald-200">
        Voice verified · 0.86 — writes unlocked for this manager
      </div>

      <div id="tour-site-memory">
        <SiteMemoryPanel brief={DEMO_LIVE.brief as SiteBrief} />
      </div>

      <div id="tour-live-transcript">
        <Card title="Live transcript">
          <div ref={scrollRef} className="flex max-h-[380px] flex-col gap-2.5 overflow-y-auto">
            {SCRIPT.slice(0, view.shown).map((r, i) => (
              <Bubble key={i} who={r.who} text={r.text} />
            ))}
            {liveRow && live ? (
              <Bubble
                who={liveRow.who}
                text={WORDS[live.idx].slice(0, live.words).join(" ")}
                status={liveRow.who === "You" ? "speaking" : view.voiced ? "speaking · Rime" : "speaking"}
                live
              />
            ) : null}
            {running && activity === "listening" && !live && SCRIPT[view.shown]?.who === "You" ? (
              <div className="flex items-center gap-1.5 self-end px-1 font-mono text-[10px] text-zinc-500">
                {view.held ? (
                  <span className="text-red-300/90">mic off — unmute to keep talking</span>
                ) : (
                  <>
                    <span>listening</span>
                    <Dots />
                  </>
                )}
              </div>
            ) : null}
            {view.held && live && liveRow?.who === "You" ? (
              <span className="self-end px-1 font-mono text-[10px] text-red-300/90">mic off — unmute to keep talking</span>
            ) : null}
            {activity === "thinking" && running ? (
              <div className="flex items-center gap-2 self-start px-1 font-mono text-[10.5px] text-zinc-400">
                <svg className="h-3.5 w-3.5 animate-spin text-zinc-400 motion-reduce:animate-none" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                <span className="animate-pulse motion-reduce:animate-none">checking drawings…</span>
              </div>
            ) : null}
          </div>
        </Card>
      </div>

      {view.evidence && ISSUES.length ? (
        <div id="tour-live-evidence" ref={evidenceRef} className={`flex flex-col gap-3 ${fadeIn}`}>
          <Card tone="red" title="Contradiction">
            <ul className="space-y-1 text-xs text-red-100">
              {ISSUES.map((c, i) => (
                <li key={i}>• {c.detail}</li>
              ))}
            </ul>
          </Card>
          {EV ? (
            <Card title="Evidence from the record">
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-mono text-xs">
                <dt className="text-zinc-500">drawing</dt>
                <dd className="text-zinc-200">
                  {EV.drawing_number} {EV.revision} · issued {EV.issued_on}
                </dd>
                <dt className="text-zinc-500">expected</dt>
                <dd className="text-zinc-200">
                  {EV.expected} {EV.unit} ± {EV.tolerance}
                </dd>
                <dt className="text-zinc-500">you said</dt>
                <dd className="text-red-200">
                  {EV.claimed} {EV.unit}
                </dd>
                {EV.code_ref ? (
                  <>
                    <dt className="text-zinc-500">code</dt>
                    <dd className="text-zinc-200">{EV.code_ref}</dd>
                  </>
                ) : null}
              </dl>
            </Card>
          ) : null}
        </div>
      ) : null}

      {done ? (
        <div id="tour-live-decisions" ref={decisionsRef} className={fadeIn}>
          {decided ? (
            <Card tone="green" title="Logged">
              <p className="text-xs text-emerald-100">{decided}</p>
              {ncrSpeaking ? <p className="mt-1.5 font-mono text-[10px] text-emerald-300/80">Vesper · speaking · Rime</p> : null}
            </Card>
          ) : (
            <div className="flex flex-wrap gap-2">
              {ALLOWED.map((d) => (
                <Button key={d} size="sm" variant={d === "raise_ncr" ? "solid" : "ghost"} onClick={() => decide(d)}>
                  {LABELS[d] ?? d}
                </Button>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

function Bubble({ who, text, live = false, status }: { who: "You" | "Vesper"; text: string; live?: boolean; status?: string }) {
  return (
    <div className={`flex flex-col ${who === "You" ? "max-w-[88%] items-end self-end" : "max-w-[92%] items-start self-start"}`}>
      <span className="mb-0.5 px-1 font-mono text-[9.5px] text-zinc-500">
        {who}
        {live && status ? ` · ${status}` : ""}
      </span>
      <div className={who === "You" ? "bubble-user" : "bubble-agent"}>
        {text || " "}
        {live ? <span className="ml-0.5 inline-block h-[1em] w-[2px] translate-y-[2px] animate-pulse bg-current opacity-60 motion-reduce:animate-none" aria-hidden /> : null}
      </div>
    </div>
  );
}

function Dots() {
  return (
    <span className="flex gap-0.5" aria-hidden>
      {[0, 1, 2].map((i) => (
        <i key={i} className="h-1 w-1 animate-pulse rounded-full bg-zinc-500 motion-reduce:animate-none" style={{ animationDelay: `${i * 180}ms` }} />
      ))}
    </span>
  );
}

function MicIcon({ className = "", off = false }: { className?: string; off?: boolean }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" x2="12" y1="19" y2="22" />
      {off ? <line x1="3" y1="3" x2="21" y2="21" /> : null}
    </svg>
  );
}

function SpeakerIcon({ on }: { on: boolean }) {
  return (
    <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M11 5 6 9H2v6h4l5 4V5Z" />
      {on ? (
        <>
          <path d="M15.5 8.5a5 5 0 0 1 0 7" />
          <path d="M19 5a10 10 0 0 1 0 14" />
        </>
      ) : (
        <>
          <line x1="22" x2="16" y1="9" y2="15" />
          <line x1="16" x2="22" y1="9" y2="15" />
        </>
      )}
    </svg>
  );
}
