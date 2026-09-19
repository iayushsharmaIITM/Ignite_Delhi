"""Ingest the synthetic company corpus into the Cognee Cloud knowledge graph.

Run this ONCE, ahead of the demo. Never ingest live on stage — that is the
single most common way a hackathon demo dies.

    python ingest.py                 # sequential (safest)
    python ingest.py --parallel 4    # fan out, mirrors the Render Workflows path

Cognee serialises writes to a dataset server-side (the server carries a dataset
queue), so parallel calls queue rather than race. That is what makes the
parallel-ingestion story honest rather than decorative.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent

# Importing cognee_cloud loads .env as a side effect, so configuration is
# correct no matter which entry point runs first.
import cognee_cloud as cc  # noqa: E402
import documents  # noqa: E402

CORPUS = HERE / "corpus"
GRAPH_FIXTURE = HERE / "fixtures" / "graph.json"


def save_graph_fixture(g: dict) -> None:
    """Snapshot the graph so the UI still works with no network.

    /api/graph and /api/stats fall back to this file when the tenant is
    unreachable, so PROVIDER=mock — or a genuinely dead network — still renders
    the graph view instead of an error. Node `properties` are dropped because
    the view only draws label and type; that takes the payload from ~190KB to
    ~77KB, which is small enough to commit.
    """
    lean = {
        "nodes": [
            {"id": n["id"], "label": n.get("label", ""), "type": n.get("type", "")}
            for n in g.get("nodes", [])
        ],
        "edges": g.get("edges", []),
    }
    GRAPH_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_FIXTURE.write_text(json.dumps(lean, separators=(",", ":")), encoding="utf-8")
    kb = GRAPH_FIXTURE.stat().st_size // 1024
    print(f"Saved offline graph fixture: fixtures/{GRAPH_FIXTURE.name} ({kb} KB)")


def load_documents() -> list:
    """Load every ingestible file in corpus/.

    Uses documents.SUPPORTED_EXTS rather than a hard-coded "*.md" glob, so the
    corpus and the upload path agree on what counts as a document. The old glob
    silently ignored the two code artefacts (11_*.yaml, 12_*.py) — a 12-file
    corpus quietly ingested as 10, and nothing said so.
    """
    if not CORPUS.exists():
        sys.exit(f"No corpus directory at {CORPUS}")

    files = sorted(
        f for f in CORPUS.iterdir()
        if f.is_file() and f.suffix.lower() in documents.SUPPORTED_EXTS
    )
    if not files:
        sys.exit(f"No ingestible documents in {CORPUS}")

    out = []
    for f in files:
        try:
            out.append((f.name, documents.extract(f.name, f.read_bytes())))
        except documents.ExtractError as exc:
            # Report and continue: one unreadable corpus file must not block the
            # rest, for the same reason extract_many never raises per file.
            print(f"  skipping {f.name}: {exc}")
    if not out:
        sys.exit("Every corpus file failed to extract.")
    return out


async def ingest_sequential(docs, name):
    for i, (filename, text) in enumerate(docs, 1):
        t0 = time.time()
        try:
            await asyncio.to_thread(cc.remember, text, name, None, True, filename)
            print(f"  [{i}/{len(docs)}] {filename} -> queued ({time.time() - t0:.1f}s)",
                  flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{i}/{len(docs)}] {filename} -> FAILED: {exc}", flush=True)


async def ingest_parallel(docs, name, workers):
    """Fan out across N workers — the same shape as parallel Render task runs."""
    sem = asyncio.Semaphore(workers)
    lock = asyncio.Lock()
    done = 0

    async def one(filename, text):
        nonlocal done
        async with sem:
            t0 = time.time()
            try:
                await asyncio.to_thread(cc.remember, text, name, None, True, filename)
                async with lock:
                    done += 1
                    print(f"  [{done}/{len(docs)}] {filename} -> queued "
                          f"({time.time() - t0:.1f}s)", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"  {filename} -> FAILED: {exc}", flush=True)

    await asyncio.gather(*(one(n, t) for n, t in docs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parallel", type=int, default=1,
                    help="concurrent ingestion workers (default 1 = sequential)")
    ap.add_argument("--dataset", default=None)
    ap.add_argument("--no-wait", action="store_true",
                    help="return as soon as documents are queued")
    ap.add_argument("--timeout", type=int, default=1800)
    args = ap.parse_args()

    if not cc.configured():
        sys.exit("COGNEE_SERVICE_URL and COGNEE_API_KEY must both be set (see .env).")

    name = args.dataset or cc.dataset()
    docs = load_documents()

    print(f"Tenant:    {cc.service_url()}")
    print(f"Dataset:   {name}")
    print(f"Documents: {len(docs)}\n")

    t0 = time.time()
    if args.parallel > 1:
        print(f"Queueing {len(docs)} documents across {args.parallel} workers...")
        asyncio.run(ingest_parallel(docs, name, args.parallel))
    else:
        print(f"Queueing {len(docs)} documents sequentially...")
        asyncio.run(ingest_sequential(docs, name))

    print(f"\nAll queued in {time.time() - t0:.1f}s.")

    if args.no_wait:
        print("--no-wait set; the graph is still being built server-side.")
        return

    print("Waiting for the graph to finish building (this is the slow part)...")
    try:
        state = cc.wait_ready(name, timeout_s=args.timeout)
        print(f"Graph ready: {state}")
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: {exc}")
        return

    try:
        g = cc.graph(name)
        print(f"\nGraph: {len(g.get('nodes', []))} nodes, {len(g.get('edges', []))} edges")

        # ONLY snapshot the demo brain. The fixture is a copy of the DEMO graph and
        # app.py serves it as the demo's offline fallback, so writing it while
        # ingesting any other dataset replaces the demo's snapshot with a graph
        # that has nothing to do with the demo.
        #
        # This is not hypothetical: ingesting the scratch dataset `kestrel_full`
        # overwrote fixtures/graph.json with 213 nodes / 469 edges, and the demo
        # brain's committed snapshot had to be restored from git. A wrong fallback
        # is worse than no fallback, because it looks authoritative.
        if name == cc.dataset():
            save_graph_fixture(g)
        else:
            print(f"Not saving the offline fixture: {name!r} is not the demo "
                  f"dataset ({cc.dataset()!r}).")
    except Exception as exc:  # noqa: BLE001
        print(f"Graph unavailable: {exc}")


if __name__ == "__main__":
    main()
