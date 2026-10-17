#!/usr/bin/env python3
"""
Scrape the three infralens.in template libraries (Site Formats, QA/QC, PMC) with Firecrawl.

  python3 data/scraper/scrape_infralens.py            # scrape everything not yet cached
  python3 data/scraper/scrape_infralens.py --limit 5  # only 5 new detail pages (smoke test)
  python3 data/scraper/scrape_infralens.py --offline  # just report cache coverage

Cache layout (re-runs never re-spend credits for cached URLs):
  data/raw/_map.json                    Firecrawl map of https://infralens.in (discovery, 1 credit)
  data/raw/<lib>__index.json            index page  (markdown, links, metadata, fetched_via)
  data/raw/<lib>__<family>__<slug>.json template page
  data/raw/html/<same-name>.html.gz     rawHtml of the page (holds the embedded Next.js RSC template JSON)

Discovery: the site map is truncated (5000-URL cap, dominated by /code pages), so the authoritative
inventory is the `families` array embedded in each library's index page; every template has a slug
and the page URL is https://infralens.in/<lib>/<family_id>/<slug>.

The FIRECRAWL_API_KEY is read from <repo>/.env (never printed). If Firecrawl fails after retries
(or credits run out) the page is fetched with plain HTTP as a fallback and marked fetched_via='http'.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent
ROOT = DATA.parent
RAW = DATA / "raw"
HTML = RAW / "html"
sys.path.insert(0, str(HERE))
from parse_infralens import decode_rsc, extract_families  # noqa: E402

BASE = "https://infralens.in"
LIBS = {"formats": f"{BASE}/formats", "qaqc": f"{BASE}/qaqc", "pmc": f"{BASE}/pmc"}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) VesperDataBot/0.1 (hackathon; polite)"

_lock = threading.Lock()
STATS = {"firecrawl": 0, "http": 0, "cached": 0, "failed": 0}


def load_key() -> str | None:
    key = os.environ.get("FIRECRAWL_API_KEY")
    if key:
        return key
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith("FIRECRAWL_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def cache_name(lib: str, family: str | None = None, slug: str | None = None) -> str:
    if family is None:
        return f"{lib}__index"
    return f"{lib}__{family}__{slug}"


REFETCH_HTTP = False


def cached(name: str) -> bool:
    p = RAW / f"{name}.json"
    if not (p.exists() and (HTML / f"{name}.html.gz").exists()):
        return False
    if REFETCH_HTTP:
        try:
            return json.loads(p.read_text()).get("fetched_via") != "http"
        except Exception:  # noqa: BLE001
            return False
    return True


def save(name: str, url: str, via: str, markdown: str, links: list, metadata: dict, raw_html: str):
    RAW.mkdir(parents=True, exist_ok=True)
    HTML.mkdir(parents=True, exist_ok=True)
    rec = {
        "url": url,
        "fetched_via": via,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "metadata": metadata or {},
        "links": links or [],
        "markdown": markdown or "",
        "raw_html_file": f"html/{name}.html.gz",
    }
    with gzip.open(HTML / f"{name}.html.gz", "wt", encoding="utf-8") as fh:
        fh.write(raw_html or "")
    tmp = RAW / f"{name}.json.tmp"
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    tmp.replace(RAW / f"{name}.json")


def fetch_firecrawl(app, url: str):
    doc = app.scrape(url, formats=["markdown", "links", "rawHtml"], only_main_content=False,
                     timeout=60000)
    d = doc.model_dump() if hasattr(doc, "model_dump") else dict(doc)
    md = d.get("markdown") or ""
    raw = d.get("raw_html") or d.get("rawHtml") or ""
    meta = d.get("metadata") or {}
    meta = {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool, list, type(None)))}
    if not raw:
        raise RuntimeError("firecrawl returned no rawHtml")
    return md, d.get("links") or [], meta, raw


def fetch_http(url: str):
    import requests
    r = requests.get(url, headers={"User-Agent": UA}, timeout=40)
    r.raise_for_status()
    return "", [], {"statusCode": r.status_code, "sourceURL": url}, r.content.decode("utf-8", "replace")


def fetch(app, name: str, url: str, force: bool = False, allow_http: bool = True) -> bool:
    if not force and cached(name):
        with _lock:
            STATS["cached"] += 1
        return True
    last = None
    if app is not None:
        for attempt in range(6):
            try:
                md, links, meta, raw = fetch_firecrawl(app, url)
                save(name, url, "firecrawl", md, links, meta, raw)
                with _lock:
                    STATS["firecrawl"] += 1
                return True
            except Exception as e:  # noqa: BLE001
                last = e
                msg = str(e).lower()
                if "insufficient" in msg or "payment" in msg or "402" in msg:
                    break  # out of credits -> fall back
                # 429 / concurrency limit (plan max_concurrency=2): back off harder
                time.sleep(min(30, 3 * (2 ** attempt)) + random.random() * 2)
    if allow_http:
        for attempt in range(3):
            try:
                md, links, meta, raw = fetch_http(url)
                save(name, url, "http", md, links, meta, raw)
                with _lock:
                    STATS["http"] += 1
                return True
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep((2 ** attempt) + random.random())
    with _lock:
        STATS["failed"] += 1
    print(f"  !! failed {url}: {last}", file=sys.stderr)
    return False


def read_html(name: str) -> str:
    p = HTML / f"{name}.html.gz"
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        return fh.read()


def discover_map(app):
    p = RAW / "_map.json"
    if p.exists() or app is None:
        return
    m = app.map(BASE, limit=5000)
    d = m.model_dump() if hasattr(m, "model_dump") else m
    p.write_text(json.dumps(d, indent=1, default=str))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max new detail pages to fetch (0 = all)")
    ap.add_argument("--workers", type=int, default=2, help="Firecrawl plan max_concurrency is 2")
    ap.add_argument("--refetch-http", action="store_true",
                    help="re-fetch pages that were cached via the plain-HTTP fallback using Firecrawl")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--http-only", action="store_true", help="skip Firecrawl, plain HTTP only")
    ap.add_argument("--only", choices=list(LIBS), action="append")
    args = ap.parse_args()
    global REFETCH_HTTP
    REFETCH_HTTP = args.refetch_http

    app = None
    if not args.offline and not args.http_only:
        key = load_key()
        if key:
            from firecrawl import Firecrawl
            app = Firecrawl(api_key=key)
            try:
                print("firecrawl credits before:", app.get_credit_usage().remaining_credits)
            except Exception:  # noqa: BLE001
                pass
        else:
            print("FIRECRAWL_API_KEY not found; using plain HTTP", file=sys.stderr)

    if not args.offline:
        discover_map(app)

    libs = args.only or list(LIBS)
    jobs = []
    for lib in libs:
        name = cache_name(lib)
        if not args.offline:
            fetch(app, name, LIBS[lib])
        if not cached(name):
            print(f"[{lib}] index not cached", file=sys.stderr)
            continue
        fams = extract_families(decode_rsc(read_html(name)))
        n = sum(len(f["templates"]) for f in fams)
        print(f"[{lib}] index: {len(fams)} families, {n} templates")
        for f in fams:
            for t in f["templates"]:
                jobs.append((cache_name(lib, f["family_id"], t["slug"]),
                             f"{BASE}/{lib}/{f['family_id']}/{t['slug']}"))

    todo = [(n, u) for n, u in jobs if not cached(n)]
    print(f"detail pages: {len(jobs)} total, {len(jobs) - len(todo)} cached, {len(todo)} to fetch")
    if args.offline:
        return
    if args.limit:
        todo = todo[: args.limit]
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 5))) as ex:
        futs = [ex.submit(fetch, app, n, u) for n, u in todo]
        for fu in as_completed(futs):
            fu.result()
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(todo)} {STATS}", flush=True)
    print("done:", STATS)
    if app is not None:
        try:
            print("firecrawl credits after:", app.get_credit_usage().remaining_credits)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
