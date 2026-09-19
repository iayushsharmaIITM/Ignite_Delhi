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
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent

# Importing cognee_cloud loads .env as a side effect, so configuration is
# correct no matter which entry point runs first.
import cognee_cloud as cc  # noqa: E402

CORPUS = HERE / "corpus"


def load_documents() -> list:
    if not CORPUS.exists():
        sys.exit(f"No corpus directory at {CORPUS}")
    files = sorted(CORPUS.glob("*.md"))
    if not files:
        sys.exit(f"No .md documents in {CORPUS}")
    return [(f.name, f.read_text()) for f in files]


async def ingest_sequential(docs, name):
    for i, (filename, text) in enumerate(docs, 1):
        t0 = time.time()
        try:
            await asyncio.to_thread(cc.remember, text, name)
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
                await asyncio.to_thread(cc.remember, text, name)
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
    except Exception as exc:  # noqa: BLE001
        print(f"Graph unavailable: {exc}")


if __name__ == "__main__":
    main()
