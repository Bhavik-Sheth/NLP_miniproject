"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Card, ErrorBanner, Button, WaveVisualizer } from "@/components/ui";

type VoiceStatus = {
  enabled: boolean;
  reachable: boolean;
  enrolled: boolean;
  threshold: number;
};

const TAKE_SECONDS = 6;
const PROMPTS = [
  "“Column C-5 pe rebar spacing check kiya, drawing A-102 revision R4.”",
  "“Beam B-12 ka concrete cover theek hai, drawing S-201 revision R2.”",
  "“Slab level 3 pe crack dekha, drawing A-305 revision R1.”",
];

export default function EnrollScreen({
  onEnrolledChange,
}: {
  onEnrolledChange?: (enrolled: boolean) => void;
}) {
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [statusErr, setStatusErr] = useState<string | null>(null);
  const [clips, setClips] = useState<(Blob | null)[]>([null, null, null]);
  const [recordingIdx, setRecordingIdx] = useState<number | null>(null);
  const [countdown, setCountdown] = useState(0);
  const [enrolling, setEnrolling] = useState(false);
  const [enrollErr, setEnrollErr] = useState<string | null>(null);
  const [result, setResult] = useState<{
    samples: number;
    cohesion: number;
  } | null>(null);
  const [done, setDone] = useState(false);

  const mrRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadStatus = useCallback(async () => {
    setStatusErr(null);
    try {
      const s = await api.voiceStatus();
      setStatus(s);
      onEnrolledChange?.(s.enrolled);
    } catch (e) {
      setStatusErr((e as Error).message);
    }
  }, [onEnrolledChange]);

  useEffect(() => {
    void loadStatus();
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, [loadStatus]);

  const stopTake = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (mrRef.current && mrRef.current.state !== "inactive") {
      mrRef.current.stop();
    }
  }, []);

  const startTake = useCallback(
    async (idx: number) => {
      setEnrollErr(null);
      setResult(null);
      setDone(false);
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
        });
        streamRef.current = stream;
        chunksRef.current = [];
        const mr = new MediaRecorder(stream, { mimeType: "audio/webm" });
        mrRef.current = mr;
        mr.ondataavailable = (e) => {
          if (e.data.size > 0) chunksRef.current.push(e.data);
        };
        mr.onstop = () => {
          const blob = new Blob(chunksRef.current, { type: "audio/webm" });
          streamRef.current?.getTracks().forEach((t) => t.stop());
          streamRef.current = null;
          setClips((prev) => {
            const next = [...prev];
            next[idx] = blob.size > 0 ? blob : null;
            return next;
          });
          setRecordingIdx(null);
          setCountdown(0);
        };
        mr.start();
        setRecordingIdx(idx);
        setCountdown(TAKE_SECONDS);
        timerRef.current = setInterval(() => {
          setCountdown((c) => {
            if (c <= 1) {
              stopTake();
              return 0;
            }
            return c - 1;
          });
        }, 1000);
      } catch (e) {
        setEnrollErr(`Microphone unavailable: ${(e as Error).message}`);
      }
    },
    [stopTake],
  );

  const capturedCount = clips.filter(Boolean).length;
  const enrollmentUnavailable = status?.enabled === false || status?.reachable === false;

  const enroll = async () => {
    const blobs = clips.filter((b): b is Blob => b != null);
    if (blobs.length < 3) return;
    setEnrolling(true);
    setEnrollErr(null);
    setResult(null);
    try {
      const r = await api.voiceEnroll(blobs);
      setResult({ samples: r.samples, cohesion: r.cohesion });
      if (r.enrolled) {
        setDone(true);
        await loadStatus();
      }
    } catch (e) {
      setEnrollErr((e as Error).message);
    } finally {
      setEnrolling(false);
    }
  };

  return (
    <div id="tour-enroll" className="flex flex-col gap-4">
      {/* Header section */}
      <div className="flex items-center justify-between px-1">
        <div>
          <span className="text-[10px] font-mono tracking-wider uppercase text-zinc-400">
            Biometric VoiceID Gate
          </span>
          <h2 className="text-lg font-medium text-white tracking-tight">
            Speaker <span className="editorial-em">Enrollment</span>
          </h2>
        </div>
        <Button variant="ghost" size="sm" onClick={loadStatus}>
          Refresh
        </Button>
      </div>

      <ErrorBanner msg={statusErr} />

      {/* VoiceID status badge card */}
      {status ? (
        <Card title="Telemetry · Voice Verification Engine">
          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <div className="flex items-center gap-2">
              <span className="text-zinc-500">Service:</span>
              <span className={status.reachable ? "text-emerald-400" : "text-red-400"}>
                {status.reachable ? "ONLINE" : "UNREACHABLE"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-zinc-500">Status:</span>
              <span className={status.enrolled ? "text-emerald-400 font-semibold" : "text-amber-400"}>
                {status.enrolled ? "ENROLLED" : "PENDING"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-zinc-500">Threshold:</span>
              <span className="text-zinc-200">{status.threshold}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-zinc-500">Enforcement:</span>
              <span className={status.enabled ? "text-zinc-200" : "text-zinc-500"}>
                {status.enabled ? "ACTIVE" : "BYPASSED"}
              </span>
            </div>
          </div>
        </Card>
      ) : null}

      {status?.enabled === false ? (
        <Card tone="amber" title="Voice enrollment is unavailable">
          <p className="text-xs leading-relaxed text-amber-100">
            Speaker verification is disabled on this server. Start the app with <code>SPEAKER_ID_ENABLED=true</code> and the VoiceID sidecar, then refresh this page.
          </p>
        </Card>
      ) : status?.reachable === false ? (
        <Card tone="amber" title="VoiceID service is offline">
          <p className="text-xs leading-relaxed text-amber-100">
            Speaker verification is enabled but the VoiceID sidecar cannot be reached. Start it on the configured service URL, then refresh this page.
          </p>
        </Card>
      ) : (
        <p className="text-xs text-zinc-400 px-1 leading-relaxed">
          Record 3 canonical Hindi / Hinglish phrases (~{TAKE_SECONDS}s each) to train the site manager voice model.
        </p>
      )}

      {/* 3 Voice Take Cards */}
      <div className="space-y-2.5">
        {[0, 1, 2].map((idx) => {
          const isRec = recordingIdx === idx;
          const captured = clips[idx] != null;
          return (
            <Card
              key={idx}
              tone={captured ? "green" : isRec ? "red" : "neutral"}
              title={`Sample Take 0${idx + 1}`}
            >
              <p className="text-xs text-zinc-200 mb-3 leading-relaxed font-sans italic">
                {PROMPTS[idx]}
              </p>
              <div className="flex items-center justify-between">
                <Button
                  variant={isRec ? "ghost" : captured ? "ghost" : "solid"}
                  size="sm"
                  onClick={() => (isRec ? stopTake() : startTake(idx))}
                  disabled={enrollmentUnavailable || (recordingIdx != null && !isRec)}
                  className={isRec ? "border-red-500 text-red-200 bg-red-950/60" : ""}
                >
                  {isRec ? (
                    <span className="flex items-center gap-1.5 text-red-300">
                      <span className="w-2 h-2 rounded-full bg-red-500 animate-ping" />
                      Stop ({countdown}s)
                    </span>
                  ) : captured ? (
                    "Re-record"
                  ) : (
                    "Record Phrase"
                  )}
                </Button>

                {isRec ? (
                  <div className="flex items-center gap-2 text-red-400 text-xs">
                    <WaveVisualizer active={true} />
                    <span className="font-mono text-[11px]">{countdown}s</span>
                  </div>
                ) : captured ? (
                  <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-mono">
                    <svg className="w-3.5 h-3.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    Captured
                  </span>
                ) : (
                  <span className="text-[11px] text-zinc-500 font-mono">Ready</span>
                )}
              </div>
            </Card>
          );
        })}
      </div>

      {/* Enroll Action Button */}
      <Button
        variant="solid"
        size="lg"
        onClick={enroll}
        disabled={enrollmentUnavailable || capturedCount < 3 || enrolling}
        className="w-full mt-1"
      >
        {enrolling
          ? "Computing Voice Embeddings…"
          : `Enroll Voice Profile (${capturedCount}/3 samples)`}
      </Button>

      <ErrorBanner msg={enrollErr} />

      {/* Result feedback */}
      {result ? (
        <Card tone={done ? "green" : "neutral"} title="Embedding Cohesion Result">
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between font-mono">
              <span className="text-zinc-400">Audio Samples:</span>
              <span className="text-white">{result.samples}</span>
            </div>
            <div className="flex justify-between font-mono">
              <span className="text-zinc-400">Cohesion Score:</span>
              <span className="text-emerald-400 font-semibold">{result.cohesion.toFixed(4)}</span>
            </div>
            {done ? (
              <div className="mt-2 pt-2 border-t border-emerald-500/30 flex items-center gap-2 text-emerald-300 font-medium">
                <svg className="w-4 h-4 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
                <span>Voice Profile Verified & Activated</span>
              </div>
            ) : null}
          </div>
        </Card>
      ) : null}
    </div>
  );
}
