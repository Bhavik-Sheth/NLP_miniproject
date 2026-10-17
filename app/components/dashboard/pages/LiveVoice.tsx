"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BarVisualizer,
  LiveKitRoom,
  RoomAudioRenderer,
  StartAudio,
  useConnectionState,
  useDataChannel,
  useLocalParticipant,
  useTrackTranscription,
  useVoiceAssistant,
} from "@livekit/components-react";
import type { TrackReferenceOrPlaceholder } from "@livekit/components-react";
import { Track } from "livekit-client";
import "@livekit/components-styles";
import { api, ApiError, type RtcToken } from "@/lib/api";
import { DEMO_LIVE } from "@/lib/demo";
import SiteMemoryPanel, { type SiteBrief } from "@/components/SiteMemoryPanel";
import { useDash } from "../context";
import { Icon } from "../icons";
import { Badge, Empty, Notice, PageHeader, Panel } from "../primitives";

// Laptop composition of the live voice console. The LiveKit/data-channel logic mirrors
// components/ConversationScreen.tsx (which stays the phone surface) — same topics, same
// transcript merge — laid out as transcript · evidence · engine event terminal.

type Contradiction = { kind?: string; severity?: string; detail: string; evidence?: unknown };
type EngineResult = {
  state?: string;
  spoken_reply?: string;
  contradictions?: Contradiction[];
  blockers?: { kind?: string; detail: string }[];
  missing?: { detail: string }[];
  resolved?: { location_id?: string; drawing?: string; drawing_id?: string; fact?: { value?: unknown; unit?: string; tolerance?: unknown; revision?: string; issued_on?: string; code_ref?: string } };
  allowed_decisions?: string[];
  allowedDecisions?: string[];
  logged?: unknown;
};
type Row = { who: "You" | "Vesper"; text: string; ts: number; id: string };
type LogLine = { ts: number; level: "info" | "state" | "warn" | "error" | "ok" | "data"; tag: string; text: string };

const DECISIONS: Record<string, string> = { log_observation: "Log observation", raise_rfi: "Raise RFI", raise_ncr: "Raise NCR", stop_work: "Stop work", cancel: "Cancel" };
const PROMPTS = ["What should I check before today's concrete pour?", "Which drawings are current?", "Any open RFIs?"];

function useLog() {
  const [lines, setLines] = useState<LogLine[]>([]);
  const push = useCallback((level: LogLine["level"], tag: string, text: string) => setLines((l) => [...l.slice(-400), { ts: Date.now(), level, tag, text }]), []);
  return { lines, push, clear: () => setLines([]) };
}

export default function LiveVoice() {
  const { project } = useDash();
  const [creds, setCreds] = useState<RtcToken | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<{ msg: string; status: number } | null>(null);
  const [replay, setReplay] = useState(false);
  const log = useLog();
  const { push } = log;

  const start = useCallback(async () => {
    setConnecting(true);
    setError(null);
    setReplay(false);
    push("info", "rtc", "requesting LiveKit token POST /api/rtc/token");
    try {
      const t = await api.rtcToken({ name: "Manager", language: "en-IN", projectId: project.id });
      push("ok", "rtc", `token issued · room ${t.room} · identity ${t.identity}`);
      setCreds(t);
    } catch (e) {
      const status = e instanceof ApiError ? e.status : 0;
      push("error", "rtc", (e as Error).message);
      setError({ msg: (e as Error).message, status });
    } finally {
      setConnecting(false);
    }
  }, [project.id, push]);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("start") !== "1") return;
    const timer = window.setTimeout(() => void start(), 0);
    return () => window.clearTimeout(timer);
  }, [start]);

  return (
    <div>
      <PageHeader
        eyebrow="Workspace"
        title="Live voice"
        description="A full-duplex call with the site record. Every claim is resolved against drawings, RFIs, permits and hold points while you talk."
        actions={
          creds || replay ? null : (
            <button className="dash-btn" onClick={() => (log.clear(), setReplay(true))}>
              <Icon name="play" size={13} /> Replay recorded call
            </button>
          )
        }
      />
      {creds ? (
        <LiveKitRoom
          serverUrl={creds.url}
          token={creds.token}
          connect
          audio={{ echoCancellation: true, noiseSuppression: true, autoGainControl: true }}
          video={false}
          onDisconnected={() => {
            log.push("warn", "rtc", "disconnected");
            setCreds(null);
          }}
        >
          <RoomView onEnd={() => setCreds(null)} log={log} />
        </LiveKitRoom>
      ) : replay ? (
        <ReplayView onEnd={() => setReplay(false)} log={log} />
      ) : (
        <Idle start={start} connecting={connecting} error={error} log={log.lines} />
      )}
    </div>
  );
}

function Idle({ start, connecting, error, log }: { start: () => void; connecting: boolean; error: { msg: string; status: number } | null; log: LogLine[] }) {
  const { health } = useDash();
  return (
    <div className="grid gap-5 xl:grid-cols-[1.3fr_1fr]">
      <section id="tour-live-stage" className="glass relative flex min-h-[440px] flex-col items-center justify-center overflow-hidden p-8 text-center">
        <div className="pointer-events-none absolute inset-0 opacity-60" style={{ background: "radial-gradient(60% 50% at 50% 45%, color-mix(in oklab, var(--accent) 16%, transparent), transparent 70%)" }} />
        <button className="dash-orb relative" data-active={connecting} onClick={start} disabled={connecting} aria-label="Start live voice session">
          <span className="dash-orb-ring" />
          <span className="dash-orb-ring r2" />
          <span className="dash-orb-core" />
          <span className="relative text-white drop-shadow">{connecting ? <span className="block h-7 w-7 animate-spin rounded-full border-[3px] border-white border-t-transparent" /> : <Icon name="mic" size={32} strokeWidth={2} />}</span>
        </button>
        <h2 className="relative mt-7 text-[20px] font-semibold tracking-[-0.02em] text-ink">
          {connecting ? "Connecting the voice pipeline…" : "Start a hands-free session"}
        </h2>
        <p className="relative mt-1.5 max-w-md text-[13px] leading-relaxed text-ink-2">
          Vesper opens with the state of the site, answers from the record, and challenges any observation that contradicts the latest For-Construction revision — out loud.
        </p>
        <div className="relative mt-5 flex flex-wrap justify-center gap-2">
          <Badge tone={health?.rime ? "ok" : "warn"} dot>Rime TTS {health?.rime ? "ready" : "unavailable"}</Badge>
          <Badge tone={health?.voiceid ? "ok" : "warn"} dot>Voice ID {health?.voiceid ? "ready" : "off"}</Badge>
          <Badge dot>LLM {health?.llm ?? "…"}</Badge>
        </div>
        {error ? (
          <div className="relative mt-6 w-full max-w-lg text-left">
            <Notice tone={error.status === 503 ? "warn" : "danger"} title={error.status === 503 ? "LiveKit is not configured on this backend" : error.status === 429 ? "Free command allowance used" : "Could not start the session"}>
              <span className="font-mono text-[11.5px]">{error.msg}</span>
              {error.status === 503 ? <p className="mt-1">Set LIVEKIT_* in .env — or use “Replay recorded call” to see the full flow.</p> : null}
            </Notice>
          </div>
        ) : null}
      </section>
      <Terminal lines={log} idle />
    </div>
  );
}

// ------------------------------------------------------------------ live room
function RoomView({ onEnd, log }: { onEnd: () => void; log: ReturnType<typeof useLog> }) {
  const { state, audioTrack, agentTranscriptions } = useVoiceAssistant();
  const { microphoneTrack, localParticipant, isMicrophoneEnabled } = useLocalParticipant();
  const conn = useConnectionState();
  const [engine, setEngine] = useState<EngineResult | null>(null);
  const [brief, setBrief] = useState<SiteBrief | null>(null);
  const [speaker, setSpeaker] = useState<{ match: boolean; score: number | null; reason?: string | null } | null>(null);
  const [speakerRequired, setSpeakerRequired] = useState(false);
  const [tts, setTts] = useState<{ provider: string; model: string; speaker: string; transport: string } | null>(null);
  const [engineReplies, setEngineReplies] = useState<Row[]>([]);
  const { push } = log;

  const [micError, setMicError] = useState<string | null>(null);

  useEffect(() => push("state", "conn", String(conn)), [conn, push]);
  useEffect(() => push("state", "agent", `state → ${state}`), [state, push]);

  // LiveKitRoom's `audio` prop publishes the microphone on connect, but a denied permission or a
  // device another app already holds fails quietly: the call stays up, the agent listens to
  // silence, and the only clue is a small "mic off" pill. Ask explicitly and say so loudly.
  const micAsked = useRef(false);
  useEffect(() => {
    if (String(conn) !== "connected") {
      micAsked.current = false; // a fresh connection may ask again
      return;
    }
    // Ask exactly once per connection. A device that keeps rejecting would otherwise be retried on
    // every re-render, and hammering getUserMedia in a loop can take the whole tab down.
    if (!localParticipant || isMicrophoneEnabled || micAsked.current) return;
    micAsked.current = true;
    let cancelled = false;
    void localParticipant
      .setMicrophoneEnabled(true)
      .then(() => {
        if (!cancelled) setMicError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        const msg = (e as Error)?.message || String(e);
        setMicError(msg);
        push("error", "mic", `microphone not published: ${msg}`);
      });
    return () => {
      cancelled = true;
    };
  }, [conn, localParticipant, isMicrophoneEnabled, push]);

  const micRef = useMemo<TrackReferenceOrPlaceholder | undefined>(
    () => (localParticipant ? { participant: localParticipant, source: Track.Source.Microphone, publication: microphoneTrack } : undefined),
    [localParticipant, microphoneTrack],
  );
  const { segments: userSegments } = useTrackTranscription(micRef);

  const send = useCallback(
    (cmd: { type: "decision"; decision: string } | { type: "text"; text: string }) => {
      push("data", "cmd", JSON.stringify(cmd));
      void localParticipant.publishData(new TextEncoder().encode(JSON.stringify(cmd)), { reliable: true, topic: "vesper-cmd" });
    },
    [localParticipant, push],
  );

  useDataChannel("vesper", (msg) => {
    try {
      const d = JSON.parse(new TextDecoder().decode(msg.payload));
      if (d.type === "session") {
        if (d.tts) setTts(d.tts);
        setSpeakerRequired(!!d.speaker_required);
        push("info", "session", `tts ${d.tts ? `${d.tts.provider} ${d.tts.model} · ${d.tts.speaker} · ${d.tts.transport}` : "—"} · speaker_required=${!!d.speaker_required}`);
      } else if (d.type === "speaker") {
        setSpeaker({ match: !!d.match, score: d.score ?? null, reason: d.reason });
        push(d.match ? "ok" : "warn", "voiceid", `${d.match ? "match" : "no match"} score=${d.score ?? "—"}${d.reason ? ` · ${d.reason}` : ""}`);
      } else if (d.type === "engine" && d.result) {
        const r = d.result as EngineResult;
        setEngine(r);
        push("state", "engine", `state → ${r.state ?? "?"}`);
        (r.contradictions ?? []).forEach((c) => push("warn", "contradiction", `${c.kind ?? ""} ${c.detail}`));
        (r.blockers ?? []).forEach((b) => push("error", "blocker", b.detail));
        if (r.logged) push("ok", "logged", JSON.stringify(r.logged));
        const reply = r.spoken_reply?.trim();
        if (reply) setEngineReplies((cur) => (cur.at(-1)?.text === reply ? cur : [...cur, { who: "Vesper", text: reply, ts: Date.now(), id: `e${Date.now()}` }]));
      } else if (d.type === "brief" && d.brief) {
        setBrief(d.brief);
        push("info", "brief", `site memory loaded · ${d.brief.open_rfis?.length ?? 0} RFIs · ${d.brief.open_hold_points?.length ?? 0} hold points`);
      } else push("data", d.type ?? "data", JSON.stringify(d).slice(0, 180));
    } catch {
      push("error", "data", "malformed message");
    }
  });

  const transcript = useMemo(() => {
    const rows: Row[] = [];
    for (const s of userSegments) if (s.final && s.text.trim()) rows.push({ who: "You", text: s.text, ts: s.firstReceivedTime ?? 0, id: `u-${s.id}` });
    for (const s of agentTranscriptions) if (s.final && s.text.trim()) rows.push({ who: "Vesper", text: s.text, ts: s.firstReceivedTime ?? 0, id: `a-${s.id}` });
    rows.push(...engineReplies);
    rows.sort((a, b) => a.ts - b.ts);
    const norm = (t: string) => t.trim().replace(/\s+/g, " ").toLowerCase();
    const out: Row[] = [];
    for (const r of rows) if (!out.some((d) => d.who === r.who && norm(d.text) === norm(r.text) && Math.abs(r.ts - d.ts) < 20_000)) out.push(r);
    return out;
  }, [userSegments, agentTranscriptions, engineReplies]);

  const interim = [...userSegments].reverse().find((s) => !s.final && s.text.trim())?.text;

  return (
    <>
      <RoomAudioRenderer />
      <StartAudio label="Click to enable Vesper’s voice" className="dash-btn mb-3 w-full" />
      {micError || (String(conn) === "connected" && !isMicrophoneEnabled) ? (
        <div className="mb-3">
          <Notice tone="danger" title="Vesper cannot hear you — your microphone is not being sent">
            <p>
              The call is connected, but no microphone track is published, so nothing is transcribed.
              Allow microphone access for this site in your browser, close any other app holding the
              mic, then press the mic button.
            </p>
            {micError ? <p className="mt-1 font-mono text-[11.5px]">{micError}</p> : null}
          </Notice>
        </div>
      ) : null}
      <Stage
        status={isMicrophoneEnabled ? String(state ?? "idle") : "mic off"}
        active={state === "speaking" || state === "listening"}
        visualizer={<BarVisualizer state={state} trackRef={audioTrack} barCount={24} className="h-8 w-full" />}
        provider={tts ? `${tts.provider} ${tts.model} · ${tts.speaker} · ${tts.transport}` : "waiting for agent…"}
        speaker={speakerRequired ? speaker : undefined}
        controls={
          <>
            <button
              className={`dash-btn dash-btn-icon ${isMicrophoneEnabled ? "" : "text-danger"}`}
              onClick={() => void localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)}
              aria-pressed={!isMicrophoneEnabled}
              title={isMicrophoneEnabled ? "Mute my mic" : "Unmute my mic"}
            >
              <Icon name={isMicrophoneEnabled ? "mic" : "x"} size={15} />
            </button>
            <button className="dash-btn" style={{ color: "var(--danger)" }} onClick={onEnd}>
              <Icon name="stop" size={12} /> End
            </button>
          </>
        }
      />
      <Layout transcript={transcript} interim={interim} engine={engine} brief={brief} log={log.lines} onSend={send} />
    </>
  );
}

// ------------------------------------------------------------------ recorded replay
function ReplayView({ onEnd, log }: { onEnd: () => void; log: ReturnType<typeof useLog> }) {
  const script = DEMO_LIVE.script;
  const [rows, setRows] = useState<Row[]>([]);
  const [typing, setTyping] = useState<string | undefined>();
  const [engine, setEngine] = useState<EngineResult | null>(null);
  const [status, setStatus] = useState("connecting");
  const { push } = log;

  useEffect(() => {
    let alive = true;
    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
    (async () => {
      push("info", "replay", "recorded demo engine output · no audio sent");
      push("state", "conn", "connected");
      push("info", "session", "tts rime mistv2 · speaker cove · websocket · speaker_required=true");
      await sleep(500);
      push("info", "brief", "site memory loaded · open RFIs, hold points, permits, current drawings");
      for (let i = 0; i < script.length && alive; i++) {
        const line = script[i];
        setStatus(line.who === "You" ? "listening" : "thinking");
        push("state", "agent", `state → ${line.who === "You" ? "listening" : "thinking"}`);
        await sleep(line.who === "You" ? 500 : 700);
        if (line.who === "Vesper") setStatus("speaking");
        const words = line.text.split(" ");
        for (let w = 1; w <= words.length && alive; w++) {
          setTyping(`${line.who}|${words.slice(0, w).join(" ")}`);
          await sleep(line.who === "You" ? 45 : 32);
        }
        if (!alive) return;
        setTyping(undefined);
        setRows((r) => [...r, { who: line.who, text: line.text, ts: Date.now(), id: `r${i}` }]);
        if (line.who === "You") {
          push("ok", "voiceid", "match score=0.86");
          push("data", "stt", `final "${line.text}"`);
        }
        if (i === script.length - 1 || (line.who === "Vesper" && /tolerance|contradict/i.test(line.text))) {
          const eng = DEMO_LIVE.engine as EngineResult | null;
          if (eng) {
            setEngine(eng);
            push("state", "engine", `state → ${eng.state ?? "challenging"}`);
            (eng.contradictions ?? []).forEach((c) => push("warn", "contradiction", `${c.kind ?? ""} ${c.detail}`));
          }
        }
        await sleep(350);
      }
      if (alive) {
        setStatus("listening");
        push("info", "replay", "end of recording — choose a decision to see how the gate responds");
      }
    })();
    return () => {
      alive = false;
    };
  }, [script, push]);

  const interim = typing?.split("|");
  return (
    <>
      <Stage
        status={status}
        active={status === "speaking" || status === "listening"}
        visualizer={<Wave active={status === "speaking" || !!typing} />}
        provider="rime mistv2 · cove · websocket (recorded)"
        speaker={{ match: true, score: 0.86 }}
        controls={
          <>
            <Badge tone="accent">Replay</Badge>
            <button className="dash-btn" onClick={onEnd}>
              <Icon name="x" size={13} /> Close
            </button>
          </>
        }
      />
      <Layout
        transcript={rows}
        interim={interim ? interim[1] : undefined}
        interimWho={interim?.[0] as Row["who"] | undefined}
        engine={engine}
        brief={DEMO_LIVE.brief as SiteBrief}
        log={log.lines}
        onSend={(cmd) => push("data", "cmd", `${JSON.stringify(cmd)} (replay: not sent)`)}
      />
    </>
  );
}

// ------------------------------------------------------------------ layout pieces
function Wave({ active }: { active: boolean }) {
  return (
    <div className="dash-wave w-full justify-center" data-active={active}>
      {Array.from({ length: 36 }).map((_, i) => (
        <i key={i} style={{ animationDelay: `${-((i * 137) % 1000) / 1000}s`, animationDuration: `${0.7 + ((i * 53) % 60) / 100}s` }} />
      ))}
    </div>
  );
}

function Stage({
  status,
  active,
  visualizer,
  provider,
  speaker,
  controls,
}: {
  status: string;
  active: boolean;
  visualizer: React.ReactNode;
  provider: string;
  speaker?: { match: boolean; score: number | null; reason?: string | null } | null;
  controls: React.ReactNode;
}) {
  return (
    <section id="tour-live-stage" className="glass mb-5 flex flex-wrap items-center gap-4 px-4 py-3">
      <div className="relative h-11 w-11 shrink-0">
        <span className="dash-orb-core" style={{ animationDuration: active ? "4s" : "14s" }} />
      </div>
      <div className="w-[92px] shrink-0">
        <p className="dash-eyebrow">Agent</p>
        <p className="mt-1 flex items-center gap-1.5 text-[13px] font-medium capitalize text-ink">
          <span className="dash-dot" data-tone={active ? "ok" : "warn"} data-pulse />
          {status}
        </p>
      </div>
      <div className="order-last h-9 min-w-[200px] flex-1 text-accent sm:order-none">{visualizer}</div>
      <div className="hidden min-w-0 max-w-[260px] lg:block">
        <p className="dash-eyebrow">Voice out</p>
        <p className="mt-1 truncate font-mono text-[11.5px] text-ink-2">{provider}</p>
      </div>
      {speaker !== undefined ? (
        <Badge tone={speaker ? (speaker.match ? "ok" : "danger") : "neutral"} dot>
          {speaker ? (speaker.match ? `Voice verified ${speaker.score?.toFixed(2) ?? ""}` : `Logging locked${speaker.reason ? ` · ${speaker.reason}` : ""}`) : "Verifying voice…"}
        </Badge>
      ) : null}
      <div className="ml-auto flex items-center gap-2">{controls}</div>
    </section>
  );
}

function Layout({
  transcript,
  interim,
  interimWho = "You",
  engine,
  brief,
  log,
  onSend,
}: {
  transcript: Row[];
  interim?: string;
  interimWho?: Row["who"];
  engine: EngineResult | null;
  brief: SiteBrief | null;
  log: LogLine[];
  onSend: (cmd: { type: "decision"; decision: string } | { type: "text"; text: string }) => void;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [transcript, interim]);
  const allowed = engine?.allowed_decisions ?? engine?.allowedDecisions ?? [];
  const contradictions = engine?.contradictions ?? [];
  const blockers = engine?.blockers ?? [];
  const fact = engine?.resolved?.fact;

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(340px,1fr)]">
      <div className="flex min-w-0 flex-col gap-5">
        <Panel title="Conversation" icon="mic" bodyClassName="p-0" action={<span className="text-[11.5px] tabular-nums text-ink-3">{transcript.length} turns</span>}>
          <div ref={scroller} className="h-[420px] space-y-4 overflow-y-auto px-5 py-4">
            {transcript.length === 0 && !interim ? (
              <Empty icon="mic" title="Listening" body="Speak an observation or ask a question to begin." />
            ) : null}
            {transcript.map((r) => (
              <Bubble key={r.id} who={r.who} text={r.text} />
            ))}
            {interim ? <Bubble who={interimWho} text={interim} streaming /> : null}
          </div>
          <div className="flex flex-wrap items-center gap-1.5 border-t border-line px-4 py-2.5">
            {allowed.length
              ? allowed.map((d) => (
                  <button key={d} className={`dash-btn dash-btn-sm ${d === "log_observation" ? "dash-btn-primary" : ""}`} style={d === "stop_work" ? { color: "var(--danger)" } : undefined} onClick={() => onSend({ type: "decision", decision: d })}>
                    {DECISIONS[d] ?? d}
                  </button>
                ))
              : PROMPTS.map((p) => (
                  <button key={p} className="dash-btn dash-btn-sm dash-btn-ghost border-line" style={{ borderColor: "var(--border)" }} onClick={() => onSend({ type: "text", text: p })}>
                    {p}
                  </button>
                ))}
          </div>
        </Panel>
        <Terminal lines={log} />
      </div>

      <div className="flex min-w-0 flex-col gap-5">
        <Panel title="Evidence" icon="shield" action={contradictions.length ? <Badge tone="danger">{contradictions.length} contradiction{contradictions.length > 1 ? "s" : ""}</Badge> : null}>
          {!engine ? (
            <Empty icon="shield" title="No claim checked yet" body="Contradictions, blockers and the resolved drawing fact appear here as the engine decides." />
          ) : (
            <div className="space-y-3">
              {contradictions.map((c, i) => (
                <div key={i} className="dash-row-in rounded-xl border p-3" style={{ borderColor: "color-mix(in oklab, var(--danger) 30%, transparent)", background: "color-mix(in oklab, var(--danger) 6%, transparent)" }}>
                  <p className="flex items-center gap-1.5 text-[11.5px] font-medium uppercase tracking-wide" style={{ color: "var(--danger)" }}>
                    <Icon name="alert" size={12} /> {(c.kind ?? "contradiction").replace(/_/g, " ")}
                  </p>
                  <p className="mt-1 text-[13px] leading-relaxed text-ink">{c.detail}</p>
                </div>
              ))}
              {blockers.map((b, i) => (
                <div key={`b${i}`} className="dash-row-in rounded-xl border p-3" style={{ borderColor: "color-mix(in oklab, var(--warn) 30%, transparent)", background: "color-mix(in oklab, var(--warn) 6%, transparent)" }}>
                  <p className="text-[11.5px] font-medium uppercase tracking-wide" style={{ color: "var(--warn)" }}>
                    Blocker
                  </p>
                  <p className="mt-1 text-[13px] text-ink">{b.detail}</p>
                </div>
              ))}
              {engine.resolved && (engine.resolved.drawing_id || fact) ? (
                <dl className="card grid grid-cols-[96px_1fr] gap-x-3 gap-y-1.5 p-3 font-mono text-[12px]">
                  {engine.resolved.location_id ? (
                    <>
                      <dt className="text-ink-3">location</dt>
                      <dd className="text-ink">{engine.resolved.location_id}</dd>
                    </>
                  ) : null}
                  {engine.resolved.drawing_id ? (
                    <>
                      <dt className="text-ink-3">drawing</dt>
                      <dd className="text-ink">{engine.resolved.drawing_id}</dd>
                    </>
                  ) : null}
                  {fact?.value != null ? (
                    <>
                      <dt className="text-ink-3">expected</dt>
                      <dd className="text-ink">
                        {String(fact.value)}
                        {fact.unit ? ` ${fact.unit}` : ""}
                        {fact.tolerance != null ? ` ± ${String(fact.tolerance)}` : ""}
                      </dd>
                    </>
                  ) : null}
                  {fact?.code_ref ? (
                    <>
                      <dt className="text-ink-3">code</dt>
                      <dd className="text-ink">{fact.code_ref}</dd>
                    </>
                  ) : null}
                </dl>
              ) : null}
              {engine.state ? (
                <p className="text-[11.5px] text-ink-3">
                  Engine state <span className="font-mono text-ink-2">{engine.state}</span>
                </p>
              ) : null}
            </div>
          )}
        </Panel>
        <Panel title="Site memory" icon="brain" bodyClassName="p-3">
          {brief ? (
            <div className="dash-legacy p-2.5">
              <SiteMemoryPanel brief={brief} />
            </div>
          ) : (
            <Empty icon="brain" title="Waiting for the site brief" body="The agent sends the latest DPRs, RFIs, permits and hold points when the call opens." />
          )}
        </Panel>
      </div>
    </div>
  );
}

function Bubble({ who, text, streaming }: { who: Row["who"]; text: string; streaming?: boolean }) {
  const you = who === "You";
  return (
    <div className={`dash-rise flex gap-2.5 ${you ? "flex-row-reverse" : ""}`}>
      <span className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full text-[10px] font-semibold ${you ? "bg-surface-2 text-ink-2" : "text-white"}`} style={you ? undefined : { background: "linear-gradient(135deg, var(--accent), var(--accent-2))" }}>
        {you ? "You" : "V"}
      </span>
      <div className={`max-w-[80%] rounded-2xl px-3.5 py-2.5 text-[13.5px] leading-relaxed ${you ? "rounded-tr-md bg-surface-2 text-ink" : "rounded-tl-md border border-line bg-surface text-ink"} ${streaming ? "dash-caret" : ""}`}>
        {text}
      </div>
    </div>
  );
}

function Terminal({ lines, idle }: { lines: LogLine[]; idle?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [lines]);
  const color: Record<LogLine["level"], string> = { info: "#8b95a7", state: "#8fb3ff", warn: "#f0b44a", error: "#ff6b5f", ok: "#5ad19a", data: "#b8a4ff" };
  return (
    <section className="dash-terminal flex min-h-0 flex-col overflow-hidden">
      <div className="flex h-9 shrink-0 items-center gap-2 border-b border-white/5 px-3">
        <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
        <span className="ml-2 text-[11px] text-[#6a7280]">vesper — engine events</span>
        <span className="ml-auto text-[11px] text-[#6a7280]">{lines.length} events</span>
      </div>
      <div ref={ref} className={`${idle ? "min-h-[400px]" : "h-[240px]"} flex-1 overflow-y-auto px-3 py-2`}>
        {lines.length === 0 ? <p className="text-[#6a7280]">$ waiting for a session…</p> : null}
        {lines.map((l, i) => (
          <div key={i} className="flex gap-2 whitespace-pre-wrap break-all">
            <span className="shrink-0 text-[#4b5260]">{new Date(l.ts).toLocaleTimeString("en-GB", { hour12: false })}</span>
            <span className="w-[92px] shrink-0 truncate" style={{ color: color[l.level] }}>
              [{l.tag}]
            </span>
            <span className={l.level === "error" ? "text-[#ffb4ad]" : "text-[#c9d1dc]"}>{l.text}</span>
          </div>
        ))}
        <span className="dash-caret text-[#6a7280]">$</span>
      </div>
    </section>
  );
}
