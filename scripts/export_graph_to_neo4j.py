"""Back the Cognee knowledge graph up to Neo4j Aura. Write-only, by design.

Kuzu/Ladybug under `data/memory/cognee` stays the source of truth: the app reads the local graph and
never reads Aura back. This script only pushes a snapshot up so the graph survives the laptop.

    export $(grep -E '^NEO4J_' backend/.env.local | xargs)   # or rely on backend/.env.local
    backend/.venv/bin/python scripts/export_graph_to_neo4j.py --dry-run
    backend/.venv/bin/python scripts/export_graph_to_neo4j.py
    backend/.venv/bin/python scripts/export_graph_to_neo4j.py --wipe   # replace the previous backup

Everything written carries `:VesperNode` / `backup_run`, so `--wipe` can clear a previous backup
without touching anything else that happens to live in the instance.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "backend" / ".env.local", override=True)

SNAPSHOT = ROOT / "data" / "memory" / "graph" / "graph.json"
BATCH = 500
_SAFE = re.compile(r"[^A-Z0-9_]")


def rel_type(label: str) -> str:
    """Neo4j relationship types cannot be parameterised, so they are sanitised and inlined."""
    t = _SAFE.sub("_", (label or "REL").upper().replace(" ", "_")).strip("_")
    return t[:60] or "REL"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=pathlib.Path, default=SNAPSHOT)
    ap.add_argument("--wipe", action="store_true", help="delete the previous Vesper backup first")
    ap.add_argument("--dry-run", action="store_true", help="report what would be written, write nothing")
    args = ap.parse_args()

    if not args.snapshot.exists():
        print(f"no graph snapshot at {args.snapshot} — run the Cognee worker first", file=sys.stderr)
        return 2
    data = json.loads(args.snapshot.read_text())
    nodes = data.get("nodes") or []
    edges = data.get("edges") or []
    print(f"snapshot : {args.snapshot.relative_to(ROOT)}  ({len(nodes)} nodes, {len(edges)} edges)")
    print(f"generated: {data.get('generated_at')}  datasets: {len(data.get('datasets') or [])}")

    by_type: dict[str, int] = {}
    for n in nodes:
        by_type[n.get("type") or "Unknown"] = by_type.get(n.get("type") or "Unknown", 0) + 1
    print("node types:", ", ".join(f"{k}={v}" for k, v in sorted(by_type.items(), key=lambda x: -x[1])[:6]))

    if args.dry_run:
        print("dry run — nothing written")
        return 0

    uri, user, pw = os.getenv("NEO4J_URI"), os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")
    if not (uri and user and pw):
        print("NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD must be set (backend/.env.local)", file=sys.stderr)
        return 2

    from neo4j import GraphDatabase

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    driver = GraphDatabase.driver(uri, auth=(user, pw))
    try:
        driver.verify_connectivity()
    except Exception as e:  # noqa: BLE001
        print(f"could not connect: {type(e).__name__}: {str(e)[:160]}", file=sys.stderr)
        return 1

    db = os.getenv("NEO4J_DATABASE", "neo4j")
    with driver.session(database=db) as s:
        if args.wipe:
            gone = s.run("MATCH (n:VesperNode) DETACH DELETE n RETURN count(n) AS c").single()["c"]
            print(f"wiped    : {gone} previously backed-up nodes")

        s.run("CREATE CONSTRAINT vesper_node_id IF NOT EXISTS "
              "FOR (n:VesperNode) REQUIRE n.id IS UNIQUE")

        written = 0
        for i in range(0, len(nodes), BATCH):
            chunk = [{"id": n.get("id"), "label": n.get("label"), "type": n.get("type") or "Unknown"}
                     for n in nodes[i:i + BATCH] if n.get("id")]
            s.run(
                "UNWIND $rows AS r MERGE (n:VesperNode {id: r.id}) "
                "SET n.label = r.label, n.type = r.type, n.backup_run = $run",
                rows=chunk, run=run_id)
            written += len(chunk)
            print(f"  nodes {written}/{len(nodes)}", end="\r", flush=True)
        print(f"nodes    : {written} written              ")

        grouped: dict[str, list[dict]] = {}
        for e in edges:
            if e.get("source") and e.get("target"):
                grouped.setdefault(rel_type(e.get("label")), []).append(
                    {"s": e["source"], "t": e["target"], "label": e.get("label")})

        total = 0
        for rtype, rows in grouped.items():
            for i in range(0, len(rows), BATCH):
                s.run(
                    f"UNWIND $rows AS r MATCH (a:VesperNode {{id: r.s}}), (b:VesperNode {{id: r.t}}) "
                    f"MERGE (a)-[x:{rtype}]->(b) SET x.label = r.label, x.backup_run = $run",
                    rows=rows[i:i + BATCH], run=run_id)
                total += len(rows[i:i + BATCH])
                print(f"  edges {total}/{len(edges)}", end="\r", flush=True)
        print(f"edges    : {total} written across {len(grouped)} relationship type(s)        ")

        n_now = s.run("MATCH (n:VesperNode) RETURN count(n) AS c").single()["c"]
        e_now = s.run("MATCH (:VesperNode)-[r]->(:VesperNode) RETURN count(r) AS c").single()["c"]
        print(f"in Aura  : {n_now} nodes, {e_now} relationships (run {run_id})")
    driver.close()
    print("done. This is a backup; the app still reads the local Kuzu graph.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
