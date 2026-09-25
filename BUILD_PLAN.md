# BUILD_PLAN — task-level execution plan for the OSS migration

**This is the execution companion to `IMPLEMENTATION_AND_POSITIONING.md`** (the research).
That doc decided *what and why*; this doc decides *in what order, checked how, and what to
do when a check fails*. It is written to be executed by **GLM 5.3 Flash** (a fast, light
model) one task card at a time, under these rules — read §0–§3 before touching anything.

Two corrections to the research, found by reading the current code (do not "fix" these,
they are already fine):

1. `terminal_kind()` in `cognee_cloud.py:60` already treats both
   `DATASET_PROCESSING_FAILED` and `DATASET_PROCESSING_ERRORED` as failure, plus a
   keyword fallback on the status field. **No `_FAILED → _ERRORED` mapping work exists.**
   The only day-1 contract changes are the two recall field renames (task M0.4).
2. The frontend actions layer (email draft / next steps / chat update) is **client-side
   JS in `static/index.html`**, not LLM calls. Phase 4 (BYOK) moves *answer generation*
   only; the actions layer is untouched until Phase 8.

---

## 0. Global invariants — the NEVER list

These hold in every task, in every phase. Violating any one is a critical failure even
if the task's own checks pass.

| # | Invariant | Why |
|---|---|---|
| N1 | **Never ingest into, delete, or re-ingest the cloud demo dataset** (`company_brain`, `kestrel_full`, `default_dataset`). Scratch datasets only, always deleted in `finally`. | The 219/500 demo graph is the product's proof. It was polluted once already. |
| N2 | **Never break the offline mock path.** After every task: `PROVIDER=mock` still boots, `/health` reports `provider=mock`, `smoke.py` passes. | The demo-with-zero-setup is a stated reliability guarantee (README). |
| N3 | **Never commit secrets.** `.env` stays gitignored; new env files for local OSS (`compose.oss.yml`, `.env.oss`) must be gitignored too. Keys arrive as environment variables from the human, never typed into files that are tracked. | |
| N4 | **Pin exact versions.** The Cognee image is `cognee/cognee:1.6.1` — never `latest`, never a minor tag. Any dependency added to `requirements.txt` is pinned `==`. | Upstream ships ~2 releases/month with breaking changes. |
| N5 | **Never install the `cognee` Python SDK into `requirements.txt`.** The app talks HTTP only (see requirements.txt header for the reasoning). | |
| N6 | **No drive-by refactors.** Touch only the files a task card names. If you see something ugly adjacent to your change, note it in PROGRESS.md under "Observations" — do not fix it. | A flash executor's job is the specified delta, not taste. |
| N7 | **The regression battery (§2) must be green before any task is marked done.** "It works on my machine" without the battery is not done. | |
| N8 | **When a task card says STOP, stop.** Write the escalation (§3) and end. Do not improvise architecture, do not "try one more thing" a third time. | |

---

## 1. Task card format, and how to work through them

Every unit of work is a card:

```
M<phase>.<n>  <title>                        [NEEDS-HUMAN] if it requires a key/decision
Files:        exact paths the task may touch
Steps:        ordered, concrete, copy-pasteable
Check:        commands to run + expected output  ← all must pass
Done when:    one sentence
```

Rules of engagement:

- Work **strictly in card order** within a phase. Phases themselves are ordered by their
  gates (§7) — never start Phase N+1 work before Phase N's gate is recorded in PROGRESS.md.
- One card = one session-sized commit. Commit message format:
  `M0.3: add contract test replaying the v1.6.1 API surface`.
- Before starting a card, re-read its Files list; if the repo state no longer matches the
  card's assumption (e.g. the function it names was renamed), **STOP and escalate** rather
  than adapting silently.
- Cards marked **[NEEDS-HUMAN]** block on the human. Do the preparatory sub-steps, then
  write the escalation and stop at that card. Do not skip ahead past it.

---

## 2. The checking harness

### 2.1 Existing suites (run from repo root)

| Command | What it proves | Green means |
|---|---|---|
| `python3 test_documents.py` | 25 extraction cases incl. every refusal path | 25/25 PASS |
| `python3 -m pytest test_pipeline_states.py test_tenants.py -q` | terminal-state machine; tenant isolation | 13/13 + 10/10 |
| `python3 smoke.py` | web tier: health, graph, streamed answer w/ citations (mock or cloud) | 4/4 PASS |
| `python3 check_ui.py` | headless browser, all 4 pages, 16 controls, zero console errors | 16/16 PASS |

`check_ui.py` needs the app running (`python3 app.py`) in another terminal first.
`smoke.py` accepts `--base <url>` for a deployed target.

### 2.2 New: `verify.sh` (built in card M0.1) — the single battery entrypoint

```bash
./verify.sh            # everything above, in order, one line of output per suite
./verify.sh --quick    # skip check_ui.py (no browser in CI / headless boxes)
```

Exit code 0 = all green. **Every card's Check section ends with `./verify.sh --quick`;
every phase gate runs the full `./verify.sh`.** If `verify.sh` itself is broken, that is a
P1 escalation — the harness is the ground truth for everything after it.

### 2.3 New: `contract_test.py` (built in card M0.3) — replayed at every phase gate

Replays our full client surface against a Cognee endpoint (cloud tenant OR local OSS
container) and asserts shape, not just status codes. It must:
- use a **scratch dataset** with a unique name (`contract_<epoch>`), refuse to run if that
  name could collide with `COGNEE_DATASET`, and delete the scratch dataset in `finally`
  (mirror `wf_smoke.py`'s existing protections — read it first);
- assert: remember accepts our multipart fields; status returns a parseable per-dataset
  map; recall returns a list with `text`; graph returns `nodes`/`edges`; data items list
  returns ids; `/data/{id}/raw` returns text;
- **fail loudly on drift** (exit 1 with the field name that changed), because its whole
  job is to catch shape changes between Cognee versions before they reach the app.

---

## 3. The iteration protocol (what to do when a Check fails)

```
run Check ── pass ──→ mark card done in PROGRESS.md, commit
   │ fail
   ▼
diagnose: re-read the error, re-read the card, read the named file. Write a 2-4
sentence diagnosis in PROGRESS.md under the card's entry.
   │
   ▼
ONE fix attempt that stays inside the card's Files list.
   │
   ├─ Check passes → done (note what the fix was)
   └─ Check fails again → SECOND fix attempt ONLY if the diagnosis materially changed
        │
        ├─ passes → done
        └─ fails → STOP. Append to BLOCKERS.md:
                    ## M<phase>.<n> — <title> — <date>
                    <diagnosis> / <what was tried, both attempts> / <exact error output>
                   End the session there.
```

Hard limits, no exceptions: **two fix attempts maximum**, both confined to the card's
Files list. Anything that needs a third attempt, touches other files, changes an
interface another module imports, or questions a decision in the research doc — is an
escalation, not a fix. Escalations are success, not failure: a flash executor that stops
at its boundary is more valuable than one that improvises.

---

## 4. Progress tracking — PROGRESS.md and BLOCKERS.md

Create both at repo root in card M0.1. PROGRESS.md format (append-only, newest first):

```
## M0.3 — contract test — DONE 2026-09-26
Check output: <paste the one-line-per-suite verify.sh output>
Notes: <anything the next session must know>
Observations (not fixed, per N6): <optional>
```

States are exactly: `DONE`, `BLOCKED` (points at a BLOCKERS.md entry), `WAITING-HUMAN`
(card needs a key/decision), `SKIPPED` (only ever with a one-line reason + human
approval recorded). No other states. BLOCKERS.md holds escalations from §3.

---

## 5. The phases, as task cards

Scope note: Phases 0–2 are fully carded below (they are the near-term work and they
carry the technical risk). Phases 3–4 are carded at milestone level with entry criteria.
Phases 5–9 are stubs (§6) — they get their cards written **after** the Phase 2 gate
resolves the graph-store question, because that answer changes their shape.

### Environment reality (verified 25 Sept 2026)

Host: macOS (darwin 27, arm64), Python 3.13 (Cognee supports 3.10–3.14 — OK).
Docker presence: **unverified — M0.1 checks it first.**
Cloud tenant: currently live via `.env` (`PROVIDER=cloud`) — the app as shipped keeps
working throughout; every OSS step is additive (new env, new compose file), never a
rip-and-replace.

---

### PHASE 0 — contract test against OSS v1.6.1  *(no app behavior changes)*

**M0.1 — Verification harness + workspace files**  `[foundation — do this first]`
- Files: `verify.sh` (new), `PROGRESS.md` (new), `BLOCKERS.md` (new), `.gitignore` (append lines)
- Steps:
  1. `docker --version && docker compose version` — if either missing, that is not a
     blocker for THIS card; finish the card and record `WAITING-HUMAN: install Docker`
     against M0.2.
  2. Write `verify.sh` per §2.2: runs `test_documents.py`, pytest pair, `smoke.py`,
     and (unless `--quick`) `check_ui.py` after starting the server; prints one line per
     suite; `chmod +x`. It must set `PROVIDER=mock` explicitly so the battery never
     depends on the tenant being up.
  3. Create PROGRESS.md (§4 header) and BLOCKERS.md (empty).
  4. Append to `.gitignore`: `.env.oss`, `compose.oss.yml`, `cognee_oss_state/`.
- Check: `./verify.sh --quick` → 3 suite lines, all PASS, exit 0.
- Done when: the battery runs green from one command.

**M0.2 — Local OSS container, pinned, auth off, fixed JWT secret**
- Files: `compose.oss.yml` (new, gitignored — it will carry local secrets), `.env.oss.example` (new, tracked, no secrets)
- Steps:
  1. `docker pull cognee/cognee:1.6.1` (pin exact — N4).
  2. Write `compose.oss.yml`: one service, image pinned above, port `8888:8000` (8888 so
     it can never be confused with our app on 8000), env from `.env.oss`.
  3. Write `.env.oss.example` with the two auth-off vars BOTH set false
     (`ENABLE_BACKEND_ACCESS_CONTROL=false`, `REQUIRE_AUTHENTICATION=false` — one alone
     is not enough, verified in the research), plus a placeholder
     `FASTAPI_USERS_JWT_SECRET=change-me-locally` (random-per-process default since
     v1.6.0 would invalidate sessions on every restart).
  4. `cp .env.oss.example .env.oss`; `docker compose -f compose.oss.yml up -d`.
  5. `curl -s localhost:8888/health` → JSON with a healthy status.
- Check: health JSON responds; `docker compose -f compose.oss.yml ps` shows running.
- Done when: the pinned container answers /health locally.
  [NEEDS-HUMAN only if Docker is absent — see M0.1 step 1.]

**M0.3 — `contract_test.py`** 
- Files: `contract_test.py` (new)
- Steps:
  1. Read `wf_smoke.py` in full first — copy its scratch-dataset protections (unique
     name, collision refusal, `finally` deletion). Read `cognee_cloud.py` for the exact
     request shapes to replay.
  2. Implement §2.3. The script takes `--base <url>` (default reads `COGNEE_SERVICE_URL`)
     and `--flavor cloud|oss` (controls the two recall field names — see M0.4).
  3. Assertions are per §2.3 plus: recall response items are dicts containing `text`.
- Check: `python3 contract_test.py --base <cloud-tenant-url> --flavor cloud` → PASS
  (proves the harness itself against the known-good endpoint).
- Done when: green against the cloud tenant with zero demo-dataset writes (scratch only).

**M0.4 — Flavor switch for the two renamed recall fields**
- Files: `cognee_cloud.py` (recall body only)
- Steps:
  1. Add module-level `def flavor() -> str: return os.getenv("COGNEE_FLAVOR", "cloud")`.
  2. In `recall()`, build the two keys conditionally: cloud sends
     `searchType`/`includeReferences`; oss sends `search_type`/`include_references`.
     Everything else in the body is identical. Default stays `cloud` — the deployed app
     must behave byte-identically until we choose to cut over (N2 in spirit).
  3. Do NOT touch `terminal_kind` (see correction 1 at the top of this doc).
- Check: `python3 contract_test.py --base http://localhost:8888 --flavor oss` → PASS,
  after `COGNEE_FLAVOR=oss` is exported in the shell running it; then `./verify.sh --quick`
  (proves cloud default unchanged).
- Done when: both flavors pass their contract test and the battery is green.

**M0.5 — Record what OSS does with `filename`**  *(verification, likely zero code)*
- Files: `PROGRESS.md` (findings), optionally `citations.py` (only if a comment is warranted)
- Steps:
  1. In the M0.3 scratch dataset flow, `remember()` one small text WITH `filename=
     "probe_filename.md"`, then fetch `/datasets/{id}/data` and inspect the item's `name`.
  2. If OSS stores the real basename (the cloud tenant silently ignored it — see
     `cognee_cloud.py` remember() docstring): record **finding F1** "OSS respects
     filename" and note that `citations.py` upload-fingerprint matching becomes a
     fallback rather than the primary path in Phase 1. If it stores `text_<hash>`:
     record **finding F1-negative**; nothing changes.
- Check: finding recorded in PROGRESS.md under M0.5, with the raw item JSON pasted.
- Done when: the finding exists and is unambiguous.

**PHASE 0 GATE** — run full `./verify.sh` (not --quick); `contract_test.py` green on both
flavors; PROGRESS.md shows M0.1–M0.5 DONE. Record the gate in PROGRESS.md.

---

### PHASE 1 — local OSS parity: the demo brain on our own key

Entry: Phase 0 gate recorded.

**M1.1 — Inference keys for the OSS container**  **[NEEDS-HUMAN]**
- Files: `.env.oss` (local only)
- Steps: prepare `.env.oss.example` additions: `LLM_PROVIDER`/`LLM_MODEL`/`LLM_API_KEY`/
  `LLM_ENDPOINT` (Cerebras `https://api.cerebras.ai/v1` or Groq — both OpenAI-compatible,
  per research), `LLM_RATE_LIMIT_REQUESTS=5` (ingestion is per-chunk and token-heavy;
  Cerebras free is 5 RPM), and embeddings choice: Gemini (`gemini/gemini-embedding-001`,
  768 dims) or local fastembed (384 dims). **`EMBEDDING_DIMENSIONS` must match the model
  exactly** — mismatched dims fail inside the process or silently fall back to 3072
  (research: issues #4313/#4364/#3490).
- Then STOP: the human supplies the key(s). Record `WAITING-HUMAN`.
- Done when: `.env.oss` holds working keys the human confirms are theirs.

**M1.2 — Ingest the corpus into local OSS**
- Files: `ingest.py` (add `--base`/flavor pass-through if absent — check first; keep cloud default)
- Steps:
  1. Export `COGNEE_SERVICE_URL=http://localhost:8888`, `COGNEE_FLAVOR=oss`, and a
     **scratch `COGNEE_DATASET`** name — never the real one (N1 applies to local too, so
     a mistake can never propagate to a habit).
  2. `python3 ingest.py` (sequential; it is the safest path) against the scratch dataset.
  3. Poll status to terminal; expect **hours, not minutes** at 5 RPM on a free tier —
     run it in the background, log to a file.
  4. Then re-point at the real local demo dataset name and repeat once the scratch run
     is clean.
- Check: `python3 contract_test.py --base http://localhost:8888 --flavor oss` incl.
  recall against the ingested dataset returns a real answer with evidence.
- Done when: local OSS answers a demo question from the corpus.

**M1.3 — App parity against local OSS**
- Files: none (environment only)
- Steps: run `PROVIDER=cloud COGNEE_SERVICE_URL=http://localhost:8888 COGNEE_FLAVOR=oss
  python3 app.py`; open `/`, ask the four demo questions from `fixtures/answers.json`.
- Check: streamed answers render; Evidence panel resolves filenames via `citations.py`
  (uses finding F1 or fingerprints); clicking a source chip opens the passage.
- Done when: the shipped UI works end-to-end against local OSS.

**M1.4 — Measure, don't assume**
- Files: `PROGRESS.md`
- Steps: during a fresh ingest, capture `docker stats --no-stream` peak MEM; record
  first-boot time (migrations + model fetch) and cold first-recall latency. These numbers
  size the Phase 2/3 host choice (research assumes 4–8 GB; verify locally).
- Check: three numbers recorded under M1.4.
- Done when: sizing evidence exists in PROGRESS.md.

**PHASE 1 GATE** — full `./verify.sh` green with the app pointed at local OSS (mock
battery still green too); M1.4 numbers recorded. This is the "local parity" milestone:
**the product now runs with zero Cognee-Cloud dependency.**

---

### PHASE 2 — externalized state (survive the container dying)

Entry: Phase 1 gate. **This phase carries the plan's biggest technical unknown.**

**M2.1 — Neon Postgres**  **[NEEDS-HUMAN]** — human creates the free Neon project and
hands over a connection string; `.env.oss` gains `DB_PROVIDER=postgres`,
`VECTOR_DB_PROVIDER=pgvector`, and the connection vars per Cognee's env template.

**M2.2 — Graph store decision: the gate inside the phase**
- Steps, in order:
  1. Try `GRAPH_DATASET_DATABASE_HANDLER=postgres_graph_shared` on the **pinned image**,
     with a scratch dataset: ingest → recall → graph → kill container → restart →
     recall again. Docs still label Postgres-as-graph "demo, not production" — this test
     is exactly the research's "single most important thing to verify".
  2. If (and only if) that fails: fall back to Neo4j Aura Free **[NEEDS-HUMAN]** (the
     human creates the instance) with `GRAPH_DATABASE_PROVIDER=neo4j` + connection vars.
- Check: the kill/restart recall returns the same answer from the same dataset, and
  `contract_test.py --flavor oss` passes after the restart.
- Done when: **finding F2 recorded**: which graph store, with evidence. This decision
  changes Phase 3's shape (Aura Free adds a service; postgres-shared keeps it 2 services).

**M2.3 — Backup proof**
- Steps: `pg_dump` the Neon DB → drop the scratch dataset → restore → recall again.
- Check: recall survives restore. Record the dump/restore commands under M2.3.
- Done when: a documented, tested restore path exists.

**PHASE 2 GATE** — full `./verify.sh`; kill-container survival proven (M2.2); restore
proven (M2.3); F2 recorded. Milestone: **state lives outside the container.**

---

### PHASE 3 — hosted deploy (thin, ~$0–3/mo pilot)

Entry: Phase 2 gate + F2 known. Target stack per research: Render free (app tier — the
existing `ignite-web` service, env updated to the OSS URL + flavor) + Cloud Run
(`cognee/cognee:1.6.1`, `max-instances=1`, scale-to-zero) + Neon + graph store per F2.

Cards (to be expanded into full cards when the phase opens — expand using the same
discipline, do not skip card format):
- **M3.1** Cloud Run service, pinned image, `--max-instances 1` (background asyncio tasks
  are in-process and single-worker — research B.3), secrets via env, conformance:
  `contract_test.py --base <run-url> --flavor oss` from the laptop.
- **M3.2** Render app-tier cutover: point `ignite-web` env at the Run URL. Cold-start
  measurement: first `/health` + first recall after scale-to-zero (research expects
  auto-migrations + model fetch to dominate; M1.4 numbers predict it).
- **M3.3** Long-ingest safety: uploads must go background + status-poll (the app already
  streams `/api/brains/{name}/events` — verify it survives Cloud Run's request ceiling;
  `/api/ask` takes 16–31 s today, so confirm the Run timeout is set above it).
- **M3.4** Warm-up: adapt `warmup.py` into a scheduled ping if cold starts hurt
  (decide with numbers from M3.2, not by default).
- **Gate**: `python3 smoke.py --base <deployed-url>` 4/4 from cold start; demo answers
  within an acceptable cold-start budget recorded in PROGRESS.md.

---

### PHASE 4 — hybrid BYOK (the core architectural move)

Entry: Phase 3 gate. Principle from the research: Cognee's LLM config is process-global,
so **answer generation moves into our app tier using the user's key; ingestion/retrieval
stay on our free-tier key.** Server-proxy default (keys never in localStorage; per-key
rate caps possible). Client-side actions layer untouched (correction 2 up top).

- **M4.1** New `generation.py`: OpenAI-compatible chat-completions call, provider+key+model
  per request; takes retrieved context (from Cognee retrieval-only search types) and the
  question; returns the answer text. No Cognee SDK (N5). Pinned deps only (N4).
- **M4.2** `memory_layer._cloud` split: retrieval from Cognee (unchanged), then
  generation via `generation.py` when a user key is present; fall back to Cognee's
  GRAPH_COMPLETION when not (so the demo path and BYOK path coexist — N2 again).
- **M4.3** Settings UI (provider + key + model) on `/`; key held server-side in the
  session, never rendered back after save.
- **M4.4** Rate limiting per key (simple token bucket in the app tier is enough at
  pilot scale).
- **M4.5** Acceptance from the research: two users with different keys see their own
  provider billing; ingestion is unaffected. This is a manual two-browser test — write
  the steps into the card when expanded, and record results in PROGRESS.md.
- **Gate**: BYOK answer path green; demo path (no key) byte-identical behaviour; full
  battery green.

---

## 6. Phases 5–9 — stubs with entry criteria (cards written later, on evidence)

| Phase | One-liner | Entry criteria | Cards get written when |
|---|---|---|---|
| 5 | Adopt Cognee's built-in users/tenants/API-keys; retire `tenants.py`; adversarial isolation suite in CI | Phase 4 gate | Cognee auth is ON in a hosted env we control |
| 6 | Slack: Cognee OSS Slack integration; decide DIY history fetcher vs waiting on upstream PR #4951 | Phase 5 gate | tenancy adopted (tokens need a per-user home) |
| 7 | Google: Gmail + Drive via Cognee v1.6.1 connectors; BYO-client pattern (dodges CASA); test native Google formats explicitly | Phase 5 gate | same |
| 8 | Actions layer goes real: MCP tools (Slack/Google) for send-actions with approval gates; per-answer actions become LLM-assisted under the user's key | Phase 4+6/7 | connectors exist |
| 9 | Packaging: AGPL-3.0, docker-compose quickstart, pinned image, externalized secrets, contract-test CI against new Cognee tags | Phase 4 gate (can start early if idle) | any time after Phase 4 |

Phase 5's adversarial suite is non-negotiable before any real customer data: the
research cites a cross-tenant role-lookup exposure (#5035) fixed in v1.6.0 — assume
actively-hardened, not proven.

---

## 7. Gate table (the whole plan on one screen)

| Gate | Proof required | Unblocks |
|---|---|---|
| Phase 0 | `verify.sh` full green; contract test green on cloud **and** oss flavors; findings F1 recorded | Phase 1 |
| Phase 1 | Demo answers from local OSS through the shipped UI; M1.4 sizing numbers | Phase 2 |
| Phase 2 | Kill-container survival + pg_dump restore proven; **F2 graph-store decision recorded** | Phase 3, and card-writing for 5–9 |
| Phase 3 | `smoke.py --base <url>` 4/4 cold; cold-start budget recorded | Phase 4 |
| Phase 4 | BYOK billing isolation test passed; demo path unchanged | Phases 5–9 |

---

## 8. Human-input register (everything the executor must ask for, and where)

| Input | Needed at | Nature |
|---|---|---|
| Docker installed/running | M0.2 | local env |
| Cerebras or Groq API key (+ choice), embedding choice | M1.1 | free-tier key, decision |
| Neon project + connection string | M2.1 | account + key |
| Neo4j Aura Free instance (only if F2 goes that way) | M2.2 | account + key |
| Cloud Run deploy (gcloud project) | M3.1 | account + key |
| A second test user's provider key | M4.5 | for the billing-isolation test |

Anything else the executor cannot obtain from the repo, this doc, or the research doc
goes to BLOCKERS.md as an escalation — never a guess.
