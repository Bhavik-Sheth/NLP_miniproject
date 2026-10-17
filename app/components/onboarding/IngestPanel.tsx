"use client";

// Project memory ingestion: upload documents, paste text, or speak a note. W3 mounts this in the
// dashboard: <IngestPanel projectId="…" />. Styles come from onboarding.css (scoped under .vo).
import "./onboarding.css";
import { useCallback, useEffect, useRef, useState } from "react";
import { ingestApi, type IngestJob } from "@/lib/api-tenancy";
import { fmtBytes } from "./FieldRenderer";
import { fmtSeconds, useRecorder } from "./useRecorder";
import { Callout, OIcon, Spin } from "./primitives";

export const INGEST_CATEGORIES: { value: string; label: string }[] = [
  { value: "drawing_register", label: "Drawing register" },
  { value: "spec", label: "Specification" },
  { value: "method_statement", label: "Method statement" },
  { value: "rfi", label: "RFI" },
  { value: "permit", label: "Permit" },
  { value: "dpr", label: "Daily progress report" },
  { value: "boq", label: "BOQ" },
  { value: "contract", label: "Contract" },
  { value: "itp", label: "ITP" },
  { value: "other", label: "Other" },
];

const ACCEPT = ".pdf,.docx,.doc,.xlsx,.xls,.csv,.txt,.md,.png,.jpg,.jpeg,.webp,.heic";
const ACTIVE = new Set(["queued", "parsing", "embedding", "graph", "uploading"]);

type Mode = "upload" | "text" | "voice";

type LocalJob = IngestJob & { local?: true; size?: number };

export type IngestPanelProps = {
  projectId: string;
  className?: string;
  /** called whenever a job reaches done */
  onIngested?: (job: IngestJob) => void;
  defaultMode?: Mode;
  /** hide the outer glass card (when the host already provides one) */
  bare?: boolean;
};

export function IngestPanel({ projectId, className = "", onIngested, defaultMode = "upload", bare = false }: IngestPanelProps) {
  const [mode, setMode] = useState<Mode>(defaultMode);
  const [jobs, setJobs] = useState<LocalJob[]>([]);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const seenDone = useRef(new Set<string>());

  const refresh = useCallback(async () => {
    try {
      const list = await ingestApi.jobs(projectId);
      setJobsError(null);
      setJobs((prev) => {
        const remoteIds = new Set(list.map((j) => j.jobId));
        const locals = prev.filter((j) => j.local && !remoteIds.has(j.jobId) && (ACTIVE.has(j.status) || j.status === "error"));
        return [...locals, ...list];
      });
      for (const j of list)
        if (j.status === "done" && !seenDone.current.has(j.jobId)) {
          seenDone.current.add(j.jobId);
          onIngested?.(j);
        }
    } catch (e) {
      const status = (e as { status?: number }).status;
      setJobsError(status === 404 ? "Ingest API isn't loaded on the backend yet." : status === 0 ? "Backend unreachable." : (e as Error).message);
    }
  }, [projectId, onIngested]);

  // mark every job already done at first load as seen
  useEffect(() => {
    seenDone.current = new Set();
    let first = true;
    ingestApi
      .jobs(projectId)
      .then((l) => {
        if (first) l.filter((j) => j.status === "done").forEach((j) => seenDone.current.add(j.jobId));
        setJobs(l);
      })
      .catch(() => {})
      .finally(() => {
        first = false;
      });
  }, [projectId]);

  const anyActive = jobs.some((j) => ACTIVE.has(j.status));
  useEffect(() => {
    if (!anyActive) return;
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [anyActive, refresh]);

  const addLocal = (j: LocalJob) => setJobs((prev) => [j, ...prev]);
  const patchLocal = (id: string, patch: Partial<LocalJob>) => setJobs((prev) => prev.map((j) => (j.jobId === id ? { ...j, ...patch } : j)));

  const body = (
    <>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="vo-eyebrow">Project memory</div>
          <h3 className="mt-1 text-[17px] font-semibold tracking-[-0.015em]">Add knowledge</h3>
        </div>
        <div className="vo-seg w-fit" role="tablist" aria-label="Ingest mode">
          {(
            [
              ["upload", "upload", "Upload"],
              ["text", "text", "Paste text"],
              ["voice", "mic", "Speak"],
            ] as const
          ).map(([m, icon, label]) => (
            <button key={m} role="tab" type="button" aria-selected={mode === m} onClick={() => setMode(m)}>
              <OIcon name={icon} size={13} /> {label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-5" role="tabpanel">
        {mode === "upload" ? <UploadMode projectId={projectId} addLocal={addLocal} patchLocal={patchLocal} refresh={refresh} /> : null}
        {mode === "text" ? <TextMode projectId={projectId} addLocal={addLocal} refresh={refresh} /> : null}
        {mode === "voice" ? <VoiceMode projectId={projectId} addLocal={addLocal} refresh={refresh} /> : null}
      </div>

      <JobList jobs={jobs} error={jobsError} onRefresh={refresh} />
    </>
  );

  return <div className={`vo ${className}`}>{bare ? body : <div className="vo-glass p-5 sm:p-6">{body}</div>}</div>;
}

export default IngestPanel;

// ---------- upload ----------

function UploadMode({
  projectId,
  addLocal,
  patchLocal,
  refresh,
}: {
  projectId: string;
  addLocal: (j: LocalJob) => void;
  patchLocal: (id: string, p: Partial<LocalJob>) => void;
  refresh: () => Promise<void>;
}) {
  const [category, setCategory] = useState("other");
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const upload = async (list: FileList | File[] | null) => {
    const files = Array.from(list ?? []);
    if (!files.length) return;
    await Promise.all(
      files.map(async (file) => {
        const tmp = `local-${crypto.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
        addLocal({ jobId: tmp, title: file.name, status: "uploading", progress: 0.05, category, local: true, size: file.size });
        try {
          const r = await ingestApi.file({ projectId, file, category });
          patchLocal(tmp, { jobId: r.jobId, docId: r.docId, status: r.status, progress: 0.15, local: true });
        } catch (e) {
          patchLocal(tmp, { status: "error", error: (e as Error).message, progress: 1 });
        }
      }),
    );
    void refresh();
  };

  return (
    <div className="flex flex-col gap-3">
      <div
        role="button"
        tabIndex={0}
        className="vo-drop flex flex-col items-center justify-center gap-2 px-6 py-9 text-center"
        data-over={over}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), input.current?.click())}
        onDragOver={(e) => (e.preventDefault(), setOver(true))}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => (e.preventDefault(), setOver(false), void upload(e.dataTransfer.files))}
        aria-label="Upload documents"
      >
        <span className="grid h-11 w-11 place-items-center rounded-full" style={{ background: "var(--vo-surface-2)", color: "var(--vo-text-2)" }}>
          <OIcon name="upload" size={18} />
        </span>
        <div className="text-[14px]">
          Drop documents here or <span style={{ color: "var(--vo-accent)" }}>browse</span>
        </div>
        <div className="vo-faint text-[12px]">PDF, DOCX, XLSX, CSV, TXT, images · multiple files</div>
        <input ref={input} type="file" hidden multiple accept={ACCEPT} onChange={(e) => (void upload(e.target.files), (e.target.value = ""))} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="vo-faint text-[12.5px]" htmlFor="ingest-cat">
          Category
        </label>
        <select id="ingest-cat" className="vo-input h-9 min-h-0 w-auto py-0 text-[13px]" value={category} onChange={(e) => setCategory(e.target.value)}>
          {INGEST_CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
        <span className="vo-faint text-[12px]">applies to the next files you add</span>
      </div>
    </div>
  );
}

// ---------- text ----------

function TextMode({ projectId, addLocal, refresh }: { projectId: string; addLocal: (j: LocalJob) => void; refresh: () => Promise<void> }) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [category, setCategory] = useState("other");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  const submit = async () => {
    if (!title.trim() || !text.trim()) return setErr("Add a title and some text.");
    setBusy(true);
    setErr(null);
    try {
      const r = await ingestApi.text({ projectId, title: title.trim(), text, category });
      addLocal({ jobId: r.jobId, docId: r.docId, title: title.trim(), status: r.status, progress: 0.15, category, local: true });
      setTitle("");
      setText("");
      setOk(true);
      setTimeout(() => setOk(false), 2400);
      void refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_200px]">
        <input className="vo-input" placeholder="Title — e.g. Slab pour sequence, Block B" value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Title" />
        <select className="vo-input" value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
          {INGEST_CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </div>
      <textarea
        className="vo-input min-h-[160px] font-[450]"
        placeholder="Paste meeting minutes, a clause, an email thread, a method statement…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        aria-label="Text"
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
            e.preventDefault();
            e.stopPropagation();
            void submit();
          }
        }}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="vo-faint text-[12px]">
          {text.length ? `${text.trim().split(/\s+/).length.toLocaleString()} words` : "⌘↵ to add"}
        </span>
        <div className="flex items-center gap-2">
          {ok ? (
            <span className="vo-fade inline-flex items-center gap-1 text-[12.5px]" style={{ color: "var(--vo-ok)" }}>
              <OIcon name="check" size={13} /> Queued
            </span>
          ) : null}
          <button type="submit" className="vo-btn vo-btn-primary" disabled={busy || !title.trim() || !text.trim()}>
            {busy ? <Spin /> : <OIcon name="plus" size={14} />} Add to memory
          </button>
        </div>
      </div>
      {err ? <Callout tone="danger">{err}</Callout> : null}
    </form>
  );
}

// ---------- voice ----------

function VoiceMode({ projectId, addLocal, refresh }: { projectId: string; addLocal: (j: LocalJob) => void; refresh: () => Promise<void> }) {
  const rec = useRecorder();
  const [title, setTitle] = useState("");
  const [blob, setBlob] = useState<Blob | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ transcript: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const recording = rec.state === "recording";

  useEffect(() => () => void (audioUrl && URL.revokeObjectURL(audioUrl)), [audioUrl]);

  const toggle = async () => {
    setErr(null);
    if (recording) {
      const b = await rec.stop();
      if (b) {
        setBlob(b);
        setAudioUrl(URL.createObjectURL(b));
      }
      return;
    }
    setBlob(null);
    setResult(null);
    setAudioUrl(null);
    await rec.start();
  };

  const send = async () => {
    if (!blob) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await ingestApi.voice({ projectId, audio: blob, title: title.trim() || undefined });
      setResult({ transcript: r.transcript });
      addLocal({ jobId: r.jobId, docId: r.docId, title: title.trim() || "Voice note", status: "queued", progress: 0.15, category: "voice_note", local: true });
      void refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const discard = () => {
    setBlob(null);
    setResult(null);
    setAudioUrl(null);
    setTitle("");
    rec.reset();
  };

  const bars = 28;
  return (
    <div className="flex flex-col items-center gap-4 py-2">
      <button type="button" className="vo-orb" data-rec={recording} style={{ ["--lvl" as string]: rec.level.toFixed(3) }} onClick={toggle} disabled={busy || rec.state === "requesting"} aria-label={recording ? "Stop recording" : "Start recording"}>
        {rec.state === "requesting" ? <Spin size={22} /> : <OIcon name={recording ? "stop" : "mic"} size={30} />}
      </button>

      <div className="flex h-9 items-center gap-3" aria-hidden={!recording}>
        {recording ? (
          <>
            <span className="font-mono text-[13px] tabular-nums" style={{ color: "var(--vo-danger)" }}>
              ● {fmtSeconds(rec.elapsed)}
            </span>
            <div className="vo-level">
              {Array.from({ length: bars }, (_, i) => {
                const wobble = 0.55 + 0.45 * Math.abs(Math.sin(i * 1.7 + rec.elapsed * 9));
                const h = 4 + rec.level * 30 * wobble;
                return <i key={i} style={{ height: `${Math.min(34, h)}px`, opacity: 0.45 + rec.level * 0.55 }} />;
              })}
            </div>
          </>
        ) : (
          <span className="vo-muted text-[13px]">{blob ? `Recorded ${fmtSeconds(rec.elapsed)} · ${fmtBytes(blob.size)}` : "Tap to record a site note, briefing or decision"}</span>
        )}
      </div>

      {rec.error ? <Callout tone="warn">{rec.error}</Callout> : null}

      {blob && !recording && !result ? (
        <div className="vo-fade flex w-full flex-col gap-3">
          {audioUrl ? <audio controls src={audioUrl} className="h-9 w-full" /> : null}
          <input className="vo-input" placeholder="Title (optional) — e.g. Morning briefing 15 Sep" value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Voice note title" />
          <div className="flex justify-end gap-2">
            <button type="button" className="vo-btn vo-btn-quiet" onClick={discard} disabled={busy}>
              Discard
            </button>
            <button type="button" className="vo-btn vo-btn-primary" onClick={send} disabled={busy}>
              {busy ? <Spin /> : <OIcon name="arrowRight" size={14} />} {busy ? "Transcribing…" : "Transcribe & add"}
            </button>
          </div>
        </div>
      ) : null}

      {result ? (
        <div className="vo-fade w-full">
          <div className="vo-card p-4">
            <div className="vo-eyebrow mb-2">Transcript</div>
            <p className="whitespace-pre-wrap text-[14px] leading-relaxed">{result.transcript || <span className="vo-faint">(empty)</span>}</p>
          </div>
          <div className="mt-3 flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 text-[12.5px]" style={{ color: "var(--vo-ok)" }}>
              <OIcon name="check" size={13} /> Added to project memory
            </span>
            <button type="button" className="vo-btn vo-btn-ghost vo-btn-sm" onClick={discard}>
              Record another
            </button>
          </div>
        </div>
      ) : null}

      {err ? <Callout tone="danger">{err}</Callout> : null}
    </div>
  );
}

// ---------- jobs ----------

const STAGES = ["queued", "parsing", "embedding", "graph", "done"];
const STAGE_LABEL: Record<string, string> = {
  uploading: "Uploading",
  queued: "Queued",
  parsing: "Parsing",
  embedding: "Embedding",
  graph: "Building graph",
  done: "In memory",
  error: "Failed",
};

function jobPct(j: LocalJob) {
  if (j.status === "done") return 100;
  if (typeof j.progress === "number") return Math.round((j.progress <= 1 ? j.progress * 100 : j.progress) || 0);
  const i = STAGES.indexOf(j.status);
  return i < 0 ? 5 : Math.round(((i + 0.5) / STAGES.length) * 100);
}

function JobList({ jobs, error, onRefresh }: { jobs: LocalJob[]; error: string | null; onRefresh: () => void }) {
  if (!jobs.length && !error) return null;
  return (
    <div className="mt-6">
      <div className="mb-2 flex items-center justify-between">
        <span className="vo-eyebrow">Recent ingestion</span>
        <button type="button" className="vo-btn vo-btn-quiet vo-btn-icon h-7 w-7" onClick={onRefresh} aria-label="Refresh jobs">
          <OIcon name="refresh" size={13} />
        </button>
      </div>
      {error ? <p className="vo-faint mb-2 text-[12.5px]">{error}</p> : null}
      <ul className="flex flex-col gap-1.5" aria-live="polite">
        {jobs.slice(0, 12).map((j) => {
          const active = ACTIVE.has(j.status);
          const pct = jobPct(j);
          const color = j.status === "error" ? "var(--vo-danger)" : j.status === "done" ? "var(--vo-ok)" : "var(--vo-text-2)";
          return (
            <li key={j.jobId} className="vo-card vo-fade px-3.5 py-2.5">
              <div className="flex items-center gap-2.5 text-[13px]">
                <span className="grid h-5 w-5 flex-none place-items-center" style={{ color }}>
                  {active ? <Spin size={13} /> : j.status === "done" ? <OIcon name="check" size={14} strokeWidth={2.2} /> : j.status === "error" ? <OIcon name="alert" size={14} /> : <OIcon name="file" size={14} />}
                </span>
                <span className="min-w-0 flex-1 truncate">{j.title || j.docId || j.jobId}</span>
                {j.category ? <span className="vo-faint hidden text-[11.5px] sm:inline">{INGEST_CATEGORIES.find((c) => c.value === j.category)?.label ?? j.category}</span> : null}
                <span className="font-mono text-[11.5px]" style={{ color }}>
                  {STAGE_LABEL[j.status] ?? j.status}
                  {active ? ` ${pct}%` : ""}
                </span>
              </div>
              {active || j.status === "error" ? (
                <div className={`vo-progress mt-2 ${active ? "is-active" : ""}`}>
                  <i style={{ width: `${Math.max(pct, 4)}%`, ...(j.status === "error" ? { background: "var(--vo-danger)" } : {}) }} />
                </div>
              ) : null}
              {j.error ? <p className="mt-1.5 text-[12px]" style={{ color: "var(--vo-danger)" }}>{j.error}</p> : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
