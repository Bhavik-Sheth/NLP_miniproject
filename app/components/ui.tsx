"use client";

import type { ReactNode } from "react";

export function VesperLogo({
  showWordmark = true,
  size = 20,
}: {
  showWordmark?: boolean;
  size?: number;
}) {
  return (
    <div className="inline-flex items-center gap-2 select-none">
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="currentColor"
        className="text-white shrink-0"
      >
        <g transform="rotate(-30 12 12)">
          <circle cx="7.3" cy="3.2" r="1.45" />
          <rect x="5.5" y="4.7" width="3.6" height="14.6" rx="1.8" />
          <rect x="14.9" y="4.7" width="3.6" height="14.6" rx="1.8" />
          <circle cx="16.7" cy="20.8" r="1.45" />
        </g>
      </svg>
      {showWordmark ? (
        <span className="text-[15px] font-semibold tracking-[-0.03em] text-white">
          Vesper<span className="font-normal text-zinc-400">.ai</span>
        </span>
      ) : null}
    </div>
  );
}

export function LiveBadge({
  state = "ok",
  label = "LIVE",
}: {
  state?: "ok" | "check" | "alert";
  label?: string;
}) {
  const dotClasses = {
    ok: "p-live-dot",
    check: "p-live-dot dot-amber",
    alert: "p-live-dot dot-red",
  };

  return (
    <span className="p-live-badge">
      <i className={dotClasses[state]} />
      <span>{label}</span>
    </span>
  );
}

export function WaveVisualizer({ active = false }: { active?: boolean }) {
  return (
    <span className={`wave-bars ${active ? "active" : ""}`}>
      <i />
      <i />
      <i />
      <i />
      <i />
    </span>
  );
}

export function Card({
  tone = "neutral",
  title,
  children,
  className = "",
  hoverable = false,
}: {
  tone?: "neutral" | "red" | "amber" | "green";
  title?: string;
  children: ReactNode;
  className?: string;
  hoverable?: boolean;
}) {
  const toneClasses = {
    neutral: "glass-panel",
    red: "glass-panel glass-panel-red",
    amber: "glass-panel glass-panel-amber",
    green: "glass-panel glass-panel-green",
  };

  return (
    <div
      className={`${toneClasses[tone]} ${
        hoverable ? "glass-panel-hoverable cursor-pointer" : ""
      } p-3.5 text-sm ${className}`}
    >
      {title ? (
        <div className="mb-2 flex items-center justify-between font-mono text-[10.5px] uppercase tracking-wider text-zinc-400">
          <span>{title}</span>
        </div>
      ) : null}
      {children}
    </div>
  );
}

export function ErrorBanner({ msg }: { msg: string | null }) {
  if (!msg) return null;
  return (
    <div className="glass-panel glass-panel-red p-3 text-sm text-red-200 whitespace-pre-wrap break-words flex items-start gap-2.5">
      <svg
        className="w-4 h-4 shrink-0 text-red-400 mt-0.5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
      <div className="flex-1 text-[13px] leading-relaxed">{msg}</div>
    </div>
  );
}

export function Chip({
  label,
  sub,
  dim,
  bad,
}: {
  label: string;
  sub?: string;
  dim?: boolean;
  bad?: boolean;
}) {
  return (
    <span
      className={`entity-pill ${
        bad ? "border-red-500/60 text-red-100" : ""
      } ${dim ? "opacity-60" : ""}`}
    >
      <span>{label}</span>
      {sub ? <small>{sub}</small> : null}
    </span>
  );
}

export function Button({
  variant = "ghost",
  children,
  onClick,
  disabled,
  className = "",
  size = "md",
  type = "button",
  id,
}: {
  id?: string;
  variant?: "solid" | "ghost";
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
  size?: "sm" | "md" | "lg";
  type?: "button" | "submit" | "reset";
}) {
  const sizeClasses = {
    sm: "h-8 px-3 text-xs",
    md: "h-9 px-4 text-xs font-medium",
    lg: "h-11 px-5 text-sm font-medium",
  };

  const variantClass =
    variant === "solid" ? "btn-solid-liquid" : "btn-ghost-liquid";

  return (
    <button
      id={id}
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`btn-base ${variantClass} ${sizeClasses[size]} disabled:opacity-40 disabled:pointer-events-none ${className}`}
    >
      {children}
    </button>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-xs text-zinc-400">
      <svg
        className="animate-spin h-3.5 w-3.5 text-zinc-400"
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
      <span>{label}</span>
    </div>
  );
}
