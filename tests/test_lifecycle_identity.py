"""Phase 0 regression tests for the uncommitted v2 fixes.

Runs against the LAB database only (never live):
    DATABASE_URL=postgresql://kestrel:kestrel@localhost:5434/kestrel \
    python3 tests/test_lifecycle_identity.py

Covers:
  1. identity=None (AUTH_MODE=off) no longer crashes — a personal workspace
     is created and the reservation commits.
  2. the same idempotency key with the same payload returns the existing job
     (UUID values serialize correctly in the conflict payload).
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg

import lifecycle

URL = os.environ.get("DATABASE_URL", "")
assert URL and "5434" in URL, "refusing to run against anything but the lab DB"


def cleanup(cur, key):
    cur.execute("select id, brain_id from brain_jobs where idempotency_key=%s", (key,))
    for row in cur.fetchall():
        cur.execute("delete from brain_job_staging where job_id=%s", (row["id"],))
        cur.execute("delete from brain_job_files where job_id=%s", (row["id"],))
        cur.execute("delete from brain_job_events where job_id=%s", (row["id"],))
        cur.execute("delete from brain_jobs where id=%s", (row["id"],))
        cur.execute("update brains set active_generation_id=null where id=%s", (row["brain_id"],))
        cur.execute("delete from brain_generations where brain_id=%s", (row["brain_id"],))
        cur.execute("delete from brains where id=%s", (row["brain_id"],))


def main():
    key = f"phase0-{uuid.uuid4()}"
    files = [("phase0.txt", b"Phase 0 regression test content.")]
    with psycopg.connect(URL, row_factory=psycopg.rows.dict_row) as conn, conn.cursor() as cur:
        cleanup(cur, key)
        conn.commit()

    # 1. identity=None must not crash (the fixed bug)
    r = lifecycle.create_brain_v2(None, f"phase0_{uuid.uuid4().hex[:6]}", files, key)
    assert r["job_id"] and r["brain_id"], "reservation failed"

    # workspace row exists for the org-less identity
    with psycopg.connect(URL, row_factory=psycopg.rows.dict_row) as conn, conn.cursor() as cur:
        ws = cur.execute(
            """select w.id from workspaces w join brains b on b.workspace_id=w.id
               where b.id=%s""", (r["brain_id"],)).fetchone()
        assert ws, "no personal workspace created"
    # 2. same key + same payload -> IdempotencyConflict with str(existing_job)
    try:
        lifecycle.create_brain_v2(None, f"phase0_{uuid.uuid4().hex[:6]}", files, key)
        raise SystemExit("FAIL: expected IdempotencyConflict")
    except lifecycle.IdempotencyConflict as exc:
        assert "existing_job" in str(exc), f"conflict payload malformed: {exc}"

    # cleanup reservation rows (job never ran)
    with psycopg.connect(URL, row_factory=psycopg.rows.dict_row) as conn, conn.cursor() as cur:
        cleanup(cur, key)
        cur.execute("delete from brain_job_staging where job_id=%s", (r["job_id"],))
        cur.execute("delete from brain_job_files where job_id=%s", (r["job_id"],))
        cur.execute("delete from brain_jobs where id=%s", (r["job_id"],))
        cur.execute("update brains set active_generation_id=null where id=%s", (r["brain_id"],))
        cur.execute("delete from brain_generations where brain_id=%s", (r["brain_id"],))
        cur.execute("delete from brains where id=%s", (r["brain_id"],))
        conn.commit()
    print("PHASE 0 REGRESSION: PASS")


if __name__ == "__main__":
    main()
