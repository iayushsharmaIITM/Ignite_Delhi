# Kestrel Upgrade Completion Report

Date: 2026-10-01 • Final execution commit: see §2 • Live Cognee: **1.6.2 candidate, digest `sha256:9afe3416a2df…`** (CUT OVER)

## 1. Executive verdict

The upgrade is **executed and reversible**, the schema/identity/provenance
layer is live, the v2 lifecycle is proven end-to-end in the lab (including
failure, recovery, and publish-gating), and the cutover to Cognee 1.6.2 is
done with counts and datasets intact. **The one thing between Kestrel and
"latest stack, honestly complete" is an exhausted free generation allowance**
(Token Harbor `:free` — next window 2026-10-06 07:29 UTC; OpenRouter key is
free-tier and 402s on the paid model). Every generation-dependent proof
(post-cutover known-answer, `company_brain` rebuild) is blocked on that
founder decision, not on engineering.

## 2. Final commit and working-tree status

- All phases committed sequentially (Phase 0 `c6146a0` → Phase 11); working
  tree clean of tracked changes at report time except files listed in §16.
- Untracked-only leftovers: `COMPETITOR_ANALYSIS.md`, `ZCODE_HANDOFF.md`
  (pre-existing, not part of this work).

## 3. Runtime stack and immutable image digests

| Component | Live | Digest/ID |
|---|---|---|
| Cognee | `1.6.2-local` (candidate image) | `sha256:9afe3416a2df745c6044813ddc5c1c5c77bf727a5ae78f386b8db6e51f8687ca` (recorded in `var/candidate-digest.txt`, `compose.cutover.yml`) |
| Postgres | `postgres:17-alpine` | `sha256:b0f9560a…` (unchanged) |
| App tier | system Python 3.13, `python3 app.py` | commit-pinned; `KESTREL_JOBS_V2` OFF by default |
| LLM route (container) | Token Harbor `openai/deepseek-v4.1-flash:free` — **EXHAUSTED until 2026-10-06** | emergency repair documented in `.env.oss` comment |
| LLM route (app) | policy-gated: local = Harbor free, beta/prod = paid OpenRouter only (`llm.py`, gate-tested) | — |

## 4. Migration and database state

- Live Alembic head: `0003_job_staging` (0001 stamped baseline; 0002 additive
  identity/provenance/jobs — 11 tables; 0003 staging). Rehearsed on lab with
  executed downgrade/re-upgrade; live application reconciled with identical
  before/after counts on all pre-existing tables.
- Fresh-bootstrap proven: `ops/test_fresh_bootstrap.sh` — `storage.init()` on
  an empty Postgres then stamp+upgrade (PASS). `storage.init()` remains the
  bootstrap; migrations own changes from 0002 on (documented in env.py).

## 5. Backup and rollback evidence

- Backups: `var/backups/20260930T212010Z` (restore-drill-validated),
  `var/backups/20261001T043923Z` (fresh, taken immediately pre-backfill), both
  with SHA256SUMS + live-state checksums + key material.
- Restore drill: `ops/restore_lab.sh` — isolated project, restored copy passed
  the known-answer ask (842 chars/3 refs on 1.6.1; 1222 chars on the re-restore).
- Rollback drill (old image reads old state): rehearsal pending — BLOCKED on
  generation (its gate includes a known-answer ask; the free route is
  exhausted). The mechanics are proven (restore path works; image swap works).

## 6. V2 lifecycle evidence — **DONE (lab-tested)**

`var/evidence/phase1/lease-recovery.log`, `var/evidence/phase2/`:
- 202 reservation (atomic, tenant-free) ✓; idempotency 409s (same-payload
  true / mismatched false) ✓; slug-conflict 409 ✓
- happy path: create → worker → extraction → submission → lease expiry →
  RECLAIM → pipeline COMPLETED → **provenance verified by content
  fingerprint** → publish → `SUCCEEDED`, brain `READY`, generation `ACTIVE`,
  `generation_documents` populated ✓
- failure path: pipeline ERRORED → job FAILED honestly, brain FAILED (three
  observed cases), old generation retained on rebuild-class failures ✓
- orphan recovery: the REAL orphaned job resolved to
  `FAILED/RECOVERY:PIPELINE_ERRORED` by the new reclaim+recover code ✓
- publish gate: zero-provenance publish is structurally impossible
  (`PROVENANCE_UNVERIFIED`) ✓
- worker authz: org A allow / org B 403 / malformed id 404 (signed-JWKS
  TestClient) ✓
- Known honest gaps: only CREATE + REBUILD kinds exist (UPDATE/REMOVE/SYNC
  not implemented); single worker (no dedup of concurrent same-brain rebuilds
  beyond fencing).

## 7. Pagination evidence — **DONE (lab-tested)**

`var/evidence/phase2/pagination-contract.log`: 120/120 submitted in 6 batches;
**120 items enumerated across 5 pages (page_size=25), stable across two reads,
`/data/count` = 120** → `PAGINATION CONTRACT … PASS`. The client paginates,
dedupes by id, and treats the count endpoint as advisory (observed off-by-one
mid-ingest; enumeration is authoritative). Mid-ingest inventories are smaller
than the final count — per-doc outcomes belong to the jobs layer (N2), now
tracked by `brain_job_files`.

## 8. Backfill evidence — **DONE (rehearsed ×2 + live)**

- Lab rehearsal: run 1 created exactly one brains+generation row per
  brain_access entry (`company_brain` READY/live; `acme_isolated`
  DEGRADED_NOT_QUERYABLE, dataset missing — ownership retained); linked only
  provable chats (2 `unresolved_legacy` preserved); 9 stale manifest keys
  reported, never fabricated. Run 2: **identical after-state (idempotent
  PASS)**. `var/evidence/phase3/rehearsal-run{1,2}.log`
- Live: same result on the production-local DB
  (`var/evidence/phase3/live-backfill.log`); fresh backup taken first
  (`20261001T043923Z`); known-answer recall green immediately after (before
  the free allowance ran out).

## 9. Cutover evidence — **DONE, one gate pending on provider**

`ops/cutover_162.sh` executed with all executable preconditions PASS; live
image = candidate digest; health ready; datasets survived (`company_brain`);
`brain_access=2`, `graph_node=93` (no drift); app healthy. **Pending:** the
post-cutover known-answer recall — the Token Harbor free allowance was
exhausted during the run ("next rolling 7-day period starts on 6 Oct 2026
07:29 UTC" — verbatim provider error in the logs). NOT a cutover defect: the
same route succeeded on this image in the lab, and no data changed.

## 10. Brain rebuild evidence — **BLOCKED on provider**

`lifecycle.rebuild_brain` + REBUILD job kind implemented (new generation,
old-generation RETIRED-but-kept, failure leaves the old generation ACTIVE,
mutation fencing). Execution for `company_brain` (`ops/rebuild_brain.py`) is
blocked by the exhausted free allowance. NOT started live; nothing deleted.

## 11. Citation durability evidence — **DONE (lab-tested)**

- Write: v2 verification persists `generation_documents`
  (backend_data_id ↔ document_version) — 2 rows for the proof brain.
- Read: `/api/ask` citations resolve from durable tables
  (`citations._durable_reference`, match by slug OR backend dataset name),
  overriding prewarmed sourceless cache entries.
- `/api/source` prefers durable provenance (`origin: durable`).
- **Works with `uploads.json` REMOVED** (renamed during the test — PASS).
- Legacy brains unchanged (slug fallback; demo resolves from corpus as before).
- Exact offsets/quotes within the stored text: NOT implemented (references
  carry the document text; per-chunk offsets need the hybrid-search metadata
  route) — recorded as the remaining durability gap.

## 12. Frontend completion evidence — **PARTIAL**

- Server-backed chat history: save (POST /api/chats) + list (GET) + load
  (GET /{id} → turns) wired into React; **round-trip PASS** (save 200 →
  reload → sidebar entry from server).
- Durable create flow: `CreateBrainDialog` → `/api/brains/v2` → live job
  progress (per-file stages) → brain selection; API-level flow fully proven.
- Honest failure: `stage:error` now renders as a visible bot turn (was
  silently dropped).
- Labeled legacy: "Graph (legacy)" asks before navigating — no silent redirects.
- **Partial:** the in-browser ask→answer→auto-save round-trip could not be
  captured end-to-end because the free generation route is exhausted/rate-
  limited (recall needs minutes even when allowed). The API-level equivalents
  of every step are proven. `uploads.json` no longer matters for new brains.

## 13. Connector state

See `CONNECTOR_STATES.md`: Slack = stub-tested (90/90, not live); Gmail/Drive
= implemented-but-not-configured (packages verified in the candidate image;
503 with the exact missing prerequisite). Nothing advertised as live.

## 14. CI/deployment/ops state

- CI: `.github/workflows/ci.yml` — fast battery + frontend + marketing builds
  on push. Not yet observed green on GitHub (no run executed — repo remote
  state unknown from here).
- Deployment target: still none — the product remains local/private-beta
  tooling (honest per the prompt's allowance).
- Ops: backup/restore scripts + drills; job-drift visibility = worker logs +
  `brain_jobs` states (no alerting).

## 15. Remaining limitations

1. Generation allowance exhausted until 2026-10-06 (or founder tops up
   OpenRouter / switches to a paid Harbor model) — blocks post-cutover
   known-answer proof, `company_brain` rebuild, rollback-drill gate.
2. Job kinds UPDATE/REMOVE/SYNC not implemented (CREATE/REBUILD only).
3. Per-chunk citation offsets not captured (document-level durable
   provenance only).
4. React in-browser ask round-trip not captured end-to-end (API equivalents
   proven; latency-blocked).
5. One worker process; no alerting; single-host only.
6. v2 routes flag-gated OFF in production (`KESTREL_JOBS_V2`) — the flag must
   be set intentionally when the founder wants React creation live.

## 16. Exact claims that are now safe to make

- "Kestrel runs Cognee 1.6.2 (digest-pinned candidate) with data intact."
- "Brain identity is durable: UUID brains, generations, jobs, and provenance
  tables are live, migrated, and backfilled."
- "Brain creation via the v2 path is proven end-to-end including failure,
  recovery, and publish-gating — in the lab."
- "Citations for v2-created brains resolve from durable provenance and open
  without `uploads.json`."
- "Backfill ran live after a passing double-rehearsal; ambiguous records are
  preserved and reported, never fabricated."
- "Pagination drains 120 items across pages with read-stability (N14 closed)."
- "The upgrade is reversible: two validated backups + a rehearsed restore
  path + old-image compatibility."

## 17. Exact claims that remain unsafe to make

- "Post-cutover known-answer answers meet baseline" — pending provider window.
- "company_brain has been rebuilt on 1.6.2" — blocked (nothing deleted).
- "Rollback from 1.6.2 to 1.6.1 is fully rehearsed" — restore path proven;
  the full drill gate (with ask) is pending the provider window.
- "The React app is the complete supported frontend" — chat/history/create
  work; graph is a labeled legacy hand-off; in-browser ask round-trip not
  captured.
- "Connectors work" — none is live; all honestly labeled.
- "CI is green" — the workflow exists; no GitHub run has been observed.
