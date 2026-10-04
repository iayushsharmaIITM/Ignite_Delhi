# The harness we need, and what each new feature must arrive with

Status: **plan.** Written 2026-10-05, after two Better Harness reviews
(`.qoder/better-harness-runs/`) and the 26-finding engine+UI hunt
(`docs/BUG_HUNT_2026-10-05.md`). Structured on the Agent Work Loop model the
review uses — five dimensions, fifteen checks — because that is the frame the
findings were already graded against. Nothing below is built; the current-state
numbers are measured, the target capabilities are proposals.

## What the harness is for

The product's claim is **a company brain whose citations you can trust and whose
permissions it respects**. The harness exists to make that claim mechanically true
rather than culturally true: to make it hard to ship an answer that isn't grounded,
a delete that loses data, an outage that looks like an empty list, or a route that
leaks a document the caller shouldn't see.

One rule governs every addition, and it is the rule this session earned:

> **A gate earns its place by naming the wrong it makes impossible.**
> `tests/test_phatic.py` exists because greetings were paying 11–25s of retrieval in
> production. `ops/check_doc_routes.py` exists because README advertised a browser
> suite for a file deleted the same morning. `ops/test_fresh_bootstrap.sh` was
> rewritten because it *could not fail* — and AGENTS.md told agents to trust it.

The corollary is what most of the sections below are about: **a capability without a
failing-first check is not a capability, it is a claim.** Three of this project's
worst defects were exactly that — code that had been merged and never run
(`test_v2_authz.py`), a doc that asserted coverage no lane executed, and a feature
(`parity_gate.py`) documented as running in CI that appears zero times in both
entrypoints.

## Where we stand, measured

| Surface | Today |
|---|---|
| Local battery | `verify.sh` — 18 tiers incl. the browser suite; lab-gated tiers SKIP rather than fake-pass, and the run closes with `ran / skipped / failing` |
| Hosted CI | 2 jobs (`fast`, `ui`). Green. Enforces `dist` ↔ `src` sync and that the served bundle is self-consistent; brings its own Postgres on 5434 and migrates it |
| Correctness | Extraction, pipeline states, tenant isolation, chat integrity (CH-1..CH-9), brain-claim race, route authz (allow/deny/traversal), v2 job authz, lifecycle identity, lease recovery, connectors vault/OAuth |
| Frontend | Acceptance over the **served** bundle: ask, stream, citations, files, draft, menus, keyboard focus, deep links, history, sidebar rail/motion, 16 graph gates, stale-bundle behaviour |
| Guardrails | `commit.sh` → staged secret gate; CI → tracked-file scan; `ops/doc_health.sh` → 9 checks incl. living-doc routes resolving; fresh-bootstrap schema proof on a throwaway DB |
| Honesty | Phatic routing tier (38 checks, hermetic, refuses a non-lab `DATABASE_URL`); API agent-readiness score (59.7%, 48 checks) |

Harness scores from the last review: task-understanding 70, controlled-execution 62,
change-validation 66, reliable-delivery **52**, learning-capture **45**. The two weak
dimensions are exactly the two that gate a real launch: acceptance/recovery and
turning fixes into durable capability.

---

## 1 · Task Understanding — the agent must know what "done" means

*Current:* `AGENTS.md` is a real contract and most of its claims were verified true,
but it has mis-routed agents twice this round (a pytest exception that crashes, a
`--quick` that promises less than it does).

*Target.*
- **Invariant section, first.** No fabricated citations · no semantic cache on the
  citation path · a storage outage is 503, never an empty list · deletion, re-ingest,
  force-push, rotation, `KESTREL_ALLOW_LIVE_DB` are owner-only, every time. One
  screen, not scattered prose.
- **A lane table that states what each lane touches** — which tiers write rows, which
  need the lab, which need a browser — because the flag-vs-database confusion was a
  live hazard, not a wording nit.
- **Definition of done per change class**: schema → fresh-bootstrap; UI → `ui-react`
  green in a browser; engine route → its tier + a failing-first assertion; new
  connector → the permission matrix below.
- **A route map to the docs** (already added) and a rule that a claim that turns out
  wrong is amended in place with a visible correction.

## 2 · Controlled Execution — one port, one database per risk, no live by accident

*Target.*
- **`KESTREL_ALLOW_LIVE_DB` gated in code, not just prose** — the guard now judges
  the effective URL; keep it that way and have a test prove the abort.
- **A lab lifecycle any agent can run blind**: `ops/restore_lab.sh`, `ops/seed_lab.py`
  (to exist), and a documented reset so a tier that writes rows can be re-run
  deterministically from a clean slate.
- **Stray-port enforcement strengthened**: `verify.sh` reports leftovers; it should
  *fail* a run that found a second app tier, because two tiers disagreeing about auth
  and database is how previews start lying.
- **A single dev entrypoint** that brings up exactly what the tier needs and nothing
  else, so "spin the preview" never means "start a second server".

## 3 · Change Validation — every feature arrives with the check that fails first

This is where new features plug in. Each row is a capability the platform needs and
the gate it must not be shipped without.

| Capability the market expects | Kestrel's version | Gate it arrives with (failing first) |
|---|---|---|
| **Connectors** (Onyx 40+, Glean 100+; we have 2) | Ranked set from `CATEGORY_SCAN_2026`: WhatsApp, Zoho, Notion, Xero/Tally | Per-connector contract suite — scope, token refresh, revoke, failure-as-503 — and an **honest capability matrix** in `/api/config`, so an unsupported source never answers as if it were indexed |
| **Permission-aware citations** (the thesis; `docs/ACL_AND_MCP_BLUEPRINT.md`) | Phase 1A closes both enumeration oracles, then document-level policy | A refusal test per visibility state, asserting the answer is **withheld**, not that citations were hidden — filtering citations alone is concealment |
| **Agent surface** (MCP) | In-process `POST /api/mcp`, 5 read-only tools, byte-identical `tools/list` | Same ACL entry point as the UI in a single test; `tools/list` equality asserted; no new dependency |
| **Evals / groundedness** | Golden question→source→answer set per corpus | `tests/test_evals.py` scoring citation-resolution rate and **hallucinated-source count = 0**; run on every ingest change. Nothing else turns "trust" into a number |
| **RAGAS-style faithfulness** | Faithfulness + refusal-correctness on the fixture corpus | Threshold in the tier; regression in a number, not in a vibe |
| **Ask/answer observability** | Route split already traced (phatic/chat/brain), Langfuse fire-and-forget | Cost-per-route assertion so an outage or a misroute can't silently double-spend; usage row present on abort paths (fixed today, keep the gate) |
| **API contract quality** | 59.7% agent-ready today; P1 = 0/39 success schemas | `ops/api_readiness.py` ≥ 70% **and zero Criticals** as a CI step, with `--ablate-error-contract` proving the checks bite |
| **Search / hybrid retrieval** | Existing racer/hedge design plus reranking | Recall-vs-citation-precision eval, so a "better" retriever that fabricates sources cannot win on latency alone |
| **Multi-tenancy at scale** | Single-worker today | A load smoke asserting 503-not-empties under saturation; a shared rate-bucket note where the code already flags it |
| **Localisation** (6 locales shipped) | Fix the 19 keys in no locale; sweep the components bypassing `t()` | **Gate first**: a check that fails when a component renders a string `t()` has no key for — otherwise the sweep silently regresses, which is how it drifted |
| **Accessibility** | Keyboard-reachable graph, focus in modals, real buttons | The existing focus/landmark gates extended to every interactive surface, plus an axe pass in `ui-react` |
| **Backup / restore** | Nightly snapshots exist; the drill can't yet prove brain-level recovery (M-ops.2) | A restore drill tier that asserts a named document is retrievable **and cited** after restore — recovery you can't prove isn't recovery |
| **Secrets** | Two Bedrock keys + an `AKIA` id in 7 gitignored files, invisible to CI's scanner by construction | Extend the scan to ignored local files in a *dev* hook (never in CI logs), and gate on rotation being recorded, not on detection |

## 4 · Reliable Delivery — the weakest dimension, and the one a launch depends on

*Target.*
- **Branch protection with the battery as a required check.** Without it CI is advice.
- **A release path with a proof at the end**: build → fresh bootstrap → migrate →
  boot → `/health` + one cited answer against the lab, as a single `ops/release_check.sh`
  (to exist) that must pass before `:8000` is touched.
- **Rollback that is rehearsed, not written down** — the restore drill above, run
  monthly, with its output archived in `var/evidence/`.
- **An off-disk second copy.** Every backup currently sits on the same iCloud-exposed
  path as the database it restores.
- **Live restart discipline**: this session twice left `:8000` running old routes
  while serving a new bundle, which 500'd the Graph nav. Rule: a change touching a
  served file or an engine route ships *with* the restart and a live probe, or not at all.

## 5 · Learning Capture — turn each fix into a permanent refusal to repeat it

*Current:* 45. Two detectors exist (`doc_health.sh`, `check_secrets.sh`) and one was
just written *because* the other couldn't see its class. Session evidence produced
zero eligible episodes, so repeated-demand claims are unobserved, not absent.

*Target.*
- **Defect-class ledger**: every closed `BUGS_AUDIT` item that came from a *class*
  (ordering-before-decision, error-as-empty, unrun gate, seeded-data dependency,
  vacuous assertion, doc claiming unwired verification) gets a named detector or an
  explicit "no mechanical detector possible" line. Six classes recurred this session.
- **The gates themselves are tested.** The single most valuable harness habit here:
  before believing a check, break the thing it defends and require it to fail. It
  caught `--quick`, the fresh-bootstrap script, T3's vacuous PASS, and a `.some()`
  that was always truthy.
- **Run the harness review on a cadence** — after each phase, not only after incidents.
- **Machine the human steps.** Two of today's findings were "a document tells an agent
  to do X" and "an override the tool prints isn't owned by the contract". Anything a
  doc or error message *suggests* must be either gated by code or named in `AGENTS.md`.

---

## Sequencing

1. **H1 — trust the tests.** Wire the two unbuilt-but-cheap gates: the i18n key
   gate and the "gate fails when it should" ablations for the readiness score. Then
   **branch protection + required check** and the **push** the owner already owes.
   Nothing new ships before H1: every later phase assumes its gate will be enforced.
2. **H2 — the thesis.** ACL Phase 1A (close both oracles) → evals with
   hallucinated-source = 0 → 1B/1C document policy. MCP after 1A, never before.
3. **H3 — reach.** Connectors in ranked order, each with its contract suite and
   capability-matrix honesty. Restore-drill proof and the off-disk copy land here,
   because volume without recovery is risk.
4. **H4 — polish that is actually debt.** Localisation sweep (after its gate),
   accessibility surfaces (reusing the correct components already in the tree),
   multi-worker readiness.

## Decisions that are the owner's, not the harness's

Branch protection and the pending push; key rotation scope (two Bedrock keys + the
`AKIA` id, and whether the ingested copy needs a re-ingest to purge); which
connector ships next and against what customer segment; whether evals run on the paid
provider per commit or nightly; external agents holding credentials at all; the ten
open findings in the hunt report — A-57 (collision table, the only remaining hole
under the citation invariant) first.

## What must not be traded away

One managed port. No new dependencies without an explicit yes. No fabricated
citations; no semantic caching on the citation path. A storage outage is a 503, never
an empty list. Deletion, re-ingest, force-push, history rewrite and rotation are
owner-only, every time. And a feature does not count as shipped until something
proves it can fail.
