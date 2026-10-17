"use client";

import { useEffect, useRef } from "react";
import { useClerk } from "@clerk/nextjs";

/** A real sign-out URL. The static landing page cannot call Clerk's React hooks, so it links
 *  here; this route ends the session and returns the visitor to the public site. */
export default function SignOutPage() {
  const { signOut } = useClerk();
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    signOut({ redirectUrl: "/" }).catch(() => {
      window.location.href = "/";
    });
  }, [signOut]);

  return (
    <main className="grid min-h-screen place-items-center bg-black px-6 text-center text-white">
      <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-zinc-500">Vesper / Session</p>
        <h1 className="mt-3 text-xl font-semibold tracking-tight">Signing you out…</h1>
        <p className="mt-2 text-sm text-zinc-400">
          One moment. If nothing happens, <a className="underline hover:text-white" href="/">return to the home page</a>.
        </p>
      </div>
    </main>
  );
}
