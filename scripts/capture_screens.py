#!/usr/bin/env python3
"""Capture product screenshots into docs/media/screens/ (landing + the /demo console).

Needs the Next dev server running (default http://localhost:3100) and Python Playwright:
    python3 scripts/capture_screens.py [base_url]
The console shots use /demo, which replays real engine output, so no sign-in is needed.
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3100").rstrip("/")
OUT = Path(__file__).resolve().parent.parent / "docs" / "media" / "screens"
OUT.mkdir(parents=True, exist_ok=True)
MOBILE = {"width": 390, "height": 844}


def shot(page: Page, name: str, full: bool = False) -> None:
    page.add_style_tag(content="nextjs-portal{display:none!important}")  # dev overlay badge
    page.screenshot(path=str(OUT / f"{name}.jpg"), full_page=full, type="jpeg", quality=82)
    print("  ", name)


def settle(page: Page, ms: int = 900) -> None:
    page.wait_for_timeout(ms)


def landing(page: Page, prefix: str, sections: list[str]) -> None:
    page.goto(f"{BASE}/", wait_until="networkidle")
    settle(page, 2600)  # entrance animation + first video frames
    shot(page, f"{prefix}-hero")
    for sec in sections:
        page.evaluate(f"document.getElementById('{sec}')?.scrollIntoView({{block:'start'}})")
        settle(page, 1400)  # scroll-reveal
        shot(page, f"{prefix}-{sec}")


def open_tab(page: Page, label: str) -> None:
    page.locator("#workflow-navigation button", has_text=label).click()
    settle(page, 700)


def console(page: Page) -> None:
    # skip the auto tour for clean screens; tour shots are taken separately below
    page.add_init_script("try{localStorage.setItem('vesper-tour-v2-demo','true')}catch(e){}")
    page.goto(f"{BASE}/demo", wait_until="networkidle")
    settle(page, 1200)
    shot(page, "app-live-replay")
    page.evaluate("window.dispatchEvent(new Event('vesper-demo-finish'))")
    settle(page)
    page.locator("#tour-site-memory button").first.click()
    settle(page)
    shot(page, "app-live-memory")
    page.locator("#tour-site-memory button").first.click()
    page.locator("#tour-live-evidence").scroll_into_view_if_needed()
    settle(page)
    shot(page, "app-live-challenge")

    open_tab(page, "Talk")
    for text in ["What should I check before the L4 slab pour?", "What is the cover at E-1?"]:
        page.locator("#workflow-suggestions button", has_text=text).click()
        settle(page, 1400)
    page.locator("#workflow-review-area").scroll_into_view_if_needed()
    shot(page, "app-talk-answer")
    page.locator("#workflow-suggestions button", has_text="E-1 column cover measured 30 mm").click()
    settle(page, 1400)
    page.locator("#tour-talk-choose").scroll_into_view_if_needed()
    settle(page)
    shot(page, "app-talk-challenge")
    page.locator("#tour-talk-choose button", has_text="Raise NCR").click()
    settle(page, 1400)
    shot(page, "app-talk-logged")
    page.locator("#workflow-suggestions button", has_text="Welding at Zone B level 3").click()
    settle(page, 1400)
    page.locator("#tour-talk-choose").scroll_into_view_if_needed()
    settle(page)
    shot(page, "app-talk-permit-blocker")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    settle(page)
    shot(page, "app-talk-history")

    open_tab(page, "Logs")
    page.locator("#tour-logs").click()
    settle(page, 1200)
    shot(page, "app-logs")
    open_tab(page, "Scenarios")
    page.locator("#tour-scenarios-run").click()
    settle(page, 1500)
    shot(page, "app-scenarios")
    open_tab(page, "Enroll")
    shot(page, "app-enroll")


def tour(page: Page) -> None:
    page.goto(f"{BASE}/demo", wait_until="networkidle")
    page.wait_for_selector(".driver-popover", timeout=8000)
    settle(page, 1200)
    shot(page, "tour-01-welcome")
    wanted = {2: "tour-02-live", 5: "tour-05-evidence", 9: "tour-09-choose", 11: "tour-11-scenarios"}
    for i in range(2, 12):
        page.locator(".driver-popover-next-btn").click()
        settle(page, 2600)
        if i in wanted:
            shot(page, wanted[i])


ONLY = set(sys.argv[2:])  # e.g. "tour" to recapture only the tour

with sync_playwright() as p:
    # real Chrome: Playwright's bundled Chromium has no H.264, so the hero video would be black
    browser = p.chromium.launch(channel="chrome")
    if not ONLY or "landing" in ONLY:
        print("landing (desktop)")
        desk = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        landing(desk, "landing", ["problem", "how-it-works", "benefits", "templates", "scenarios", "compare", "pricing", "faqs"])
        print("landing (mobile)")
        mob = browser.new_page(viewport=MOBILE, device_scale_factor=2, is_mobile=True, has_touch=True)
        landing(mob, "landing-mobile", ["how-it-works", "benefits"])
    if not ONLY or "app" in ONLY:
        print("console (/demo, mobile)")
        app = browser.new_context(viewport=MOBILE, device_scale_factor=2, is_mobile=True, has_touch=True).new_page()
        console(app)
    if not ONLY or "tour" in ONLY:
        print("guided tour (/demo, mobile)")
        t = browser.new_context(viewport=MOBILE, device_scale_factor=2, is_mobile=True, has_touch=True).new_page()
        tour(t)
    browser.close()
print(f"saved to {OUT}")
