#!/usr/bin/env bash
# Build the public, key-free site for Cloudflare Pages: the landing page at "/" and the
# /demo console (recorded engine output + pre-rendered Rime clips + guided tour).
# No backend, no Clerk, no API keys ship in this build.
#
#   scripts/build_static_demo.sh            # build into app/.next-static
#   scripts/build_static_demo.sh deploy     # build, then deploy to vesper-ai.pages.dev
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f app/public/demo-audio/manifest.json ]; then
  echo "note: no pre-rendered Rime clips (run backend/.venv/bin/python scripts/build_demo_audio.py); demo will be silent"
fi

(cd app && rm -rf .next-static && STATIC_DEMO=1 node_modules/.bin/next build)
OUT=app/.next-static

python3 - "$OUT" <<'PY'
import pathlib, re, sys
out = pathlib.Path(sys.argv[1])
landing = (out / "landing" / "index.html").read_text()
# On the public link every "Launch App" opens the key-free laptop dashboard (recorded data + tour);
# the phone console replay stays at /demo/.
landing = landing.replace('href="/app"', 'href="/app/"')
# The public build carries no Clerk keys, so the sign-in / sign-out links have nothing to talk to
# (/sign-in* already redirects to /app/, and /sign-out has no rule at all). Drop those anchors.
landing = re.sub(r'<a[^>]*href="/sign-(?:in|out)"[^>]*>.*?</a>', '', landing)
(out / "index.html").write_text(landing)
(out / "landing" / "index.html").write_text(landing)
(out / "_redirects").write_text("/app /app/ 301\n/onboarding /onboarding/ 301\n/sign-in* /app/ 302\n/sign-up* /app/ 302\n/demo /demo/ 301\n")
# next build emits its own bare 404.html at the output root and it wins over public/404.html,
# so Cloudflare would serve "This page could not be found." Put ours back on top.
custom_404 = pathlib.Path("app/public/404.html")
if custom_404.exists():
    (out / "404.html").write_text(custom_404.read_text())
for junk in ("uploads",):
    p = out / junk
    if p.is_dir() and not any(p.iterdir()):
        p.rmdir()
PY

# Fail the build if anything secret-shaped slipped into the static output.
if grep -rqE "pk_(test|live)_|sk_(test|live)_|sk_[a-z0-9]{8}_[A-Za-z0-9]{20,}|re_[A-Za-z0-9]{8}_[A-Za-z0-9]{20,}|csk-[a-z0-9]{10}|gsk_[A-Za-z0-9]{10}|nvapi-|RIME_API_KEY|SARVAM_API_KEY|RESEND_API_KEY" "$OUT"; then
  echo "refusing to ship: secret-like string found in $OUT" >&2
  exit 1
fi
echo "static site ready: $OUT ($(du -sh "$OUT" | cut -f1))"

if [ "${1:-}" = "deploy" ]; then
  npx wrangler pages deploy "$OUT" --project-name vesper-ai --branch main --commit-dirty=true
fi
