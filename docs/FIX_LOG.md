# FIX LOG — correctness pass, 2026-10-05

Branch `fix/bughunt-2026-10`, cut locally from `main` at `c5e810a` (6 commits still unpushed, on
Ayush's instruction — nothing on this branch is pushed, merged or deployed). Scope agreed with
Ayush: **strict on correctness** — the citation and outage semantics are fixed properly rather than
guarded, and the structural rewrites (Radix consolidation of every dialog surface, splitting
`app.py`, `React.lazy`) are explicitly out of this pass.

Every fix here is: failing test first → confirm it fails for the stated reason → smallest fix →
confirm the test and the rest of the battery both pass. `--quick` is not treated as sufficient
evidence; the tier that can actually see the bug is named each time, and the battery's closing
`ran/skipped/failing` line is quoted.

## Baseline (S0)

Before any edit, on `main` at `c5e810a`:

```
== done: ran 16 tier(s), skipped 2, failing 0 ==
   did not run: ui-react clerk-gate
```

Working tree at the start, untouched by this pass and not staged by any commit here:
`frontend/index.html` (modified), `COMPETITOR_ANALYSIS.md`, `ZCODE_HANDOFF.md`,
`docs/ui-review/screens/41-compare-react-5174.png` (untracked).

**Not measured:** the read-only live query that would count how many non-demo brains have a
document filename colliding with one of the 12 files in `corpus/`. Live DB reads were not
authorised in this pass and the expected answer is zero — the corpus names are demo-specific
(`01_contract_MSA-2025-0114_bluepeak.md` and friends). The fix is written so the answer does not
change what ships: a non-demo citation that only ever resolved out of `corpus/` now reports no
source rather than showing a demo document.

## Status table

| ID | Defect | Status | Files | Test | Gate result |
|---|---|---|---|---|---|
| S1 | `/api/source` reads `corpus/<filename>` off disk before consulting the authorised brain, so a tenant document sharing a demo corpus filename opens the demo's text | **FIXED** | `app.py` (`source()`), `verify.sh`, `tests/test_source_precedence.py` (new) | `tests/test_source_precedence.py` — 7 checks, new always-on `source-precedence` tier | pre-fix: 3 of 7 fail, tenant got the corpus file's 2,149 chars; post-fix `ran 17 tier(s), skipped 2, failing 0` |
| S2 | citation fingerprints are first-120-chars, last-writer-wins; `_collisions` is written and read by nobody | pending | | | |
| S3 | `_durable_reference` uses `limit 1` with no ordering; `durable_source` picks the newest version by `created_at` | pending | | | |
| S4 | connector state and token refresh handling (4 defects) | pending | | | |
| S5 | dialog semantics and the OAuth landing view | pending | | | |
| S6 | rebuild publish fence (E13/A-58) | pending — reproduce only | | | |
| S8 | a storage outage answers 403 "Unknown brain" | pending (was memo D1, approved as a fix) | | | |
| D2 | legacy tenancy (`_owner_clause` NULL/NULL, org-OR-creator, unregistered brains in scoped usage) | **characterise only, no change** — Ayush's call was "demonstrate, change nothing" | | | |

## Refuted premises in the incoming brief (nothing was "fixed" for these)

| ID | Claim | Why it is not a bug |
|---|---|---|
| B09 | `pop_state` consumes the state token before checking provider/expiry, so a wrong-provider callback destroys a valid state | Deliberate, and asserted: `connectors_test.py:177-179` burns the token on a wrong-provider pop with the reason written in the test — an attacker probing states must not be able to try one against several providers and keep a live one usable. Changing it would weaken replay protection for no gain. |
| B11 | On a refresh transport failure the stale token is returned even if expired | Deliberate, and asserted: `connectors_test.py:253` ("network blip -> stale token", with `expires_at = now-10`). A flaky network must not force a re-consent; the downstream call answers 401 and that path already maps to `needs_reconnect`. |
| B05/B06 | `_owner_clause`'s `(org_id IS NULL AND created_by IS NULL)` arm and org-OR-creator let legacy chats be seen across identities | Documented grandfathering in `storage.py:393-406`, not an oversight. See D2 above. |
| B03 | `citations` swallowing every exception silently substitutes a source | With S1 and S2 in place the swallow yields "unresolved", which is the honest outcome; the only path that could substitute was the fingerprint collision, which S2 closes. No new exception type was added. |
| B07 | `brain_access` returning `None` on outage is a bug | It was a recorded owner decision (`app.py:405-409`, SEC-2 fail-closed). Ayush approved reversing it, and that is S8 — the denial for a genuinely missing or foreign brain stays byte-identical so nothing new is leakable. |
| B10 | Process-local OAuth state breaks under multiple workers | There is one uvicorn worker (`app.py:2368-2377`, `render.yaml`), and the single-worker stance is deliberate. Restructuring state into Redis/DB would add infrastructure to get lighter, which is a standing no. Documented, unchanged. |
