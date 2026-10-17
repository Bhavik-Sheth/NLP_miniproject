"""Hybrid retrieval with abstention.

query -> follow-up rewrite (rules; LLM only on pronoun/ellipsis when allowed) -> regex-gated decomposition
      -> parallel legs: LanceDB vector (top 30 per sub-query) | FTS5 BM25 (top 15, exact-ID column boosts)
      -> RRF k=60 (+ exact-entity leg, thin-stub down-weight) -> cross-encoder rerank of the head
      -> keep 8 with per-doc cap + fingerprint dedup -> neighbour expansion for the top 3
      -> abstain if the best rerank score < threshold or a key entity (RFI/drawing/grid/code/clause/template)
         in the question appears in none of the kept hits.
Rerank is skipped when an exact-ID BM25 hit already dominates (latency), and its scores are cached.
"""
from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from . import chunkers, config, embed, rerank, store

_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="memory-retrieve")
RERANK_HEAD = int(__import__("os").getenv("MEMORY_RERANK_HEAD", "8"))  # 8 pairs x ~480 chars ~ 250 ms idle on M3
RERANK_PASSAGE_CHARS = int(__import__("os").getenv("MEMORY_RERANK_PASSAGE_CHARS", "520"))
THIN_WEIGHT = 0.75
PROJECT_WEIGHT = float(__import__("os").getenv("MEMORY_PROJECT_WEIGHT", "1.5"))
PROJECT_IN_HEAD = int(__import__("os").getenv("MEMORY_PROJECT_IN_HEAD", "3"))

HINGLISH = {
    "kitna": "how much", "kitni": "how much", "kitne": "how many", "kya": "what", "kaunsa": "which", "kaunsi": "which",
    "kaun": "which", "kab": "when", "kahan": "where", "kaise": "how", "chahiye": "required", "batao": "tell",
    "bataiye": "tell", "aaj": "today", "kal": "yesterday", "daam": "price", "bhav": "price", "keemat": "price",
    "sariya": "steel rebar", "saria": "steel rebar", "ret": "sand", "gitti": "aggregate", "tarai": "curing",
    "taraai": "curing", "pe": "at", "par": "at", "mein": "in", "lambai": "length", "motai": "thickness",
    "doori": "spacing", "jaanch": "inspection check", "ijazat": "permit", "suraksha": "safety",
}
STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "for", "by", "with", "is", "are", "was", "were", "be",
    "what", "whats", "which", "who", "whom", "when", "where", "why", "how", "much", "many", "do", "does", "did", "can",
    "could", "should", "would", "will", "shall", "may", "i", "we", "you", "me", "my", "our", "your", "it", "its",
    "this", "that", "these", "those", "there", "please", "tell", "show", "give", "list", "about", "as", "per", "any",
    "kya", "hai", "hain", "ka", "ki", "ke", "ko", "se", "pe", "par", "mein", "tha", "thi", "wala", "wali", "aur",
    "batao", "bataiye", "kitna", "kitni", "kitne", "me", "from", "into", "than", "then", "so", "if", "not", "no",
    "yes", "all", "get", "need", "required", "require", "value", "current", "latest",
}
_PRONOUN = re.compile(r"\b(it|its|that|this|those|these|there|same|them|they|iska|uska|iski|uski|wahan|wahi|yeh|woh|"
                      r"usme|isme)\b", re.I)
_ELLIPSIS = re.compile(r"^\s*(and|what about|how about|aur|or|also|then|same for|for)\b", re.I)
_DECOMP = re.compile(r"\b(and|vs\.?|versus|compare|compared|between|aur)\b", re.I)


def content_terms(q: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9.\-/]*", (q or "").lower())
    out = []
    for w in words:
        w = w.strip(".-/")
        if len(w) < 2 or w in STOP:
            continue
        out.append(w)
    return out


def key_entities(q: str) -> list[str]:
    return [tok for typ, tok in chunkers.extract_entities(q) if typ in chunkers.KEY_ENTITY_TYPES]


# ============================================================== rewriting
def rewrite(query: str, history: list[dict] | None = None, allow_llm: bool = False) -> tuple[str, str]:
    """Returns (rewritten, method). Rules first: carry the previous turn's entities/topic into a follow-up."""
    q = chunkers.normalize_query_ids(" ".join((query or "").split()))
    if not history:
        return q, "none"
    prev = history[-1]
    ents = key_entities(q)
    terms = content_terms(q)
    followup = bool(_PRONOUN.search(q) or _ELLIPSIS.match(q)) or len(terms) <= 2
    if not followup:
        return q, "none"
    add = []
    prev_q = prev.get("rewritten") or prev.get("query") or ""
    prev_ents = key_entities(prev_q)
    prev_terms = [t for t in content_terms(prev_q) if not re.match(r"^[a-z]{1,3}-?\d", t)]
    if not ents and prev_ents:
        add += prev_ents_display(prev_q)
    if len(terms) <= 2 or (_PRONOUN.search(q) and not ents):
        add += [t for t in prev_terms if t not in terms][:4]
    if not add:
        return q, "none"
    base = _ELLIPSIS.sub("", q).strip(" ?") if _ELLIPSIS.match(q) else q.strip(" ?")
    out = f"{base} {' '.join(dict.fromkeys(add))}".strip()
    if allow_llm and _PRONOUN.search(q) and config.llm_available():
        try:
            from .answer import llm_rewrite

            better = llm_rewrite(q, prev_q)
            if better:
                return chunkers.normalize_query_ids(better), "llm"
        except Exception:  # noqa: BLE001
            pass
    return out, "rules"


def prev_ents_display(q: str) -> list[str]:
    """Entity surface forms as written in the previous query ('E-1', 'RFI-050', 'IS 456')."""
    forms = []
    for typ, rx, _fn in chunkers._ENT:  # noqa: SLF001
        if typ in chunkers.KEY_ENTITY_TYPES:
            forms += [m.group(0) for m in rx.finditer(q)]
    return forms


def decompose(q: str) -> list[str]:
    if len(q.split()) < 6 or not _DECOMP.search(q):
        return []
    parts = [p.strip(" ,?") for p in re.split(r"\b(?:and|vs\.?|versus|compared with|compared to|aur)\b", q, flags=re.I)]
    parts = [p for p in parts if len(content_terms(p)) >= 2]
    return parts[:3] if len(parts) >= 2 else []


# ============================================================== legs
def fts_match(q: str) -> str:
    parts: list[str] = []
    for tok in dict.fromkeys(key_entities(q) + [t for typ, t in chunkers.extract_entities(q) if typ == "grade"]):
        parts.append(f'entities:"{tok}"')
    for typ, rx, _fn in chunkers._ENT:  # noqa: SLF001
        if typ in chunkers.KEY_ENTITY_TYPES:
            for m in rx.finditer(q):
                phrase = re.sub(r"[^A-Za-z0-9]+", " ", m.group(0)).strip()
                if phrase:
                    parts.append(f'"{phrase}"')
    terms = content_terms(q)
    extra = []
    for t in terms:
        if t in HINGLISH:
            extra += HINGLISH[t].split()
    for t in list(dict.fromkeys([*terms, *extra]))[:14]:
        t = re.sub(r"[^A-Za-z0-9]+", " ", t).strip()
        if t and t not in STOP:
            parts.append(f'"{t}"')
    return " OR ".join(dict.fromkeys(parts))


def _vector_leg(q: str, datasets: list[str], k: int) -> tuple[list[dict], float, float]:
    t = time.perf_counter()
    vec = embed.embed_query(q)
    te = time.perf_counter() - t
    rows = store.vector_search(vec, datasets, k)
    return rows, te, time.perf_counter() - t - te


def _fts_leg(q: str, datasets: list[str], k: int) -> tuple[list[dict], float]:
    t = time.perf_counter()
    rows = store.fts_search(fts_match(q), datasets, k)
    return rows, time.perf_counter() - t


def _rrf_add(fused: dict, cid: str, rank: int, weight: float = 1.0) -> None:
    fused[cid] = fused.get(cid, 0.0) + weight / (config.RRF_K + rank + 1)


_rr_cache: OrderedDict[tuple, float] = OrderedDict()
_rr_lock = threading.Lock()
_rr_stats = threading.local()


def _rerank(q: str, rows: list[dict]) -> list[float] | None:
    key_q = q.lower().strip()
    missing = [r for r in rows if (key_q, r["chunk_id"]) not in _rr_cache]
    _rr_stats.scored, _rr_stats.cached = len(missing), len(rows) - len(missing)
    if missing:
        terms = content_terms(q)
        passages = [_window(r, terms) for r in missing]
        scores = rerank.score(q, passages)
        if scores is None:
            return None
        with _rr_lock:
            for r, s in zip(missing, scores):
                _rr_cache[(key_q, r["chunk_id"])] = s
            while len(_rr_cache) > 20000:
                _rr_cache.popitem(last=False)
    return [_rr_cache[(key_q, r["chunk_id"])] for r in rows]


def _window(r: dict, terms: list[str]) -> str:
    """Rerank input: heading + the most query-dense window of the chunk (not just its first N chars),
    so a matching line deep in a long template / fact sheet is what the cross-encoder reads."""
    head = f"{r.get('title') or ''} · {r.get('section') or ''}\n"
    budget = max(120, RERANK_PASSAGE_CHARS - len(head))
    text = r["text"]
    if len(text) <= budget or not terms:
        return (head + text)[:RERANK_PASSAGE_CHARS]
    lines = text.splitlines() or [text]
    stems = [t[:5] for t in terms]
    scores = [sum(1 for s in stems if s in ln.lower()) for ln in lines]
    best = max(range(len(lines)), key=lambda i: (scores[i], -i))
    start, used, out = best, 0, []
    while start > 0 and used + len(lines[start - 1]) < budget // 3:  # a little context before the best line
        start -= 1
        used += len(lines[start]) + 1
    for ln in lines[start:]:
        if used + len(ln) > budget and out:
            break
        out.append(ln)
        used += len(ln) + 1
    return (head + "\n".join(out))[:RERANK_PASSAGE_CHARS]


def _fingerprint(r: dict) -> str:
    return f"{r['doc_id']}|{r.get('section')}|{r['text'][:200]}"


# ============================================================== main
def search(query: str, datasets: list[str], *, k: int | None = None, history: list[dict] | None = None,
           allow_llm_rewrite: bool = False, rerank_mode: str = "auto") -> dict:
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    k = k or config.KEEP_K
    rewritten, method = rewrite(query, history, allow_llm_rewrite)
    timings["rewrite_ms"] = (time.perf_counter() - t0) * 1000
    subs = decompose(rewritten)
    legs_q = [rewritten, *subs]
    q_ents = key_entities(rewritten)

    fts_futs = [_pool.submit(_fts_leg, x, datasets, config.FTS_K) for x in legs_q]
    vec_futs = [_pool.submit(_vector_leg, x, datasets, config.VECTOR_K) for x in legs_q]
    # project-only legs: 20k global chunks must never crowd the project's own record out of the candidates
    proj_ds = [d for d in datasets if d.startswith("org_")]
    if proj_ds and len(proj_ds) < len(datasets):
        vec_futs.append(_pool.submit(_vector_leg, rewritten, proj_ds, 8))
        fts_futs.append(_pool.submit(_fts_leg, rewritten, proj_ds, 6))
    fused: dict[str, float] = {}
    vec_best: dict[str, float] = {}
    bm25_rank: dict[str, int] = {}
    t_legs = time.perf_counter()
    for f in vec_futs:
        rows, te, tv = f.result()
        timings["embed_ms"] = timings.get("embed_ms", 0) + te * 1000
        timings["vector_ms"] = timings.get("vector_ms", 0) + tv * 1000
        for i, r in enumerate(rows):
            _rrf_add(fused, r["chunk_id"], i)
            vec_best[r["chunk_id"]] = max(vec_best.get(r["chunk_id"], -1), r["vector_score"])
    for f in fts_futs:
        frows, tb = f.result()
        timings["bm25_ms"] = timings.get("bm25_ms", 0) + tb * 1000
        for i, r in enumerate(frows):
            _rrf_add(fused, r["chunk_id"], i)
            bm25_rank[r["chunk_id"]] = min(bm25_rank.get(r["chunk_id"], 10 ** 6), i + 1)
    timings["legs_wall_ms"] = (time.perf_counter() - t_legs) * 1000

    t_fuse = time.perf_counter()
    rows = store.chunks_by_ids(list(fused))
    # exact-entity leg: chunks whose entity column carries every key entity of the question
    if q_ents:
        ent_hits = sorted((cid for cid, r in rows.items()
                           if all(e in (r.get("entities") or "").split() for e in q_ents)),
                          key=lambda c: -fused[c])
        for i, cid in enumerate(ent_hits):
            _rrf_add(fused, cid, i, weight=1.0)
    for cid, r in rows.items():
        meta = r.get("meta") or ""
        if '"thin": true' in meta:
            fused[cid] *= THIN_WEIGHT
        if r.get("scope") == "project":  # the project's own record outranks generic knowledge
            fused[cid] *= PROJECT_WEIGHT
    order = sorted((c for c in fused if c in rows), key=lambda c: -fused[c])
    # guarantee the best project passages reach the cross-encoder even when 550 templates crowd the head
    head_n = max(config.RERANK_TOP, RERANK_HEAD)
    proj = [c for c in order if rows[c].get("scope") == "project"][:PROJECT_IN_HEAD]
    if proj and any(c not in order[:RERANK_HEAD] for c in proj):
        rest = [c for c in order if c not in proj]
        order = order[:RERANK_HEAD - len([c for c in proj if c not in order[:RERANK_HEAD]])]
        order = list(dict.fromkeys(order + proj + rest))
    timings["fuse_ms"] = (time.perf_counter() - t_fuse) * 1000

    head = [rows[c] for c in order[:max(config.RERANK_TOP, RERANK_HEAD)]]
    terms = content_terms(rewritten)
    dominant = False
    if head and q_ents:
        top = head[0]
        blob = f"{top.get('title')} {top.get('section')} {top['text']}".lower()
        dominant = (all(e in (top.get("entities") or "").split() for e in q_ents)
                    and bm25_rank.get(top["chunk_id"], 99) <= 3
                    and sum(1 for w in terms if w in blob) >= max(1, len(terms) - 1))
    rr_scores = None
    t = time.perf_counter()
    if head and rerank_mode != "off" and not (rerank_mode == "auto" and dominant):
        cand = head[:RERANK_HEAD]
        rr_scores = _rerank(rewritten, cand)
        if rr_scores is not None:
            smap = {r["chunk_id"]: s for r, s in zip(cand, rr_scores)}
            max_f = max(fused[r["chunk_id"]] for r in cand) or 1.0
            cand.sort(key=lambda r: -(0.85 * smap[r["chunk_id"]] + 0.15 * fused[r["chunk_id"]] / max_f))
            head = cand + head[RERANK_HEAD:]
    timings["rerank_ms"] = (time.perf_counter() - t) * 1000
    smap = {r["chunk_id"]: s for r, s in zip(head[:RERANK_HEAD], rr_scores)} if rr_scores is not None else {}
    if rr_scores is not None:
        smap = {r["chunk_id"]: _rr_cache.get((rewritten.lower().strip(), r["chunk_id"])) for r in head[:RERANK_HEAD]}

    kept, per_doc, seen_fp = [], {}, set()
    for r in head:
        if len(kept) >= k:
            break
        fp = _fingerprint(r)
        if fp in seen_fp or per_doc.get(r["doc_id"], 0) >= config.MAX_PER_DOC:
            continue
        seen_fp.add(fp)
        per_doc[r["doc_id"]] = per_doc.get(r["doc_id"], 0) + 1
        kept.append(r)

    hits = []
    for i, r in enumerate(kept):
        h = {"chunkId": r["chunk_id"], "docId": r["doc_id"], "title": r.get("title"), "section": r.get("section"),
             "source": r.get("source"), "url": r.get("url"), "category": r.get("category"), "dataset": r["dataset"],
             "scope": r["scope"], "kind": r.get("kind"), "text": r["text"],
             "vectorScore": round(vec_best[r["chunk_id"]], 4) if r["chunk_id"] in vec_best else None,
             "bm25Rank": bm25_rank.get(r["chunk_id"]), "rrfScore": round(fused[r["chunk_id"]], 5),
             "rerankScore": round(smap[r["chunk_id"]], 4) if smap.get(r["chunk_id"]) is not None else None,
             "citation": r.get("citation")}
        if i < 3 and r.get("kind") in ("text", "clause", "record"):
            nb = store.neighbours(r["doc_id"], r["n"], 1)
            if nb:
                h["context"] = "\n".join(x["text"] for x in nb)[:1200]
        hits.append(h)

    # ---------------------------------------------------------------- abstention
    reason = None
    best = max((h["rerankScore"] for h in hits if h["rerankScore"] is not None), default=None)
    if not hits:
        reason = "no_hits"
    elif q_ents:
        found = set()
        for h in kept:
            found |= set((h.get("entities") or "").split())
        missing = [e for e in q_ents if e not in found]
        if missing:
            reason = f"entity_missing:{','.join(missing)}"
    if reason is None and best is not None and best < config.ABSTAIN_THRESHOLD:
        reason = "low_rerank"
    confidence = best if best is not None else (0.7 if dominant else (0.5 if hits else 0.0))
    timings["total_ms"] = (time.perf_counter() - t0) * 1000
    tm = {k2: round(v, 1) for k2, v in timings.items()}
    if rerank_mode == "off":
        rr_mode = "off"
    elif dominant and rerank_mode == "auto":
        rr_mode = "skipped_exact_id"      # an exact-ID BM25 hit already answers; abstention uses the entity check
    elif rr_scores is None:
        rr_mode = "unavailable" if head else "no_candidates"
    elif getattr(_rr_stats, "scored", 0) == 0:
        rr_mode = "cached"                # same (query, chunk) scored earlier; scores reused, threshold still applied
    else:
        rr_mode = "cross_encoder"
    rr_info = {"mode": rr_mode, "model": config.RERANK_MODEL,
               "scored": getattr(_rr_stats, "scored", 0) if rr_scores is not None else 0,
               "cached": getattr(_rr_stats, "cached", 0) if rr_scores is not None else 0}
    timings_ms = {"rewrite": tm.get("rewrite_ms", 0.0), "embed": tm.get("embed_ms", 0.0),
                  "vector": tm.get("vector_ms", 0.0), "bm25": tm.get("bm25_ms", 0.0), "fuse": tm.get("fuse_ms", 0.0),
                  "rerank": tm.get("rerank_ms", 0.0), "llm": 0.0, "total": tm.get("total_ms", 0.0),
                  "rerankSkipped": rr_mode not in ("cross_encoder",), "rerankMode": rr_mode}
    return {"query": query, "rewrittenQuery": rewritten, "rewriteMethod": method, "subQueries": subs,
            "abstain": reason is not None, "abstainReason": reason, "confidence": round(float(confidence), 4),
            "reranked": rr_scores is not None, "rerank": rr_info, "dominantExactHit": dominant, "entities": q_ents,
            "hits": hits, "timingsMs": timings_ms, "timings": tm}
