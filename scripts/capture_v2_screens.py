"""Recapture the v2 dashboard screenshots used by the walkthrough GIF.

The dashboard is behind Clerk, so this uses the dev-preview cookie that `app/proxy.ts` honours
outside production. It seeds a little local state first (Ask history threads) so the panels are
shown populated rather than empty.

    # Next dev server on :3000, then
    python3 scripts/capture_v2_screens.py
    python3 scripts/capture_v2_screens.py --base http://localhost:3000 --only ask

Writes docs/media/screens/v2-*.jpg at 1440x900, which is what build_walkthrough_gif.py expects.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "media" / "screens"

# name -> (path, settle seconds)
SHOTS = {
    "ask": ("/app/ask", 3.0),
    "dash-overview": ("/app", 3.5),
    "memory": ("/app/memory", 3.5),
    "documents": ("/app/documents", 3.0),
}
FILES = {
    "ask": "v2-ask-memory.jpg",
    "dash-overview": "v2-dash-overview.jpg",
    "memory": "v2-memory.jpg",
    "documents": "v2-documents.jpg",
}

# Shown in the Ask history panel so the capture is not an empty state.
SEED_THREADS = [
    {"id": "s1", "title": "What cover does IS 456 require for columns?", "updatedAt": 0,
     "msgs": [{"id": "u1", "role": "user", "text": "What cover does IS 456 require for columns?"}]},
    {"id": "s2", "title": "Which permits are blocking work today?", "updatedAt": 0,
     "msgs": [{"id": "u2", "role": "user", "text": "Which permits are blocking work today?"}]},
    {"id": "s3", "title": "What is holding the L4 slab pour?", "updatedAt": 0,
     "msgs": [{"id": "u3", "role": "user", "text": "What is holding the L4 slab pour?"}]},
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--only", nargs="*", choices=sorted(SHOTS), help="capture just these")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    names = args.only or list(SHOTS)
    OUT.mkdir(parents=True, exist_ok=True)

    now_ms = int(time.time() * 1000)
    threads = [{**t, "updatedAt": now_ms - i * 5_400_000} for i, t in enumerate(SEED_THREADS)]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        # The walkthrough GIF is dark throughout; headless Chromium reports prefers-color-scheme:
        # light, which would drop one light frame into the middle of it.
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                  color_scheme="dark")
        # proxy.ts lets this cookie through outside production, so the capture does not need a login.
        ctx.add_cookies([{"name": "vesper_dev_preview", "value": "1", "url": base}])
        ctx.add_init_script(
            "try{localStorage.setItem('vesper_ask_threads_P1', %s);"
            "localStorage.setItem('vesper_ask_history_open','1');"
            "localStorage.setItem('vesper-theme','dark');"
            # DashTour keys its "seen" flag per user (`vesper-dash-tour-v2-<id>`), and the capture
            # runs signed out, so the id is "anon". Without this the welcome modal covers Overview.
            "localStorage.setItem('vesper-dash-tour-v2-anon','1');"
            "localStorage.setItem('vesper-dash-tour-v2','1');"
            "localStorage.setItem('vesper-tour-v2-demo','true')}catch(e){}"
            % json.dumps(json.dumps(threads))
        )
        page = ctx.new_page()
        for name in names:
            path, settle = SHOTS[name]
            page.goto(f"{base}{path}", wait_until="networkidle", timeout=45_000)
            page.add_style_tag(content="nextjs-portal,[data-nextjs-toolbar],#__next-build-watcher"
                                       "{display:none !important}")
            page.wait_for_timeout(int(settle * 1000))
            target = OUT / FILES[name]
            page.screenshot(path=str(target), type="jpeg", quality=88)
            print(f"{FILES[name]:26} {target.stat().st_size // 1024} KB  <- {path}")
        ctx.close()
        browser.close()
    print(f"\nwrote {len(names)} screenshot(s) to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
