"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";
import { DashboardProvider, useDash } from "./context";
import { ThemeProvider, ThemeToggle, useTheme } from "./theme";
import { Icon, VesperMark } from "./icons";
import { NAV, NAV_ITEMS, activeItem } from "./nav";
import { Kbd } from "./primitives";
import CommandPalette from "./CommandPalette";
import DashTour from "./DashTour";

export default function Shell({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <DashboardProvider>
        <ShellInner>{children}</ShellInner>
      </DashboardProvider>
    </ThemeProvider>
  );
}

function Background() {
  return (
    <div className="dash-bg" aria-hidden="true">
      <div className="dash-bg-blob a" />
      <div className="dash-bg-blob b" />
      <div className="dash-bg-blob c" />
      <div className="dash-bg-dots" />
    </div>
  );
}

function isTyping(el: EventTarget | null) {
  const t = el as HTMLElement | null;
  return !!t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
}

function ShellInner({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { sidebarCollapsed, setSidebarCollapsed, setPaletteOpen, paletteOpen } = useDash();
  const { toggle } = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);
  const gPending = useRef<number | null>(null);

  useEffect(() => setMobileOpen(false), [pathname]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(!paletteOpen);
        return;
      }
      if (mod && e.shiftKey && e.key.toLowerCase() === "l") {
        e.preventDefault();
        toggle();
        return;
      }
      if (mod || e.altKey || isTyping(e.target) || paletteOpen) return;
      if (e.key === "[") {
        setSidebarCollapsed((v) => !v);
        return;
      }
      if (gPending.current) {
        window.clearTimeout(gPending.current);
        gPending.current = null;
        const hit = NAV_ITEMS.find((n) => n.keys.split(" ")[1]?.toLowerCase() === e.key.toLowerCase());
        if (hit) {
          e.preventDefault();
          router.push(hit.href);
        }
        return;
      }
      if (e.key.toLowerCase() === "g") gPending.current = window.setTimeout(() => (gPending.current = null), 900);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paletteOpen, setPaletteOpen, setSidebarCollapsed, toggle, router]);

  return (
    <div className="dash-root">
      <Background />
      <aside className="dash-sidebar" data-collapsed={sidebarCollapsed} suppressHydrationWarning>
        <SidebarContent collapsed={sidebarCollapsed} />
      </aside>

      <div className="dash-main">
        <Topbar onMenu={() => setMobileOpen(true)} />
        <main key={pathname} className="dash-page mx-auto w-full max-w-[1480px] flex-1 px-4 pb-16 pt-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>

      {mobileOpen ? (
        <>
          <div className="dash-overlay" onClick={() => setMobileOpen(false)} />
          <aside className="dash-sheet dash-sheet-left glass-strong overflow-hidden" role="dialog" aria-label="Navigation">
            <SidebarContent collapsed={false} onNavigate={() => setMobileOpen(false)} />
          </aside>
        </>
      ) : null}

      <CommandPalette />
      <DashTour />
    </div>
  );
}

function ProjectSwitcher({ collapsed }: { collapsed: boolean }) {
  const { projects, project, setProjectId } = useDash();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const on = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    window.addEventListener("mousedown", on);
    return () => window.removeEventListener("mousedown", on);
  }, [open]);
  const initials = (project.code ?? project.name).slice(0, 2).toUpperCase();
  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className={`flex w-full items-center gap-2.5 rounded-lg border border-transparent p-1.5 text-left transition hover:border-line hover:bg-[color-mix(in_oklab,var(--text)_4%,transparent)] ${collapsed ? "justify-center" : ""}`}
        title={project.name}
      >
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-[11px] font-semibold text-white" style={{ background: "linear-gradient(135deg, var(--accent), var(--accent-2))" }}>
          {initials}
        </span>
        <span className="dash-hide-collapsed min-w-0 flex-1">
          <span className="block truncate text-[12.5px] font-medium text-ink">{project.name}</span>
          <span className="block truncate text-[11px] text-ink-3">{[project.code ?? project.id, project.city].filter(Boolean).join(" · ")}</span>
        </span>
        <Icon name="chevronUpDown" size={13} className="dash-hide-collapsed text-ink-3" />
      </button>
      {open ? (
        <div className="glass-strong absolute left-0 top-full z-50 mt-1 w-[260px] p-1.5" style={{ animation: "dash-fade .15s ease" }}>
          <p className="dash-eyebrow px-2 pb-1 pt-1.5">Projects</p>
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => {
                setProjectId(p.id);
                setOpen(false);
              }}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12.5px] text-ink-2 hover:bg-[color-mix(in_oklab,var(--text)_6%,transparent)] hover:text-ink"
            >
              <span className="flex-1 truncate">{p.name}</span>
              <span className="font-mono text-[10.5px] text-ink-3">{p.code ?? p.id}</span>
              {p.id === project.id ? <Icon name="check" size={13} className="text-accent" /> : null}
            </button>
          ))}
          <div className="my-1 h-px bg-line" />
          <Link href="/onboarding" className="flex items-center gap-2 rounded-md px-2 py-1.5 text-[12.5px] text-ink-2 hover:bg-[color-mix(in_oklab,var(--text)_6%,transparent)] hover:text-ink">
            <Icon name="plus" size={13} /> New project
          </Link>
        </div>
      ) : null}
    </div>
  );
}

function SidebarContent({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const current = activeItem(pathname);
  const { setSidebarCollapsed } = useDash();
  const { resolved } = useTheme();
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className={`flex h-[52px] shrink-0 items-center gap-2 border-b border-line px-3 ${collapsed ? "justify-center" : ""}`}>
        <Link href="/app" className="flex items-center gap-2 text-ink" onClick={onNavigate}>
          <VesperMark size={18} />
          <span className="dash-hide-collapsed text-[14.5px] font-semibold tracking-[-0.03em]">
            Vesper<span className="font-normal text-ink-3">.ai</span>
          </span>
        </Link>
        {!collapsed ? (
          <div className="dash-hide-collapsed ml-auto flex min-w-0 max-w-[128px] items-center overflow-hidden">
            <OrganizationSwitcher
              hidePersonal={false}
              afterSelectOrganizationUrl="/app"
              appearance={{
                elements: {
                  rootBox: "max-w-full",
                  organizationSwitcherTrigger: `max-w-full rounded-md px-1.5 py-1 text-[11.5px] ${resolved === "dark" ? "text-zinc-300 hover:bg-white/5" : "text-zinc-600 hover:bg-black/5"}`,
                  organizationPreviewAvatarBox: "h-4 w-4",
                  organizationPreviewTextContainer: "truncate",
                },
              }}
            />
          </div>
        ) : null}
      </div>

      <div className="shrink-0 px-2.5 pt-3">
        <ProjectSwitcher collapsed={collapsed} />
      </div>

      <nav id="tour-dash-nav" className="min-h-0 flex-1 overflow-y-auto px-2.5 py-3" aria-label="Dashboard">
        {NAV.map((g) => (
          <div key={g.label} className="mb-4">
            {!collapsed ? <p className="dash-eyebrow mb-1.5 px-2.5">{g.label}</p> : <div className="mx-auto mb-2 h-px w-6 bg-line" />}
            <ul className="space-y-0.5 pl-2.5" style={collapsed ? { paddingLeft: 0 } : undefined}>
              {g.items.map((n) => (
                <li key={n.id}>
                  <Link
                    href={n.href}
                    className="dash-nav-item"
                    aria-current={current.id === n.id ? "page" : undefined}
                    title={collapsed ? `${n.label} (${n.keys})` : undefined}
                    onClick={onNavigate}
                  >
                    <Icon name={n.icon} size={15} className="shrink-0" />
                    <span className="dash-hide-collapsed truncate">{n.label}</span>
                    {!collapsed ? (
                      <span className="dash-shortcut flex gap-0.5">
                        {n.keys.split(" ").map((k) => (
                          <Kbd key={k}>{k}</Kbd>
                        ))}
                      </span>
                    ) : null}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="shrink-0 space-y-0.5 border-t border-line p-2.5">
        <Link href="/app/console" className="dash-nav-item" title="Phone field console" onClick={onNavigate}>
          <Icon name="arrowUpRight" size={15} />
          <span className="dash-hide-collapsed">Field console</span>
        </Link>
        <button className="dash-nav-item w-full" onClick={() => window.dispatchEvent(new Event("vesper-dash-tour"))} title="Take the tour">
          <Icon name="compass" size={15} />
          <span className="dash-hide-collapsed">Take the tour</span>
        </button>
        {!onNavigate ? (
          <button className="dash-nav-item w-full" onClick={() => setSidebarCollapsed((v) => !v)} title="Collapse sidebar ( [ )">
            <Icon name="sidebar" size={15} />
            <span className="dash-hide-collapsed">Collapse</span>
            {!collapsed ? (
              <span className="dash-shortcut">
                <Kbd>[</Kbd>
              </span>
            ) : null}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function StatusPills() {
  const { health, healthError, memoryLive, v2, refreshStatus } = useDash();
  const backend = healthError ? "danger" : health ? (health.db ? "ok" : "warn") : undefined;
  const voice = health ? (health.rime ? (health.voiceid ? "ok" : "warn") : "danger") : undefined;
  const memory = memoryLive ? "ok" : v2 ? "warn" : undefined;
  const pill = (label: string, tone: string | undefined, title: string) => (
    <button className="dash-pill hover:text-ink" title={title} onClick={refreshStatus}>
      <span className="dash-dot" data-tone={tone} data-pulse={tone === "ok"} />
      {label}
    </button>
  );
  return (
    <div id="tour-dash-status" className="hidden items-center gap-1.5 md:flex">
      {pill("Backend", backend, healthError ? "Backend unreachable" : health ? `db ${health.db ? "ok" : "down"} · llm ${health.llm}` : "Checking…")}
      {pill("Voice", voice, health ? `Rime TTS ${health.rime ? "on" : "off"} · voice ID ${health.voiceid ? "on" : "off"}` : "Checking…")}
      <span className="hidden xl:inline-flex">{pill("Memory", memory, memoryLive ? "Memory router loaded" : v2 ? `Memory router: ${v2.routers?.["routes.memory"] ?? "not loaded"}` : "v2 status unavailable")}</span>
    </div>
  );
}

function Topbar({ onMenu }: { onMenu: () => void }) {
  const pathname = usePathname();
  const current = activeItem(pathname);
  const { project, setPaletteOpen, setSidebarCollapsed } = useDash();
  const group = NAV.find((g) => g.items.includes(current));
  return (
    <header className="dash-topbar">
      <button className="dash-btn dash-btn-ghost dash-btn-icon lg:hidden" onClick={onMenu} aria-label="Open navigation">
        <Icon name="menu" size={16} />
      </button>
      <button className="dash-btn dash-btn-ghost dash-btn-icon hidden lg:inline-flex" onClick={() => setSidebarCollapsed((v) => !v)} aria-label="Toggle sidebar">
        <Icon name="sidebar" size={15} />
      </button>
      <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-[13px]">
        <span className="hidden max-w-[220px] truncate text-ink-3 sm:inline">{project.name}</span>
        <Icon name="chevronRight" size={12} className="hidden text-ink-3 sm:inline" />
        {group && current.id !== "overview" ? (
          <>
            <span className="hidden text-ink-3 md:inline">{group.label}</span>
            <Icon name="chevronRight" size={12} className="hidden text-ink-3 md:inline" />
          </>
        ) : null}
        <span className="truncate font-medium text-ink">{current.label}</span>
      </nav>

      <div className="ml-auto flex items-center gap-2">
        <button
          id="tour-dash-search"
          onClick={() => setPaletteOpen(true)}
          className="glass flex h-8 items-center gap-2 rounded-lg px-2.5 text-[12.5px] text-ink-3 transition hover:text-ink sm:w-64"
          style={{ borderRadius: 9, boxShadow: "inset 0 1px 0 var(--glass-highlight)" }}
          aria-label="Open command palette"
        >
          <Icon name="search" size={14} />
          <span className="hidden flex-1 text-left sm:inline">Search or ask memory…</span>
          <span className="hidden gap-0.5 sm:flex">
            <Kbd>⌘</Kbd>
            <Kbd>K</Kbd>
          </span>
        </button>
        <StatusPills />
        <ThemeToggle />
        <div className="grid h-8 w-8 place-items-center">
          <UserButton appearance={{ elements: { avatarBox: "h-7 w-7" } }} />
        </div>
      </div>
    </header>
  );
}
