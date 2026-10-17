#!/usr/bin/env python3
"""Build docs/media/vesper-walkthrough.gif from the captured screenshots.

The GIF is a captioned walkthrough of Vesper.ai: a title card followed by
17 annotated frames (landing page, live site memory, answers from the record,
drawing contradictions, decision buttons, permit blockers, audit logs, the
scenario suite, the voiceprint gate and the guided tour).

Inputs : docs/media/screens/*.jpg   (captured by scripts/capture_screens.py)
Output : docs/media/vesper-walkthrough.gif

Usage (any Python 3 with Pillow installed):

    python -m pip install pillow
    python scripts/build_walkthrough_gif.py            # default output path
    python scripts/build_walkthrough_gif.py --no-fade  # skip crossfades (smaller file)
    python scripts/build_walkthrough_gif.py --out /tmp/walkthrough.gif

Design: 1200x760 black canvas, white/grey sans text (SF Pro / Helvetica Neue,
Pillow default as last resort), accent #bad0ff used sparingly, red #f87171
only on the "challenge / blocked" frames. Every content frame carries its
annotation bar at the TOP (step chip, bold caption, one grey explanation line)
with the screenshot fitted underneath. Frames are quantised to an adaptive
128-colour palette so the file stays well under 9 MB.

To change the story, edit STEPS below and re-run.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SCREENS = ROOT / "docs" / "media" / "screens"
DEFAULT_OUT = ROOT / "docs" / "media" / "vesper-walkthrough.gif"

W, H = 1200, 760
BG = (0, 0, 0)
WHITE = (245, 245, 245)
GREY = (150, 150, 150)
DIM = (90, 90, 90)
LINE = (38, 38, 38)
ACCENT = (186, 208, 255)  # #bad0ff
RED = (248, 113, 113)     # #f87171

BAR_H = 124               # annotation bar height (top of every content frame)
PAD = 40

TITLE_MS = 3500
STEP_MS = 2800
FADE_MS = 90
FADE_STEPS = 2            # blend frames between slides
COLORS = 128

TITLE = "Vesper.ai — voice-led site memory"
SUBLINE = ("It checks what you say against the latest drawings, permits and hold "
           "points — and argues before anything wrong is logged. "
           "Every reply spoken with Rime.")

# (screenshot, caption, explanation, tag) -- a tag ("CHALLENGE"/"BLOCKED") renders the chip in red.
STEPS = [
    ("landing-hero.jpg",
     "Site AI agents that catch errors before they're built",
     "Speak in Hinglish; every observation is checked against the latest drawings, RFIs, BOQ and permits.",
     None),
    ("v2-landing-stack.jpg",
     "Built end to end on an open, local-first stack",
     "Next.js · FastAPI · LiveKit · Sarvam · Rime · Groq/Cerebras · bge-m3 · LanceDB · Cognee · Clerk · Cloudflare.",
     None),
    ("v2-dash-overview.jpg",
     "One laptop dashboard per project",
     "Switch Pithoragarh ↔ Nashik: KPIs, blockers, drawings, RFIs, permits and Live voice all follow the project.",
     None),
    ("v2-ask-memory.jpg",
     "Ask memory: cited answers or an honest no",
     "IS codes, 550 QA/QC templates and your PDFs — every claim cites a clause, checklist or page.",
     None),
    ("v2-memory.jpg",
     "Local-first memory with a knowledge graph",
     "bge-m3 + BM25 fusion, cross-encoder rerank, per-project datasets, Cognee graph; the same tools are exposed over MCP.",
     None),
    ("v2-documents.jpg",
     "Upload PDFs, paste text or speak a briefing",
     "Drawing registers, specs, BOQs, method statements — parsed, chunked, embedded and searchable in seconds.",
     None),
    ("app-live-replay.jpg",
     "Opens with site memory, not a blank chat",
     "Voice verified 0.86 · C-401 R2 issued · hold point CL-PP-L4-001 at Slab L4 still not released.",
     None),
    ("app-live-memory.jpg",
     "Knows what needs attention on site today",
     "5 open RFIs · 1 hold point · 3 permits blocked — each with the exact shortfall and pending check.",
     None),
    ("app-talk-answer.jpg",
     "Questions answered straight from the record",
     "“Cover at E-1?” → 40 mm ± 5 per A-201 R1 issued 26 Aug (IS 456 Cl. 26.4), plus open RFI-061.",
     None),
    ("app-live-challenge.jpg",
     "You said 30 mm. The drawing says 40 ± 5.",
     "Vesper challenges with A-201 R1; the follow-up “what is the tolerance there?” keeps the E-1 context.",
     "CHALLENGE"),
    ("app-talk-challenge.jpg",
     "Nothing is logged until you decide",
     "Contradiction card, then one tap: Log observation, Raise RFI, Raise NCR or Cancel.",
     "CHALLENGE"),
    ("app-talk-logged.jpg",
     "Your decision, confirmed and written",
     "OBS-000110 logged for an NCR only after the manager chose — never silently.",
     None),
    ("app-talk-permit-blocker.jpg",
     "Unsafe work is blocked, not logged",
     "Hot work at Zone B L3: HWP-0112 fire-watch checks still pending, so only Stop work, Raise NCR or Cancel.",
     "BLOCKED"),
    ("app-logs.jpg",
     "Every log is tied to a verified revision",
     "Audit trail: RW-1 350 mm on C-401@R2 linked to RFI-060; the Zone B hot-work entry is flagged CONFLICT.",
     None),
    ("app-scenarios.jpg",
     "10 / 10 scenarios pass · 0 wrong logs",
     "Regression suite replays revision mismatches, tolerance breaches, barge-ins and permit blockers.",
     None),
    ("app-enroll.jpg",
     "Only the enrolled manager's voice can write",
     "VoiceID gate: status ENROLLED, threshold 0.7, enforcement ACTIVE — trained on 3 Hinglish takes.",
     None),
    ("tour-05-evidence.jpg",
     "Guided tour: it argues with citations",
     "Evidence: A-201 R1 issued 2026-08-26 · expected 40 mm ± 5 · you said 30 mm · IS 456 Cl. 26.4.",
     None),
]

# ---------------------------------------------------------------- fonts

_SANS = [
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_MONO = [
    "/System/Library/Fonts/SFNSMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]


def _font(paths: list[str], size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont:
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            if path.endswith("HelveticaNeue.ttc"):
                return ImageFont.truetype(path, size, index=1 if weight in ("Bold", "Semibold") else 0)
            if path.endswith("Helvetica.ttc"):
                return ImageFont.truetype(path, size, index=1 if weight in ("Bold", "Semibold") else 0)
            font = ImageFont.truetype(path, size)
            try:
                font.set_variation_by_name(weight)
            except Exception:
                pass
            return font
        except Exception:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def sans(size: int, weight: str = "Regular"):
    return _font(_SANS, size, weight)


def mono(size: int, weight: str = "Regular"):
    return _font(_MONO, size, weight)


def text_w(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    l, _, r, _ = draw.textbbox((0, 0), text, font=font)
    return r - l


def fit_font(draw, text, max_w, size, weight, min_size):
    while size > min_size:
        f = sans(size, weight)
        if text_w(draw, text, f) <= max_w:
            return f
        size -= 1
    return sans(min_size, weight)


def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if text_w(draw, trial, font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- helpers

def rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=255)
    return mask


def paste_shot(canvas: Image.Image, shot: Image.Image, box, radius: int, border=(58, 58, 58)):
    """Fit `shot` inside `box` (x0, y0, x1, y1), centred, rounded, with a thin border."""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    scale = min(bw / shot.width, bh / shot.height)
    size = (round(shot.width * scale), round(shot.height * scale))
    img = shot.resize(size, Image.LANCZOS)
    px = x0 + (bw - size[0]) // 2
    py = y0 + (bh - size[1]) // 2
    canvas.paste(img, (px, py), rounded_mask(size, radius))
    ImageDraw.Draw(canvas).rounded_rectangle(
        (px - 1, py - 1, px + size[0], py + size[1]), radius + 1, outline=border, width=1)
    return (px, py, px + size[0], py + size[1])


def load(name: str) -> Image.Image:
    return Image.open(SCREENS / name).convert("RGB")


# ---------------------------------------------------------------- frames

def title_card() -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((PAD + 4, 44), "VESPER.AI  ·  WALKTHROUGH", font=mono(15), fill=ACCENT)
    tf = fit_font(d, TITLE, W - 2 * PAD, 50, "Bold", 30)
    d.text((PAD, 74), TITLE, font=tf, fill=WHITE)
    sf = sans(21)
    y = 146
    for line in wrap(d, SUBLINE, sf, W - 2 * PAD - 120):
        d.text((PAD + 2, y), line, font=sf, fill=GREY)
        y += 31
    d.line((PAD, y + 20, W - PAD, y + 20), fill=LINE, width=1)

    # Preview strip of four app screens, dimmed, below the message.
    previews = ["app-live-replay.jpg", "app-live-challenge.jpg",
                "app-talk-permit-blocker.jpg", "app-scenarios.jpg"]
    top = y + 44
    slot_h = H - top - 28
    slot_w = round(slot_h * 780 / 1688)
    gap = 36
    total = len(previews) * slot_w + (len(previews) - 1) * gap
    x = (W - total) // 2
    for name in previews:
        paste_shot(im, load(name), (x, top, x + slot_w, top + slot_h), 14)
        x += slot_w + gap
    # Fade the strip toward the bottom so the message stays dominant.
    fade = Image.new("L", (W, H), 0)
    fd = ImageDraw.Draw(fade)
    for yy in range(top, H):
        fd.line((0, yy, W, yy), fill=int(110 + 130 * (yy - top) / max(1, H - top)))
    im = Image.composite(Image.new("RGB", (W, H), BG), im, fade)
    return im


def content_frame(idx: int, total: int, shot_name: str, caption: str, note: str, tag: str | None) -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    alert = bool(tag)
    tone = RED if alert else ACCENT

    # --- annotation bar (top)
    chip = f"{idx:02d} / {total:02d}"
    cf = mono(16, "Semibold")
    cw = text_w(d, chip, cf) + 26
    chip_box = (PAD, 30, PAD + cw, 60)
    d.rounded_rectangle(chip_box, 15, outline=tone, width=1,
                        fill=(40, 16, 16) if alert else (16, 20, 30))
    d.text((PAD + 13, 36), chip, font=cf, fill=tone)
    if tag:
        tf_ = mono(14, "Semibold")
        d.text((PAD + cw + 14, 39), tag, font=tf_, fill=RED)
        cap_x = PAD + cw + 14 + text_w(d, tag, tf_) + 16
    else:
        cap_x = PAD + cw + 18
    capf = fit_font(d, caption, W - cap_x - PAD, 29, "Bold", 20)
    d.text((cap_x, 27), caption, font=capf, fill=WHITE)
    nf = fit_font(d, note, W - 2 * PAD, 19, "Regular", 15)
    d.text((PAD + 1, 76), note, font=nf, fill=GREY)
    # progress rule under the bar
    d.line((0, BAR_H - 6, W, BAR_H - 6), fill=LINE, width=1)
    d.line((0, BAR_H - 6, round(W * idx / total), BAR_H - 6), fill=tone, width=2)

    # --- screenshot below the bar
    shot = load(shot_name)
    area = (PAD, BAR_H + 12, W - PAD, H - 16)
    if shot.width > shot.height:            # desktop landing shot: scale to width
        paste_shot(im, shot, area, 10)
    else:                                   # mobile shot: full height, centred
        paste_shot(im, shot, area, 22)
    return im


def quantize(frame: Image.Image) -> Image.Image:
    return frame.convert("P", palette=Image.ADAPTIVE, colors=COLORS)


def build(out: Path, fade: bool) -> None:
    slides = [(title_card(), TITLE_MS)]
    total = len(STEPS)
    for i, (name, cap, note, tag) in enumerate(STEPS, start=1):
        slides.append((content_frame(i, total, name, cap, note, tag), STEP_MS))

    frames, durations = [], []
    for n, (img, ms) in enumerate(slides):
        frames.append(img)
        durations.append(ms)
        if fade:
            nxt = slides[(n + 1) % len(slides)][0]
            for k in range(1, FADE_STEPS + 1):
                frames.append(Image.blend(img, nxt, k / (FADE_STEPS + 1)))
                durations.append(FADE_MS)

    pal = [quantize(f) for f in frames]
    out.parent.mkdir(parents=True, exist_ok=True)
    pal[0].save(out, save_all=True, append_images=pal[1:], duration=durations,
                loop=0, optimize=True, disposal=1)
    size = out.stat().st_size
    print(f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}: "
          f"{len(pal)} frames ({len(slides)} slides), {size / 1024 / 1024:.2f} MB")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-fade", action="store_true", help="skip crossfade blend frames")
    args = ap.parse_args()
    build(args.out, fade=not args.no_fade)


if __name__ == "__main__":
    main()
