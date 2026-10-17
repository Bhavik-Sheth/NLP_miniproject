"use client";

import "./onboarding.css";
import Link from "next/link";
import { useEffect, type ReactNode, type SVGProps } from "react";
import { useAuth } from "@clerk/nextjs";
import { VesperLogo } from "@/components/ui";
import { ThemeProvider, ThemeToggle } from "@/components/dashboard/theme";
import { setTenancyActiveOrg, setTenancyTokenGetter, setTenancyUser } from "@/lib/api-tenancy";

// ---------- icons (1.6px stroke, 24 grid) ----------
const paths: Record<string, ReactNode> = {
  mic: (<><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></>),
  stop: <rect x="7" y="7" width="10" height="10" rx="2" />,
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  arrowRight: <path d="M5 12h14m-5-5 5 5-5 5" />,
  arrowLeft: <path d="M19 12H5m5-5-5 5 5 5" />,
  plus: <path d="M12 5v14M5 12h14" />,
  x: <path d="M6 6l12 12M18 6 6 18" />,
  upload: <path d="M12 15V4m-4.5 4.5L12 4l4.5 4.5M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3" />,
  file: (<><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></>),
  text: <path d="M4 6h16M4 12h16M4 18h10" />,
  wave: <path d="M3 12h2m3-5v10m4-13v16m4-11v6m4-3h1" />,
  pin: (<><path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" /><circle cx="12" cy="9.5" r="2.5" /></>),
  info: (<><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>),
  alert: (<><path d="M10.3 3.9 2.4 17.5A2 2 0 0 0 4.1 20.5h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></>),
  building: (<><path d="M4 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16M16 9h2a2 2 0 0 1 2 2v10M3 21h18" /><path d="M8 7h4M8 11h4M8 15h4" /></>),
  sparkle: <path d="M12 3v4m0 10v4M3 12h4m10 0h4M6.3 6.3l2.5 2.5m6.4 6.4 2.5 2.5m0-11.4-2.5 2.5m-6.4 6.4-2.5 2.5" />,
  brain: (<><path d="M9 4a3 3 0 0 0-3 3v.2A3 3 0 0 0 4 10a3 3 0 0 0 1 2.2A3 3 0 0 0 6 17a3 3 0 0 0 3 3V4z" /><path d="M15 4a3 3 0 0 1 3 3v.2A3 3 0 0 1 20 10a3 3 0 0 1-1 2.2A3 3 0 0 1 18 17a3 3 0 0 1-3 3V4z" /></>),
  trash: <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" />,
  locate: (<><circle cx="12" cy="12" r="3" /><path d="M12 2v3m0 14v3M2 12h3m14 0h3" /><circle cx="12" cy="12" r="7" /></>),
  refresh: <path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" />,
};

export function OIcon({ name, size = 16, ...rest }: { name: keyof typeof paths | string; size?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden {...rest}>
      {paths[name] ?? null}
    </svg>
  );
}

export function Spin({ size = 14 }: { size?: number }) {
  return (
    <svg className="vo-spin" width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity=".2" strokeWidth="2.5" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

// ---------- auth wiring ----------

/** Registers Clerk's token getter + active org with the tenancy client (and lib/api.ts). */
export function useTenancyAuth() {
  const { getToken, orgId, isLoaded, isSignedIn, userId } = useAuth();
  useEffect(() => {
    setTenancyTokenGetter(() => getToken());
    return () => setTenancyTokenGetter(null);
  }, [getToken]);
  useEffect(() => {
    setTenancyActiveOrg(orgId ?? null);
  }, [orgId]);
  useEffect(() => {
    setTenancyUser(userId ?? null);
  }, [userId]);
  return { orgId: orgId ?? null, isLoaded, isSignedIn, userId };
}

// ---------- layout ----------

export function OnboardingShell({ children, right, wide = false }: { children: ReactNode; right?: ReactNode; wide?: boolean }) {
  return (
    <ThemeProvider>
      <div className="vo vs-theme vo-page flex min-h-dvh flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 px-4 sm:px-6" style={{ background: "color-mix(in srgb, var(--vo-bg) 72%, transparent)", backdropFilter: "blur(14px)", WebkitBackdropFilter: "blur(14px)" }}>
          <Link href="/" aria-label="Vesper home" className="opacity-90 transition hover:opacity-100 [&_svg]:!text-[var(--vo-text)] [&_span]:!text-[var(--vo-text)]">
            <VesperLogo size={20} />
          </Link>
          <div className="flex items-center gap-2">
            {right}
            <ThemeToggle />
          </div>
        </header>
        <main className={`mx-auto w-full flex-1 px-4 pb-16 sm:px-6 ${wide ? "max-w-6xl" : "max-w-2xl"}`}>{children}</main>
      </div>
    </ThemeProvider>
  );
}

export function VoiceBadge({ reason }: { reason: string }) {
  return (
    <span className="vo-voice-badge" tabIndex={0} role="note" aria-label={`Used by voice. ${reason}`}>
      <OIcon name="wave" size={11} />
      used by voice
      <span className="vo-tip" role="tooltip">{reason}</span>
    </span>
  );
}

export function Callout({ tone = "info", title, children, icon }: { tone?: "info" | "warn" | "danger" | "ok"; title?: ReactNode; children?: ReactNode; icon?: string }) {
  const color = tone === "warn" ? "var(--vo-warn)" : tone === "danger" ? "var(--vo-danger)" : tone === "ok" ? "var(--vo-ok)" : "var(--vo-accent)";
  return (
    <div className="vo-callout vo-fade" data-tone={tone} role={tone === "danger" ? "alert" : "status"}>
      <OIcon name={icon ?? (tone === "ok" ? "check" : tone === "info" ? "info" : "alert")} size={16} style={{ color, flex: "none", marginTop: 2 }} />
      <div className="min-w-0">
        {title ? <strong className="block">{title}</strong> : null}
        {children ? <div className={title ? "mt-0.5" : ""}>{children}</div> : null}
      </div>
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="vo-kbd">{children}</kbd>;
}
