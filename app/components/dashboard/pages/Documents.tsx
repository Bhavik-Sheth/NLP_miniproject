"use client";

import { useCallback, useRef, useState } from "react";
import { IngestPanel } from "@/components/onboarding/IngestPanel";
import { apiV2, isMissing } from "@/lib/api-v2";
import { useDash } from "../context";
import { Icon } from "../icons";
import { Badge, EndpointNotice, Empty, Notice, PageHeader, Panel, Segmented, Skeleton, statusTone, useAsync } from "../primitives";

// Mounts W4's IngestPanel (upload / text / voice + live job progress) next to the memory's document list.

const CATEGORIES = ["drawing", "specification", "method_statement", "boq", "contract", "report", "other"];

export default function Documents() {
  const { project } = useDash();
  const docs = useAsync(() => apiV2.documents(project.id), [project.id]);
  return (
    <div>
      <PageHeader eyebrow="Knowledge" title="Documents & ingest" description="Add drawings, specs, BOQs, method statements and site voice notes. Each is parsed, chunked, embedded with bge-m3 and linked into the project graph." />
      <div className="grid gap-5 xl:grid-cols-[1.1fr_1fr]">
        <div id="tour-ingest">
          <IngestPanel projectId={project.id} onIngested={() => docs.reload()} />
        </div>
        <Panel title="In project memory" icon="file" bodyClassName="p-2" action={<button className="dash-btn dash-btn-ghost dash-btn-sm" onClick={docs.reload} aria-label="Refresh"><Icon name="refresh" size={12} /></button>}>
          {docs.loading && !docs.data ? (
            <div className="space-y-2 p-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
          ) : docs.error ? (
            <div className="p-2"><EndpointNotice state={docs} endpoint="GET /api/memory/documents" /></div>
          ) : !docs.data?.length ? (
            <Empty icon="upload" title="Nothing ingested yet" body="Documents appear here once they finish parse → embed → graph." />
          ) : (
            <ul className="divide-y divide-line">
              {docs.data.map((d) => (
                <li key={d.docId} className="flex items-center gap-3 px-2.5 py-2.5">
                  <Icon name="file" size={15} className="text-ink-3" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium text-ink">{d.title}</p>
                    <p className="truncate text-[11.5px] text-ink-3">{[d.category, `${d.chunks} chunks`, d.source].filter(Boolean).join(" · ")}</p>
                  </div>
                  <Badge tone={statusTone(d.status)} dot>{d.status}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}

// Fallback ingest forms (same PLAN §4 API) kept for hosts without W4's IngestPanel.
export function IngestForms({ projectId, onQueued }: { projectId: string; onQueued: () => void }) {
  const [mode, setMode] = useState<"file" | "text" | "voice">("file");
  const [category, setCategory] = useState("other");
  const [msg, setMsg] = useState<{ tone: "ok" | "danger" | "neutral"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const report = (e: unknown) =>
    setMsg(isMissing(e) ? { tone: "neutral", text: "The ingest API is not live on this backend yet (W1). Your file was not uploaded." } : { tone: "danger", text: (e as Error).message });

  const upload = async (files: FileList | File[]) => {
    setBusy(true);
    setMsg(null);
    try {
      for (const f of Array.from(files)) await apiV2.ingestFile(projectId, f, category);
      setMsg({ tone: "ok", text: `Queued ${files.length} file${files.length > 1 ? "s" : ""} for ingest.` });
      onQueued();
    } catch (e) {
      report(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title="Add to project memory" icon="upload" action={<Segmented size="sm" value={mode} onChange={setMode} options={[{ value: "file", label: "File" }, { value: "text", label: "Text" }, { value: "voice", label: "Voice note" }]} />}>
      <div className="space-y-4">
        {mode !== "voice" ? (
          <label className="block text-[12px] text-ink-2">
            Category
            <select className="dash-input mt-1" value={category} onChange={(e) => setCategory(e.target.value)}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {mode === "file" ? (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              if (e.dataTransfer.files.length) void upload(e.dataTransfer.files);
            }}
            onClick={() => fileRef.current?.click()}
            className={`glass flex cursor-pointer flex-col items-center justify-center px-6 py-12 text-center transition ${drag ? "scale-[1.01]" : ""}`}
            style={drag ? { borderColor: "var(--accent)" } : undefined}
          >
            <div className="mb-3 grid h-12 w-12 place-items-center rounded-2xl border border-line bg-surface text-accent">
              {busy ? <span className="h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <Icon name="upload" size={20} />}
            </div>
            <p className="text-[14px] font-medium text-ink">{busy ? "Uploading…" : "Drop files or click to browse"}</p>
            <p className="mt-1 text-[12px] text-ink-3">PDF, DOCX, XLSX / CSV, TXT / MD, images (OCR)</p>
            <input ref={fileRef} type="file" multiple hidden accept=".pdf,.docx,.xlsx,.csv,.txt,.md,image/*" onChange={(e) => e.target.files && void upload(e.target.files)} />
          </div>
        ) : mode === "text" ? (
          <form
            className="space-y-3"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setMsg(null);
              try {
                await apiV2.ingestText({ projectId, title, text, category });
                setMsg({ tone: "ok", text: "Text queued for ingest." });
                setTitle("");
                setText("");
                onQueued();
              } catch (err) {
                report(err);
              } finally {
                setBusy(false);
              }
            }}
          >
            <input className="dash-input" placeholder="Title — e.g. Slab L4 pour sequence" value={title} onChange={(e) => setTitle(e.target.value)} required />
            <textarea className="dash-input" rows={8} placeholder="Paste a method statement, minutes of meeting, specification clause…" value={text} onChange={(e) => setText(e.target.value)} required />
            <button className="dash-btn dash-btn-primary" disabled={busy || !title || !text}>
              Add to memory
            </button>
          </form>
        ) : (
          <VoiceNote projectId={projectId} onDone={onQueued} setMsg={setMsg} report={report} />
        )}
        {msg ? <Notice tone={msg.tone} title={msg.text} /> : null}
      </div>
    </Panel>
  );
}

function VoiceNote({ projectId, onDone, setMsg, report }: { projectId: string; onDone: () => void; setMsg: (m: { tone: "ok" | "danger" | "neutral"; text: string } | null) => void; report: (e: unknown) => void }) {
  const [rec, setRec] = useState<MediaRecorder | null>(null);
  const [secs, setSecs] = useState(0);
  const [title, setTitle] = useState("");
  const [transcript, setTranscript] = useState<string | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<number | null>(null);

  const stop = useCallback(() => {
    rec?.stop();
    if (timer.current) window.clearInterval(timer.current);
  }, [rec]);

  const start = async () => {
    setMsg(null);
    setTranscript(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunks.current = [];
      mr.ondataavailable = (e) => chunks.current.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRec(null);
        try {
          const r = await apiV2.ingestVoice(projectId, new Blob(chunks.current, { type: "audio/webm" }), title || undefined);
          setTranscript(r.transcript ?? null);
          setMsg({ tone: "ok", text: "Voice note transcribed with Sarvam and queued." });
          onDone();
        } catch (e) {
          report(e);
        }
      };
      mr.start();
      setRec(mr);
      setSecs(0);
      timer.current = window.setInterval(() => setSecs((s) => s + 1), 1000);
    } catch (e) {
      setMsg({ tone: "danger", text: `Microphone unavailable: ${(e as Error).message}` });
    }
  };

  return (
    <div className="space-y-3">
      <input className="dash-input" placeholder="Title (optional)" value={title} onChange={(e) => setTitle(e.target.value)} />
      <div className="glass flex flex-col items-center py-8">
        <button className="dash-orb" style={{ width: 84, height: 84 }} data-active={!!rec} onClick={rec ? stop : start} aria-label={rec ? "Stop recording" : "Record voice note"}>
          <span className="dash-orb-ring" />
          <span className="dash-orb-ring r2" />
          <span className="dash-orb-core" />
          <span className="relative text-white">
            <Icon name={rec ? "stop" : "mic"} size={24} strokeWidth={2} />
          </span>
        </button>
        <p className="mt-4 text-[13px] text-ink-2">{rec ? `Recording · ${secs}s — tap to stop` : "Record a site voice note (Hindi / English)"}</p>
      </div>
      {transcript ? <p className="card p-3 text-[13px] leading-relaxed text-ink-2">{transcript}</p> : null}
    </div>
  );
}
