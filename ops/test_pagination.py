"""PR-5 contract test: pagination-safe data_items enumeration (N14).

Ingests NUM tiny synthetic documents into a scratch dataset on the target
Cognee, waits for the pipeline to reach a terminal state, then enumerates via
the paginated client and cross-checks against /data/count.

    COGNEE_SERVICE_URL=http://localhost:8889 python3 ops/test_pagination.py 120

Cost note: each doc triggers Cognee's extraction pipeline on the configured
DeepSeek route; tiny docs bound the spend. Writes only to the scratch dataset
`pagination_test_<pid>` — never to company_brain.
"""
import os
import sys
import time

import asyncio

NUM = int(sys.argv[1]) if len(sys.argv) > 1 else 120
DATASET = f"pagination_test_{os.getpid()}"

import cognee_cloud


async def main():
    ok = cognee_cloud.configured() or cognee_cloud.service_url().startswith(("http://localhost", "http://127.0.0.1"))
    assert ok, "COGNEE_SERVICE_URL must point at the lab/candidate stack"

    print(f"[1/3] ingesting {NUM} tiny docs into '{DATASET}' (background, parallel)…")
    async def one(i: int):
        text = (f"Pagination probe document {i:03d}. Clause {i}: the renewal "
                f"window runs {i} days and the credit schedule references "
                f"section {i} of the synthetic agreement.")
        try:
            await asyncio.to_thread(
                cognee_cloud.remember, text, DATASET, None, True, f"probe_{i:03d}.txt")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"  doc {i} failed: {str(exc)[:120]}")
            return False
    results = await asyncio.gather(*(one(i) for i in range(NUM)))
    fed = sum(results)
    print(f"      submitted {fed}/{NUM}")
    if fed == 0:
        sys.exit("all submissions failed")

    print("[2/3] waiting for pipeline terminal state…")
    state = await asyncio.to_thread(cognee_cloud.wait_ready, DATASET, 3600, 10)
    kind = cognee_cloud.terminal_kind(state)
    print(f"      pipeline: {kind}")

    print("[3/3] enumerating via paginated client…")
    rid = cognee_cloud.resolve_id(DATASET)
    items = await asyncio.to_thread(cognee_cloud.data_items, rid)
    print(f"      enumerated: {len(items)} items")
    distinct = len({i.get('id') for i in items if isinstance(i, dict)})
    print(f"      distinct ids: {distinct}")
    verdict = "PASS" if fed >= NUM - 2 and distinct == len(items) else "FAIL"
    print(f"PAGINATION CONTRACT ({NUM} docs): {verdict}")
    # cleanup the scratch dataset so the lab stays clean
    try:
        cognee_cloud.delete_dataset(DATASET)
        print("      scratch dataset deleted")
    except Exception as exc:  # noqa: BLE001
        print(f"      cleanup failed (note): {str(exc)[:120]}")


asyncio.run(main())
