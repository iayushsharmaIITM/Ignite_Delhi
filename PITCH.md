# PITCH — Ignite Room

Two different rounds, two different jobs.

- **Mentoring (15:30–16:30)** scores the **story**: Problem Clarity · Design Decisions ·
  Scalability · Technical Implementation · Scope & Prioritisation
- **Judging (17:00–18:00)** scores the **product**: Production standards · Technical
  Understanding · System Architecture · Completeness · Reliability

Do not reuse one script for both. The 5-minute pitch argues; the 1-minute pitch asserts.

Both scripts are word-counted against a 140 wpm speaking rate:

| Round | Words | At 140 wpm | Budget | Buffer |
|---|---|---|---|---|
| Round 1 (5 min) | 550 | **236s** | 300s | 64s for pauses and emphasis |
| Round 2 (1 min) | 133 | **57s** | 60s | 3s — it fits at 150–160 wpm with room |

Every Round 1 segment is individually inside its own budget, so you can check your pace at each
timestamp rather than discovering at 4:30 that you are behind.

---

## Numbers to know cold

| Fact | Value |
|---|---|
| Corpus | 10 synthetic company documents |
| Graph | **219 nodes · 500 edges** |
| Ingest time | 10 documents queued in **10.9s** across 3 workers; graph ready in **~1 minute** |
| Parallel fan-out proof | 3 documents → 3 separate task containers → **`failed:0 queued:3` in 6.05s**, all queryable from one shared graph |
| Answer latency | **~16–31s** end-to-end; first token at **~18s**, then streams fast |
| Credentials per container | **1** (an API key) |
| Services | **2** (web tier + workflow tier) |
| Code | **~1,300 lines** — 725 Python (web tier, Cognee client, memory layer, workflow) · 562 UI |

---

## ROUND 1 — 5-minute mentoring pitch

### 0:00 — Problem Clarity (45s)

> "Company knowledge is scattered. A contract lives in one system, the incident that
> breached it in another, the meeting where we apologised for it in a third, and the
> policy that governs the remedy in a fourth.
>
> So here is a question a real company could not answer: **why is the Bluepeak renewal at
> risk, and what have we promised them?**
>
> No single document answers that. Search returns five documents and leaves you to
> assemble it. We return one answer, with the five sources attached — and we flag where
> those sources contradict each other."

**Land this line:** the contradiction. It is the thing that makes this a memory product
rather than a search box.

### 0:45 — Technical Implementation (60s)

> "Ten documents go in. Cognee extracts entities and relationships and builds a graph —
> 219 nodes, 500 edges. The graph is built **ahead of time**, not on stage.
>
> Ask a question and the answer streams in, followed by its evidence block.
>
> Watch what it does with the credit. The contract says 10%. The meeting notes say we
> offered the customer 25%. The policy says anything above 20% needs CFO sign-off. The
> graph holds all three, and the answer says so."

### 1:45 — Design Decisions (75s) — *the highest-value segment*

> "Three decisions, and what we rejected.
>
> **One: the graph lives outside the compute.** Render task runs are ephemeral containers
> — destroyed when the run ends. Cognee's default graph backend is file-based. So a graph
> built during an ingest run was **gone** by the time a retrieve run started. We hit that
> directly. The fix isn't to avoid ephemeral containers — it's to put the graph where
> containers can't kill it. That's why the memory layer sits outside the workflow tier.
>
> **Two: we dropped the Cognee SDK from the deploy.** We talk to the same HTTP API with a
> light client. The SDK drags in the whole model and embedding stack. Smaller image,
> faster build, fewer failure modes — for identical behaviour.
>
> **Three: a provider adapter.** The memory layer is `mock | cloud`. If the network dies
> on stage, we flip one environment variable and the demo serves committed fixtures. A
> live demo must not be able to fail because of someone else's uptime."

### 3:00 — Scalability (60s)

> "Here's the part I think is actually interesting.
>
> Because the graph lives outside the container, **every container needs exactly one
> credential** — an API key. No model key, no database password, no mounted volume.
>
> So scaling is adding containers. We proved it: three documents fanned out across three
> ephemeral containers into one shared graph, in six seconds. A hundred documents is a
> hundred containers and no change to the design.
>
> And that same property hands you the platform for free. **A brain is a dataset** — separate
> graph, separate index, separate storage. Adding a customer adds containers, not architecture.
>
> So we went further: **anyone can upload their own documents and get their own queryable
> brain.** What we didn't build is the accounts layer — signup, SSO, billing."

### 4:00 — Scope & Prioritisation (45s)

> "And here is what we deliberately did **not** build.
>
> No Slack, GitHub or Linear connectors. No accounts, no SSO, no per-user isolation. No
> fine-tuning, no custom embeddings, no agent swarms, no admin panel.
>
> Every one of those is a real feature. We chose not to have them so the ones we did
> build would work. Three hours, one builder — the kill list *is* the deliverable."

### 4:45 — Close (15s)

> "Ten documents. One graph. One question that no single document could answer, answered
> with its sources and its contradictions exposed. Thank you."

---

## ROUND 2 — 1-minute judging pitch

Deliver this standing next to the running app. Assert, don't argue.

> "Company knowledge is scattered, so a question spanning a contract, an incident, a meeting
> and a policy is unanswerable. We built the Kestrel Company Brain: ten documents in, one
> knowledge graph out — 219 nodes, 500 edges.
>
> Ask why the Bluepeak renewal is at risk and it answers from five sources at once, cites all
> five, and **flags that our contract and our meeting notes disagree on the account value**.
>
> Two services: a web tier that streams answers, and a Render Workflow that fans ingestion
> across ephemeral containers. The graph lives outside them, in a Cognee Cloud tenant — so
> the containers cannot kill it.
>
> The graph is pre-built, the memory layer falls back to fixtures if the network dies, and
> `/health` checks every component *and* that our key still works. **The demo cannot die.**"

---

## The 90-second demo click path

Rehearse this exactly. Do not improvise on stage.

1. **Open `/`** — the UI is already loaded. Point at the graph count in the footer:
   *"219 nodes, 500 edges — that's the whole company."*
2. **Click chip 1** — *"Why is the Bluepeak renewal at risk, and what have we promised them?"*
   The box shows *"Searching the knowledge graph…"* for **~18s before the first word
   appears.** That gap is yours — fill it: *"it's traversing the graph now; the answer
   isn't a document, it's assembled from five."* Then let it stream and stop talking.
3. **Point at the answer** when it mentions the **$420k vs $480k** discrepancy.
   *"Nobody asked it to compare those. It found them."*
4. **Point at the Evidence panel.** *"Three sources. Every answer is grounded."*
5. **Click chip 4** — the renewal-date consistency question. *"Same corpus, different
   question. This is the one a human would get wrong."*
6. **Open `/graph`.** *"And this is the graph itself."* Pause. Let it land. Move on.
7. **Close on `/health`.** *"Four upstream components healthy — plus an authenticated probe,
   because a health endpoint that reports 'up' while rejecting your key is worse than no
   check at all. And a fallback if any of it fails."*

**If anything stalls:** say *"while that's thinking — "*, then talk architecture. Never
apologise, never reload, never debug on stage.

**Answer shape varies between runs** — sometimes a table, sometimes bullets, same facts
either way, and both render correctly. So do not promise a table on stage. Point at the
*content* (the `$420k` vs `$480k` mismatch), never at the layout.

---

## Q&A bank

**"Why not just use a vector database and RAG?"**
> Because RAG retrieves text that *looks* similar. We need relationships. "Who owns the
> renewal" is a relationship. "Which incident breached which contract clause" is a
> traversal. And RAG cannot tell you two documents disagree — it just returns both and
> hopes you notice. The graph can.

**"Is this really scalable?"**
> Ingestion is: more documents, more containers, no change. Retrieval is a single HTTP
> call. The honest limit is the tenant instance — at real volume you'd move the graph to
> a dedicated Neo4j cluster and point Cognee at it with `GRAPH_DATABASE_PROVIDER=neo4j`.
> The application code does not change.

**"Isn't this just a single-tenant demo? Where's the multi-tenancy?"**
> It is multi-tenant, and you can watch it happen. A brain is a dataset — separate graph,
> separate vector index, separate storage, nothing shared. We proved it twice: three documents
> fanned out across three ephemeral containers into three isolated datasets; and there is a
> live upload page — drop your own files in, get your own brain, query it in the same
> dashboard. What's missing is the accounts layer: signup, SSO, per-user isolation. That is
> product work rather than architecture, and it was the deliberate cut.

**"What happens if the network dies?"**
> `/health` reports `upstream: unreachable`. And the memory layer falls back to the mock
> provider, which serves committed fixtures offline. One environment variable.

**"How do you know this will actually work on stage?"**
> Three layers. The four demo questions run against a pre-built graph, so nothing is generated
> live. `warmup.py` rehearses all four demo questions and times them — anything slow or
> ungrounded surfaces before we walk on. And `/health` runs an *authenticated* probe, because
> we found the tenant's own health endpoint is unauthenticated: it reported everything healthy
> while every query returned 401. A check that cannot fail is not a check.
>
> The one live step is the upload, if we demo it. That one does depend on a real extraction
> completing, which is why we measured it — about 34 seconds for three files — instead of
> assuming it.

**"Did you build the graph view?"**
> We render it ourselves from `/api/graph` — force-directed, coloured by node type. The
> data is ours; we didn't want to hide behind someone else's UI.

**"How much of this is Cognee doing the work?"**
> Cognee does the hard part: entity extraction, relationship building, graph-grounded
> answering, and the evidence block. What's ours is the architecture around it — the
> ephemeral-container problem, the orchestration, the reliability layer, and the corpus.

**"What would you do with another day?"**
> Three things, in order: the Neo4j backend for real traversal queries; `CONTRADICTION_
> DETECTION` and `PROVENANCE_TRACKING`, which are off by default and would turn the
> contradiction from a nice answer into a flagged alert; and real connectors, so the
> corpus grows itself.

---

## Failure protocol — two strikes

If a bug appears:

1. **Strike one:** note it, do not fix it during the round. Keep talking.
2. **Strike two:** switch `PROVIDER=mock`. The demo completes on fixtures.
3. Fix it in the 16:30–17:00 gap, or not at all.

**Never debug on stage. The rubric rewards a demo that completes, not one that is
technically perfect.**
