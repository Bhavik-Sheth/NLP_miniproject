"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useAuth, useUser } from "@clerk/nextjs";
import { api, type Health } from "@/lib/api";
import { apiV2, isMissing, setDashboardTokenGetter, type Me, type ProjectRef, type V2Status } from "@/lib/api-v2";
import { setDemoMode } from "@/lib/demo";
import { STATIC_DEMO } from "@/lib/static-demo";

/** The seeded demo project every signed-in user can read (PLAN §3). Used when /api/me is not live. */
export const DEMO_PROJECT: ProjectRef = {
  id: "P1",
  name: "Pithoragarh District Hospital & Staff Quarters",
  code: "P1",
  type: "Hospital",
  city: "Pithoragarh, Uttarakhand",
  status: "Active",
  role: "viewer",
};

type Ctx = {
  me: Me | null;
  meMissing: boolean;
  projects: ProjectRef[];
  project: ProjectRef;
  setProjectId: (id: string) => void;
  health: Health | null;
  healthError: boolean;
  v2: V2Status | null;
  /** memory router loaded on the backend */
  memoryLive: boolean;
  refreshStatus: () => void;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (v: boolean | ((v: boolean) => boolean)) => void;
  paletteOpen: boolean;
  setPaletteOpen: (v: boolean) => void;
};

const DashCtx = createContext<Ctx | null>(null);
const PROJECT_KEY = "vesper-project";
const SIDEBAR_KEY = "vesper-sidebar-collapsed";

export function DashboardProvider({ children }: { children: ReactNode }) {
  const { getToken, userId } = useAuth();
  const { user } = useUser();

  // Set synchronously during render: child effects (their first fetches) run before ours.
  // The public static build answers v1 calls (health, observations, scenarios) from recorded data.
  setDemoMode(STATIC_DEMO);
  const tokenRef = useRef(getToken);
  tokenRef.current = getToken;
  const installed = useRef(false);
  if (!installed.current) {
    setDashboardTokenGetter(() => tokenRef.current());
    installed.current = true;
  }

  const [me, setMe] = useState<Me | null>(null);
  const [meMissing, setMeMissing] = useState(false);
  const [projectId, setProjectIdState] = useState<string>("P1");
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [v2, setV2] = useState<V2Status | null>(null);
  const [sidebarCollapsed, setSidebarCollapsedState] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    try {
      const p = localStorage.getItem(PROJECT_KEY);
      if (p) setProjectIdState(p);
      setSidebarCollapsedState(localStorage.getItem(SIDEBAR_KEY) === "1");
    } catch {
      /* private mode */
    }
  }, []);

  useEffect(() => {
    apiV2
      .me()
      .then((m) => {
        setMe(m);
        setMeMissing(false);
      })
      .catch((e) => setMeMissing(isMissing(e) || true));
  }, [userId]);

  // Same per-user seeding the phone console does, once per browser session.
  const email = user?.primaryEmailAddress?.emailAddress;
  useEffect(() => {
    if (!email) return;
    try {
      if (sessionStorage.getItem("vesper-bootstrapped") === email) return;
      sessionStorage.setItem("vesper-bootstrapped", email);
    } catch {
      /* ignore */
    }
    api.bootstrapDemo(email).catch(() => undefined);
  }, [email]);

  const refreshStatus = useCallback(() => {
    api
      .health()
      .then((h) => {
        setHealth(h);
        setHealthError(false);
      })
      .catch(() => setHealthError(true));
    apiV2.v2Status().then(setV2).catch(() => setV2(null));
  }, []);

  useEffect(() => {
    refreshStatus();
    const t = window.setInterval(refreshStatus, 30_000);
    return () => window.clearInterval(t);
  }, [refreshStatus]);

  const projects = useMemo(() => {
    const list = me?.projects?.length ? [...me.projects] : [];
    if (!list.some((p) => p.id === "P1")) list.push(DEMO_PROJECT);
    return list;
  }, [me]);
  const project = projects.find((p) => p.id === projectId) ?? projects[0] ?? DEMO_PROJECT;

  const setProjectId = useCallback((id: string) => {
    setProjectIdState(id);
    try {
      localStorage.setItem(PROJECT_KEY, id);
    } catch {
      /* ignore */
    }
  }, []);

  const setSidebarCollapsed = useCallback((v: boolean | ((v: boolean) => boolean)) => {
    setSidebarCollapsedState((cur) => {
      const next = typeof v === "function" ? v(cur) : v;
      try {
        localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const memoryLive = v2?.routers?.["routes.memory"] === "ok";

  return (
    <DashCtx.Provider
      value={{
        me,
        meMissing,
        projects,
        project,
        setProjectId,
        health,
        healthError,
        v2,
        memoryLive,
        refreshStatus,
        sidebarCollapsed,
        setSidebarCollapsed,
        paletteOpen,
        setPaletteOpen,
      }}
    >
      {children}
    </DashCtx.Provider>
  );
}

export function useDash(): Ctx {
  const c = useContext(DashCtx);
  if (!c) throw new Error("useDash outside DashboardProvider");
  return c;
}
