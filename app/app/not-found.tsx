/* Custom 404 for the Next routes; the static Cloudflare build serves public/404.html.
   Generated from that file. Class names carry a g404- prefix because the dashboard
   globals define .glass and .grain, which would otherwise repaint these layers. */
export default function NotFound() {
  return (
    <div className="vs404">
      <style dangerouslySetInnerHTML={{ __html: `
  .vs404 {
    --bg: #000000;
    --text: #ffffff;
    --muted: #9a9a9a;
    --border: rgba(255, 255, 255, 0.16);
    --border-soft: rgba(255, 255, 255, 0.12);
    --ease: cubic-bezier(0.16, 1, 0.3, 1);
    --pad: 24px;
  }
  * { box-sizing: border-box; }
  .vs404 { min-height: 100vh; }
  .vs404 {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    /* Static page: the Next font variables do not exist here, so name real faces. */
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Helvetica, Arial, system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    overflow-x: hidden;
    display: flex;
    flex-direction: column;
    -webkit-tap-highlight-color: transparent;
  }

  /* Ambient light pools: the glass has to catch something, or it reads as flat plastic. */
  .g404-aura { position: fixed; inset: 0; pointer-events: none; z-index: 0; }
  .g404-aura::before, .g404-aura::after {
    content: ""; position: absolute; border-radius: 50%; filter: blur(90px);
  }
  .g404-aura::before {
    width: 60vmax; height: 60vmax; left: -14vmax; top: -22vmax;
    background: radial-gradient(circle, rgba(120, 170, 255, 0.20), transparent 62%);
  }
  .g404-aura::after {
    width: 52vmax; height: 52vmax; right: -16vmax; bottom: -20vmax;
    background: radial-gradient(circle, rgba(196, 150, 255, 0.16), transparent 64%);
  }
  .g404-grain {
    position: fixed; inset: 0; z-index: 1; pointer-events: none; opacity: 0.16;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3'/></filter><rect width='160' height='160' filter='url(%23n)' opacity='0.42'/></svg>");
    mix-blend-mode: overlay;
  }

  .vs404 main {
    position: relative; z-index: 2; flex: 1;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: clamp(20px, 3.4vw, 34px);
    padding: clamp(40px, 9vh, 96px) var(--pad);
    text-align: center;
  }

  .g404-eyebrow {
    margin: 0; font-size: clamp(10px, 1.5vw, 12px); letter-spacing: 0.34em;
    text-transform: uppercase; color: var(--muted);
    opacity: 0; animation: rise 0.9s var(--ease) 0.05s forwards;
  }

  /* ---------------------------------------------------------------- liquid glass 404
     Four stacked layers share one glyph: an extruded body, the refracting glass face,
     a specular sweep, and a caustic pool underneath. Each is the same text so the
     silhouette stays identical while the materials differ. */
  .g404-glass {
    position: relative;
    font-weight: 800;
    font-size: clamp(116px, 27vw, 340px);
    line-height: 0.92;
    letter-spacing: clamp(-6px, -0.9vw, -2px);
    opacity: 0; animation: rise 1.1s var(--ease) 0.14s forwards;
    will-change: transform;
  }
  /* The stack must stay a grid: every layer sits in the same cell so the four materials
     overlap into one glyph. Do not give .g404-glass > span a display of its own — it outranks
     .g404-stack on specificity and the layers fall into a vertical column. */
  .g404-glass .g404-stack { display: grid; place-items: center; position: relative; }
  .g404-glass .g404-layer { grid-area: 1 / 1; position: relative; }

  /* Extruded depth — stacked shadows fake the side walls of a solid slab. */
  .g404-depth {
    color: rgba(255, 255, 255, 0.07);
    text-shadow:
      0 1px 0 rgba(255,255,255,.22), 0 2px 0 rgba(190,205,235,.18), 0 3px 0 rgba(170,190,225,.15),
      0 4px 0 rgba(150,175,215,.13), 0 6px 0 rgba(130,160,205,.11), 0 8px 0 rgba(110,145,195,.09),
      0 12px 24px rgba(0,0,0,.55), 0 30px 60px rgba(0,0,0,.45);
    transform: translateY(2px);
  }

  /* The glass face itself: a cool gradient with a bright top edge and a heavy bottom lip. */
  .g404-face {
    background:
      linear-gradient(176deg,
        rgba(255,255,255,0.96) 0%,
        rgba(214,230,255,0.80) 17%,
        rgba(150,185,240,0.42) 38%,
        rgba(120,150,215,0.30) 52%,
        rgba(196,170,245,0.40) 74%,
        rgba(255,255,255,0.88) 100%);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    -webkit-text-stroke: 1.2px rgba(255, 255, 255, 0.5);
    filter: drop-shadow(0 2px 10px rgba(140, 180, 255, 0.34));
  }

  /* Surface tension: a travelling highlight, the thing that sells it as liquid. */
  .g404-sheen {
    background: linear-gradient(104deg,
      transparent 32%, rgba(255,255,255,0.10) 42%, rgba(255,255,255,0.92) 50%,
      rgba(255,255,255,0.10) 58%, transparent 68%);
    background-size: 280% 100%;
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    animation: sweep 5.6s var(--ease) 1.1s infinite;
  }

  /* Caustic pool — light that passed through the glass and landed on the floor. */
  .g404-caustic {
    color: transparent;
    text-shadow: 0 0 46px rgba(150, 190, 255, 0.55), 0 0 110px rgba(190, 150, 255, 0.35);
    filter: blur(2px);
  }

  .g404-copy { max-width: 46ch; display: grid; gap: 12px; opacity: 0; animation: rise 0.9s var(--ease) 0.34s forwards; }
  .g404-copy h1 { margin: 0; font-size: clamp(19px, 2.9vw, 27px); font-weight: 600; letter-spacing: -0.02em; }
  .g404-copy p { margin: 0; color: var(--muted); font-size: clamp(14px, 1.8vw, 16px); line-height: 1.6; }
  .g404-stamp {
    font-family: ui-monospace, "SF Mono", "Geist Mono", monospace;
    font-size: 11px; letter-spacing: 0.16em; text-transform: uppercase;
    color: rgba(255,255,255,0.42);
  }

  .g404-actions { display: flex; flex-wrap: wrap; gap: 12px; justify-content: center;
             opacity: 0; animation: rise 0.9s var(--ease) 0.46s forwards; }
  .g404-btn {
    display: inline-flex; align-items: center; justify-content: center;
    height: 46px; padding: 0 22px; border-radius: 999px;
    font-size: 14px; font-weight: 500; text-decoration: none;
    border: 1px solid var(--border); transition: transform .3s var(--ease), background .3s var(--ease), border-color .3s var(--ease);
  }
  .g404-btn:hover, .g404-btn:focus-visible { transform: translateY(-2px); }
  .g404-btn-solid { background: #ffffff; color: #000000; border-color: #ffffff; }
  .g404-btn-solid:hover, .g404-btn-solid:focus-visible { background: rgba(255,255,255,0.88); }
  .g404-btn-ghost { color: var(--text); background: rgba(255,255,255,0.04); }
  .g404-btn-ghost:hover, .g404-btn-ghost:focus-visible { background: rgba(255,255,255,0.09); border-color: rgba(255,255,255,0.3); }

  @keyframes rise { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: none; } }
  @keyframes sweep { 0% { background-position: 150% 0; } 55%, 100% { background-position: -150% 0; } }
  @keyframes bob { 0%, 100% { transform: translateY(0) rotateX(0deg); } 50% { transform: translateY(-10px) rotateX(2deg); } }

  @media (prefers-reduced-motion: no-preference) {
    .g404-glass { animation: rise 1.1s var(--ease) 0.14s forwards, bob 7s var(--ease) 1.2s infinite; }
  }
  @media (prefers-reduced-motion: reduce) {
    .g404-sheen { animation: none; background-position: -150% 0; }
    .g404-eyebrow, .g404-glass, .g404-copy, .g404-actions { opacity: 1; animation: none; }
  }
` }} />

  <div className="g404-aura" aria-hidden="true"></div>
  <div className="g404-grain" aria-hidden="true"></div>

  <main>
    <p className="g404-eyebrow">Error 404 · Page not found</p>

    <div className="g404-glass" role="img" aria-label="404">
      <span className="g404-stack" aria-hidden="true">
        <span className="g404-layer g404-caustic">404</span>
        <span className="g404-layer g404-depth">404</span>
        <span className="g404-layer g404-face">404</span>
        <span className="g404-layer g404-sheen">404</span>
      </span>
    </div>

    <div className="g404-copy">
      <h1>This page was never issued for construction.</h1>
      <p>
        We checked the drawing register twice. No revision, no RFI, no permit —
        just an empty grid reference and a URL somebody typed from memory.
      </p>
      <p className="g404-stamp">Status: Superseded · Latest revision: the home page</p>
    </div>

    <div className="g404-actions">
      <a className="g404-btn g404-btn-solid" href="/">Back to safety</a>
      <a className="g404-btn g404-btn-ghost" href="/app">Launch App</a>
    </div>
  </main>
    </div>
  );
}
