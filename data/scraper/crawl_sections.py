#!/usr/bin/env python3
"""Crawl + parse the non-template sections of infralens.in (IS codes, prices, steel, SOR, rate analysis,
thumb rules, handbook, knowledge, glossary terms, DCR, CPHEEO, IRC, GATE).

Cache layout (resumable):
    data/raw/sections/<section>/<slug>.html.gz   raw HTML
    data/raw/sections/<section>/<slug>.json      {url, section, title, text, structured, fetched_at}
    data/raw/sections/_inventory.json            {section: {slug: url}}
    data/raw/sections/_crawl_log.txt             progress (every 50 pages) + final counts

Usage:
    python3 data/scraper/crawl_sections.py                         # full crawl, default sections
    python3 data/scraper/crawl_sections.py --sections code,prices --limit 3
    python3 data/scraper/crawl_sections.py --offline               # coverage report, no network
    python3 data/scraper/crawl_sections.py --reparse [--sections term]   # rebuild JSON from cached HTML
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import sys
import threading
import time
import urllib.robotparser
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "raw"
OUT = RAW / "sections"
sys.path.insert(0, str(HERE))
from parse_infralens import decode_rsc, extract_jsonld, fix_mojibake, _DEC  # noqa: E402

BASE = "https://infralens.in"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0.0.0 Safari/537.36")
DEFAULT_SECTIONS = ["code", "prices", "steel", "sor", "rate-analysis", "thumbrules", "handbook", "knowledge",
                    "term", "dcr", "cpheeo", "irc", "gate"]
# tools/maps/cad-library/tender are interactive apps / file listings; projects/boq are opt-in via --sections.
ALL_KNOWN = DEFAULT_SECTIONS + ["projects", "boq", "tools", "maps", "cad-library", "tender"]
CONCURRENCY = 4
LOG = OUT / "_crawl_log.txt"
_lock = threading.Lock()
STATS = Counter()
_local = threading.local()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str):
    line = f"[{now()}] {msg}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with _lock, LOG.open("a") as f:
        f.write(line + "\n")


# ================================================================================================
# Inventory
# ================================================================================================
def split_url(url: str) -> tuple[str, str] | None:
    path = re.sub(r"^https?://(www\.)?infralens\.in", "", url.split("#")[0].split("?")[0]).strip("/")
    if not path:
        return None
    parts = path.split("/")
    slug = "__".join(parts[1:]) or "_index"
    slug = re.sub(r"[^A-Za-z0-9._\-]", "_", slug)[:180]
    return parts[0], slug


def session():
    import requests
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
        _local.s.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml",
                                 "Accept-Language": "en-IN,en;q=0.9"})
    return _local.s


def http_get(url: str, tries: int = 6) -> tuple[int, str]:
    delay = 2.0
    for attempt in range(tries):
        try:
            r = session().get(url, timeout=45)
            if r.status_code == 429 or r.status_code >= 500:
                ra = r.headers.get("Retry-After")
                wait = float(ra) if ra and ra.isdigit() else delay
                with _lock:
                    STATS["retries"] += 1
                time.sleep(wait + random.uniform(0, 1))
                delay = min(delay * 2, 120)
                continue
            return r.status_code, r.content.decode("utf-8", "replace")
        except Exception:  # network error
            with _lock:
                STATS["retries"] += 1
            time.sleep(delay + random.uniform(0, 1))
            delay = min(delay * 2, 120)
    return -1, ""


def build_inventory(sections: list[str], offline: bool) -> dict:
    inv_path = OUT / "_inventory.json"
    inv: dict[str, dict[str, str]] = defaultdict(dict)
    if inv_path.exists():
        for s, d in json.loads(inv_path.read_text()).items():
            inv[s].update(d)
    urls: list[str] = []
    sm_path = OUT / "_sitemap.xml"
    if not offline:
        code, body = http_get(f"{BASE}/sitemap.xml")
        if code == 200:
            sm_path.write_text(body)
            # sitemap index support
            for sub in re.findall(r"<sitemap>\s*<loc>([^<]+)</loc>", body):
                c2, b2 = http_get(sub.strip())
                if c2 == 200:
                    body += b2
            sm_path.write_text(body)
    if sm_path.exists():
        urls += re.findall(r"<loc>([^<]+)</loc>", sm_path.read_text())
    mp = RAW / "_map.json"
    if mp.exists():
        for x in json.loads(mp.read_text()).get("links", []):
            urls.append(x if isinstance(x, str) else x.get("url", ""))
    if not offline:
        for s in sections:  # section index pages
            code, body = http_get(f"{BASE}/{s}")
            if code == 200:
                urls.append(f"{BASE}/{s}")
                urls += [BASE + h for h in re.findall(r'href="(/' + re.escape(s) + r'(?:/[^"#?]*)?)"', body)]
    for u in urls:
        sp = split_url(u.strip())
        if sp and sp[0] in ALL_KNOWN:
            inv[sp[0]].setdefault(sp[1], BASE + "/" + re.sub(r"^https?://(www\.)?infralens\.in/?", "", u.strip()).rstrip("/"))
    OUT.mkdir(parents=True, exist_ok=True)
    inv_path.write_text(json.dumps({s: dict(sorted(d.items())) for s, d in sorted(inv.items())}, indent=1))
    return inv


# ================================================================================================
# HTML -> markdown-ish text
# ================================================================================================
BLOCK = {"p", "div", "section", "article", "main", "aside", "header", "ul", "ol", "li", "dl", "dt", "dd",
         "blockquote", "pre", "figure", "figcaption", "details", "summary", "tr", "br", "hr", "form",
         "h1", "h2", "h3", "h4", "h5", "h6", "table", "nav", "footer"}
SKIP = {"script", "style", "noscript", "template", "svg", "nav", "footer", "button", "input", "select",
        "textarea", "iframe", "canvas", "img", "link", "meta"}
JUNK_CLASS = re.compile(r"il-nav|eco-bar|footer|breadcrumb|share|toast|cookie", re.I)


def cell_text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).replace("|", "/")


def table_rows(t) -> list[list[str]]:
    rows = []
    for tr in t.find_all("tr"):
        cells = [cell_text(c) for c in tr.find_all(["th", "td"])]
        if any(cells):
            rows.append(cells)
    return rows


def table_md(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    w = max(len(r) for r in rows)
    rows = [r + [""] * (w - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * w]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def clean_inline(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([,.;:)\]%])", r"\1", s)
    return re.sub(r"([(\[₹])\s+", r"\1", s)


def html_to_md(root) -> str:
    from bs4 import Comment, NavigableString
    lines: list[str] = []
    buf: list[str] = []

    def flush(prefix=""):
        t = clean_inline("".join(buf))
        if prefix:
            t = re.sub(r"^[•·▪◦‣\-–]\s*", "", t)
        buf.clear()
        if t:
            lines.append(prefix + t)

    def walk(node, li_prefix=""):
        for ch in node.children:
            if isinstance(ch, Comment):
                continue
            if isinstance(ch, NavigableString):
                buf.append(str(ch))
                continue
            name = ch.name
            if name in SKIP:
                continue
            cls = " ".join(ch.get("class") or [])
            if cls and JUNK_CLASS.search(cls):
                continue
            if name == "table":
                flush(li_prefix)
                md = table_md(table_rows(ch))
                if md:
                    lines.append(md)
            elif name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                flush(li_prefix)
                t = clean_inline(ch.get_text(" ", strip=True))
                if t:
                    lines.append("#" * int(name[1]) + " " + t)
            elif name == "li":
                flush(li_prefix)
                walk(ch, "- ")
                flush("- ")
            elif name in BLOCK:
                flush(li_prefix)
                walk(ch, li_prefix)
                flush(li_prefix)
            else:
                buf.append(" ")
                walk(ch, li_prefix)
                buf.append(" ")
    walk(root)
    flush()
    # dedupe consecutive identical lines
    out = []
    for ln in lines:
        if not out or out[-1] != ln:
            out.append(ln)
    return "\n".join(out)


# ================================================================================================
# Parsing
# ================================================================================================
def find_obj(rsc: str, key: str):
    """Smallest decodable JSON object in the RSC stream that encloses the first occurrence of `key`."""
    i = rsc.find(key)
    j = i
    for _ in range(600):
        if j <= 0:
            return None
        j = rsc.rfind("{", 0, j)
        if j < 0:
            return None
        try:
            o, e = _DEC.raw_decode(rsc, j)
            if e > i and isinstance(o, dict):
                return o
        except json.JSONDecodeError:
            pass
    return None


def ld_of(lds, typ):
    return [x for x in lds if isinstance(x, dict) and (x.get("@type") == typ or typ in (x.get("@type") or []))]


def faq_from(lds) -> list[dict]:
    out = []
    for f in ld_of(lds, "FAQPage"):
        for q in f.get("mainEntity") or []:
            a = q.get("acceptedAnswer") or {}
            out.append({"q": q.get("name"), "a": a.get("text") if isinstance(a, dict) else None})
    return out


def rows_as_dicts(rows: list[list[str]]) -> list[dict]:
    if len(rows) < 2:
        return []
    hdr = [re.sub(r"\W+", "_", h.lower()).strip("_") or f"col{i}" for i, h in enumerate(rows[0])]
    return [dict(zip(hdr, r)) for r in rows[1:]]


def pick(d: dict, *pats) -> str | None:
    for k, v in d.items():
        if any(re.search(p, k) for p in pats):
            return v
    return None


CODE_RE = re.compile(r"\b(IS|IRC|SP|NBC|BS|EN|ASTM|ACI|IEC|ISO)[\s:-]*([0-9]{1,5}(?:\s*\(?Part[\s-]*[0-9A-Z]+\)?)?)"
                     r"(?:\s*[:\-]\s*((?:19|20)[0-9]{2}))?", re.I)


def parse_page(section: str, slug: str, url: str, html: str) -> dict:
    from bs4 import BeautifulSoup
    html = fix_mojibake(html)
    soup = BeautifulSoup(html, "lxml")
    lds = extract_jsonld(html)
    h1 = soup.find("h1")
    title = clean_inline(h1.get_text(" ", strip=True)) if h1 else None
    if not title and soup.title:
        title = clean_inline(soup.title.get_text())
    tables = [table_rows(t) for t in soup.find_all("table")]
    tables = [t for t in tables if t]
    body = soup.body or soup
    text = html_to_md(body)
    if title:  # drop pre-h1 chrome (promo bars, breadcrumbs)
        k = text.find("# " + title)
        if k > 0:
            text = text[text.rfind("\n", 0, k) + 1:]
    headings = [clean_inline(h.get_text(" ", strip=True)) for h in soup.find_all(["h2", "h3"])]
    links = []
    for a in soup.find_all("a", href=True):
        h = a["href"].split("#")[0]
        if h.startswith("/") and len(h) > 1 and h not in links:
            links.append(h)
    ext_docs = [{"title": cell_text(a), "href": a["href"]} for a in soup.find_all("a", href=True)
                if re.search(r"\.pdf($|\?)", a["href"], re.I)]
    arts = ld_of(lds, "TechArticle") + ld_of(lds, "Article")
    desc = None
    for x in lds:
        if isinstance(x, dict) and x.get("description") and x.get("@type") not in ("WebApplication",):
            desc = x["description"]
            break
    st: dict = {"description": desc, "headings": headings, "tables": tables, "faq": faq_from(lds),
                "breadcrumbs": [i.get("name") for b in ld_of(lds, "BreadcrumbList")
                                for i in b.get("itemListElement", [])],
                "links": links[:200]}
    if arts:
        a = arts[0]
        st.update({"headline": a.get("headline") or a.get("name"),
                   "date_modified": a.get("dateModified") or a.get("datePublished")})
    parts = slug.split("__")
    rsc = decode_rsc(html) if section in ("code", "gate", "irc", "cpheeo") else ""

    if section == "code":
        m = re.match(r"([A-Z]+)-(.+?)-((?:19|20)\d{2})$", parts[0]) if parts[0] != "_index" else None
        st["code_slug"] = parts[0]
        st["code_number"] = (f"{m.group(1)} {m.group(2).replace('-', ' ')}:{m.group(3)}" if m else parts[0])
        if len(parts) >= 3 and parts[1] == "clause":
            st["page_type"] = "clause"
            st["clause_id"] = parts[2].replace("-", ".")
            st["clause_title"] = title
            st["clause_text"] = text
            st["code_title"] = next((b for b in st["breadcrumbs"] if b and re.match(r"[A-Z]{2,5}[\s-]*\d", b)), None)
            st["related_clauses"] = sorted({l for l in links if "/clause/" in l and not l.endswith("/" + parts[2])})
        elif len(parts) == 2:
            st["page_type"] = parts[1]  # e.g. clauses index
            st["clauses"] = [l for l in links if "/clause/" in l]
        else:
            st["page_type"] = "code"
            st["code_title"] = (arts[0].get("headline") if arts else None) or title
            data = find_obj(rsc, '"quick_ref"') or find_obj(rsc, '"key_clauses"') or {}
            for k in ("key_values", "key_clauses", "key_tables", "key_formulas", "practical_notes",
                      "amendments", "quick_ref"):
                if k in data:
                    st[k] = data[k]
            clauses = []
            sec = soup.find(id="clauses")
            for a in (sec.find_all("a", href=True) if sec else []):
                if "/clause/" not in a["href"]:
                    continue
                divs = [clean_inline(d.get_text(" ", strip=True)) for d in a.find_all("div") if not d.find("div")]
                clauses.append({"clause_id": a["href"].rsplit("/", 1)[-1].replace("-", "."),
                                "clause_title": divs[0] if divs else None,
                                "summary": divs[1] if len(divs) > 1 else None, "url": BASE + a["href"]})
            st["clauses"] = clauses
    elif section == "prices":
        ds = (ld_of(lds, "Dataset") or [{}])[0]
        place = (ds.get("spatialCoverage") or {}).get("name") if isinstance(ds.get("spatialCoverage"), dict) else None
        st.update({"material": parts[0] if len(parts) == 2 else None,
                   "city_slug": parts[-1] if parts[0] != "_index" else None, "region": place,
                   "date": ds.get("temporalCoverage") or ds.get("dateModified"),
                   "source": (ds.get("creator") or {}).get("name") if isinstance(ds.get("creator"), dict) else None})
        items = []
        for t in tables:
            for d in rows_as_dicts(t):
                items.append({"item": pick(d, r"^item|^material|^city|^component|^grade|^type|^col0$") or next(iter(d.values()), None),
                              "spec": pick(d, r"spec|brand|grade|size"), "unit": pick(d, r"^unit"),
                              "rate": pick(d, r"price|rate|per_sqft|cost"), "row": d})
        st["items"] = items
    elif section == "steel":
        prod = (ld_of(lds, "Product") or [{}])[0]
        st.update({"section_name": prod.get("name") or title,
                   "standard": (CODE_RE.search(desc or "") or [None])[0] if desc else None,
                   "properties": [{"name": p.get("name"), "value": p.get("value"), "unit": p.get("unitText")}
                                  for p in prod.get("additionalProperty") or []]})
    elif section in ("sor", "rate-analysis"):
        comps, group = [], None
        for t in tables:
            if not t or not any(re.search(r"component|description|item|particular", h, re.I) for h in t[0]):
                continue
            hdr = [h.lower() for h in t[0]]
            for r in t[1:]:
                if len([c for c in r if c]) == 1:
                    group = r[0]
                    continue
                d = dict(zip(hdr, r))
                comps.append({"group": group, "component": r[0], "quantity": pick(d, r"qty|quantity"),
                              "unit": pick(d, r"^unit"), "rate": pick(d, r"^rate"), "amount": pick(d, r"amount|total")})
        tot = re.search(r"Total rate\s*\(([^)]*)\)\s*(₹[\d,]+(?:\s*[–-]\s*₹[\d,]+)?)\s*per\s+(\w+)", text)
        st.update({"item_code": parts[0] if parts[0] != "_index" else None, "item_description": title,
                   "unit": tot.group(3) if tot else None, "rate": tot.group(2) if tot else None,
                   "rate_city": tot.group(1) if tot else None, "components": comps,
                   "authority": (re.search(r"Authority:\s*([^\n]+?)(?:\s+Region:|\n)", text) or [None, None])[1],
                   "region": (re.search(r"Region:\s*([^\n]+?)(?:\s+Documents:|\n)", text) or [None, None])[1],
                   "documents": ext_docs})
    elif section == "term":
        dt = (ld_of(lds, "DefinedTerm") or [{}])[0]
        also = re.search(r"Also called\s+(.+?)(?:\n|Related on InfraLens)", text)
        st.update({"term": dt.get("name") or title, "definition": dt.get("description"),
                   "short_definition": None, "aliases": also.group(1).strip() if also else None,
                   "category": (dt.get("inDefinedTermSet") or {}).get("name")
                   if isinstance(dt.get("inDefinedTermSet"), dict) else None})
        if h1 and h1.find_next_sibling():
            st["short_definition"] = clean_inline(h1.find_next_sibling().get_text(" ", strip=True))[:300]
    elif section == "dcr":
        st.update({"topic": parts[0], "city": parts[1] if len(parts) > 1 else None,
                   "regulation": (re.search(r"Regulation:\s*([^\n]+?)(?:\s+Category:|\n)", text) or [None, None])[1],
                   "documents": ext_docs})
    else:  # thumbrules, handbook, knowledge, cpheeo, irc, gate, projects, boq ...
        st["codes_referenced"] = sorted({clean_inline(m.group(0)) for m in CODE_RE.finditer(text)
                                         if m.group(1).upper() in ("IS", "IRC", "NBC", "SP")})[:50]
        if ext_docs:
            st["documents"] = ext_docs
    return {"url": url, "section": section, "slug": slug, "title": title, "text": text, "structured": st}


# ================================================================================================
# Crawl
# ================================================================================================
def paths(section, slug):
    d = OUT / section
    return d / f"{slug}.html.gz", d / f"{slug}.json"


def write_json(section, slug, url, html, fetched_at):
    _, jp = paths(section, slug)
    try:
        doc = parse_page(section, slug, url, html)
    except Exception as e:  # keep HTML; record parse failure
        doc = {"url": url, "section": section, "slug": slug, "title": None, "text": "", "structured": {},
               "parse_error": repr(e)}
        with _lock:
            STATS["parse_errors"] += 1
    doc["fetched_at"] = fetched_at
    jp.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    return doc


def crawl_one(section, slug, url, robots, total, t0):
    hp, jp = paths(section, slug)
    if hp.exists() and jp.exists():
        with _lock:
            STATS["cached"] += 1
        return
    if robots and not robots.can_fetch(UA, url):
        with _lock:
            STATS["robots_skip"] += 1
        return
    time.sleep(random.uniform(0.3, 0.8))
    code, html = http_get(url)
    if code != 200 or not html:
        with _lock:
            STATS["failed"] += 1
            STATS[f"http_{code}"] += 1
        log(f"FAIL {code} {url}")
        return
    hp.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(hp, "wt", encoding="utf-8") as f:
        f.write(html)
    write_json(section, slug, url, html, now())
    with _lock:
        STATS["fetched"] += 1
        STATS[f"sec_{section}"] += 1
        n = STATS["fetched"]
    if n % 50 == 0:
        el = time.time() - t0
        done = STATS["fetched"] + STATS["cached"] + STATS["failed"]
        rate = STATS["fetched"] / el if el else 0
        eta = (total - done) / rate / 60 if rate else 0
        log(f"progress fetched={n} cached={STATS['cached']} failed={STATS['failed']} "
            f"retries={STATS['retries']} {done}/{total} rate={rate:.2f}/s eta={eta:.0f}min")


def coverage(inv, sections):
    rep = {}
    for s in sections:
        want = inv.get(s, {})
        have_h = sum(1 for sl in want if paths(s, sl)[0].exists())
        have_j = sum(1 for sl in want if paths(s, sl)[1].exists())
        rep[s] = {"inventory": len(want), "html": have_h, "json": have_j}
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sections", default=",".join(DEFAULT_SECTIONS))
    ap.add_argument("--limit", type=int, default=0, help="max pages per section")
    ap.add_argument("--offline", action="store_true", help="coverage report only")
    ap.add_argument("--reparse", action="store_true", help="rebuild JSON from cached HTML, no network")
    ap.add_argument("--no-discover", action="store_true", help="skip second pass over newly linked URLs")
    a = ap.parse_args()
    sections = [s.strip() for s in a.sections.split(",") if s.strip()]
    OUT.mkdir(parents=True, exist_ok=True)

    if a.offline or a.reparse:
        inv = build_inventory(sections, offline=True)
        if a.reparse:
            n = 0
            for s in sections:
                for hp in sorted((OUT / s).glob("*.html.gz")):
                    slug = hp.name[:-len(".html.gz")]
                    jp = paths(s, slug)[1]
                    old = json.loads(jp.read_text()) if jp.exists() else {}
                    url = old.get("url") or inv.get(s, {}).get(slug) or f"{BASE}/{s}/{slug.replace('__', '/')}"
                    with gzip.open(hp, "rt", encoding="utf-8") as f:
                        write_json(s, slug, url, f.read(), old.get("fetched_at") or now())
                    n += 1
            print(f"reparsed {n} pages (parse_errors={STATS['parse_errors']})")
        print(json.dumps(coverage(inv, sections), indent=1))
        return

    robots = urllib.robotparser.RobotFileParser(f"{BASE}/robots.txt")
    rc, rtxt = http_get(f"{BASE}/robots.txt")  # urllib's own fetch gets blocked -> would disallow all
    if rc == 200:
        robots.parse(rtxt.splitlines())
    else:
        robots = None
    inv = build_inventory(sections, offline=False)
    log(f"start sections={sections} inventory=" + json.dumps({s: len(inv.get(s, {})) for s in sections}))

    for rnd in range(2):
        jobs = []
        for s in sections:
            items = list(inv.get(s, {}).items())
            if a.limit:
                items = items[:a.limit]
            jobs += [(s, sl, u) for sl, u in items]
        t0 = time.time()
        with ThreadPoolExecutor(CONCURRENCY) as ex:
            futs = [ex.submit(crawl_one, s, sl, u, robots, len(jobs), t0) for s, sl, u in jobs]
            for f in as_completed(futs):
                if f.exception():
                    log(f"ERR {f.exception()!r}")
        if a.no_discover or a.limit or rnd == 1:
            break
        # discovery pass: same-section internal links not in inventory (e.g. clause pages)
        added = 0
        for s in sections:
            for jp in (OUT / s).glob("*.json"):
                try:
                    links = json.loads(jp.read_text()).get("structured", {}).get("links", [])
                except Exception:
                    continue
                for l in links:
                    sp = split_url(BASE + l)
                    if sp and sp[0] in sections and sp[1] not in inv[sp[0]]:
                        inv[sp[0]][sp[1]] = BASE + l.rstrip("/")
                        added += 1
        (OUT / "_inventory.json").write_text(json.dumps({s: dict(sorted(d.items())) for s, d in sorted(inv.items())}, indent=1))
        log(f"discovery pass: +{added} new URLs")
        if not added:
            break

    rep = coverage(inv, sections)
    (OUT / "_summary.json").write_text(json.dumps({"finished_at": now(), "stats": dict(STATS), "coverage": rep}, indent=1))
    log("DONE stats=" + json.dumps(dict(STATS)))
    log("coverage=" + json.dumps(rep))


if __name__ == "__main__":
    main()
