# Document health — what the repo's own docs still get wrong

Method: the architecture-health scene from `architecture-visualization:explore`'s
routing (see the attribution note in `deployment-topology.md` — built against the
package's shared contract and evidence references, with the scenario bodies not
separately executed). It answers one question: **can a coding
agent trust these documents?** Every row below was checked against code, config, or
git state, not against another document.

The check is now mechanical, not a review: `ops/doc_health.sh` asserts it and
`verify.sh` runs it as the `doc-health` tier, so a document that contradicts the
repo fails the battery instead of waiting for the next audit.

## Verified and now correct (fixed 2026-10-04)

| Claim that was false | Where | What it cost an agent | Fix |
|---|---|---|---|
| "verify with `python3 -m pytest test_documents.py test_pipeline_states.py`" | `CLAUDE_CONTEXT.md` §8 | A false green: `verify.sh` states pytest collects 2 of 13 pipeline checks and none of `test_tenants.py`'s 10 | §8 now routes `./verify.sh` / `--quick` and says plainly that the file is historical |
| "M4 (TOCTOU) remains open" | `CLAUDE_CONTEXT.md` §7 item 5 | A wrong picture of open defects; M4 was closed by the brain-claim work | Marked closed with the commit and the test that proves it |
| "history is clean and green at `e07a219`" | `CLAUDE_CONTEXT.md` §Git | A pinned revision that was ~30 commits stale at the time it was read | Replaced with a pointer to `PROGRESS.md` + `git log` |
| `python3 test_auth_isolation.py` as a runnable route | that file's docstring | Silent no-op: importing the module created a database, defined five tests, ran none, exited 0 | Added a real standalone runner; both routes now report 5/5 |
| The suite writing to whichever server `DATABASE_URL` names | `test_auth_isolation.py` | With no `DATABASE_URL` it falls through to `.env` — the **live** database — and creates/truncates a database there | Lab-only guard, same rule the battery already applies, `KESTREL_ALLOW_LIVE_DB=1` to insist |

Still true but worth naming: `README.md` describes the hackathon-era architecture
("Cognee + Render Workflows", `README.md:9`, `:129`, `:137`) and its feature table
reports `pytest test_pipeline_states.py → 2/2 PASS` (`README.md:339`). Both are
accurate about that moment and misleading about this one. `README.md` is human
documentation, not an agent route, so it is left as-is rather than rewritten —
`AGENTS.md` is the entrypoint.

## Deferred: divergences whose owner is Ayush, not a script

`ops/doc_health.sh` reports these as `WARN` and does not fail the battery, because
"fixing" them means a decision, not an edit.

1. **`compose.oss.yml` is tracked while `BUILD_PLAN.md` N3 requires it gitignored**
   (`BUILD_PLAN.md:30`, `:182`, `:187`). Verified: `git ls-files` tracks it,
   `.gitignore:40` covers `.env.oss` but nothing covers `compose.oss.yml`.
   `ops/check_secrets.sh --file compose.oss.yml` exits 0 — the file interpolates
   `${VAR}`s and contains no secret-shaped literal — so this is a policy conflict,
   not a leak. The rule's stated reason was "it will carry local secrets", which
   makes either resolution legitimate: untrack it, or amend N3.
2. **Two backends live in one repo.** `.env` runs `COGNEE_FLAVOR=oss` against a
   local Cognee container, while `render.yaml` is written for the Cognee **Cloud**
   tenant ("no LLM key and no database password below: the tenant owns the model").
   The Render path is dormant. This matters for P4: the deploy target is undecided
   until the backend choice is, because Cognee here is a graph store with two named
   volumes, not a URL.
3. **`PLAN.md` P4 is Heroku and there is no `Procfile`** (verified absent; also no
   `app.json`/`system.properties`). `HOST=127.0.0.1` in `.env` would additionally
   refuse external traffic on a platform that injects `PORT` and expects `0.0.0.0`.
   See `deployment-topology.md` §4.

## How to re-verify

```bash
bash ops/doc_health.sh                                  # the assertions themselves
grep -n "python3 -m pytest test_" CLAUDE_CONTEXT.md     # expect: nothing
grep -n "pytest collects only" verify.sh                # expect: the canonical line
git ls-files --error-unmatch compose.oss.yml            # expect: tracked (deferred #1)
grep -n "COGNEE_FLAVOR" .env; grep -n "type: web" render.yaml
```

Reading order for a new agent: `AGENTS.md` → this file if it concerns docs →
`deployment-topology.md` if it concerns running or releasing → `PROGRESS.md` for
current state → `BUGS_AUDIT.md` Round 3 for the defect history →
`CLAUDE_CONTEXT.md` as history only.
