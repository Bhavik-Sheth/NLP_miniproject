"use client";

import { useEffect, useRef } from "react";

export default function AuthDitherField() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const pointerRef = useRef({ x: -10_000, y: -10_000, active: false });

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    let frame = 0;
    let width = 0;
    let height = 0;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => {
      const bounds = canvas.getBoundingClientRect();
      width = bounds.width; height = bounds.height;
      canvas.width = Math.floor(width * ratio); canvas.height = Math.floor(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    };
    const observer = new ResizeObserver(resize); observer.observe(canvas); resize();
    const paint = (time: number) => {
      context.clearRect(0, 0, width, height); context.fillStyle = "#050709"; context.fillRect(0, 0, width, height);
      const pointer = pointerRef.current; const unit = Math.max(5, Math.min(width, height) / 75); const drift = time * 0.00018;
      for (let x = unit; x < width; x += unit) for (let y = unit; y < height; y += unit) {
        const nx = x / width - 0.5; const ny = y / height - 0.5;
        const arch = Math.sin(nx * 11 + ny * 4) + Math.cos(ny * 15 - nx * 2);
        const tower = Math.max(0, 1 - Math.abs(nx * 1.45)) * (0.72 - ny);
        const noise = Math.sin(x * 0.14 + y * 0.11 + drift * 4) * 0.22;
        const hover = pointer.active ? Math.max(0, 1 - Math.hypot(x - pointer.x, y - pointer.y) / 170) : 0;
        const level = tower + arch * 0.16 + noise + hover * 0.75;
        if (level > 0.27) {
          const alpha = Math.min(0.9, 0.15 + level * 0.35);
          context.fillStyle = hover > 0.1 ? `rgba(125, 211, 252, ${alpha})` : `rgba(241, 245, 249, ${alpha})`;
          const size = Math.max(1.1, unit * (0.25 + Math.min(0.65, level * 0.3)));
          context.fillRect(x - size / 2, y - size / 2, size, size);
        }
      }
      frame = requestAnimationFrame(paint);
    };
    frame = requestAnimationFrame(paint);
    return () => { observer.disconnect(); cancelAnimationFrame(frame); };
  }, []);

  return <canvas ref={canvasRef} className="auth-dither-canvas" onPointerMove={(event) => { const rect = event.currentTarget.getBoundingClientRect(); pointerRef.current = { x: event.clientX - rect.left, y: event.clientY - rect.top, active: true }; }} onPointerLeave={() => { pointerRef.current.active = false; }} aria-hidden="true" />;
}
