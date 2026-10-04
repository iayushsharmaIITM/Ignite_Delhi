# BLOCKERS — escalations out of the iteration protocol (BUILD_PLAN.md §3)

One entry per blocker, newest first. Format:

```
## M<phase>.<n> — <title> — <date>
<diagnosis> / <what was tried> / <exact error output>
<what unblocks it>
```

---

## M-sec.1 — backup snapshots hold plaintext key material, and no gate can see them — 2026-10-04 — **OPEN: owner decision**

Found with the independent scanner (`secrun scan --all`) — the first check here that
looks at **ignored** files. `ops/backup.sh:26-28` deliberately copies `.env` and
`.env.oss` into every backup directory ("key recovery material") and sets them `0600`
(verified: all 8 copies are `-rw-------`). The intent is sound — a restore needs the
config — but the consequence is measured, not assumed:

- `var/backups/20261003T211935Z/env.app:70` matches the `aws-ak` rule: a real `AKIA…`
  access-key id sits in plaintext there, next to the Clerk secret key, Langfuse keys
  and model-provider keys from the same file.
- `var/` is gitignored (`.gitignore:44`) and `git ls-files var` is empty, so **nothing
  in git carries this** — and `ops/check_secrets.sh --all` scans tracked files only, so
  it cannot see these by design. The `--env` and `--context` surfaces came back clean.
- The copies sit under `~/Desktop/Kestrel_brains` — the same iCloud/TCC-exposed path
  that makes M-ops.1 impossible — on the same disk as the database they restore, so
  they buy no separation while adding a sync surface. Retention keeps 14 such dirs.
- The same scan's 12 tracked-file hits were reviewed and are **false positives**:
  `${POSTGRES_PASSWORD}`-style interpolation, the detector's own regex text, the
  `KESTREL_ALLOW_SECRETS` advice string, and a minified React warning ("…but you
  passed …") in the committed bundle. **No credential is in git.**

**Options, not a plan:** (1) accept it as at-rest risk on an encrypted volume;
(2) move the repo off `~/Desktop`, which also fixes M-ops.1; (3) keep key material
out of backups and reference it instead (the `secret-fetch` / KMS route); (4) rotate
the AWS key if that folder is or was iCloud-synced. A key that has sat in plaintext
copies needs rotating at the provider, not just deleting from disk — and rotation is
explicitly the owner's call.

---

## M-delivery.1 — the repository has no delivery boundary and no second copy — 2026-10-04 — **OPEN: owner action**

**Measured 2026-10-04 while checking whether the new CI steps could be verified.**

- `git status -sb` → `main...origin/main [ahead 172]`.
- `git ls-tree -r --name-only origin/main | grep workflows` → nothing. The workflow
  file exists only in the working tree.
- `gh api repos/…/actions/workflows` → **0** workflows; `gh run list` → empty.

So every claim this repo has made about CI ("fails on every push", "the battery is
what CI runs", "dist sync is enforced") describes a pipeline that has never executed.
`ci.yml` is a well-formed intention, not a control. The delivery-acceptance dimension
of the harness review scored 48 partly because it could not observe a boundary; the
real answer is that there isn't one.

**The bigger exposure is not CI, it is that the work exists in one place.** 172 commits
plus the live database plus the nightly backups are all on this laptop. `~/Kestrel_backups`
sits on the same disk as `~/Desktop/Kestrel_brains`, and the Git history has no remote
copy. One dead SSD takes the code, the data and the backups together — which is exactly
the failure the backup script exists to prevent, defeated by location rather than by
logic.

**What unblocks it (in order, all owner decisions):**
1. `git push` the 172 commits (first push publishes the workflow → CI runs → H-2 and
   the `dist`-sync and secret-scan gates start existing). `gh` is installed and
   authenticated with `repo` + `workflow` scopes, so nothing needs installing for this.
   Expect the **first** run to be the real test of everything assumed about CI.
2. Add a branch protection / required-check step once runs exist, or the acceptance
   boundary stays advisory.
3. Copy the backups off-disk (any object storage, or a second machine). The backup
   job is honest and the artefacts restore; they just are not *elsewhere*.

**Not done here deliberately:** pushing is a shared-state write with 172 commits behind
one command, and the first CI run may fail in ways only visible on the hosted runner.
That is a decision to make awake, not an agent convenience.

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

**Update, same day — the backup half of this is closed with evidence.**
`com.kestrel.backup` was reinstalled with `ops/install_agents.sh` and triggered
**through launchd** (`launchctl kickstart`), not from a terminal: it wrote
`~/Kestrel_backups/20261003T223258Z` with a clean dump plus both volume tars, and
`shasum -a 256 -c SHA256SUMS` verifies all three. `install_agents.sh --verify` now
hashes the repo copy against the installed copy and exits 1 on drift — it reported
DRIFT before the reinstall and "matches" after — because the stale installed copy
was the thing writing `  ok: pg_dump` into every nightly dump. **The stack-up job
remains open**: it has to read the repo, so it needs decision 1 or 2.

`ops/install_agents.sh --verify` prints which of these is still true; it reports
the 126 honestly rather than showing "loaded" as if that meant "working".

---

## M-ops.2 — the restore drill cannot prove brain-level recovery (lab LLM endpoint) — 2026-10-04 — **OPEN**

**What is proven.** `ops/restore_lab.sh` restores a real backup into the lab and
now reports every gate: schema dropped and reloaded cleanly, `brain_access=2`,
`chats=8`, `graph_node=93`, both cognee volume tars listed, dataset present on the
restored copy, lab cognee healthy. Before this pass the drill died at the first
line of the restore (`relation "alembic_version" already exists`) and, after that,
silently mid-gate under `set -e` — a failed drill that printed nothing looked like
a passed one.

As of 2026-10-04 the drill also consumes **the nightly job's own artefacts**. It
previously understood only `ops/backup.sh`'s `.tgz` names and repo-relative paths,
so the schedule that actually runs at 03:17 had never been restored end to end; the
first thing that did was the corrected dump (`20261003T223258Z`, taken through
launchd, SHA256SUMS verified, no runner chatter inside `db.sql`).

**What is not proven.** The final gate (ask the restored brain) fails with
`GATE demo-answer: FAIL (0 chars, 0 refs)`. The cause is now read from the lab
cognee logs rather than guessed: **not** a `LiteLLM TimeoutError` and not lab
network config —

```
RateLimitError: OpenAIException - You've used this period's free allowance.
Your next rolling 7-day period starts on 6 Oct 2026 at 07:29 UTC.
```

The lab's credential (`.env.oss LLM_API_KEY`, via openrouter) is out of free
quota, so cognee retries with backoff and the ask never completes inside 240s.
This is an upstream quota window, so the gate is blocked until **2026-10-06
07:29 UTC** unless the lab is pointed at a paid model/key — a configuration choice,
not a code fix, and it needs the owner's call because it spends money.

**What this does NOT say about live.** Live uses a *different* credential
(`.env TOKENHARBOR_API_KEY`, base `https://tokenharbor.ai/v1`, model
`deepseek-v4.1-flash:free` — same provider family, same `:free` tier), so live may
or may not be inside the same allowance. It could not be measured from here:
`/api/ask` on the live app answers `401 A valid Clerk session token is required`,
so a CLI probe never reaches the brain. **One question in the browser settles it,
and it should be asked before any demo.**

**What unblocks it.** Point the lab brain at a working LLM/embedding endpoint (the
live container's config in `compose.lab.yml` env) or wait for the quota window to
roll at 2026-10-06 07:29 UTC, then re-run `./ops/restore_lab.sh
~/Kestrel_backups/<latest>`. Until then: "we can restore" is proven for schema,
rows, volumes and the dataset, and unproven for answering.

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
