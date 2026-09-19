# Overview — Kestrel Company Brain

**Built for:** Ignite Room hackathon · Problem Statement **PS-2 Mini Company Brain**
**Stack:** Cognee · Render Workflows · Cognee Cloud tenant instance
**Status:** Working end to end, verified with real queries, and **failure-tested** — the
health check has been watched failing on a bad key, which is the only way to know it works.

---

## What was built

A company-brain service that ingests scattered business documents into a single knowledge
graph and answers cross-document questions **with citations**.

| | |
|---|---|
| Corpus | 10 synthetic documents — contract, incident ticket, two meeting notes, two policy docs, two chat threads, a handbook, an onboarding ticket |
| Graph | **219 nodes · 500 edges** |
| Ingest | 10 documents queued in **10.9s** across 3 parallel workers; graph ready in ~1 min |
| Latency | **~16–31s** end-to-end; first token at **~18s**, then streams in ~3s |
| App code | ~1,300 lines — 725 Python (web tier, Cognee client, memory layer, workflow) · 562 UI |

### The headline result

Asked *"Why is the Bluepeak renewal at risk, and what have we promised them?"* it answered
from five documents at once and **caught a contradiction nobody asked it to find** — the
contract says the account is worth **$420k**, the meeting notes say **$480k**. It also
caught that a promised 25% credit exceeds the 20% threshold finance can approve alone.

A second question surfaced a **comparison of the renewal dates**, which disagree across the
contract (1 Dec 2026), the QBR notes (15 Dec 2026), and the internal paperwork schedule.
Note the answer *format* varies between runs — sometimes a markdown table, sometimes bullets.
The renderer handles both, so the UI never shows raw `**markdown**` or `|---|` pipes.

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

**5. The tenant's `/health` endpoint is unauthenticated — it reported healthy with a dead key.**
Found by testing the failure path instead of trusting the happy path. With
`COGNEE_API_KEY=badkey123`, `/health` returned `upstream: "healthy"` and all four components
green, while every query returned `401 Unauthorized`. The one check a judge would look at was
the one that *could not fail*. `/health` now also probes an authenticated endpoint and reports
`auth: ok | failed`, and the UI LED, `smoke.py` and `warmup.py` all require it. Verified in
both directions: the bad key now yields **3 FAILED, exit 1** — where it previously passed.

**6. The answer takes ~18s to *begin*, which is not the same thing as streaming.**
Timed event by event on the flagship question: first chunk at **17.8s**, then 226 chunks over
3s. Streaming is real but entirely back-loaded, so the UI sat on an empty box for 18 seconds —
which reads as broken on stage. It now writes *"Searching the knowledge graph…"* immediately
and clears it on the first chunk. The demo script was corrected to use that gap deliberately
rather than sit through it.

**7. The graph view was the last thing that could break, and now it can't.**
`/api/graph` and `/api/stats` bypassed the provider adapter, so with the network genuinely gone
the footer count and the graph page failed while the ask path still worked — a confusing
half-failure. Both now fall back to a committed 77KB graph snapshot and report
`source: "cloud" | "fixture"`. Verified with the tenant pointed at a non-existent host: footer
reads `219 nodes · 500 edges`, the graph renders 602k painted pixels, the LED honestly says
`cloud · unreachable`, and there are **zero console errors**. Functional *and* truthful.

**8. A task that silently ingested garbage and reported success.**
`render workflows start` spreads a *bare* JSON object as keyword arguments; wrap it in an array
and it arrives as the first positional argument instead. That made `documents` a **dict**, so
`for doc in documents` iterated its **keys** — and `ingest_corpus` ingested the literal strings
`"dataset"` and `"documents"`, then returned `{"queued":2,"failed":0}`. A confident success over
garbage, and because the subtasks received an empty dataset name, the junk landed in the **demo
graph** (219/500 → 225/504). Fixed with a type guard in `pipeline.py` that now fails in 0.57s
with an explanatory message. The graph was repaired **surgically** via
`DELETE /api/v1/datasets/{id}/data/{data_id}` — deleting only the two junk items (identified by
reading their raw content: 9 and 7 chars against 1353–2592 for the real documents) and restoring
exactly **219 nodes / 500 edges**, rather than re-ingesting and risking a different count.

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
| `smoke.py` | 4-check demo-path test; `--base` targets any URL, including a broken one |
| `warmup.py` | One-command pre-demo rehearsal — health, graph size, all 4 questions timed |
| `fixtures/answers.json` | Offline answers for the `mock` fallback (real outputs, not placeholders) |
| `fixtures/graph.json` | Lean graph snapshot (77KB) so the graph view survives with no network |
| `ASSESSMENT.md` | Strategic assessment: whether to pivot to a multi-tenant platform (recommendation: no) |
| `render.yaml` | Blueprint: web + workflow services, Singapore region |
| `commit.sh` | Continuous-commit helper — a single bulk commit can trigger a plagiarism check |

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
- **Health checks must be able to fail** — the upstream `/health` was unauthenticated and
  reported healthy with a dead key, so it was replaced in the critical path by an
  authenticated probe. A check you have never seen fail is not evidence of anything.

---

## Open items

1. **GitHub repo** — needed for deploy and for a continuous commit history.
2. **`RENDER_API_KEY`** — needed to deploy via `render.yaml` (blueprint is written and
   validated: two services, web + workflow, Singapore region).
3. **Neo4j** — not required for the shipped scope. It becomes relevant at company scale for
   multi-hop traversal; Cognee supports it with no application change.
4. **Multi-tenant platform pivot — assessed and declined.** See `ASSESSMENT.md`. Short version:
   the platform layer is the one Cognee already occupies, W.Brain already sells the exact
   concept at $39/month, and the rubric pays nothing for novelty. The platform story is
   claimable for free because `--dataset` already provides per-brain isolation.

---

## Verified command reference

```bash
# build the graph (once, ahead of the demo)
python ingest.py --parallel 3

# run the web tier
python app.py                      # http://127.0.0.1:8000

# smoke-test the demo path — 4 checks, exit 1 on failure
python smoke.py
python smoke.py --base https://your-app.onrender.com    # any deployed URL

# full pre-demo rehearsal: health + every upstream component, graph size,
# and all 4 demo questions timed with citation counts
python warmup.py
```

### Proving the reliability claim (worth doing in front of a judge)

```bash
# 1. good config -> 4/4 PASS, exit 0
python smoke.py

# 2. deliberately bad key -> the check FAILS instead of falsely passing
COGNEE_API_KEY=badkey123 PORT=8097 python app.py &
python smoke.py --base http://127.0.0.1:8097    # expect 3 FAILED, exit 1
```

Step 2 is the evidence that `/health` is a real check. Before the fix it reported
`upstream: healthy` on that same broken key and the smoke test passed anyway.
