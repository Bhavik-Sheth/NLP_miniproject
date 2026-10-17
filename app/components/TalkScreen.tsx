"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type DecisionKey,
  type DecisionResponse,
  type Health,
  type TurnResponse,
} from "@/lib/api";
import { Card, Chip, ErrorBanner, Button, WaveVisualizer, VesperLogo } from "@/components/ui";
import CommandLimitReached from "@/components/CommandLimitReached";
import ConversationHistory from "@/components/ConversationHistory";
import { DEMO_PROMPTS, isDemo } from "@/lib/demo";

const DECISION_LABELS: Record<DecisionKey, string> = {
  log_observation: "Log observation",
  raise_rfi: "Raise RFI",
  raise_ncr: "Raise NCR",
  stop_work: "Stop work",
  cancel: "Cancel",
};

const LIVE_SUGGESTED = [
  "What should I check before the L4 slab pour?",
  "What is the cover at E-1?",
  "Any open RFIs?",
  "E-1 column cover measured 30 mm",
];

type QuickReply = { label: string; text: string };

/** Tap-able answers for whatever Vesper just asked, so a manager never has to speak or type
 *  a one-word reply. Derived only from the engine response (its candidates are DB rows). */
function quickReplies(r: TurnResponse | null): QuickReply[] {
  if (!r) return [];
  const out: QuickReply[] = [];
  if (r.state === "confirming" && (r.lowConfidence?.length ?? 0) > 0) {
    out.push({ label: "Yes, that's right", text: "yes" }, { label: "No", text: "no" });
  }
  const m = r.missing?.[0] as { evidence?: { field?: string; candidates?: string[] } } | undefined;
  const field = m?.evidence?.field;
  const cands = m?.evidence?.candidates ?? [];
  if (field === "level") {
    for (const id of cands.slice(0, 4)) {
      const lvl = id.split(":")[2] ?? "";
      out.push({ label: lvl.replace(/^L(\d+)$/, "Level $1"), text: lvl.replace(/^L(\d+)$/, "level $1") });
    }
  } else if (field === "element") {
    for (const c of cands.slice(0, 4)) out.push({ label: c, text: c });
  } else if (field === "attribute") {
    for (const a of ["spacing", "cover", "thickness"]) out.push({ label: a, text: a });
  } else if (field === "location_unknown") {
    for (const c of cands.slice(0, 6)) out.push({ label: c, text: c });
  }
  for (const c of r.contradictions ?? []) {
    const ev = c.evidence as { candidates?: string[] } | undefined;
    if (c.kind === "unknown_drawing") {
      for (const d of (ev?.candidates ?? []).slice(0, 4)) out.push({ label: d, text: `drawing ${d}` });
    }
  }
  return out;
}

// Minimal shape of the Web Speech API we use.
type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((ev: {
    resultIndex: number;
    results: ArrayLike<
      ArrayLike<{ transcript: string }> & { isFinal: boolean }
    >;
  }) => void) | null;
  onspeechstart: (() => void) | null;
  onerror: ((ev: { error: string }) => void) | null;
  onend: (() => void) | null;
};

function getSR(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    SpeechRecognition?: new () => SpeechRecognitionLike;
  };
  return w.webkitSpeechRecognition ?? w.SpeechRecognition ?? null;
}

export default function TalkScreen({
  sessionId,
  health,
  sessionError,
  voiceEnrolled,
  onGoToEnroll,
  commandsRemaining,
  onCommandUsed,
}: {
  sessionId: string | null;
  health: Health | null;
  sessionError: string | null;
  voiceEnrolled?: boolean | null;
  onGoToEnroll?: () => void;
  commandsRemaining?: number;
  onCommandUsed?: () => void;
}) {
  const [lang, setLang] = useState<"en-IN" | "hi-IN">("en-IN");
  const [listening, setListening] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState("");
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [resp, setResp] = useState<TurnResponse | null>(null);
  const [decisionResult, setDecisionResult] = useState<DecisionResponse | null>(
    null,
  );
  const [ttsMissing, setTtsMissing] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [limitReached, setLimitReached] = useState(false);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  // client-only capability detection — must NOT run during render (SSR hydration)
  const [mounted, setMounted] = useState(false);
  const [srSupported, setSrSupported] = useState(false);
  const [micSupported, setMicSupported] = useState(false);
  const sttViaServerRef = useRef(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const finalTranscriptRef = useRef("");
  const bargeInRef = useRef(false);
  const audioUrlRef = useRef<string | null>(null);

  useEffect(() => {
    setMounted(true);
    const sr = getSR() != null;
    setSrSupported(sr);
    setMicSupported(
      typeof navigator !== "undefined" &&
        !!navigator.mediaDevices &&
        typeof MediaRecorder !== "undefined",
    );
    sttViaServerRef.current = !sr; // no Web Speech API -> always transcribe server-side
  }, []);

  const stopPlayback = useCallback(() => {
    if (audioRef.current && !audioRef.current.paused) {
      audioRef.current.pause();
    }
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    setSpeaking(false);
  }, []);

  // Barge-in: if the agent is speaking, cut it and flag this turn.
  const maybeBargeIn = useCallback(() => {
    if (speaking || (audioRef.current && !audioRef.current.paused)) {
      bargeInRef.current = true;
      stopPlayback();
    }
  }, [speaking, stopPlayback]);

  const playTts = useCallback(
    async (text: string, language: "en-IN" | "hi-IN") => {
      if (!text) return;
      setTtsMissing(false);

      // Use Web Speech API directly in the browser
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(text);
        const voices = window.speechSynthesis.getVoices();
        const languagePrefix = language === "hi-IN" ? "hi" : "en";
        const preferred =
          voices.find((v) => v.lang.toLowerCase().replace("_", "-") === language.toLowerCase()) ||
          voices.find((v) => v.lang.toLowerCase().startsWith(languagePrefix));
        if (preferred) u.voice = preferred;
        u.lang = language;
        u.rate = 1.0;
        u.onstart = () => setSpeaking(true);
        u.onend = () => setSpeaking(false);
        u.onerror = () => setSpeaking(false);
        window.speechSynthesis.speak(u);
        return;
      }

      // Fallback to server TTS if SpeechSynthesis is not supported
      const out = await api.tts(text, language);
      if (out.ok) {
        if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
        const url = URL.createObjectURL(out.blob);
        audioUrlRef.current = url;
        let el = audioRef.current;
        if (!el) {
          el = new Audio();
          audioRef.current = el;
        }
        el.src = url;
        el.onplay = () => setSpeaking(true);
        el.onended = () => setSpeaking(false);
        el.onpause = () => setSpeaking(false);
        try {
          await el.play();
        } catch {
          /* autoplay may be blocked until a user gesture */
        }
        return;
      }
      setTtsMissing(out.reason === "rime key missing");
    },
    [],
  );

  const sendTurn = useCallback(
    async (args: { text: string; audio?: Blob; bargeIn: boolean }) => {
      if (!sessionId) return;
      if (limitReached || commandsRemaining === 0) {
        setLimitReached(true);
        return;
      }
      setBusy(true);
      setErr(null);
      setDecisionResult(null);

      let text = args.text.trim();
      const audioBlob = args.audio;

      // If we recorded audio, check if we need server STT.
      // We transcribe via server whenever:
      // 1. Web Speech produced no text (empty interim/final transcript), OR
      // 2. Web Speech was completely unavailable (Linux Chromium, or error fallback).
      if (audioBlob && (!text || sttViaServerRef.current)) {
        try {
          const stt = await api.stt(audioBlob, lang);
          if (stt.text) {
            text = stt.text;
            setLiveTranscript(text);
          }
        } catch (e) {
          // STT failure is non-fatal if we already had browser text
          if (!text) {
            setErr(`Transcription failed: ${(e as Error).message}`);
            setBusy(false);
            return;
          }
        }
      }

      if (!text && !audioBlob) {
        setBusy(false);
        return;
      }

      try {
        let r: TurnResponse;
        if (audioBlob) {
          r = await api.turnMultipart({
            sessionId,
            text,
            audio: audioBlob,
            bargeIn: args.bargeIn,
            language: lang,
          });
        } else {
          r = await api.turnJson({
            sessionId,
            text,
            bargeIn: args.bargeIn,
            language: lang,
          });
        }
        setResp(r);
        onCommandUsed?.();
        setHistoryRefresh((value) => value + 1);
        const speech = r.reply?.speech || r.reply?.text || "";
        void playTts(speech, lang);
      } catch (e) {
        if ((e as { status?: number }).status === 429) setLimitReached(true);
        setErr((e as Error).message);
      } finally {
        setBusy(false);
        bargeInRef.current = false;
      }
    },
    [sessionId, lang, playTts, limitReached, commandsRemaining, onCommandUsed],
  );

  const stopMic = useCallback(() => {
    setListening(false);
    try {
      recognitionRef.current?.stop();
    } catch {
      /* noop */
    }
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state !== "inactive"
    ) {
      mediaRecorderRef.current.stop();
    }
  }, []);

  const startMic = useCallback(async () => {
    setErr(null);
    setLiveTranscript("");
    finalTranscriptRef.current = "";
    chunksRef.current = [];
    maybeBargeIn();

    const SR = getSR();

    // Always start MediaRecorder so we capture raw audio for:
    // 1. VoiceID speaker verification (mandatory on every voice turn).
    // 2. Server STT fallback (whenever browser STT produces nothing or fails).
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mr = new MediaRecorder(stream, { mimeType: "audio/webm" });
      mediaRecorderRef.current = mr;
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        void sendTurn({
          text: finalTranscriptRef.current || liveTranscript,
          audio: blob.size > 0 ? blob : undefined,
          bargeIn: bargeInRef.current,
        });
      };
      mr.start();
    } catch (e) {
      setErr(`Microphone unavailable: ${(e as Error).message}`);
      return;
    }

    if (!SR) {
      // No Web Speech API (typical on Linux Chromium). MediaRecorder is already running;
      // onstop will transcribe via /api/stt. Nothing else to wire up.
      setListening(true);
      return;
    }

    const rec = new SR();
    recognitionRef.current = rec;
    rec.lang = lang;
    rec.continuous = true;
    rec.interimResults = true;
    rec.onspeechstart = () => {
      maybeBargeIn();
    };
    rec.onresult = (ev) => {
      let interim = "";
      let final = finalTranscriptRef.current;
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const res = ev.results[i];
        const chunk = res[0]?.transcript ?? "";
        if (res.isFinal) final += chunk;
        else interim += chunk;
      }
      if (interim) maybeBargeIn();
      finalTranscriptRef.current = final;
      setLiveTranscript((final + " " + interim).trim());
    };
    rec.onerror = (ev) => {
      if (
        ev.error === "network" ||
        ev.error === "service-not-allowed" ||
        ev.error === "language-not-supported"
      ) {
        sttViaServerRef.current = true;
        return;
      }
      if (ev.error !== "no-speech" && ev.error !== "aborted") {
        setErr(`Speech recognition error: ${ev.error}`);
      }
    };
    rec.onend = () => {
      if (mediaRecorderRef.current?.state === "recording") {
        try {
          rec.start();
        } catch {
          sttViaServerRef.current = true; // fall through to server STT on final stop
        }
      }
    };
    try {
      rec.start();
      setListening(true);
    } catch (e) {
      setErr(`Could not start recognition: ${(e as Error).message}`);
    }
  }, [lang, liveTranscript, maybeBargeIn, sendTurn, stopMic]);

  useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.abort();
      } catch {
        /* noop */
      }
      streamRef.current?.getTracks().forEach((t) => t.stop());
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
    };
  }, []);

  // The /demo tour drives a prompt through Talk so its "Choose" step has options to show.
  useEffect(() => {
    const onSend = (e: Event) => void sendTurn({ text: String((e as CustomEvent).detail ?? ""), bargeIn: false });
    window.addEventListener("vesper-demo-send", onSend);
    return () => window.removeEventListener("vesper-demo-send", onSend);
  }, [sendTurn]);

  const submitTyped = () => {
    if (!typed.trim()) return;
    maybeBargeIn();
    void sendTurn({ text: typed, bargeIn: bargeInRef.current });
    setTyped("");
  };

  const onDecision = async (d: DecisionKey) => {
    if (!sessionId) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await api.decision(sessionId, d, lang);
      setDecisionResult(r);
      const speech = r.reply?.speech || r.reply?.text || "";
      void playTts(speech, lang);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const entities = resp?.entities ?? [];
  const contradictions = resp?.contradictions ?? [];
  const blockers = resp?.blockers ?? [];
  const allowed = resp?.allowedDecisions ?? [];
  const replies = decisionResult ? [] : quickReplies(resp);
  const speakerLocked = resp?.speaker && resp.speaker.match === false;
  const exhausted = limitReached || commandsRemaining === 0;

  return (
    <div className="flex flex-col gap-4">
      {/* Language & Health Header */}
      <div className="flex items-center justify-between gap-2 px-1">
        <div
          id="workflow-language"
          className="flex items-center gap-1.5 p-0.5 rounded-lg border border-white/10 bg-black/40"
        >
          {(["en-IN", "hi-IN"] as const).map((l) => {
            const active = lang === l;
            return (
              <button
                key={l}
                onClick={() => setLang(l)}
                className={`px-2.5 py-1 text-xs rounded-md transition-all font-medium ${
                  active
                    ? "bg-white text-black shadow-sm font-semibold"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                {l === "en-IN" ? "English" : "Hinglish"}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-2 text-[11px] text-zinc-400 font-mono">
          {health ? (
            <span className="truncate max-w-[170px] opacity-80">
              {health.llm} {health.rime ? "· RIME" : ""}{" "}
              {health.voiceid ? "· VOICEID" : ""}
            </span>
          ) : null}
          {ttsMissing ? (
            <span className="rounded bg-amber-950 border border-amber-600/50 px-1.5 py-0.5 text-amber-200 text-[10px]">
              No Rime key
            </span>
          ) : null}
        </div>
      </div>

      <ErrorBanner msg={sessionError} />
      {!sessionId && !sessionError ? (
        <div className="glass-panel p-3 text-center text-xs text-zinc-400 flex items-center justify-center gap-2">
          <svg className="animate-spin h-3.5 w-3.5 text-zinc-300" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <span>Establishing session memory…</span>
        </div>
      ) : null}

      {exhausted ? <CommandLimitReached /> : null}

      {/* Push-to-Talk Mic hero */}
      <div
        id="workflow-capture"
        className="glass-panel py-6 px-4 flex flex-col items-center justify-center text-center"
      >
        <h2 className="mb-4 text-base font-medium text-white tracking-tight">
          Ask a question or report an <span className="editorial-em">observation</span>
        </h2>

        {/* Concentric Radar Ring Mic Button */}
        <div className={`mic-shell ${listening ? "listening" : ""}`}>
          <button
            type="button"
            onClick={() => {
              if (busy) return;
              if (listening) stopMic();
              else void startMic();
            }}
            disabled={exhausted || !sessionId || busy || (mounted && !micSupported)}
            aria-label={listening ? "Stop recording" : "Push to talk"}
            className={`mic-circle ${listening ? "is-listening" : ""}`}
          >
            {listening ? (
              <svg className="w-8 h-8" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="3" />
              </svg>
            ) : (
              <svg className="w-8 h-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" x2="12" y1="19" y2="22" />
              </svg>
            )}
          </button>
        </div>

        <div className="mt-4 flex flex-col items-center gap-1.5 min-h-[44px]">
          {speaking ? (
            <div className="flex items-center gap-2 text-emerald-400 text-xs font-medium">
              <WaveVisualizer active={true} />
              <span>Vesper is speaking…</span>
            </div>
          ) : listening ? (
            <span className="text-xs font-medium text-red-400 animate-pulse">
              Listening… tap button to finish
            </span>
          ) : busy ? (
            <div className="flex items-center gap-2 text-xs text-zinc-400">
              <svg className="animate-spin h-3.5 w-3.5 text-zinc-300" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              <span>Verifying drawings & specs…</span>
            </div>
          ) : (
            <span className="text-xs text-zinc-400">
              {commandsRemaining === undefined
                ? "Unlimited local commands · tap mic or type below"
                : `${commandsRemaining} free command${commandsRemaining === 1 ? "" : "s"} remaining · tap mic or type below`}
            </span>
          )}

          {voiceEnrolled === false ? (
            <p className="text-[11px] text-zinc-500">
              Voice not enrolled —{" "}
              <button
                onClick={onGoToEnroll}
                className="underline underline-offset-2 text-zinc-300 hover:text-white"
              >
                enroll voice
              </button>
            </p>
          ) : null}
        </div>
      </div>

      {/* Typed chat fallback */}
      {!exhausted ? (
        <div id="workflow-suggestions" className="flex flex-wrap gap-1.5 px-1">
          <span className="w-full text-[10px] font-mono uppercase tracking-wider text-zinc-500">Try</span>
          {(isDemo() ? DEMO_PROMPTS : LIVE_SUGGESTED).map((question) => (
            <button
              key={question}
              type="button"
              disabled={busy || !sessionId}
              onClick={() => void sendTurn({ text: question, bargeIn: false })}
              className="rounded-full border border-sky-200/15 bg-sky-300/[0.06] px-2.5 py-1 text-left text-[11px] text-sky-100/85 transition hover:border-sky-200/35 hover:bg-sky-300/[0.12]"
            >
              {question}
            </button>
          ))}
        </div>
      ) : null}
      <div id="workflow-typed-input" className="flex gap-2">
        <input
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submitTyped();
          }}
          placeholder="Chat with Vesper: 'What is the latest drawing for C-5?'"
          className="flex-1 rounded-lg border border-white/15 bg-black/60 px-3.5 py-2 text-xs outline-none text-white placeholder:text-zinc-500 focus:border-white/40 focus:ring-1 focus:ring-white/20 transition-all backdrop-blur-md"
        />
        <Button
          variant="solid"
          size="sm"
          onClick={submitTyped}
          disabled={exhausted || !sessionId || busy || !typed.trim()}
        >
          Send
        </Button>
      </div>

      <div id="workflow-review-area">
        <ErrorBanner msg={err} />

      {/* Live Transcript Bubble */}
      {liveTranscript ? (
        <div className="flex flex-col items-end gap-1.5 self-end max-w-[90%]">
          <div className="flex items-center gap-1 text-[10.5px] text-zinc-500 font-mono pr-1">
            <span>You</span>
          </div>
          <div className="bubble-user">
            {liveTranscript}
          </div>
        </div>
      ) : null}

      {/* Speaker Verification Lock */}
      {speakerLocked ? (
        <Card tone="red">
          <div className="flex items-center gap-2 font-medium text-red-200">
            <svg className="w-4 h-4 shrink-0 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
            <span>Speaker not verified — logging locked</span>
            {resp?.speaker ? (
              <span className="ml-auto font-mono text-[11px] opacity-70">
                score {resp.speaker.score.toFixed(2)}
              </span>
            ) : null}
          </div>
        </Card>
      ) : null}

      {/* Extracted Entity Badges */}
      {entities.length ? (
        <div className="flex flex-col gap-1.5">
          <span className="text-[10px] font-mono tracking-wider uppercase text-zinc-500 px-1">
            Extracted Context
          </span>
          <div className="flex flex-wrap gap-1.5">
            {entities.map((en, i) => (
              <Chip
                key={`${en.label}-${i}`}
                label={en.label}
                dim={en.confidence < 0.7}
                sub={en.confidence < 0.7 ? "low conf" : undefined}
              />
            ))}
          </div>
        </div>
      ) : null}

      {/* Contradiction Alerts */}
      {contradictions.length ? (
        <Card tone="red" title="Drawing / BOQ Contradiction">
          <ul className="space-y-1.5 text-xs text-red-100">
            {contradictions.map((c, i) => (
              <li key={i} className="flex items-start gap-2 leading-relaxed">
                <span className="text-red-400 mt-0.5">•</span>
                <span>{c.detail}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {/* Blocker Alerts */}
      {blockers.length ? (
        <Card tone="amber" title="Work Blocker Detected">
          <ul className="space-y-1.5 text-xs text-amber-100">
            {blockers.map((b, i) => (
              <li key={i} className="flex items-start gap-2 leading-relaxed">
                <span className="text-amber-400 mt-0.5">•</span>
                <span>{b.detail}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {/* Agent Reply Bubble */}
      {resp?.reply?.text ? (
        <div className="flex flex-col items-start gap-1.5 self-start max-w-[92%]">
          <div className="flex items-center gap-1.5 text-[10.5px] text-zinc-400 font-mono pl-1">
            <VesperLogo showWordmark={false} size={14} />
            <span>Vesper</span>
            <span className="text-zinc-600">·</span>
            <span className="text-zinc-500 uppercase text-[9px]">{resp.state}</span>
          </div>
          <div className="bubble-agent">
            {resp.reply.text}
          </div>
        </div>
      ) : null}

      {/* Options: answer Vesper's question or decide, with one tap */}
      {!decisionResult && (replies.length || allowed.length) ? (
        <div id="tour-talk-choose" className="glass-panel p-3 flex flex-col gap-2">
          <span className="text-[10px] font-mono tracking-wider uppercase text-zinc-400">Choose</span>
          {replies.length ? (
            <div className="flex flex-wrap gap-1.5">
              {replies.map((q) => (
                <button
                  key={q.label}
                  type="button"
                  disabled={busy}
                  onClick={() => void sendTurn({ text: q.text, bargeIn: false })}
                  className="rounded-full border border-sky-200/20 bg-sky-300/[0.07] px-3 py-1.5 text-xs text-sky-100 hover:border-sky-200/40 disabled:opacity-50"
                >
                  {q.label}
                </button>
              ))}
            </div>
          ) : null}
          {allowed.length ? (
            <div className="flex flex-wrap gap-2">
              {allowed.map((d) => (
                <Button
                  key={d}
                  variant={d === "log_observation" || d === "stop_work" ? "solid" : "ghost"}
                  size="sm"
                  onClick={() => onDecision(d)}
                  disabled={busy}
                >
                  {DECISION_LABELS[d]}
                </Button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Confirmation Card */}
      {decisionResult ? (
        <Card tone="green" title="Action Confirmed">
          <div className="text-xs text-emerald-100 leading-relaxed">
            <p className="font-medium">{decisionResult.reply?.text}</p>
            {decisionResult.logged?.observation_id ? (
              <p className="mt-1 font-mono text-[10.5px] text-emerald-300/80">
                {decisionResult.logged.observation_id}
                {decisionResult.logged.rfi_id ? ` · ${decisionResult.logged.rfi_id}` : ""}
              </p>
            ) : null}
          </div>
        </Card>
      ) : null}
      <ConversationHistory refreshKey={historyRefresh} />
      </div>
    </div>
  );
}
