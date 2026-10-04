# AGENTS.md

Operating contract for coding agents in this repository. Not a README: deeper
context is linked, not embedded.

## Validate before claiming anything

- `./verify.sh` — the full battery. It starts its own mock app tier on port 8020
  and refuses to run against the live database — including when a live `DATABASE_URL`
  was exported before it, not only when it picked the URL itself.
- `./verify.sh --quick` — skips the browser tiers. That is all the flag does: which
  suites write rows is decided by whether `DATABASE_URL` names the lab on 5434, not
  by `--quick`. The CI's fast job runs it against no database at all, which is where
  the "no lab writes" idea came from.
- `KESTREL_CLERK_GATE=1 DATABASE_URL=<lab 5434> ./verify.sh` — adds the
  Clerk-mode browser gate.
- Another port if 8020 is taken: `KESTREL_VERIFY_PORT=8021 ./verify.sh`.
- Do not use `python3 -m pytest` as the verification route. `verify.sh` states
  that pytest collects 2 of `test_pipeline_states.py`'s 13 checks and none of
  `test_tenants.py`'s 10. The old exception for `test_auth_isolation.py` was wrong
  on both halves and is corrected here: run it as `python3 test_auth_isolation.py`,
  which prints one `PASS`/`FAIL` line per check and exits non-zero on failure, and
  expect `pytest --collect-only` on it to abort — the suite refuses a non-lab
  database at import time, so collection itself raises. pytest is not the route for
  it either.
- A suite is green only when its own exit code says so and you read its log at
  `/tmp/kestrel_verify_<suite>.log`. Piping to `tail` reports `tail`'s status, not
  the suite's. Read the battery's closing `ran / skipped / failing` line too: exit 0
  with tiers standing down is not the same claim as a full pass.

## Boundaries that change behaviour

- Live is `:8000` with Postgres `5433`; the lab is `5434` with lab Cognee on
  `8889`. Never restart or write to live without Ayush.
- `KESTREL_ALLOW_LIVE_DB=1` is the only thing that lets the battery point at the
  live database, and it is Ayush's call to make — the same standing as deletion and
  re-ingest below. The abort messages in `verify.sh` and `test_auth_isolation.py`
  print it as a suggestion; treat that as a pointer to an owner decision, never as a
  retry flag you may set yourself.
- Single-brain mode locally: do not create brains or re-ingest datasets.
  Deletion, re-ingest, force-push, history rewrite, and key rotation require Ayush
  explicitly, every time.
- No new dependencies without Ayush's approval.
- Secrets live only in the gitignored `.env` and `.env.oss` — never echoed, never
  staged. `commit.sh` runs `git add -A` and then `ops/check_secrets.sh --staged`;
  `ops/check_secrets.sh --all` is CI's backstop and must exit 0. Use
  `KESTREL_ALLOW_SECRETS=1` only for a documented false positive.
- Product invariant: no fabricated citations, and no semantic caching on the
  citation path. Ever.

## Generated and dual-owned artifacts

- `frontend/dist` is committed and served by the Python tier. Any edit under
  `frontend/src` must be followed by `./ops/build_frontend.sh` in the same commit;
  CI fails on drift ("dist is in sync with src").
- Schema has two authorities: `storage.init()` DDL and `migrations/versions/*`.
  Every statement must be idempotent — `CREATE TABLE IF NOT EXISTS`,
  `ALTER TABLE … ADD COLUMN IF NOT EXISTS`, and
  `op.create_table(..., if_not_exists=True)` — because a deploy may boot the app or
  run migrations first, in either order. `migrations/env.py` bootstraps the app
  tier so a release-phase `alembic upgrade head` works on an empty database.
- Prove a schema change with `ops/test_fresh_bootstrap.sh` (throwaway Postgres on
  port 5435; touches neither live nor lab).

## Where truth lives

- [docs/INDEX.md](docs/INDEX.md) — the document map. Start here before trusting any
  markdown file: it marks which documents are living, which are historical, and which
  are commercial artefacts. It is the only place that grades the rest.
- [docs/architecture/](docs/architecture/deployment-topology.md) — runtime topology,
  ports, release path, and the `ops/doc_health.sh` output.
- `BUGS_AUDIT.md` — defect ledger by round. `PROGRESS.md` — execution log, newest
  first. `BLOCKERS.md` — open escalations, `M-<phase>.<n>`. `PLAN.md` — locked
  phase plan; do not re-litigate it. `DESIGN.md` — frontend design system.
- [docs/ACL_AND_MCP_BLUEPRINT.md](docs/ACL_AND_MCP_BLUEPRINT.md) — design, not built:
  document-level permissions and the MCP read surface. Do not describe it as shipped.
- When a documented claim turns out to be wrong, amend it in place with a visible
  correction instead of silently rewriting it.
- `README.md` is the human-facing product overview, and its architecture section is
  hackathon-era: it describes a tier layout this repository no longer runs. Trust the
  commands above and the code over it.
- `CLAUDE_CONTEXT.md` is historical. Where it disagrees with the commands above or
  with the code, this file and the code win.

## Debug route

- Battery: `/tmp/kestrel_verify_<suite>.log`, app tier at
  `/tmp/kestrel_verify_server.log`.
- Live app: `/tmp/kestrel_app.log`; `GET :8000/health` reports `provider`,
  `llm.active_base`, `llm.active_model`, `nova_status` and `upstream`.
- Lab brain: `docker logs kestrel-lab-cognee`. An LLM `RateLimitError` there means
  provider quota, not a broken restore or a broken backup.
- A storage outage must surface as 503, never as an empty list.
