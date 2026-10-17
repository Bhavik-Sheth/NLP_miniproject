"use client";

// MediaRecorder wrapper with a live input level (0..1) from an AnalyserNode.
import { useCallback, useEffect, useRef, useState } from "react";

export type RecorderState = "idle" | "requesting" | "recording" | "stopped" | "error";

export function useRecorder() {
  const [state, setState] = useState<RecorderState>("idle");
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const mr = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const ctx = useRef<AudioContext | null>(null);
  const raf = useRef<number | null>(null);
  const chunks = useRef<Blob[]>([]);
  const started = useRef(0);
  const resolveStop = useRef<((b: Blob | null) => void) | null>(null);

  const teardown = useCallback(() => {
    if (raf.current) cancelAnimationFrame(raf.current);
    raf.current = null;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    ctx.current?.close().catch(() => {});
    ctx.current = null;
    setLevel(0);
  }, []);

  useEffect(() => teardown, [teardown]);

  const start = useCallback(async () => {
    setError(null);
    if (typeof window === "undefined" || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("This browser can't record audio.");
      setState("error");
      return false;
    }
    setState("requesting");
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      stream.current = s;
      const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((m) => MediaRecorder.isTypeSupported?.(m));
      const rec = new MediaRecorder(s, mime ? { mimeType: mime } : undefined);
      chunks.current = [];
      rec.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      rec.onstop = () => {
        const blob = chunks.current.length ? new Blob(chunks.current, { type: rec.mimeType || "audio/webm" }) : null;
        teardown();
        setState("stopped");
        resolveStop.current?.(blob);
        resolveStop.current = null;
      };
      mr.current = rec;
      rec.start(250);

      const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ac = new AC();
      ctx.current = ac;
      const an = ac.createAnalyser();
      an.fftSize = 512;
      ac.createMediaStreamSource(s).connect(an);
      const buf = new Uint8Array(an.fftSize);
      started.current = performance.now();
      const tick = () => {
        an.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) {
          const v = (buf[i] - 128) / 128;
          sum += v * v;
        }
        const rms = Math.sqrt(sum / buf.length);
        setLevel((prev) => prev * 0.6 + Math.min(1, rms * 4) * 0.4);
        setElapsed((performance.now() - started.current) / 1000);
        raf.current = requestAnimationFrame(tick);
      };
      tick();
      setState("recording");
      return true;
    } catch (e) {
      teardown();
      const name = (e as DOMException).name;
      setError(name === "NotAllowedError" ? "Microphone permission was denied." : `Couldn't start the microphone (${(e as Error).message}).`);
      setState("error");
      return false;
    }
  }, [teardown]);

  const stop = useCallback((): Promise<Blob | null> => {
    const rec = mr.current;
    if (!rec || rec.state === "inactive") return Promise.resolve(null);
    return new Promise((resolve) => {
      resolveStop.current = resolve;
      rec.stop();
    });
  }, []);

  const reset = useCallback(() => {
    setState("idle");
    setElapsed(0);
    setError(null);
  }, []);

  return { state, level, elapsed, error, start, stop, reset };
}

export function fmtSeconds(s: number) {
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${r.toString().padStart(2, "0")}`;
}
