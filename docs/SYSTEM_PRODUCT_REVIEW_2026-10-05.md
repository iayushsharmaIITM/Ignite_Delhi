# Kestrel — complete system and product review

Generated 2026-10-05. This is the single consolidated view: what the platform is for,
what it measurably does today, every open defect from this session's reviews, the
product-design audit, and the decisions that are the owner's rather than the
engineer's. It supersedes reading four documents in sequence; the source documents are
linked at the end and remain authoritative for their own detail.

It is written to be handed to a reviewer. Where a claim is measured, the number and
its location are given. Where something is design-not-code, it says so. Nothing here is
an overall score, and no section should be read as one.

---

## 1 · The goal

A **company brain whose citations you can trust and whose permissions it respects**.
You upload the documents your company runs on — contracts, tickets, meeting notes,
policies — and it answers by retrieving from that material and naming the file every
part of the answer came from. When it does not know, it says so.

That is the invariant the whole repository exists to protect:

> **No fabricated citations. No semantic caching on the citation path. A storage
> outage surfaces as 503, never as an empty list.**

The strategic bet (`docs/CATEGORY_SCAN_2026.md`): the established players win on
connector breadth — Onyx 40+, Glean 100+, against our two — and that is a fight worth
declining. The defensible position is **answers whose provenance and permissions
survive contact with reality**, which nobody in that market does well and which is the
prerequisite for running an agent over your own documents at all.

The engineering constraint that shapes everything: **one managed port**. `:8000` serves
the UI, the API, the answers and the graph from a single Python tier, one worker,
restartable. Every significant breakage this session traced back to two surfaces
disagreeing, not to a missing feature.

## 2 · Current state, measured

| | |
|---|---|
| Auth | Clerk-only. `AUTH_MODE` defaults to `clerk`; an unrecognised value refuses to boot. Live `/health` → `ok:true, provider:cloud, auth:ok, upstream:ready` |
| Verification | `verify.sh` — 18 tiers (documents, pipeline states, connectors, tenants, smoke, two frontend static gates, phatic, doc-health, chat integrity, brain-claim, auth isolation, route authz, v2 authz, lifecycle identity, lease recovery, browser acceptance, opt-in Clerk gate). Last full run: **ran 17, skipped 1, failing 0**, browser suite clean, zero console errors. **Amended the same day, Round 9:** six more lanes landed on the still-unmerged `fix/bughunt-2026-10` — `source-precedence`, `citation-collisions`, `durable-identity`, `storage-outage`, `rebuild-fence`, and `legacy-visibility` (a characterisation lane, not a security gate). Full run on that branch: **ran 23, skipped 1, failing 0**. The tier list above is where they belong; the count is what the battery prints, so it is no longer repeated in a document |
| CI | Two jobs, green on the hosted runner. Builds and enforces that the committed bundle matches `frontend/src`, that every asset `index.html` names exists, and runs the invariant suites against its own migrated Postgres |
| UI | React only. The legacy UI is fully deleted — last hand-written page (`static/graph.html`) ported to React with 16 browser gates proving force layout, camera, disclosure and the inspector before it was removed. `/graph`, `/brains`, `/upload` are 307 redirects; `/static` is not mounted |
| Engine | Greetings/thanks/capability questions answered from a 6-locale template with **zero model calls and zero retrieval**; a retrieval that returns nothing now says so with no references rather than raising an outage and answering from fixtures |
| Footprint | `frontend/dist` 1.0 MB; `app.py` 2,377 lines; `App.tsx` 2,024; 16 declared Python deps; no heavy scientific libraries imported at runtime |
| API quality | 59.7 % agent-ready across 48 checks (429 rate-limit headers, machine-readable error `code`, and 0/39 success schemas are the gap) |
| Harness review scores | task-understanding 70 · controlled-execution 62 · change-validation 66 · **reliable-delivery 52** · **learning-capture 45** |

## 3 · Defects found and fixed this session

Not history for its own sake: each one is the class the harness is meant to make
impossible, and each has a gate now.

**Engine.** Greetings paid 11–25 s of retrieval because the browser's local-time note
was prepended *before* the classifier ran — and the same note was then *discarded*
(`q` reassigned, never read again; proven by AST), so "what time is it?" got the
server's clock labelled "local time". **Cross-tenant `cancel`**: `POST /api/jobs/{id}/cancel`
had no ownership check while the GET on the same resource did. **Fabricated citations
by fallback**: an empty-but-successful retrieval was recorded as a failure and fell
through to fixtures carrying hand-written citation chips naming real contract files.
**An outage rendered as "no model calls recorded yet."** **`/api/extract`** read
unbounded uploads into memory after `_read_capped` existed for exactly that.
**JWKS** discarded valid cached keys past TTL, re-fetched on every request, and blocked
the event loop from `async def` handlers — 401-ing every user at once. **Cancelled asks
never metered** (`GeneratorExit` skipped bookkeeping while the tokens were spent).
The general-chat branch **orphaned the citations prewarmer**; the rate-bucket map grew
without bound; and the phatic path would have been metered as if it cost inference.

**UI.** "New chat" from any other section did nothing (the same defect already fixed in
its sibling `openChat`, never looked for sideways). "Add documents" on a brain row
**re-filed the conversation you were reading into the other brain**. "New chat" and
"Clear conversation" did not abort the in-flight answer, so the abandoned stream wrote
into the new thread and then **saved the mixture**. A destructive confirm armed and
**never disarmed**, leaving a row one click from deleting up to 500 chats. The
stale-bundle guard went **permanently blind on a tab opened in the background**. A sheet
reported **success** on a refused progress stream. Double-clicking Send emailed twice.
A per-keystroke blob leak, a full-bleed panel, and two translation keys that were
typos silently discarding existing translations.

**Harness itself.** Three verification mechanisms could not fail: the fresh-bootstrap
script that AGENTS.md names as the proof for every schema change echoed a count under
"a expect 11" and printed PASS unconditionally; a lease-recovery tier printed PASS on
two of four paths with no assertion; and `verify.sh` exited 0 with half its tiers
skipped. The doc-freshness gate could not see a document routing to a deleted file —
the class it was written for — and README was advertising `python3 check_ui.py` at
**16/16 PASS** for a file deleted that morning. An authorization suite sat in the tree
invoked by nothing while a report counted it as coverage.

## 4 · Open defects — the queue

Ranked by what can hurt a user or the product's claim, not by effort.

**Under the invariant**
1. **The citation collision table is written and never read** (`citations.py:116-137`).
   Two documents sharing a 120-char prefix cite the wrong file and `/api/source` hands
   back the other document's text as evidence. Measured 0 collision groups today —
   latent, and the only remaining hole under the headline claim.
2. **Rebuild can never publish** (`lifecycle.py:438`): the fence requires
   `brains.state == 'CREATING'` while a rebuild targets a `READY` brain, so the ops
   script burns a full ingest and ends `FAILED`. An undeliverable feature is worse than
   an absent one.
3. **`_offline_brains()` turns an unreadable snapshot manifest into `[]`**, which the
   tier then narrates as "no snapshots found, run snapshot.py" — same error-as-empty
   shape, offline branch only.

**Reach and trust**
4. **Two connectors** against a category norm of 40–100+. Ranked candidates in the
   category scan; each must arrive with a per-connector contract suite (scope, refresh,
   revoke, failure-as-503) **and** an honest capability matrix in `/api/config`, so an
   unsupported source can never answer as though it were indexed.
5. **No Drive ingest**: the OAuth scope is requested and no code calls the API.
6. **Permission-aware citations — design, not code** (`docs/ACL_AND_MCP_BLUEPRINT.md`).
   Two enumeration oracles are live now: distinct 403 wording distinguishes "unknown"
   from "not yours", and `GET /api/brains` returns every dataset with no access filter.
   Phase 1A closes both, and nothing else in that design should ship first.
7. **No evals.** "Trust the citation" is currently defended by gates around fabrication,
   not by a measured groundedness score. The missing number is
   **hallucinated-source count = 0** on a golden question→source set.
8. **API contract**: no machine-readable error `code`; 0 of 39 success schemas. Clients
   retry by parsing English.

**Product surface (design audit — 16 findings, 12 major, 4 minor)**
9. **Three primary controls are mouse-only**, and one is dead for mouse users too
   (`window.open` on a `data:` URL is blocked). A correct keyboard implementation
   already exists in the tree, unused (`Animations.tsx:247-257`).
10. **Modals announce `aria-modal` without moving or restoring focus**; the files sheet
    has no dialog semantics and ignores Escape.
11. **Localisation drift**: five components render chrome without `t()`, 34 of 43 toasts
    are raw English, and 17 keys exist in no locale — while the six locales are
    otherwise exactly 154/154 identical, which is what makes the drift invisible.
12. **Developer affordances visible to users**: the Brains page renders a `/health` link
    and a "demo dashboard" link beside real user actions, and duplicates "New brain".
13. **No onboarding and no inline help anywhere**; the only guidance is four suggestion
    chips that exist for the demo brain alone, and "what can you do" is now a fixed
    template. A new user with their own brain sees an empty chat and no indication of
    what is indexed there.
14. **Weight paid whether or not a feature is used**: per-ask citation prewarm fan-out
    (8-worker `data_raw` dump), a 600-second event long-poll on a one-worker tier, and a
    1.0 MB bundle that ships the canvas graph renderer to the chat screen.
15. **Touch-target density** unresolved on mobile; a deleted single conversation has no
    undo; the create-brain dialog can stick on "Working…" with an uncancellable poll;
    the restore overlay is announced visually only.

## 5 · The design opportunities those findings cluster into

1. **Make every failure state honest and reachable** — high. The product is candid
   about answers and vague about its own state; for a trust product that is a defect,
   not polish.
2. **One voice across six locales, enforced by a gate** — high. The gate must land
   *before* the sweep, or the sweep regresses the way it already did.
3. **Keyboard parity on every primary surface** — high. Reachable-by-keyboard is a
   procurement question for enterprise buyers, and the correct component already exists.
4. **Make the first sixty seconds work for a new brain** — high. No onboarding +
   demo-only prompts + developer links compound into the weakest screen in the product.
5. **Pay only for what a request needs** — medium. Items 14's three costs are the same
   defect: work done regardless of whether the feature is used.
6. **Let the user take back a mistake** — low. Bulk delete is armed and expires now;
   single-chat deletion is still irreversible.

## 6 · Standing decisions, and what must not be traded away

**Owner's, not the harness's:** push the local commits; restart live `:8000` so this
session's engine fixes land (it twice ran old routes against a new bundle — a live
change and its restart must ship together); branch protection with the battery as a
required check; an off-disk second copy of backups; rotation of two Bedrock API keys and
one `AKIA` id sitting across seven gitignored files that CI's tracked-file scan is
structurally blind to, plus whether the copy that entered ingested document content
needs a re-ingest to purge; which connector next and for which segment; whether evals
run per-commit on the paid provider or nightly; whether external agents may hold
credentials at all; and the lightness/reliability backlog order.

**Not tradeable, whatever gets built next:** one managed port. No new dependencies
without an explicit yes. The citation invariant, and its two corollaries — 503 not an
empty list, refusal withheld rather than citation-hidden. Deletion, re-ingest,
force-push, history rewrite and key rotation are owner-only every time. A storage
outage must stay a 503. **One worker is a design choice, and the correctness of the
process-local caches and rate buckets depends on it** — if that ever changes, they move
to Postgres first. And a feature is not shipped until something proves it can fail.

## Sources

`docs/BUG_HUNT_2026-10-05.md` (26 findings, evidence + repro per finding) ·
`BUGS_AUDIT.md` Rounds 5–8 (A-28…A-73) ·
`docs/HARNESS_BLUEPRINT_2026.md` (five-dimension plan + feature→gate matrix) ·
`docs/ACL_AND_MCP_BLUEPRINT.md` (permission model + MCP, unbuilt) ·
`docs/CATEGORY_SCAN_2026.md` (2026 bar, connector landscape, thesis) ·
`spark-output/context/audit.json` (16 design findings, 6 opportunities) ·
`.qoder/better-harness-runs/2026-10-04-postci/` (harness review, 10 findings) ·
`docs/INDEX.md` (which of these is living, historical, or commercial)
