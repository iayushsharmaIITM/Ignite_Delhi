# Improvement Brief — Kestrel Company Brain

**Audit only. No application code was changed by this review.**

| | |
|---|---|
| **Purpose** | A prioritised, implementable brief for another coding model (DeepSeek V4.1 Flash) |
| **Baseline audited** | `main` @ `6597341` — 22 commits, tree clean, 3,208 code lines |
| **Method** | Read the source, the corpus and the tests; re-ran the suites; verified every claim in `BUILD_REPORT.md` against the code. Nothing was deployed or written to the tenant. |
| **Scope rule** | Protect the working demo first. Every Tier 1–3 item must leave `219 nodes / 500 edges` intact. **No re-ingestion.** |

**Read §0 before doing anything.** The single most damaging thing in this project right now is not a bug — it is a claim that the corpus itself disproves. Fix that before writing feature code.

---

## 0. The headline: one claim is overstated, and a judge can disprove it in 60 seconds

`BUILD_REPORT.md` §2.4 and `REQUIREMENTS.md` §4 both claim the flagship multi-hop answer derives a conclusion that *"appears in none of the three documents individually"* and is *"unprovable by vector search."*

**That is not true of the current Chain A.** The chat thread already states the conclusion outright:

> `corpus/04_chat_bluepeak-renewal.md:18-20` — **Priya:** *"Our policy caps a straightforward P1 credit at 10% for a sub-120-minute event. **25% is well outside that.**"*
> `corpus/04_chat_bluepeak-renewal.md:26-29` — **Elena:** *"Anything over 20% needs CFO sign-off."*
> `corpus/04_chat_bluepeak-renewal.md:31-34` — **Nadia:** *">20% needs CFO approval, no exceptions."*

So a single document (`04_chat`) yields **both** the breach **and** the sign-off chain. A judge who opens the corpus — or a VP auditor who reads it — finds this. Being caught overstating the one claim the whole pitch rests on is far more damaging than the claim is valuable.

**This is fixable, and the fix is stronger than the original claim.** See Task 2.1 — the corpus contains a genuine cross-document conclusion that no single file states. Retire Chain A's framing, adopt the §5.2 breach.

**Two more claims that do not match the code** (both trivially checkable):

| Claim | Reality | Where |
|---|---|---|
| *"`smoke.py` asserts `auth: ok`"* | It asserts `auth != "failed"` — which **passes when the field is absent or `None`**. The assertion is weaker than advertised. | `smoke.py:43` |
| *"`service_credit_cap` connects the policy to its threshold"* | It connects `msa-2025-0114 → "30% annual service credit cap"` — a **contract** cap. The >20%→CFO relation is carried by `requires_approval`, which is a different edge. | `fixtures/graph.json` |

Verified edge endpoints:

```
service_credit_cap   msa-2025-0114              -> 30% annual service credit cap
requires_approval    credit value above 20%     -> cfo          ← this is the real chain
escalates_to         finance                    -> cfo
```

---

## 1. What is already strong — do not touch

Listing this so the implementing model does not "improve" things that are load-bearing.

| Strength | Why it must survive |
|---|---|
| **Fixture fallback scoped to the demo brain only** (`app.py:105-112`) | Serving the demo snapshot under a user's brain would fabricate a result. This is the single best engineering decision in the project. |
| **`409` on existing brain, never a silent merge** (`app.py:283-287`) | Prevents answers from documents the user never uploaded. |
| **Mock adapter refuses uploaded brains** (`memory_layer.py:89-98`) | The safety net is allowed to fail; it is not allowed to lie. |
| **Demo-dataset delete guard in `cognee_cloud.py`, not the route** (`cognee_cloud.py:199-202`) | Cannot be bypassed by a future caller. |
| **`extract_many` returns errors as data, never raises** (`documents.py:185-219`) | One bad file cannot lose the batch. |
| **Scanned-PDF empty-string detection** (`documents.py:101-106`) | Catches the silent-no-op that would otherwise report success. |
| **`[hidden] { display:none !important }`** (`static/upload.html`) | Kills a whole class of UI bug. |
| **Authenticated `/health` probe** (`app.py:144-149`) | The one check a judge looks at can actually fail. |
| **Markdown renderer, no CDN dependency** (`static/index.html:268-321`) | One fewer remote failure mode. |
| **All user-supplied strings via `textContent`** | XSS-safe; verified. Do not "simplify" to `innerHTML`. |

---

## 2. Tier 1 — defects that can lose the demo

Ordered by damage. Each has an acceptance test.

### 2.1 · CRITICAL · A failed ingestion is reported to the user as **success**

**Mechanism.** `cognee_cloud.py:53` defines `_TERMINAL = ("completed","success","errored","failed")` — terminal *and* failure states together. `is_terminal()` (`cognee_cloud.py:134-141`) returns `True` for both. `app.py:350-352` then emits `{"stage":"ready"}` for **any** terminal state, and `static/upload.html:302-304` maps `ready` to *"Pipeline complete."* plus an **"Open the dashboard"** link.

**Impact.** An ingestion that errored server-side is presented as a working brain. The user lands on a dashboard that will answer nothing. On stage this is unrecoverable.

**Fix.**
1. Add `terminal_kind(state) -> "success" | "failure" | None` in `cognee_cloud.py`, matching the **exact** `status` enum values (`DATASET_PROCESSING_COMPLETED` → success; `..._FAILED` / `..._ERRORED` → failure). Do not substring-match the whole JSON blob (see 2.6).
2. Keep `is_terminal()` as a thin wrapper over `terminal_kind()` so existing callers still work.
3. `app.py` emits `{"stage":"failed","detail":...}` on failure, `ready` only on success.
4. `upload.html` handles `failed` → `finish(false)`.

**Acceptance test.**
```
Stub cognee_cloud.status to return {"<uuid>": {"status": "DATASET_PROCESSING_FAILED"}}.
GET /api/brains/x/events
Assert: the stream contains stage "failed"; it NEVER contains stage "ready".
```

---

### 2.2 · HIGH · A batch where every document failed returns `200 {"ok": true}`

**Mechanism.** `app.py:301-317`. `ingest()` catches per-document exceptions and returns `ok:false` — correct, so one failure cannot abort the batch. But the response is unconditionally `"ok": True` (`app.py:311`) and `documents` is `sum(...)` (`app.py:313`). `chars` (`app.py:314`) sums **all** extracted documents including the failed ones, so it can be large while nothing was stored.

**Impact.** `upload.html:237-238` prints *"Brain "x" created with 0 document(s), 4,231 characters."* — a success message with a large number and zero content.

**Fix.** After `asyncio.gather`, if `documents == 0` raise `HTTPException(502, detail=<per-file reasons>)`. Otherwise set `"ok": documents == len(docs)` and add `"partial": documents < len(docs)` so the UI can say "3 of 5 documents ingested".

**Acceptance test.**
```
Monkeypatch memory_layer.remember to raise.
POST one valid .md file.
Assert: status >= 400, and the body does NOT contain "ok": true.
```

---

### 2.3 · HIGH · `DELETE /api/brains/default_dataset` deletes Cognee's internal dataset

**Mechanism.** `RESERVED_NAMES` (`app.py:56`) is enforced in `create_brain` (`app.py:273`) but **not** in `delete_brain` (`app.py:361-374`). `delete_dataset` (`cognee_cloud.py:199`) guards only `name == dataset()`, i.e. `company_brain`. So `default_dataset` — which the UI correctly hides a delete button for (`static/brains.html:137`) — is deletable over the API.

**Impact.** Data loss on a shared tenant, reachable by a single `curl`. Also a "Production standards" and "Reliability" problem in front of a judge.

**Fix.** Reject `RESERVED_NAMES` in `delete_brain` before calling the client, and re-assert it inside `cognee_cloud.delete_dataset` (the same defence-in-depth reasoning that put the demo guard there).

**Acceptance test.**
```
DELETE /api/brains/default_dataset  -> 400/403, dataset still present
DELETE /api/brains/company_brain    -> 400 (already passing — do not regress)
```

---

### 2.4 · HIGH · Upload is read fully into memory before any limit is checked, and parsing blocks the event loop

**Mechanism.** `app.py:289` does `await f.read()` for **every** file before anything validates size. `MAX_FILE_BYTES` / `MAX_FILES` are enforced inside `documents.extract` / `extract_many` (`documents.py:142-146`, `:195`) — i.e. **after** the bytes are resident. Then `app.py:293` calls `documents.extract_many(payload)` **synchronously inside `async def`**, so pypdf/docx parsing stalls the entire event loop, including `/health`.

**Impact.** A large upload OOMs the free-tier container. During a slow PDF parse, `/health` stops responding — and a Render health check that times out can restart the service mid-demo.

**Fix.**
1. Enforce a file-count cap and a per-file size cap **before/while** reading — read in chunks with a running total, abort at the cap, return `413`.
2. `docs, failures = await asyncio.to_thread(documents.extract_many, payload)`.

**Acceptance test.**
```
POST a 50 MB file  -> 413, process survives (no OOM).
Fire a slow PDF parse and GET /health concurrently -> /health responds < 1s.
```

---

### 2.5 · MEDIUM · The claimed Render Workflow path is not the path the product uses

**Mechanism.** `app.py:3-6` and `render.yaml:7-8` state *"web tier → triggers runs → Render Workflow (compute)"*. But `app.py:303` calls `memory_layer.remember` **directly**, and `app.py` never imports `render` or `pipeline`. So `pipeline.py`'s `Retry(max_retries=3)` and the fan-out (`pipeline.py:30-76`) **never apply to uploads**. A transient 502 from the tenant silently drops a document with no retry.

**Impact.** Two problems. (a) An integrity gap: if a judge asks *"walk me through the workflow tier,"* the honest answer is that it is not on the request path. (b) Reliability: uploads have no retry.

**Fix — pick one and be explicit.**
- **Option A (honest, cheap):** correct the docstring and the `render.yaml` comment to say the web tier talks to the tenant directly, and the workflow tier is the fan-out/ingest path used by `ingest.py`. Add retry/backoff to the web ingest path so the reliability claim is real.
- **Option B (stronger, more work):** route `POST /api/brains` ingestion through `ctx.run(ingest_document, ...)`. **Do not attempt this before judging** — it is a deployment-path change and the Render services have never been deployed (see 2.7).

**Recommendation: Option A now, Option B after the event.**

**Acceptance test.** Inject one 502 into `cognee_cloud.remember`; assert the document is retried and eventually succeeds, rather than being reported as a permanent skip.

---

### 2.6 · MEDIUM · `is_terminal` substring match can fire prematurely

**Mechanism.** `cognee_cloud.py:140-141` lowercases the **entire** JSON payload and substring-searches for `"success" / "failed" / "errored"`. Because `status()` requests `include_error_detail=true` (`cognee_cloud.py:248`), any error-detail text containing those words makes a **still-processing** dataset look terminal — and per 2.1 that is then reported as "ready".

**Fix.** Parse the `status` field and match exact enum values. Never substring-match a whole payload.

**Acceptance test.**
```
{"<uuid>": {"status": "DATASET_PROCESSING_STARTED",
            "error_detail": "previous run failed"}}
-> terminal_kind() is None (still running)
```

---

### 2.7 · MEDIUM · Nothing is deployed, and the deployment has never been exercised

`render.yaml` defines two services and **validates**, but per `BUILD_REPORT.md` §9.3 the services have never run on Render. Two concrete risks the config review surfaced:

- **Port binding.** Render requires binding to `0.0.0.0` on `$PORT`. `app.py:410-414` defaults `HOST` to `127.0.0.1`. It reads `HOST` from env, so it works **only if `HOST=0.0.0.0` is actually set on the service** — and `render.yaml:25-33` does **not** set it. **This will likely fail the first deploy.** Add `HOST=0.0.0.0` to the web service's `envVars`.
- **Free-tier cold starts.** A free web service sleeps; the first request after idle takes tens of seconds. Warm it before judging.

**Acceptance test.** Deploy, then `python smoke.py --base https://<app>.onrender.com` → 4/4 PASS.

---

## 3. Tier 2 — the differentiator: make the grounding *visible*

**This is the highest points-per-hour change available.** It converts Core Requirement 4 from an assertion into something a judge can see, and it turns the multi-hop claim from report prose into product output.

### The problem

Live citations are **opaque UUIDs**. Verified from a real run:

```
cites: 3 -> ['chunk 1 of document text_cfa979402db25ffb287',
             'chunk 1 of document text_2642a65cc1936ba3fa5',
             'chunk 1 of document text_33e5090c8eda2772cb1']
```

No filename. No excerpt. `cognee_cloud.py:326-347` parses the `Evidence:` block, and `cognee_cloud.py:308-323` concedes structured references are *"usually empty"*.

Meanwhile the **offline fixtures are richer than the live path** — `fixtures/answers.json` hand-writes filenames *and* excerpts:

```
chunk 1 of 01_contract_MSA-2025-0114_bluepeak.md — §4.2 service credit, §3.1 annual fee USD 420
```

**That inversion is the biggest honesty gap in the project:** the fallback looks *more* grounded than production. A judge shown the mock path and then the live path sees the live one look worse.

### Task 3.1 · Resolve citations to source filenames + verbatim excerpts

`documents.py` already knows the filename for every ingested document. Thread it through so a `data_id` / `chunk_id` maps back to a human filename, then have `split_evidence` emit:

```
{"source": "01_contract_MSA-2025-0114_bluepeak.md", "excerpt": "Annual subscription fee: USD 420,000…"}
```

Render each as `filename` + excerpt instead of a UUID. **No re-ingestion** — this is a mapping and a render change, so `219/500` is untouched.

**Acceptance test.** Every citation in every demo answer matches `\S+\.(md|txt|pdf|docx)` and carries a non-empty excerpt.

### Task 3.2 · Show the traversal — turn the multi-hop claim into visible output

Right now nothing in the product shows a path. `app.py:164-173` emits only `start / chunk / references / done`, and `static/index.html:381-389` renders flat strings. `BUILD_REPORT.md:172-173` describes a `Traversal:` line — that is **report prose, not product output**.

Emit the actual traversed typed edges and render them:

```
{"type":"path","edges":[{"from":"25% goodwill credit","rel":"requires_approval","to":"cfo"}]}
```

The graph already contains the exact edges needed:

```
requires_approval   credit value above 20%   -> cfo
escalates_to        finance                  -> cfo
```

**Acceptance test.** The flagship answer emits ≥2 hops whose endpoints are the credit entity and `cfo`, and the UI draws them.

### Task 3.3 · Reframe the multi-hop claim to one that is actually true — and stronger

The corpus contains a genuine cross-document conclusion that **no single file states**. Use it.

| Document | What it establishes |
|---|---|
| `06_meeting_2026-08-28_qbr.md:25-26` | *"the July goodwill credit was **finalised at 25%** … Bluepeak's procurement team **has been told to expect it in writing**"* |
| `06_meeting_2026-08-28_qbr.md:52-53` | Action: *"Close out credit approval paperwork — Nadia Osei — **2026-09-12**"* → **still open** |
| `05_policy_SLA-credit-01.md:47-48` | **§5.2** *"No credit may be confirmed to a customer in writing until the approvals in §4 have been obtained and recorded."* |

**Joining 06 + 05 yields:** a credit was represented to the customer's procurement as finalised while the approval paperwork was still open — **a breach of policy §5.2**. `06` alone states only the representation. `05` alone states only the rule. **Neither states the breach.** This is genuinely graph-only, it spans the two most recent documents, and it is a *stronger* story than the current Chain A because it is about what is happening **now**, not what was proposed in August.

**Also surface the supersession tension**, which is currently invisible: `06` says the credit was "finalised at 25%", while `06:28-29` (Elena) says it *"should not be treated as final until that is done."* The fixture for Q2 cites `05 / 04 / 03` and **omits `06`** — the most recent and most contradictory source. Add `06`.

**Acceptance test.**
```
Flagship answer contains "25%" AND "CFO"/"CFO sign-off", and cites >=2 distinct source docs.
Negative control: no single cited document states the §5.2 breach.
```

---

## 4. Tier 3 — polish and honesty

| # | Item | File | Fix |
|---|---|---|---|
| 4.1 | **`smoke.py` under-asserts.** `assert data.get("auth") != "failed"` passes when the field is missing. | `smoke.py:43` | Change to `== "ok"`. Then run the bad-key check and confirm it exits 1. |
| 4.2 | **Dashboard hides the `source` field**, so it prints `graph: 219 nodes · 500 edges` even when served from the committed fixture. | `static/index.html:232-238` | Read `d.source`; when `fixture`, render `graph: 219 nodes · 500 edges (offline snapshot)`. `brains.html:174-175` already does this correctly — copy that pattern. |
| 4.3 | **Graph animation never stops.** `tick()` calls `requestAnimationFrame` unconditionally, so `draw()` runs every frame forever after the layout settles. | `static/graph.html:151-159` | Only re-schedule while `alpha > 0.02`, plus an explicit redraw on interaction/zoom. |
| 4.4 | **78 of 219 nodes render as unlabelled blobs.** Labels longer than 34 chars are skipped (`graph.html:139-147`) and UUID labels collapse (`graph.html:204`). | `static/graph.html` | Truncate long labels with an ellipsis instead of dropping them; label `DocumentChunk` nodes with a short filename. |
| 4.5 | **`/api/stats` reports a capped count as the total.** `graph(..., limit=500)` (`cognee_cloud.py:365`), then `len(nodes)` is reported as the size. Harmless at 219, wrong above 500. | `app.py:200` | Surface `truncated: true` or report `500+`. |
| 4.6 | **`/api/ask` has no `q` length cap**; `timeout_s` is client-controlled (`app.py:321`). | `app.py:161`, `:321` | Clamp both. |

---

## 5. Tier 4 — after the event (do not start now)

Only if the project continues past the hackathon. Ordered by value.

1. **Authentication + per-user isolation.** The honest gap: `?dataset=` is a *data* partition, **not** an *authorisation* boundary. Anyone reaching the app can read or delete any non-demo brain. This is the first thing that must change for anything real.
2. **Route ingestion through Render Workflows** (2.5 Option B) so retries and fan-out actually apply.
3. **Delete `default_dataset` handling / hide system datasets entirely** from the API surface.
4. **OCR** for scanned PDFs, so the current refusal becomes a feature.
5. **Connectors** (Drive/Slack/Notion) — only if differentiating on breadth; `W.Brain` already ships these.
6. **Add code documents to the corpus** to cover all five artefact types in the Challenge paragraph. Note the cost: re-ingestion is non-deterministic, so every documented node/edge number changes.

---

## 6. Suggested order of work

| Order | Task | Why this order |
|---|---|---|
| 1 | **2.1** failed-terminal-as-success | Highest damage; small change |
| 2 | **2.2** zero-success batch | Same code path as 2.1 |
| 3 | **2.3** reserved-name delete | One-line guard; data-loss vector |
| 4 | **2.6** exact status matching | Prerequisite for 2.1 being correct |
| 5 | **4.1** `smoke.py` auth assertion | Makes the verification story true before anything else changes |
| 6 | **3.1** citation → filename + excerpt | The differentiator |
| 7 | **3.2 + 3.3** traversal + honest multi-hop | The differentiator, part two |
| 8 | **2.4** streaming size caps + `to_thread` | Reliability hardening |
| 9 | **2.5** correct the workflow claim (+ retry) | Integrity; low effort |
| 10 | **4.2–4.6** polish | Last, and only if time remains |
| — | **2.7** deploy | Needs the GitHub repo — see blockers |

**Do not start 3.1/3.2 before 2.1–2.6.** Fixing the honesty of the *claims* is worth more than adding surface area, and every Tier 1 item is smaller than the differentiator.

---

## 7. Blockers (need the operator, not a model)

1. **GitHub repo URL** — no git remote exists, so nothing can be pushed or deployed. `gh` is not installed.
2. **`RENDER_API_KEY`** — needed for deploy; possibly unnecessary, since `render login` is an interactive device flow.
3. **Decision:** does the ~32 s upload run live in the demo, or stay a Q&A answer? Recommendation unchanged: keep it **out** of the four-question path, which runs against a pre-built graph and cannot fail.

---

## 8. Copy-ready prompt for DeepSeek V4.1 Flash

Paste the block below. It is self-contained.

```text
You are working in the repository at /Users/_iayushsharma/Desktop/Ignite_Delhi
("Kestrel Company Brain", Python FastAPI + vanilla JS, talks to a Cognee Cloud tenant).

HARD CONSTRAINTS — violating any of these fails the task:
1. DO NOT re-ingest the corpus and DO NOT write to the cloud tenant. The demo graph
   must stay at exactly 219 nodes / 500 edges. Every change must be code-only.
2. DO NOT modify corpus/*.md, fixtures/graph.json, or fixtures/answers.json.
3. DO NOT remove or weaken existing guards: the demo-dataset delete guard in
   cognee_cloud.py:199, the RESERVED_NAMES checks, the demo-only fixture fallback in
   app.py:105-112, or the mock provider's refusal in memory_layer.py:89-98.
4. DO NOT introduce new dependencies, a bundler, or a CDN script. The UI is
   dependency-free by design.
5. Keep all user-supplied strings rendered via textContent, never innerHTML.

Implement these tasks IN ORDER. After each one, run the stated acceptance test and
report the result before moving to the next.

TASK 1 — cognee_cloud.py + app.py + static/upload.html
A failed ingestion is currently reported to the user as success.
- Add terminal_kind(state) -> "success" | "failure" | None to cognee_cloud.py.
  Match EXACT status enum values: "DATASET_PROCESSING_COMPLETED" -> success;
  any "..._FAILED" / "..._ERRORED" -> failure. Do NOT substring-match the whole
  JSON payload (the payload includes error_detail text, which can contain the
  words "failed"/"success" while the dataset is still processing).
- Redefine is_terminal(state) as a thin wrapper: terminal_kind(state) is not None.
- app.py brain_events (around line 350): emit {"stage":"failed","detail":...} on
  failure and only emit {"stage":"ready"} on success.
- static/upload.html follow(): handle stage "failed" -> finish(false).
Acceptance: stub cognee_cloud.status to return
{"<uuid>":{"status":"DATASET_PROCESSING_FAILED"}}; GET /api/brains/x/events must
contain stage "failed" and must NEVER contain stage "ready".

TASK 2 — app.py create_brain (lines ~301-317)
A batch where every document failed returns HTTP 200 with "ok": true.
- After asyncio.gather, if documents == 0, raise HTTPException(502, detail=<the
  per-file failure reasons>).
- Otherwise set "ok": (documents == len(docs)) and add
  "partial": (documents < len(docs)).
- Do NOT include the char count of failed documents in the response as if it were
  ingested.
Acceptance: monkeypatch memory_layer.remember to raise; POST one valid .md file;
assert status >= 400 and the body does not contain "ok": true.

TASK 3 — app.py delete_brain (lines ~361-374)
DELETE /api/brains/default_dataset currently deletes Cognee's internal dataset.
- Reject any name in RESERVED_NAMES with 400 before calling the client.
- Also re-assert the same check inside cognee_cloud.delete_dataset as
  defence-in-depth, alongside the existing demo guard.
Acceptance: DELETE /api/brains/default_dataset -> 400, dataset still present;
DELETE /api/brains/company_brain -> 400 (must not regress).

TASK 4 — static/index.html (lines ~232-238)
The dashboard prints "graph: 219 nodes · 500 edges" even when that data came from
the committed offline fixture.
- Read the `source` field from /api/stats. When source === "fixture", append
  " (offline snapshot)". Copy the pattern already used in static/brains.html:174-175.
Acceptance: force a fixture fallback; the label must disclose it.

TASK 5 — smoke.py line 43
`assert data.get("auth") != "failed"` passes when the field is absent.
- Change it to assert the value is exactly "ok".
Acceptance: python smoke.py -> 4/4 PASS. Then run with a deliberately bad key and
confirm it exits 1:
  COGNEE_API_KEY=badkey123 PORT=8097 python app.py &
  python smoke.py --base http://127.0.0.1:8097   # expect failure, exit 1

TASK 6 — citations become human-readable (the highest-value change)
Live citations currently render as opaque UUIDs, e.g.
"chunk 1 of document text_cfa979402db25ffb287".
- Thread the uploaded filename through the ingest path so a data_id/chunk_id
  resolves back to a filename.
- Change split_evidence() in cognee_cloud.py (lines ~326-347) so each evidence item
  becomes {"source": "<filename>", "excerpt": "<short verbatim snippet>"}.
- Render filename + excerpt in the Evidence panel (static/index.html renderEvidence,
  lines ~381-389).
Acceptance: every citation in every demo answer matches \S+\.(md|txt|pdf|docx) and
carries a non-empty excerpt. This must NOT require re-ingestion.

TASK 7 — show the traversal
Nothing in the product currently shows a multi-hop path.
- Emit {"type":"path","edges":[{"from":..,"rel":..,"to":..}]} from /api/ask.
- Render it in static/index.html.
Acceptance: the flagship answer emits >= 2 hops; the UI draws them.

TASK 8 — static/graph.html
- The tick() loop (lines ~151-159) calls requestAnimationFrame unconditionally, so
  draw() runs forever. Only re-schedule while alpha > 0.02, and redraw explicitly on
  interaction/zoom.
- Labels longer than 34 chars are skipped (lines ~139-147), leaving 78 of 219 nodes
  unlabelled. Truncate with an ellipsis instead of dropping; label DocumentChunk
  nodes with a short filename.
Acceptance: CPU drops to idle once the layout settles; every node renders a label.

REPORT FORMAT: for each task, state the files changed, the exact command run, and
the observed result. If an acceptance test fails, stop and report — do not proceed.
```

---

## 9. Verification checklist for the operator

Run these before judging, in this order.

```bash
cd /Users/_iayushsharma/Desktop/Ignite_Delhi
PY=/Users/_iayushsharma/.workbuddy-ai/binaries/python/envs/hackathon/bin/python

git status --short                 # expect: clean
$PY test_documents.py              # expect: 25 passed, 0 failed
$PY app.py &                       # start
$PY smoke.py                       # expect: 4/4 PASS
$PY warmup.py                      # expect: all green, all 4 questions cited

# must still be exactly this — proves no re-ingestion happened
curl -s "http://127.0.0.1:8000/api/graph?dataset=company_brain" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print(len(d['nodes']),len(d['edges']))"
# expect: 219 500

# the new guard
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE \
  http://127.0.0.1:8000/api/brains/default_dataset      # expect: 400
```

**Then open the UI in a real browser.** `curl` proves nothing about rendering — that is how two of the original bugs were missed.
