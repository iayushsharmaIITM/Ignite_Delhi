# PROGRESS — execution log for BUILD_PLAN.md

Append-only, newest first (BUILD_PLAN.md §4). States are exactly:
`DONE` | `BLOCKED` (points at a BLOCKERS.md entry) | `WAITING-HUMAN` | `SKIPPED`
(SKIPPED only ever carries a one-line reason + recorded human approval).

## M0.3 — contract_test.py — DONE 2026-09-25

`python3 contract_test.py --flavor cloud` → **11/11 PASS** (was 10/11).
`./verify.sh --quick` → documents 25/25, pipe-states 13/13, tenants 10/10,
smoke 4/4, exit 0.

Root cause of the one FAIL (terminal wait, 300s cap): NOT latency. Raw-payload
diagnostic (scratch `contract_diag_*`, polled every 15s, deleted after) showed
the cloud status endpoint returns a **bare string map** without
`include_error_detail` — `{"<uuid>": "DATASET_PROCESSING_COMPLETED"}` — which
`_status_values()` never yielded (dict-only), so `terminal_kind()` stayed None
even on COMPLETED. Pipeline actually completes in ~35s.

Two edits to unblock:
1. `contract_test.py::_status_payload` now sends `include_error_detail=true`,
   mirroring `cc.status()` (in-card file; the test now replays what the app
   actually sends).
2. `cognee_cloud.py::_status_values` also yields bare string values
   (M0.4-adjacent hardening, human-approved via "continue"; flat
   `{"status": ...}` still yields exactly once; 13/13 pipe-states green).

Findings banked: terminal `DATASET_PROCESSING_COMPLETED -> success`; cloud
stores filename as `text_<hash>` (reconfirms fingerprint design); cloud
silently accepts BOTH recall naming styles (200). Scratch deleted; tenant
left with the five real brains.

Next: M0.4 exactly as carded (flavor switch in `recall()` only).

## M0.3 — contract_test.py — IN PROGRESS 2026-09-25 (handoff point)

`contract_test.py` written per plan §2.3 (wf_smoke.py safety pattern: unique
scratch, collision refusal, finally-deletion). Validated against the CLOUD
tenant: **10/11 checks PASS** in its first real run —

- remember/status/data-items/data-raw/graph/recall(200, no 422) all conform;
  scratch auto-deleted.
- Findings already banked: **cloud stores our filename as `text_<hash>`**
  (confirms citations.py's content-fingerprint design is still required for
  the cloud flavor), and **the cloud tenant silently accepts BOTH recall
  naming styles** (camel and snake) — the drift signal there is silent, not
  loud, so the oss-flavor 422 check is the one that matters.

**The one FAIL:** `pipeline reaches a terminal state (300s cap)` — the status
map never satisfied `terminal_kind()` within 300 s on the cloud tenant.
Recall returned 200 mid-ingest (the known confident-answer trap), so the
skip-line now reports the actual kind rather than claiming "failed pipeline".
Diagnosis so far: NOT a shape issue (data items + raw round-trip work);
likely either (a) tenant queue latency > 300 s for `run_in_background=true`
with the status map possibly staying `{}` (no status key at all) while
queued — `_status_values` yields nothing for `{}`, which would look exactly
like this — or (b) a slow pipeline. A raw-payload diagnostic was started but
cut short for the handoff.

**Next agent, in order:**
1. Rerun the diagnostic (script sketch is in the HANDOFF.md): `remember` on
   a scratch dataset, poll `/api/v1/datasets/status?dataset=<uuid>` every
   15 s, PRINT each distinct raw payload. If `{}` persists, that is the
   answer: empty map while queued. Fix = longer default `--wait-timeout`
   (600–900) plus optionally reporting elapsed-queued as an INFO line; if a
   non-standard state string appears, extend `cognee_cloud._status_values`
   mapping instead (that is an M0.4-adjacent edit — see BUILD_PLAN.md M0.4
   before touching `cognee_cloud.py`).
2. Green cloud run → mark M0.3 DONE, commit.
3. Proceed to M0.4 exactly as carded (flavor switch in `recall()` only).

Leftover scratch from the cancelled diagnostic (`contract_diag_*`) was swept
from the tenant — dataset list verified back to the five real brains.

## M0.2 — local OSS container (pinned, auth off) — DONE 2026-09-25
(human chose Colima via brew when Docker was found absent)

- Installed colima 0.10.3 + docker CLI 29.8.1 + compose 5.5.1 via brew (one
  retry needed: stale brew metadata aborted the first install; `brew update`
  fixed it). Compose plugin symlinked into ~/.docker/cli-plugins.
- `colima start --cpu 2 --memory 4` — VM up (x86 emulation available).
- **Correction to research + plan:** Docker Hub tag is `cognee/cognee:1.6.1`
  — NO `v` prefix (`v1.6.1` does not resolve; found via registry API).
  compose.oss.yml and BUILD_PLAN.md corrected. Digest:
  sha256:db0973f4b913d73daa4061bc19362cde6edc59d1be8243b6667fade364b06428.
- `compose.oss.yml` (gitignored; port 8888:8000, named volume for embedded
  state) + tracked `.env.oss.example` (both auth flags false, fixed JWT
  secret placeholder, commented LLM/embedding block for M1.1).
- Check results:
  - `curl localhost:8888/health` → `{"status":"ready","health":"healthy","version":"1.6.1-local"}` (≈30s after start; first boot runs migrations).
  - `docker compose ps` → Up.
  - **Auth-off proven:** `GET /api/v1/datasets/` unauthenticated → 307 → 200 `[]`.
    Note: OSS canonical path has NO trailing slash (FastAPI redirect); our
    client's trailing-slash URL still works because requests follows redirects.
- Observations (not fixed, per N6): none new.


## M0.1 — verification harness + workspace files — DONE 2026-09-25
(was BLOCKED; the two out-of-scope fixes were approved by the human and applied)

- Environment verified: Python 3.13.3, all requirements importable, port 8000
  free, `playwright-cli` present at check_ui.py's NODE_BIN path, `brew` present.
- `verify.sh` per plan §2.2, refined during the card: forces `PROVIDER=mock`
  for the whole battery, starts/stops its own server, refuses a pre-owned
  port 8000, runs each suite via its own standalone entrypoint (pytest is the
  wrong runner here — collects 2 of 13 and 0 of 10 checks), tenants runs
  `--with-tenants` against the battery's own server.
- **Found and fixed in scope:** stale `__pycache__` bytecode compiled in the
  original Ignite_Delhi workspace, executing since the repo was copied
  (preserved mtimes validated it). Caches cleared — this affected every suite.
- **Approved out-of-scope fixes applied (BLOCKERS.md resolved):**
  1. `test_pipeline_states.py::drive()` now sets/restores
     `memory_layer.PROVIDER` itself — the suite no longer depends on ambient
     `.env` saying `PROVIDER=cloud`; still zero network (status stubbed).
  2. `app.py::delete_brain` now evaluates `require_dataset_access` BEFORE the
     mock-mode guard — unauthorized DELETE gets 401/403 in every mode instead
     of a masking 400. No regression in cloud or authorized paths.
- Check output (`./verify.sh --quick`):

```
== Kestrel verification battery (PROVIDER=mock) ==
[documents] PASS  25/25
[pipe-states] PASS  13/13
[server] up (pid 83199, mock fixtures)
[tenants] PASS  10/10
[smoke] PASS  4/4
[ui] SKIP  (--quick)
== done: 0 failing suite(s) ==
```

- PROGRESS.md and BLOCKERS.md created; `.gitignore` gained
  `.env.oss`, `compose.oss.yml`, `cognee_oss_state/`.
- Observations (not fixed, per N6): `.gitignore` contains a duplicated
  `.playwright-cli/` block; `.zcodeignore` duplicates it as well;
  `create_brain` and `brain_events` share delete_brain's guard-before-authz
  ordering (same class, only delete_brain was approved); `pytest` is not in
  `requirements.txt` (installed globally here; the battery no longer needs it).
