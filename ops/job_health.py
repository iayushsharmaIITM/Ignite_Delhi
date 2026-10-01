"""Phase 11: stale-job visibility — one honest table of job states.

    DATABASE_URL=... python3 ops/job_health.py [--json]

Exits nonzero when jobs are stuck in a leased/reconcile state older than
their lease (the operator signal the completion prompt asks for).
"""
import json
import os
import sys

import psycopg

STUCK_STATES = ("EXTRACTING", "INGESTING", "VERIFYING")

def main():
    url = os.environ["DATABASE_URL"]
    with psycopg.connect(url, row_factory=psycopg.rows.dict_row) as conn, conn.cursor() as cur:
        rows = cur.execute("""
            select state, count(*) as n from brain_jobs group by state order by state
        """).fetchall()
        stuck = cur.execute("""
            select id, kind, state, lease_owner, lease_expires_at, attempt, error_code
            from brain_jobs
            where state = any(%s)
              and (lease_expires_at is null or lease_expires_at < now())
        """, (list(STUCK_STATES),)).fetchall()
        recon = cur.execute("""
            select id, kind, attempt, error_code from brain_jobs
            where state = 'RECONCILIATION_REQUIRED'""").fetchall()
    counts = {r["state"]: r["n"] for r in rows}
    if "--json" in sys.argv:
        print(json.dumps({"counts": counts, "stuck": [dict(s) for s in stuck],
                          "reconciliation_required": [dict(r) for r in recon]}, default=str))
    else:
        print("job states:", counts or "{}")
        if stuck:
            print("STUCK (expired lease):")
            for s in stuck:
                print(f"  {s['id']} {s['kind']} attempt={s['attempt']} err={s['error_code']}")
        if recon:
            print("RECONCILIATION_REQUIRED:")
            for r in recon:
                print(f"  {r['id']} {r['kind']} attempt={r['attempt']} err={r['error_code']}")
        healthy = not stuck
        print("JOB HEALTH:", "PASS" if healthy else "ACTION NEEDED (run the worker; recovery decides outcomes)")
    sys.exit(0 if healthy else 1)

if __name__ == "__main__":
    main()
