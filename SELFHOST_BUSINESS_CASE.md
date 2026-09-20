# Self-hosted Cognee + DeepSeek + open-source auth: does it work as a business?

**Question:** can I host this cheaply, use open-source auth, run open-source Cognee, call DeepSeek V4.1 Flash, and sell it to customers?

**Answer: yes, and the economics are materially better than the Cognee Cloud route — roughly 80–93% gross margin instead of ~60%.** But the thing that gates this is not cost. It is multi-tenancy, and I'll explain why that's the real work.

---

## 1. The three pieces, and what they actually cost

### DeepSeek V4.1 Flash — the price that changes the maths

| | Off-peak | Peak (2×) |
|---|---|---|
| Input (cache miss) | **$0.15** / 1M | $0.30 / 1M |
| **Input (cache hit)** | **$0.003** / 1M | $0.006 / 1M |
| Output | **$0.60** / 1M | $1.20 / 1M |

**Peak windows are 01:00–04:00 and 06:00–10:00 UTC, Mon–Fri. Everything else, including all weekend, is half price.**

⚠️ **In IST that is 06:30–09:30 and 11:30–15:30** — so a meaningful slice of Indian business hours is at **double** the price. Budget a blended rate, not the off-peak number. This is the detail that quietly breaks a spreadsheet.

**Automatic prefix caching is the big lever.** Cache hits are **50× cheaper** than cache misses. A knowledge-graph query sends a large, stable context; if that context is cached, per-query input cost collapses from ~$0.0045 to ~$0.0001. Design the prompt so the graph context sits in a stable prefix and this alone can halve your LLM bill.

### Self-hosted Cognee — free, and lighter than expected

Cognee is **Apache-2.0**. The shipped `docker-compose.yml` uses profiles:

| Service | Profile | Port |
|---|---|---|
| `cognee` (core API) | *always* | 8000 |
| `postgres` (+ pgvector) | `postgres` | 5432 |
| `neo4j` | `neo4j` | 7474 / 7687 |
| `redis` | `redis` | 6379 |
| `frontend` | `ui` | 3000 |

**The defaults are embedded** — SQLite for relational, LanceDB for vectors, Ladybug for the graph. So the *minimum* is **one container**. A production setup wants Postgres + a graph store, but you are not forced into a four-service stack on day one.

### Hosting — genuinely cheap

| Provider | Spec | Price/mo |
|---|---|---|
| **Hetzner Cloud** | 2 vCPU / 4 GB / 40 GB NVMe | **~$4.50** |
| Hetzner (production tier) | 2 vCPU / 8 GB / 80 GB NVMe | ~$11 |
| Contabo | 4 vCPU / 8 GB / 200 GB SSD | ~$4.35 |
| Vultr HF | 1 vCPU / 1 GB | $2.50 — **too small for a database** |

**Hetzner at ~$11/month is the right starting point.** It runs the app, Postgres and Cognee on one box. Contabo gives more specs for less but has 48–72 hour support queues.

### Open-source auth — solved, and not the hard part

**Authentik** (Python, modern DX), **Zitadel** (Go, multi-tenant by design), **Keycloak** (complete, heavy), **SuperTokens**, **Ory Kratos**. All free, all mature. Pick **Zitadel or Authentik** and move on.

---

## 2. The unit economics, with the actual numbers

### Cost to serve one customer per month

| Item | Assumption | Cost |
|---|---|---|
| LLM — ingestion | 100 docs, ~1.5M input + 150K output | $0.32 |
| LLM — queries | 100 queries × ~30K in / 800 out | $0.50 |
| **LLM subtotal (off-peak)** | | **~$0.82** |
| Blended for IST peak overlap | ~1.5× | **~$1.20** |
| With prefix caching working well | input largely cached | **~$0.40** |

**Take $1.00–1.50 per customer per month as the honest planning figure.**

### Infrastructure, shared across everyone

| Item | Cost/mo |
|---|---|
| Hetzner 8 GB (app + Postgres + Cognee + auth) | $11 |
| Backups / object storage | $3 |
| **Total** | **~$14** |

### The margin, at scale

| Customers | Infra/cust | LLM/cust | Total cost | Revenue @ $20 | **Gross margin** |
|---|---|---|---|---|---|
| 5 | $2.80 | $1.20 | $4.00 | $100 | **80%** |
| 20 | $0.70 | $1.20 | $1.90 | $400 | **90%** |
| 100 | $0.14 | $1.20 | $1.34 | $2,000 | **93%** |

**Compare with the Cognee Cloud route I costed earlier: ~60% margin.** The self-hosted path is roughly **1.5× better**, for three reasons:

1. DeepSeek is **5–10× cheaper per token** than what the cloud tenant charges for.
2. **No $5/workspace fee.**
3. A **fixed ~$14** replaces a per-customer variable cost.

**Even at five customers you are at 80% gross margin.** That is a real business, not a hobby.

---

## 3. The honest problems — and the one that actually gates this

### ⚠️ Multi-tenancy is the real work, not the cost

This is the thing to think hardest about. **Per-brain isolation in this project is data-level, not access-level.** `?dataset=` partitions the graph; it is *not* an authorisation boundary. Anyone who can reach the app can query any brain.

For a hackathon that was a defensible trade. **For paying customers it is disqualifying.** If two companies' documents live in one Postgres and one graph, and one customer's question can retrieve another's chunks, you have a data breach, not a bug.

What it takes:
- A tenant column or schema on every table, enforced in the query layer — not in the route handler
- Row-level security in Postgres, or schema-per-tenant
- Per-tenant graph namespacing
- Auth that carries tenant identity into every data access, not just into the session
- A test that proves tenant A cannot retrieve tenant B's chunk, run in CI

**This is a genuine engineering project.** Not a config change, and not something to bolt on after the first customer.

### You now own the infrastructure

Postgres backups, migrations, graph-store upgrades, uptime, security patches, monitoring. That is precisely what you were paying Cognee to do. At $400 MRR it is affordable; it is also real work, and it is the reason managed services exist.

### The architecture claim changes

The whole design of this project rested on *"state lives in the tenant, so ephemeral containers need one credential."* Self-hosting means you now run Postgres + a graph store + Redis + auth. `render.yaml`'s clean two-service shape becomes three or four containers, and the "one credential" argument no longer holds. **Be ready to say that plainly** — it is a change of design, not a detail.

### Data residency

Indian business customers may require data to stay in India. Hetzner is EU/US; Contabo has Singapore/Tokyo. For Indian residency you want an Indian provider — **E2E Networks, NeevCloud, or AWS Mumbai**. That costs more than Hetzner, but it is a purchase requirement for some buyers, not a preference.

### Smaller ones

- **DeepSeek has no free tier** and tighter rate limits at peak.
- **Content filtering differs from Western providers** — worth checking against enterprise requirements before promising anything.
- **Peak pricing lands on Indian working hours.** Budget blended.

---

## 4. What I would actually do

1. **Start self-hosted on one Hetzner box at ~$11/month**, with embedded stores. Do not build a four-service stack before you have a customer.
2. **Use Authentik or Zitadel for auth** — free, mature, done.
3. **DeepSeek V4.1 Flash with prefix caching designed in from the start.** Structure prompts so graph context is a stable cached prefix; that is a 50× saving on the largest input component.
4. **Do the multi-tenancy work before the first paying customer**, not after. Postgres row-level security + per-tenant graph namespacing + a CI test that proves isolation. This is the gate.
5. **Price at ₹1,499–1,999/month, billed annually** — the researched sweet spot for Indian SaaS, and the margin supports it comfortably.
6. **Keep the managed path as an option.** Cognee Cloud at $1/1M is expensive per token but removes all operational burden. For your first two or three customers that may genuinely be worth it while you build the isolation layer.

---

## The verdict

| Question | Answer |
|---|---|
| Can it be hosted cheaply? | **Yes** — ~$11–14/month for the whole stack on Hetzner. |
| Open-source auth? | **Yes** — Authentik, Zitadel, Keycloak. Solved problem. |
| Open-source Cognee? | **Yes** — Apache-2.0, and the minimum is one container. |
| DeepSeek V4.1 Flash via API? | **Yes** — $0.15/$0.60 per 1M off-peak, with 50× cheaper cache hits. |
| Is it a business worth customers? | **Yes at 80–93% gross margin.** Better than the managed route. |
| **What actually gates it?** | **Multi-tenancy.** Data-level isolation is not access-level isolation, and that is the difference between a demo and a product. |

**The economics are not the problem — they are unusually good.** The problem is that selling a shared knowledge graph to multiple companies requires real tenant isolation, and this codebase deliberately does not have it yet. That is the first thing to build, and it is worth building because everything else here works.

**Sources:** DeepSeek pricing (aipricing.guru, synced 2026-09-20; official rate card at api-docs.deepseek.com) · Cognee Docker deployment docs (docs.cognee.ai) · Cognee pricing page (cognee.ai/pricing) · VPS cost comparison (serverhabit.com, May 2026) · Indian SaaS pricing research (rajeshrnair.com, Apr 2026).
