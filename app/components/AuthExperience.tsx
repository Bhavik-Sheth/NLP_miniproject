"use client";

import Link from "next/link";
import { SignIn, SignUp } from "@clerk/nextjs";
import AuthDitherField from "@/components/AuthDitherField";
import { VesperLogo } from "@/components/ui";

const appearance = { elements: { rootBox: "w-full", card: "w-full rounded-none border-0 bg-transparent shadow-none", headerTitle: "text-2xl font-semibold tracking-tight text-white", headerSubtitle: "text-sm leading-relaxed text-zinc-400", socialButtonsBlockButton: "border border-white/10 bg-white/[0.04] text-white hover:bg-white/[0.09]", dividerLine: "bg-white/10", dividerText: "text-zinc-500", formFieldLabel: "text-zinc-300", formFieldInput: "border-white/15 bg-black/35 text-white placeholder:text-zinc-600 focus:border-sky-300/60", formButtonPrimary: "bg-sky-200 text-slate-950 hover:bg-white", footerActionText: "text-zinc-500", footerActionLink: "text-sky-200 hover:text-white", identityPreviewText: "text-white" } };

export default function AuthExperience({ mode }: { mode: "sign-in" | "sign-up" }) {
  const isSignUp = mode === "sign-up";
  return <main className="auth-experience"><section className="auth-form-side"><div className="auth-form-inner"><Link href="/" aria-label="Vesper.ai home" className="inline-flex w-fit opacity-90 transition hover:opacity-100"><VesperLogo size={28} /></Link><p className="mt-10 max-w-sm text-sm leading-relaxed text-zinc-400">{isSignUp ? "Build a safer, voice-led record of site decisions." : "Welcome back. Pick up from the site memory you already verified."}</p><div className="mt-8 w-full max-w-md">{isSignUp ? <SignUp appearance={appearance} fallbackRedirectUrl="/app" /> : <SignIn appearance={appearance} fallbackRedirectUrl="/app" />}</div></div></section><section className="auth-art-side"><AuthDitherField /><div className="auth-art-copy"><p className="font-mono text-[10px] uppercase tracking-[0.24em] text-sky-100/70">Vesper / Site intelligence</p><h1>{isSignUp ? "A safer memory starts with one verified voice." : "Every site observation deserves a second look."}</h1><p>{isSignUp ? "Speak naturally. Vesper grounds every decision in the current drawing, permit and RFI record." : "Hover through the site grid. Vesper connects what you say to the evidence that matters."}</p><div className="mt-6 flex items-center gap-2 text-xs text-sky-100/85"><span className="p-live-dot" /> Grounded in drawings, RFIs and permits</div></div></section></main>;
}
