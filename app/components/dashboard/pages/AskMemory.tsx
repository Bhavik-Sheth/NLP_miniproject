"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { apiV2, isMissing, type AskResponse, type SearchResponse } from "@/lib/api-v2";
import { DEMO_QUESTIONS, STATIC_DEMO } from "@/lib/static-demo";
import { useDash } from "../context";
import { Icon } from "../icons";
import { Badge, Kbd, Notice, PageHeader, Sheet, Skeleton } from "../primitives";
import { HitList, LatencyBars } from "../Retrieval";

type Msg =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; pending?: boolean; res?: AskResponse; via?: "memory" | "engine"; error?: string; ms?: number; query: string };

/** A saved Ask thread. Ask is read-only and has no server-side history (`/api/conversations` holds
 *  voice sessions, not these), so threads live in localStorage, scoped per project. */
type Thread = { id: string; title: string; updatedAt: number; msgs: Msg[] };

const THREAD_LIMIT = 40;

const SUGGESTIONS = [
  "What cover does IS 456 require for columns?",
  "Why was A-101 revised to R2?",
  "Which permits are blocking work today?",
  "What is holding the L4 slab pour?",
];

export default function AskMemory() {
  const { project } = useDash();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [inspect, setInspect] = useState<{ query: string; res?: SearchResponse; error?: string; missing?: boolean; ms?: number; loading: boolean; askTimings?: AskResponse["timings"] } | null>(null);
  const engineSession = useRef<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [histOpen, setHistOpen] = useState(true);
  const storeKey = `vesper_ask_threads_${project.id}`;

  useEffect(() => {
    try {
      setHistOpen(localStorage.getItem("vesper_ask_history_open") !== "0");
    } catch {
      /* ignore */
    }
  }, []);

  const toggleHist = (open: boolean) => {
    setHistOpen(open);
    try {
      localStorage.setItem("vesper_ask_history_open", open ? "1" : "0");
    } catch {
      /* ignore */
    }
  };

  const writeThreads = (next: Thread[]) => {
    setThreads(next);
    try {
      localStorage.setItem(storeKey, JSON.stringify(next));
    } catch {
      /* private mode or full quota — history is a convenience, never block asking */
    }
  };

  // Switching project switches history: a thread about P1 must not appear under NSK.
  useEffect(() => {
    let loaded: Thread[] = [];
    try {
      loaded = JSON.parse(localStorage.getItem(storeKey) || "[]");
    } catch {
      loaded = [];
    }
    setThreads(Array.isArray(loaded) ? loaded : []);
    setActiveId(null);
    setMsgs([]);
  }, [storeKey]);

  // Save once the answer has settled, so a half-finished "pending" bubble is never persisted.
  useEffect(() => {
    if (STATIC_DEMO || busy) return;
    const settled = msgs.filter((m) => !(m.role === "assistant" && m.pending));
    if (!settled.length) return;
    const id = activeId ?? `t${Date.now()}`;
    if (!activeId) setActiveId(id);
    const first = settled.find((m) => m.role === "user");
    const title = first && first.role === "user" ? first.text.slice(0, 70) : "Untitled";
    setThreads((cur) => {
      const next = [{ id, title, updatedAt: Date.now(), msgs: settled }, ...cur.filter((t) => t.id !== id)].slice(0, THREAD_LIMIT);
      try {
        localStorage.setItem(storeKey, JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }, [msgs, busy, activeId, storeKey]);

  const newChat = () => {
    setMsgs([]);
    setActiveId(null);
    setInput("");
    taRef.current?.focus();
  };

  const openThread = (t: Thread) => {
    setMsgs(t.msgs);
    setActiveId(t.id);
    setInspect(null);
  };

  const deleteThread = (id: string) => {
    writeThreads(threads.filter((t) => t.id !== id));
    if (activeId === id) {
      setMsgs([]);
      setActiveId(null);
    }
  };

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [msgs]);

  const ask = async (q: string) => {
    const query = q.trim();
    if (!query || busy) return;
    setInput("");
    setBusy(true);
    const id = `${Date.now()}`;
    setMsgs((m) => [...m, { id: `u${id}`, role: "user", text: query }, { id: `a${id}`, role: "assistant", pending: true, query }]);
    const t0 = performance.now();
    const done = (patch: Partial<Extract<Msg, { role: "assistant" }>>) =>
      setMsgs((m) => m.map((x) => (x.id === `a${id}` ? ({ ...x, pending: false, ms: performance.now() - t0, ...patch } as Msg) : x)));
    try {
      const res = await apiV2.ask({ query, projectId: project.id });
      done({ res, via: "memory" });
    } catch (e) {
      // Ask is read-only. Never fall back to the v1 dialogue engine (/api/turn): it captures and
      // logs observations, so a question could turn into a written log entry.
      done({
        error: isMissing(e)
          ? "The memory layer isn't loaded on the backend (GET /api/v2/status). Restart the backend to enable Ask memory."
          : (e as Error).message,
      });
    } finally {
      setBusy(false);
      taRef.current?.focus();
    }
  };

  // Public static demo: play the recorded questions into the thread one by one until the visitor
  // types or clicks something themselves.
  const autoplayStop = useRef(false);
  useEffect(() => {
    if (!STATIC_DEMO || !DEMO_QUESTIONS.length || new URLSearchParams(window.location.search).get("q")) return;
    let cancelled = false;
    const stop = () => (autoplayStop.current = true);
    window.addEventListener("keydown", stop, { once: true });
    window.addEventListener("pointerdown", stop, { once: true });
    (async () => {
      await new Promise((r) => setTimeout(r, 1800));
      for (const q of DEMO_QUESTIONS) {
        if (cancelled || autoplayStop.current) return;
        await ask(q);
        await new Promise((r) => setTimeout(r, 2600));
      }
    })();
    return () => {
      cancelled = true;
      window.removeEventListener("keydown", stop);
      window.removeEventListener("pointerdown", stop);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ?q= deep link runs once (React dev double-invokes effects, which asked the question twice)
  const askedFromUrl = useRef(false);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    if (!q || askedFromUrl.current) return;
    askedFromUrl.current = true;
    void ask(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Speak the question instead of typing it: record, send to /api/stt (Sarvam saaras, Hindi and
  // English), and drop the transcript into the box so it can be corrected before asking.
  const [rec, setRec] = useState<MediaRecorder | null>(null);
  const [sttBusy, setSttBusy] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);
  const chunks = useRef<Blob[]>([]);

  const startDictation = async () => {
    setMicError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunks.current = [];
      mr.ondataavailable = (e) => chunks.current.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRec(null);
        setSttBusy(true);
        try {
          const { text } = await api.stt(new Blob(chunks.current, { type: "audio/webm" }));
          const said = (text || "").trim();
          if (said) setInput((cur) => (cur ? `${cur} ${said}` : said));
          else setMicError("Nothing was heard — check the microphone input device.");
          taRef.current?.focus();
        } catch (e) {
          setMicError((e as Error).message);
        } finally {
          setSttBusy(false);
        }
      };
      mr.start();
      setRec(mr);
    } catch (e) {
      setMicError(`Microphone unavailable: ${(e as Error).message}`);
    }
  };

  const openInspector = async (query: string, askTimings?: AskResponse["timings"]) => {
    setInspect({ query, loading: true, askTimings });
    const t0 = performance.now();
    try {
      const res = await apiV2.search({ query, projectId: project.id, scopes: ["global", "project"], k: 8 });
      setInspect({ query, res, loading: false, ms: performance.now() - t0, askTimings });
    } catch (e) {
      setInspect({ query, loading: false, error: (e as Error).message, missing: isMissing(e), askTimings });
    }
  };

  return (
    <div className="relative flex h-[calc(100dvh-52px-3rem-4rem)] min-h-[520px] flex-col">
      <PageHeader
        eyebrow="Knowledge"
        title="Ask memory"
        description="Grounded answers over project documents, IS codes, templates and the site record — every claim cited, or an explicit abstain."
        actions={
          // Above xl the floating history panel carries its own "New" button and would sit on top
          // of this one, so only show it at widths where the panel is hidden.
          msgs.length ? (
            <span className="xl:hidden">
              <button className="dash-btn dash-btn-sm" onClick={newChat}>
                <Icon name="plus" size={13} /> New chat
              </button>
            </span>
          ) : null
        }
      />

      <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto pr-1">
        {msgs.length === 0 ? (
          <div className="mx-auto flex max-w-2xl flex-col items-center pt-8 text-center">
            <div className="glass mb-5 grid h-14 w-14 place-items-center rounded-2xl text-accent">
              <Icon name="sparkles" size={24} />
            </div>
            <p className="text-[18px] font-semibold tracking-[-0.02em] text-ink">
              What do you need to know <span className="dash-serif font-normal text-ink-2">on site?</span>
            </p>
            <p className="mt-1 text-[13px] text-ink-3">Hybrid retrieval · vector + BM25 → RRF → cross-encoder rerank</p>
            <div className="mt-6 grid w-full gap-2 sm:grid-cols-2">
              {(STATIC_DEMO && DEMO_QUESTIONS.length ? DEMO_QUESTIONS.slice(0, 4) : SUGGESTIONS).map((s, i) => (
                <button key={s} onClick={() => ask(s)} className="card card-hover dash-rise flex items-center gap-2 px-3.5 py-3 text-left text-[13px] text-ink-2 hover:text-ink" style={{ animationDelay: `${i * 50}ms` }}>
                  <Icon name="arrowRight" size={13} className="text-ink-3" />
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-5 pb-4">
            {msgs.map((m) =>
              m.role === "user" ? (
                <div key={m.id} className="dash-rise flex justify-end">
                  <div className="max-w-[80%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-[13.5px] leading-relaxed text-[var(--accent-ink)] shadow-[var(--shadow-sm)]">{m.text}</div>
                </div>
              ) : (
                <Answer key={m.id} m={m} onInspect={() => openInspector(m.query, m.res?.timings ?? m.res?.timingsMs)} />
              ),
            )}
          </div>
        )}
      </div>

      <form
        id="tour-ask-box"
        className="glass-strong mx-auto mt-3 flex w-full max-w-3xl items-end gap-2 p-2"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(input);
        }}
      >
        <textarea
          ref={taRef}
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void ask(input);
            }
          }}
          placeholder={`Ask about ${project.name}…`}
          className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-2.5 py-2.5 text-[14px] text-ink outline-none placeholder:text-ink-3"
        />
        <span className="hidden items-center gap-1 pb-3 text-[11px] text-ink-3 sm:flex">
          <Kbd>↵</Kbd>
        </span>
        <button
          type="button"
          className="dash-btn h-10 w-10 p-0"
          style={rec ? { color: "var(--danger)", borderColor: "color-mix(in oklab, var(--danger) 45%, transparent)" } : undefined}
          onClick={() => (rec ? rec.stop() : void startDictation())}
          disabled={sttBusy}
          aria-label={rec ? "Stop dictation" : "Ask by voice"}
          title={rec ? "Stop and transcribe" : "Ask by voice (Hindi or English)"}
        >
          {sttBusy ? (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          ) : (
            <Icon name={rec ? "stop" : "mic"} size={15} />
          )}
        </button>
        <button type="submit" className="dash-btn dash-btn-primary h-10 w-10 p-0" disabled={busy || !input.trim()} aria-label="Ask">
          {busy ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <Icon name="send" size={15} />}
        </button>
      </form>

      <Sheet
        open={!!inspect}
        onClose={() => setInspect(null)}
        title={
          <span className="flex items-center gap-2">
            <Icon name="search" size={15} className="text-accent" /> Retrieval inspector
          </span>
        }
        subtitle={inspect ? `“${inspect.query}”` : null}
      >
        {inspect ? (
          <div className="space-y-5">
            <section>
              <p className="dash-eyebrow mb-2.5">Latency by leg</p>
              {inspect.loading ? <Skeleton className="h-20" /> : <LatencyBars timings={inspect.res?.timings ?? inspect.res?.timingsMs ?? inspect.askTimings} clientMs={inspect.ms} />}
            </section>
            <section>
              <p className="dash-eyebrow mb-2.5">Hits · POST /api/memory/search</p>
              {inspect.loading ? (
                <div className="space-y-2">
                  {[0, 1, 2].map((i) => (
                    <Skeleton key={i} className="h-24" />
                  ))}
                </div>
              ) : inspect.error ? (
                <Notice tone={inspect.missing ? "neutral" : "danger"} title={inspect.missing ? "/api/memory/search is not live yet" : "Search failed"}>
                  {inspect.missing ? "The inspector shows vector, BM25, RRF and rerank scores once the memory router is loaded." : <span className="font-mono text-[11.5px]">{inspect.error}</span>}
                </Notice>
              ) : inspect.res ? (
                <HitList hits={inspect.res.hits} rewrittenQuery={inspect.res.rewrittenQuery} abstain={inspect.res.abstain} />
              ) : null}
            </section>
          </div>
        ) : null}
      </Sheet>

      {/* Floats over the empty right-hand gutter rather than taking a column of its own, so the
          conversation stays centred at every width. Hidden below xl, where there is no gutter. */}
      {/* The wrapper does the positioning, not the panel: `.glass` declares `position: relative`
          in globals.css, which sits outside Tailwind's utility layer and beats `absolute`. */}
      <div className="absolute right-0 top-1 z-20 hidden xl:block">
        {!histOpen ? (
          <button
            className="glass flex items-center gap-1.5 px-3 py-2 text-[12px] text-ink-2 transition hover:text-ink"
            onClick={() => toggleHist(true)}
            title="Show chat history"
            aria-label="Show chat history"
          >
            <Icon name="clock" size={13} />
            History{threads.length ? ` · ${threads.length}` : ""}
          </button>
        ) : (
          <aside id="ask-history" className="glass flex w-[252px] flex-col p-2.5" style={{ maxHeight: "min(62vh, 520px)" }}>
        <div className="mb-2 flex items-center justify-between gap-1 pl-1">
          <p className="dash-eyebrow">History</p>
          <span className="flex items-center gap-1">
            <button className="dash-btn dash-btn-sm" onClick={newChat} title="Start a new chat">
              <Icon name="plus" size={13} /> New
            </button>
            <button
              className="dash-btn dash-btn-sm px-1.5"
              onClick={() => toggleHist(false)}
              title="Collapse history"
              aria-label="Collapse history"
            >
              <Icon name="x" size={13} />
            </button>
          </span>
        </div>

        <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-0.5">
          {threads.length === 0 ? (
            <p className="card px-3 py-2.5 text-[12px] leading-relaxed text-ink-3">
              Past questions land here. They stay in this browser — Ask is read-only, so nothing is written to the
              site record.
            </p>
          ) : (
            threads.map((t) => (
              <div
                key={t.id}
                className="group card card-hover flex items-start gap-2 px-3 py-2.5"
                style={t.id === activeId ? { borderColor: "var(--accent)" } : undefined}
              >
                <button onClick={() => openThread(t)} className="min-w-0 flex-1 text-left" title={t.title}>
                  <span className="block truncate text-[12.5px] leading-snug text-ink">{t.title}</span>
                  <span className="mt-0.5 block text-[11px] text-ink-3">
                    {new Date(t.updatedAt).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                    {" · "}
                    {new Date(t.updatedAt).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </button>
                <button
                  onClick={() => deleteThread(t.id)}
                  aria-label={`Delete thread: ${t.title}`}
                  title="Delete"
                  className="mt-0.5 shrink-0 text-ink-3 opacity-0 transition hover:text-ink focus:opacity-100 group-hover:opacity-100"
                >
                  <Icon name="x" size={12} />
                </button>
              </div>
            ))
          )}
        </div>
          </aside>
        )}
      </div>
    </div>
  );
}

function Answer({ m, onInspect }: { m: Extract<Msg, { role: "assistant" }>; onInspect: () => void }) {
  if (m.pending)
    return (
      <div className="dash-rise flex gap-3">
        <Avatar />
        <div className="flex-1 space-y-2 pt-1">
          <Skeleton className="h-3.5 w-3/4" />
          <Skeleton className="h-3.5 w-1/2" />
          <p className="text-[11.5px] text-ink-3">Retrieving · reranking · composing…</p>
        </div>
      </div>
    );
  if (m.error)
    return (
      <div className="flex gap-3">
        <Avatar />
        <div className="flex-1">
          <Notice tone="danger" title="The memory could not answer">
            <span className="font-mono text-[11.5px]">{m.error}</span>
          </Notice>
        </div>
      </div>
    );
  const r = m.res!;
  return (
    <div className="dash-rise flex gap-3">
      <Avatar />
      <div className="min-w-0 flex-1">
        {r.abstain ? (
          <div className="rounded-2xl border border-dashed px-4 py-3" style={{ borderColor: "color-mix(in oklab, var(--warn) 45%, transparent)", background: "color-mix(in oklab, var(--warn) 6%, transparent)" }}>
            <p className="flex items-center gap-2 text-[12px] font-medium" style={{ color: "var(--warn)" }}>
              <Icon name="alert" size={13} /> Not enough evidence — Vesper abstained
            </p>
            <p className="mt-1.5 whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink-2">{r.answer}</p>
          </div>
        ) : (
          <p className="whitespace-pre-wrap text-[14px] leading-[1.65] text-ink">{r.answer}</p>
        )}
        {r.citations?.length ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {r.citations.map((c, i) => {
              const inner = (
                <>
                  <span className="grid h-4 min-w-4 place-items-center rounded bg-surface-2 px-1 font-mono text-[10px] text-ink-2">{i + 1}</span>
                  <span className="max-w-[260px] truncate">{c.citation || [c.title, c.section].filter(Boolean).join(" · ")}</span>
                </>
              );
              const cls = "inline-flex h-7 items-center gap-1.5 rounded-full border border-line bg-surface pl-1 pr-2.5 text-[12px] text-ink-2 transition hover:border-[var(--border-strong)] hover:text-ink";
              return c.url ? (
                <a key={i} href={c.url} target="_blank" rel="noreferrer" className={cls} title={c.title}>
                  {inner}
                </a>
              ) : (
                <span key={i} className={cls} title={c.title}>
                  {inner}
                </span>
              );
            })}
          </div>
        ) : null}
        <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[11.5px] text-ink-3">
          {m.via === "engine" ? <Badge tone="warn">v1 site engine · memory layer offline</Badge> : <Badge tone="accent">memory</Badge>}
          {!r.abstain && m.via === "memory" ? <span className="tabular-nums">confidence {(r.confidence * 100).toFixed(0)}%</span> : null}
          {m.ms != null ? <span className="tabular-nums">{Math.round(m.ms)} ms</span> : null}
          <SpeakAnswer text={r.answer} />
          <button onClick={onInspect} className="ml-auto inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 hover:bg-surface-2 hover:text-ink">
            <Icon name="search" size={12} /> Inspect retrieval
          </button>
        </div>
      </div>
    </div>
  );
}

/** Read the grounded answer out loud through /api/tts (Sarvam bulbul). Useful on site, where the
 *  manager is holding a drawing rather than looking at the screen. */
function SpeakAnswer({ text }: { text: string }) {
  const [state, setState] = useState<"idle" | "loading" | "playing">("idle");
  const [failed, setFailed] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null);

  useEffect(
    () => () => {
      audio.current?.pause();
      audio.current = null;
    },
    [],
  );

  const stop = () => {
    audio.current?.pause();
    audio.current = null;
    setState("idle");
  };

  const speak = async () => {
    if (state === "playing") return stop();
    if (state === "loading") return;

    // Use Web Speech API directly in the browser
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      const voices = window.speechSynthesis.getVoices();
      const preferred =
        voices.find((v) => v.lang.toLowerCase().startsWith("en-in")) ||
        voices.find((v) => v.lang.toLowerCase().startsWith("en"));
      if (preferred) u.voice = preferred;
      u.onstart = () => setState("playing");
      u.onend = () => setState("idle");
      u.onerror = () => {
        setFailed(true);
        setState("idle");
      };
      window.speechSynthesis.speak(u);
      return;
    }

    setState("loading");
    setFailed(false);
    const res = await api.tts(text);
    if (!res.ok) {
      setFailed(true);
      setState("idle");
      return;
    }
    const url = URL.createObjectURL(res.blob);
    const el = new Audio(url);
    audio.current = el;
    const cleanup = () => {
      URL.revokeObjectURL(url);
      audio.current = null;
      setState("idle");
    };
    el.onended = cleanup;
    el.onerror = () => {
      setFailed(true);
      cleanup();
    };
    try {
      await el.play();
      setState("playing");
    } catch {
      setFailed(true);
      cleanup();
    }
  };

  return (
    <button
      onClick={() => void speak()}
      className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 hover:bg-surface-2 hover:text-ink"
      title={failed ? "Speech is unavailable on this backend" : state === "playing" ? "Stop" : "Read this answer aloud"}
      aria-label={state === "playing" ? "Stop reading" : "Read this answer aloud"}
    >
      {state === "loading" ? (
        <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
      ) : (
        <Icon name={state === "playing" ? "stop" : "play"} size={12} />
      )}
      {state === "playing" ? "Stop" : failed ? "No audio" : "Listen"}
    </button>
  );
}

function Avatar() {
  return (
    <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-white" style={{ background: "linear-gradient(135deg, var(--accent), var(--accent-2))" }}>
      <Icon name="sparkles" size={13} />
    </span>
  );
}
