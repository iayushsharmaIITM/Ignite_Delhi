# Overview — Kestrel Company Brain

**Built for:** Ignite Room hackathon · Problem Statement **PS-2 Mini Company Brain**
**Stack:** Cognee · Render Workflows · Cognee Cloud tenant instance
**Status:** Working end to end, verified with real queries.

---

## What was built

A company-brain service that ingests scattered business documents into a single knowledge
graph and answers cross-document questions **with citations**.

| | |
|---|---|
| Corpus | 10 synthetic documents — contract, incident ticket, two meeting notes, two policy docs, two chat threads, a handbook, an onboarding ticket |
| Graph | **219 nodes · 500 edges** |
| Ingest | 10 documents queued in **10.9s** across 3 parallel workers; graph ready in ~1 min |
| Latency | ~15–20s per answer, streamed |
| App code | ~600 lines |

### The headline result

Asked *"Why is the Bluepeak renewal at risk, and what have we promised them?"* it answered
from five documents at once and **caught a contradiction nobody asked it to find** — the
contract says the account is worth **$420k**, the meeting notes say **$480k**. It also
caught that a promised 25% credit exceeds the 20% threshold finance can approve alone.

A second question produced a **comparison table** showing the renewal date differs between
the contract (1 Dec 2026), the QBR notes (15 Dec 2026), and the internal paperwork dates.

---

## Key findings

**1. The provided key was a Cognee Cloud management key, not a model key.**
It failed as `LLM_API_KEY` (`AuthenticationError: Incorrect API key provided`). It
authenticates against `https://api.aws.cognee.ai` with an `X-Api-Key` header (401 without,
200 with). That yielded the tenant and its dedicated instance URL — which **removed the
need for any model-provider key**, because the tenant owns the model and embeddings.

**2. Ephemeral containers cannot hold the graph.**
Cognee's default backend is file-based. A graph built during an ingest run is destroyed
with the container. This is why the memory layer sits outside the compute tier.

**3. Querying mid-ingest returns a confident, wrong answer — not an error.**
Measured: it invented **"$39 per year"** for a $420,000 contract. `wait_ready()` now blocks
until the pipeline reports a terminal state.

**4. Two API traps that silently waste time.**
`dataset` params take a UUID (a name returns `422 uuid_parsing`), and the terminal state is
`DATASET_PROCESSING_COMPLETED` — an exact match on `"completed"` never fires.

---

## Files delivered

| File | Purpose |
|---|---|
| `README.md` | Architecture, quickstart, design decisions, the kill list |
| `PITCH.md` | 5-min mentoring script, 1-min judging script, 90-second demo path, Q&A bank |
| `SPEC.md` | Decision brief, updated to match what shipped |
| `app.py` | FastAPI web tier — streams answers, `/health`, `/graph` |
| `cognee_cloud.py` | The only file that talks to Cognee Cloud |
| `memory_layer.py` | `mock \| cloud` adapter — the demo safety net |
| `pipeline.py` | Render Workflow tasks (ingest fan-out, retrieve, answer) |
| `ingest.py` | Builds the graph from `corpus/` — run once, ahead of time |
| `corpus/` | 10 synthetic company documents |
| `static/index.html`, `static/graph.html` | Ask UI and force-directed graph view |

---

## Design decisions worth defending

- **Cloud tenant over local Cognee + Neo4j** — both keep state outside the container; the
  tenant removes two credentials from the critical path (1 credential per container, not 3).
- **Dropped the Cognee SDK from the deploy** — same HTTP API via a light `requests` client.
  Smaller image, faster build, fewer failure modes, identical behaviour.
- **`mock | cloud` provider adapter** — a dead network cannot kill a live demo.
- **Graph pre-built, never ingested on stage** — ingestion is the slowest, least
  predictable step.
- **Explicit kill list** — no connectors, no auth, no multi-tenancy, no live ingestion, no
  fine-tuning. Scope & Prioritisation is worth 5 points on its own.

---

## Open items

1. **GitHub repo** — needed for deploy and for a continuous commit history.
2. **`RENDER_API_KEY`** — needed to deploy via `render.yaml` (blueprint is written and
   validated: two services, web + workflow, Singapore region).
3. **Neo4j** — not required for the shipped scope. It becomes relevant at company scale for
   multi-hop traversal; Cognee supports it with no application change.

---

## Verified command reference

```bash
# build the graph (once, ahead of the demo)
python ingest.py --parallel 3

# run the web tier
python app.py                      # http://127.0.0.1:8000

# smoke checks
curl localhost:8000/health
curl localhost:8000/api/stats
curl -N "localhost:8000/api/ask?q=Why+is+the+Bluepeak+renewal+at+risk%3F"
```
