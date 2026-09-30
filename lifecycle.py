"""Durable brain lifecycle (PR-7): jobs, worker, idempotency, fencing.

Flag-gated by KESTREL_JOBS_V2. The legacy create path in app.py remains the
default; nothing here runs unless the flag is on and the v2 routes are hit.

Design contract (implementation spec §2, condensed for the beta):
- 202 create: one transaction reserves workspace/brain/generation/job and
  stages raw file bytes; the tenant is NOT contacted in the request.
- worker: claims with FOR UPDATE SKIP LOCKED, leases the job, persists
  SUBMITTING before each network submission, treats post-submission failure
  as OUTCOME_UNKNOWN (job -> RECONCILIATION_REQUIRED, never blind retry).
- publish: only when brain.state, expected mutation_generation, lease and
  job state all still match. VERSIONED generations only (beta).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import logging
import os
import time
import uuid

import psycopg

log = logging.getLogger("kestrel.lifecycle")

WORKER_ID = f"worker-{os.getpid()}"
LEASE_MINUTES = 10
READY_TIMEOUT_S = 1800


class LifecycleError(RuntimeError):
    pass


class SlugConflict(LifecycleError):
    pass


class IdempotencyConflict(LifecycleError):
    pass


def _conn() -> psycopg.Connection:
    from storage import DATABASE_URL
    return psycopg.connect(DATABASE_URL, row_factory=psycopg.rows.dict_row)


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# create reservation (the 202 path)
# ---------------------------------------------------------------------------

def ensure_workspace(cur, identity: dict | None) -> str:
    identity = identity or {"user_id": "local", "org_id": None}
    org = identity.get("org_id")
    user = identity.get("user_id")
    if org:
        row = cur.execute(
            "select id from workspaces where clerk_org_id=%s", (org,)).fetchone()
        if row:
            return row["id"]
        ws = _uuid()
        cur.execute("insert into workspaces (id, clerk_org_id) values (%s,%s)", (ws, org))
        return ws
    row = cur.execute(
        "select id from workspaces where personal_user_id=%s", (user,)).fetchone()
    if row:
        return row["id"]
    ws = _uuid()
    cur.execute("insert into workspaces (id, personal_user_id) values (%s,%s)", (ws, user))
    return ws


def create_brain_v2(identity: dict, slug: str, files: list[tuple[str, bytes]],
                    idempotency_key: str) -> dict:
    """Reserve brain + job + staging in ONE transaction; returns 202 payload.

    Idempotency: same (workspace, idempotency_key) returns the existing job;
    the stored request_hash tells the caller whether the payload matched.
    """
    identity = identity or {"user_id": "local", "org_id": None}
    if not files:
        raise LifecycleError("No files were uploaded.")
    request_hash = hashlib.sha256(
        b"".join(sorted(n.encode() + b"\0" + b for n, b in files))).hexdigest()
    brain_id, generation_id, job_id = _uuid(), _uuid(), _uuid()
    backend_dataset_name = f"{slug}_{brain_id[:8]}"

    with _conn() as conn, conn.cursor() as cur:
        ws = ensure_workspace(cur, identity)

        prior = cur.execute(
            """select id, request_hash, state from brain_jobs
               where workspace_id=%s and idempotency_key=%s""",
            (ws, idempotency_key)).fetchone()
        if prior:
            raise IdempotencyConflict(json.dumps({
                "existing_job": str(prior["id"]),
                "same_payload": prior["request_hash"] == request_hash,
            }))

        try:
            cur.execute(
                """insert into brains (id, workspace_id, slug, display_name, owner_user_id,
                                        visibility, kind, storage_mode, state)
                   values (%s,%s,%s,%s,%s,'PRIVATE','UPLOAD','VERSIONED','CREATING')""",
                (brain_id, ws, slug, slug, identity.get("user_id")))
        except psycopg.errors.UniqueViolation:
            raise SlugConflict(
                f"A brain called '{slug}' already exists in this workspace.")

        cur.execute(
            """insert into brain_generations (id, brain_id, workspace_id, generation_number,
                                backend_dataset_name, state, publication_mode)
               values (%s,%s,%s,1,%s,'BUILDING','VERSIONED')""",
            (generation_id, brain_id, ws, backend_dataset_name))
        cur.execute(
            """update brains set active_generation_id=%s where id=%s""",
            (generation_id, brain_id))
        try:
            cur.execute(
                """insert into brain_jobs (id, workspace_id, brain_id, generation_id, kind, state,
                              idempotency_key, request_hash)
                   values (%s,%s,%s,%s,'CREATE','QUEUED',%s,%s)""",
                (job_id, ws, brain_id, generation_id, idempotency_key, request_hash))
        except psycopg.errors.UniqueViolation:
            # raced with a concurrent same-key create: this reservation is the loser
            raise IdempotencyConflict(json.dumps({"existing_job": "concurrent"}))
        for i, (filename, content) in enumerate(files):
            client_file_id = f"{i}:{filename}"
            cur.execute(
                """insert into brain_job_files (id, job_id, brain_id, client_file_id, stage)
                   values (%s,%s,%s,%s,'QUEUED')""",
                (_uuid(), job_id, brain_id, client_file_id))
            cur.execute(
                """insert into brain_job_staging (id, job_id, client_file_id, filename,
                                content_bytes, sha256, size_bytes)
                   values (%s,%s,%s,%s,%s,%s,%s)""",
                (_uuid(), job_id, client_file_id, filename, content,
                 hashlib.sha256(content).hexdigest(), len(content)))
    return {"brain_id": brain_id, "job_id": job_id, "state": "QUEUED",
            "status_url": f"/api/jobs/{job_id}",
            "documents_url": f"/api/brains/{brain_id}/documents"}


# ---------------------------------------------------------------------------
# worker
# ---------------------------------------------------------------------------

def claim_job() -> dict | None:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""update brain_jobs set state='EXTRACTING', lease_owner=%s,
                    lease_expires_at=now() + interval '{LEASE_MINUTES} minutes',
                    lease_generation=lease_generation+1, attempt=attempt+1,
                    updated_at=now()
               where id = (select id from brain_jobs
                            where state='QUEUED' and cancel_requested_at is null
                            order by created_at limit 1 for update skip locked)
               returning *""", (WORKER_ID,))
        return cur.fetchone()


def _job_event(cur, job_id: str, event: dict) -> None:
    cur.execute(
        """insert into brain_job_events (job_id, seq, event)
           values (%s, (select coalesce(max(seq),0)+1 from brain_job_events where job_id=%s), %s)""",
        (job_id, job_id, json.dumps(event)))


def _fail(cur, job_id: str, brain_id: str, code: str) -> None:
    cur.execute(
        "update brain_jobs set state='FAILED', error_code=%s, updated_at=now() where id=%s",
        (code, job_id))
    cur.execute(
        """update brains set state = case when state='CREATING' then 'FAILED' else state end,
               mutation_generation = mutation_generation + 1 where id=%s""", (brain_id,))
    _job_event(cur, job_id, {"event": "failed", "code": code})


def _cancel_requested(cur, job_id: str) -> bool:
    row = cur.execute("select cancel_requested_at from brain_jobs where id=%s", (job_id,)).fetchone()
    return bool(row and row["cancel_requested_at"])


def process_job(job: dict) -> None:
    job_id, brain_id, generation_id = job["id"], job["brain_id"], job["generation_id"]
    import documents as documents_mod
    import cognee_cloud as cc

    with _conn() as conn, conn.cursor() as cur:
        staged = cur.execute(
            """select client_file_id, filename, content_bytes, sha256
               from brain_job_staging where job_id=%s order by client_file_id""", (job_id,)).fetchall()
        gen = cur.execute(
            "select backend_dataset_name from brain_generations where id=%s",
            (generation_id,)).fetchone()
        mutation = cur.execute(
            "select mutation_generation from brains where id=%s", (brain_id,)).fetchone()["mutation_generation"]
    backend_dataset = gen["backend_dataset_name"]

    # EXTRACTING
    docs, failures = asyncio.run(asyncio.to_thread(
        documents_mod.extract_many,
        [(s["filename"], bytes(s["content_bytes"])) for s in staged]))
    with _conn() as conn, conn.cursor() as cur:
        if _cancel_requested(cur, job_id):
            cur.execute("update brain_jobs set state='CANCELLED', updated_at=now() where id=%s", (job_id,))
            cur.execute("update brains set state='FAILED', mutation_generation=mutation_generation+1 where id=%s", (brain_id,))
            conn.commit()
            return
        for s in staged:
            matched = next((d for d in docs if d["name"] == s["filename"]), None)
            if matched:
                doc_id, dv_id = _uuid(), _uuid()
                cur.execute(
                    """insert into documents (id, brain_id, workspace_id, filename, origin, lifecycle_state)
                       values (%s, %s, (select workspace_id from brains where id=%s), %s, 'UPLOAD', 'ACTIVE')""",
                    (doc_id, brain_id, brain_id, s["filename"]))
                cur.execute(
                    """insert into document_versions (id, document_id, brain_id, workspace_id,
                            original_sha256, exact_extracted_text, text_sha256, extraction_report)
                       values (%s, %s, %s, (select workspace_id from brains where id=%s),
                               %s, %s, %s, %s)""",
                    (dv_id, doc_id, brain_id, brain_id, s["sha256"], matched["text"],
                     hashlib.sha256(matched["text"].encode()).hexdigest(),
                     json.dumps({"name": matched["name"], "chars": matched["chars"]})))
                cur.execute(
                    """update brain_job_files set stage='EXTRACTED', document_version_id=%s
                       where job_id=%s and client_file_id=%s""",
                    (dv_id, job_id, s["client_file_id"]))
            else:
                err = next((f.get("error", "unreadable") for f in failures
                            if f.get("name") == s["filename"]), "unreadable")
                cur.execute(
                    """update brain_job_files set stage='FAILED', outcome=%s
                       where job_id=%s and client_file_id=%s""",
                    (str(err)[:200], job_id, s["client_file_id"]))
        _job_event(cur, job_id, {"event": "extracted", "docs": len(docs), "failures": len(failures)})
        if not docs:
            _fail(cur, job_id, brain_id, "NO_EXTRACTABLE_DOCUMENTS")
            conn.commit()
            return
        cur.execute("update brain_jobs set state='INGESTING', updated_at=now() where id=%s", (job_id,))
        conn.commit()

    # INGESTING — SUBMITTING persisted before each network call
    submissions: dict[str, str] = {}
    for d in docs:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                """update brain_job_files f set stage='SUBMITTING'
                   from brain_job_staging st
                   where st.job_id=f.job_id and st.client_file_id=f.client_file_id
                     and f.job_id=%s and st.filename=%s""",
                (job_id, d["name"]))
            conn.commit()
        try:
            cc.remember(d["text"], backend_dataset, None, True, d["name"])
            submissions[d["name"]] = "ACCEPTED"
        except Exception as exc:  # noqa: BLE001
            submissions[d["name"]] = f"ERROR:{str(exc)[:120]}"
            log.warning("submit failed for %s: %s", d["name"], str(exc)[:120])
    with _conn() as conn, conn.cursor() as cur:
        for name, outcome in submissions.items():
            cur.execute(
                """update brain_job_files f set
                     stage = case when %s like 'ERROR%%' then 'FAILED' else 'PROCESSING' end,
                     outcome = %s
                   from brain_job_staging st
                   where st.job_id=f.job_id and st.client_file_id=f.client_file_id
                     and f.job_id=%s and st.filename=%s""",
                (outcome, outcome, job_id, name))
        _job_event(cur, job_id, {"event": "submitted", "outcomes": submissions})
        conn.commit()

    if any(v.startswith("ERROR") for v in submissions.values()):
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                """update brain_jobs set state='RECONCILIATION_REQUIRED',
                       error_code='SUBMIT_ERRORS', updated_at=now() where id=%s""", (job_id,))
            _job_event(cur, job_id, {"event": "reconciliation_required"})
            conn.commit()
        return

    # VERIFYING
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("update brain_jobs set state='VERIFYING', updated_at=now() where id=%s", (job_id,))
        conn.commit()
    try:
        cc.wait_ready(backend_dataset, READY_TIMEOUT_S, 10)
    except Exception as exc:  # noqa: BLE001
        with _conn() as conn, conn.cursor() as cur:
            _fail(cur, job_id, brain_id, f"PIPELINE:{str(exc)[:140]}")
            conn.commit()
        return
    gen_row = None
    with _conn() as conn, conn.cursor() as cur:
        gen_row = cur.execute(
            "select backend_dataset_id from brain_generations where id=%s",
            (generation_id,)).fetchone()
    ds_id = gen_row["backend_dataset_id"] or cc.resolve_id(backend_dataset)
    by_name = {i.get("name"): i.get("id") for i in cc.data_items(ds_id) if isinstance(i, dict)}
    verified = 0
    with _conn() as conn, conn.cursor() as cur:
        for row in cur.execute(
                """select f.client_file_id, f.document_version_id, st.filename
                   from brain_job_files f
                   join brain_job_staging st on st.job_id=f.job_id and st.client_file_id=f.client_file_id
                   where f.job_id=%s and f.document_version_id is not null""",
                (job_id,)).fetchall():
            data_id = by_name.get(row["filename"])
            if data_id:
                cur.execute(
                    """insert into generation_documents
                       (generation_id, document_version_id, brain_id, workspace_id,
                        backend_data_id, verified_at)
                       values (%s,%s,%s,(select workspace_id from brains where id=%s),%s,now())
                       on conflict (generation_id, document_version_id) do update
                         set backend_data_id=excluded.backend_data_id, verified_at=now()""",
                    (generation_id, row["document_version_id"], brain_id, brain_id, data_id))
                cur.execute(
                    """update brain_job_files set stage='PROVENANCE_VERIFIED'
                       where job_id=%s and client_file_id=%s""", (job_id, row["client_file_id"]))
                verified += 1
        conn.commit()

    # PUBLISH — fenced
    with _conn() as conn, conn.cursor() as cur:
        brain = cur.execute(
            "select state, mutation_generation from brains where id=%s", (brain_id,)).fetchone()
        job_now = cur.execute(
            "select lease_owner, state, cancel_requested_at from brain_jobs where id=%s",
            (job_id,)).fetchone()
        ok = (brain["state"] == "CREATING"
              and brain["mutation_generation"] == mutation
              and job_now["lease_owner"] == WORKER_ID
              and not job_now["cancel_requested_at"]
              and job_now["state"] not in ("CANCELLED",))
        if not ok:
            cur.execute(
                """update brain_jobs set state='RECONCILIATION_REQUIRED',
                       error_code='PUBLISH_FENCED', updated_at=now() where id=%s""", (job_id,))
            _job_event(cur, job_id, {"event": "publish_fenced"})
            conn.commit()
            return
        cur.execute(
            """update brain_generations set state='ACTIVE', backend_dataset_id=%s,
                   inventory_verified_at=now() where id=%s""", (ds_id, generation_id))
        cur.execute(
            "update brains set state='READY', active_generation_id=%s where id=%s",
            (generation_id, brain_id))
        cur.execute("update brain_jobs set state='SUCCEEDED', updated_at=now() where id=%s", (job_id,))
        _job_event(cur, job_id, {"event": "published", "verified": verified})
        cur.execute("delete from brain_job_staging where job_id=%s", (job_id,))
        conn.commit()


def reclaim_expired_leases() -> int:
    """Phase 1: an orphaned job (worker died mid-EXTRACTING/INGESTING/VERIFYING)
    must never remain invisible. Expired-lease active jobs move to
    RECONCILIATION_REQUIRED — the recovery routine (not a blind retry) decides
    the honest outcome from the upstream pipeline state."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            """update brain_jobs set state='RECONCILIATION_REQUIRED',
                   error_code='LEASE_EXPIRED', lease_owner=null,
                   lease_expires_at=null, updated_at=now()
               where state in ('EXTRACTING','INGESTING','VERIFYING')
                 and lease_expires_at is not null and lease_expires_at < now()""")
        n = cur.rowcount
        if n:
            conn.commit()
            log.warning("reclaimed %d expired-lease job(s) -> RECONCILIATION_REQUIRED", n)
        return n


def recover_reconciliation(max_attempts: int = 3) -> int:
    """Decide the honest outcome for RECONCILIATION_REQUIRED jobs.

    Upstream state rules the result: pipeline ERRORED/FAILED -> job FAILED;
    COMPLETED -> verify inventory and publish if fully verifiable; still
    running -> left alone. Jobs are never resubmitted here. After
    max_attempts inconclusive passes the job FAILs visibly instead of
    hiding forever.
    """
    import cognee_cloud as cc
    handled = 0
    with _conn() as conn, conn.cursor() as cur:
        jobs = cur.execute(
            """select id, brain_id, generation_id, attempt from brain_jobs
               where state='RECONCILIATION_REQUIRED'
                 and (lease_expires_at is null or lease_expires_at < now())
               order by created_at limit 5 for update skip locked""").fetchall()
    for job in jobs:
        job_id, brain_id, generation_id = job["id"], job["brain_id"], job["generation_id"]
        with _conn() as conn, conn.cursor() as cur:
            gen = cur.execute(
                "select backend_dataset_name, backend_dataset_id from brain_generations where id=%s",
                (generation_id,)).fetchone()
        if not gen:
            with _conn() as conn, conn.cursor() as cur:
                _fail(cur, job_id, brain_id, "RECOVERY:NO_GENERATION")
                conn.commit()
            handled += 1
            continue
        name = gen["backend_dataset_name"]
        try:
            state = cc.status(name)
            kind = cc.terminal_kind(state)
        except Exception as exc:  # noqa: BLE001 - tenant down: stay put
            log.warning("recovery deferred for %s: %s", job_id, str(exc)[:120])
            continue
        with _conn() as conn, conn.cursor() as cur:
            if kind == "failure":
                _fail(cur, job_id, brain_id, f"RECOVERY:PIPELINE_ERRORED")
                conn.commit()
                handled += 1
                continue
            if kind == "success":
                ds_id = gen["backend_dataset_id"] or _resolve_dataset(name)
                items = cc.data_items(ds_id)
                by_name = {i.get("name"): i.get("id") for i in items if isinstance(i, dict)}
                rows = cur.execute(
                    """select f.client_file_id, st.filename from brain_job_files f
                       join brain_job_staging st on st.job_id=f.job_id
                                            and st.client_file_id=f.client_file_id
                       where f.job_id=%s and f.document_version_id is not null""",
                    (job_id,)).fetchall()
                unverified = [r["filename"] for r in rows if by_name.get(r["filename"]) is None]
                brain = cur.execute(
                    "select state, mutation_generation from brains where id=%s", (brain_id,)).fetchone()
                if unverified or brain["state"] != "CREATING":
                    cur.execute(
                        """update brain_jobs set error_code='RECOVERY:INVENTORY_INCOMPLETE',
                               attempt=attempt+1, updated_at=now() where id=%s""", (job_id,))
                    _job_event(cur, job_id, {"event": "recovery_incomplete",
                                             "unverified": unverified})
                    if job["attempt"] + 1 >= max_attempts:
                        _fail(cur, job_id, brain_id, "RECOVERY:UNRESOLVED")
                    conn.commit()
                    handled += 1
                    continue
                cur.execute(
                    """update brain_generations set state='ACTIVE', backend_dataset_id=%s,
                           inventory_verified_at=now() where id=%s""", (ds_id, generation_id))
                cur.execute(
                    "update brains set state='READY', active_generation_id=%s where id=%s",
                    (generation_id, brain_id))
                cur.execute(
                    """update brain_jobs set state='SUCCEEDED', error_code=null,
                           updated_at=now() where id=%s""", (job_id,))
                _job_event(cur, job_id, {"event": "recovered_published", "verified": len(rows)})
                cur.execute("delete from brain_job_staging where job_id=%s", (job_id,))
                conn.commit()
                handled += 1
                continue
            # still running upstream: leave for a later pass
    return handled


def worker_loop(poll_seconds: float = 2.0) -> None:
    log.info("lifecycle worker %s started", WORKER_ID)
    while True:
        try:
            reclaim_expired_leases()
            if recover_reconciliation() == 0:
                job = claim_job()
                if job:
                    process_job(job)
                else:
                    time.sleep(poll_seconds)
        except Exception as exc:  # noqa: BLE001 - the worker never dies
            log.exception("worker iteration failed: %s", str(exc)[:200])
            time.sleep(poll_seconds)


def start_worker() -> None:
    import threading
    threading.Thread(target=worker_loop, name="kestrel-lifecycle-worker", daemon=True).start()


def job_status(job_id: str) -> dict | None:
    with _conn() as conn, conn.cursor() as cur:
        job = cur.execute("select * from brain_jobs where id=%s", (job_id,)).fetchone()
        if not job:
            return None
        files = cur.execute(
            "select client_file_id, stage, outcome, warning from brain_job_files "
            "where job_id=%s order by client_file_id", (job_id,)).fetchall()
        events = cur.execute(
            "select seq, ts, event from brain_job_events where job_id=%s order by seq",
            (job_id,)).fetchall()
        return {"job": job, "files": files, "events": events}


def request_cancel(job_id: str) -> bool:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "update brain_jobs set cancel_requested_at=now(), updated_at=now() where id=%s",
            (job_id,))
        return cur.rowcount > 0
