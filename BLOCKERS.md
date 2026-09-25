# BLOCKERS — escalations out of the iteration protocol (BUILD_PLAN.md §3)

One entry per blocker, newest first. Format:

```
## M<phase>.<n> — <title> — <date>
<diagnosis> / <what was tried> / <exact error output>
<what unblocks it>
```

---

## M0.1 — battery red: two test suites depend on ambient `.env` PROVIDER — 2026-09-25 — **RESOLVED**

Human approved both proposed edits on 2026-09-25. Applied:
1. `test_pipeline_states.py::drive()` sets/restores `memory_layer.PROVIDER`.
2. `app.py::delete_brain` runs `require_dataset_access` before the mode guard.

Battery after: documents 25/25, pipe-states 13/13, tenants 10/10, smoke 4/4 —
all green under forced mock. Entry kept for the record.

---

**Original entry (for the record):**

**Diagnosis.** Forcing `PROVIDER=mock` (the battery's design: hermetic, never
depends on the tenant) exposed that two suites silently relied on `.env`
saying `PROVIDER=cloud`. Neither failure is caused by the battery; both are
latent defects the battery exists to catch. A third, unrelated defect was
also found and fixed inside card scope: `__pycache__/` contained bytecode
compiled in the original `Ignite_Delhi` workspace and copied over with
preserved mtimes — its header validated against the copied sources, so stale
bytecode (paths pointing at a directory that does not exist, pre-fix test
counts) was executing. Caches cleared; tracebacks now reference this repo.

**Failure 1 — `test_pipeline_states.py` (crashes under mock).**
`drive()` stubs `cognee_cloud.status` but never sets `memory_layer.PROVIDER`;
`app.py:596` raises `400: Progress needs PROVIDER=cloud.` before the stub
matters. The test needs the provider STRING, not the cloud (zero network).
**Proposed fix (one line + restore, in `drive()`):** set
`memory_layer.PROVIDER = "cloud"` before the call, restore after.
**Mechanism proven** without editing: monkeypatching the string in a replica
of `drive()` yields `stages: ['poll', 'failed']` — exactly the asserted
contract.

**Failure 2 — `test_tenants.py` 9/10 (authz masked by mode guard).**
`app.py::delete_brain` checks `memory_layer.PROVIDER != "cloud"` (400)
BEFORE `require_dataset_access` (401/403). Under mock, an unauthorized
DELETE gets the mode-guard 400 instead of an authz refusal, so the "A cannot
DELETE B's brain" check reads 400 ≠ 403. Real (if low-severity) ordering
defect: authorization should be evaluated first. Same pattern exists in
`create_brain` and `brain_events` (noted, not proposed for this fix).
**Proposed fix (reorder two statements in `delete_brain`):** move
`require_dataset_access(request, name)` above the mock guard. No behavior
regression in any mode: cloud unchanged; mock+unauthorized becomes 401/403
(strictly more fail-closed); mock+authorized still 400.

**What was tried (in card scope):** cleared `__pycache__` + `.pytest_cache`;
switched the battery to the suites' own standalone entrypoints (pytest
collects only 2 of pipe-states' 13 checks and 0 of tenants' 10); tenants now
runs `--with-tenants` against the battery's own mock server. Result:
documents 25/25, smoke 4/4, tenants 9/10, pipe-states crash — both remaining
failures need the out-of-scope edits above.

**Unblocks:** human approval for the two proposed edits (test file + app.py).
M0.1 stays BLOCKED until then; M0.2+ are behind it in card order.
