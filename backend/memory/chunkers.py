"""Parsers and structure-aware chunkers (bd-agent style).

- heading-path sections ("H1 > H2 > H3"), flush on a new heading or past ~1250 chars, no overlap
- whole-table chunks: rows never split mid-row; embed a summary + head of the table, keep the markdown
- template chunks: one per template section with hold points / mandatory flags, plus an overview
- IS-code clause chunks: one per clause, code + clause id in metadata and a spoken citation
- price / SOR rows as table chunks
Every chunk gets normalised entity tokens (RFI050 A102 C5 IS456 CL2642 ...) for exact-token BM25.
"""
from __future__ import annotations

import hashlib
import io
import re
import uuid
from dataclasses import dataclass, field

MAX_CHARS = 1250
MIN_CHARS = 30
TABLE_ROWS_PER_CHUNK = 30
_NS = uuid.UUID("6f1c3b8e-7d4a-4c1e-9a55-8e2f0b6a9d21")


@dataclass
class Chunk:
    text: str
    section: str = ""
    kind: str = "text"            # text|table|template|clause|record|profile
    page: int | None = None
    embed_text: str | None = None
    citation: str | None = None
    meta: dict = field(default_factory=dict)


# ============================================================== ids / hashing
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_text(s: str) -> str:
    return sha256_bytes((s or "").encode("utf-8"))


def doc_id_for(dataset: str, content_hash: str) -> str:
    return str(uuid.uuid5(_NS, f"{dataset}:{content_hash}"))


# ============================================================== entities
KNOWN_IS = {"456", "800", "875", "1786", "13920", "1893", "383", "2502", "10262", "516", "4926", "3370", "1343",
            "2911", "3764", "1200", "732", "1904", "2386", "269", "8112", "12269", "4990", "2062", "1080", "4082",
            "3812", "1199", "2720", "14687", "3696", "16700", "4014", "7969", "1239", "3025", "10500", "5816"}

_ENT = [
    ("rfi", re.compile(r"\bRFI[\s\-]?(\d{2,4})\b", re.I), lambda m: f"RFI{m.group(1)}"),
    ("template", re.compile(r"\b((?:QC|PMC|FMT)-[A-Z]{2,4}(?:-[A-Z]{2,4})?-\d{3})\b", re.I),
     lambda m: m.group(1).upper().replace("-", "")),
    ("permit", re.compile(r"\b(HWP|WAH|EXC|ELP|LFT|CSP|PTW)[\s\-]?(\d{3,5})\b", re.I),
     lambda m: f"{m.group(1).upper()}{m.group(2)}"),
    ("checklist", re.compile(r"\b(CL-[A-Z0-9]+(?:-[A-Z0-9]+)+)\b"), lambda m: m.group(1).replace("-", "")),
    ("code", re.compile(r"\b(IS|IRC|SP|NBC)\s?[:\-]?\s?(\d{2,5})\b"), lambda m: f"{m.group(1)}{m.group(2)}"),
    ("clause", re.compile(r"\b(?:Cl(?:ause)?s?\.?|clause)\s*(\d+(?:\.\d+)+)", re.I),
     lambda m: "CL" + m.group(1).replace(".", "")),
    ("drawing", re.compile(r"\b([A-Z])-(\d{3})\b"), lambda m: f"{m.group(1)}{m.group(2)}"),
    ("grid", re.compile(r"\b([A-H])-(\d{1,2})\b(?![\d.])"), lambda m: f"{m.group(1)}{m.group(2)}"),
    ("grade", re.compile(r"\b(M|Fe)\s?(\d{2,3})\b"), lambda m: f"{m.group(1).upper()}{m.group(2)}"),
    ("level", re.compile(r"\b(L\d{1,2})\b"), lambda m: m.group(1)),
]
KEY_ENTITY_TYPES = {"rfi", "template", "permit", "checklist", "code", "clause", "drawing", "grid"}


def normalize_query_ids(q: str) -> str:
    """Spoken/lower-case forms -> document forms: 'e-1' -> 'E-1', 'rfi 50' -> 'RFI-050', 'is 456' -> 'IS 456'."""
    s = q or ""
    s = re.sub(r"\b([a-hA-H])[\s\-]?(\d{1,2})\b(?=\s|$|[?,.])",
               lambda m: f"{m.group(1).upper()}-{m.group(2)}" if ("-" in m.group(0) or m.group(0)[1:].isdigit())
               else m.group(0), s)
    s = re.sub(r"\brfi[\s\-]?(\d{1,4})\b", lambda m: f"RFI-{int(m.group(1)):03d}", s, flags=re.I)
    s = re.sub(r"\b(is|irc|sp)\s?[:\-]?\s?(\d{2,5})\b",
               lambda m: f"{m.group(1).upper()} {m.group(2)}"
               if (m.group(1).lower() != "is" or m.group(2) in KNOWN_IS) else m.group(0), s, flags=re.I)
    s = re.sub(r"\b([asmcel])-?(\d{3})\b", lambda m: f"{m.group(1).upper()}-{m.group(2)}", s)
    s = re.sub(r"\bm\s?(\d{2})\b", lambda m: f"M{m.group(1)}", s)
    s = re.sub(r"\bfe\s?(\d{3})\b", lambda m: f"Fe{m.group(1)}", s, flags=re.I)
    s = re.sub(r"\bcl(?:ause)?\.?\s*(\d+(?:\.\d+)+)", lambda m: f"Cl. {m.group(1)}", s, flags=re.I)
    return s


def extract_entities(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen = set()
    for typ, rx, fn in _ENT:
        for m in rx.finditer(text or ""):
            tok = fn(m)
            if typ == "grid" and re.match(r"[A-Z]-\d{3}", m.group(0)):
                continue
            if (typ, tok) not in seen:
                seen.add((typ, tok))
                out.append((typ, tok))
    return out


def entity_string(text: str, limit: int = 60) -> str:
    return " ".join(t for _, t in extract_entities(text)[:limit])


# ============================================================== parsers -> blocks
def _clean(s: str) -> str:
    return re.sub(r"[ \t ]+", " ", (s or "").replace("\r", "")).strip()


def table_markdown(headers: list[str], rows: list[list[str]]) -> str:
    h = [_clean(str(x)) or f"col{i + 1}" for i, x in enumerate(headers)]
    lines = ["| " + " | ".join(h) + " |", "|" + "---|" * len(h)]
    for r in rows:
        cells = [_clean(str(c)).replace("|", "/") for c in list(r) + [""] * (len(h) - len(r))][:len(h)]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


_NUM_HEAD = re.compile(r"^(\d+(?:\.\d+){0,4})\.?\s+[A-Z(]")


def _heading_level(text: str) -> int | None:
    t = text.strip()
    if len(t) > 110 or t.endswith((".", ",", ";", ":")) and not _NUM_HEAD.match(t):
        return None
    m = _NUM_HEAD.match(t)
    if m and len(t) < 100:
        return min(m.group(1).count(".") + 1, 4)
    letters = re.sub(r"[^A-Za-z]", "", t)
    if len(letters) >= 4 and letters.isupper() and len(t) < 80:
        return 1
    return None


def parse_markdown(text: str) -> list[dict]:
    blocks: list[dict] = []
    para: list[str] = []
    table: list[str] = []

    def flush_para():
        if para:
            blocks.append({"type": "para", "text": _clean(" ".join(para))})
            para.clear()

    def flush_table():
        if not table:
            return
        rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in table
                if not re.match(r"^\s*\|?\s*:?-{2,}", ln)]
        if rows:
            blocks.append({"type": "table", "headers": rows[0], "rows": rows[1:]})
        table.clear()

    for ln in (text or "").splitlines():
        s = ln.rstrip()
        if s.lstrip().startswith("|") and s.count("|") >= 2:
            flush_para()
            table.append(s)
            continue
        flush_table()
        m = re.match(r"^(#{1,6})\s+(.*)", s)
        if m:
            flush_para()
            blocks.append({"type": "heading", "level": len(m.group(1)), "text": _clean(m.group(2))})
        elif not s.strip():
            flush_para()
        elif s.lstrip().startswith(("- ", "* ", "• ")):
            flush_para()
            blocks.append({"type": "para", "text": _clean(s.lstrip()[2:])})
        else:
            lvl = _heading_level(s) if len(s) < 100 and not para else None
            if lvl:
                flush_para()
                blocks.append({"type": "heading", "level": lvl, "text": _clean(s)})
            else:
                para.append(s.strip())
    flush_para()
    flush_table()
    return blocks


def parse_pdf(data: bytes) -> list[dict]:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=data, filetype="pdf")
    sizes: list[float] = []
    pages = []
    for page in doc:
        d = page.get_text("dict")
        tabs = []
        try:
            for t in page.find_tables().tables:
                tabs.append((fitz.Rect(t.bbox), t.extract()))
        except Exception:  # noqa: BLE001
            pass
        lines = []
        h = page.rect.height
        for b in d.get("blocks", []):
            for ln in b.get("lines", []):
                spans = ln.get("spans", [])
                txt = _clean("".join(s.get("text", "") for s in spans))
                if not txt:
                    continue
                y0 = ln["bbox"][1]
                if y0 < 0.04 * h or y0 > 0.96 * h and len(txt) < 40:
                    continue  # running header / footer / page number
                if any(r.contains(fitz.Rect(ln["bbox"])) for r, _ in tabs):
                    continue
                size = max(s.get("size", 0) for s in spans)
                bold = any("bold" in s.get("font", "").lower() or s.get("flags", 0) & 16 for s in spans)
                sizes.append(size)
                lines.append((y0, txt, size, bold))
        pages.append((lines, tabs))
    body = sorted(sizes)[len(sizes) // 2] if sizes else 10
    blocks: list[dict] = []
    for pno, (lines, tabs) in enumerate(pages, start=1):
        items = [(y, "line", (t, s, b)) for y, t, s, b in lines] + [(r.y0, "table", rows) for r, rows in tabs]
        for _, kind, payload in sorted(items, key=lambda x: x[0]):
            if kind == "table":
                rows = [[c or "" for c in r] for r in payload if any(c for c in r)]
                if rows:
                    blocks.append({"type": "table", "headers": rows[0], "rows": rows[1:], "page": pno})
                continue
            txt, size, bold = payload
            lvl = None
            if len(txt) < 110:
                if size >= body * 1.35:
                    lvl = 1
                elif size >= body * 1.15 or (bold and len(txt) < 80 and not txt.endswith(".")):
                    lvl = 2
                lvl = _heading_level(txt) or lvl
            if lvl:
                blocks.append({"type": "heading", "level": lvl, "text": txt, "page": pno})
            elif blocks and blocks[-1]["type"] == "para" and blocks[-1].get("page") == pno \
                    and not blocks[-1]["text"].endswith((".", ":", ";")):
                blocks[-1]["text"] += " " + txt
            else:
                blocks.append({"type": "para", "text": txt, "page": pno})
    return blocks


def parse_docx(data: bytes) -> list[dict]:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(io.BytesIO(data))
    blocks: list[dict] = []
    for el in d.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(el, d)
            txt = _clean(p.text)
            if not txt:
                continue
            style = (p.style.name if p.style is not None else "") or ""
            m = re.match(r"Heading\s*(\d)", style)
            if m or style == "Title":
                blocks.append({"type": "heading", "level": int(m.group(1)) if m else 1, "text": txt})
            else:
                blocks.append({"type": "para", "text": txt})
        elif tag == "tbl":
            t = Table(el, d)
            rows = []
            for r in t.rows:
                cells = []
                for c in r.cells:
                    v = _clean(c.text)
                    if not cells or cells[-1] != v:  # merged cells repeat
                        cells.append(v)
                rows.append(cells)
            if rows:
                blocks.append({"type": "table", "headers": rows[0], "rows": rows[1:]})
    return blocks


def parse_tabular(data: bytes, filename: str) -> list[dict]:
    import pandas as pd

    blocks: list[dict] = []
    if filename.lower().endswith((".csv", ".tsv")):
        sep = "\t" if filename.lower().endswith(".tsv") else ","
        sheets = {"Sheet1": pd.read_csv(io.BytesIO(data), sep=sep, header=None, dtype=str, keep_default_na=False)}
    else:
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None, dtype=str)
    for name, df in sheets.items():
        df = df.fillna("").astype(str)
        df = df.loc[:, (df != "").any(axis=0)]
        df = df[(df != "").any(axis=1)]
        if df.empty:
            continue
        rows = df.values.tolist()
        hdr_i = next((i for i, r in enumerate(rows[:10]) if sum(1 for c in r if c.strip()) >= max(2, len(r) // 2)), 0)
        blocks.append({"type": "heading", "level": 1, "text": str(name)})
        blocks.append({"type": "table", "name": str(name), "headers": rows[hdr_i], "rows": rows[hdr_i + 1:]})
    return blocks


def parse_html(data: bytes | str) -> list[dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data, "lxml")
    for t in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "form"]):
        t.decompose()
    blocks: list[dict] = []
    root = soup.body or soup
    for el in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "table", "pre"]):
        if el.find_parent("table") is not None or (el.name == "p" and el.find_parent("li") is not None):
            continue
        if el.name == "table":
            rows = [[_clean(c.get_text(" ")) for c in tr.find_all(["th", "td"])] for tr in el.find_all("tr")]
            rows = [r for r in rows if any(r)]
            if rows:
                blocks.append({"type": "table", "headers": rows[0], "rows": rows[1:]})
        elif el.name.startswith("h"):
            txt = _clean(el.get_text(" "))
            if txt:
                blocks.append({"type": "heading", "level": int(el.name[1]), "text": txt})
        else:
            txt = _clean(el.get_text(" "))
            if txt:
                blocks.append({"type": "para", "text": txt})
    return blocks


def parse_any(filename: str, data: bytes) -> list[dict]:
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext == "pdf":
        return parse_pdf(data)
    if ext in ("docx",):
        return parse_docx(data)
    if ext in ("xlsx", "xlsm", "xls", "csv", "tsv"):
        return parse_tabular(data, filename)
    if ext in ("html", "htm"):
        return parse_html(data)
    return parse_markdown(data.decode("utf-8", errors="replace"))


# ============================================================== blocks -> chunks
_NUMS = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def table_chunks(headers: list, rows: list[list], *, title: str, section: str, name: str | None = None,
                 page: int | None = None, citation: str | None = None) -> list[Chunk]:
    name = name or (section.split(" > ")[-1] if section else None) or (f"Table on page {page}" if page else "Table")
    out: list[Chunk] = []
    parts = [rows[i:i + TABLE_ROWS_PER_CHUNK] for i in range(0, max(len(rows), 1), TABLE_ROWS_PER_CHUNK)]
    for pi, part in enumerate(parts):
        md = table_markdown(headers, part)
        nums = _NUMS.findall(md)[:50]
        label = name + (f" (rows {pi * TABLE_ROWS_PER_CHUNK + 1}-{pi * TABLE_ROWS_PER_CHUNK + len(part)})"
                        if len(parts) > 1 else "")
        summary = (f"{title} | {label} | Cols: {', '.join(_clean(str(h)) for h in headers)[:300]} | "
                   f"{len(part)} rows | Values: {' '.join(nums[:30])}")
        text = f"{label}\n{md}"
        out.append(Chunk(text=text, section=section or name, kind="table", page=page,
                         embed_text=f"{summary}\n{md[:1500]}", citation=citation,
                         meta={"table_name": label, "rows": len(part), "numbers": nums}))
    return out


def blocks_to_chunks(blocks: list[dict], title: str, *, citation_prefix: str | None = None,
                     max_chars: int = MAX_CHARS) -> list[Chunk]:
    stack: list[tuple[int, str]] = []
    buf: list[str] = []
    buf_page: int | None = None
    out: list[Chunk] = []

    def section() -> str:
        return " > ".join(t for _, t in stack)

    def cite(sec: str) -> str:
        base = citation_prefix or f"per {title}"
        leaf = sec.split(" > ")[-1] if sec else ""
        return f"{base}, {leaf}" if leaf and leaf.lower() != title.lower() else base

    def flush():
        nonlocal buf_page
        txt = "\n".join(buf).strip()
        buf.clear()
        if len(txt) >= MIN_CHARS:
            sec = section()
            out.append(Chunk(text=txt, section=sec, kind="text", page=buf_page,
                             embed_text=f"{title}\n{sec}\n{txt}"[:2000], citation=cite(sec)))
        buf_page = None

    for b in blocks:
        if b["type"] == "heading":
            flush()
            lvl = b.get("level", 1)
            while stack and stack[-1][0] >= lvl:
                stack.pop()
            stack.append((lvl, b["text"][:120]))
        elif b["type"] == "table":
            flush()
            out += table_chunks(b.get("headers") or [], b.get("rows") or [], title=title, section=section(),
                                name=b.get("name"), page=b.get("page"), citation=cite(section()))
        else:
            t = b.get("text", "")
            if buf and (sum(len(x) for x in buf) + len(t) > max_chars or (b.get("page") and buf_page
                                                                          and b["page"] != buf_page and
                                                                          sum(len(x) for x in buf) > max_chars // 2)):
                flush()
            if len(t) > max_chars * 1.6:  # a single giant paragraph: sentence-split
                for piece in _split_sentences(t, max_chars):
                    buf.append(piece)
                    buf_page = buf_page or b.get("page")
                    flush()
                continue
            buf.append(t)
            buf_page = buf_page or b.get("page")
    flush()
    return out


def _split_sentences(t: str, max_chars: int) -> list[str]:
    parts, cur = [], ""
    for s in re.split(r"(?<=[.;!?])\s+", t):
        if cur and len(cur) + len(s) > max_chars:
            parts.append(cur)
            cur = ""
        cur = (cur + " " + s).strip()
        while len(cur) > max_chars * 1.5:
            parts.append(cur[:max_chars])
            cur = cur[max_chars:]
    if cur:
        parts.append(cur)
    return parts


# ============================================================== domain chunkers
def template_chunks(t: dict, fields: list[dict], codes: list[str], overview_extra: str = "") -> list[Chunk]:
    tid, title = t["template_id"], t["title"]
    head = f"{tid} {title}"
    secs: dict[str, list[dict]] = {}
    for f in sorted(fields, key=lambda f: f.get("ordinal") or 0):
        secs.setdefault(f.get("section") or "Fields", []).append(f)
    holds = [f for f in fields if f.get("is_hold_point")]
    mand = [f for f in fields if f.get("is_mandatory")]
    sec_summary = "; ".join(
        f"{s} ({len(v)} items{', ' + str(sum(1 for x in v if x.get('is_hold_point'))) + ' hold points' if any(x.get('is_hold_point') for x in v) else ''})"
        for s, v in secs.items())
    ov = (f"TEMPLATE {tid} — {title} [{t.get('type')}] · {t.get('source_id', '').upper()} library · family "
          f"{t.get('family')}.\n" + (f"Codes: {', '.join(codes)}\n" if codes else "")
          + (f"{t.get('description')}\n" if t.get("description") else "")
          + (f"{overview_extra.strip()}\n" if overview_extra else "")
          + (f"Sections: {sec_summary}\n" if secs else "")
          + (f"{len(fields)} fields, {len(holds)} hold points, {len(mand)} mandatory." if fields else ""))
    out = [Chunk(text=ov.strip(), section=f"{head} — Overview", kind="template",
                 citation=f"per template {tid}, {title}", meta={"template_id": tid, "part": "overview"})]
    for s, items in secs.items():
        lines = []
        for f in items:
            flags = (" [HOLD POINT]" if f.get("is_hold_point") else "") + (" [MANDATORY]" if f.get("is_mandatory") else "")
            ln = f"{(f.get('item_ref') or '').strip()} {f['label']}".strip() + flags
            if f.get("unit"):
                ln += f" (unit {f['unit']})"
            if f.get("requirement"):
                ln += f" | Requirement: {f['requirement']}"
            if f.get("code_ref"):
                ln += f" | Code: {f['code_ref']}"
            if f.get("acceptance"):
                ln += f" | Acceptance: {f['acceptance']}"
            lines.append(ln)
        body, part = [], 1
        for ln in lines + [None]:
            if ln is None or (body and sum(len(x) for x in body) + len(ln) > 1400):
                if body:
                    label = f"{head} — {s}" + (f" (part {part})" if part > 1 or ln is not None else "")
                    txt = label + "\n" + "\n".join(body)
                    out.append(Chunk(text=txt, section=f"{head} — {s}", kind="template",
                                     embed_text=f"{title} checklist — {s}\n" + "\n".join(body),
                                     citation=f"per template {tid}, {s} section",
                                     meta={"template_id": tid, "part": s}))
                    part += 1
                body = []
            if ln is not None:
                body.append(ln)
    if holds or mand:
        txt = (f"{head} — Hold points and mandatory checks\n"
               + (f"Hold points ({len(holds)}): " + "; ".join(f"{(h.get('item_ref') or '').strip()} {h['label']}".strip()
                                                            for h in holds) + "\n" if holds else "")
               + (f"Mandatory ({len(mand)}): " + "; ".join(m["label"] for m in mand[:40]) if mand else ""))
        out.append(Chunk(text=txt.strip(), section=f"{head} — Hold points", kind="template",
                         citation=f"per template {tid} hold points", meta={"template_id": tid, "part": "hold_points"}))
    return out


_CLAUSE_LINE = re.compile(r"^\s*(?:#{1,6}\s*)?(?:Cl(?:ause)?\.?\s*)?(\d{1,3}(?:\.\d{1,3}){1,4})\s+(.{3,160})$")


def clause_chunks(text: str, code: str, title: str) -> list[Chunk]:
    """One chunk per clause (lines starting '26.4 Nominal cover ...'); falls back to sections."""
    out: list[Chunk] = []
    cur_id, cur_head, buf = None, "", []

    def flush():
        body = "\n".join(buf).strip()
        if cur_id and len(body) + len(cur_head) >= MIN_CHARS:
            for i, piece in enumerate(_split_sentences(body, 1600) if len(body) > 1800 else [body]):
                out.append(Chunk(text=f"{code} Cl. {cur_id} {cur_head}\n{piece}".strip(),
                                 section=f"{code} Cl. {cur_id} {cur_head}".strip(), kind="clause",
                                 citation=f"per {code} clause {cur_id}",
                                 meta={"code": code, "clause": cur_id, "part": i}))

    for ln in (text or "").splitlines():
        m = _CLAUSE_LINE.match(ln)
        if m:
            flush()
            cur_id, cur_head, buf = m.group(1), m.group(2).strip(), []
        else:
            buf.append(ln)
    flush()
    if not out:
        out = blocks_to_chunks(parse_markdown(text), title, citation_prefix=f"per {code}")
        for c in out:
            c.kind = "clause" if c.kind == "text" else c.kind
            c.meta.setdefault("code", code)
    return out


def split_text_chunks(text: str, title: str, *, citation: str | None = None, kind: str = "text") -> list[Chunk]:
    chunks = blocks_to_chunks(parse_markdown(text), title, citation_prefix=citation)
    for c in chunks:
        if c.kind == "text":
            c.kind = kind
    return chunks
