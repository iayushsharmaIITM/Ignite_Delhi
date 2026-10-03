# BLOCKERS — escalations out of the iteration protocol (BUILD_PLAN.md §3)

One entry per blocker, newest first. Format:

```
## M<phase>.<n> — <title> — <date>
<diagnosis> / <what was tried> / <exact error output>
<what unblocks it>
```

---

## M-ops.1 — launchd cannot read ~/Desktop, so the "self-healing" stack job never runs — 2026-10-04 — **OPEN: owner's machine decision**

**Diagnosis.** `com.kestrel.stackup` (the login job the handover documents rely
on: "logging into the Mac should bring everything up") is loaded and fires, and
fails before its first line, because macOS denies launchd access to `~/Desktop`:

```
/bin/bash: /Users/_iayushsharma_/Desktop/Kestrel_brains/ops_stack_up.sh: Operation not permitted
last exit code = 126
```

Reproduced by `launchctl kickstart -k gui/<uid>/com.kestrel.stackup`. This is
also why colima has stopped four times with the stack staying down: the recovery
mechanism was never able to run, and nothing said so — the job's exit status
nobody read, and `/tmp/kestrel_stackup.log` shows old successful runs from when
it was launched from a terminal, which is what made it look alive.

**What was tried.** The same wall was hit installing a nightly backup: pointing a
plist at the repo path reproduced exit 126 exactly. Fixed there by keeping the
launchd target outside the repo entirely — `ops/install_agents.sh` installs
`~/Library/Application Support/Kestrel/kestrel_nightly_backup.sh`, which reads
nothing under Desktop (docker only) and writes to `~/Kestrel_backups`. Verified:
`last exit code = 0`, a 12 MB backup with a checksum manifest, and a receipt that
reports `STALE` (exit 1) if it goes older than 36 hours, because a silently
missing backup and a silently broken job are the same class of failure.

**What unblocks the stack job.** A watchdog has to reach `compose.oss.yml` and
`app.py`, so it cannot be moved out of the repo the way the backup was. One of:

1. grant Full Disk Access to `/bin/bash` (System Settings → Privacy & Security) —
   broad, and it is the owner's call;
2. move the project out of `~/Desktop` — also removes iCloud/TCC surprises for
   the whole stack, and is the option that makes every future agent trivial;
3. keep recovery explicit: run `./ops_stack_up.sh` from a terminal (which already
   has the permission), and unload the job so nothing pretends to be watching.

`ops/install_agents.sh --verify` prints which of these is still true; it reports
the 126 honestly rather than showing "loaded" as if that meant "working".

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
