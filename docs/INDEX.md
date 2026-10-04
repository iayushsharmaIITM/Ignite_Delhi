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
| `BUGS_AUDIT.md` | defect ledger by round (1–4), each closure with its measurement | 8 | every defect found or fixed |
| `BLOCKERS.md` | open escalations, `M-<phase>.<n>` | 5 | when something needs the owner |
| `PLAN.md` | locked 7-phase plan (P1–P3 done, P4 = deploy) | 4 | **do not re-litigate**; amend only with a decision |
| `DESIGN.md` | frontend design system: tokens, components, the rules CI/battery can check | 3 | any visual or token change |
| `README.md` | human-facing product overview | — | features/positions change (its architecture section is hackathon-era; see below) |
| `docs/architecture/` | runtime topology + document-health gate output (Round 4) | new | when ports, services or release paths change |
| `docs/api-analysis/` | per-endpoint logic + API agent-readiness score | new | when a route's contract changes |
| `docs/ui-review/` | UI audit and browser baselines | 3 | before/after visual work |
| `docs/CATEGORY_SCAN_2026.md` | 2026 feature bar scored against this codebase, connector landscape and the standout thesis | new | before committing roadmap or connector work |

## Historical — read-only, do not cite as current

`CLAUDE_CONTEXT.md` (6 refs; superseded by `AGENTS.md`, kept because it is the only
narrative of the hackathon build), `PROJECT_TIMELINE_AND_STATUS.md` (through 28 Sep),
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
./verify.sh                       # the whole gate, 13 tiers
git ls-files '*.md' | wc -l       # count of documents, which only ever grows
```
