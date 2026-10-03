# Bug audit — post-P3 pass (28 Sep 2026)

Fresh audit run after P3 (Clerk auth) shipped and both Clerk dashboard actions
went live. This file is a **fix work-queue**: every entry below is OPEN.
It does not renumber `BUGS.md`; that pass's C1–C3 / H1–H5 / M1–M7 are fixed
except **M4 (TOCTOU)**, which stays open there (see Cross-reference).

Method: read the source, then re-verify against the live stack
(`localhost:8000`, Clerk mode) and by execution — signed-JWT probes, direct
Postgres reads, direct function calls. Each entry states its proof:

- **[E]** proven by execution (measured output shown)
- **[R]** code path confirmed by reading (exact lines quoted)

Fix sizes: **S** = a few lines, one file · **M** = one function/route plus a
test · **L** = needs a design decision or touches many call sites.

---

## STATUS — Round 1 CLOSED (2026-10-04)

**All 45 items above are fixed in the current tree.** The queue was worked
systematically by ID: each fix carries an in-code comment naming its audit ID
(`SEC-1/2/4/5/6/8/9/10`, `COR-1…11`, `LOW-1…9`), and every Tier-2/Tier-3 site
was re-verified against the React port rather than the legacy file it was
written against. No legacy defect was reimplemented in React — the port routes
every call through `apiFetch` (`frontend/src/lib/api.ts`), which is exactly the
"one helper" fix this file's Systemic Patterns §2 asked for.

Corroborated live (not just by reading): `GET /api/brains` and
`GET /api/brains/{name}/events` now return **401** unauthenticated (SEC-3,
LOW-10 — both were 200), and the frontend transport gate passes
(`python3 tests/test_frontend_api_transport.py` → "every /api call goes
through apiFetch, and the served bundle is complete").

**Caveat:** this closure is code-audit + the two measurements above. It has
**not** been re-run through `./verify.sh` — the stack was down when this status
was written (colima stopped, 00:32). Re-run the battery before repeating the
word "fixed" to anyone.

Three residuals, all deliberate or missing-test, not regressions:

- **SEC-5 backfill.** `storage.py` `_owner_clause` still hands
  `(org_id IS NULL AND created_by IS NULL)` rows to *every* authenticated
  user, by design, "until the item-1 backfill". Pre-P3 chats remain
  cross-tenant visible until the creator backfill runs. **Owner decision.**
- **SEC-2 nuance.** A Postgres outage now fails closed as **403** rather than
  the 503 this file suggested; documented as an explicit choice in the
  `brain_allowed` docstring.
- **Missing regression test.** `tests/test_route_authz.py` has route-level
  authz coverage but no case-variant delete (`DELETE /api/brains/ACME_ISOLATED`)
  — the exact SEC-1 exploit. Add it even though the code is fixed.

**Round 2 (the chat subsystem + React shell) is the live queue — see the bottom
of this file.**

---

## Summary

### Tier 1 — security & data destruction

| ID | Sev | Bug | Where | Size |
|---|---|---|---|---|
| SEC-1 | CRITICAL | Delete authorizes the **raw** name, then deletes the **normalized** one → cross-org brain deletion | `app.py:810` vs `817,838` | S |
| SEC-2 | CRITICAL | Brain authorization **fails open**: no `brain_access` row (or a DB error) = allowed; only `create_brain` ever writes a row | `app.py:155-157`, `storage.py:233-240`, `app.py:663-665` | M |
| SEC-3 | HIGH | `GET /api/brains/{name}/events` has **no auth gate at all** | `app.py:740-741` | S |
| SEC-4 | HIGH | `DELETE /api/chats/{id}` checks identity but not ownership | `app.py:413-418`, `storage.py:196` | S |
| SEC-5 | HIGH | Chats are effectively public: client-supplied `org_id`, and NULL-org rows list for everyone | `storage.py:141,167` | M |
| SEC-6 | HIGH | Path traversal via `?dataset=../uploads` → reads arbitrary `fixtures/*.json` as a graph | `app.py:288-290` | S |
| SEC-7 | MED-HIGH | JWKS cache TTL is dead code — Clerk key rotation breaks auth until restart | `auth.py:56-75` | S |
| SEC-8 | MED | Org-less creator locked out of their own brain; the "creator" branch in the docstring does not exist | `app.py:147-163` | S |
| SEC-9 | MED | Ownership row is written **before** upload validation → stale owner survives a failed create | `app.py:663-673` | S |
| SEC-10 | MED | Chat turn rewrite is non-atomic; `_ts` misses `OSError`/`OverflowError` → partial turn loss / 500s | `storage.py:47,143-158,259-265` | M |

### Tier 2 — Clerk-mode frontend (one defect class)

| ID | Sev | Bug | Where | Size |
|---|---|---|---|---|
| FE-1 | HIGH | `authHeaders()` returns `{}` until Clerk boots and never awaits the boot promise → every parse-time caller is unauthenticated | `static/auth.js:66-73,108` | S |
| FE-2 | HIGH | `/graph` shows "no graph yet" in Clerk mode (parse-time fetch, misread 401 as empty) | `static/graph.html:613` | S |
| FE-3 | HIGH | Source modal ("open the passage") 401s — fetch sends no auth | `static/index.html:1036` | S |
| FE-4 | MED | Chat restore: first GET races boot; the local-only push POST/GET **never** authenticate | `static/index.html:881-901` | S |
| FE-5 | MED | In-chat uploads to an existing brain POST without auth → silently dropped | `static/index.html:1189,1768,1808` | S |
| FE-6 | MED | Chat deletes send no auth → server copy survives, "deleted" chats return | `static/shell.js:89,108`, `static/index.html:1630` | S |
| FE-7 | MED | "Delete brain" always GETs (options passed as 3rd arg) → **405 in every mode**, button never worked | `static/brains.html:180-182` | S |
| FE-8 | MED | Citations render but are never persisted (references event lands after `done`; TURNS entry keeps `[]`) | `static/index.html:1135,1231-1253` | S |
| FE-9 | MED | Rail tooltip XSS: model text into `innerHTML`; `clean()` is markdown-strip, not escaping (same class as fixed C2) | `static/index.html:1408,1640-1654` | S |

### Tier 3 — correctness & runtime

| ID | Sev | Bug | Where | Size |
|---|---|---|---|---|
| COR-1 | HIGH | Fixture fallback never fires: `produced` flips on **stage** events, so any failure after the first step loses the fallback and mislabels a never-streamed answer as "incomplete" | `memory_layer.py:109-135` | S |
| COR-2 | HIGH | `wait_ready` treats `...FAILED` as ready → `ingest.py` snapshots a failed graph and prints "Graph ready" | `cognee_cloud.py:346-349`, `ingest.py:177-197` | S |
| COR-3 | HIGH | `KESTREL_RACE_RETRIEVAL=0` path is 100% broken: 6 positional args to a 5-param `recall` → TypeError on every ask | `orchestrator.py:79-81` | S |
| COR-4 | MED | A citations failure **after** `done` mislabels a complete answer "(connection dropped mid-answer … incomplete)" and persists the label | `citations.py:293`, `orchestrator.py:177-182`, `memory_layer.py:115-126` | S |
| COR-5 | LOW | Hardcoded `"company_brain"` duplicates `DEMO_DATASET`; drifts silently | `orchestrator.py:163` | S |
| COR-6 | MED | Smalltalk classifier: common thanks-phrases classify BRAIN; content words classify SMALLTALK | `memory_layer.py:182-201` | M |
| COR-7 | MED | Router routes on `"CHAT" in reply` substring — a negation ("not a chat") flips the route | `orchestrator.py:238-241` | S |
| COR-8 | MED | Fingerprint collisions: 3 upload entries share one fingerprint → a citation can resolve to the wrong file | `citations.py:60-62,117,181` | M |
| COR-9 | MED | Encrypted PDF escapes `extract_many` → HTTP 500 (should be a clear 400/422) | `documents.py:103,209`, `app.py:673` | S |
| COR-10 | MED | Mock/offline references are bare strings while the UI contract is enriched objects → no usable chips in mock mode | `memory_layer.py:168-173` | S |
| COR-11 | MED | Summarizer calls blocking `requests.post(..., timeout=90)` inside async → stalls every other request | `summarizer.py:26-51` | S |
| COR-12 | LOW | i18n: `apply()` runs in `<head>` (before the DOM); duplicate `up.sub` key in all 6 locales | `static/ui.js:583,58,83` | S |
| COR-13 | LOW | Light theme: watermark / nav hover / graph panel hardcode dark-theme colors | `index.html:34`, `shell.css:26-28,78-80,184`, `graph.html:22-31` | S |
| COR-14 | LOW | `esc()` strips `<>&"` instead of escaping → "R&D" renders as "RD" | `static/shell.js:122` | S |
| COR-15 | MED | Mid-stream failure wipes the bubble even after `finalized`, and a transport error discards a partial answer; AbortError path is the correct model | `index.html:1234-1236,1285-1288`, `app.py:485-487` | S |

### Low / hardening

| ID | Bug | Where |
|---|---|---|
| LOW-1 | `warmup.py` / `battery.py` unusable against `AUTH_MODE=clerk` (no tokens) | `warmup.py`, `battery.py` |
| LOW-2 | `setInterval` step ticker never cleared (one leak per ask) | `index.html:1164` |
| LOW-3 | `.bar-menu-row` never exists → the "PDF blocked" notice can never show (TypeError in the catch) | `index.html:1574` |
| LOW-4 | `/api/usage` returns platform-wide metering, not the caller's | `storage.py:243-256`, `app.py:421-423` |
| LOW-5 | `/health` leaks service URL + DB host unauthenticated | `app.py:328` |
| LOW-6 | Malformed JSON body → 500 instead of 400 | `app.py:383-391` |
| LOW-7 | JWT: `alg` taken from the token header; `exp` not required | `auth.py:99-103` |
| LOW-8 | `snapshot.py` can blank `index.json` on a failed read | `snapshot.py` |
| LOW-9 | `record_upload` non-atomic + overwrites on collision (feeds COR-8) | `citations.py:105-129` |
| LOW-10 | `GET /api/brains` lists every brain unauthenticated | `app.py:539` |
| LOW-11 | `GET /api/chats/{id}` checks identity but not ownership | `app.py:403-405` |

---

## Tier 1 — security & data destruction

### SEC-1 · CRITICAL — delete authorizes the raw name, deletes the normalized one

**Where** `app.py:810` (authorization, raw name) vs `app.py:817,838` (delete, normalized name).

**What** `delete_brain` runs `require_dataset_access(request, name)` on the **raw**
path segment. The authz rule looks the name up exactly (`storage.brain_access`),
and rows are only ever stored normalized. `ACME_ISOLATED` has no row → `None` →
"nothing stored about this brain: allow" (`app.py:155-157`). Then line 817
normalizes the same string to `acme_isolated` — the victim's dataset — and line
838 deletes it.

**Why it matters** Any authenticated tenant can permanently delete another
tenant's brain by changing the case. It also defeats the reserved-name guard
for the same reason (the reserved check runs on `safe`, after authz on the raw).

**Proof [E]** Live code, direct calls:
`brain_access('ACME_ISOLATED')` → `None` → `brain_allowed` returns (allow),
while `normalize_brain_name('ACME_ISOLATED')` → `'acme_isolated'`.
Live DB confirms the row exists only under the normalized key:
`brain_access('acme_isolated')` → `org_A`.

**Fix** Normalize first, authorize the normalized name:
`safe = normalize_brain_name(name)` → 400 if falsy → `require_dataset_access(request, safe)` →
reserved check → `delete_dataset(safe)`. One name, one meaning, start to finish.

**Verify** Route-level test: seed `acme_isolated`/`org_A`; DELETE as `org_B`
with `ACME_ISOLATED` → 403; as owner with the same casing → 200 and the dataset
is gone.

---

### SEC-2 · CRITICAL — brain authorization fails open

**Where** `app.py:155-157` (`rec is None: return`), `storage.py:233-240`
(`brain_access` returns `None` on any exception), `app.py:663-665`
(`register_brain` is the only writer, and only on create).

**What** "No row" and "database error" are the same value at the caller, and
both mean **allow**. Any dataset that never went through `create_brain` has no
row: brains ingested by script, pre-P3 brains, anything created by ops. During a
Postgres outage every brain in the system becomes readable by any valid token.

**Why it matters** This is the difference between authorization and decoration.
The demo brain is already registered (`company_brain`, shared), so denying
unknowns is safe — the fix is to flip the default, not to add an allowlist.

**Proof [E]** Live `brain_access('<never-created>')` → `None`; live DB shows
only 2 rows total. **[R]** `storage.py:233-240` swallows every exception to
`None`. `register_brain` call-site grep: one, inside `create_brain`.

**Fix** `if rec is None: raise HTTPException(403, "Unknown brain.")`; seed
`company_brain`/shared at startup (or treat `DEMO_DATASET` as an explicit
allow). Optionally let a DB outage be a 503 — fail closed loudly, not open
silently.

**Verify** Create a dataset out-of-band (direct cognee call), then ask it with
any token → 403. Stop Postgres → ask the demo brain → 401/403/503, never 200.

---

### SEC-3 · HIGH — the events stream has no auth gate at all

**Where** `app.py:740-741` — no `require_tenant` / `require_dataset_access`
anywhere in the handler (grep of all route auth calls confirms the gap).

**What** `GET /api/brains/{name}/events` streams pipeline progress (and with
`timeout_s` unbounded until H4's clamp) to anyone, unauthenticated, even in
Clerk mode.

**Why it matters** Unauthenticated access to a tenant-scoped resource —
textbook. Doubles as an unauthenticated long-poll DoS while the clamp is the
only bound.

**Proof [E]** Live: `GET /api/brains/company_brain/events?timeout_s=5` with no
token → **200**. Contrast `/api/stats` → 401 in the same batch.

**Fix** `require_dataset_access(request, name)` at the top of the handler,
mirroring every other route.

**Verify** Re-run the same curl → 401; with a valid token for an unrelated org
→ 403.

---

### SEC-4 · HIGH — chat deletion has no ownership check

**Where** `app.py:413-418` (identity only), `storage.py:196`
(`DELETE FROM chats WHERE id = %s`).

**What** Any signed-in user who knows (or guesses) a chat id can delete it —
any org, any brain. Ids are `c<timestamp>-<rand>` and are enumerable today via
`GET /api/chats` because of SEC-5 (all 26 live chats have `org_id NULL`, so
every authenticated user sees every id).

**Why it matters** Cross-tenant destruction of the user's own work product.
"Knows the id" is not a security property.

**Proof [R]** Route body has `require_tenant` and nothing else; the storage
statement has no org predicate. **[E]** Live: the 26 ids are listable through
the NULL-org path (SEC-5 measurement).

**Fix** Pass the identity down: `DELETE ... WHERE id = %s AND (org_id = %s OR
org_id IS NULL AND brain says so)` — better, stamp `org_id` on every chat
server-side (SEC-5 fix), then require `org_id = identity.org_id OR is_shared`.

**Verify** Two identities, one chat: owner deletes → 200; other org deletes →
403/404 and the row survives.

---

### SEC-5 · HIGH — chats are effectively public

**Where** `storage.py:141` (`org_id` read from the client-supplied record),
`storage.py:167` (`WHERE (org_id = %s OR org_id IS NULL)`), `app.py:383-391`
(upsert route).

**What** The server never stamps the identity onto a chat; it stores whatever
the client sends (or nothing). Every historical chat has `org_id NULL`, and the
list query deliberately returns NULL rows to **everyone** — so every chat
written before P3 is visible to every tenant. The client can also self-declare
membership in someone else's org.

**Why it matters** Cross-tenant read of conversation history, including
uploaded-document excerpts quoted in the turns. In a 10–100-seat product this
is the reportable kind of bug.

**Proof [E]** Live DB: `SELECT count(*) ... org_id IS NULL` → **26 of 26**;
`chats.org_id` nullable = YES. **[R]** the list predicate above.

**Fix** Server-stamp `org_id`/`created_by` from `request.state.identity` on
every write; backfill existing rows to their brain's owner (or a `legacy` org)
once; then drop the `OR org_id IS NULL` escape hatch.

**Verify** Insert via API as org_A; list as org_B → absent. Legacy rows appear
only for the backfilled owner.

---

### SEC-6 · HIGH — path traversal via `?dataset=`

**Where** `app.py:288-290` — `candidates = [BRAINS_DIR / f"{target}.json"]`
with `target` taken unmodified from the query string.

**What** A `dataset` like `../uploads` resolves to `fixtures/uploads.json`;
`../graph` resolves to `fixtures/graph.json`. The authz layer lets it through
because the traversal name has no `brain_access` row (SEC-2's fail-open), and
`_load_graph` happily serves whatever JSON it finds.

**Why it matters** Breaks the fixture-directory boundary — anything a future
writer drops in `fixtures/` becomes readable. The served shape is "a graph",
so the leak is quiet. The `/api/source` route got a careful path-safety triad;
this route got none.

**Proof [E]** Live: `GET /api/graph?dataset=../uploads` → authz ALLOWED,
`_load_graph` returns a dict with 7 keys parsed from `fixtures/uploads.json`.
`fixtures/brains/../graph.json` exists; `../tenants.json` does not.

**Fix** Reuse `normalize_brain_name` (or an allow-list regex `^[a-z0-9_-]{1,64}$`)
on `dataset` before it touches the filesystem, and `resolve()`+confine the
result to `BRAINS_DIR`.

**Verify** All traversal attempts (`../uploads`, `..%2f`, absolute paths,
`a/../../x`) → 400/404, never a JSON graph.

---

### SEC-7 · MED-HIGH — the JWKS TTL is dead code

**Where** `auth.py:56-64` (`@lru_cache(maxsize=4)` on `_fetch_jwks`),
`auth.py:71-75` (the TTL check that calls it).

**What** The TTL branch compares `_JWKS_TS` and then calls the `lru_cache`d
fetch — which returns the cached keys forever without ever stamping a new
timestamp. Net effect: **keys are fetched once per process and never
refreshed.**

**Why it matters** Clerk rotates signing keys. After a rotation every new
token fails verification, fail-closed, until the process restarts — an
outage triggered by an event the TTL was written to absorb. The shipped test
never caught it because it injects JWKS via `inject_jwks_for_test`, so
`_fetch_jwks` is never exercised (`test_auth_isolation.py:64-78` — vacuous).

**Proof [E]** Two calls → `CacheInfo(hits=1, misses=1)`; simulating 700s and
calling again returns the same object with `_JWKS_TS` unchanged.

**Fix** Drop `lru_cache`; store `(ts, data)` and refetch when stale, or use
`cachetools.TTLCache`. Add a test that actually drives `_fetch_jwks` with a
rotating stub URL.

**Verify** New test: stub source returns key A, advance the clock past the
TTL, source returns key B → the second verify uses B.

---

### SEC-8 · MED — the org-less creator is locked out of their own brain

**Where** `app.py:147-163` — docstring line 150 promises "or the creator when
org-less"; the body (lines 158-161) only checks `is_shared` and org equality.

**What** A user who signs in without an active Clerk organization creates a
brain; the row's `org_id` is NULL/empty; on return, `rec.get("org_id")` is
falsy and the caller gets 403 on the brain they just built.

**Why it matters** Clerk users can be org-less (personal account), and the
code already stores `created_by` (`register_brain(name, org, user)`) — the
identifier exists, it is just never consulted.

**Proof [R]** The branch does not exist; the docstring and body disagree.
**[E]** allowed/denied paths for org members measured (org_A allow, org_B 403).

**Fix** Add the promised branch: `if rec.get("created_by") and
rec.get("created_by") == identity.get("user_id"): return`.

**Verify** Row `(brain, org=None, created_by=user_A)`: user_A → allowed;
user_B → 403.

---

### SEC-9 · MED — ownership is registered before the upload can fail

**Where** `app.py:663-665` (`register_brain`) runs before payload validation
(666) and extraction (673); `storage.py:219-230` does `ON CONFLICT DO NOTHING`.

**What** A create request that fails validation or extraction still leaves an
ownership row for a brain that was never created. If another org later
succeeds with the same name, `DO NOTHING` keeps the stale owner — the second
org builds the dataset but the row credits the first, and `brain_allowed`
(org match) hands control to the wrong tenant.

**Why it matters** Silent ownership confusion, reachable without an attacker:
one user fat-fingers an upload, the name is poisoned for everyone.

**Proof [R]** Statement order in the handler; `ON CONFLICT DO NOTHING`
semantics in storage.

**Fix** Register ownership only after the dataset is confirmed created (or
delete the row on every failure path). `create_brain` is already async with a
clear success point after ingest.

**Verify** Fail an upload (bad payload), then create the same name as a
different org → the second org owns it.

---

### SEC-10 · MED — non-atomic turn rewrite, narrow timestamp handling

**Where** `storage.py:47` (`autocommit=True`), `143-158` (DELETE then per-row
INSERTs), `259-265` (`_ts` catches only `TypeError, ValueError`).

**What** Saving a chat deletes all turns and re-inserts them one statement at a
time, each auto-committed. A failure between statements loses the history
permanently. Separately, `_ts` re-raises `OSError`/`OverflowError` (e.g. an
out-of-range date from a client), turning a bad input into a 500 on
save/restore.

**Why it matters** The DELETE is the dangerous half: it commits before the new
rows exist. A crash, OOM, or connection blip mid-rewrite = empty chat.

**Proof [R]** Autocommit + statement order; the exception tuple is explicit.

**Fix** Wrap the rewrite in an explicit transaction (single `with conn:`
block), and widen `_ts` to a catch-all that returns `None` for unparseable
timestamps.

**Verify** Kill the connection between statements (stub) → old turns survive;
POST a chat with a garbage `at` → 200 with the field dropped, not 500.

---

## Tier 2 — Clerk-mode frontend: one defect class

The root cause is FE-1; FE-2…FE-6 are instances. One helper fixes the class.

### FE-1 · HIGH — `authHeaders()` is empty until boot, and nobody waits

**Where** `static/auth.js:66-73` (`if (mode !== 'clerk') return {}`),
`static/auth.js:47-64` (mode flips only after `/api/config` + `Clerk.load()`),
`static/auth.js:108` (`init()` fires at script eval).

**What** `authHeaders()` has no knowledge of the in-flight boot. Any caller
that runs at parse time — `restoreHistory()` (`index.html:1671`), the graph
fetch (`graph.html:613`) — gets `{}` and fires an unauthenticated request. The
`booted` promise already exists (line 48); it is simply never awaited.

**Why it matters** It converts "Clerk mode" into "silently broken page" for
everything that runs early, and it is the structural reason FE-2/FE-4 exist.

**Proof [R]** The three lines above. **[E]** Live: authenticated-only routes
return 401 without a token (`/api/source`, `/api/chats`, `/api/stats`) — so
`{}` means failure, not "no-op".

**Fix** `await booted;` as the first line of `authHeaders()` (and keep the
`{}` fallback for auth-off). One line.

**Verify** Load the ask page in Clerk mode with the network throttled; the
restore and graph requests must carry `Authorization` on first fire.

---

### FE-2 · HIGH — `/graph` is dead in Clerk mode, and lies about why

**Where** `static/graph.html:613` — the fetch runs at parse time with
`authHeaders()`'s `{}`.

**What** The 401 body parses as valid JSON without `.error`, so `rawNodes`
is empty and the page shows "This brain has no graph yet. Ingestion may still
be running" — a false diagnosis of an auth failure.

**Why it matters** The graph is a core selling surface; in Clerk mode it
never renders for anyone.

**Proof [R]** Call site + empty-graph branch. **[E]** `/api/graph` requires
auth (401 without token, same family as measured routes).

**Fix** FE-1, plus treat `!res.ok` as an error state in graph.html instead of
falling into the empty branch.

**Verify** Open `/graph?brain=...` signed in → nodes render; signed out →
an auth message, not "no graph yet".

---

### FE-3 · HIGH — the citations modal 401s

**Where** `static/index.html:1036` — `fetch('/api/source?' + params…)` with no
headers.

**What** The "open the passage" flow — the feature the whole citation design
exists for — fails in Clerk mode: 401 → "Could not open this source".

**Why it matters** It is the proof-of-grounding affordance; broken auth here
undermines the product's cardinal claim.

**Proof [R]** Call site; **[E]** `/api/source?name=…` → 401 without a token
(measured live).

**Fix** Add `headers: await window.KestrelAuth.authHeaders()`.

**Verify** In Clerk mode, click a citation chip → the modal opens with the
highlighted passage.

---

### FE-4 · MED — chat restore: a boot race and two headerless calls

**Where** `static/index.html:881-882` (GET races boot) and `898-901` (the
local-only-chat push POST + refetch send **no** auth at all).

**What** In Clerk mode the server read can 401 (race), and the fallback path —
which migrates a local chat to Postgres — always fires without a token, so it
never migrates and the cleaned server render never arrives.

**Why it matters** History restore is the headline feature (C1 in BUGS.md).
It regresses specifically in the mode P3 shipped.

**Proof [R]** Both call sites: one awaits a headerless-until-boot helper, two
send no headers. **[E]** `/api/chats` → 401 without a token (measured live).

**Fix** FE-1 fixes 881; add headers to 898-901.

**Verify** Sign in, clear localStorage, send a message, reload → the turn
restores from Postgres.

---

### FE-5 · MED — in-chat uploads silently dropped

**Where** `static/index.html:1189` (attach to current brain), `1768`, `1808`
(upload page paths).

**What** `fetch('/api/brains', { method:'POST', body: fd })` without auth →
401 in Clerk mode; the rejection is swallowed by `.catch(() => {})` at 1192.

**Why it matters** "Add these files to this brain" appears to work and does
nothing — the worst failure shape.

**Proof [R]** Call sites + the swallowing catch. **[E]** POST /api/brains
requires a tenant (`app.py:631` guards it).

**Fix** Add headers; surface the failure in the step log instead of swallowing.

**Verify** Attach a file in Clerk mode → the step log shows it ingested; check
the brain grew.

---

### FE-6 · MED — deletes never reach the server

**Where** `static/shell.js:89` (`deleteChat`), `static/shell.js:108`
(`deleteBrainChats`), `static/index.html:1630` (new-chat cleanup).

**What** All three send `DELETE` with no auth headers and swallow the
rejection. The local copy is removed; the Postgres row is not — so the chat
reappears on the next list/reload, and "delete this brain's chats" is a local
illusion.

**Why it matters** Users believe data is deleted when it is not — a trust bug
with a privacy flavor.

**Proof [R]** Three call sites, all headerless. **[E]** `/api/chats` requires
auth (401 measured); the DELETE route shares the gate.

**Fix** Add headers to all three.

**Verify** In Clerk mode delete a chat → reload → it stays deleted; check the
DB row is gone.

---

### FE-7 · MED — "Delete brain" has never worked (405 in every mode)

**Where** `static/brains.html:180-182` —
`fetch(url, { headers: … }, { method: 'DELETE' })`.

**What** `fetch` takes two arguments; the third is ignored. The request is a
**GET**, the route is `@app.delete` (`app.py:797`), FastAPI answers **405**,
and the UI shows "delete failed: HTTP 405". This is broken in auth-off mode
too — it is not a Clerk regression.

**Why it matters** There is no way to delete a brain from the UI at all;
users accumulate junk brains with no recourse.

**Proof [E]** Live: `GET /api/brains/company_brain` → **405** (route is
DELETE-only); **[R]** the call site's argument shape.

**Fix** Merge the options: `fetch(url, { headers: await
window.KestrelAuth.authHeaders(), method: 'DELETE' })`.

**Verify** Click delete (two-step armed confirm) → 200, row and dataset gone.

---

### FE-8 · MED — citations render but are never persisted

**Where** `static/index.html:1135` (finalize stores `sources` into TURNS),
`1231-1233` and `1251-1253` (the references handlers rebind + re-render but do
not update the saved turn); server ordering is `orchestrator.py:175` (`done`)
then `182` (`references`).

**What** In the cloud path, `done` arrives first and finalize snapshots the
then-empty `sources` into TURNS. The `references` event lands after, updates
the DOM, and calls `saveHistory()` — but TURNS still holds `[]`, so what is
persisted has no citations. After a reload the chips are gone (and SOURCES is
empty, so the follow-up actions lose their source list too).

**Why it matters** The citation trail survives only until the next reload —
the exact artifact that makes the product trustworthy.

**Proof [R]** Both handlers rebind the loop variable; nothing writes back to
`TURNS[last].sources`. Server ordering quoted above.

**Fix** In the references handlers, update the last bot turn before saving:
`const t = TURNS.filter(x => x.role === 'bot').pop(); if (t) t.sources = sources;`
then `saveHistory()`.

**Verify** Ask a cloud question, wait for chips, reload → chips restore from
Postgres.

---

### FE-9 · MED — rail tooltip XSS (same class as the fixed C2)

**Where** `static/index.html:1408` —
`railTip.innerHTML = '<b></b>' + (answer ? answer + '…' : '')`; `clean()`
(`1640-1654`) strips markdown, it does not escape HTML.

**What** `answer` is `clean(TURNS[i+1].text)` — model output derived from
user-uploaded documents. HTML in a document can survive into an answer and
execute on tooltip hover. This is the C2 defect (graph legend) replicated on
the rail; the correct pattern (create/ set `textContent`) sits 10 lines away
for the `<b>` element.

**Why it matters** Stored XSS with a plausible delivery path (a crafted
document in a shared brain). The product's users run it on their own
documents; one malicious PDF in a team brain is enough.

**Proof [R]** The innerHTML site; `clean()` performs no escaping; the fixed C2
pattern is in the same file.

**Fix** Build the tooltip with nodes: keep `railTip.querySelector('b')` for the
label and append a text node for the excerpt, or escape `answer` before
interpolation.

**Verify** Inject a node/text containing `<img src=x onerror=…>` into a turn's
text → hover the rail tick → no execution, text shown literally.

---

## Tier 3 — correctness & runtime

### COR-1 · HIGH — the fixture fallback never fires, and the "incomplete" label lies

**Where** `memory_layer.py:109-135`.

**What** `produced = True` is set for **every** event, including
`{"stage":"step"}` — and the orchestrator emits a step ("planning retrieval
agents") before any retrieval happens. So when the cloud path fails after that
first step but before any text, `produced` is already true: the code takes the
"connection dropped mid-answer" branch (116-126), appends "(The answer above is
incomplete)" to a stream that **never carried an answer**, and returns — the
fixture fallback at 134, the designed behavior for an unreachable tenant, is
unreachable.

**Why it matters** A dead cloud tenant no longer degrades to committed answers
(the design intent, quoted in the comment) — it produces a confusing
half-message. And the incompleteness claim is false, which on the citation
path is a correctness sin.

**Proof [R]** The flag's assignment covers all events; the step event precedes
retrieval in `orchestrator.py:71`.

**Fix** Track *answer text*, not events: set `produced = True` only for
`type == "chunk"`; only claim mid-answer incompleteness when chunks were
actually streamed.

**Verify** Point the provider at an unreachable host with `PROVIDER=cloud`;
ask a fixture question → the committed answer arrives, no "incomplete" note.

---

### COR-2 · HIGH — `wait_ready` treats FAILED as ready

**Where** `cognee_cloud.py:346-349` (`if is_terminal(state): return state`),
`ingest.py:177-197` (prints "Graph ready" then snapshots).

**What** `is_terminal` is true for failure states too. `ingest.py` then
prints `Graph ready: {'…': 'DATASET_PROCESSING_FAILED'}` and proceeds to
`save_graph_fixture`, overwriting a good fixture with the failed/empty graph.

**Why it matters** A transient ingest failure silently corrupts the committed
demo fixture — the artifact every offline demo and the verify battery reads.

**Proof [E]** `is_terminal({'x': 'DATASET_PROCESSING_FAILED'})` → **True**.
**[R]** the ingest call site with no success check.

**Fix** `wait_ready` should distinguish: raise `CogneeCloudError` (or return a
kind) when `terminal_kind(state)` is a failure; `ingest.py` exits non-zero
before touching the fixture.

**Verify** Stub `status()` to return a FAILED state → `wait_ready` raises;
`ingest.py` exits 1 and `fixtures/graph.json` is untouched.

---

### COR-3 · HIGH — the non-race retrieval path is broken

**Where** `orchestrator.py:79-81` — 6 positional args to
`cognee_cloud.recall`, whose signature is
`recall(query, name=None, search_type=GRAPH_COMPLETION, top_k=None,
include_references=True)` — 5 parameters.

**What** With `KESTREL_RACE_RETRIEVAL=0`, every ask raises
`TypeError: recall() takes from 1 to 5 positional arguments but 6 were given`
(the extra pair also contains a dead `smalltalk` conditional — smalltalk
already returned at line 60). The race path (line 88) passes 3 correctly.

**Why it matters** The documented escape hatch for flaky retrieval is a
guaranteed 100% failure; anyone flipping it during an incident makes it worse.

**Proof [R]/[E]** AST count of the `to_thread` call: 6; signature
introspection: 5.

**Fix** `asyncio.to_thread(cognee_cloud.recall, query, dataset, strategy)`.

**Verify** `KESTREL_RACE_RETRIEVAL=0 ./verify.sh` (or one ask) → an answer,
not a TypeError.

---

### COR-4 · MED — a citations failure mislabels a complete answer

**Where** `citations.py:293` (`items_map = _data_items_cached(dataset)` is
unguarded), `orchestrator.py:177-182` (`await refs_task` after `done`),
`memory_layer.py:115-126` (the "connection dropped mid-answer" branch).

**What** After `done` is yielded, the orchestrator awaits the citations task.
If the cognee items lookup fails there (flaky call, dataset reset), the
exception propagates into `memory_layer`'s `except` — with `produced` already
true — and the user's **complete** answer gets "(The connection dropped
mid-answer: … The answer above is incomplete.)" appended and saved that way.

**Why it matters** The failure of an optional enrichment is reported as a
failure of the answer. Users re-ask, distrust correct output, and the history
keeps the false label.

**Proof [R]** The unguarded call, the post-`done` await, and the catch path
compose exactly as above (COR-1's fix must keep this case distinct).

**Fix** Make citations unable to fail the stream: wrap `await refs_task` in
try/except (yield references only on success) and/or guard
`_data_items_cached` inside `enrich`.

**Verify** Stub `enrich` to raise → the answer still completes, no trailer,
`grounded 0 sources` may be skipped silently.

---

### COR-5 · LOW — hardcoded demo dataset name

**Where** `orchestrator.py:163` — `citations.enrich(items, dataset or
"company_brain")`.

**What** Duplicates `DEMO_DATASET` as a literal. Today they match; a rename
silently breaks demo citations.

**Proof [R]** the literal.

**Fix** Import/receive the constant; never re-type it.

---

### COR-6 · MED — smalltalk classifier: misses the real ones, catches content words

**Where** `memory_layer.py:182-201` (`_GREET` / `_SOCIAL` / `_FILLER`).

**What** Live measurement: `"thank you so much"`, `"thanks a lot"`,
`"ok thanks"`, `"awesome, thanks!"`, `"namaste"`, `"hola buenos dias"` all
classify **BRAIN** (they pay the 10–25s retrieval round trip for a pure
pleasantry), while `"all"`, `"team"`, `"doc"`, `"brain"`, `"today"` classify
**SMALLTALK** (real single-word asks skip retrieval entirely).

**Why it matters** Both directions hurt: latency on conversations, wrong
answers (no retrieval) on terse questions — the pattern Indian users type.

**Proof [E]** live run of `_is_smalltalk` over the phrase set above.

**Fix** Match social phrases on word boundaries (regex with `\b`), require the
whole query to be social tokens (length-capped), and never classify a bare
content word — the current substring lists are simultaneously too loose and
too tight.

**Verify** Extend a unit list: the six phrases above → smalltalk; the five
words → brain; plus `"who is on the team?"` → brain.

---

### COR-7 · MED — the router matches a substring, so a negation flips it

**Where** `orchestrator.py:238-241` — `word = reply.strip().upper(); if
"CHAT" in word: return "chat"`.

**What** The decision is a substring test over the whole reply. "This is not a
chat request" contains CHAT → routed to CHAT → retrieval skipped for a real
question. The fallback (RETURN "brain") is safe, but an affirmative-looking
negation is not.

**Why it matters** A router misfire is invisible to the user — the answer
comes from the model's memory, not the brain, and looks plausible.

**Proof [R]** the two lines.

**Fix** Require the reply to *be* the token: `reply.strip().upper().split()[0]
== "CHAT"` (or ask for JSON and parse it).

**Verify** Stub the router reply with "Not a chat — needs retrieval" → route
must be brain.

---

### COR-8 · MED — fingerprint collisions can mis-resolve a citation

**Where** `citations.py:60-62` (`_fingerprint` = first 120 normalized chars),
`117` (write), `181` (read).

**What** Measured in the live `fixtures/uploads.json`: 11 entries, **9 unique
fingerprints** — three entries share one (the same `people-100.csv` uploaded
to two datasets plus `people-100 (1).csv`). A citation resolves
fingerprint→filename through a single-key map; with a collision the chip can
name the wrong file/dataset.

**Why it matters** A citation pointing at the wrong source is a false
citation — the one outcome the product must never produce.

**Proof [E]** fingerprint scan of the live manifest (9 unique / 11 entries).

**Fix** Key by `(dataset, fingerprint)` or store all candidates and
disambiguate by the citing dataset; have `record_upload` flag collisions when
writing.

**Verify** Collide two files deliberately; the citation for dataset B resolves
to B's filename.

---

### COR-9 · MED — encrypted PDFs 500 the upload

**Where** `documents.py:103` — `for number, page in enumerate(reader.pages…)`
runs **outside** `_from_pdf`'s try; `196-209` (`extract_many` catches only
`ExtractError`); `app.py:673`.

**What** `pypdf.errors.FileNotDecryptedError` escapes `extract_many` and the
route returns 500 with a stack trace instead of a clear rejection.

**Why it matters** Password-protected PDFs are common in Indian services
firms (bank/HR documents); a 500 on one file aborts the whole upload batch
with an unhelpful error.

**Proof [E]** Built an encrypted PDF, called extraction →
`FileNotDecryptedError` propagated.

**Fix** Catch `pypdf` errors in `extract_many` and re-raise as `ExtractError`
("password-protected PDF — remove the password and retry"); surface per-file
failure like other extract errors.

**Verify** `test_documents.py` gains the encrypted case → clean per-file
failure, batch continues.

---

### COR-10 · MED — mock references are bare strings; the UI expects objects

**Where** `memory_layer.py:168-173` (yields `entry["references"]` verbatim);
`fixtures/answers.json` (entries are plain strings, e.g.
`"chunk 1 of 05_policy_SLA-credit-01.md — …"`); the UI contract is the
enriched `{source, excerpt, …}` shape produced by `citations.enrich`.

**What** In mock/offline mode (the verify battery, offline demos) the
references event carries strings. The client's `SOURCES` filter
(`i && i.source`) drops them all and `renderSources` has nothing actionable —
so the demo brain, the thing a prospect sees first offline, shows no usable
citations.

**Why it matters** Two shapes for one contract; the offline story is the
fallback when the cloud is down, and that is exactly when chips vanish.

**Proof [R]** fixture shape + passthrough + the client's object-shaped filter.
Mock mode is the only path where references bypass `enrich`.

**Fix** Shape mock references through the same formatter (or make the client
tolerate strings).

**Verify** `PROVIDER=mock` ask → source chips render and open.

---

### COR-11 · MED — the summarizer blocks the event loop

**Where** `summarizer.py:26-51` — `async def summarize_history` calling
`requests.post(..., timeout=90)` directly (line 32).

**What** A 90-second blocking call inside an async handler freezes every
concurrent request — `/health`, asks, everything — for the duration.

**Why it matters** The summarizer runs on chat save; a slow provider stalls
the whole server, not just the caller.

**Proof [R]** the call site; the pattern elsewhere in the codebase correctly
uses `asyncio.to_thread`.

**Fix** `await asyncio.to_thread(requests.post, …)` (or an httpx async client).

**Verify** Slow-stub the endpoint; concurrent `/health` stays responsive.

---

### COR-12 · LOW — i18n applies before the DOM exists; duplicate key

**Where** `static/ui.js:583` (`apply()` runs while the script is still in
`<head>`); `58` and `83` define `'up.sub'` twice in every locale (58/83,
140/165, …).

**What** The first `apply()` can find no nodes (document.body null / elements
not parsed); the duplicate key means one catalog string is unreachable.

**Proof [R]** the call site and the repeated key.

**Fix** Run the initial `apply()` on `DOMContentLoaded`; delete the shadowed
duplicate.

**Verify** Load with a non-English locale → all strings render; no missing-key
fallbacks.

---

### COR-13 · LOW — light theme keeps dark-theme colors in three places

**Where** `index.html:34` (`.watermark` = `rgba(255,255,255,.045)` — invisible
on the light background), `shell.css:184` (nav hover hardcodes dark values),
`graph.html:22-31` (panel + legend `rgba(30,30,30,.92)` — a dark card on the
light theme).

**Why it matters** Cosmetic, but the light theme is what the Clerk gate and
account surfaces were explicitly themed for — these three read as unfinished
next to them.

**Proof [R]** the hardcoded values; theme variables exist (`--wash`, lines
26-28 dark / 78-80 light).

**Fix** Use the theme variables; no literal rgba in those rules.

---

### COR-14 · LOW — `esc()` strips characters instead of escaping

**Where** `static/shell.js:122` — `.replace(/[<>&"]/g, '')`.

**What** "R&D" renders as "RD"; "a < b" loses the operator. Safe but wrong
(the C2-era fix chose deletion over encoding).

**Proof [R]** the one-liner.

**Fix** Escape to entities (`&amp;` etc.) or build with `textContent`.

---

### COR-15 · MED — an error mid-answer discards the partial answer

**Where** `static/index.html:1234-1236` (server `stage:error` — no `finalized`
guard) and `1285-1288` (transport error — no `text` check); server side
`app.py:485-487` emits `stage:error` then `done` on any exception.

**What** Two shapes, same loss: (a) an error event arriving **after** the
answer was finalized (e.g. COR-4's post-done citations failure) replaces the
completed bubble with "Something went wrong" — the answer is wiped from
screen while a reload would restore it; (b) a transport failure after partial
text replaces the bubble with "Could not reach the server" and the partial
answer is never pushed to TURNS. The AbortError path a few lines up
(1265-1280) does exactly the right thing — keep the partial, label it, save
it — proving the intended behavior.

**Why it matters** Losing a long answer to a blip is the worst apparent-outage
experience; (a) additionally contradicts the persistence layers.

**Proof [R]** both branches; contrast the AbortError branch.

**Fix** Guard: ignore `stage:error` when `finalized`; in the catch, if `text`
exists, keep-and-label like the AbortError path.

**Verify** Stub a stream that errors after `done` → the answer stays on
screen. Kill the connection mid-answer → partial text stays, labeled.

---

## Low / hardening (compact)

- **LOW-1** `warmup.py` / `battery.py` hit the API without tokens → unusable
  against `AUTH_MODE=clerk` (verify.sh sidesteps by forcing `AUTH_MODE=off`).
  Give them a service token or document the constraint.
- **LOW-2** `index.html:1164` — `stepTick` `setInterval` never cleared; one
  ticker leaks per ask.
- **LOW-3** `index.html:1574` — `.bar-menu-row` exists nowhere in the repo
  (grep: one occurrence); `appendChild` on null throws inside the setTimeout,
  so the "PDF blocked" notice can never show.
- **LOW-4** `storage.py:243-256` + `app.py:421-423` — `/api/usage` returns
  platform-wide totals to every tenant; scope it by org/brain or say "all".
- **LOW-5** `app.py:328` — `/health` exposes the Cognee service URL and DB
  host unauthenticated; trim to status booleans.
- **LOW-6** `app.py:383-391` — malformed JSON body raises → 500; wrap
  `request.json()` and 400.
- **LOW-7** `auth.py:99-103` — `algorithms=[headers.get("alg", "RS256")]`
  takes the algorithm from the token header, and `options={"verify_aud":
  False}` without `require: ["exp"]`. Pin `["RS256"]`; require `exp`.
- **LOW-8** `snapshot.py` — a failed read can be written back as an empty
  `index.json`; write to a temp file and replace only on success.
- **LOW-9** `citations.py:105-129` — `record_upload` is a read-modify-write
  without the file lock held across both; also last-write-wins on fingerprint
  collision (feeds COR-8).
- **LOW-10** `app.py:539` — `GET /api/brains` lists every brain with no auth
  (measured live: 200 unauthenticated). Previously noted; still open.
- **LOW-11** `app.py:403-405` — `GET /api/chats/{id}` checks identity but not
  ownership; any signed-in user reads any chat by id. Same fix family as
  SEC-4/SEC-5. Previously noted; still open.

---

## Cross-reference: previously known / out of scope

- **BUGS.md M4 (TOCTOU on brain creation)** — still the one deliberately-open
  item from that pass; SEC-9 is adjacent (the ownership row makes the race
  worse, not better). Fix together.
- **BUGS.md "What is genuinely solid"** still holds — `/api/source` path
  safety, upload caps, `renderDetail` escaping, two-layer reserved-name guard.
  This audit found the *siblings* of those defenses missing (SEC-1, SEC-6,
  FE-9), not holes in the defenses themselves.
- **Hygiene contradiction:** `compose.oss.yml` is committed despite invariant
  N3 ("no secrets committed"). It carries config, not keys, today — but the
  invariant says the file should be gitignored with a `.example`. Decide and
  align, before P4 makes it public-facing.
- **Test gaps that let these ship:** `test_auth_isolation.py` injects JWKS
  (so `_fetch_jwks`'s TTL bug is invisible, SEC-7) and calls `brain_allowed`
  directly (so no route-level authz, SEC-1/SEC-3/SEC-6 slipped through). The
  P3 hardening items deferred to P4 should include: route-level authz tests
  per branch, a JWKS-rotation test, and a traversal test on `/api/graph`.

---

## Systemic patterns (fix the cause, not just the instance)

1. **Fail-open defaults.** `brain_allowed` (no row = allow), `brain_access`
   (error = None), `_load_graph` (unsanitized path = serve it),
   `wait_ready` (FAILED = ready), `produced` (any event = produced). Five
   places where "unclear" resolves to "continue". Each produced a bug in this
   list; each fix is to make "unclear" stop the flow.
2. **The frontend never adapted to auth.** Ten fetch sites with no headers
   plus a boot-race helper. One `apiFetch()` helper (authHeaders + JSON +
   error surfacing) replacing raw `fetch` on API paths kills the whole tier.
3. **The post-`done` citations path assumes it cannot fail.** Nothing enforces
   that (COR-4, COR-15a, FE-8 all live there). Cite resolution should be
   structurally unable to affect the answer stream — then the UI ordering
   problem is the only thing left.
4. **Names normalized in some places, not others.** `normalize_brain_name`
   is applied at 3 of 4 boundaries; the missing one is authz-before-delete
   (SEC-1). Normalize at the edge, once, before anything reads the name.

---

## Recommended fix order

Ordered by risk removed per hour, not by severity alone.

1. **SEC-1, SEC-3, SEC-6, SEC-7** — surgical, testable today (each S-sized):
   the exploit, the open stream, the traversal, the rotation outage.
2. **SEC-2 + SEC-8 + SEC-9** — the authorization rule itself; one function,
   one migration-free change, plus route-level tests.
3. **FE-1, then FE-2…FE-7** — the boot race first (one line), then the
   mechanical header fixes; FE-7 is independent and user-visible (S).
4. **FE-8 + COR-4 + COR-15** — the citations/error cluster on the cardinal
   path; do them together so the persistence and the label are consistent.
5. **SEC-4 + SEC-5 + LOW-11 + LOW-10** — chat ownership stamping and the two
   known-open read routes; needs the backfill decision.
6. **COR-1, COR-2, COR-3, COR-9** — one-liners with clear reproductions.
7. **COR-6, COR-7, COR-8, COR-10** — retrieval quality; COR-8 pairs with
   LOW-9.
8. **COR-11…COR-15, SEC-10, LOW-1…LOW-9** — batch as cleanup.

After every fix: `./verify.sh` must stay green (battery runs with
`AUTH_MODE=off`), **and** re-run the live Clerk-mode checks added for SEC-1,
SEC-3, FE-1, FE-7 — the battery does not exercise Clerk mode, which is how
Tier 2 shipped.

---

# ROUND 2 — the live queue (opened 2026-10-04)

## STATUS — Round 2 CLOSED (same day), audit tail excepted

Every CH item below is fixed in this tree and the fix was **verified by
execution**, not by reading:

- **`tests/test_chat_integrity.py`** — 19 checks, wired into `verify.sh` as
  `[chat-integrity]` (it writes rows, so it runs only against the lab DB and
  removes everything it creates). Covers CH-1, CH-2, CH-3, CH-5, CH-6, CH-7,
  CH-8, CH-9.
- **A real-browser probe** at 1440x900 and at 390x844 with touch emulation: the
  anchor now starts at the row's left edge (`gap=0`), every sampled offset
  hit-tests to `a.chat-link`, the hidden delete button reports
  `pointer-events: none` on a hover device and is visible *and* tappable at
  opacity .45 on a touch device (CH-4) — and the owner's two symptoms pass
  end-to-end: opening a chat from the Brains view survives a reload, and a
  deleted chat does not come back.
- **`./verify.sh` with `KESTREL_CLERK_GATE=1` on the lab database**: documents
  25/25, pipe-states 13/13, connectors 90/90, tenants 10/10, smoke 4/4,
  frontend-transport, frontend-css, **chat-integrity**, ui-react (four new
  gates), **clerk-gate** — 0 failing suites.
- Migrations: `0005_chat_tombstones` applied to lab and live (each preceded by a
  `pg_dump` in `/tmp`); live is at `0005_chat_tombstones`, 7 chats intact.

**CH-13 — found by this pass and fixed.** `openChat` wrote `?chat=` without
clearing `?view=`, so opening a chat from another view left the URL
self-contradictory: the conversation loaded while the screen stayed on Brains,
and only a reload proved it. This is the defect the dead client audit had
reproduced and never reported. Locked by two acceptance gates ("the stale view
param is cleared", "the jump survives a reload").

**CH-11 audit tail — closed.** The dead audit's unfinished surface (light/dark
parity, mid-stream brain switching) was covered by this pass:

- **Theme parity** measured in the page at 1440 and 390, in both themes, by
  computing real rendered contrast: every checked surface clears WCAG AA, worst
  case 5.84:1 (sidebar nav), most above 11:1, with no page errors in either
  theme.
- **Mid-stream switching** turned up CH-14, and is now gated in the acceptance
  suite (two brains required; skipped with a printed note when the fixture set
  has one).

What remains unaudited is cosmetic rather than behavioural: the connectors shelf
and the settings menu have never been walked in both themes at both widths.

**One fix needed a second attempt, recorded because the first looked correct:**
CH-12's gate read `authMode !== "clerk" || signedIn`, but `authMode` starts as
`"unknown"` until `/api/config` resolves — so the prefetch still fired on every
signed-out load. The corrected rule treats unknown as "wait". Verified by
network evidence on the live Clerk-mode server: the only backend request on a
signed-out load is `/api/config`, and the console holds nothing but Clerk's own
development-mode warning.

Fixing it broke `tests/test_react_clerk.py`, and on inspection the test was the
one that had been wrong — its single "control" run conflated two different
states:

- **a session that cannot mint a token** → the app must still ask, take the 401
  and quote the server's own words, or an unreadable history reads as an empty
  one.
- **no session at all** → asking is a bug, not a fallback. Nothing should be
  requested but `/api/config`, and because the panel is no longer populated by a
  401 it must not claim "No saved chats yet" either: a signed-out sidebar now
  says **"Sign in to see your chats"**, which is the truth — nothing has been
  looked at.

The gate runs all three profiles now (token / noToken / signedOut) and all three
pass, so the distinction is locked rather than re-litigated.

---

Chat subsystem + React shell. Provenance: the previous session was cut off at
00:18 IST by a provider quota error while fixing exactly this area. It left two
audits behind — a server-side chat/storage audit (15 findings, delivered but
never triaged) and a **client-side audit that died mid-run** (it had already
reproduced a dead click-zone before it stopped). Both were re-verified against
the current tree (uncommitted work included) at 00:30, because the workspace was
being edited *during* those audits, so their line numbers were stale.

Verification levels below: **[R]** re-read in the current tree by me ·
**[P]** reproduced by that session against the lab DB (`:5434`) or its
TestClient on `:8020` · **[B]** reproduced in a real browser on `:8020`.

| ID | Sev | Bug | Where | Proof |
|---|---|---|---|---|
| CH-1 | CRITICAL | 60-turn save window + wholesale turn replace = silent, permanent history loss | `App.tsx:694` + `storage.py:244` | [R][P] |
| CH-2 | HIGH | A deleted chat resurrects — no tombstone, and POST with a previously-deleted id recreates the row | `storage.py:226-233` | [P] |
| CH-3 | HIGH | `DELETE` answers 200 `{"ok": false}` for a no-op delete while its own comment claims 404 | `app.py` `chats_delete` | [R] |
| CH-4 | HIGH | Sidebar chat rows have a dead click-zone; the invisible delete button is hit-testable | `legacy/deck.css:242-251`, `Sidebar.tsx:198-210` | [B] |
| CH-5 | MEDIUM | `at` round-trip corruption — re-saving a restored chat restamps **every** old turn with `now()` | `storage.py:431-439`, `:250`, `lib/api.ts:191` | [P] |
| CH-6 | MEDIUM | `POST /api/chats` never calls `require_dataset_access` — a chat can be filed under any brain | `app.py:618-646` | [R] |
| CH-7 | MEDIUM | `total` promised but absent, no `OFFSET`, no `updated` tiebreaker; the client asks for 500 and ignores both fields | `app.py:660-663`, `storage.py:287`, `lib/api.ts:148` | [R] |
| CH-8 | MEDIUM | Mid-life storage outage is undetected (`available()` sticky-true); raw psycopg errors escape as 500 where routes promise 503; `get_chat` reads chat + turns as two autocommit statements (torn read) | `storage.py:53-68`, `:309-322` | [P] |
| CH-9 | LOW | Only `text` is size-capped — `steps`/`sources`/`attachments` unbounded; `int(t["workedMs"])` on `"abc"` → 500 | `app.py:640`, `storage.py:261` | [P] |
| CH-10 | LOW | Schema authority split: `init()` DDL duplicates 0004 verbatim, `0001_baseline` is a no-op, live DB still at `0003`; `chats.brain_id` is never created by `init()` so `ops/backfill.py` breaks on a bootstrap DB | `storage.py:80-116`, `0004:28-31`, `0002:308-311` | [R] |
| CH-11 | OPEN TASK | The client-side bug hunt was never finished — its audit agent died mid-run. The React shell has had no complete defect pass. | — | — |
| CH-12 | LOW | Signed-out visitors throw two console errors: the app prefetches `/api/chats?limit=500` and `/api/brains` before anyone is signed in, and both correctly 401. The authorization is right — the fetch should simply not happen when there is no session. | `lib/api.ts:148`, `useBrains` call site | [B] |
| CH-13 | HIGH | `openChat` set `?chat=` without clearing `?view=`: opening a chat from another view left the URL contradictory, so a reload landed back on Brains with the conversation loaded but invisible. Found and fixed by this pass. | `App.tsx` `openChat` | [B] |
| CH-14 | HIGH | Switching brain mid-stream neither aborted the ask nor cleared the thread: brain A's conversation stayed on screen under brain B, and the next save filed it into B. The switcher's own confirm text promised "this starts a fresh chat" — the code did not. Now aborts, blanks the thread (state AND the ref, so the aborted ask's save cannot resurrect it) and drops the stale `?chat=`. | `App.tsx` `handleBrainChange` | [B] |

## The owner's two reported symptoms, mapped

1. *"When I am not in the new chat section … I can't click and directly jump to
   the chat history."* → **CH-4** (browser-reproduced: the row's left 34 px is
   `div.nav-item`, not the anchor, so clicking there does nothing while the row
   still shows `cursor:pointer`; at the right edge the `opacity:0` delete button
   is hit-testable, so a mobile tap **arms delete** instead of opening). The
   stale-`?view=` half of it looks addressed in the in-flight work
   (`App.tsx:901` deletes `view` on the chat route) — **must be re-tested in the
   browser, not assumed**.
2. *"Even after I delete the chat history, there is still somehow it always
   stays."* → **CH-3 + CH-2** together: a delete that matched no row still
   toasts success (HTTP 200), and any later save of that still-open conversation
   re-inserts the chat with its turn window — so the chat returns.

## Fix order (Round 2)

Executed 2026-10-04 in this order; see the STATUS block above for what verifies
each item. Step 0's "open acceptance FAIL" was itself a bug in the assertion, not
in the app (the gate compared the whole `into <brain>` label against a row).

0. **Commit the in-flight work first** — 11 files of turn-7 fixes are uncommitted
   and fragile; the turn-detail columns (`steps`/`worked_ms`/`stopped`/`error`)
   and the `chats_get` 404 contract belong to CH-5's neighborhood. Triage the one
   open acceptance FAIL (`check_ui_react.py:447` "sheet targets the row's brain")
   and get `./verify.sh` green before layering more change on top.
1. **CH-1 + CH-2 + CH-3** as one change — the silent-loss + lie pair. Reject a
   save whose turn count is lower than what is stored unless the client declares
   a trim; tombstone deleted ids (or have `delete_chat` stamp a marker
   `upsert_chat` refuses to overwrite); make `DELETE` 404 on zero rows and read
   `d.ok` at all three client call sites.
2. **CH-4** — row-level click handler or padding on `.chat-link`, plus keeping
   the un-armed `.row-del` out of the hit test. Verify in a browser at 390 px.
3. **CH-6** — one missing line, and it is the only write route that skips the
   authorization every other write route has.
4. **CH-5** — teach `_ts` ISO strings (`datetime.fromisoformat`) so restored
   turns keep their real times.
5. **CH-7 → CH-10** as a batch; **CH-11** (finish the client audit) before any
   further UI work is called done.

