# FEATURES.md — What Would Make This Stand Out

Two questions answered here:

1. A ranked list of features that would make this project stand out — everything worth considering.
2. An exact statement of what the **dataset-upload-to-a-company-brain** capability is, and is not.

Everything below is grounded in the current repository state, verified by reading the code,
not recalled from memory.

---

## 0. Read this first: the rubric pays nothing for novelty

Verified from the criteria sheet: **ten criteria × 5 points = 50**, split across a mentoring
round (scores the *story*) and a judging round (scores the *product*).

**There is no novelty, creativity, or "wow factor" line.**

That single fact reorganises every decision below. A feature is worth building only if it moves
a scored line. The lines we can see:

| Criterion | What it actually asks |
|---|---|
| Problem Clarity | Does the judge understand the problem you solved? |
| Technical Implementation | Is the engineering real and non-trivial? |
| Design Decisions | Can you justify your tradeoffs out loud? |
| System Architecture | Is the shape of the system sound? |
| Scalability | Does it hold beyond the demo? |
| Completeness | Does what you claimed actually work end to end? |
| Reliability | Does it survive failure? |
| Scope & Prioritisation | Did you cut well? |

**The consequence, stated plainly:** the biggest threat to this score is not a missing feature.
It is a *half-finished* feature, because a half-finished feature damages Completeness and
Reliability simultaneously — the two lines where a working demo already scores well.

Every Tier 3 item below is a **liability today** and an asset only after the freeze.

---

## 1. What already earns points (the baseline)

| Capability | Verified state | Rubric line it moves |
|---|---|---|
| Cross-document contradiction catch | `$420,000` (MSA) vs `$480,000` (meeting notes) surfaced **unprompted** | Problem Clarity, Technical Implementation |
| Knowledge graph | **219 nodes / 500 edges** from 10 documents | Technical Implementation |
| Graph visualisation | dependency-free canvas renderer, 602k painted pixels, 5 legend types | Technical Implementation |
| Durable orchestration | 4 tasks; `ingest_corpus` fan-out ×3 → `queued:3 failed:0` in **6.5s** | System Architecture, Scalability |
| Ephemeral-container answer | state lives in the tenant; **one credential per container** | Design Decisions, System Architecture |
| Multi-dataset isolation | `ingest.py --dataset X`, demonstrated across 3 isolated containers | Scalability |
| Three-layer failure story | bad key → `auth: failed`; dead tenant → fixture graph, UI intact | Reliability |
| Offline demo path | `PROVIDER=mock`; fresh clone with zero credentials → smoke 4/4 | Reliability |
| Documented traps | 7 traps in README, each with the failure it prevented | Design Decisions |

This is already a strong position. The items below are *additions*, not repairs.

---

## 2. Tier 1 — build these if you build anything (high return, each under an hour)

### 1.1 Contradiction Report — the single highest-value addition

**What:** a dedicated view listing conflicts the graph found *across* documents, each with both
sides quoted and both sources cited. Two are already planted and already proven to surface:

- `$420,000` in the MSA vs `$480,000` in the meeting notes
- `25%` credit promised in the meeting vs `10%` policy baseline (with `>20%` needing CFO sign-off)

**Why it scores:** this is the one thing a vector-search competitor **cannot** do. Retrieval
finds the nearest passage; it cannot notice that two passages disagree. It converts the demo
from "it answers questions" into "it catches errors nobody asked it to find" — which is the
actual business value of a company brain.

**Effort:** low. The behaviour already works. This is a route plus a render.

**Risk:** low. Additive; the existing ask flow is untouched.

**Moves:** Problem Clarity, Technical Implementation, Design Decisions.

### 1.2 Clickable provenance

**What:** today citations render as text lines produced by `split_evidence()`. Make each one a
chip that reveals the source document and the matched span.

**Why it scores:** "where did that come from?" is the first question a judge asks about any
LLM answer. Being able to answer it instantly, from real data, is the difference between a
demo and a product.

**Effort:** low–medium. The source documents are committed and small.

**Moves:** Technical Implementation, Reliability.

### 1.3 Latency honesty indicator

**What:** a live counter during retrieval — `retrieving… 12s` — and on completion, the measured
split.

**Why it scores:** the answer takes **~18s to begin** (first chunk at 17.8s, then 226 chunks
over 3s — measured). That is the weakest moment in the demo. Naming it turns an apparent
freeze into visible evidence that you measured your own system.

**Effort:** trivial. The status line already exists; this adds a number to it.

**Moves:** Technical Implementation, Design Decisions.

### 1.4 Ingest telemetry panel

**What:** visualise the pipeline that produced the graph: 10 documents → chunks → entities →
219 nodes / 500 edges, with the three-container fan-out shown as three parallel lanes.

**Why it scores:** the Render Workflows story is currently **invisible** during the demo. The
judge sees an answer and a graph; they do not see durable orchestration, retry policy, or
fan-out. This makes the architecture claim self-evidencing instead of rhetorical.

**Effort:** low–medium. All the numbers already come from `/api/stats` and `/api/graph`.

**Moves:** System Architecture, Technical Implementation.

---

## 3. Tier 2 — build only if Tier 1 is done and verified

| # | Feature | Moves | Effort | Notes |
|---|---|---|---|---|
| 2.1 | **"Not in the graph" path** — when recall finds nothing, say so explicitly instead of producing fluent filler | Reliability, Technical Implementation | low | Directly answers the judge's sharpest question. High value per minute. |
| 2.2 | **Read-only brain switcher** — a dropdown that points the app at a second pre-seeded dataset | Scalability, System Architecture | medium | The honest, cheap version of the platform story. Requires reworking `COGNEE_DATASET` from a startup env var into a per-request parameter — see §6. |
| 2.3 | **Subgraph highlight after answering** — dim the graph to only the nodes the answer traversed | Technical Implementation, Scalability | medium | Visually proves the graph is doing work, not decoration. |
| 2.4 | **Timeline / entity resolution view** — the same entity with conflicting attributes shown over time | Problem Clarity | medium | Generalises the contradiction catch into a reusable view. |
| 2.5 | **Live verification page** — surface smoke/warmup results in the UI | Reliability | low | Turns your test suite into demo evidence. |
| 2.6 | **Progressive citations** — stream references as they resolve rather than at the end | Technical Implementation | low–medium | Marginal over 1.2. |

---

## 4. Tier 3 — the platform bets (post-hackathon, not now)

These are the features that turn "a company brain" into "a platform for building company
brains". They are **real business features** and **scored liabilities** in the current window.

| # | Feature | Why it is not now |
|---|---|---|
| 3.1 | **File upload → brain creation** (`POST /api/brains`, multipart, async ingest, progress) | Needs a document parser, a job queue, a progress UI, and failure handling — none tested. The app currently has **zero write endpoints**. |
| 3.2 | **Real auth + per-tenant isolation** | No rubric line. Any mid-demo breakage costs Reliability. |
| 3.3 | **Connector sync** (Drive, Slack, Notion, Jira) | OAuth flows. W.Brain already ships these; matching them is not differentiation. |
| 3.4 | **COGX export/import** | Portability. Cognee 1.0 parity, not an edge. |
| 3.5 | **Brain sharing and permissions** | Depends on 3.2. |
| 3.6 | **Scheduled re-ingest / drift detection** — "this contract changed since last week" | Genuinely compelling, genuinely large. The strongest post-event idea here. |
| 3.7 | **Billing and plan tiers** | Premature by definition. |
| 3.8 | **Audit log** — who asked what, and what it saw | Enterprise requirement, not a demo feature. |
| 3.9 | **Retention and deletion UI** | The API supports it (see §6), the UI does not. |

---

## 5. Kill list — do not build these, at any point today

Each of these has been considered and rejected for a specific reason:

- **Custom embeddings or vector-store tuning** — the tenant owns the vector store. We cannot
  meaningfully tune it, and no rubric line rewards it.
- **Fine-tuning** — no model key exists in this architecture, by design.
- **A second graph backend** — the whole point of the tenant is that we do not run one.
- **Mobile or responsive redesign** — the demo runs on a laptop, projected.
- **Real-time collaboration** — no user model exists to collaborate between.
- **Anything requiring a model-provider key** — we deliberately hold **zero** model credentials.
  Adding one re-introduces the exact blocker that was eliminated early on.

---

## 6. The upload question — exact inventory

You asked me to state precisely what we have and what we do not. This section is the answer,
with the evidence.

### 6.1 The headline

**There is no dataset-upload feature. There is no way for a user to create a company brain
through the application.** The web tier has **six routes, and every single one is a GET**:

```
app.py:60   @app.get("/health")
app.py:97   @app.get("/api/ask")      ?q=<question>
app.py:113  @app.get("/api/graph")
app.py:123  @app.get("/api/stats")
app.py:143  @app.get("/")
app.py:148  @app.get("/graph")
```

**Not one POST. Not one PUT. Not one DELETE.** The application is read-only.

### 6.2 What we HAVE

| Capability | Where | Notes |
|---|---|---|
| Text ingestion into a named dataset | `cognee_cloud.remember()` → outbound `POST /api/v1/remember` | Multipart with a **text field** (`raw_data=<text>`), not a file upload |
| Per-brain isolation **as a parameter** | `ingest.py --dataset X`; `COGNEE_DATASET` env var; `pipeline.py` accepts a `dataset` kwarg | This is real and it works |
| Multi-tenant fan-out, demonstrated | `ingest_corpus` across 3 ephemeral containers into isolated datasets | The architecture-level capability is proven |
| Dataset listing | `cognee_cloud.datasets()` (`cognee_cloud.py:153`) | One call away from a "your brains" list |
| Dataset deletion | `wf_smoke.py:165 delete_scratch()` — a raw `requests.delete`, written as test cleanup | Exists, but as a test helper, not an API |
| Data-item deletion | `DELETE /api/v1/datasets/{id}/data/{data_id}` — used once, documented in `OVERVIEW.md:88` | A one-off repair, **not committed as a function** |
| Document listing / raw retrieval | `GET /api/v1/datasets/{id}/data` and `.../raw` | Used during the junk-node repair; not exposed in the app |
| A committed corpus | `corpus/` — 10 documents | Ingested by CLI **before** the app starts |

### 6.3 What we DO NOT have

| Missing | Evidence |
|---|---|
| **Any upload endpoint** | No POST/PUT route exists. `grep` for `UploadFile`, `multipart`, `FormData` across the repo returns **only** the outbound comment in `cognee_cloud.py:16` and two `FileResponse` uses for serving HTML. |
| **Any file input in the UI** | `static/index.html` contains exactly one `<input>` (`id="q"`, a text field) and one `<button>` (`id="go"`). No `<input type="file">`, no drag-and-drop, no `<select>`. |
| **Any document parser** | No `pypdf`, no `python-docx`, no `openpyxl`, no CSV handling anywhere. `requirements.txt` has none. |
| **A "create a brain" flow** | No route, no form, no concept of a user-owned brain in the UI. |
| **A brain switcher** | `COGNEE_DATASET` is read at **process start** (`app.py:66`, `app.py:138`). The running web app is bound to **one** dataset and cannot serve two brains simultaneously. |
| **Ingestion progress in the UI** | Ingestion is CLI-only and happens before the app launches. |
| **User-triggered workflows** | Render Workflows is invoked via `render workflows start` from the CLI — the web tier cannot trigger it. |
| **Any auth, account, or session** | None. Every route is anonymous. |
| **Retention / deletion UI** | The API supports both; the app exposes neither. |

### 6.4 The precise distinction to hold in your head

> **Per-brain isolation exists as a CLI/workflow parameter. It does not exist as a user-facing
> feature.**

The multi-tenant *capability* is real — `--dataset X` scopes ingestion and query, and it was
demonstrated across three isolated containers. What is missing is the *product surface*: no
upload, no parser, no brain list, no switcher, no accounts.

This distinction is why the platform reframe is defensible in a pitch and why the upload
feature is correctly deferred. You can claim the architecture. You cannot claim the workflow.

---

## 7. The one sentence for a judge

If asked "so can I upload my company's documents?":

> "The ingestion path is real and runs through a durable workflow — we demonstrated it fanning
> out across three containers into isolated datasets. What we deliberately did not build in a
> three-hour window is the upload surface around it: the parser, the job queue, and the
> per-tenant accounts. We chose a working, verified pipeline over a half-finished signup form."

That answer scores. A broken upload button does not.

---

## 8. Recommendation

**Build Tier 1.1 (Contradiction Report) and Tier 1.3 (latency indicator) if you build anything.**

Together they cost well under an hour, they are additive rather than invasive, and they move
four scored lines. They also both make a claim you have *already proven* visible to a judge who
has not read your code.

Then stop, and spend the remaining time on the thing that actually decides the score:
**running `warmup.py` until all four questions are green, twice in a row.**
