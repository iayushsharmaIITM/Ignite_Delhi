"""Phase 7: rebuild a brain's generation from its approved corpus files.

    PYTHONPATH=. DATABASE_URL=... COGNEE_SERVICE_URL=... \
        python3 ops/rebuild_brain.py company_brain corpus/

Stages a REBUILD job; the worker ingests into a NEW generation and publishes
only after provenance verification. The old generation is RETIRED (kept) and
its dataset is never deleted here.
"""
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lifecycle

slug = sys.argv[1]
src = sys.argv[2] if len(sys.argv) > 2 else "corpus"
files = []
for name in sorted(os.listdir(src)):
    path = os.path.join(src, name)
    if os.path.isfile(path):
        files.append((name, open(path, "rb").read()))
print(f"staging REBUILD for '{slug}' with {len(files)} files")
r = lifecycle.rebuild_brain(slug, files, f"rebuild-{uuid.uuid4()}")
print("job:", r["job_id"], "generation:", r["generation"])
job = r["job_id"]
while True:
    st = lifecycle.job_status(job)
    state = st["job"]["state"]
    if state in ("SUCCEEDED", "FAILED", "RECONCILIATION_REQUIRED", "CANCELLED"):
        print("final:", state, st["job"].get("error_code") or "")
        for f in st["files"]:
            print("  ", f["client_file_id"], f["stage"])
        break
    time.sleep(15)
