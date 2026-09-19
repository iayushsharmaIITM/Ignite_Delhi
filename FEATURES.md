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
| 2.2 | ~~Read-only brain switcher~~ — **BUILT** | Scalability, System Architecture | done | `?dataset=` on every read route, plus the `/brains` dashboard. The per-request refactor it required is in `app.py`. |
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
| 3.1 | ~~File upload → brain creation~~ — **BUILT** | Shipped: `POST /api/brains` with a real parser (`documents.py`), progress streaming, and per-file failure reporting. Verified end to end in 34.1s. |
| 3.2 | **Real auth + per-tenant isolation** | Still the biggest genuine gap. Brains are global to the tenant; there is no "my brains". No rubric line, but it is the first thing a product-minded judge will ask. |
| 3.3 | **Connector sync** (Drive, Slack, Notion, Jira) | OAuth flows. W.Brain already ships these; matching them is not differentiation. |
| 3.4 | **COGX export/import** | Portability. Cognee 1.0 parity, not an edge. |
| 3.5 | **Brain sharing and permissions** | Depends on 3.2. |
| 3.6 | **Scheduled re-ingest / drift detection** — "this contract changed since last week" | Genuinely compelling, genuinely large. The strongest post-event idea here. |
| 3.7 | **Billing and plan tiers** | Premature by definition. |
| 3.8 | **Audit log** — who asked what, and what it saw | Enterprise requirement, not a demo feature. |
| 3.9 | **Retention policy** | Deleting a brain is now possible from the UI; what is missing is a policy, a TTL, and an audit trail. |

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

### 6.1 The headline — this changed

**An earlier revision of this document stated that no upload feature existed. That is no longer
true: it was built and verified.** The web tier went from six GET routes with no write path to a
full create / list / delete surface.

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | health + authenticated tenant probe |
| GET | `/api/ask?q=&dataset=` | streamed answer, any brain |
| GET | `/api/graph?dataset=` | graph, any brain |
| GET | `/api/stats?dataset=` | node/edge counts, any brain |
| GET | `/api/brains` | list every brain |
| **POST** | `/api/brains` | **create a brain from uploaded files** |
| GET | `/api/brains/{name}/events` | ingestion progress (NDJSON) |
| **DELETE** | `/api/brains/{name}` | remove a brain |
| GET | `/` `/graph` `/brains` `/upload` | pages; `?brain=` scopes the first two |

The load-bearing change underneath it: `COGNEE_DATASET` used to be read at **process start**, so
the app was bound to one dataset. Every read route now takes `?dataset=`, which is what lets a
single dashboard serve every brain.

### 6.2 What we HAVE

| Capability | Where | Notes |
|---|---|---|
| **File upload → brain creation** | `POST /api/brains` (`app.py`) | Multipart: a name plus up to 20 files |
| **Document parsing** | `documents.py` | PDF (pypdf), DOCX (python-docx), TXT, MD, CSV, JSON. Verified **25/25** in `test_documents.py` |
| **Per-request dataset** | `?dataset=` on `/api/ask`, `/api/graph`, `/api/stats` | Was a process-start env var. This is the refactor that makes multi-brain work at all |
| **Brain listing** | `GET /api/brains` → `cognee_cloud.datasets()` | The dashboard shows per-brain node/edge counts |
| **Brain deletion** | `DELETE /api/brains/{name}` → `cognee_cloud.delete_dataset()` | Refuses the demo dataset **in code**, not in a comment |
| **Ingestion progress in the UI** | `GET /api/brains/{name}/events` | Streams real pipeline states: `DATASET_PROCESSING_STARTED` → `DATASET_PROCESSING_COMPLETED` |
| Per-brain isolation | `ingest.py --dataset X`; the upload path | Demonstrated across 3 ephemeral containers |
| Guards | `app.py` | Name normalisation + validation; reserved names rejected; existing brain refused (409) rather than silently merged into; 5 MB/file, 20 files, 500k chars |
| Data-item deletion | `DELETE /api/v1/datasets/{id}/data/{data_id}` | Used for the junk-node repair; still not exposed in the app |
| A committed corpus | `corpus/` — 10 documents | Ingested by CLI **before** the app starts |

### 6.3 What we still DO NOT have

| Missing | Evidence |
|---|---|
| **Any auth, account, or session** | None. Every route is anonymous — including `POST` and `DELETE`. Anyone with the URL can create or delete a brain. Fine for a hackathon; not for a product. |
| **Per-user isolation** | Brains are global to the tenant. There is no notion of "my brains" versus "yours". |
| **Connectors** | No Slack, Drive, Jira or Notion. Ingestion is manual upload only. |
| **Web-triggered workflows** | The upload path ingests **directly** via `memory_layer.remember`, not through the Render Workflow tier. Deliberate: the web tier already holds the tenant credential, so routing through a workflow would add latency and a second credential path for no gain. The workflow tier remains demonstrated by `ingest.py`, `pipeline.py` and `wf_smoke.py`. |
| **Billing / plans** | None. |
| **Retention policy** | You can delete a brain, but there is no policy, TTL, or audit trail. |
| **Code in the demo corpus** | The PS-2 Challenge paragraph mentions code. The upload path accepts it as plain text, but `corpus/` has none. See `REQUIREMENTS.md` §5. |
| **OCR** | A scanned PDF is detected and refused with a clear message rather than silently ingesting nothing. That is honest, but it is not reading the scan. |

### 6.4 The precise distinction to hold in your head

> **Per-brain isolation is now a user-facing feature. What remains missing is the multi-user
> layer around it: accounts, auth and per-user scoping.**

The distinction moved. Previously the honest statement was "you can claim the architecture, you
cannot claim the workflow." Today you can claim both — a person can upload documents and query
the resulting brain in the same dashboard as the demo brain. What you still cannot claim is that
two *different* people using it would be isolated from each other, because there are no accounts.

That is a much stronger position, and a much easier gap to defend: "no auth" is a scope decision,
whereas "no upload" would have been a missing feature.

---

## 7. The one sentence for a judge

If asked "so can I upload my company's documents?":

> "Yes — try it. Drop your files on the upload page and you have a queryable brain in about a
> minute. We verified it end to end: four documents in, 40 nodes and 64 edges out, answering
> from the content with citations. What we did not build is the multi-user layer around it —
> accounts, per-user scoping, connectors, billing. We chose a working ingestion path over a
> half-finished signup form."

That answer scores. A broken upload button does not.

---

## 8. Recommendation — updated after the upload path was built

Tier 1.1 (Contradiction Report) is still the highest-value **unbuilt** item: it is the one thing
a vector-search competitor structurally cannot do, and it costs well under an hour.

But the priority order has changed now that the upload path exists. **The upload demo is now the
riskiest thing you own**, because it is the only part of the system whose happy path depends on a
live LLM extraction completing, on a tenant you do not control, in front of an audience.

So the order is:

1. **Rehearse the upload against the real tenant and time it.** Measured at ~34s end to end for
   3 files. Know the number before you promise it out loud.
2. **Run `warmup.py` until all four demo questions are green twice in a row.**
3. Only then consider the Contradiction Report.

Do not add a fourth moving part on the day.
