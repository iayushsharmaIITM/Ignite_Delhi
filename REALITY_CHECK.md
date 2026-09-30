# Kestrel Reality Check

_Date: 2026-10-01 • Reviewed at commit `05b4289` with a dirty tree_

## Executive verdict

- The **live product is still the 1.6.1 legacy-path app** — that, and only that, is genuinely "Done" for its current scope: running, healthy, battery green (25/13/90/10/4 + UI), demo corpus checksum-verified untouched.
- The upgrade is **roughly half-built and a quarter-proven**. Schema (11 new tables), candidate 1.6.2 image, backup/restore drill, Alembic, pagination-fix code, backfill script, and the v2 lifecycle all exist and are committed — but "built" is not "verified," and several verification runs never finished.
- **The working tree is dirty**: the v2 identity-guard and UUID-serialization fixes in `app.py`/`lifecycle.py` are uncommitted. The committed v2 code is broken in off-mode (`require_tenant` returns None → AttributeError). Per your own standard: uncommitted work is not shipped work.
- **The v2 happy path has never been observed succeeding.** The one committed job is orphaned in `VERIFYING` — my app restarts killed its worker and there is **no lease-expiry reclaim**, a real design gap. Its pipeline actually ERRORED upstream (`DATASET_PROCESSING_ERRORED`, 2 data items present — inventory without completion), so a live worker would have failed it honestly; nothing did, because nothing was alive.
- **The pagination contract test never completed.** After 30+ minutes the 120-doc ingestion is still in its submission phase and the lab candidate container is now **unhealthy**. The N14 fix is committed but unproven at the count it was written for.
- **Backfill has never been rehearsed or run.** The 11 new tables on live are empty; `brain_access` remains the only ownership authority; `uploads.json` remains the only uploaded-brain citation store.
- The isolation spike proved only the **deny-direction**; the allow-direction died on my stub LLM's fidelity, and real Drive/Gmail sync is blocked on founder-supplied OAuth config. Connectors remain honestly "not configured."
- `llm.py` still routes the app tier to **`deepseek-v4.1-flash:free`** — known, documented, unfixed.
- `UPGRADE_REPORT.md` is largely accurate but its commit title ("PR-1..PR-7 build") and framing overstate completion: PR-5's proof never landed, PR-6 never rehearsed, PR-7's happy path never observed.

## Claimed vs built

| Area | Claimed in docs | Actually in repo | Verification status | Risk if overstated | Verdict |
|---|---|---|---|---|---|
| Phase A baseline | full evidence pack, gates green | `docs/baseline/` (11 artifacts), checksums, battery log | **Live-tested** (on the real stack) | none | **Done** (for its scope) |
| PR-1 backup/restore | validated backup + restore drill | `ops/backup.sh`, `ops/restore_lab.sh`, `compose.lab.yml`, backup `20260930T212010Z` w/ SHA256SUMS | **Lab-tested** (restore + known-answer ask on copy: 842 chars/3 refs) | none | **Done** (local scope) |
| PR-2 candidate image | 1.6.2 + extras + hash-gated patches | `Dockerfile.candidate` → `kestrel-cognee:1.6.2-candidate` | **Lab-tested** (migrations, dataset survived, ask 688 chars/3 refs, no 402) | upstream drift between now and cutover re-breaks gates | **Done** as artifact; **not cutover-proven over time** |
| Isolation spike | "deny-direction PROVEN" | spike ran; B→A dataset 404 with exact contract | deny-direction lab-tested; allow-direction untested (stub fidelity) | overstated if quoted as "isolation proven" | **Partially verified** |
| PR-3 Alembic | baseline stamped | `alembic.ini`, `migrations/`, live at `0002` | **Live-tested** (stamp + 0002 applied) | low | **Done** |
| PR-4 expand schema | 11 additive tables, composite FKs | migration 0002; 11 tables on live; counts reconciled; downgrade executed on lab | **Live-tested** (additive) | tables are empty — existence ≠ adoption | **Done** (schema only) |
| PR-5 pagination | fix committed; test running | `cognee_cloud.data_items` rewritten; `ops/test_pagination.py` | test **STUCK** — submissions never drained; lab container unhealthy | silent-truncation risk unproven-fixed | **Built, NOT verified** |
| PR-6 backfill | script ready, rehearsal pending | `ops/backfill.py` (syntax-checked; fixed fetchall bug) | never rehearsed, never run on live | live identity adoption = zero | **Built, NOT verified** |
| PR-7 v2 lifecycle | 202/idempotency/slug/honest-FAIL proven; happy path "in flight" | `lifecycle.py` + 3 flag-gated routes + worker | 202/409s/fail-path **lab-tested**; happy path **never observed SUCCEEDED**; orphaned-lease gap found; two fixes **uncommitted** | "core paths proven" ≠ job system done | **Partially verified, NOT committed-complete** |
| PR-8 cutover | staged runbook, exit 1 | `ops/cutover_162.sh` | not executed; live still 1.6.1 | none if wording honest | **Staged only** |
| Token cap | behaviorally intact on 1.6.2 | patches hash-identical; real ask on 1.6.2 without 402 | lab-tested (behavioral, not request-inspection) | low | **Verified (behavioral)** |
| Citation durability | provenance tables exist | tables empty; live path still `uploads.json` + fingerprints | live path unchanged | "durable provenance" claims would be false | **NOT started on live path** |
| Auth/workspace isolation | v2 workspace authz added | org-mode check in `/api/jobs/{id}`; untested | built, untested | medium | **Built, NOT verified** |
| Frontend | React UI with tokens, connectors dialog, Lighthouse 100 | true — but chat history is localStorage; brain create/manage redirects to legacy `/upload`, `/brains`, `/graph` | live-verified | "first-class React" claims false | **Partial: chat skin only** |
| CI / deployment | none claimed | none exist; marketing built, not deployed | — | — | **Missing** |
| LLM policy | ":free deferred (D6)" | `llm.py:16` still `deepseek-v4.1-flash:free` | live | policy-violation risk for beta data | **Open, known** |

## Area-by-area assessment

**Cognee / graph stack.** Live = `cognee/cognee:1.6.1` (digest `db0973f4…`, self-reports `1.6.1-local`). Candidate 1.6.2 built and lab-exercised; **not deployed**. 1.6.2's auth-posture default flip is handled only in the runbook, not in live config (live `.env.oss` already pins `ENABLE_BACKEND_ACCESS_CONTROL=false` — verified — so a naive image bump would boot, but the runbook gate is still mandatory).

**Backup/restore.** Real and validated: one consistent dump (graph tables live in Postgres — confirmed and corrected from the brief), both mounts, manifest, key material, checksums. Restore into an isolated project passed the known-answer ask. This is the strongest new subsystem.

**Migrations/Alembic.** Live at `0002_identity_provenance_jobs`; 0001 stamped, 0002 applied with before/after count equality; downgrade executed on the lab. Sound. Note: `storage.init()` is still the fresh-bootstrap path; migrations don't yet own the full schema (documented).

**Brain identity.** Schema exists on live; **zero rows**. `brain_access` (2 rows: `company_brain`, `acme_isolated`) remains the sole ownership authority. Reconciliation drift from baseline is unrepaired (1 dataset vs 2 owner rows vs 10 stale manifest keys vs 2 chats pointing at dead brains).

**v2 lifecycle / jobs.** Reservation atomicity, idempotency (both 409 shapes), slug conflicts, and honest pipeline-failure handling are lab-proven. Three hard gaps: (1) happy-path SUCCEEDED never observed; (2) **no lease-expiry reclaim** — an orphaned `VERIFYING` job is stuck forever, found by experiment; (3) the two fixes that make v2 work at all in off-mode are **uncommitted**.

**Citations.** Live path unchanged: Cognee evidence strings → fingerprint match → `uploads.json` on app-host disk → `/api/source` reads corpus or tenant raw. The spec's durable provenance (`source_references`, `generation_documents`, verified excerpts) is schema-only; nothing populates or reads it in the live path.

**Auth.** Clerk mode live and healthy; battery's tenant suite (10/10) still passes; fail-closed behavior intact. v2's workspace authz check is written but untested.

**Connectors.** Slack: stub-tested only (90/90 on stubs), never live. Gmail/Drive: candidate has the extras importing; `POST /authorize` returns honest 503 (`"google_drive integration is not configured on this server."`) because founder-side OAuth config doesn't exist. Root cause of the original ZCode failure confirmed (packages absent in 1.6.1 image).

**Frontend.** React = chat surface + Connectors view + Clerk theming. Chat history is `localStorage` (`frontend/src/lib/api.ts:50-54`); brain create/manage/graph all `location.href` into legacy pages (`frontend/src/App.tsx:218-220`). The legacy shell remains the only complete product UI. Both frontends work; neither is the "one supported frontend" the spec demands.

**Verification/ops.** `verify.sh` remains excellent for what it is — and it is **mock-only by design** (`PROVIDER=mock AUTH_MODE=off`). Real-stack validation exists only as my manual lab/live scripts. No CI. No deployed environment. Marketing built, not deployed.

## Latest-stack gap

"Latest intended stack" per the governing docs = Cognee 1.6.2 (digest-pinned candidate) + explicit access-control env + the current FastAPI/Postgres17/Clerk/React/DeepSeek stack. Already upgraded: nothing in production. Prepared: image, schema, runbook, client fix. Still old: the running graph tier (1.6.1), the app's default create path, citation storage (disk manifest), the app-tier LLM route (`:free`).

Blocking an honest "on the latest stack" claim: (1) v2 happy path never green; (2) pagination contract never green; (3) live flip not executed; (4) backfill not run, so new schema is decorative; (5) uncommitted v2 fixes; (6) no post-cutover rebuild of `company_brain`, so old/new chunking would coexist unmeasured.

## Completion plan

1. **Commit the v2 fixes.** Files: `app.py`, `lifecycle.py`. Proof: `git status` clean; battery green. Type: code. Rollback: revert commit.
2. **Add lease-expiry reclaim** to `lifecycle.claim_job` (claim `VERIFYING/INGESTING` with expired leases → `RECONCILIATION_REQUIRED`). Proof: unit-style test — orphan a job, run claim, assert state. Type: code. Rollback: revert.
3. **Finish the v2 happy path on a quiet candidate.** Kill the 8889 lab container; fresh candidate on 8892; re-run the exact v2 create. Proof: `brain_jobs.state='SUCCEEDED'`, `brains.state='READY'`, `generation_documents` rows with `backend_data_id`, and a known-answer ask on the new brain returning citations that open. Type: lab validation.
4. **Fix the pagination test's approach** (batch submissions ~20-at-a-time, or raise parallelism limits on the lab container) and re-run to a printed `PAGINATION CONTRACT … PASS`. Proof: that line in the log plus `/data/count` equality. Type: lab validation.
5. **Rehearse backfill on the lab copy**, then run on live. Proof: `ops/backfill.py` assertions pass; live reconciliation report emitted; `brains` rows == `brain_access` rows; `chats.brain_id` set only for provable links. Type: migration/backfill. Rollback: down-migration (new tables only).
6. **Cutover (founder-gated).** Execute `ops/cutover_162.sh` with a fresh backup. Proof: runbook gates a–c (datasets present, identical known-answer citations, count equality) + rollback rehearsal re-verified. Type: cutover.
7. **Post-cutover rebuild of `company_brain`** as the first approved batch. Proof: known-answer ask returns the same references post-rebuild. Type: live validation.
8. **Citation durability read-path (flag-gated):** make `/api/source` prefer `source_references` when present. Proof: v2-created brain's citation opens via the new table; legacy brains unchanged. Type: code + lab validation.
9. **LLM policy line:** remove `:free` from `llm.py` or gate it behind `APP_ENV=local`. Proof: config manifest in env-names doc; one live ask on the paid route. Type: config change. (Founder decision D6.)
10. **CI lane:** GitHub Actions running `./verify.sh --quick` on push. Proof: first green run. Type: ops.

## Decision calls

- **Cut over now?** **Wait.** The candidate is good but its own happy-path and pagination proofs haven't finished; cutover gates reference tests that haven't passed.
- **Run backfill now?** **After rehearsal only** — the script is unproven; rehearsal is minutes away once the lab drains. Additive and reversible, so this is days-not-weeks.
- **Enable v2 lifecycle now?** **No.** Uncommitted fixes, orphaned-lease gap, and zero SUCCEEDED observations.
- **Rebuild brains now?** **No.** Meaningless pre-cutover; the chunking change only exists on 1.6.2.
- **Claim latest-stack complete now?** **Not yet.** Five concrete gates above; closest credible window is after steps 1–6.

## Non-negotiable wording corrections

1. Commit `ca05868` title "PR-1..PR-7 build" → "**PR-1..PR-7 built; v2 happy path and pagination contract unproven; two v2 fixes applied post-commit**."
2. UPGRADE_REPORT §1 PR-7 "CORE PATHS PROVEN" → "**reservation/idempotency/conflict/fail paths proven; happy path never observed SUCCEEDED; orphaned-lease gap discovered**."
3. UPGRADE_REPORT §1 PR-2 spike "deny-direction PROVEN" → keep, but add "**allow-direction untested; real Drive/Gmail sync untested (founder-blocked)**."
4. DELTA_PLAN "smallest reversible sequence … PR-6 backfill" → add "**backfill never rehearsed at report time**."
5. Any "latest stack" phrasing → "**candidate verified in lab; production still 1.6.1; cutover gated on unfinished proofs.**"
6. "Isolation PROVEN" anywhere without the qualifier → "**deny-direction only.**"
