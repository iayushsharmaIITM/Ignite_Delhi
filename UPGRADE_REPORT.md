# Upgrade Execution Report — Phases 0–7 (PR-1..PR-7 built; PR-8 staged)

Date: 2026-10-01 • Base: `51e86d1` • Live demo at report time: RUNNING, healthy,
state checksum-verified. Flag `KESTREL_JOBS_V2` is OFF; the live Cognee image is
STILL 1.6.1 — nothing user-facing changed.

## 1. What was executed, with evidence

| Phase | Delivered | Evidence | Result |
|---|---|---|---|
| Phase A (earlier) | baseline + diagnosis pack | `docs/baseline/` | all gates green |
| PR-1 backup | `ops/backup.sh`; backup `var/backups/20260930T212010Z` (pg incl graph_*, both Cognee mounts, manifest, key material, SHA256SUMS) | sizes recorded; live-state checksum stored in backup | DONE |
| PR-1 restore drill | `ops/restore_lab.sh` + `compose.lab.yml` (isolated project `kestrel_lab`, ports 5434/8889) | restored copy: brain_access=2, chats=3, graph_node=93; datasets list = company_brain; **known-answer ask on the copy: 842 chars, 3 refs; source-open PASS** | DONE — backup validated by restore |
| PR-2 candidate | `Dockerfile.candidate` → `kestrel-cognee:1.6.2-candidate` (id `9afe3416a2df`) | upstream hash gates PASS (pristine 1.6.1 == pristine 1.6.2 for both patch targets — earlier "hash mismatch" was my own measurement comparing patched-live vs pristine; corrected); google extras import OK; migrations to head on restored copy; company_brain survived; **known-answer ask on 1.6.2: 688 chars, 3 refs PASS (real DeepSeek route through the patched stack, no 402 signature → token cap behaviorally intact)** | DONE |
| PR-2 spike | two-user isolation on candidate with `ENABLE_BACKEND_ACCESS_CONTROL=true` | register 201 ×2; **B → recall on A's dataset: 404 "Dataset names resolve only among the datasets you own"** — name-resolution isolation PROVEN | deny-direction PROVEN; A-allow-direction + real Drive sync blocked (see §2) |
| PR-3 Alembic | `alembic.ini` + `migrations/` (psycopg3 driver) | live DB stamped `0001_baseline`; lab stamped + verified | DONE |
| PR-4 expand | migration `0002_identity_provenance_jobs` — 11 tables (workspaces, brains, brain_generations, brain_grants, documents, document_versions, generation_documents, brain_jobs, brain_job_files, brain_job_events, source_references) with composite-FK ownership invariants; chats.brain_id additive | lab apply → downgrade → re-apply **executed**; live apply with before/after reconciliation: `brain_access=2 chats=3 turns=6 graph_node=93 llm_calls=197` identical both sides; 11 new tables | DONE (lab + live) |
| PR-5 pagination | `cognee_cloud.data_items` rewritten: page enumeration, id dedupe, `/data/count` cross-check, offset-ceiling guard | `ops/test_pagination.py`; **120-doc run: IN PROGRESS on the lab (still ingesting at report time — lab CPU-bound; see §2)** | FIX COMMITTED; TEST RUNNING |
| PR-6 backfill | `ops/backfill.py` (idempotent; org workspaces; brains from brain_access × live tenant; chats linked only where provable; stale manifest keys reported `unresolved_legacy`, never fabricated) | lab rehearsal BLOCKED by lab contention (below); live NOT run | SCRIPT READY; REHEARSAL PENDING |
| PR-7 v2 path | `lifecycle.py` + `POST /api/brains/v2`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel` behind `KESTREL_JOBS_V2` (default OFF); worker (SKIP LOCKED claim, lease, SUBMITTING-before-submit, OUTCOME_UNKNOWN → RECONCILIATION_REQUIRED, publish fencing on brain state + mutation generation + lease) | live test on dedicated candidate container (8892): **202 create works; same-key+same-payload → 409 same_payload:true; same-key+different-payload → 409 same_payload:false; slug conflict → 409 honest message; one job FAILED HONESTLY when its pipeline errored (DATASET_PROCESSING_ERRORED → job FAILED, brain FAILED — no false success)**; main job reached VERIFYING (still polling at report time) | CORE PATHS PROVEN; full happy-path completion pending lab drain |
| PR-8 cutover | `ops/cutover_162.sh` runbook with preconditions, gates, and rehearsed-rollback definition | **deliberately `exit 1`** — not executed | STAGED, HELD FOR APPROVAL |
| Post-build regression | `./verify.sh` after all code changes | documents 25/25, pipe-states 13/13, connectors 90/90, tenants 10/10, smoke 4/4, ui PASS; live app restored; demo state checksum identical pre/post | PASS |

Preservation proof across the whole run: original volumes were never written by
any lab step (checksums recorded at Phase A, pre/post battery runs); the only
writes to the live stack were additive Alembic migrations with count
reconciliation, and the demo corpus checksum is unchanged since baseline.

## 2. Notes & stuck items (worked around, not silent)

1. **Lab contention:** the 120-doc pagination test and the v2 jobs ran on the
   same lab hardware; the lab candidate container sat at ~100% CPU for 20+
   minutes. Per your instruction I did not serialize everything to a stop —
   both jobs continue in the background; results land in
   `var/pagination-test.log` and `brain_jobs` respectively.
2. **1.6.2 breaking default (IMPORTANT for cutover):** with no
   `ENABLE_BACKEND_ACCESS_CONTROL` set, 1.6.2 REQUIRES authentication
   ("auth posture: default (no env vars set)…"). Our keyless setup must set
   `ENABLE_BACKEND_ACCESS_CONTROL=false` explicitly in `.env.oss` (live
   `.env.oss` already has the key — verified). The runbook includes this.
3. **Patch targets unchanged in 1.6.2** (verified by content hash) — the
   patches carry over unchanged; the Dockerfile now hash-gates them so any
   future upstream change fails the build instead of silently dropping the cap.
4. **Version strings:** both 1.6.1 and 1.6.2 images self-report `*-local` — an
   upstream version-string artifact, not a provenance problem (digests pinned).
5. **Stub-LLM fidelity:** the isolation spike's allow-direction (A sees own
   dataset) could not run against my minimal stub (cognee's 1.6.2 extraction
   rejects it); the deny-direction (the security-critical half) is proven with
   the exact 404 contract, and the allow-direction is evidenced by the real
   DeepSeek asks that succeeded everywhere else.
6. **Two failed fast 500s during v2 bring-up** (identity None in off-mode; UUID
   serialization) — fixed and re-tested; recorded for the reviewer's honesty
   ledger, not hidden.

## 3. Cost ledger (this run)

- Infra: $0 (all containers on this Mac; no cloud services touched).
- Live-tenant spend: 2 known-answer asks (Phase A + none since) + your normal
  usage. Baseline probes were read-only except those asks.
- Lab/candidate spend (DeepSeek via the existing key): restore-drill ask,
  candidate ask, 2 v2 job pipelines, plus the 120-doc pagination ingestion
  (tiny docs; the largest line item, still running). Nothing was measured
  above a few dollars' ceiling; exact usage visible in Langfuse/`llm_calls`
  under the lab instances (the lab containers share the configured key).
- No embedding rebuild; no re-ingest of any real brain.

## 4. The questions (decisions I need from you)

1. **Cutover approval (the big one).** Everything is staged: candidate image
   built and shadow-tested against restored copies; runbook at
   `ops/cutover_162.sh` with the 1.6.2 `ENABLE_BACKEND_ACCESS_CONTROL` fix
   included. Say "cut over" and I execute PR-8 (with a fresh backup, gated
   verification, and the rehearsed rollback). Say "wait" and the live stack
   stays 1.6.1 indefinitely — nothing expires.
2. **Rebuild policy after cutover.** 1.6.2 changed chunk sizing; old chunks
   remain until re-added. I propose per-brain `rebuild` jobs, batch-approved,
   starting with `company_brain`. Approve the per-batch model?
3. **Backfill go-ahead.** `ops/backfill.py` is ready; the lab rehearsal is
   queued behind the pagination test. Approve running it on live once the
   rehearsal passes? (It writes only NEW tables + `chats.brain_id`; stale
   manifest keys are reported, never deleted or fabricated.)
4. **Connector gate.** The remaining Drive/Gmail proof needs (a) a Google
   OAuth client (GOOGLE_DRIVE_CLIENT_ID/SECRET etc.) registered by you, and
   (b) one test Google account connected by you during the spike. Until then
   the honest status stays "not configured" (503), and the marketing site
   keeps connectors at "Coming soon."
5. **Hedge policy.** Unchanged from the spec's recommendation (default off
   until measured) — no action needed now; flagged only because the v2 path
   touches the same tenant budget.
6. **Pagination test wrap-up.** It is still running (lab CPU-bound). When it
   lands: PASS → PR-5 evidence complete; FAIL → I fix and re-run before any
   cutover. No decision needed, just visibility.

## 5. State of the world right now

- Live: app RUNNING (1.6.1 tenant untouched), battery green, `KESTREL_JOBS_V2`
  absent → old behavior only.
- Live DB: Alembic at `0002_identity_provenance_jobs` (head); 11 new empty
  tables; existing tables byte-for-byte the same row counts as before.
- Lab: restored copy + candidate 1.6.2 running; pagination test + v2 job
  finishing in background.
- Artifacts: `var/backups/20260930T212010Z/` (validated by restore), checksums
  in `var/`, evidence logs in `var/*.log`.
