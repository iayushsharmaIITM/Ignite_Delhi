# Delta Plan — Baseline, Diagnosis, and the Reversible PR Sequence

Status: **PLAN — awaiting founder approval. No code or state changed yet.**
Date: 2026-10-01 • Repo commit at planning time: `ed91d64`

Governing documents read before writing this plan:
1. `Kestrel_ZCode_Nonbreaking_Upgrade_Addendum.md` (non-breaking rules; safer
   procedure wins on conflict)
2. `Kestrel_Consolidated_Audit_Implementation_Draft.md` v1.0 (treated as the
   "Kestrel implementation specification" — **Decision D1 confirms**)
3. `Kestrel_Stack_Audit_Addendum_A_Cognee_1.6.2_Connectors.md` (Cognee 1.6.2
   + connectors addendum; its A.3 spike is the connector gate)
4. `STACK_REVIEW.md` @ `f0a644c` (the brief — now partially corrected below)

---

## 1. Baseline facts collected today (all read-only, nothing mutated)

Runtime:
- Git: `ed91d64` (clean tree except two untracked docs unrelated to this work).
- Containers: `cognee-oss` = `cognee/cognee:1.6.1`, digest
  `sha256:db0973f4b913…`, up 22h (healthy); `kestrel-db` = `postgres:17-alpine`
  digest `sha256:b0f9560a2de0…`; `kestrel-langfuse` = `langfuse/langfuse:2`
  digest `sha256:85c278dcab96…`. Compose: `compose.oss.yml` (3 services,
  2 Cognee mounts + bind-mounted patches, LaunchAgent self-heal).
- The app tier is **not currently running** (no `python app.py` process) —
  port 8000 appears free, which makes the verify.sh baseline run unblocked.
- Container self-reports `cognee.__version__ = 1.6.1-local` — does NOT match
  a published release string. Artifact provenance must be verified during the
  candidate-image phase (N11). Digest is recorded above regardless.

Data (live counts, 2026-10-01):
- Cognee tenant: **1 dataset** — `company_brain` (`98676ce0…`).
- Postgres: `brain_access=2` rows, `chats=2`, `turns=4`, `llm_calls=194`;
  tables also include `graph_node(93)`, `graph_edge(161)`, `graph_metadata(2)`,
  `connector_credentials`, `slack_workspaces`.
- `uploads.json`: 13 entries across **10 dataset keys** — vs 1 live dataset.
- `.env.oss`: duplicate keys CONFIRMED — `LLM_PROVIDER, LLM_MODEL,
  LLM_ENDPOINT, LLM_API_KEY, LLM_RATE_LIMIT_REQUESTS` each appear more than
  once (last-block-wins is live, issue #6/N15).

Diagnosis findings (answers the addendum's "diagnosis only" mandate):
1. **Connector failure root cause (confirmed by direct inspection):** the
   running 1.6.1 container has **zero** `google-api-python-client` /
   `google-auth` packages (`docker exec pip list` count = 0), while 9
   `/api/v1/integrations/*` routes EXIST in the image. This matches Addendum
   A's assumption exactly: routes present, extras missing → authorize can
   start, first sync hits `ImportError`. Runtime `pip install` is not a fix
   (lost on recreate) — the derived-image route (A.2) is the cure.
2. **Storage-topology correction (N15):** `.env.oss` carries
   `GRAPH_DATABASE_PROVIDER/HOST/PORT/NAME/USER/PASSWORD` keys and the
   Postgres instance holds real graph data (93 nodes / 161 edges). The graph
   lives in **Postgres, not "Kuzu inside the container"** as STACK_REVIEW.md
   and the brief state. Consequences: (a) backup/restore of the graph is a
   `pg_dump` table set, same instance as app tables — actually simplifies
   consistent backups; (b) prior docs must be corrected; (c) the candidate
   image must be checked for its default graph provider — a silent default
   flip would strand the graph.
3. **Reconciliation drift is live (issue #3):** tenant has 1 dataset;
   `brain_access` has 2 rows; `uploads.json` references 10 datasets. At
   least one of: deleted-out-of-band datasets, stale manifest entries, or a
   graph wipe happened without app-side cleanup. Inventoried in the baseline
   pack; NOT repaired until the backfill phase is approved.
4. **Version drift:** host venv reports `fastapi 0.115.0` while
   `requirements.txt` pins `0.141.1` — interpreter/package provenance to
   verify in the baseline pack (affects reproducibility claims only; no
   action until confirmed).
5. **Pagination blocker (N14):** `cognee_cloud.data_items` reads a single
   page; 1.6.1 paginates at 100. Today's data is small (13 manifest entries),
   so nothing is currently truncated — the fix is still required before any
   brain exceeds 100 documents and before the 1.6.2 cutover.
6. **1.6.2 target artifact:** tag existence to be verified by
   `docker manifest inspect cognee/cognee:1.6.2` in Phase A (Addendum A could
   not confirm it; this is a hard gate before any candidate build).

## 2. Phase A — Baseline & diagnosis completion (the current task)

Execution checklist (reads only; artifacts into `docs/baseline/`, sanitized;
bulky logs gitignored under `var/`):

| # | Item | Command / source | Output artifact |
|---|---|---|---|
| A1 | Pin digests + versions | already collected (§1) | `docs/baseline/runtime.md` |
| A2 | Env-name manifest (NAMES only, no values), dup-key report | `grep -oE` both env files | `docs/baseline/env-names.md` |
| A3 | DB schema snapshot + counts (all tables) | `pg_dump --schema-only`, SELECT counts | `schema.sql`, `counts.md` |
| A4 | API schema export | `curl :8000/openapi.json` (app started briefly on a free port, mock provider, auth off — never against live demo state) | `openapi.json` |
| A5 | verify.sh full battery + targeted suites (port 8000 is currently free) | `./verify.sh` | `verify-baseline.log` |
| A6 | Demo evidence: 1 ask with opened source (known-answer Bluepeak question), transcript + citation resolution | scripted curl | `demo-ask-evidence.md` |
| A7 | Connector error capture, redacted | reproduce authorize→sync on 1.6.1 (no data change; expect ImportError class) | `connector-diagnosis.md` |
| A8 | Reconciliation inventory: datasets × brain_access × uploads.json × chats.brain | read-only joins | `reconciliation-inventory.md` |
| A9 | 1.6.2 registry verification | `docker manifest inspect cognee/cognee:1.6.2` | recorded in `runtime.md` |
| A10 | Storage-root inventory: which Cognee paths hold what (mount sizes, PG table sizes) | `du` via docker, `pg_relation_size` | `storage-roots.md` |

Phase A exit gate: every preservation gate in Addendum §3 re-measured and
recorded (behavior, data, costs, auth, connectors=unavailable-but-honest,
ops). If any gate FAILS on the baseline itself (e.g. battery red), stop and
report — no PR sequence starts on an unverified base.

## 3. Proposed PR sequence (smallest reversible; expand → backfill → cutover → contract)

Standard **evidence block attached to every PR** (per your instruction):
before/after `./verify.sh` + targeted suites; data-count reconciliation
queries with expected==actual tables; cost delta (infra $, token estimate,
embedding-rebuild policy); unresolved assumptions list; an **executed**
rollback check (the revert/restore is actually performed on the scratch
stack and gates re-run — described-but-not-run does not count).

### Phase E — EXPAND (nothing dropped, nothing switched)

- **PR-1 — Backup/restore tooling + drill on copies** (ops only; after your
  approval of Phase A evidence). Consistent copy = `pg_dump` (app tables +
  graph_* tables in one dump — one instance, one consistent point) + tar of
  both Cognee mounts + `uploads.json` + Fernet key recovery note. Restore
  into an ISOLATED compose project (different name/ports). Gate: demo ask +
  source-open + ownership check pass **on the copy**. Originals untouched.
  Rollback check: scratch stack destroyed; originals verified byte-identical
  (mount checksums before/after).
- **PR-2 — Candidate 1.6.2 derived image** (build only; live container
  untouched). Verify tag/digest; build from upstream tag `v1.6.2` with
  `COGNEE_EXTRAS="gmail google-drive"` (preferred) or layered extras
  (fallback, tested); re-apply both patches with upstream file-hash checks
  that FAIL the build on mismatch; pin by digest. Tests: token-cap behavior
  with a stub provider; connector packages importable; shadow boot against
  the PR-1 restored copy with access control ON; two-workspace isolation
  spike (Addendum A.3 steps 1–6); Google test account Drive sync to
  `syncStatus=ok`; recall returns text; SameSite/callback behavior recorded;
  1.6.1-vs-1.6.2 known-answer comparison on both corpora copies. **This PR
  produces the candidate test results you require before ANY approval.**
- **PR-3 — Alembic baseline** (no schema change). Stamp the live schema as
  migration 0001; `storage.init()` DDL frozen; tests unchanged. Rollback:
  remove alembic/, DB untouched.
- **PR-4 — Additive identity/provenance/jobs schema** (expand only):
  `workspaces, brains(UUID), brain_grants, brain_generations, documents,
  document_versions, generation_documents, brain_jobs, brain_job_files,
  brain_job_events, source_references` per spec §2 table contract —
  additive `CREATE TABLE` + additive columns only; `brain_access` and all
  existing columns untouched; composite-FK ownership invariants included;
  dual-accept (name+UUID) code paths behind imports only. Rollback:
  `alembic downgrade` to 0001 (tables dropped — additive, no data loss) on
  the scratch stack, executed and evidenced.
- **PR-5 — `data_items` pagination fix** (small, independent, blocker-class):
  page until short page, dedup by id, read totals from `/data/count`,
  contract test with >100 tiny synthetic documents (120, not 250 — proves
  the same boundary at ~half the ingestion spend; expansion to 250 optional).
  Costs: one-time synthetic ingest on the scratch stack (fastembed local =
  $0 embeddings; Cognee LLM extraction of 120 tiny docs ≈ minor token spend,
  capped, on the approved DeepSeek route).

### Phase B — BACKFILL

- **PR-6 — Batch backfill + reconciliation report.** `brains` rows from
  (live datasets × `brain_access` × `uploads.json`), legacy-unresolvable
  manifest entries marked `unresolved_legacy` (never guessed filenames);
  `chats.brain_id` backfilled preserving existing ownership stamps;
  expected==actual count reconciliation for every table touched; sample
  ownership spot-checks. Old paths still work; new tables are written but
  not yet authoritative. Rollback: down-migration on scratch; originals
  never the target until you approve cutover.

### Phase C — CUTOVER (each gated; flags default OFF until parity)

- **PR-7 — New create/job path behind `KESTREL_JOBS_V2` (default off)**:
  202 + brain_jobs + worker (`FOR UPDATE SKIP LOCKED`, lease + mutation
  fencing, OUTCOME_UNKNOWN handling), idempotency keys, provenance gate
  before substantive answers. Old path stays default. Parity gate = the
  spec's release-acceptance subset (same-slug two-workspace, idempotent
  retry, kill-before/after-submit, >100-doc inventory, citation unchanged).
- **PR-8 — 1.6.2 image switch on the working stack** — ONLY after you
  approve PR-2's candidate results AND PR-1's restore drill. Short window:
  stop writes, final backup, swap digest, run migrations deliberately,
  reconcile, known-answer + source-open + counts. Rollback = rehearsed
  old-image + restored-old-state + old config (not just a tag flip).
  **Re-ingest/rebuild of existing brains happens per-brain as explicit
  `rebuild` jobs AFTER cutover, only with your per-batch approval — never a
  blanket re-ingest** (embedding chunk-size change 8191→4096 makes old/new
  chunks coexist until then).

### Phase D — CONTRACT (explicitly deferred; needs separate approval)

- **PR-9 — retire name-only identity/`uploads.json` dual-writes/compat
  aliases** only after: one clean deployment, restore drill, and a full
  regression cycle on the new path. NOT part of this cycle.

Connector pilot (Drive/Gmail) rides inside PR-2's shadow stack; it touches
the working stack only after PR-8 approval + Google test-account setup
(D1/D5 below). Slack stays app-owned; 1.6.2 Slack history import stays OFF
until the ownership-overlap decision (spec A.3).

## 4. Preservation gates (stop-and-report, no silent fallback)

Re-checked at every PR: `./verify.sh` green; demo corpus byte-identical
(mount checksums); citation behavior unchanged on known answers (unknown
stays unresolved, never "fixed"); token cap still enforced (stub-provider
test, not file presence); no cross-org readability; AUTH_MODE=off /
PROVIDER=mock still available for local tests; no route removed or reshaped
(compat layer if ever needed). Any failure → halt that PR, report the exact
failed test + versions, wait for your call.

## 5. Costs (whole sequence)

Infra: $0 (all local; scratch stacks are containers on this Mac).
Network: one 1.6.2 image pull (size recorded in PR-2).
Tokens (estimates, DeepSeek-only): baseline demo asks ~4–6 asks at existing
per-ask cost; PR-2 candidate tests ~10–15 scratch asks + Drive sync of one
small test account + 120-doc synthetic ingest (PR-5) — bounded, recorded per
run in Langfuse and `llm_calls`, reconciled in each PR's evidence block.
No uncontrolled embedding/graph rebuild at any point before cutover
approval; post-cutover rebuilds are per-brain, per-batch approved.

## 6. Decisions needed from you (recommendation in parentheses)

- **D1 — Implementation spec.** I treated
  `Kestrel_Consolidated_Audit_Implementation_Draft.md` v1.0 as "the Kestrel
  implementation specification" (with Addendum A layered on). Confirm, or
  point me at a different document. *(Recommended: confirm — it is the only
  consolidated spec with verification gates.)*
- **D2 — Phase A execution.** Approve the Phase A checklist (§2) as the
  immediate task. All read-only except starting the app briefly on mock/auth-
  off for the schema/API export while port 8000 is free. *(Recommended:
  approve as-is.)*
- **D3 — Backup/restore drill (PR-1).** Creates copies only; originals get
  checksummed before/after. Approve to proceed once Phase A evidence lands.
  *(Recommended: yes.)*
- **D4 — Pagination test size.** 120-doc synthetic test instead of 250
  (same boundary proof, ~half the spend). *(Recommended: 120.)*
- **D5 — Google test account.** The Drive/Gmail spike needs one personal
  Google test account you control (connect it yourself during PR-2; I never
  handle the OAuth codes). Also confirm no Gmail datasets from 1.6.1 exist
  that would need deletion — current tenant inventory shows none (only
  `company_brain`).
- **D6 — Free-route policy.** `llm.py` currently prefers Token Harbor's
  `:free` variant. Spec wants free routes restricted to synthetic data. I
  propose NOT changing local-dev defaults now (addendum forbids silent dev-
  default changes); implement the policy gate with the `APP_ENV=beta` work
  after cutover. *(Recommended: defer.)*
- **D7 — Rebuild scope post-1.6.2.** Per-brain `rebuild` jobs after cutover,
  batch-approved, starting with `company_brain` on the smallest corpus first.
  *(Recommended: accept the per-batch model.)*
