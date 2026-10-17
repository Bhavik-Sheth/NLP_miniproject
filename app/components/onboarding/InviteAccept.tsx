"use client";

// /onboarding/invite?token= → POST /api/invites/accept → /app/projects/{projectId}
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { tenancyApi, type TenancyError } from "@/lib/api-tenancy";
import { setOnboardingCookie } from "./OnboardingGate";
import { Callout, OIcon, OnboardingShell, Spin, useTenancyAuth } from "./primitives";

export default function InviteAccept() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token");
  const { isLoaded, isSignedIn } = useTenancyAuth();
  const [state, setState] = useState<"idle" | "working" | "done" | "error">("idle");
  const [msg, setMsg] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (!isLoaded || !isSignedIn || !token || started.current) return;
    started.current = true;
    setState("working");
    tenancyApi
      .acceptInvite(token)
      .then((r) => {
        setState("done");
        setOnboardingCookie("done");
        setMsg(`Joined as ${r.role}.`);
        setTimeout(() => router.replace(`/app/projects/${encodeURIComponent(r.projectId)}`), 900);
      })
      .catch((e: TenancyError) => {
        setState("error");
        setMsg(e.status === 404 ? "This invite was not found or has already been used." : e.message);
      });
  }, [isLoaded, isSignedIn, token, router]);

  return (
    <OnboardingShell>
      <section className="grid min-h-[70dvh] place-items-center py-10">
        <div className="vo-glass vo-enter w-full max-w-md p-7 text-center">
          <span className="mx-auto grid h-12 w-12 place-items-center rounded-full" style={{ background: "var(--vo-surface-2)", color: state === "error" ? "var(--vo-danger)" : "var(--vo-accent)" }}>
            {state === "working" ? <Spin size={20} /> : <OIcon name={state === "done" ? "check" : state === "error" ? "alert" : "building"} size={20} />}
          </span>
          <h1 className="mt-5 text-[22px] font-semibold tracking-[-0.02em]">
            {!token ? "Invite link incomplete" : state === "done" ? "You're in" : state === "error" ? "Couldn't accept invite" : "Joining project…"}
          </h1>
          <p className="vo-muted mt-2 text-[14px]">
            {!token ? "The link is missing its token. Open the link from the invite email again." : msg ?? "Linking this invite to your account."}
          </p>
          {state === "error" ? (
            <div className="mt-5 text-left">
              <Callout tone="danger">Check that you&apos;re signed in with the email address the invite was sent to.</Callout>
            </div>
          ) : null}
          {state === "error" || !token ? (
            <Link href="/app" className="vo-btn vo-btn-ghost mt-6">
              Go to dashboard
            </Link>
          ) : null}
        </div>
      </section>
    </OnboardingShell>
  );
}
