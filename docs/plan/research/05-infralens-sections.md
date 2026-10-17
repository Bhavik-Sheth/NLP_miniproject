# 05 — infralens.in non-template sections (W6)

Scope: everything on infralens.in beyond the 3 template libraries (formats/qaqc/pmc, cached earlier).
Crawler: `data/scraper/crawl_sections.py`. Cache: `data/raw/sections/<section>/<slug>.{html.gz,json}`.

## Access
- `robots.txt`: `Allow: /` for all agents; single sitemap `https://infralens.in/sitemap.xml` (no index), **5,763 URLs**, not truncated (Firecrawl `_map.json` capped at 5,000).
- All pages server-render full HTML over plain HTTP (Next.js App Router). No JS or Firecrawl needed.
- Every page carries JSON-LD (BreadcrumbList + TechArticle/Article/Dataset/Product/DefinedTerm + usually FAQPage).
- IS code pages also embed a structured page-data object in the RSC stream (`self.__next_f.push`), decoded with `parse_infralens.decode_rsc`.

## Inventory (sitemap ∪ _map.json ∪ section index links)
| section | URLs | URL shape | primary content |
|---|---|---|---|
| code | 2,610 | `/code/<IS-456-2000>` (2,432), `/code/<id>/clauses` (24), `/code/<id>/clause/<6-1>` (154) | HTML + JSON-LD + RSC page data |
| prices | 868 | `/prices/<city>` (66), `/prices/<material>/<city>` (800; 16 materials × 50 cities) | HTML tables + Dataset JSON-LD |
| term | 394 | `/term/<slug>` | DefinedTerm JSON-LD + HTML |
| steel | 220 | `/steel/<islb-100>` | Product JSON-LD `additionalProperty` |
| thumbrules | 151 | `/thumbrules/<slug>` | HTML (1 table typical) |
| knowledge | 120 | `/knowledge/<slug>` | HTML article |
| sor | 118 | `/sor/<authority>` | HTML doc listings (PDF links, editions) |
| rate-analysis | 118 | `/rate-analysis/<item>` | HTML component table |
| handbook | 98 | `/handbook/<slug>` | HTML, many tables |
| dcr | 78 | `/dcr/<topic>/<city>` | HTML + tables (setbacks, FSI) |
| cpheeo | 48 | `/cpheeo/<slug>` | HTML article |
| gate | 44 | `/gate/<subject>[/<topic>]` | HTML |
| irc | 9 | `/irc/<slug>` | HTML |
| **default total** | **4,876** | | |

Not crawled by default (opt-in via `--sections`): projects 151, boq 59; skipped: tools 26, maps 17, cad-library 17, tender (interactive apps / file listings, little text).
A discovery pass after the main pass adds same-section internal links not in the inventory (e.g. extra clause pages).

## Final crawl result (2026-09-15, 08:04–08:39 UTC, ~35 min)
Discovery added 2,576 URLs. About 1,780 of them were real IS/other code pages that are missing from the sitemap. The other 762 returned 404 (748 `/code/*` links, plus a few in sor, term, handbook and knowledge). Parse errors: 0. Cache size: 326 MB.

| section | pages cached (html+json) |
|---|---|
| code | 4,391 (code 4,213 · clause 154 · clauses index 24) |
| prices | 869 |
| term | 394 |
| steel | 220 |
| thumbrules | 151 |
| knowledge | 120 |
| sor | 118 |
| rate-analysis | 118 |
| handbook | 98 |
| dcr | 78 |
| gate | 76 |
| cpheeo | 48 |
| irc | 9 |
| **total** | **6,690** |

The 404 URLs stay in `_inventory.json`, and `--offline` reports them as uncached. This is expected.

## Parsed JSON schema
`{url, section, slug, title, text, structured, fetched_at}` (+ `parse_error` if parsing failed; HTML kept).
- `text`: markdown-ish — `#` headings, `- ` bullets, tables as markdown tables; nav/footer/promo bars stripped; starts at H1.
- `structured` common fields (all sections): `description, headings[], tables[[cells]], faq[{q,a}], breadcrumbs[], links[] (internal paths, ≤200), headline, date_modified`.

Section-specific `structured` fields:
- **code** (`page_type`=`code`): `code_slug, code_number` ("IS 456:2000"), `code_title, key_values{}, key_clauses[], key_tables[], key_formulas[], practical_notes[], amendments[], quick_ref[{label,value,clause,note}], clauses[{clause_id,clause_title,summary,url}]`.
- **code** (`page_type`=`clause`): `code_slug, code_number, code_title, clause_id` ("6.1"), `clause_title, clause_text, related_clauses[]` (+ tables).
- **code** (`page_type`=`clauses`): `clauses[]` (links).
- **prices**: `material` (null on city pages), `city_slug, region, date` (Dataset temporalCoverage), `source, items[{item, spec, unit, rate, row{}}]` (rate strings keep range, e.g. "₹428 ₹407–449").
- **steel**: `section_name, standard` ("IS 808:2021"), `properties[{name,value,unit}]` (depth, width, tw, tf, weight, area, Ixx, …).
- **rate-analysis / sor**: `item_code, item_description, unit, rate, rate_city, components[{group, component, quantity, unit, rate, amount}]`, `authority, region, documents[{title,href}]` (SOR PDF editions).
- **term**: `term, definition, short_definition, aliases, category`.
- **dcr**: `topic, city, regulation, documents[]`.
- **thumbrules / handbook / knowledge / cpheeo / irc / gate**: `codes_referenced[]`, `documents[]` (if any), plus common fields.

## Quality notes (smoke-tested)
- IS 456 page: 33 KB text, 25 quick-ref rows, 6 key clauses, 15 clause cards, 5 FAQs.
- Clause 6.1: key requirements bullets + 2 tables + related clauses.
- Rate analysis M20: per-cum components grouped Materials/Labour/Machinery with ranges; total "₹8,886 – ₹11,412 per cum (Delhi)".
- Many of the 2,432 code pages are thin stubs (overview + FAQ); rich pages are the major IS/IRC codes.
