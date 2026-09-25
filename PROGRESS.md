# PROGRESS — execution log for BUILD_PLAN.md

Append-only, newest first (BUILD_PLAN.md §4). States are exactly:
`DONE` | `BLOCKED` (points at a BLOCKERS.md entry) | `WAITING-HUMAN` | `SKIPPED`
(SKIPPED only ever carries a one-line reason + recorded human approval).

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
