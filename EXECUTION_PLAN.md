# Kestrel Upgrade Completion — Execution Plan

Derives from `/private/tmp/prompt.md` (execution prompt) + `REALITY_CHECK.md`
(baseline review at `05b4289`). This is the plan; execution starts on approval.

## 0. Baseline state table (verified 2026-10-01, immediately pre-plan)

| Item | Value |
|---|---|
| Current commit | `05b4289` (docs: upgrade execution report) |
| Working tree | DIRTY — `app.py` (+3/−1), `lifecycle.py` (+5/−2): v2 identity-guard + UUID-serialization fixes, uncommitted |
| Live Cognee | `cognee/cognee:1.6.1` digest `sha256:db0973f4…`, healthy, RUNNING |
| Candidate | `kestrel-cognee:1.6.2-candidate` id `9afe3416a2df` (also `lab-cognee-v2test` running on :8892) |
| Feature flags | `KESTREL_JOBS_V2` unset (=OFF) everywhere; `ENABLE_BACKEND_ACCESS_CONTROL=false` pinned in `.env.oss` |
| Live migration head | `0002_identity_provenance_jobs` (11 new tables, all EMPTY on live) |
| Live row counts | brain_access=2, chats=3, turns=6, llm_calls=197, graph_node=93, graph_edge=161 |
| Tenant datasets | 1 (`company_brain`) |
| Manifest | `uploads.json`: 10 keys / 13 entries, all stale (deleted test brains) |
| Lab jobs | `itest3…` VERIFYING (ORPHANED — worker killed by app restart; lease expired 22:34Z; upstream pipeline actually ERRORED, 2 data items present); `itest-…` FAILED (honest) |
| Stuck test | 120-doc pagination: submissions never drained; lab candidate :8889 now UNHEALTHY |
| Frontend routing | React = chat surface + Connectors only; create/manage/graph `location.href` → legacy `/upload`, `/brains`, `/graph`; chat history = localStorage |
| LLM route (app) | `llm.py`: Token Harbor `deepseek-v4.1-flash:free` first, OpenRouter `deepseek/deepseek-v4.1-flash` fallback |
| Connectors | Slack: stub-tested (90/90) not live; Gmail/Drive: extras import in candidate, honest 503 (no founder OAuth config) |
| CI / deployment | none; marketing built, not deployed |
| Known gaps carried in | no lease-expiry reclaim; backfill never rehearsed; provenance tables unwired; v2 happy path never SUCCEEDED |

## 1. Execution order, gates, and work items

### Phase 0 — Freeze reality, clean the branch (S, half day)
- Work: review + keep the two uncommitted fixes; add regression test
  (`tests/test_lifecycle_identity.py`: `create_brain_v2(identity=None, …)` against
  the lab DB asserts a QUEUED job + personal workspace row); commit everything.
- Proof gate: `git status` clean; battery green (`./verify.sh`, requires port
  8000 → controlled live-app stop/restart, checksummed); commit hash recorded.
- Rollback: revert commit.

### Phase 1 — v2 worker recoverability (S–M, 1 day)
- Work: in `lifecycle.py` — (a) reclaim path: expired-lease jobs in
  `VERIFYING/INGESTING/EXTRACTING` transition to `RECONCILIATION_REQUIRED`
  (never auto-retry — upstream state is unknown), operator-visible via
  `/api/jobs/{id}`; (b) `claim_job` may then pick `RECONCILIATION_REQUIRED`
  jobs ONLY into a dedicated `verify-recover` routine that re-verifies
  inventory via paginated `data_items` + `/processing-status` before publishing
  or failing — no blind resubmission. Tests: unexpired lease not stolen;
  expired lease detected; orphan → documented recovery state; worker restart
  creates no duplicate processing; post-unknown-state job never blind-retried.
- Proof gate: all five test cases pass; the REAL orphaned job
  (`itest3…`, currently VERIFYING) transitions on first reclaim run and its
  honest terminal outcome (expected: FAILED via `DATASET_PROCESSING_ERRORED`)
  is recorded. Commit.
- Rollback: revert; stuck jobs remain stuck (current state).

### Phase 2 — Candidate lab proof (M, 1–2 days)
- Work: destroy the unhealthy :8889 lab container; keep :8892 (healthy) or a
  fresh one; delete the two v2 scratch brains/jobs from the lab DB for a clean
  slate (lab-only). Re-run:
  a) **v2 happy path**: create → SUCCEEDED → brain READY → generation ACTIVE →
     `generation_documents.backend_data_id` set → events ordered → known-answer
     ask with citations → source-open → idempotent replay (same result) →
     mismatched replay (409, `same_payload:false`).
  b) **failure path**: force a real pipeline failure (stub provider on a
     side container, as already proven once) → job FAILED, brain FAILED,
     no false READY.
  c) **pagination**: rewrite `ops/test_pagination.py` submission loop into
     batches of 20 (sleep between batches); require the printed marker
     `PAGINATION CONTRACT … PASS` + `/data/count` equality + healthy container
     through the run.
- Proof gate: all evidence under `var/evidence/<ts>/` (logs, DB dumps of
  job/generation/document rows); candidate digest recorded; no orphaned job
  counted as a pass.
- Rollback: lab-only; live untouched. Commit only if code changed.

### Phase 3 — Backfill rehearsal (S, half day)
- Work: fresh restore from the validated backup into the lab (`ops/restore_lab.sh`)
  → `alembic upgrade head` → run `ops/backfill.py` TWICE; capture before/after
  counts, ambiguous-record list, second-run diff (must be zero-change).
- Proof gate: first run passes with expected==actual; second run changes
  nothing (idempotent); reconciliation report saved to
  `var/evidence/<ts>/backfill-rehearsal.md`; ambiguous records explicitly
  listed (hghi/kestrel_full chats + 10 stale manifest keys).
- Rollback: lab-only.

### Phase 4 — Production-readiness gaps (M, 1–2 days)
1. `compose.cutover.yml` staged with the candidate image pinned by **digest**
   (`@sha256:9afe3416…`) + explicit `ENABLE_BACKEND_ACCESS_CONTROL` comment.
2. Cutover script rewritten from checklist to **executable gates** (real
   `test`/`curl`/`psql` checks, nonzero exit on any miss).
3. `:free` policy (D6) implemented: `llm.py` gains an `APP_ENV` gate —
   `local` (default) keeps Token Harbor `:free`; `beta` refuses it (paid
   DeepSeek route only). Encoded in code + env-names doc.
4. Rollback drill: `ops/rollback_drill.sh` — boot candidate on the lab copy,
   then restore the old backup + old image and prove old-image-reads-old-state
   (gates: datasets list, known-answer ask, graph_node count).
5. Fresh-bootstrap check: empty PG container → `storage.init()` → `alembic
   stamp 0001` → `upgrade head` → no-op; documented that `storage.init()`
   remains the bootstrap until migrations own the schema.
6. v2 authz allow/deny tests using `auth.inject_jwks_for_test` (two signed
   org identities): A reads A's job (allow), B denied (403), unknown job →
   same not-found contract.
- Proof gate: all checks executable and green; digests recorded; policy in
  code; authz tests pass; rollback drill log saved. Commit.

### Phase 5 — Live backfill (S, half day; authorized by prompt after 3+4)
- Work: fresh `ops/backup.sh`; verify SHA256SUMS; record commit + migration
  head; run `ops/backfill.py` on live; emit before/after + reconciliation;
  re-run read-only idempotency check; known-answer ask after.
- Proof gate: backup validates; counts reconcile; `brains`/`workspaces`
  nonzero as expected; ambiguous records preserved + reported; ask green.
  Any unexpected live-count change → stop + restore per runbook.
- Rollback: restore from the fresh backup (drilled path).

### Phase 6 — Cognee cutover (S execution + gates; FOUNDER-GATED)
- Work: unlock + execute `ops/cutover_162.sh` (Phase-4 hardened version):
  fresh backup → stop app → swap image (digest-pinned compose) → migrations →
  gates: version/digest, datasets, known-answer ask + source-open, counts,
  access-control behavior, log inspection for false-ready.
- Proof gate: live on candidate digest; baseline-equivalent answers; no count
  drift; rollback possible. Any gate failure → stop, roll back, report.
- Rollback: rehearsed in Phase 4.4.

### Phase 7 — `company_brain` rebuild as a new generation (M–L)
- Work: implement the `REBUILD` job kind in `lifecycle.py` (new generation for
  an existing brain from the approved corpus/; same worker flow; old generation
  RETIRED only after comparison; deletion of the old dataset deferred to
  approval). Run it for `company_brain`.
- Proof gate: document count matches corpus; known-answer references equivalent
  (or differences explained); all cited sources open; old generation retained;
  promotion recorded. Rollback: old generation/dataset intact until approval.

### Phase 8 — Durable citation path (M)
- Work: (a) at v2 verification, write `source_references` rows (backend data
  id → document_version; excerpt located within `exact_extracted_text` when
  evidence provides one, offsets null when not — recorded honestly);
  (b) `/api/source` prefers durable references when present, legacy behavior
  otherwise. Tests: v2 brain cites from tables; source-open after app restart;
  source-open with `uploads.json` temporarily absent; legacy brain unchanged;
  unmatched evidence → no citation; retired generation leaves no misleading
  references.
- Proof gate: end-to-end lab evidence + restart + legacy-compat logs.
- Rollback: read-path flag; legacy path intact.

### Phase 9 — React as the supported frontend (L, 2–4 days)
- Work: in `frontend/` — brain creation via `/api/brains/v2` (+ idempotency
  key), job progress via `/api/jobs/{id}` polling, brain list/selection from
  server (new lightweight GET or reuse `/api/brains`), server-backed chat
  history (wire existing `/api/chats*`), graph view ported or explicitly
  documented legacy-only for beta. Keep legacy as fallback; no undocumented
  redirects.
- Proof gate: browser smoke (create→ingest→ready→ask→cite→open→history
  survives restart) from React alone; no silent legacy redirects; mobile +
  desktop checks saved as evidence.
- Rollback: React changes are additive routes/components; legacy untouched.

### Phase 10 — Connector classification (S, no code)
- Work: documentation + UI status labels only: Slack = stub-tested/not live;
  Gmail/Drive = implemented-but-unconfigured (prerequisite list:
  GOOGLE_* OAuth client + founder test account). No enablement.
- Proof gate: honest statuses visible in app + docs.

### Phase 11 — CI + operational baseline (M)
- Work: GitHub Actions — (a) fast lane on push (`verify.sh --quick`), (b)
  scheduled/manual real-stack lane (candidate smoke against lab), (c) weekly
  backup+restore drill job; artifact retention; digest/env manifest script;
  worker job-drift visibility (stuck-job counter from `brain_jobs`).
- Proof gate: first green CI run; drill artifact saved.
- Rollback: CI changes only.

### Final gate
`UPGRADE_COMPLETION_REPORT.md` per the prompt's 17 sections, every claim
labeled done/partial/blocked/deferred with evidence paths + commit + digest,
"safe to claim" vs "unsafe to claim" lists. Working tree clean at the end.

## 2. Founder-input register (execution stops at these boundaries)

| # | Needed for | Phase | Blocking? |
|---|---|---|---|
| F1 | Approval to run live backfill (after Phase 3 gate passes) | 5 | yes |
| F2 | Cutover approval (after Phases 0–5 evidence) | 6 | yes |
| F3 | Rebuild-batch approval (after cutover) | 7 | yes |
| F4 | Google OAuth client + test account (Drive/Gmail) | 10 | blocks connectors only |
| F5 | `:free` policy confirmation (default implemented in Phase 4.3) | 4 | no — implemented, reversible |
| F6 | Graph-view-in-React vs documented-legacy for beta | 9 | shapes Phase 9 scope |

## 3. Standing rules during execution

- Live-app stop/restart only for battery runs and cutover, always checksummed
  before/after; never during founder activity without a note.
- Every commit message states its phase and proof-gate result.
- Evidence under `var/evidence/<phase>-<ts>/` (gitignored) with sanitized
  summaries into `docs/` when they belong in the permanent record.
- Stop-and-report on: any preservation-gate failure, any unexpected live count
  drift, any citation invariant change.
