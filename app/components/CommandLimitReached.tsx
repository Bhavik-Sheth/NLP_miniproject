import DottedGlowBackground from "@/components/DottedGlowBackground";

export default function CommandLimitReached() {
  return (
    <section className="command-limit-card" role="status" aria-live="polite">
      <DottedGlowBackground />
      <div className="relative z-10 flex flex-col items-center px-5 py-8 text-center">
        <span className="command-limit-check">✓</span>
        <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.2em] text-sky-200/70">Free session complete</p>
        <h2 className="mt-2 text-2xl font-medium tracking-tight text-white">Thank you for trying Vesper.</h2>
        <p className="mt-2 max-w-xs text-sm leading-relaxed text-zinc-300">
          Your three complimentary voice or chat commands are complete. Your verified conversations remain available below.
        </p>
        <span className="mt-5 rounded-full border border-sky-300/20 bg-white/5 px-3 py-1.5 text-xs text-sky-100 animate-pulse">We’ll be glad to welcome you back.</span>
      </div>
    </section>
  );
}
