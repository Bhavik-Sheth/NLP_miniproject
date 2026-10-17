"use client";

// Client-side onboarding guard for the dashboard (W3 wraps /app with it).
//   <OnboardingGate>{dashboard}</OnboardingGate>
// Calls GET /api/me; if the org or first project is missing it routes to /onboarding(/project).
// Never blocks when the tenancy API is absent (404 / backend down), in local auth mode (the seeded
// P1 demo project), or when the user chose "explore the demo project" (localStorage flag).
// It also writes the `vesper_onb` cookie ("pending" | "done") that proxy.ts uses to redirect
// before paint on the next visit.
import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { tenancyApi, type Me, setTenancyActiveOrg, setTenancyTokenGetter } from "@/lib/api-tenancy";

export const ONB_COOKIE = "vesper_onb";
export const ONB_SKIP_KEY = "vesper-onboarding-skip";

export function setOnboardingCookie(state: "pending" | "done") {
  document.cookie = `${ONB_COOKIE}=${state}; path=/; max-age=${60 * 60 * 24 * 30}; samesite=lax`;
}

export function skipOnboarding() {
  try {
    localStorage.setItem(ONB_SKIP_KEY, "1");
  } catch {
    /* ignore */
  }
  setOnboardingCookie("done");
}

export function onboardingTarget(me: Me): string | null {
  if (me.authMode === "local") return null;
  if (!me.onboarding.orgDone) return "/onboarding";
  if (!me.onboarding.projectDone) return "/onboarding/project";
  return null;
}

export function OnboardingGate({
  children,
  fallback = null,
  onMe,
}: {
  children: ReactNode;
  /** rendered while /api/me is in flight (default: nothing, to avoid a dashboard flash) */
  fallback?: ReactNode;
  onMe?: (me: Me | null) => void;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { getToken, orgId, isLoaded, isSignedIn } = useAuth();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!isLoaded) return;
    let alive = true;
    const allow = () => alive && setReady(true);

    let skipped = false;
    try {
      skipped = localStorage.getItem(ONB_SKIP_KEY) === "1";
    } catch {
      /* ignore */
    }
    if (!isSignedIn || skipped || pathname?.startsWith("/onboarding")) {
      allow();
      return;
    }

    setTenancyTokenGetter(() => getToken());
    setTenancyActiveOrg(orgId ?? null);
    const timeout = setTimeout(allow, 4000); // never hold the dashboard hostage
    tenancyApi
      .me()
      .then((me) => {
        if (!alive) return;
        onMe?.(me);
        const target = onboardingTarget(me);
        setOnboardingCookie(target ? "pending" : "done");
        if (target) router.replace(target);
        else allow();
      })
      .catch(() => {
        onMe?.(null);
        allow();
      })
      .finally(() => clearTimeout(timeout));
    return () => {
      alive = false;
      clearTimeout(timeout);
    };
  }, [isLoaded, isSignedIn, orgId, getToken, router, pathname, onMe]);

  return <>{ready ? children : fallback}</>;
}

export default OnboardingGate;
