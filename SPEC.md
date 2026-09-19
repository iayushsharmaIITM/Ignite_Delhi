# SPEC — Ignite Room Hackathon Build

**Date:** 2026-09-19 · **Status:** problem statement selection pending confirmation
**Builder:** solo · **Rounds:** Mentoring 15:30–16:30, Judging 17:00–18:00

---

## 1. The rubric, decoded

Two rounds, 25 points each, ten criteria. The single most important observation:

> **There is no "novelty" or "wow factor" criterion. Every point is awarded for engineering judgment.**

That inverts the usual hackathon strategy. A tight, complete, reliable small system beats an
ambitious half-working one. The kill list is not a compromise — it is a **scoring instrument**
(Scope & Prioritisation is worth 5 points on its own).

### Mentoring round — 15:30–16:30 · 5 min pitch + 2 min Q&A

| Criterion | Pts | What actually earns it |
|---|---|---|
| Problem Clarity | 5 | One sentence. Who hurts, and how, concretely |
| Design Decisions | 5 | Name the alternatives you *rejected* and why |
| Scalability | 5 | How it grows 100× without a rewrite |
| Technical Implementation | 5 | It works, and every part has a stated reason to exist |
| Scope & Prioritisation | 5 | What you deliberately did **not** build ← the kill list scores here |

### Judging round — 17:00–18:00 · 1 min pitch + 2 min demo + 2 min Q&A

| Criterion | Pts | What actually earns it |
|---|---|---|
| Production standards | 5 | Env config, no committed secrets, error states, README, health check |
| Technical Understanding | 5 | You can explain any line of code on demand |
| System Architecture | 5 | Two services, why, and where state actually lives |
| Completeness | 5 | The demo path works end to end, first time, no excuses |
| Reliability | 5 | Fallbacks, retries, and a demo that cannot die |

**Read the two lists together and the strategy writes itself:** the mentoring round scores the
*story*, the judging round scores the *product*. The 30-minute gap between them (16:30–17:00) is
the highest-leverage half hour of the day — it is where mentor feedback converts into judging points.

---

## 2. The problem statements

| PS | Tool | Sub-option | Shape |
|---|---|---|---|
| **PS-1** | Neo4j | a) Environmental Impact & Logistics | Model logistics + compute carbon impact |
| **PS-1** | Neo4j | b) Logistics & Supply Chain Transparency | Multi-hop provenance across a supply chain |
| **PS-2** | Cognee | Mini Company Brain | Ingest scattered company knowledge → one graph → ask it anything |
| **PS-3** | General | User Context Layer | Per-user memory that persists and improves across sessions |

---

## 3. Recommendation: **PS-2 — Mini Company Brain**

Built with **Cognee on Neo4j, orchestrated by Render Workflows**. Rationale:

1. **Highest probability of Completeness + Reliability (10 of 50 points).** The core is
   `remember()` and `recall()` — Cognee does the hard part.
2. **The wow moment is free.** Cognee ships a **built-in graph view**. There is nothing to build.
3. **Citations are free.** Answers come back citing their sources ("3 sources: call transcript ·
   contract §4.2 · #acme-renewal thread"). That is a credibility moment costing zero build time.
4. **It is the tool's canonical use case**, so Technical Understanding and Design Decisions are
   easy to speak to honestly.
5. **Two off-by-default features are a cheap, strong differentiator:** `CONTRADICTION_DETECTION`
   and `PROVENANCE_TRACKING`. Turning them on directly addresses the genuinely hard part of memory —
   facts change, and a static store cannot say which version is true. Almost nobody will do this.
6. **`run_in_background=True` gives a real orchestration story:** fan ingestion out across Render
   Workflows tasks, each in its own container. That is Scalability and System Architecture, earned.

### Why not the others

| PS | Verdict | Reasoning |
|---|---|---|
| PS-1a Environmental Impact | **Skip** | Logistics modelling *plus* emissions computation. Two domains in three hours, solo. Scope risk is the one thing the rubric explicitly punishes. |
| PS-1b Supply Chain Transparency | **Strong alternative** | Genuinely the most graph-native problem (`MATCH (a)-[:SUPPLIES*1..5]->(b)`), no LLM dependency so fewer failure modes, and the highest differentiation. Costs ~30 more minutes of schema and seed-data design. Choose this if you want to swing bigger. |
| PS-3 User Context Layer | **Viable** | Maps cleanly onto `session_id` (session memory) plus `self_improvement` bridging into permanent memory. Attractive because most teams will crowd PS-2. But "General" is vaguer, which puts Problem Clarity (5 pts) at risk. |

---

## 4. Architecture — uses all three provided technologies

```
Browser
   │
   ▼
Web tier (FastAPI)              ← serves UI, streams answers, /health
   │  triggers task runs
   ▼
Render Workflow                 ← ingest (parallel, retried) → retrieve → answer
   │  each task run in its own EPHEMERAL container
   ▼
Cognee Cloud tenant instance    ← the graph, the vectors, the LLM, the embeddings
```

**The load-bearing design decision:** Render task runs are ephemeral containers destroyed
when the run ends, so a file-based graph cannot survive between an `ingest` run and a
`retrieve` run. **We hit this directly** — the first ingest built a graph the next run
could not see. The fix is not to avoid ephemeral containers; it is to put the graph
somewhere containers cannot kill.

**Why the cloud tenant rather than local Cognee + Neo4j.** Both keep state outside the
container, which is the requirement. The tenant additionally owns the model and the
embeddings, so it removes two credentials from the critical path:

| | Local Cognee + Neo4j | Cognee Cloud tenant *(shipped)* |
|---|---|---|
| Credentials per container | 3 (LLM key, DB user, DB password) | **1** (an API key) |
| Model provider needed | Yes | No — the tenant has one |
| Volume / network config | Yes | No |
| Failure modes | More | Fewer |

At company scale, Neo4j is still the right answer for multi-hop traversal, and Cognee
speaks it natively (`GRAPH_DATABASE_PROVIDER=neo4j`) with no application change. It was
not enabled because it adds credentials to the critical path without changing what the
demo proves.

**Reliability layer:** the memory layer sits behind a `PROVIDER=mock|cognee` adapter. If Neo4j, the
LLM, or the network fails, the demo serves committed fixtures and still completes. This is the
concrete answer to "Reliability (5)".

---

## 5. Scope

**Tier 1 — must work (the demo path):**
- Seed a synthetic corpus of ~10 documents for a fictional company (tickets, meeting notes, a
  contract, a policy, chat threads)
- Build the graph once, ahead of time
- Ask a question → streamed answer **with citations**
- Show the built-in graph view

**Tier 2 — should work:**
- Parallel ingestion via Render Workflows (the Scalability story)
- One hand-written Cypher query shown live (proves *you* modelled the graph)
- Contradiction detection on a deliberately conflicting fact pair
- Loading / empty / error states, `/health`, README with screenshots

**Tier 3 — kill list (explicitly out, and worth 5 points to say so):**
- Real Slack / GitHub / Linear connectors
- Auth, multi-tenant, admin panel
- Live ingestion on stage
- Fine-tuning, custom embeddings, agent swarms

---

## 6. The 90-second demo

1. **Problem (15s)** — one sentence: company knowledge is scattered, so agents can't recall it.
2. **Action (40s)** — type one business question live. Let the answer stream. **Citations appear.**
3. **Proof (20s)** — open the graph view, then run one hand-written Cypher query live.
4. **Close (15s)** — parallel ingestion across ephemeral containers means this scales to a whole
   company. One sentence, then stop talking.

---

## 7. Timeline

| Clock | Phase | Gate |
|---|---|---|
| 11:00–11:15 | Lock scope, wire credentials | — |
| 11:15–11:30 | Copy skeleton, verify, deploy | **GATE 1: deployed by 11:30** |
| 11:30–12:15 | Core: corpus → graph → streamed answer with citations | — |
| 12:15–12:55 | Wow: graph view + Cypher panel + parallel ingestion | — |
| 12:55–13:25 | Seed + harden: error states, health, retries, contradiction | — |
| 13:25–13:55 | Production standards: README, `.env.example`, clean console | **GATE 2: feature freeze 13:55** |
| 13:55–14:30 | Build the 5-min pitch deck, rehearse twice | — |
| 14:30–15:00 | Buffer — bug fixing only | — |
| 15:00–15:30 | Warm every server and task. Final rehearsal. | **GATE 3: demo freeze 15:30** |
| **15:30–16:30** | **MENTORING ROUND** — 5 min pitch + 2 min Q&A | — |
| **16:30–17:00** | **Implement mentor feedback — highest-leverage 30 min of the day** | — |
| **17:00–18:00** | **JUDGING ROUND** — 1 min pitch + 2 min demo + 2 min Q&A | — |

---

## 8. Blocking needs — all resolved

| Need | Status |
|---|---|
| `LLM_API_KEY` | **Not required.** The Cognee Cloud tenant owns the model and the embeddings |
| PS confirmation | **Done** — PS-2 Mini Company Brain |
| Cognee Cloud credentials | **Done** — management key validated; tenant `Personal Workspace` is `active` |
| Graph store | **Done** — tenant instance, `company_brain` dataset, 219 nodes / 500 edges |
| Neo4j Aura instance | **Not needed** for the shipped scope (see §4) |
| GitHub repo URL | Still outstanding — deploy + continuous commit history |
| `RENDER_API_KEY` | Still outstanding — deploy only |

### How the key was validated

The management key was not a model-provider key. Testing it established that:

```
POST/GET https://api.aws.cognee.ai/api/tenants/current
  no auth  -> 401
  X-Api-Key -> 200      ← valid
```

which returned the tenant and, from `/api/tenants/current/service-url`, the dedicated
instance URL. Everything downstream uses `X-Api-Key` against that instance.
