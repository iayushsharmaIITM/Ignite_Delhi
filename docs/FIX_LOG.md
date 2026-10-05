# FIX LOG — correctness pass on `fix/bughunt-2026-10` (2026-10-05)

An outside brief (B01–B14 plus a citation-redesign phase) arrived as a fix-it prompt. This
file is the running account: what was verified, what was refused, what each fix was proven
by, and what the battery said after every commit. Defect IDs continue the ledger
(`BUGS_AUDIT.md` Round 9, A-74…A-88).

Agreed with Ayush before any edit: **scope = correctness only**, **strict on correctness**
(the citation and outage semantics fixed properly rather than guarded), **legacy tenancy =
demonstrate, change nothing**, **hold the push** — the branch was cut locally and nothing is
pushed, merged or deployed.

## Baseline

Before any edit, on `main` at `c5e810a` with the four pre-existing working-tree items left
untouched and unstaged throughout:

```
== done: ran 16 tier(s), skipped 2, failing 0 ==
   did not run: ui-react clerk-gate
```

After the pass, full battery (browser suite included, lab on 5434):

```
== done: ran 23 tier(s), skipped 1, failing 0 ==
   did not run: clerk-gate
```

## Status

| ID | Defect | Status | Files | Test that proves it | Gate after the fix |
|---|---|---|---|---|---|
| A-74 | `/api/source` served `corpus/<filename>` before the authorised brain, so a tenant citation could open Kestrel's demo document | **FIXED** (S1) | `app.py` `source()`, `verify.sh` | `tests/test_source_precedence.py` — 3 of 7 checks failed first, tenant brain returning the corpus file's 2,149 chars | `smoke`, `route-authz` green; tier now always-on |
| A-75 | 120-char fingerprints resolved last-writer-wins; `uploads.json::_collisions` had no reader; an empty corpus file adopted every failed raw fetch | **FIXED** (S2), closes **A-57** | `citations.py` (`_corpus_fingerprints`, new `_name_map`/`_collision_prefixes`, three call sites) | `tests/test_citation_collisions.py` — 2 checks failed then `AttributeError` before `_name_map` existed | new `citation-collisions` tier, 12 checks |
| A-76 | `_durable_reference` used `limit 1` with no ordering on a content-keyed join | **FIXED** (S3) | `citations.py` | `tests/test_durable_identity.py` (new `citations._rows` seam) | new `durable-identity` tier, 12 checks |
| A-77 | `durable_source` opened the newest version, not the one cited | **FIXED** (S3), additive | `citations.py`, `app.py`, `frontend/src/App.tsx`, `SourceModal.tsx`, `frontend/dist` | same tier, plus 2 new checks in `tests/test_source_precedence.py` | full battery incl. `ui-react` |
| A-78 | The modal's where-line called every non-`tenant` origin "from the corpus" | **FIXED** (S3) | `SourceModal.tsx` | `check_ui_react.py` origin-line gate | `ui-react` PASS |
| A-79 | `_states` never pruned, never capped (5,001 expired records reproduced) | **FIXED** (S4) | `connectors.py` | `connectors_test.py` "oauth state is bounded" | `connectors` 90 → 112 |
| A-80 | A known-expired token with no refresh token was still returned | **FIXED** (S4) | `connectors.py` | three-case check (future / past / untracked expiry) | `connectors` PASS |
| A-81 | `invalid_client` / `unauthorized_client` flipped every user to `needs_reconnect`; HTTP status never read | **FIXED** (S4) | `connectors.py` (`refresh_failure`) | five refusal cases, incl. the revoked grant still flipping | `connectors` PASS |
| A-82 | A rotated refresh token that failed to persist was swallowed by `except: pass` | **FIXED** (S4) | `connectors.py` (`rotation_losses()`) | retry-once-then-recorded, stored grant verified stale | `connectors` PASS |
| A-83 | A storage outage answered 403 "Unknown brain"; `/api/source` 404ed | **FIXED** (S8) — reverses the SEC-2 note, approved | `storage.py`, `app.py`, `citations.py`, `verify.sh` | `tests/test_storage_outage.py` — 6 of 11 failed first | new `storage-outage` tier; `route-authz` + `auth-isolation` still green, which is the evidence the denials did not loosen |
| A-84 | `FilesSheet` had no dialog semantics; three other surfaces had the role but none of the focus handling | **FIXED** (S5) | `lib/utils.ts` (`useDialog`), `FilesSheet.tsx`, `SourceModal.tsx`, `Animations.tsx`, `frontend/dist` | 6 new `ui-react` gates | full battery, browser suite PASS |
| A-85 | The OAuth landing pad moved the screen without moving the URL | **FIXED** (S5) | `App.tsx` | 8 new `ui-react` gates (success + failure return, each re-checked after reload) | `ui-react` PASS |
| A-86 | `history.replaceState(…, "")` is a no-op, so the round-trip param was never stripped | **FIXED** (S5), found by A-85's gate | `App.tsx` | observed failing URL: `?connected=google&view=connectors&chat=cfdd6ead-…` | `ui-react` PASS |
| A-87 | A REBUILD job could never publish (both fences required `CREATING`) | **FIXED** (S6), closes **A-58** | `lifecycle.py` (`_publishable`, two fences, recovery select gains `kind`) | `tests/test_rebuild_publish.py` — located both inline comparisons before changing either | new `rebuild-fence` tier; `lifecycle-identity`, `lease-recovery` unaffected |
| B05/B06/X-USAGE | Legacy `NULL/NULL` rows visible to every identity; org-OR-creator; unregistered brains in scoped usage | **DEMONSTRATED ONLY** (Ayush: change nothing) | `tests/test_legacy_visibility.py`, `verify.sh` | characterisation tier, labelled non-security in its own output | `legacy-visibility` PASS / "characterisation only" |
| B04 | `for_dataset` cannot tell "unavailable" from "empty" | **PARTIAL** — the user-visible outcome is already honest ("no citation"), and with A-74/A-75 closed nothing can be substituted. The status plumbing waits for the citation redesign | — | — | — |
| A-88 | `lifecycle.py:263`/`:267` assign `is_rebuild` twice, identically | **OPEN** — reported, unrelated to the fence fix, not touched | — | — | — |

## Refuted (nothing was "fixed" for these)

| Brief | Claim | Why it is not a bug |
|---|---|---|
| B09 | `pop_state` should not consume the token on a wrong-provider attempt | Deliberate and asserted at `connectors_test.py:177-179`, with the attack reasoning in the test: a probe across providers must not leave a live token usable |
| B11 | A transport blip must not return the stale/expired token | Deliberate and asserted at `connectors_test.py:253` (`expires_at = now-10` in the fixture): a flaky network must not force re-consent; the downstream 401 is the detector |
| B03 | `citations` swallowing exceptions silently substitutes a source | Reachable only through the collision path, which A-75 closes. No new exception type was added |
| B05/B06 | The `_owner_clause` arms are vulnerabilities | Documented grandfathering, `storage.py:393-406`. Now characterised, unchanged |
| B10 | Process-local OAuth state breaks under multiple workers | One uvicorn worker, by design (`app.py:2368-2377`, `render.yaml`) |
| Phase 7 | Numbered Perplexity-style citations | Deferred by the owner. A-77's `document_version_id` is the prerequisite, not the redesign |
| B07 | `brain_access` returning `None` on outage is a defect | It was a recorded decision, not an oversight — so it became a decision memo first, and only became code (A-83) after Ayush approved reversing it |

## NEEDS DECISION — open, unanswered, and not worked around

1. **Are legacy rows with both owner columns NULL demo data or somebody's private data?**
   Today every authenticated identity can read them. If they are private: stamp them
   (an ownership backfill, which is Ayush's call and his only), or quarantine them behind
   an explicit shared/demo flag. Nothing here mutates ownership.
2. **Should an org-owned row follow org membership or its creator?** Today either is
   enough, so a former member keeps reading what they created inside an org they left.
3. **Should a brain with no `brain_access` row be hidden from a scoped caller's usage?**
   Today it is included by the grandfathering arm in `usage_summary`'s scope.
4. **Radix consolidation of the four dialog surfaces** (`FilesSheet`, `SourceModal`,
   `UsageModal`, `UpgradeModal`) onto `components/ui/dialog.tsx`. Deferred as structural,
   not correctness; `useDialog` is the interim single implementation.
5. **A `(brain_id, backend_data_id)` unique constraint** would make A-76's clash
   impossible rather than detected. Needs a read of existing rows first — a migration on
   live data is not this pass's authority.
6. **A-72** (`CreateBrainDialog`'s poll never stops, only under `KESTREL_JOBS_V2=1`) was
   in the brief's frontend phase and is **not** fixed here: it was not reproduced against
   a running v2 job, and the flag is off by default.

## Not run against a real stack

- No brain was created, rebuilt, re-ingested or deleted; no live service was restarted.
- The rebuild fence (A-87) was proven by the extracted predicate plus a source-level
  guard, **not** by executing a REBUILD job — that would have needed a real ingest.
- The storage outage contract was proven against a stubbed connection, not by stopping
  Postgres.
- The read-only live query that would count how many non-demo brains share a `corpus/`
  filename was not authorised. It is not load-bearing: A-74 is written so the answer does
  not change what ships.
- `clerk-gate` never ran (needs `KESTREL_CLERK_GATE=1` with the lab), and no Clerk-mode
  behaviour was re-verified beyond the `auth-isolation` and `route-authz` tiers that did.
- Nothing was pushed; CI has not seen this branch.

## Review round — what the fresh reader found in my own fixes

The branch was handed to an independent reviewer with the diff, this file and the ledger
(none of this session's reasoning). Two Critical, five Important, seven Minor; **each one
verified against the code before being accepted**. Ledger: A-89 … A-96.

| Follow-up | Closed | What had been wrong |
|---|---|---|
| S2b | A-89 | The collision sweep matched a **32-character prefix** of a fingerprint and deleted every key that started with it, so a clash between two documents silenced a third that merely opened with the same five words. Reproduced: the unique sibling resolved to None. Ambiguity is a property of the whole fingerprint; the table now stores and matches the whole thing |
| S8b | A-90 | `document_version_id` was shape-checked with a hex regex that admits `12345678`. Against a `uuid` column that raises a psycopg type error, which S8's own contract reads as a storage failure — so one query parameter returned 503 **and** marked storage down, poisoning `/health`. Now a UUID check, with a tier asserting no query leaves the process |
| S8b | A-91 | S8 propagated what `durable_source` used to swallow, which made "this volume has not run migration 0002" a permanent 503 on every tenant source read. `UndefinedTable`/`UndefinedColumn` now answer "no durable rows"; only a real failure marks storage down |
| S8b | A-92 | A pinned citation could still fall through to the version-agnostic tenant read when its version row was missing — the substitution the pin exists to prevent. Now 404 |
| S8b | A-93 | S3 × S6: `backend_data_id` is content and the provenance index is unique per **generation**, so once rebuilds could publish, a rebuilt brain legitimately holds the same content twice and "two matches = ambiguous" would have stripped durable provenance from every rebuilt brain. The active generation is preferred; only a same-generation clash refuses |
| S5b | A-94 | Three gates were weaker than their claim (the fence guard counted call sites anywhere in the file; the OAuth gate proved "Connectors rendered" by the composer being absent; the tenancy lane implied end-to-end visibility), `stopPropagation` let one Escape close two overlays, a provider string was logged unbounded, and a colleague's document in a shared brain was labelled "from your upload" |
| — | A-95 | **OPEN**: `normalize_brain_name` allows a brain called `_collisions`, which is the collision table's own top-level key inside `uploads.json`. Needs a naming decision plus a look for an existing brain by that name |
| — | A-96 | **OPEN**: `d937105` carries `frontend/index.html` without a rebuilt `dist`, so CI's drift check fails *that commit alone*. The branch tip is consistent; fixing the record would need a history rewrite, which is Ayush's call every time |

The claim corrected in the code, the route's OpenAPI notes, the ledger and the test: A-83
first said the missing-row and foreign-row denials were "byte-identical so existence stays
unprobeable". They never were — `"Unknown brain."` and `"…belongs to another workspace."`
differ, and that difference is the enumeration oracle `ACL_AND_MCP_BLUEPRINT` already lists
as Phase 1A's first job. S8 changes neither denial and adds no existence signal; the tier
now asserts the two details *differ*, so if Phase 1A unifies them it has to be done on
purpose.

**Branch after the review round: 12 commits, `ran 23 / skipped 1 / failing 0`, 76 checks
across the six new hermetic tiers, 14 new browser gates, `connectors_test.py` at 112.**

The method note worth keeping: a failing-first test proves the defect you were looking for,
not the ones your fix introduces. Both reviewers' findings this week (the harness round,
then this one) were in code that had already gone green.
