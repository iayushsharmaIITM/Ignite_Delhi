# Kestrel Company Brain — Full Stack Review Brief

**Purpose of this document.** The founder considers the brain-creation flow
("brain making") the least professional part of this product and wants a
third-party review of the entire stack. This file is written to be pasted,
whole, into a capable model (Claude Sonnet 5.5 / GPT 6.1) with **no repo
access** — every claim below is sourced from the code as of commit
`f0a644c` (2026-09-30). File and symbol names are given so a reviewer with
the repo can verify, but nothing here requires it.

**What we ask of you, the reviewer.** Read sections 1–4 for context, then
concentrate on §5 (the brain lifecycle — the acknowledged weak point), §6
(the issue inventory — please challenge, extend, and prioritize it), and §9
(the specific questions). Return: (a) severity-ranked findings with concrete
fixes, (b) anything we believe that is wrong, (c) the 3 changes with the
best professionalism-per-effort ratio. Be blunt. This is an internal review
document, not marketing.

---

## 1. What the product is

Kestrel is a company-knowledge workspace. A user organizes documents into
named collections called **brains**, asks questions in plain language, and
gets streamed answers with **citations** that resolve to the uploaded file
and a verbatim excerpt. Core user-visible flows: create a brain from files,
add files to it, chat with it, save chat history per brain, inspect cited
sources, explore a knowledge graph of the corpus.

Stage: **local development / private beta tooling**. Nothing is deployed.
One Clerk dev instance, one local Docker stack, one demo corpus of synthetic
documents (`corpus/01–10`, e.g. `01_contract_MSA-2025-0114_bluepeak.md`).

Hard product rules the founder has locked (challenging them is welcome):
1. Every answer must carry checkable citations; a citation you cannot open
   is an assertion, so `/api/source` returns the raw document text.
2. The citation→source path must never guess ("fuzzy-match" is banned
   language) — see §5.6 and the tension noted there.
3. The demo brain (`company_brain`) must never be destructible by normal
   API calls.
4. No secrets in code; env files only.

## 2. Architecture at a glance

```
Browser (two frontends, both live)
  ├─ static/index.html      legacy single-file HTML/JS shell (fallback UI)
  └─ frontend/              Vite + React 19 + Tailwind v4 + shadcn/ui
        │  fetch /api/* (dev proxy :5173 → :8000)
        ▼
FastAPI app tier (app.py, 1761 lines, runs on host: python app.py, port 8000)
  ├─ auth.py        Clerk session-JWT verification (JWKS, fail-closed)
  ├─ tenants.py     legacy X-API-Key multi-tenant mode (still supported)
  ├─ memory_layer.py  PROVIDER=mock|cloud switch; demo safety net
  ├─ orchestrator.py  per-ask head agent: router + hedged retrieval + prewarm
  ├─ cognee_cloud.py  THE ONLY client that talks to the graph tier (requests)
  ├─ citations.py     citation → (real filename, verbatim excerpt) resolver
  ├─ documents.py     pypdf / python-docx / text extraction
  ├─ ocr.py           stage-2 OCR for scanned PDFs (PyMuPDF + vision model)
  ├─ connectors.py    OAuth vault + Slack scope-picker connector
  ├─ agents.py        pydantic-ai draft/send actions (email/Slack)
  ├─ observe.py       Langfuse trace bridge (fail-open)
  ├─ llm.py           shared LLM endpoint resolution (Token Harbor → OpenRouter)
  └─ storage.py       Postgres: chats, turns, brain_access, llm_calls
        │                                  │
        ▼                                  ▼
Cognee OSS 1.6.1 container (:8888)   Postgres 17 container (:5433)
  graph + vector store + chunking     app metadata + metering + connector vault
  (LanceDB + Kuzu inside the image)   (also hosts Langfuse's database)
        │
        └─ LLM calls from INSIDE the container: DeepSeek via LiteLLM
           (.env.oss block swap; two bind-mounted patches cap max tokens)

Optional/separate: pipeline.py (Render Workflows tasks — the original
cloud ingest tier, dormant while running the OSS stack locally).
Local Langfuse v2 container (:3000) for tracing.
Marketing site: marketing/ (static, Cloudflare Pages) — no backend coupling.
```

The one-sentence architecture: **the app tier owns all user state that the
graph tier won't keep (chats, ownership, citation manifest) in Postgres, and
talks to a Cognee tenant over HTTP for everything graph-shaped.**

## 3. The runtime stack, component by component

### 3.1 Graph tier — Cognee OSS 1.6.1 (`compose.oss.yml`, `cognee_cloud.py`)

**What it does.** Cognee ingests raw text into a knowledge graph: it chunks
the text, extracts entities/relations with an LLM, embeds chunks (vector
store), and stores a property graph. Retrieval strategies include
`GRAPH_COMPLETION` (multi-hop graph traversal + generation) and
`RAG_COMPLETION` (vector retrieval + generation); both return an answer plus
trailing "Evidence:" lines naming the `data_id`/`chunk_id` that grounded it.

**How it runs here.** Docker image `cognee/cognee:1.6.1` pinned exactly
(upstream ships breaking releases ~monthly), port 8888 on the host. Embedded
stores live in named volumes (`/app/.cognee`, `/cognee-storage`) — a partial
volume mount once wiped the demo graph on recreation (2026-09-28), so both
paths are mounted now. The container's LLM is configured by **block-swapped
env in `.env.oss`** (LiteLLM underneath): the active block is DeepSeek;
dormant blocks exist for Ollama, Cerebras, Groq, OpenRouter.

**Logic behind key decisions.**
- *Why a server, not the local SDK:* the original cloud tier ran in Render
  Workflow task containers, which are **ephemeral** — a file-based graph died
  with the run. A tenant service that owns the graph is the fix; the app tier
  then holds no graph credentials beyond one API key.
- *Why `cognee_cloud.py` is hand-rolled `requests`:* deliberately
  dependency-light; four endpoints (remember, status, recall, graph) cover
  everything. The file documents four expensive traps: (1) id-taking
  endpoints want UUIDs, never names → `resolve_id()`; (2) the terminal
  pipeline state is the exact string `DATASET_PROCESSING_COMPLETED` →
  `terminal_kind()`; (3) querying a mid-ingest dataset returns confident
  wrong answers (measured: invented "$39/year" for a $420,000 contract) →
  `wait_ready()`; (4) env must be read lazily (dotenv-after-import silently
  empties config).
- *Why bind-mounted patches:* LiteLLM injects the model's advertised
  `max_tokens` (131072) into requests; against a near-empty OpenRouter
  balance this 402'd every call. `patches/native_adapter.py` and
  `patches/stream_completion.py` (mounted read-only into the image) cap
  `max_completion_tokens` at the configured value (`LLM_MAX_COMPLETION_TOKENS=4000`).

**Current state / honesty.** Works for the demo corpus and manual uploads.
Not professional about: the two patches fork upstream behavior and will
silently break or be lost on image upgrade; the OSS container runs with
**authentication disabled** on loopback (any local process can read, ingest,
or delete any dataset — fine on a laptop, disqualifying for a shared host);
one shared tenant means **one flat dataset namespace for all brains of all
orgs** (see §5.2, the core brain-making weakness).

### 3.2 Web tier — FastAPI (`app.py` + modules)

**What it does.** Serves the two frontends as static pages, the REST API,
and two NDJSON streaming endpoints (`/api/ask`, `/api/brains/{name}/events`).
All authorization funnels through two functions: `require_tenant()`
(authentication) and `require_dataset_access()` → `brain_allowed()`
(authorization; §5.4). Rate limiting is per identity per route bucket
(`_check_rate`). Streaming is newline-delimited JSON over
`StreamingResponse` — chosen over SSE to reuse one proven shape.

**Logic behind decisions.** The file is heavily annotated with issue IDs
(SEC-*, H*, S*, COR-*, O*, LOW-*) from four security/robustness passes —
e.g. SEC-1 (normalize the name BEFORE authorizing it, so a case variant
can't bypass a lookup), COR-11 (every blocking parse/OCR runs in a worker
thread or a slow PDF stalls the event loop and trips the Render liveness
probe). The battery (`verify.sh`) runs the app with `PROVIDER=mock,
AUTH_MODE=off` so tests never need the tenant.

**Current state.** Works, tested (§8). Not professional about: it's one
1761-line module for ~40 routes + pages; no CI (tests run locally only);
no request logging/middleware layer to speak of; NDJSON streaming is
nonstandard (fine, but reviewers should know); no HTTPS story of its own.

### 3.3 Metadata tier — Postgres 17 (`storage.py`, compose `kestrel-db`)

**Tables.** `chats` (id, brain, org_id, created_by, title, timestamps),
`turns` (per-chat ordered messages with JSONB sources/attachments),
`brain_access` (brain → org_id, created_by, is_shared — the ownership
registry, §5.4), `llm_calls` (per-ask metering, chars/4 token estimates,
180-day retention), `connector_credentials` (Fernet-encrypted OAuth
grants), `slack_workspaces` (per-workspace Slack grants, owner_key + team_id).

**Logic.** Postgres is the **durable app-side truth** precisely because the
graph tier keeps none of it: the tenant stores document *content* but not
the filenames users chose, not ownership, not chat history. `upsert_chat`
rewrites turns in ONE transaction and server-stamps ownership (a client can
neither omit nor self-declare org). The module convention is
never-raise-degrade (a DB outage degrades features, not the process) — with
deliberate exceptions where a failure must propagate (chat rewrite rollback).

**Not professional about:** migrations are idempotent `CREATE TABLE IF NOT
EXISTS / ALTER ... ADD COLUMN IF NOT EXISTS` inside `init()` — no migration
tool, no versioning; the demo fallback dataset string is duplicated between
`storage._demo()` and `app.DEMO_DATASET` with a comment admitting one
import direction is forbidden; `brain_access` has no FK to anything (by
design — it must outlive the graph tier's answer about existence, see
SEC-9), which is a consistency risk.

### 3.4 Identity — Clerk (`auth.py`, dev instance `ample-skink-6708`)

**What it does.** `AUTH_MODE=clerk`: every request must carry a Clerk
session JWT; verified against Clerk's published JWKS (RS256, issuer pinned,
10s leeway, expiry required, algorithm never taken from the token header).
Identity = `{user_id, org_id}` from Clerk's org claims (three known shapes
accepted). JWKS cached 10 min; infrastructure failure fails closed.
`AUTH_MODE=off` = single local user (legacy open behavior).

**Logic.** Fail-closed everywhere, including Postgres-outage → 403 rather
than fail-open (SEC-2). The verification seam is injectable so tests sign
tokens with a local RSA keypair.

**Not professional about:** org claim parsing accepts three shapes (Clerk's
templating variance) — pragmatic, but it's a compatibility shim, not a
contract; no token rotation testing in prod-like conditions; the Clerk
instance is a dev instance ("My Application" display name still unset).

### 3.5 Generation — DeepSeek-only, two call paths (`llm.py`, `.env.oss`)

**What it does.** After a founder decision, gpt-oss-120b was routed out
entirely; DeepSeek v4.1 Flash is the only model. Two independent paths:
1. **App tier** (router, smalltalk direct-chat, OCR, agents): `llm.py`
   resolves ONE (base_url, api_key, model) triple — **Token Harbor first**
   (`https://tokenharbor.ai/v1`, model `deepseek-v4.1-flash:free`),
   **OpenRouter fallback** (`deepseek/deepseek-v4.1-flash`).
2. **Container tier** (Cognee's internal chunking/extraction/generation):
   the `.env.oss` active block, currently DeepSeek via an OpenAI-compatible
   endpoint, with `LLM_MAX_COMPLETION_TOKENS=4000` and the bind-mounted
   patches capping pre-authorization (OpenRouter 402s on a negative balance
   if LiteLLM requests the model's advertised 131k output).

**Logic.** One resolver file so five call sites don't drift; per-site model
overrides still honored. 402 is treated as terminal (billing), not retried;
429/5xx retried with backoff.

**Not professional about:** `llm.py` points Token Harbor at the **`:free`**
variant — a leftover; quality/rate-limit behavior of `:free` was exactly
what we routed away from on OpenRouter, and nobody reconciled this line;
the container and app tier can silently run **different models** if one env
block drifts (dotenv last-wins already bit us once — the `.env.oss`
accumulated duplicate LLM blocks and the last one won); there is no model
identity surfaced to the user or in traces beyond Langfuse metadata.

### 3.6 Extraction & OCR (`documents.py`, `ocr.py`)

**What it does.** Stage 1: pypdf (PDF text layer), python-docx (paragraphs
AND tables), plain text/MD/CSV/JSON/code — caps 40 files × 5 MB per upload.
Stage 2: if a PDF has NO text layer, PyMuPDF renders pages locally at 110
DPI (free) and ONE vision-model call reads up to 10 pages / 3 MB; blank
pages get an honest 400, never invented text. Stage 3 for chat attachments
only: `/api/extract` returns text so the CURRENT answer can use it, while
`POST /api/brains` ingest makes files answerable in FUTURE asks.

**Logic.** No system OCR binaries (tesseract) — a vision call reuses the
existing key and behaves identically on any host. All extraction runs in
worker threads (event-loop hygiene). Limits exist because extraction and
OCR cost embedding + LLM tokens; they're bounded per caller like asks.

### 3.7 Citations (`citations.py`) — the trust mechanism

**What it does.** Cognee's evidence names opaque ids:
`chunk 1 of document text_cfa9794… (data_id: …)`. For each dataset the
module builds a map from those ids to `{source filename, verbatim excerpt}`:
- Demo brain: corpus files on disk are fingerprinted (whitespace-insensitive
  120-char prefix, lowercased) and matched by CONTENT, because the tenant
  never stored our filenames — content is the only reliable join key, and a
  failed match returns nothing rather than a guess.
- Uploaded brains: `record_upload` fingerprints each successfully ingested
  file at upload time into `cognee_oss_state/uploads.json` (gitignored
  after a key fragment was once committed to it).
- Caches: a resolved-map cache with 300 s TTL, an in-memory `data_id →
  {source, excerpt}` cache, and dataset-item caches; prewarmed during the
  ask (orchestrator) so resolution is instant after the answer.
- The authoritative rule: if the fingerprints don't match, return NOTHING —
  never guess a source.

**Not professional about / reviewer attention:** the entire citation join
for user uploads lives in a **local JSON file on the app host**, not
Postgres — a rebuilt container, a second instance, or a lost volume silently
turns every uploaded brain's citations into "unresolvable" (the graph is
fine; the *proof* is gone). The in-memory id-cache is per-process. And note
the tension with the locked rule in §1: the code *does* cache maps and
fingerprint-match content — the rule, as implemented, means "never fabricate
a citation; match by content, cache only warm lookups." If that's not what
the rule should mean, say so.

### 3.8 Observability — Langfuse v2 local (`observe.py`, compose)

Per-route traces (smalltalk / chat / brain) with per-generation token
estimates, feature labels, and Slack-post traces. Fail-open bridge: no keys
→ no-op. Local container, Postgres-only flavor, seeded with project keys.
**State:** working locally; nothing exported; not wired into any alerting.

### 3.9 Connectors — Slack scope-picker (`connectors.py`, 90/90 tests)

OAuth code flow with a server-side single-use `state` binding identity +
scope choice; Fernet-encrypted grants in Postgres; the "Configure access"
dialog maps to scope sets (read_post / read × private channels); per-workspace
grants (`slack_workspaces`), honest 403 if a read-only grant tries to post,
cursor-paginated history, revoke-on-disconnect. Error surfaces are human
sentences ("invite the bot to the channel"). **State:** fully built and
tested with stubbed Slack; **not live** — no Slack app registered yet
(owner-blocked: needs SLACK_CLIENT_ID/SECRET). Gmail/Drive: OAuth start
exists; sync workers don't.

### 3.10 Frontends

- `static/index.html` — legacy single-file shell (~1400 lines). The
  complete app (auth gate, work log, attachments, brains pages). Kept as
  fallback; the API is shared.
- `frontend/` — Vite + React 19 + Tailwind v4 + shadcn/ui port with the
  design tokens in `DESIGN.md`; streaming reader, citations panel,
  Connectors view + Slack dialog, Clerk theming. Lighthouse a11y 100.
  **State:** chat history in the new UI is still localStorage-only (the
  legacy shell owns the Postgres-backed history UX); extraction wiring exists
  but brain upload from the new UI is a thin redirect to legacy pages.

### 3.11 Ops

Local: colima + `compose.oss.yml` (cognee-oss, postgres, langfuse), a
LaunchAgent (`com.kestrel.stackup`) that self-heals the stack at login, and
`ops_stack_up.sh`. Verification is `./verify.sh` (mock provider, auth off)
plus targeted suites. **No CI, no deployment target** — the Render cloud
tier (`pipeline.py`, Render Workflows) is dormant code kept for the
architecture rationale, not currently exercised.

## 4. Request flows you should know before reviewing brains

**Ask** (`POST /api/ask?q&dataset&tz&local_time&context`):
1. `require_dataset_access` (identity → brain_allowed, fail-closed).
2. Smalltalk classifier (regex/keyword): greetings skip retrieval entirely —
   one direct DeepSeek call, and saved smalltalk turns are stripped of
   citations authoritatively on write (`storage.upsert_chat`).
3. Otherwise the orchestrator: a **router** sub-agent classifies
   BRAIN/CHAT concurrently with a **hedged retrieval** — GRAPH_COMPLETION
   starts immediately; RAG_COMPLETION starts only if GRAPH is slow past
   `KESTREL_HEDGE_SECONDS` (8) or fails. (An earlier true race ran both
   always — cancelling a `to_thread` await never stops the worker thread,
   so it paid 2× tokens on every ask; the hedge is the cost compromise.)
4. Citations prewarm overlaps retrieval; the answer streams as
   `{"type":"chunk"}` events; then `{"type":"references"}` carries resolved
   `{source, excerpt}` items; per-ask metering lands in `llm_calls`.
5. Chat persistence: server-stamped ownership, smalltalk strip, transaction.

**Ingestion progress** (`GET /api/brains/{name}/events`): polls the tenant
status endpoint every 3 s (clamped 10–900 s) and streams real pipeline
states; terminal FAILURE is reported as failure (an earlier version told
users a failed ingest was "ready").

## 5. The brain lifecycle — the part we consider unprofessional

### 5.1 What a brain actually IS (three records in three places)

Creating a brain touches **three systems with no cross-system identity**:

| System | Record | Survives container rebuild? |
|---|---|---|
| Cognee tenant | a **dataset** (name = normalized brain name, UUID id) | yes |
| Postgres `brain_access` | ownership row (org_id, created_by, is_shared) | yes |
| App host disk | `cognee_oss_state/uploads.json` manifest (fingerprint → filename) | **NO** |

There is no brain ID. The normalized dataset name IS the primary key
everywhere. The UUID exists only inside Cognee and must be resolved by name
on every use (`resolve_id` scans the dataset list).

### 5.2 The core weakness: a flat, global dataset namespace

`POST /api/brains` normalizes the user's name (`normalize_brain_name`:
lowercase, `_`-fold, 3–40 chars `[a-z0-9_]`) and checks existence **against
the one shared tenant** (`cognee_cloud.exists`). Consequences we know of:

1. **Name collisions across orgs are structural.** If Org A creates
   `sales`, Org B cannot. There is no per-org prefixing/namespacing because
   Cognee datasets are flat and the app chose names as keys.
2. **The 403/409 split is a membership oracle.** B creating `sales` gets
   `409` only if B may see it; otherwise `require_dataset_access` 403s with
   "This brain belongs to another workspace" — either way the caller learns
   the name exists. Brain names leak as an enumeration oracle.
3. **Global uniqueness of short human names** (`acme`, `sales`, `hr`) is a
   product-logic landmine even within one org.

### 5.3 Creation semantics (`create_brain`, ~130 annotated lines)

Flow: provider gate (mock refuses) → normalize/validate → reserved names →
authenticate → global `exists()` probe (fail-closed 503 if tenant down) →
if exists: owner-gate + 409 unless `append=true` → rate limit → read files
(capped) → extract in a worker thread → **parallel `remember()` per
document** (`asyncio.gather`, each a fire-and-forget background pipeline on
the tenant) → if NOTHING ingested: 502 and no brain is registered →
ownership row registered only after ≥1 success (SEC-9, `ON CONFLICT DO
NOTHING`) → citation manifest recorded for exactly the landed docs (H2:
failed docs must never enter the manifest — a brain citing a file that
isn't in its graph is the one thing this product must never do) → response
distinguishes `appended` vs created, `partial` with per-file results.

**The 409/append rule** is deliberate product logic: silently merging into
a brain the user believes is new would produce answers from documents they
never saw; `append=true` is the explicit opt-in.

**What is unprofessional here (beyond §5.2):**
- **Non-atomic, non-idempotent, partially observable.** A 6-file create can
  land 4 docs and return `partial:true` — the brain exists forever in that
  half-built state, with no retry, no reconciliation, no way to know WHICH
  parts are weak beyond per-file `ingested[]`. No rollback option.
- **Concurrency races.** Two simultaneous creates of the same name both pass
  `exists()=false` (no unique-anything at the tenant) and both ingest; the
  Postgres row resolves to whoever registered first. No lock, no CAS.
- **Progress is dataset-level, not document-level.** `/events` polls the
  dataset status; N parallel background pipelines inside Cognee are not
  individually observable from here. The user sees coarse states, and the
  stream gives up at 900 s even though ingest may still complete — after
  which the UI has no way to discover the outcome except re-listing brains.
- **No validation feedback loop.** Extraction failures are surfaced, but
  *ingestion* failures inside Cognee come back as short error strings
  truncated to 200 chars; there's no retry, no DLQ, no diagnostic artifact.
- **No dedup/versioning.** Uploading the same file twice ingests it twice
  (whether Cognee dedups identical content is unknown to us — reviewer
  question). There's no document list per brain exposed to the user
  (`data_items` is used internally, never shown), so users can't see or
  remove what's inside.
- **Deletion is name-addressed and double-guarded** (route RESERVED_NAMES +
  client `_PROTECTED_DATASETS`), releases the ownership row (S2) — but
  **chats referencing a deleted brain are not handled** (they keep
  `brain=<name>` and will query a nonexistent dataset), and the citation
  manifest/`uploads.json` entries for that brain are not cleaned up.
- **Ownership rows for out-of-band brains don't exist.** Any dataset created
  outside `POST /api/brains` (e.g. `ingest.py` scripts, ops `curl`) has no
  `brain_access` row and is therefore **403 "Unknown brain" for everyone**
  in Clerk mode (fail-closed SEC-2). The demo brain works only because a
  creator-owned row was inserted manually. There is no sync/reconciliation
  between the tenant's dataset list and the ownership table.
- **The `demo` alias.** The UI key is `demo`, the dataset is
  `company_brain`; `safe_dataset()` maps the alias at every edge. It's
  documented and centralized, but it's a hack that exists because ownership
  rows are name-keyed and a row named "demo" could collide with a real
  user brain.
- **`is_shared` exists in the schema and nowhere else** — sharing is
  modeled but has no API, no UI, no tests. Dead product surface.
- **The manifest will outlive or underlive the graph.** `uploads.json`
  entries are never removed on brain delete, and (above) don't survive
  host rebuilds. Postgres would fix both; it was kept on disk because the
  manifest is "local operational state" after a secret-leak incident —
  the incident response (move out of git) and the design decision (don't
  move to the DB that exists for exactly this) should be revisited.

### 5.4 Authorization model for brains (`brain_allowed`)

Read rule, enforced for every brain-scoped route by one funnel:
**shared brains** → any authenticated identity; **org-owned** → same
org_id; **org-less** → the creating user only; **no row** → 403 fail-closed
(including during a Postgres outage, and including the demo — which instead
holds a real creator-owned row). Chats have their own parallel ownership
stamp on `chats` (first-stamp-wins for legacy NULL rows; overwrite refused
otherwise). Create stamps ownership after success (SEC-9 — before that,
failed creates left stale rows and ON CONFLICT credited other orgs'
creates to them). Delete releases the row (S2) after the dataset is gone.

**Unprofessional about:** the model is brain-level only — no per-user
read/write split, no roles, no invite flow; and the "no row = 403" rule
makes out-of-band ingestion land as broken (§5.3).

### 5.5 Numbers and limits (as implemented)

3–40 char names `[a-z0-9_]`; ≤40 files × 5 MB per upload; OCR ≤10 pages /
3 MB per PDF; events poll 10–900 s; ingest `wait_ready` 900 s default;
recall timeout 600 s (COGNEE_TIMEOUT); 3 retry attempts on 429/5xx;
chat history LIMIT 50; metering 180-day retention; ask rate-limit buckets
per identity per route ("ask", "upload", "events").

### 5.6 The locked rules, restated as implemented

1. **Citations must resolve to real files + verbatim excerpts** — yes:
   `/api/source` re-reads corpus or tenant raw text; unmatched → nothing.
2. **Never guess on the citation path** — implemented as: content
   fingerprint matching (whitespace-insensitive 120-char prefix) + cached
   warm maps (TTL 300 s) + persistent id-cache in memory. If reviewers read
   the locked rule as "no caching, no fuzzy matching at all," the current
   implementation violates it; the founder's intent was "never fabricate or
   approximate a citation." Reconcile this wording for us.
3. **Demo brain indestructible** — route guard + client guard + protected
   in `cognee_cloud.delete_dataset`; the UI also hides the button (three
   layers; the API is the boundary).

## 6. Consolidated issue inventory (challenge/extend this)

Severity is our guess; please re-rank.

| # | Issue | Sev | Where |
|---|---|---|---|
| 1 | Citation join for uploads lives on app-host disk (`uploads.json`), not Postgres → citations silently die on rebuild/second instance; also never cleaned on brain delete | High | citations.py:46–58, app.py:1493–1504 |
| 2 | Flat global dataset namespace: cross-org name collisions + 403/409 existence oracle; names are the only key, no brain ID | High | app.py:1336–1421, cognee_cloud.py |
| 3 | No reconciliation between tenant datasets and `brain_access` rows: script-created brains are 403-dead in Clerk mode; deleted-out-of-band datasets leave zombie rows | High | storage.py:336–372, app.py:212–236 |
| 4 | Create is non-atomic/non-idempotent: partial brains persist, concurrent same-name creates both ingest, no lock | High | app.py:1451–1487 |
| 5 | Ingestion observability is dataset-level polling with a 900 s ceiling; no per-document progress, no post-timeout outcome discovery | Med | app.py:1521–1581 |
| 6 | `llm.py` Token Harbor model is the `:free` variant; container vs app-tier model identity can drift silently (dotenv last-wins already bit once) | Med | llm.py:16, .env.oss |
| 7 | Two bind-mounted patches fork Cognee 1.6.1 behavior; image is pinned but an upgrade loses them silently | Med | compose.oss.yml, patches/ |
| 8 | OSS container auth-off on loopback; one shared tenant = all orgs' content in one store with one API key | Med (prod blocker) | compose.oss.yml, .env.oss |
| 9 | Migrations = idempotent init(); no schema versioning tool | Med | storage.py:70–140 |
| 10 | New-UI brain creation redirects to legacy pages; new-UI chat history is localStorage; two frontends diverge | Med | frontend/src/App.tsx |
| 11 | No document inventory/deletion per brain for users; no dedup/versioning on re-upload | Med | (missing feature) |
| 12 | Chats referencing a deleted brain unhandled; `is_shared` dead schema | Low | app.py:1584–1638, storage.py:99 |
| 13 | No CI; verify.sh is manual; no staging/prod deployment at all | Med | repo |
| 14 | `cognee_cloud.exists()` on the create path adds a tenant round trip that is also the existence oracle; fail-closed 503 is right, the oracle is not | Low | app.py:1389–1402 |
| 15 | Clerk org-claim parsing accepts 3 shapes; Clerk instance still dev-named | Low | auth.py:117–127 |

## 7. What we are deliberately NOT building (scope fence)

No per-user vector stores; no multi-tenant Cognee (one tenant, one key);
no custom chunking (Cognee defaults); no streaming token-level citations;
no real-time collaboration; no public sign-up (invite-based early access);
no self-hosted OCR binaries. Challenge if you think any of these fences is
what's making the product feel unprofessional.

## 8. Verification that exists today

`./verify.sh` = full battery with `PROVIDER=mock AUTH_MODE=off` (never
touches the tenant): `battery.py` (end-to-end via the app), `contract_test.py`
(API contract), `test_pipeline_states.py` (13 pipeline-state checks),
`test_tenants.py` (10 authz checks), `connectors_test.py` +
`slack_scopes_test.py` (10 checks; connectors currently 90/90 across
suites), plus `check_ui.py` (browser smoke). Everything runs locally; a
human runs it; nothing runs on push.

## 9. Specific questions for the reviewers

1. **Brain identity.** Should we introduce a real brain ID (UUID) at the
   app tier, keep names as display handles, and namespace tenant datasets
   (e.g. `org<id>__<slug>`) to kill collisions and the oracle — or is the
   cleaner move a separate store (Postgres) as source of truth with
   datasets as opaque storage? What breaks first?
2. **Citation durability.** Move `uploads.json` into Postgres (table keyed
   by dataset name + content fingerprint)? Any reason the current design is
   better than it looks? What's the migration path for existing brains?
3. **Atomicity.** For create-with-N-files: saga with compensating delete?
   per-document job records with a finalizing state machine? Or accept
   partial brains but expose per-document state to the user? Concrete
   recommendation, given Cognee's API only exposes dataset-level status.
4. **Concurrency.** Is a Postgres advisory lock on the normalized name
   during create sufficient given the tenant has no unique constraint? What
   would you do about the double `exists()` race?
5. **Progress.** Job IDs + a `brain_jobs` table polled by the client, or
   keep dataset-status polling but add a timeout-safe "check later" flow?
   What's the minimum professional version?
6. **Model governance.** How do we stop container vs app-tier model drift,
   and should `deepseek-v4.1-flash:free` on Token Harbor be replaced
   (quality vs cost, given ~1x hedge token spend per ask)?
7. **Cognee coupling.** Given the pinned image + bind-mounted patches +
   snake_case flavor switch: at what point is wrapping Cognee behind our own
   ingest service (Celery/Arq + direct LanceDB/Kuzu) cheaper than tracking
   upstream? Is the evidence-based citation dependency on Cognee's
   "Evidence:" text format a time bomb?
8. **The locked citation rule.** Restate it so an implementer can't misread
   it; audit our caches against your restatement.
9. **What else makes this feel unprofessional** that we haven't listed?
   Assume the founder will act on anything severity ≥ Medium.

## 10. Appendix

**API surface (auth-gated unless noted):** `GET /health` (public),
`POST/GET/DELETE /api/brains[...]`, `GET /api/brains/{name}/events`,
`GET /api/ask` (NDJSON stream), `GET /api/stats`, `GET /api/graph`,
`GET /api/usage`, `POST /api/upload`, `GET /api/source`,
`POST /api/actions/draft|send`, `POST /api/extract`,
`/api/connectors/*` (status, oauth start/callback, slack connect/
workspaces/channels/messages/post/disconnect, import, disconnect),
`/api/chats*`, page routes for the legacy UI.

**Env surface (names only — values are in gitignored .env/.env.oss):**
`PROVIDER, AUTH_MODE, CLERK_ISSUER, CLERK_SECRET_KEY, CLERK_JWKS_URL,
COGNEE_SERVICE_URL, COGNEE_API_KEY, COGNEE_DATASET, COGNEE_TIMEOUT,
COGNEE_FLAVOR, DATABASE_URL, TOKENHARBOR_API_KEY, OPENROUTER_API_KEY,
LLM_MAX_COMPLETION_TOKENS (container), KESTREL_RACE_RETRIEVAL,
KESTREL_HEDGE_SECONDS, KESTREL_OCR_MODELS, ROUTER_MODEL, SUMMARIZER_MODEL,
AGENT_MODEL, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST,
CONNECTOR_VAULT_KEY, SLACK_CLIENT_ID, SLACK_CLIENT_SECRET, APP_BASE_URL,
SMTP_*, RENDER_API_KEY (dormant tier)`.

**Repo map:** `app.py` (web tier), `cognee_cloud.py` (tenant client),
`memory_layer.py` (mock/cloud switch), `orchestrator.py` (ask pipeline),
`citations.py`, `documents.py`, `ocr.py`, `storage.py`, `auth.py`,
`tenants.py`, `connectors.py`, `agents.py`, `observe.py`, `llm.py`,
`pipeline.py` (dormant Render tier), `ingest.py` (script), `snapshot.py`,
`compose.oss.yml`, `patches/`, `static/` (legacy UI), `frontend/` (React),
`marketing/` (static site), `verify.sh` + test files, `DESIGN.md`,
`BUILD_PLAN.md` (build history M0–P7 with issue IDs), `corpus/` (synthetic
demo documents), `fixtures/answers.json` (offline demo answers).

**Test command:** `./verify.sh` (full battery), `./verify.sh --quick` (no
browser smoke). Current state: green as of 2026-09-30 (connectors 90/90,
pipeline states 13/13, tenants 10/10, UI smoke passing).
