# Kestrel runtime and deployment topology

Produced under `architecture-visualization:explore`, which routed this job to the
deployment-topology and architecture-health scenes. Attribution stated precisely: the
artefact was built against the package's shared contract references
(`architecture-contract.md`, `architecture-evidence-model.md`,
`diagram-output-formats.md`), not by executing the scenario skill bodies, and
`explore`'s own rule is to pick the smallest skill set that answers the question — so
the other nine skills in that package were deliberately not run, not overlooked.
Business-path modelling is deliberately not in this view — the ask/retrieve/persist
workflow is documented under `docs/api-analysis/` instead.

Audience: Ayush (owner/operator) and any agent preparing the P4 Heroku deploy.
Scope: where Kestrel runs today, how it is released, and what the deploy target
still lacks. Read the tables first; the diagrams are the same facts in graph form.

Every node and edge below carries evidence. Confidence: **high** = read from code,
config, a running process, or a container listing; **medium** = several partial
signals; **assumption** = stated, not observed.

## 1. Current state — one laptop, four stacks

| Process | Where it runs | Port | Backend it talks to | Evidence |
|---|---|---|---|---|
| Live web tier `python3 app.py` | host process, no supervisor | `127.0.0.1:8000` | Postgres `5433`, Cognee OSS `8888`, LLM via `tokenharbor.ai` | `.env` (`PROVIDER=cloud`, `COGNEE_FLAVOR=oss`, `COGNEE_SERVICE_URL`, `AUTH_MODE=clerk`), `lsof`, `GET :8000/health` |
| `kestrel-db` (postgres:17-alpine) | container | `5433→5432` | — | `docker ps` |
| `cognee-oss` (cognee/cognee:1.6.1) | container | `8888→8000` | `kestrel-db`, graph volumes | `compose.oss.yml`, `docker ps` |
| `kestrel-langfuse` (langfuse:2) | container | `3000→3000` | — | `LANGFUSE_HOST`, `docker ps` |
| Lab stack (`compose.lab.yml`, project `kestrel_lab`) | containers | `5434` db, `8889` cognee | its own volumes | `compose.lab.yml`, `docker ps` |
| Battery app tier | started by `verify.sh` | `127.0.0.1:8020` | lab db `5434`, `PROVIDER=mock`, `AUTH_MODE=off` | `verify.sh` PORT/BASE block |
| Restore drill app tier | started by `ops/restore_lab.sh` | `8010` | restored lab copy | that script, step 5 |
| Clerk-mode gate tier | started by `tests/test_react_clerk.py` | `8031` | lab db `5434` + self-served JWKS | `KESTREL_TEST_PORT` |

Storage nodes (the ones a backup has to be right about):

| Volume / database | Owner | Backup that covers it | Confidence |
|---|---|---|---|
| `kestrel-db` → database `kestrel` | live app | nightly `pg_dump` **and** `ops/backup.sh` | high |
| `kestrel_brains_cognee_oss_state`, `..._data` | `cognee-oss` | nightly tars; `ops/backup.sh` writes `.tgz` | high |
| `kestrel_lab_state`, `kestrel_lab_data`, `kestrel_lab_db` | lab | not backed up (scratch by design) | high |

## 2. Two release paths exist in this repo, and they disagree

| Path | Definition | State | Evidence |
|---|---|---|---|
| Render | `render.yaml` — web `ignite-web` + workflow service, region singapore, free plan, `startCommand: python app.py`, `healthCheckPath: /health` | **dormant**: it targets the Cognee **Cloud tenant** ("no LLM key and no database password below: the tenant owns the model"), which is not what runs today | `render.yaml` header comments; today's `.env` uses `COGNEE_FLAVOR=oss` |
| GitHub Actions | `.github/workflows/ci.yml` — `fast` + `ui` jobs | **active**, and it stops at CI: no deploy step anywhere in the file | `ci.yml` |
| Heroku (PLAN P4) | not yet defined | **missing**: no `Procfile`, no `app.json`, no `system.properties`, no release-phase command | `ls Procfile` → not found |
| Vercel | `DEPLOY_VERCEL.md` documents a static/snapshot deploy | describes an earlier demo architecture | that file |
| launchd | `com.kestrel.backup` nightly 03:17 → `~/Kestrel_backups`; `com.kestrel.stackup` login self-heal | backup half **working and drift-checked**; stack-up half **cannot execute** (launchd cannot read `~/Desktop`, exit 126) | `ops/install_agents.sh`, `BLOCKERS.md` M-ops.1 |

## 3. The single point of failure worth naming

The live tier is an unsupervised host process. There is no launchd, Docker, or
container orchestration keeping it up: the only automatic recovery route is
`com.kestrel.stackup`, which macOS refuses to execute from this path
(`BLOCKERS.md` **M-ops.1**). So "the app is down" is currently repaired by a human
opening a terminal. `ops/restore_lab.sh` proves the data can be restored; nothing
proves the *service* comes back.

Second availability edge, distinct from the first: answering depends on an
upstream LLM quota. Both the lab and live route to a `deepseek … :free` model
(`/health` reports `llm.active_base=tokenharbor`, `llm.active_model=…:free`;
`docker logs kestrel-lab-cognee` shows `RateLimitError … next rolling 7-day
period starts on 6 Oct 2026 at 07:29 UTC`). A quota exhaustion looks exactly like
an application outage to the person on the other side of the browser.

## 4. Target state for P4 (Heroku) — what has to be true

Labelled as design, not observation.

1. `Procfile` with `web: python app.py`, and `PORT` honoured — `app.py:2121`
   already reads `int(os.getenv("PORT", "8000"))`, and Heroku injects `PORT`, so no
   code change is needed for binding. Bind host matters: `HOST=127.0.0.1` in `.env`
   would refuse external traffic on Heroku. **Verify before deploy** — this is the
   most likely first-day failure.
2. Release phase runs `alembic upgrade head` **before** the app boots. This is now
   safe: `migrations/env.py` bootstraps the app-tier schema first, and both orderings
   were measured from an empty database to `0006_brain_claim (head)`.
   `ops/test_fresh_bootstrap.sh` is the existing verifier for exactly this.
3. Postgres moves from a container to a managed service; `DATABASE_URL` is already
   the single knob (`storage.py`, `migrations/env.py` rewrite `postgresql://` →
   `postgresql+psycopg://`).
4. Cognee cannot be a dyno-sidecar on Heroku. Either the Render-style cloud tenant,
   or an external container host. Until that is decided, the deploy target is
   undecided, because "backend" here is a graph database with two named volumes, not
   a URL.
5. Backups have to leave the laptop. The current receipt is honest
   (`FAIL`/`STALE` end the run) and the artefacts restore, but both live under
   `~/Kestrel_backups` on the same disk as the data they protect.

## 5. Reading order and how to re-verify

```bash
docker ps --format '{{.Names}}\t{{.Ports}}'      # containers, right now
lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(8000|8020|8010|8031|8888|8889|5433|5434)'
curl -s localhost:8000/health | python3 -m json.tool   # provider, llm route, upstream
cat "$HOME/Kestrel_backups/backup.status"        # last real backup receipt
bash ops/install_agents.sh --verify              # drift between repo and installed job
```

Diagram sources: `deployment-topology.dot` (graphviz; `dot` is not installed on this
machine, so render it with `dot -Tsvg deployment-topology.dot -o topology.svg`
wherever graphviz exists) and `deployment-topology.mmd` (Mermaid, renders in the IDE
without a toolchain).

## 6. Known unknowns

- Whether the live tier binds `127.0.0.1` only on purpose (`HOST=127.0.0.1` in
  `.env`) — for Heroku it must not.
- Whether `cognee-oss` is restarted by anything after a colima stop; nothing in the
  repo claims to.
- Which LLM provider live will use after the free window; `render.yaml` deliberately
  carries no key, so the answer is a human decision, not a config value.
