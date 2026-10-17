"use client";

import type { ReactNode } from "react";
import { OnboardingGate } from "@/components/onboarding/OnboardingGate";

// W4's onboarding guard. It never blocks in local auth mode (seeded P1 demo), when /api/me is
// absent or the backend is down, or when the user chose to explore the demo project.
export default function Gate({ children }: { children: ReactNode }) {
  return (
    <OnboardingGate
      fallback={
        <div className="grid min-h-dvh place-items-center">
          <div className="flex items-center gap-3 text-[13px] text-ink-3">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
            Loading workspace…
          </div>
        </div>
      }
    >
      {children}
    </OnboardingGate>
  );
}
