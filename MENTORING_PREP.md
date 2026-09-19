# MENTORING ROUND PREP — read this first

**Round:** mentoring, 5 min pitch + 2 min Q&A. Scores the **story**, not the product.
**Criteria (25 pts):** Problem Clarity · Design Decisions · Scalability · Technical Implementation · Scope & Prioritisation.
**The one thing to remember:** there is **no novelty/wow criterion**. Every point is awarded for engineering judgment. Do not sell "cool" — sell "deliberate".

---

## 1. The stack, in plain language

You have **four** moving parts. Learn these four sentences and you can answer almost anything.

| # | Component | What it IS | Why it is there |
|---|---|---|---|
| 1 | **Cognee Cloud tenant instance** | The knowledge-graph engine. It owns the **LLM, embeddings, vector store (pgvector), relational DB, graph store and file storage**. | It is where **all durable state lives**. We talk to it over plain HTTP with **one API key**. |
| 2 | **Render Workflows** | The orchestration tier for long-running / parallel work. | Each task run gets **its own ephemeral container**, so we can fan ingestion out across workers. |
| 3 | **FastAPI (Python)** | The web tier. Serves the UI, streams answers as NDJSON. | It is the only public surface. It is the thing that talks to the tenant. |
| 4 | **Vanilla JS + Canvas** | The UI — no framework, no build step, no CDN. | Nothing to compile, nothing to break. The graph renderer is ~200 lines of hand-written Canvas. |

### The one architectural insight that ties it together

> **Render task runs cannot accept inbound connections (no ports) and are destroyed when the run ends.**

That single constraint explains the whole shape:

- A workflow task **can never serve the UI** → you need **two services**.
- A **file-based graph backend cannot survive** a container being destroyed → state must live **outside** the compute.
- Therefore the graph lives in the **tenant**, and every container needs exactly **one credential** (an API key) instead of three.

**Say this out loud if you say nothing else.** It shows you understood the platform rather than assembling a tutorial.

### What we rejected, and why (this is the Design Decisions points)

| Rejected | Reason |
|---|---|
| **Neo4j** (the organisers suggested it) | The tenant **already** provides a graph store outside the container. Neo4j would add a second datastore and a second credential for **no gain at this scale**. It stays a drop-in if we ever need company-scale traversal. |
| **Cognee SDK** | We hit the same HTTP API with a light `requests` client. Smaller image, faster build, fewer failure modes, identical behaviour. |
| **The multi-tenant platform pivot** | The platform layer is the one Cognee already occupies; W.Brain ships this concept at $39/mo; **the rubric pays nothing for novelty**. Net −5 on the rubric. |
| **Real connectors** (Slack/Drive/Jira) | The graph is the hard part; a connector is a polling loop. |
| **A CDN markdown library** | The app already needs the network for the tenant. A second remote dependency is a second way to fail. |

---

## 2. Cheat sheet — one line per criterion

| Criterion | Your line |
|---|---|
| **Problem Clarity** | "Company knowledge is scattered. A contract lives in one system, the incident that breached it in another, the meeting where we apologised in a third, and the policy governing the remedy in a fourth." |
| **Technical Implementation** | "Ten documents in, one knowledge graph out — **219 nodes, 500 edges**. Answers stream with citations." |
| **Design Decisions** | "Three decisions and what we rejected: state outside the compute; no SDK; and a provider adapter so a dead network cannot kill the demo." |
| **Scalability** | "Ingestion fans out across ephemeral containers. Add documents, get more containers, change nothing else — the tenant absorbs the state." |
| **Scope & Prioritisation** | "Here is the kill list. **Scope is worth 5 points on its own** — that list is a scoring instrument, not an apology." |

---

## 3. Numbers to know cold

| | |
|---|---|
| Corpus | **12 documents**, six information types |
| Graph | **219 nodes · 500 edges** |
| Relationship labels | **112** — 107 of them domain-specific |
| Answer latency | **~16–31s**; first token ~18s |
| Credentials per container | **1** |
| Services | **2** (web + workflow) |
| Tests | 25 unit · 13 state · 4 smoke |
| Build | **19 commits, 1h 47m** against a 3-hour budget |

---

## 4. The strongest thing you can say

Ask it the credit question and let it answer:

> **Q:** What service credit did we promise Bluepeak, does it breach our own policy, and who signs it off?
> **A:** A **25% goodwill credit**. Policy **SLA-CREDIT-01** caps ≤10% at support-lead, 10–20% at finance, and **>20% needs the CFO**. So it **breaches our own policy** until approved.

Then the honest kicker — **do not overclaim this**:

> "It joins a meeting note to a policy to the approval chain. The graph carries those typed edges — `requires_approval: credit value above 20% → cfo`. **I'll be straight with you: the chat thread states the breach outright, so this one is a genuine multi-document join rather than a derivation no single document supports.** The one that genuinely needs two documents is our QBR-to-policy chain: the QBR says the credit was *finalised at 25%* and procurement *has been told to expect it in writing*, while the policy §5.2 forbids confirming a credit in writing before approvals are recorded. **Neither document states that breach.**"

Volunteering the limit of your own claim is the single most credible thing you can do in a mentoring round. It is also true.

---

## 5. Likely questions, with answers

**"How is this different from a vector search / RAG?"**
A vector index returns the passage nearest your question. It cannot tell you that a *policy* makes a *meeting promise* non-compliant. That needs typed edges between entities, which is what the graph holds.

**"Why does the graph live in the cloud and not locally?"**
Because Render task runs are ephemeral. A graph built during an ingest run is destroyed with the container — we hit that directly. The fix is not to avoid ephemeral containers; it is to put the graph where containers cannot kill it.

**"Is it robust, or is it a demo?"**
It is failure-tested. `/health` probes an **authenticated** endpoint, because the tenant's own health check is unauthenticated and reported healthy with a dead key. We watched it go red with a bad key — a check you have never seen fail is not evidence of anything.

**"What happens if the network dies on stage?"**
A `mock | cloud` provider adapter falls back to committed fixtures, and the graph view falls back to a committed snapshot. The safety net is allowed to fail; it is **not** allowed to lie — it refuses to answer for an uploaded brain rather than serving demo data.

**"Why only 219 nodes?"**
Because the corpus is 12 documents. The claim is not size, it is **structure**: 112 relationship labels, 107 of them domain-specific. A bigger corpus is a credit spend, not a redesign.

**"Did you use Neo4j?"**
No, and here is the reasoning: the tenant already gives us a graph store that outlives the container. Neo4j would add a credential and a second datastore for no gain at this scale. It remains a drop-in.

**"What is the upload feature?"**
You can build your own brain from your own documents — a real parser (PDF, DOCX, text, code), per-file failure reporting, progress streaming, and it lands on the same dashboard scoped to your brain. **Verified end to end: ~32s from upload to a queryable brain.**

**"What did you NOT build?"**
Auth, connectors, billing, OCR, multi-tenancy. Say the list confidently — it is the Scope criterion, and it is worth 5 points.

**"What is the weakest part?"**
"Per-brain isolation is **data-level, not access-level**. `?dataset=` partitions the graph; it is not an authorisation boundary. Anyone who can reach the app can query any brain. For a hackathon that is a deliberate trade — no rubric line rewards auth — but it is the first thing that must change for anything real."

---

## 6. If you get stuck

- **Numbers you can always fall back on:** 12 documents · 219 nodes · 500 edges · 112 relationship labels · 1 credential · 2 services.
- **The sentence that always works:** "State lives outside the compute, because Render task runs are ephemeral containers with no ports."
- **If something breaks live:** switch to `PROVIDER=mock` and say so. "The network just died and the demo did not — that is the fallback working."

---

## 7. Two minutes before you walk in

```bash
cd /Users/_iayushsharma/Desktop/Ignite_Delhi
PY=/Users/_iayushsharma_/.workbuddy-ai/binaries/python/envs/hackathon/bin/python
$PY app.py &          # then open http://127.0.0.1:8000
$PY smoke.py          # expect 4/4 PASS
$PY warmup.py         # rehearses all four demo questions, timed
```

Then open the app once so the tenant connection is warm — the first question after idle is the slowest.

**Delivery:** 553 words ≈ 237s of your 300s. Every segment is inside its own budget, so you can check your pace at each timestamp. You have 63 seconds of slack — **use it for pauses, not extra content.**
