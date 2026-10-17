"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Icon, type IconName } from "./icons";
import { NAV_ITEMS } from "./nav";
import { useDash } from "./context";
import { useTheme } from "./theme";
import { Kbd } from "./primitives";

type Item = { id: string; group: string; label: string; icon: IconName; hint?: string; keywords?: string; run: () => void };

export default function CommandPalette() {
  const { paletteOpen, setPaletteOpen, projects, setProjectId, setSidebarCollapsed } = useDash();
  const { setPref } = useTheme();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (paletteOpen) {
      setQ("");
      setIdx(0);
      window.setTimeout(() => inputRef.current?.focus(), 10);
    }
  }, [paletteOpen]);

  const close = () => setPaletteOpen(false);
  const go = (href: string) => {
    close();
    router.push(href);
  };

  const items = useMemo<Item[]>(() => {
    const query = q.trim();
    const base: Item[] = [
      ...NAV_ITEMS.map((n) => ({ id: `nav-${n.id}`, group: "Go to", label: n.label, icon: n.icon, hint: n.keys, keywords: n.keywords, run: () => go(n.href) })),
      { id: "a-live", group: "Actions", label: "Start a live voice session", icon: "mic", keywords: "call talk", run: () => go("/app/live?start=1") },
      { id: "a-scen", group: "Actions", label: "Run the scenario suite", icon: "flask", keywords: "tests", run: () => go("/app/scenarios?run=1") },
      { id: "a-ingest", group: "Actions", label: "Upload a document to memory", icon: "upload", keywords: "ingest pdf", run: () => go("/app/documents") },
      { id: "a-light", group: "Theme", label: "Light theme", icon: "sun", run: () => (close(), setPref("light")) },
      { id: "a-dark", group: "Theme", label: "Dark theme", icon: "moon", run: () => (close(), setPref("dark")) },
      { id: "a-sys", group: "Theme", label: "Match system theme", icon: "monitor", run: () => (close(), setPref("system")) },
      { id: "a-sidebar", group: "Actions", label: "Toggle sidebar", icon: "sidebar", hint: "[", run: () => (close(), setSidebarCollapsed((v) => !v)) },
      { id: "a-tour", group: "Actions", label: "Take the dashboard tour", icon: "compass", run: () => (close(), window.dispatchEvent(new Event("vesper-dash-tour"))) },
      { id: "a-console", group: "Actions", label: "Open the phone field console", icon: "arrowUpRight", run: () => go("/app/console") },
      ...projects.map((p) => ({ id: `p-${p.id}`, group: "Switch project", label: p.name, icon: "building" as IconName, hint: p.code ?? p.id, run: () => (close(), setProjectId(p.id)) })),
    ];
    const needle = query.toLowerCase();
    const filtered = needle ? base.filter((i) => `${i.label} ${i.keywords ?? ""} ${i.group}`.toLowerCase().includes(needle)) : base;
    const ask: Item[] = query
      ? [
          { id: "ask", group: "Ask memory", label: `Ask: “${query}”`, icon: "sparkles", hint: "↵", run: () => go(`/app/ask?q=${encodeURIComponent(query)}`) },
          { id: "search", group: "Ask memory", label: `Inspect retrieval for “${query}”`, icon: "search", run: () => go(`/app/memory?q=${encodeURIComponent(query)}`) },
        ]
      : [];
    return [...ask, ...filtered];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, projects]);

  useEffect(() => setIdx(0), [q]);
  useEffect(() => {
    listRef.current?.querySelector(`[data-idx="${idx}"]`)?.scrollIntoView({ block: "nearest" });
  }, [idx]);

  if (!paletteOpen) return null;

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIdx((i) => Math.min(items.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIdx((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      items[idx]?.run();
    } else if (e.key === "Escape") close();
  };

  let lastGroup = "";
  return (
    <>
      <div className="dash-overlay" onClick={close} />
      <div className="dash-palette glass-strong overflow-hidden" role="dialog" aria-label="Command palette" onKeyDown={onKey}>
        <div className="flex items-center gap-3 border-b border-line px-4">
          <Icon name="search" size={16} className="text-ink-3" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search pages and actions, or ask the project memory…"
            className="h-12 flex-1 bg-transparent text-[14.5px] text-ink outline-none placeholder:text-ink-3"
          />
          <Kbd>esc</Kbd>
        </div>
        <div ref={listRef} className="max-h-[min(420px,60vh)] overflow-y-auto p-1.5">
          {items.length === 0 ? <p className="px-3 py-6 text-center text-[13px] text-ink-3">No matches</p> : null}
          {items.map((it, i) => {
            const header = it.group !== lastGroup ? it.group : null;
            lastGroup = it.group;
            return (
              <div key={it.id}>
                {header ? <p className="dash-eyebrow px-2.5 pb-1.5 pt-2.5">{header}</p> : null}
                <button
                  data-idx={i}
                  onMouseMove={() => setIdx(i)}
                  onClick={it.run}
                  className={`flex h-9 w-full items-center gap-3 rounded-lg px-2.5 text-left text-[13px] transition-colors ${
                    i === idx ? "bg-[color-mix(in_oklab,var(--text)_8%,transparent)] text-ink" : "text-ink-2"
                  }`}
                >
                  <Icon name={it.icon} size={15} className={i === idx ? "text-accent" : "text-ink-3"} />
                  <span className="flex-1 truncate">{it.label}</span>
                  {it.hint ? (
                    <span className="flex gap-1">
                      {it.hint.split(" ").map((k, j) => (
                        <Kbd key={j}>{k}</Kbd>
                      ))}
                    </span>
                  ) : null}
                </button>
              </div>
            );
          })}
        </div>
        <div className="flex items-center gap-4 border-t border-line px-4 py-2 text-[11px] text-ink-3">
          <span className="flex items-center gap-1"><Kbd>↑</Kbd><Kbd>↓</Kbd> navigate</span>
          <span className="flex items-center gap-1"><Kbd>↵</Kbd> open</span>
          <span className="ml-auto">Type a question to ask the project memory</span>
        </div>
      </div>
    </>
  );
}
