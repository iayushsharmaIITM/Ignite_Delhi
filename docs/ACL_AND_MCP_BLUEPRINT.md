# Permission-aware citations and an agent-facing read surface — build plan

Status: **design, not built.** Nothing in this file is implemented. Written
2026-10-04 after the code-architect pass; every claim below about the *current*
state was re-read from the tree and carries a `file:line`.

Why this and not another connector: `docs/CATEGORY_SCAN_2026.md` scores the 2026
bar for company-brain products and concludes the only defensible differentiator
is **citations that respect the source system's own permissions**. Onyx, Glean and
the rest retrieve first and filter the *display* afterwards. A product whose answer
text leaks a document the asker cannot open has no enterprise story. Kestrel's
retrieval path is small enough to do the honest thing — refuse before any chunk
streams — which is also the only behaviour consistent with the standing product
invariant (no fabricated citations, no semantic caching on the citation path).

## What exists today (verified)

* `brain_access` is the **only** access-control table the app reads
  (`storage.py:166`, consumed at `app.py:416`). It is brain-level: one row per
  brain, PK is the brain **name text**, columns `org_id`, `created_by`,
  `is_shared`, `status`, `claimed_at`.
* `brain_grants` is **dead**. It is created only by
  `migrations/versions/0002_identity_provenance_jobs.py:113` and dropped at `:329`;
  `storage.init()` does not create it, and no line of application code selects
  from it. Any design that assumes it exists is wrong on a fresh boot.
* The other 0002 control-plane tables (`brains`, `documents`, …) carry **zero
  rows** on every volume — they were never populated by the ingest path. So a
  policy keyed on `documents.id` has nothing to key against. The design below
  therefore keys on `(brain name, document filename)`, which is what the storage
  layer actually holds and what citations already render.
* There is **no Drive ingest**. `connectors.py:52` requests the
  `drive.readonly` OAuth scope, and nothing anywhere calls the Drive API. Google
  authorisation exists; document identity from it does not.
* Two **enumeration oracles** are live right now, and they are the reason Phase 1A
  ships before any feature that reads document-level policy:
  1. `app.py:418` answers `403 "Unknown brain."` for a brain with no access row
     but `app.py:426` answers `403 "This brain belongs to another workspace."`
     for one that has a row belonging to someone else. The difference in wording
     tells an unauthenticated prober which names are real.
  2. `GET /api/brains` (`app.py:1702`, body at `:1726-1739`) returns **every**
     dataset name from `cognee_cloud.datasets()` with no `brain_access` filter,
     after passing only `require_tenant`. Any signed-in caller of any workspace
     reads the whole fleet's brain inventory.
  Neither is exploitable to *read content* today — `require_dataset_access`
  gates the content routes — but both leak the namespace, and a document-level
  ACL layered on top of a leaking namespace buys nothing.

## Feature 1 — document-level policy

**Model.** An allow-list of principals per document, with a tri-state visibility
that decides what a *non*-allowed caller is even told exists:

| visibility | caller not on the allow-list learns |
|---|---|
| `ORG` | the document exists and is in their workspace; answer proceeds |
| `LIST` | the document exists, title only, no content |
| `OWNER` | nothing — the document is absent from every listing and never named |

**Tables** (four, all idempotent DDL per `AGENTS.md`, both authorities —
`storage.init()` *and* a new migration — because a deploy may boot or migrate
first):

* `document_policies` — keyed `(brain, doc_name)`, holds `visibility`,
  `owner_principal`, `source_system`, `source_doc_id`, `synced_at`.
* `document_policy_principals` — the allow-list rows, `(brain, doc_name,
  principal_type, principal_id)`; `principal_type` in (`org`, `user`, `group`).
* `identity_links` — maps a connector identity (Google sub, Slack user id) to a
  Clerk `user_id`, so a principal arriving over MCP resolves to the same person
  arriving over the web UI.
* `acl_sync_runs` — one row per connector sync: watermark, counts, result. The
  table that lets us say *how stale* a policy is rather than pretending it is
  current.

**Code home.** A new `document_acl.py`, one entry point — resolve the caller to a
principal set, then ask whether an answer may be emitted. Routes stay thin.

**Enforcement point.** Before any chunk streams, in the answer path — not at
citation-render time. If any retrieved span is above the caller's clearance, the
request is **refused as a whole** and the response says a policy blocked it.
Filtering the citation list while still emitting the answer text is concealment:
the leaked content is the answer, not the footer. This is the decision that makes
the feature defensible, and it is the one that costs the most UX polish.

**Phases.**

* **1A** — close both oracles. Uniform `403` wording; `GET /api/brains` filtered
  through `brain_access`. No schema change. *Nothing downstream ships until this
  is green.*
* **1B** — the four tables, dual-authored, proven with
  `ops/test_fresh_bootstrap.sh` (and that script must actually assert — see
  `BUGS_AUDIT.md` Round 5; as written it cannot fail).
* **1C** — `document_acl.py` + enforcement in the answer path, with a gate that
  proves refusal, written as a test that fails before the code exists.
* **1D** — policy UI: per-document visibility, allow-list editor, staleness from
  `acl_sync_runs`.
* **1E** — Drive ingest: real read, real per-file ACL harvest, so
  `source_doc_id`/`source_system` stop being decorative.
* **1F** — Gmail and Slack message-level policy, which is where the owner
  question below bites.
* **1G** — group principals, i.e. `identity_links` earning its existence.

## Feature 2 — the MCP read surface

`POST /api/mcp`, **in-process** on the same app tier and the **same single port**
as everything else — no second service, no sidecar. Hand-rolled JSON-RPC over the
existing FastAPI route so no new dependency is added (standing rule: no new deps
without the owner). Five read-only tools, all of which route through the same
`document_acl` entry point as the web UI — one enforcement seam, not two.
`tools/list` returns **byte-identical** output for every caller, so the surface
itself cannot disclose which brains exist.

Feature 2 is **not** gated on the deployment phase, but it **is** gated on
Feature 1 Phase 1A: exposing a read surface over a namespace that leaks is worse
than the status quo.

## Owner decisions this needs before 1C

1. **Refusal UX.** When a policy blocks an answer, what does the asker see — a
   flat "not permitted", a request-to-access affordance, or a partial answer from
   the permitted subset only? The three are very different products; concealment
   is not one of them.
2. **Gmail and Slack DMs.** Message-level ACL makes almost every personal email
   and DM `OWNER`-only, which means the workspace brain stops answering questions
   about them for *everyone*, including the sender's own team. Accept that, or
   keep personal correspondence out of the brain entirely.
3. **External agents holding credentials.** Should a third-party agent get a
   long-lived Kestrel key at all, or only short-lived, per-org, read-only
   tokens minted per session? This decides whether `identity_links` is a
   convenience table or the security boundary.

## What must not change while building this

* One managed port — `:8000`, brought up by `ops_stack_up.sh`.
* No new dependencies.
* No fabricated citations; no semantic caching anywhere on the citation path.
* A storage outage surfaces as `503`, never as an empty list — including from
  every new ACL lookup. If `document_acl` cannot resolve, the request fails
  closed and loud; it does not degrade to "no policies found".
* Deletion, re-ingest, force-push, history rewrite and key rotation stay
  owner-only, every time.
