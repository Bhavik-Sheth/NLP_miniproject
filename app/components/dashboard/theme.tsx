"use client";

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useState, type ReactNode } from "react";
import { Icon } from "./icons";

export type ThemePref = "light" | "dark" | "system";
export type Resolved = "light" | "dark";

const KEY = "vesper-theme";

type Ctx = { pref: ThemePref; resolved: Resolved; setPref: (p: ThemePref) => void; toggle: () => void };
const ThemeCtx = createContext<Ctx | null>(null);

const systemTheme = (): Resolved =>
  typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";

function apply(pref: ThemePref): Resolved {
  const resolved = pref === "system" ? systemTheme() : pref;
  const root = document.documentElement;
  root.setAttribute("data-theme", resolved);
  root.setAttribute("data-theme-pref", pref);
  return resolved;
}

function readPref(): ThemePref {
  try {
    const p = localStorage.getItem(KEY);
    return p === "light" || p === "dark" ? p : "system";
  } catch {
    return "system";
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<ThemePref>("system");
  const [resolved, setResolved] = useState<Resolved>("dark");

  // The inline script in app/layout.tsx already set data-theme before paint. Re-apply here:
  // React's dev Strict Mode remount strips attributes it doesn't manage from <html>.
  useLayoutEffect(() => {
    const p = readPref();
    setPrefState(p);
    setResolved(apply(p));
  }, []);

  useEffect(() => {
    if (pref !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const on = () => setResolved(apply("system"));
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [pref]);

  const setPref = useCallback((p: ThemePref) => {
    try {
      localStorage.setItem(KEY, p);
    } catch {
      /* private mode */
    }
    const run = () => {
      setPrefState(p);
      setResolved(apply(p));
    };
    const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (doc.startViewTransition && !reduce) doc.startViewTransition(run);
    else run();
  }, []);

  const toggle = useCallback(() => setPref(resolved === "dark" ? "light" : "dark"), [resolved, setPref]);

  return <ThemeCtx.Provider value={{ pref, resolved, setPref, toggle }}>{children}</ThemeCtx.Provider>;
}

export function useTheme(): Ctx {
  const c = useContext(ThemeCtx);
  if (!c) throw new Error("useTheme outside ThemeProvider");
  return c;
}

export function ThemeToggle() {
  const { resolved, toggle, pref } = useTheme();
  return (
    <button
      className="dash-btn dash-btn-ghost dash-btn-icon"
      onClick={toggle}
      aria-label={`Switch to ${resolved === "dark" ? "light" : "dark"} theme`}
      title={`Theme: ${pref}${pref === "system" ? ` (${resolved})` : ""} · ⇧⌘L`}
      suppressHydrationWarning
    >
      <span className="relative grid h-4 w-4 place-items-center">
        <Icon
          name="sun"
          size={16}
          className="absolute transition-all duration-500"
          style={{ opacity: resolved === "light" ? 1 : 0, transform: resolved === "light" ? "rotate(0) scale(1)" : "rotate(-90deg) scale(.6)" }}
        />
        <Icon
          name="moon"
          size={15}
          className="absolute transition-all duration-500"
          style={{ opacity: resolved === "dark" ? 1 : 0, transform: resolved === "dark" ? "rotate(0) scale(1)" : "rotate(90deg) scale(.6)" }}
        />
      </span>
    </button>
  );
}
