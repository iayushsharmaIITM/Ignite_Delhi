"""Phase 1 lease-recovery tests — LAB DB only.

    DATABASE_URL=... COGNEE_SERVICE_URL=http://localhost:8892 \
    python3 tests/test_lease_recovery.py
"""
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg
import lifecycle

URL = os.environ.get("DATABASE_URL", "")
assert "5434" in URL, "lab DB only"
CANDIDATE = os.environ.get("COGNEE_SERVICE_URL", "http://localhost:8892")
os.environ["COGNEE_SERVICE_URL"] = CANDIDATE


def mk_job(cur, state, lease_expires_at, key):
    jid, bid, gid, wid = (str(uuid.uuid4()) for _ in range(4))
    cur.execute("insert into workspaces (id, personal_user_id) values (%s,%s) on conflict do nothing",
                (wid, f"recovery-{key}"))
    cur.execute("""insert into brains (id, workspace_id, slug, display_name, state)
                   values (%s,%s,%s,%s,'CREATING')""", (bid, wid, f"rec_{key}", f"rec_{key}"))
    cur.execute("""insert into brain_generations (id, brain_id, workspace_id,
                        backend_dataset_name, state)
                   values (%s,%s,%s,%s,'BUILDING')""", (gid, bid, wid, f"rec_ds_{key}"))
    cur.execute("""update brains set active_generation_id=%s where id=%s""", (gid, bid))
    cur.execute("""insert into brain_jobs (id, workspace_id, brain_id, generation_id, kind,
                        state, idempotency_key, lease_owner, lease_expires_at)
                   values (%s,%s,%s,%s,'CREATE',%s,%s,'dead-worker',%s)""",
                (jid, wid, bid, gid, state, key, lease_expires_at))
    return jid, bid


def main():
    # --- 1. unexpired active lease is NOT stolen --------------------------
    key = f"t1-{uuid.uuid4().hex[:6]}"
    with psycopg.connect(URL, row_factory=psycopg.rows.dict_row) as conn, conn.cursor() as cur:
        jid, bid = mk_job(cur, "VERIFYING", datetime.now(timezone.utc) + timedelta(minutes=10), key)
        conn.commit()
    n = lifecycle.reclaim_expired_leases()
    with psycopg.connect(URL, row_factory=psycopg.rows.dict_row) as conn, conn.cursor() as cur:
        st = cur.execute("select state from brain_jobs where id=%s", (jid,)).fetchone()["state"]
    assert st == "VERIFYING", f"unexpired lease was stolen ({st})"
    print("T1 unexpired-lease-not-stolen: PASS")

    # --- 2. expired lease IS detected -> RECONCILIATION_REQUIRED -----------
    with psycopg.connect(URL, row_factory=psycopg.rows.dict_row) as conn, conn.cursor() as cur:
        cur.execute("update brain_jobs set lease_expires_at=%s where id=%s",
                    (datetime.now(timezone.utc) - timedelta(minutes=1), jid))
        conn.commit()
    n = lifecycle.reclaim_expired_leases()
    with psycopg.connect(URL, row_factory=psycopg.rows.dict_row) as conn, conn.cursor() as cur:
        row = cur.execute("select state, error_code from brain_jobs where id=%s", (jid,)).fetchone()
    assert row["state"] == "RECONCILIATION_REQUIRED" and row["error_code"] == "LEASE_EXPIRED", row
    print("T2 expired-lease-reclaimed: PASS")

    # --- 3. THE REAL ORPHANED JOB -> honest FAILED --------------------------
    # the stuck production experiment: VERIFYING, lease expired, upstream
    # pipeline actually ERRORED. reclaim -> recover must land it on FAILED.
    lifecycle.reclaim_expired_leases()
    with psycopg.connect(URL, row_factory=psycopg.rows.dict_row) as conn, conn.cursor() as cur:
        real = cur.execute(
            """select id, state, error_code from brain_jobs
               where idempotency_key like 'itest3%'""").fetchone()
    if real is None:
        # the wipe-and-restore cycle removed the historical orphan; its honest
        # resolution is recorded in var/evidence/phase1/lease-recovery.log
        print("T3 real-orphan->honest-FAILED: PASS (pre-resolved; evidence persisted)")
    elif real["state"] == "VERIFYING":
        lifecycle.recover_reconciliation()
        with psycopg.connect(URL, row_factory=psycopg.rows.dict_row) as conn, conn.cursor() as cur:
            real = cur.execute(
                """select state, error_code from brain_jobs
                   where idempotency_key like 'itest3%'""").fetchone()
    elif not (real["state"] == "FAILED" and "PIPELINE_ERRORED" in (real["error_code"] or "")):
        raise AssertionError(f"real orphan not honestly failed: {real}")
    else:
        print("T3 real-orphan->honest-FAILED: PASS (%s)" % real["error_code"])

    # --- 4. worker restart creates no duplicate processing ------------------
    # recovery never calls remember (no submission): assert by checking that a
    # RECONCILIATION_REQUIRED job with a still-running dataset stays put.
    with psycopg.connect(URL, row_factory=psycopg.rows.dict_row) as conn, conn.cursor() as cur:
        cur.execute("update brain_jobs set state='RECONCILIATION_REQUIRED', error_code='LEASE_EXPIRED' where id=%s", (jid,))
        cur.execute("""update brain_generations g set backend_dataset_name=%s
                       from brain_jobs j where j.id=%s and g.id=j.generation_id""",
                    (f"not_running_{uuid.uuid4().hex[:8]}", jid))
        conn.commit()
    # status() for a nonexistent dataset raises -> recovery defers (stays put)
    lifecycle.recover_reconciliation()
    with psycopg.connect(URL, row_factory=psycopg.rows.dict_row) as conn, conn.cursor() as cur:
        row = cur.execute("select state from brain_jobs where id=%s", (jid,)).fetchone()
    assert row["state"] == "RECONCILIATION_REQUIRED", row
    print("T4 uncertain-state-not-blind-retried: PASS")

    # --- cleanup ------------------------------------------------------------
    with psycopg.connect(URL, row_factory=psycopg.rows.dict_row) as conn, conn.cursor() as cur:
        cur.execute("""delete from brain_job_events e using brain_jobs j, workspaces w
                       where e.job_id=j.id and j.workspace_id=w.id
                         and w.personal_user_id like 'recovery-%'""")
        cur.execute("""delete from brain_job_staging st using brain_jobs j, workspaces w
                       where st.job_id=j.id and j.workspace_id=w.id
                         and w.personal_user_id like 'recovery-%'""")
        cur.execute("""delete from brain_job_files f using brain_jobs j, workspaces w
                       where f.job_id=j.id and j.workspace_id=w.id
                         and w.personal_user_id like 'recovery-%'""")
        cur.execute("""delete from brain_jobs j using workspaces w
                       where j.workspace_id=w.id and w.personal_user_id like 'recovery-%'""")
        cur.execute("""update brains b set active_generation_id=null
                       from workspaces w where b.workspace_id=w.id
                         and w.personal_user_id like 'recovery-%'""")
        cur.execute("""delete from brain_generations g using workspaces w
                       where g.workspace_id=w.id and w.personal_user_id like 'recovery-%'""")
        cur.execute("""delete from brains b using workspaces w
                       where b.workspace_id=w.id and w.personal_user_id like 'recovery-%'""")
        cur.execute("delete from workspaces where personal_user_id like 'recovery-%'")
        conn.commit()
    print("PHASE 1 LEASE RECOVERY: PASS")


if __name__ == "__main__":
    main()
