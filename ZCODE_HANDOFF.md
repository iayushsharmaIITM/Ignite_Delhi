# ZCODE_HANDOFF.md — session state for the next ZCode account

**Written:** 28 Sept 2026, ~20:00 IST, by the previous ZCode session.
**Purpose:** complete handoff of what's built, what's in flight RIGHT NOW, and
what's next. Read fully before acting. The predecessor documents still apply:
`CLAUDE_CONTEXT.md` (written earlier today — architecture, traps, decisions;
still accurate except where updated below), `DEMO_DAY.md` (tomorrow's runbook),
`PLAN.md` (locked 7-phase plan), `PROGRESS.md`, `BUGS_AUDIT.md`.

---

## 1. THE ONE URGENT THING: demo is TOMORROW (Tue 29 Sept)

The product is demo-ready and verified. The morning procedure is
`DEMO_DAY.md`. **Key change since that file was written:** the stack is now
self-healing — a LaunchAgent (`com.kestrel.stackup`) runs
`ops_stack_up.sh` at login: starts colima → compose (brain+db) → waits for
health → starts the app if port 8000 is dead. So logging into the Mac should
bring everything up; then just sign in as the OWNER and run warmup
(`python3 warmup.py --token-file ...` — see DEMO_DAY.md §2–3 for the
password-less owner sign-in recipe and the token-refresher loop).

**Critical context — colima was STOPPED again when this handoff was written**
(the third such incident; Docker socket unreachable, containers down). The
LaunchAgent only fires at login, so if the Mac slept/rebooted without login,
run `./ops_stack_up.sh` manually (idempotent, ~2 min) and check
`curl http://127.0.0.1:8000/health` says `upstream: ready, auth: ok`.

## 2. Committed state (everything green, battery-verified)

`main` @ `d604266`. Latest commits, newest first:
- `d604266` — footer ("local oss · ready") removed; self-healing stack
  LaunchAgent added; root-caused the user's 503+403 cascade to colima-down
  (fail-closed authz + the T3 503 guard both behaved correctly).
- `c21f2f0` — CLAUDE_CONTEXT.md (full context doc, still worth reading).
- `e07a219` — **OCR ladder**: scanned/image-only PDFs answer in chat.
  `ocr.py`: PyMuPDF renders locally → one OpenRouter vision call
  (`openai/gpt-6-luna`, free fallbacks; `KESTREL_OCR_MODELS` overridable;
  max 10 pages / 3MB). `documents.py` raises typed `ExtractEmpty` for scans
  (trigger is the exception type — do NOT string-match error messages; that
  bit once). Working line shows "read via OCR".
- Earlier today: `a735413` PDF/DOCX chat answers (`/api/extract` route),
  bug-fix batch (T1–T5: demo runbook, Q2 latency profile, create_brain 503
  on tenant-down, footer honesty, recovery-table gotcha), `9b397e9`
  preservation commit. Before that: 59-defect fix session, settings system
  (6 languages, 3 themes, usage stats, upgrade, account, disconnect), WCAG
  contrast fixes, Clerk gate fixes (boot, JWKS cache, reload-loop), slide
  animation.

Battery at last run: 25/25, 13/13, 10/10, 4/4, UI pass; auth isolation 5/5.
**Verification habit (non-negotiable):** after any shared-code change, run
`./verify.sh` (needs port 8000 free: kill by port — `lsof -nP -iTCP:8000
-sTCP:LISTEN -t | xargs kill`; `pkill -f "python3 app.py"` does NOT match)
then restart the app (`nohup python3 app.py > /tmp/kestrel_app.log 2>&1 &`).

## 3. IN FLIGHT (uncommitted working tree) — P5 Langfuse observability

The task: wire **Langfuse** tracing to every LLM call (locked in PLAN.md P5;
P2 deferred it). Ayush explicitly asked for it with "test at every step."

**Done, uncommitted, code-complete and unit-tested:**
- **`observe.py` (new)** — zero-dependency Langfuse bridge. One
  `observe.trace(feature=..., brain=, route=, model=, user=, est_prompt=,
  est_completion=, ms=, ok=, error=)` call queues a trace; a daemon thread
  POSTs to `<LANGFUSE_HOST>/api/public/ingestion` (Basic auth). Fail-open by
  design: no keys → silent no-op; any error dropped; bounded queue (500).
  Unit-verified: queues and drains cleanly.
- **Wire points (4, all patched, syntax-checked):**
  1. `app.py` `/api/ask` — route dimension captured from the orchestrator's
     own stage labels (`smalltalk`/`chat`/`brain`), success + error paths,
     same chars/4 estimates as the `llm_calls` metering; also
     `require_dataset_access` now RETURNS the identity (needed for userId).
  2. `orchestrator.py` `_classify` — the router's own LLM call traced with
     its decision; failure path traced too. NOTE: the `import observe` is
     function-local (inside `_classify`) — top-level didn't fit the file's
     import layout; verify it survives any refactor.
  3. `summarizer.py` `summarize_history` — both paths.
  4. `ocr.py` `read_pdf` — vision call, with `meta={"pages": N}`.
- **`compose.oss.yml`** — added a `langfuse` service (image
  `langfuse/langfuse:2`, port 3000, Postgres-only v2 — no ClickHouse),
  `depends_on: postgres` (NOT kestrel-db — that's the container_name, the
  SERVICE name is `postgres`). Compose validates.
- **`.env` (gitignored)** — LANGFUSE_* vars added; keys were rotated to the
  proper format (`pk-lf-` + 32 hex).

**Where it's STUCK (exact resume point):** the local Langfuse container is
healthy (`/api/public/health` → `{"status":"OK","version":"2.95.11"}`) but
**API auth fails: "Invalid credentials"**. The `LANGFUSE_INIT_*` env vars
reach the container but the v2.95.11 init seeder does not run (0 orgs, 0
users, 0 projects in its DB after clean wipe + recreate — verified in
`docker exec kestrel-db psql -U kestrel -d langfuse`). Path chosen to fix:
**UI signup at `http://localhost:3000/auth/sign-up`** (name/email/password —
creds in `.env`: ayush@kestrel.local / kestrel-local-demo), then create an
org + project in the UI and mint API keys, then update `LANGFUSE_PUBLIC_KEY`
/ `LANGFUSE_SECRET_KEY` in `.env`. **The browser automation was ~2 steps into
the signup form when the session ended** — the form fields were located
(name/email/password); the submit click had not completed. An alternative if
UI signup fights back: run the seeder manually inside the container
(`docker exec -it kestrel-langfuse node …` — find the init script in
`/langfuse`), or insert org/user/project rows directly via SQL (v2 schema:
organizations, users, projects, api_keys tables — bcrypt'd password not
needed if you only use API keys).

**After keys work, the remaining verification checklist:**
1. `python3 -c "import observe; observe.trace(feature='handoff-test',...)"
   → confirm it appears in `GET /api/public/traces` (Basic auth with the
   new keys).
2. Restart app; run one live ask (smalltalk + one brain question) as owner;
   confirm both traces land with the right route labels.
3. Trigger summarize + OCR once; confirm their traces.
4. Full `./verify.sh` (expect green — the bridge is fail-open by design, so
   even a dead Langfuse cannot break the battery).
5. Commit as one P5 commit. Then optionally: a `/api/usage` enhancement or
   dashboard pointer is NOT required — P5's remaining scope after this is
   the model-routing formalization (see §5).

## 4. Standing rules (unchanged, all still locked)

- Citation path: NO caching/fuzzy matching, ever.
- **Single-brain mode locally** — never create new local brains (the
  embedded graph is single-tenant; new brains pollute the demo graph).
- No new dependencies without Ayush's explicit approval (PyMuPDF and the
  Langfuse compose service were both approved tonight).
- Nothing irreversible (deletes/re-ingest/force-push/key rotation) without
  Ayush. Secrets only in `.env` / `.env.oss` (gitignored).
- Demo brain `company_brain` is **creator-owned** by Ayush's Clerk user
  (`user_3JvGjL6x2VWrmAa0IYcvdckHbMv`) — warmup/tests must run as him
  (sign-in-token → ticket-strategy recipe in DEMO_DAY.md §2).
- The AI-team scaffolding (AI_TASKS/AI_RESULTS/AI_STATE/AI_TEAMUP/
  MUSE_PROMPT) was **deleted at Ayush's request** — ZCode builds solo now.

## 5. After P5 — the roadmap (locked order)

- **Finish P5:** Langfuse live (above) + model-routing formalization (route
  labels already flow into traces; remaining: route→model mapping — smalltalk
  → no retrieval ✓ done; factual → DeepSeek V4.1 Flash; premium → BYOK later).
- **P6:** Pydantic AI agents (email-composition agent with typed outputs
  citing exact sources; per-answer action buttons; usage limits from Langfuse
  data) + MCP connectors (Slack first, then Google) with approval gates.
- **P7:** launch — pricing enforcement (fair-use caps measured via Langfuse),
  onboarding, AGPL packaging.
- **P4 (parallel, any time):** hosting decision is Ayush's open call —
  committed `render.yaml` blueprint vs PLAN.md's locked Heroku (Student Pack
  $13/mo credit; Heroku dynos CANNOT host the Cognee brain — that goes to
  Cognee Cloud pilot or Hetzner CX22). Vercel was analyzed tonight (see
  `DEPLOY_VERCEL.md`): only viable as web-tier + Cloud-tenant brain + Pro
  plan (Hobby's 10s timeout kills every ask; asks take 23–45s).
- Small threads: SEC-5 legacy NULL-org rows (owner call), old M4 TOCTOU,
  Q2 ~38s (accepted as the "deep question"), optional DeepSeek re-ingest to
  restore graph depth (93/161 now vs 246/587 pre-wipe).

## 6. Known-weak spots to watch (learned the hard way tonight)

- Compose file edits: the service block must stay under `services:` (an
  append once landed under `volumes:` — validate with
  `docker compose -f compose.oss.yml config --quiet` before `up`).
- `_classify` has THREE `import requests` sites (function-local pattern).
- The app must be restarted (kill by port) after editing app.py — the
  running process serves stale code otherwise.
- Langfuse v2 container + `depends_on` uses the SERVICE name (`postgres`),
  while `docker exec` uses the CONTAINER name (`kestrel-db`).
- Playwright browser sessions drop (`playwright-cli open <url>` to restart;
  re-sign-in as owner via the ticket recipe after a drop).

## 7. File map for this handoff

`ZCODE_HANDOFF.md` (this file — delete or archive once absorbed) ·
`CLAUDE_CONTEXT.md` (broader context incl. the ten traps) · `DEMO_DAY.md`
(morning runbook) · `observe.py` (the new bridge, uncommitted) · modified
and uncommitted: `app.py`, `orchestrator.py`, `summarizer.py`, `ocr.py`,
`compose.oss.yml` · `.env` (gitignored; has the LANGFUSE_* block).
