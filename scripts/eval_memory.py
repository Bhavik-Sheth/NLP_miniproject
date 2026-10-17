#!/usr/bin/env python
"""Golden-set evaluation of Vesper memory retrieval (in-process, no HTTP).

    backend/.venv/bin/python scripts/eval_memory.py            # search metrics + threshold sweep
    backend/.venv/bin/python scripts/eval_memory.py --ask 12   # also time N /ask calls (Groq)

Reports recall@8 (answerable), abstain precision/recall, latency p50/p95 per leg (first pass = uncached
query embedding + rerank; repeat pass = cached), and the abstention threshold that maximises abstain F1
without losing answerable recall. Writes data/memory/eval_report.json.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from memory import api, config, retrieve  # noqa: E402


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))], 1)


def hit_ok(res: dict, expect: list[str]) -> bool:
    blob = " ".join(f"{h.get('title')} {h.get('section')} {h.get('text')}" for h in res["hits"]).lower()
    return any(e.lower() in blob for e in expect)


ENGINE_CASES = [  # v1 engine regressions (fix 1): no confident wrong answers, no observation capture for knowledge
    {"q": "chiller commissioning checklist?", "not": ["CL-PP-L3", "Location bataiye"]},
    {"q": "lap length 16 mm M25?", "not": ["RFI-041", "Location bataiye", "grid line"]},
    {"q": "curing period IS 456?", "not": ["CL-PP-L4", "Location bataiye", "grid line"]},
    {"q": "today's steel rate?", "not": ["C-401 R2", "2026-09-11"]},
    {"q": "What cover does IS 456 require for columns?", "not": ["grid line", "Location bataiye", "which grid"]},
    {"q": "whats the pending blockers", "all": ["CL-PP-L4-001", "HWP-0112", "RFI-049"]},
    {"q": "Give all information you can for Level 3", "all": ["Level 3"], "any": ["M-401", "HWP-0112", "RFI-049"],
     "not": ["could not find"]},
    {"q": "But you said that M-401 is pending, where did RFI-049 come from", "all": ["RFI-049", "M-401"],
     "not": ["Location bataiye", "grid line"]},
    {"q": "what is the cover at E-1?", "all": ["40 mm", "A-201"]},
]


def run_engine_cases() -> None:
    import shutil
    import tempfile

    import config as bconfig  # backend/config.py
    import db as dbmod
    from engine.dialogue import DialogueSession

    tmp = tempfile.mktemp(suffix=".db")
    shutil.copy(bconfig.SITE_DB_PATH, tmp)
    repo = dbmod.Repo(dbmod.connect(tmp), bconfig.PROJECT_ID)
    ok = 0
    for c in ENGINE_CASES:
        sess = DialogueSession(repo, dbmod.create_session(repo, "eval"), None, persist_turns=False)
        t = time.perf_counter()
        out = sess.handle(text=c["q"])
        ms = (time.perf_counter() - t) * 1000
        txt = out["reply"]["text"]
        good = (all(s in txt for s in c.get("all", [])) and (not c.get("any") or any(s in txt for s in c["any"]))
                and not any(s.lower() in txt.lower() for s in c.get("not", [])) and out.get("kind") == "answer")
        ok += good
        print(f"  {'OK ' if good else 'BAD'} {ms:6.0f}ms {c['q'][:55]:55} -> {txt[:150]}")
    print(f"engine cases {ok}/{len(ENGINE_CASES)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default=str(config.MEMORY_DIR / "golden.json"))
    ap.add_argument("--ask", type=int, default=0)
    ap.add_argument("--engine", action="store_true", help="run only the v1 engine regression cases")
    ap.add_argument("--http", default="", help="evaluate a running backend, e.g. http://localhost:8000")
    a = ap.parse_args()
    if a.engine:
        run_engine_cases()
        return
    qs = json.loads(Path(a.golden).read_text())["questions"]
    org, pid = config.DEMO_ORG, config.DEMO_PROJECT
    if a.http:  # evaluate the running server (one reranker in RAM); timings are the server's timingsMs
        import httpx

        cli = httpx.Client(base_url=a.http.rstrip("/"), timeout=120)

        class _Remote:
            config = config

            @staticmethod
            def search(q, org_id=None, project_id=None, **_):
                r = cli.post("/api/memory/search", headers={"X-Vesper-User": "eval", "X-Vesper-Org": org_id or ""},
                             json={"query": q, "projectId": project_id})
                r.raise_for_status()
                return r.json()

            @staticmethod
            def ask(q, org_id=None, project_id=None, **_):
                r = cli.post("/api/memory/ask", headers={"X-Vesper-User": "eval", "X-Vesper-Org": org_id or ""},
                             json={"query": q, "projectId": project_id})
                r.raise_for_status()
                d = r.json()
                d.setdefault("timings", {"llm_ms": (d.get("timingsMs") or {}).get("llm")})
                return d

        globals()["api"] = _Remote
    else:
        api.warmup(background=False)
    api.search("warm up the pipeline", org_id=org, project_id=pid)

    rows = []
    for q in qs:
        qo, qp = q.get("org", org), q.get("project", pid)
        r1 = api.search(q["q"], org_id=qo, project_id=qp)
        r2 = api.search(q["q"], org_id=qo, project_id=qp)
        leak = [h["dataset"] for h in r1["hits"] if h["dataset"] in (q.get("expect_not_datasets") or [])
                or (h["scope"] == "project" and h["dataset"] != api.config.project_dataset(qo, qp))]
        leak += [t for t in (q.get("expect_not_text") or []) for h in r1["hits"]
                 if h["scope"] != "project" and re.search(rf"\b{re.escape(t)}\b", h["text"])]
        best = max((h["rerankScore"] for h in r1["hits"] if h["rerankScore"] is not None), default=None)
        rows.append({"id": q["id"], "type": q["type"], "q": q["q"], "must_abstain": bool(q.get("abstain")),
                     "abstain": r1["abstain"], "reason": r1["abstainReason"], "best": best,
                     "reranked": r1["reranked"], "found": hit_ok(r1, q.get("expect_any") or []) if q.get("expect_any") else None,
                     "t1": r1["timingsMs"], "t2": r2["timingsMs"], "leak": leak,
                     "top": [(h["title"] or "")[:60] for h in r1["hits"][:3]]})

    ans = [r for r in rows if not r["must_abstain"]]
    neg = [r for r in rows if r["must_abstain"]]
    recall8 = sum(1 for r in ans if r["found"]) / max(1, len(ans))
    answered_correct = sum(1 for r in ans if r["found"] and not r["abstain"]) / max(1, len(ans))
    tp = sum(1 for r in neg if r["abstain"])
    fp = sum(1 for r in ans if r["abstain"])
    prec = tp / max(1, tp + fp)
    rec = tp / max(1, len(neg))

    # threshold sweep: entity / empty abstentions are threshold-independent
    sweep = []
    for t in [x / 100 for x in range(2, 96, 2)]:
        def pred(r):
            if r["reason"] and not r["reason"].startswith("low_rerank"):
                return True
            return r["best"] is not None and r["best"] < t
        tp_t = sum(1 for r in neg if pred(r))
        fp_t = sum(1 for r in ans if pred(r))
        ans_ok = sum(1 for r in ans if r["found"] and not pred(r)) / max(1, len(ans))
        p_t, r_t = tp_t / max(1, tp_t + fp_t), tp_t / max(1, len(neg))
        f1 = 2 * p_t * r_t / max(1e-9, p_t + r_t)
        sweep.append({"t": t, "precision": round(p_t, 3), "recall": round(r_t, 3), "f1": round(f1, 3),
                      "answerable_answered": round(ans_ok, 3)})
    best_t = max(sweep, key=lambda s: (round(s["f1"] + s["answerable_answered"], 3), -abs(s["t"] - 0.35)))

    lat = {}
    for key in ("rewrite", "embed", "vector", "bm25", "fuse", "rerank", "total"):
        lat[key] = {"p50_first": pct([r["t1"][key] for r in rows], .5), "p95_first": pct([r["t1"][key] for r in rows], .95),
                    "p50_repeat": pct([r["t2"][key] for r in rows], .5), "p95_repeat": pct([r["t2"][key] for r in rows], .95)}

    ask_lat = []
    ask_rows = []
    if a.ask:
        for q in [x for x in qs if not x.get("abstain")][:a.ask] + [x for x in qs if x.get("abstain")][:2]:
            t = time.perf_counter()
            res = api.ask(q["q"], org_id=org, project_id=pid)
            ask_lat.append((time.perf_counter() - t) * 1000)
            ask_rows.append({"id": q["id"], "abstain": res["abstain"], "speech": res["speech"][:200],
                             "provider": res.get("provider"), "llm_ms": res["timings"].get("llm_ms")})

    by_type = {}
    for r in rows:
        d = by_type.setdefault(r["type"], {"n": 0, "found": 0, "abstained": 0})
        d["n"] += 1
        d["found"] += bool(r["found"])
        d["abstained"] += bool(r["abstain"])
    report = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "threshold_in_use": config.ABSTAIN_THRESHOLD,
              "n": len(rows), "answerable": len(ans), "must_abstain": len(neg),
              "recall_at_8": round(recall8, 3), "answerable_answered_and_found": round(answered_correct, 3),
              "abstain_precision": round(prec, 3), "abstain_recall": round(rec, 3),
              "calibrated_threshold": best_t, "scope_leaks": [r["id"] for r in rows if r["leak"]], "latency_ms": lat,
              "ask_ms": {"p50": pct(ask_lat, .5), "p95": pct(ask_lat, .95), "n": len(ask_lat)} if ask_lat else None,
              "ask_samples": ask_rows, "by_type": by_type, "rows": rows, "sweep": sweep}
    (config.MEMORY_DIR / "eval_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"recall@8 {recall8:.3f} · answered+found {answered_correct:.3f} · abstain P {prec:.3f} R {rec:.3f} "
          f"(threshold {config.ABSTAIN_THRESHOLD})")
    print(f"calibrated threshold {best_t}")
    print("scope leaks:", [(r["id"], r["leak"][:3]) for r in rows if r["leak"]] or "none")
    print("search latency ms (first pass):", {k: (v['p50_first'], v['p95_first']) for k, v in lat.items()})
    print("search latency ms (repeat):", {k: (v['p50_repeat'], v['p95_repeat']) for k, v in lat.items()})
    if ask_lat:
        print(f"ask p50 {pct(ask_lat, .5)} ms p95 {pct(ask_lat, .95)} ms (n={len(ask_lat)})")
    print("by type:", by_type)
    for r in rows:
        flag = ("OK " if (r["abstain"] if r["must_abstain"] else (r["found"] and not r["abstain"])) and not r["leak"] else "BAD")
        print(f"  {flag} {r['id']:6} abst={str(r['abstain'])[0]} {str(r['reason'] or ''):22} best={r['best']} "
              f"found={r['found']} {r['t1']['total']:.0f}ms | {r['top'][:1]}")


if __name__ == "__main__":
    main()
