# PROGRESS — execution log for BUILD_PLAN.md

Append-only, newest first (BUILD_PLAN.md §4). States are exactly:
`DONE` | `BLOCKED` (points at a BLOCKERS.md entry) | `WAITING-HUMAN` | `SKIPPED`
(SKIPPED only ever carries a one-line reason + recorded human approval).

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
