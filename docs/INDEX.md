# Document map — what to read, what to trust, what to update

Generated 2026-10-04 from evidence, not from titles: for every root markdown file,
inbound references from code/scripts/docs (`git grep`), last commit touching it
(`git log -1 --format=%as`), and whether the claims inside still match the tree.
The root carried 32 markdown files; this page exists so the next release does not
have to re-derive which of them are load-bearing.

Rule of thumb: **start at `AGENTS.md`.** Everything below is either an operating
record, a historical record, or a business document.

## Living — update these as you work

| File | Purpose | Inbound refs | Update when |
|---|---|---|---|
| `AGENTS.md` | the agent entrypoint: battery lanes, DB boundaries, dist rule, schema authority | — | any command or boundary changes |
| `PROGRESS.md` | execution log, newest first | 6 | every completed piece of work |
| `BUGS_AUDIT.md` | defect ledger by round (1–9), each closure with its measurement | 8 | every defect found or fixed |
| `docs/FIX_LOG.md` | the running fix account for the current branch: status per defect, the test that proves it, the battery line after each commit, and what was never run against a real stack | new | every commit on a fix branch |
| `docs/HANDOVER_2026-10-05.md` | the handover for `fix/bughunt-2026-10`: the live/branch skew, the boundaries, every defect with its proof, the review round, the measured inventory of what is built, and the plan + prompts to continue from | new | when the branch merges, is abandoned, or the inventory changes |
| `BLOCKERS.md` | open escalations, `M-<phase>.<n>` | 5 | when something needs the owner |
| `PLAN.md` | locked 7-phase plan (P1–P3 done, P4 = deploy) | 4 | **do not re-litigate**; amend only with a decision |
| `DESIGN.md` | frontend design system: tokens, components, the rules CI/battery can check | 3 | any visual or token change |
| `README.md` | human-facing product overview | — | features/positions change (its architecture section is hackathon-era; see below) |
| `docs/architecture/` | runtime topology + document-health gate output (Round 4) | new | when ports, services or release paths change |
| `docs/api-analysis/` | per-endpoint logic + API agent-readiness score | new | when a route's contract changes |
| `docs/ui-review/` | UI audit and browser baselines | 3 | before/after visual work |
| `docs/CATEGORY_SCAN_2026.md` | 2026 feature bar scored against this codebase, connector landscape and the standout thesis | new | before committing roadmap or connector work |
| `docs/BUG_HUNT_2026-10-05.md` | the widest engine + UI hunt to date: 26 defects, evidence and repro per finding, and which were fixed versus handed back | new | when one of its open items is closed |
| `docs/SYSTEM_PRODUCT_REVIEW_2026-10-05.md` | the single consolidated review: goal, measured state, every open defect, the design audit, and the owner's decisions | new | when an open item closes or the measured numbers move |
| `docs/HARNESS_BLUEPRINT_2026.md` | the harness plan: what each of the five work-loop dimensions must grow, and the gate every new platform feature must arrive with | new | when a phase lands or a defect class gains a detector |
| `docs/ACL_AND_MCP_BLUEPRINT.md` | **design, not built** — document-level policy model, the two live enumeration oracles that must close first, and the in-process MCP read surface | new | when an ACL phase lands or an oracle is closed |

## Historical — read-only, do not cite as current

`CLAUDE_CONTEXT.md` (6 refs; superseded by `AGENTS.md`, kept because it is the only
narrative of the hackathon build), `PROJECT_TIMELINE_AND_STATUS.md` (through 28 Sep),
`docs/LEGACY_SHELL_SPEC.md` and `docs/LEGACY_TO_REACT_PARITY.md` (the spec and the parity
ledger for the shell that was deleted on 2026-10-04 — kept as the record of what the React
port had to reproduce, not as a description of anything that still exists),
`BUGS.md` (370 lines, pre-audit ledger; `BUGS_AUDIT.md` is the ledger now),
`STACK_REVIEW.md`, `IMPROVEMENTS.md`, `CHATBAR_DESIGN.md`, `DEMO_DAY.md` (one
event's runbook), `REALITY_CHECK.md`, `UPGRADE_REPORT.md` +
`UPGRADE_COMPLETION_REPORT.md` (two accounts of one upgrade; the 281-line one is the
fuller record), `BUILD_PLAN.md`, `DELTA_PLAN.md`, `EXECUTION_PLAN.md`,
`CONNECTOR_STATES.md`, `DEPLOY_VERCEL.md`, and the `docs/baseline/` captures.

Where a historical document disagrees with the code, **the code wins** — that is the
rule `ops/doc_health.sh` now enforces for the entrypoint-facing claims.

## Business documents — not clutter, do not treat as technical debt

`INDIA_PRICING.md`, `STUDENT_PACK_STACK.md`, `SELFHOST_BUSINESS_CASE.md`,
`GRANTS_AND_CREDITS.md`, `GLOBAL_GRANTS_AND_CREDITS.md`,
`OSS_STACK_AND_COMPETITORS.md`. These carry pricing and grant narratives with
mutually inconsistent margins (see the trust map in `BUGS_AUDIT.md` Round 1
cross-references); they are application/commercial artefacts, so they were left in
place rather than moved or merged.

## Removed on 2026-10-04 (dead code, evidence-based)

`battery.py` (superseded by `verify.sh` — no importer, no invoker, referenced only in
old prose), `contract_test.py`, `provider_check.py`, `slack_scopes_test.py` (all: zero
code references, wired into no entrypoint), and `STACK_AUDIT_PROMPT.md` (a one-time
prompt whose output, `STACK_REVIEW.md`, is the artefact). Deleted files remain
recoverable from git history; the battery was re-run afterwards to prove nothing
depended on them.

**The legacy UI is gone as of the same day.** `static/` was deleted whole: `graph.html`
(the last hand-written page) with `shell.js`, `ui.js`, `auth.js` and `shell.css`. Its
canvas force layout, camera zoom/pan, click-to-open disclosure over the twelve core nodes
and the node inspector were ported into React's `GraphView` first, and each behaviour is
gated in `check_ui_react.py`'s "graph view" section — sixteen checks, all passing, before
the file went. `/graph`, `/brains` and `/upload` are 307 redirects into the app and
`app.py` no longer mounts `/static`. `frontend/src/legacy/` was **renamed, not deleted**:
it is the design system the React app imports, and the directory name had already fooled
two reviews into proposing its removal. Older documents that cite `static/…` paths
(`BUGS.md`, Round 1 of `BUGS_AUDIT.md`, `docs/ui-review/`, `docs/LEGACY_*`) are historical
records; they now describe deleted files and must not be read as current.

## Still clutter — decisions left to the owner, not acted on

1. `parity_gate.py` + `parity_shots.py` + `parity_states.py`: a working visual-parity
   capture tool (uses Playwright, mentioned in `requirements-dev.txt`) that **no
   entrypoint runs**. Either wire it into CI or delete it; leaving it unwired is how
   it became invisible.
2. `screenshots/` (3.1 MB, 11 PNGs, linked from `README.md`) vs
   `docs/ui-review/screens/` (41 files): two screenshot trees for one product.
   Consolidating means editing README links.
3. `Dockerfile.candidate` + `compose.cutover.yml` + `ops/cutover_162.sh`: the one-time
   v1.6.2 Cognee cutover path, referenced only by historical reports. Archive under
   `docs/history/` or keep as the rehearsal record it is.
4. `BUGS.md` vs `BUGS_AUDIT.md`, `UPGRADE_REPORT.md` vs `UPGRADE_COMPLETION_REPORT.md`,
   `OSS_STACK_AND_COMPETITORS.md` vs the untracked `COMPETITOR_ANALYSIS.md`: three
   near-duplicate pairs. Merging loses nothing except provenance, which git keeps.
5. Untracked and undecided: `COMPETITOR_ANALYSIS.md`, `ZCODE_HANDOFF.md`,
   `docs/ui-review/screens/41-compare-react-5174.png`. Not committed, not deleted —
   they are yours.

## How to keep this true on the next release

```bash
bash ops/doc_health.sh            # entrypoint agrees with the repo (battery tier)
./verify.sh                       # the whole gate — it prints its own tier count, so
                                  # no number is repeated here. 23 ran / 1 skipped on
                                  # 2026-10-05; a stale count in a document is worse
                                  # than none, and three docs carried one.
git ls-files '*.md' | wc -l       # count of documents, which only ever grows
```
