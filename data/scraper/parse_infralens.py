"""
Parsers for cached infralens.in pages.

infralens.in is a Next.js App Router site; each page streams its React Server Component payload via
`self.__next_f.push([1,"..."])` script tags. That payload embeds the complete template JSON
(header, project_fields, sections/items or columns, signoff with required flags, metadata, codes)
plus, on index pages, the `families` inventory. We decode it here rather than scraping the rendered
DOM, which only shows a truncated preview ("Showing 35 of 56").
"""
from __future__ import annotations

import json
import re

_PUSH = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', re.S)
_DEC = json.JSONDecoder()


def fix_mojibake(text: str) -> str:
    """Pages fetched over plain HTTP without a charset header may be latin-1-decoded UTF-8."""
    if text and ("â€" in text or "Ã" in text or "â\x80" in text):
        try:
            return text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return text


def decode_rsc(html: str) -> str:
    html = fix_mojibake(html)
    out = []
    for c in _PUSH.findall(html or ""):
        try:
            out.append(json.loads('"' + c + '"'))
        except json.JSONDecodeError:
            pass
    return "".join(out)


def _text_rows(s: str) -> dict:
    """RSC 'T' rows: `<id>:T<hexlen>,<text>` hold long strings referenced as "$<id>"."""
    rows = {}
    for m in re.finditer(r'(?:^|\n)([0-9a-f]+):T([0-9a-f]+),', s):
        start = m.end()
        n = int(m.group(2), 16)
        b = s[start:start + n * 2].encode("utf-8")[:n]
        rows[m.group(1)] = b.decode("utf-8", "ignore")
    return rows


def _resolve(obj, rows):
    if isinstance(obj, str):
        m = re.fullmatch(r"\$([0-9a-f]+)", obj)
        if m and m.group(1) in rows:
            return rows[m.group(1)]
        if obj == "$undefined":
            return None
        return obj
    if isinstance(obj, list):
        return [_resolve(x, rows) for x in obj]
    if isinstance(obj, dict):
        return {k: _resolve(v, rows) for k, v in obj.items()}
    return obj


def extract_families(rsc: str) -> list:
    i = rsc.find('"families":[')
    if i < 0:
        return []
    fams, _ = _DEC.raw_decode(rsc, i + len('"families":'))
    return fams


def extract_template(rsc: str, template_id: str | None = None) -> dict | None:
    """Largest embedded JSON object whose template_id matches (the full template definition)."""
    rows = _text_rows(rsc)
    best, best_len = None, -1
    pat = r'\{"template_id":"' + (re.escape(template_id) if template_id else r'[A-Z]+-')
    for m in re.finditer(pat, rsc):
        try:
            obj, end = _DEC.raw_decode(rsc, m.start())
        except json.JSONDecodeError:
            continue
        ln = end - m.start()
        if ln > best_len:
            best, best_len = obj, ln
    return _resolve(best, rows) if best is not None else None


def extract_jsonld(html: str) -> list:
    out = []
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html or "", re.S):
        try:
            d = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        out.extend(d if isinstance(d, list) else [d])
    return out


# ================================================================================================
# Normalisation: codes, types, fields
# ================================================================================================
TYPE_MAP = {
    "checklist": "Checklist", "form": "Form", "register": "Register", "test-report": "Test Report",
    "test_report": "Test Report", "plan": "Plan", "permit": "Permit", "schedule": "Schedule",
    "report": "Report", "log": "Log", "matrix": "Matrix", "document": "Document", "doc": "Document",
    "certificate": "Certificate", "chart": "Chart", "billing": "Billing", "mom": "MOM",
}


def norm_type(site_type: str | None, template_id: str) -> str:
    seg = template_id.split("-")[2] if template_id.count("-") >= 3 else ""
    if seg in ("PRM", "PMT"):
        return "Permit"
    t = (site_type or "").strip().lower()
    return TYPE_MAP.get(t, t.replace("-", " ").title() or "Document")


_CODE_PATTERNS = [
    (r"\bIS\s*/?\s*ISO\s*(\d{3,5})", lambda m: f"IS/ISO {m.group(1)}"),
    (r"\bIS\s*:?\s*(\d{2,5})(?:\s*\(\s*Part\s*([\dIVX]+)\s*\))?", lambda m: f"IS {m.group(1)}" + (f" (Part {m.group(2)})" if m.group(2) else "")),
    (r"\bIRC\s*:?\s*(?:SP\s*:?\s*)?(\d{1,3})", lambda m: ("IRC:SP " if "SP" in m.group(0) else "IRC ") + m.group(1)),
    (r"\bISO\s*(\d{3,5})", lambda m: f"ISO {m.group(1)}"),
    (r"\bNBC\b(?:\s*(\d{4}))?", lambda m: "NBC 2016"),
    (r"\bFIDIC\b(?:\s*(Red|Yellow|Silver|Green|White|Pink|Gold|Emerald)\s*Book)?", lambda m: f"FIDIC {m.group(1)} Book" if m.group(1) else "FIDIC"),
    (r"\bRERA\b", lambda m: "RERA 2016"),
    (r"\bBOCW\b", lambda m: "BOCW Act 1996"),
    (r"\bCPWD\s*(Works Manual|Specifications?|Spec|DSR|DAR|Manual|Guidelines)?", lambda m: {
        None: "CPWD", "Works Manual": "CPWD Works Manual", "Manual": "CPWD Works Manual",
        "Specification": "CPWD Specifications", "Specifications": "CPWD Specifications", "Spec": "CPWD Specifications",
        "DSR": "CPWD DSR", "DAR": "CPWD DAR", "Guidelines": "CPWD Guidelines"}[m.group(1)]),
    (r"\bGFR\b", lambda m: "GFR 2017"),
    (r"\bMoRTH\b|\bMORTH\b", lambda m: "MoRTH Specifications"),
    (r"\bOISD\s*-?\s*(?:STD\s*-?\s*)?(\d+)", lambda m: f"OISD {m.group(1)}"),
    (r"\bCPHEEO\b", lambda m: "CPHEEO Manual"),
    (r"\bFactories Act\b", lambda m: "Factories Act 1948"),
    (r"\bIndian Electricity Rules\b|\bCEA\b", lambda m: "CEA Regulations"),
    (r"\bASTM\s*([A-Z]\s?\d+)", lambda m: f"ASTM {m.group(1).replace(' ', '')}"),
]


def extract_codes(text: str) -> list[str]:
    if not text:
        return []
    out = []
    for pat, fn in _CODE_PATTERNS:
        for m in re.finditer(pat, text):
            try:
                c = fn(m)
            except Exception:  # noqa: BLE001
                continue
            if c and c not in out:
                out.append(c)
    # "IS/ISO 9001" also matches ISO 9001 — keep both (harmless); drop bogus IS numbers (<10)
    return [c for c in out if not re.fullmatch(r"IS \d", c)]


def clause_ref(code_ref: str | None, requirement: str | None) -> str | None:
    """'IS 456:2000' + 'Cl. 26.4.1 — ...' -> 'IS 456 Cl. 26.4.1'."""
    code_ref = (code_ref or "").strip()
    req = requirement or ""
    m = re.search(r"\b(?:Cl(?:ause)?\.?|Sub-clause|Section|Table|Annex)\s*[\w.()\-, ]{1,25}?(?=\s+—|\s+-\s|$|;)", req)
    clause = m.group(0).strip().rstrip(",") if m else None
    base = re.sub(r":\s*\d{4}\b", "", code_ref).strip() if code_ref else ""
    if base and clause:
        return f"{base} {clause}"[:120]
    if base:
        return base[:120]
    if clause:
        return clause[:120]
    return None


_KIND_BY_TYPE = {"text": "text", "textarea": "text", "number": "number", "date": "date", "datetime": "date",
                 "time": "text", "select": "select", "checkbox": "yes_no", "yes_no": "yes_no",
                 "signature": "signature"}


def kind_from_label(label: str, declared: str | None = None) -> str:
    if declared and declared in _KIND_BY_TYPE and declared not in ("text", "textarea"):
        return _KIND_BY_TYPE[declared]
    l = label.lower()
    if re.search(r"\bsign(ature|ed)?\b|\bsign\s*/|name\s*/\s*sign", l):
        return "signature"
    if re.search(r"\b(date|dated|valid until|valid from|period)\b", l):
        return "date"
    if re.search(r"\(yes/no|\byes/no\b|\(y/n\)", l):
        return "yes_no"
    if re.search(r"\(y/n(/na)?\)", l):
        return "yes_no"
    if (re.search(r"\((?:[\w .\-]+/){2,}[\w .\-]+\)", l) and not re.search(r"location|name|ref|address", l)) \
            or re.search(r"\bstatus\b|\burgency\b|\btype\b", l):
        return "select"
    if re.search(r"location|name|\bby\b|description|remarks|details|address", l):
        return "text"
    if re.search(r"\b(qty|quantity|amount|rate|nos\.?|count|volume|weight|length|area|%|percentage|value|\(m3\)|\(m³\)|\(mm\)|\(kg\)|\(₹\)|rs\.?)\b", l):
        return "number"
    return declared and _KIND_BY_TYPE.get(declared, "text") or "text"


def unit_from_label(label: str) -> str | None:
    m = re.search(r"\((mm|m|cm|m²|m2|sqm|m³|m3|cum|kg|t|MT|nos|%|₹|Rs|MPa|N/mm²|kN|°C|hrs?|days?|lpm|bar|kPa|Ω|kW|kVA|V|A)\)", label)
    return m.group(1) if m else None


HOLD_RE = re.compile(r"hold[\s-]?point|witness point|\bhold\b.*\b(release|approval)|release(d)? for (pour|concreting)|"
                     r"approved for pour|pour card|permit to pour|stop[\s-]work|do not proceed|shall not proceed|"
                     r"must not (proceed|start|commence)|prior approval|before (pour|concreting).*(approv|sign)", re.I)
MANDATORY_RE = re.compile(r"\bmandatory\b|\bcompulsory\b|\bmust\b|\bnon-negotiable\b|\bat all times\b", re.I)
PERMIT_CRITICAL_RE = re.compile(r"fire[\s-]?watch|gas test|\bLEL\b|oxygen|O2\b|isolation|lock[\s-]?out|\bLOTO\b|"
                                r"harness|anchor|life ?line|shoring|benching|sloping|standby|attendant|rescue|"
                                r"atmospher|ventilat|extinguisher|barricad|underground (utilit|service)|cable detect", re.I)


def _is_permit(tpl: dict, template_id: str) -> bool:
    seg = template_id.split("-")[2] if template_id.count("-") >= 3 else ""
    name = (tpl.get("template_name") or "").lower()
    return seg in ("PRM", "PMT") or "permit" in name


def template_fields(tpl: dict, template_id: str) -> list[dict]:
    """Flatten an embedded template definition into template_fields rows."""
    rows: list[dict] = []
    permit = _is_permit(tpl, template_id)
    is_checklist_like = (tpl.get("template_type") or "").lower() in ("checklist",) or "checklist" in (tpl.get("template_name") or "").lower()

    def add(section, label, kind="text", unit=None, mand=0, hold=0, code=None, item_ref=None, req=None, acc=None):
        label = re.sub(r"\s+", " ", str(label or "")).strip()
        if not label:
            return
        rows.append({"section": section, "ordinal": len(rows) + 1, "label": label[:500], "field_kind": kind,
                     "unit": unit, "is_mandatory": int(bool(mand)), "is_hold_point": int(bool(hold)),
                     "code_ref": code, "item_ref": item_ref, "requirement": req, "acceptance": acc})

    for grp, sec in (("project_fields", "Header"), ("detail_fields", "Details")):
        for f in tpl.get(grp) or []:
            if not isinstance(f, dict):
                continue
            lab = f.get("label") or f.get("field_id")
            kind = kind_from_label(lab or "", f.get("type"))
            mand = f.get("required") is True or (permit and grp == "project_fields" and
                                                  re.search(r"permit no|location|valid|date", (lab or "").lower()))
            add(sec, lab, kind, unit_from_label(lab or ""), mand, 0, None, f.get("field_id"),
                acc=", ".join(f.get("options") or []) or None)

    for s in tpl.get("sections") or []:
        if not isinstance(s, dict):
            continue
        stitle = (s.get("section_title") or s.get("title") or s.get("section_id") or "").strip()
        for it in s.get("items") or []:
            if isinstance(it, str):
                add(stitle, it, "check_item")
                continue
            lab = it.get("checkpoint") or it.get("label") or it.get("item") or it.get("description")
            req = it.get("is_requirement") or it.get("requirement")
            acc = it.get("acceptance_criteria") or it.get("acceptance")
            mcol = re.match(r"^\s*Column\s+\d+\s*:\s*(.+?)\s+[—–-]\s+(.+)$", lab or "")
            if mcol:  # register column definition -> a real register column
                cname = mcol.group(1).strip()
                cname_t = cname.title() if cname.isupper() else cname
                add("Register columns", cname_t, kind_from_label(cname), unit_from_label(cname),
                    bool(re.search(r"\bno\b|date|location|area|observation|status", cname.lower())), 0,
                    clause_ref(it.get("is_code_ref"), req), it.get("item_id"), req, mcol.group(2).strip())
                continue
            blob = " ".join(str(x) for x in (lab, req, acc) if x)
            opts = [o.upper() for o in (it.get("status_options") or [])]
            hold = bool(HOLD_RE.search(blob))
            if permit and PERMIT_CRITICAL_RE.search(blob):
                hold = True
            mand = permit or hold or bool(MANDATORY_RE.search(blob)) or (opts and "NA" not in opts)
            code = clause_ref(it.get("is_code_ref") or it.get("code_ref"), req)
            add(stitle, lab, "check_item", unit_from_label(lab or ""), mand, hold, code, it.get("item_id"), req, acc)
        # register / table style sections
        for col in s.get("columns") or []:
            lab = col.get("label") if isinstance(col, dict) else col
            add(stitle, lab, kind_from_label(str(lab), col.get("type") if isinstance(col, dict) else None),
                unit_from_label(str(lab)))

    for col in tpl.get("columns") or []:
        lab = col.get("label") if isinstance(col, dict) else col
        add("Register columns", lab, kind_from_label(str(lab), col.get("type") if isinstance(col, dict) else None),
            unit_from_label(str(lab)))

    so = tpl.get("signoff") or {}
    if isinstance(so, dict):
        if so.get("verdict_options") and not any((f.get("field_id") == "verdict") for f in so.get("fields") or [] if isinstance(f, dict)):
            add("Sign-off", "Overall Verdict", "select", mand=1, hold=is_checklist_like,
                acc=" | ".join(so["verdict_options"]))
        for f in so.get("fields") or []:
            if not isinstance(f, dict):
                continue
            lab = f.get("label") or f.get("field_id") or ""
            kind = "signature" if re.search(r"sign|approval", lab, re.I) else kind_from_label(lab, f.get("type"))
            verdict = f.get("field_id") == "verdict" or "verdict" in lab.lower()
            hold = (verdict and is_checklist_like) or bool(re.search(r"approval \(if hold\)|release", lab, re.I))
            add("Sign-off", lab, "select" if verdict else kind, None,
                f.get("required") is True or verdict or (permit and kind == "signature"), hold,
                acc=" | ".join(so.get("verdict_options") or []) if verdict else None)

    # PMC shape: key_sections [{section_title, fields:[str]}]
    for s in tpl.get("key_sections") or []:
        if not isinstance(s, dict):
            continue
        stitle = (s.get("section_title") or "").strip()
        sec_l = stitle.lower()
        for lab in s.get("fields") or []:
            lab_s = str(lab)
            l = lab_s.lower()
            kind = kind_from_label(lab_s)
            question = lab_s.rstrip().endswith("?") or bool(re.search(r"\(y/n(/na)?\)", l))
            if question and not re.search(r"header|project info", sec_l):
                kind = "check_item"  # checklist question on a PMC form/permit ("... ? (Y/N)")
            mand = bool(re.search(r"\b(no\.|number|date|location|gridline|drawing no|revision|rev\.? no|status|raised by|subject)\b", l)) \
                or (permit and (kind in ("check_item", "signature") or bool(re.search(r"permit no|validity|location|fire watch", l)))) \
                or bool(MANDATORY_RE.search(lab_s))
            hold = bool(HOLD_RE.search(lab_s)) or (permit and bool(PERMIT_CRITICAL_RE.search(lab_s)))
            add(stitle, lab_s, kind, unit_from_label(lab_s), mand, hold, None)
    return rows


def render_template_text(tpl: dict) -> list[tuple[str, str]]:
    """Readable (section_title, text) blocks for retrieval chunks, derived from the embedded JSON."""
    blocks = []
    md = tpl.get("metadata") or {}
    head = []
    for k in ("when_to_use", "frequency"):
        if md.get(k):
            head.append(f"{k.replace('_', ' ').title()}: {md[k]}")
    if md.get("who_uses"):
        head.append("Who uses: " + ", ".join(md["who_uses"]))
    if tpl.get("description"):
        head.append(tpl["description"])
    for w in tpl.get("when_used") or []:
        head.append(f"When used: {w}")
    if head:
        blocks.append(("Overview", "\n".join(head)))
    for s in tpl.get("sections") or []:
        if not isinstance(s, dict):
            continue
        lines = []
        for it in s.get("items") or []:
            if isinstance(it, str):
                lines.append(f"- {it}")
                continue
            parts = [f"{it.get('item_id', '')} {it.get('checkpoint') or it.get('label') or ''}".strip()]
            if it.get("is_requirement"):
                parts.append(f"Requirement: {it['is_requirement']}" + (f" ({it['is_code_ref']})" if it.get("is_code_ref") else ""))
            if it.get("acceptance_criteria"):
                parts.append(f"Acceptance: {it['acceptance_criteria']}")
            lines.append(" | ".join(parts))
        for col in s.get("columns") or []:
            lines.append(f"- column: {col.get('label') if isinstance(col, dict) else col}")
        blocks.append((s.get("section_title") or "", "\n".join(lines)))
    for s in tpl.get("key_sections") or []:
        if isinstance(s, dict):
            blocks.append((s.get("section_title") or "", "Fields: " + "; ".join(map(str, s.get("fields") or []))))
    so = tpl.get("signoff") or {}
    if isinstance(so, dict) and (so.get("fields") or so.get("verdict_options")):
        t = "Sign-off: " + "; ".join((f.get("label", "") + (" (required)" if f.get("required") else ""))
                                     for f in so.get("fields") or [] if isinstance(f, dict))
        if so.get("verdict_options"):
            t += "\nVerdict options: " + " | ".join(so["verdict_options"])
        blocks.append(("Sign-off", t))
    for lg in tpl.get("status_legend") or []:
        if isinstance(lg, dict) and lg.get("code") == "HOLD":
            blocks.append(("Status legend", "HOLD = " + lg.get("meaning", "")))
    for k in ("compliance_notes",):
        if tpl.get(k):
            blocks.append(("Compliance notes", "\n".join(f"- {x}" for x in tpl[k])))
    if tpl.get("sample_filled_excerpt"):
        blocks.append(("Sample filled excerpt", str(tpl["sample_filled_excerpt"])))
    for s in tpl.get("seo_sections") or []:
        if isinstance(s, dict):
            body = s.get("body") or s.get("content") or s.get("text") or ""
            if isinstance(body, list):
                body = "\n".join(map(str, body))
            blocks.append((s.get("title") or s.get("heading") or "Notes", str(body)))
    return [(t, b) for t, b in blocks if b and b.strip()]


def trim_markdown(md: str) -> str:
    """Keep page body: from the first H1 up to the related-templates footer."""
    if not md:
        return ""
    lines = md.split("\n")
    start = next((i for i, l in enumerate(lines) if l.startswith("# ")), 0)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if re.match(r"#{2,4}\s*(Related (Templates|Formats)|More related)", lines[i]) or lines[i].strip().startswith("Related Templates"):
            end = i
            break
    return "\n".join(lines[start:end]).strip()
