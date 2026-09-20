# Proposal: building this on the GitHub Student Developer Pack

**Question:** can the free student stack (Clerk, Heroku, Blackfire, Doppler and the rest) carry this product?

**Answer: yes for building and validating — and one of these offers solves the exact problem I flagged as the real blocker.** But there is a licensing catch that matters, and it is the first thing below because it changes how you use all of it.

---

## ⚠️ Read this first: the student pack is for non-commercial educational use

The pack's benefits are **licensed for non-commercial educational use**. Running a paid product on them is, for most partner offers, a terms violation — not a grey area.

**So the honest framing is:** use the pack to **build, test, and validate** at near-zero cost. When you have paying customers, migrate those workloads to commercial tiers. Do not build a business that structurally depends on student credits, because they lapse at graduation and the terms do not cover commercial use.

That said — **"build and validate at zero cost" is exactly what you need right now**, and it is worth a great deal.

---

## 1. The offers that actually matter, verified

| Service | What students get | Value | Verified |
|---|---|---|---|
| **Clerk** | **Pro plan free — 10,000 MAU**, includes Organizations (multi-tenancy) and Billing components | $240/yr | clerk.com/github-student-developer-pack |
| **Heroku** | **$13/month platform credit for 24 months** ($312 total) — spendable on Dynos, Heroku Postgres, Heroku Key-Value Store | $312 | heroku.com/github-students |
| **Blackfire** | Free Profiler — **supports Python 3.x**, profiling on production | €348/yr | blackfire.io/students |
| **Doppler** | Free plan, indefinitely — **3 users** | — | doppler.com/pricing |
| **GitHub Actions** | 2,000 min/month private (unlimited on public repos) | — | GitHub |
| **Namecheap / Name.com** | Free domain for a year | $10–20 | pack listing |
| **Azure for Students** | $100 credit + free services, no card required | $100+ | pack listing |
| **DigitalOcean** | $200 credit, 1 year — **⚠️ reported to be leaving the pack** | $200 | conflicting sources |
| MongoDB, Datadog, Codecov, Travis CI, Deepnote | Listed in the pack; individual terms not verified here | — | pack listing |

**Heroku's $13/month is the anchor.** It covers *exactly* a minimal production stack: Eco Dynos ($5, 1,000 dyno hours) + Mini Postgres ($5) + Mini Key-Value Store ($3) = **$13**. Managed, with backups, for 24 months.

**Clerk's 10,000 MAU is the other anchor**, and it is worth more than the money — see §3.

---

## 2. The architecture this enables

### Phase 1 — build and validate (student credits, ~$0 infrastructure)

```
Browser
  │
  ├── Clerk            auth + ORGANISATIONS (= tenants)      free, 10k MAU
  │
  ▼
Heroku Eco Dyno        FastAPI web tier                      $5  ┐
  │                                                              │
  ├── Heroku Postgres  relational + pgvector + RLS             $5  ├ $13/mo credit
  ├── Heroku Key-Value session/queue cache                     $3  ┘
  │
  ▼
Cognee (self-hosted, Apache-2.0)   embedded Kuzu/LanceDB, or Neo4j Aura free
  │
  ▼
DeepSeek V4.1 Flash    $0.15 / $0.60 per 1M off-peak    ← the only real cost
```

**The only line item you actually pay for is DeepSeek.** Everything else is covered. For build-and-validate that is **$5–20/month total**, and most of that is you testing ingestion repeatedly.

Add **Blackfire** on the Python web tier (it supports Python 3.x) and **Doppler** for secrets instead of `.env` files — both free, both genuinely useful, and both things a real deployment should have anyway.

### Phase 2 — first paying customers (commercial tiers)

| Item | Commercial cost |
|---|---|
| Clerk Pro | $25/mo (10,000 MAU included) |
| Heroku Eco + Postgres + KV | $13/mo — or Hetzner at ~$11 |
| DeepSeek | ~$1.20 per customer/month |
| **Fixed total** | **~$38/mo** |

At 10 customers on ₹1,700/month (≈$195):
- Cost: $38 fixed + $12 LLM = **$50**
- **Gross margin: ~74%**

The migration is a billing change, not a rewrite — same services, paid tiers.

---

## 3. The important part: Clerk Organizations solves the multi-tenancy gate

Yesterday I identified the real blocker on this project: **`?dataset=` isolation is data-level, not access-level.** Two customers in one Postgres means one customer's question can retrieve another's chunks. I said that was the gate before the first paying customer.

**Clerk's Organizations feature is most of that identity layer, free.**

| What you need | What Clerk gives you |
|---|---|
| A tenant entity | **Organization** — one per customer company |
| Users belonging to a tenant | Organization membership |
| Roles within a tenant (admin, member, viewer) | Organization roles and permissions |
| Tenant identity on every request | `org_id` in the session token |
| Switching between tenants | Built-in organization switcher |

So the work collapses from "build multi-tenancy" to:

1. **Set `org_id` from the Clerk session** on every request — a dependency, not a route-level check.
2. **Add a `tenant_id` column** to every table, defaulted from that session value.
3. **Enable Postgres row-level security** with a policy `tenant_id = current_setting('app.tenant_id')`.
4. **Namespace the graph per tenant** — a `tenant_id` prefix on the dataset name.
5. **Write one CI test that proves it**: authenticate as tenant A, ask a question whose answer exists only in tenant B's documents, assert you get nothing.

Clerk does not do steps 2–5 for you — **that is still real engineering.** But it removes the hardest part (identity, membership, roles, session propagation), which is what you would otherwise spend weeks building badly.

**This is the single most valuable thing in the pack for this project.** It is worth claiming for that reason alone.

---

## 4. The catches, stated plainly

**Student credits do not roll over.** Heroku's $13/month is a burn-down — unused credit expires monthly. You cannot bank it. Treat $13 as a hard ceiling, not a cushion.

**Heroku requires a credit card and charges overage.** Exceed $13 in a month and your card is billed. Set a spend alert on day one.

**Heroku credits cannot be used on a Team account.** Solo only, which suits you now but blocks collaboration later.

**Student credits expire at graduation.** The pack lapses at your next re-verification. Plan the migration before that, not after.

**DigitalOcean may be leaving the pack.** One source reports it is withdrawing and that the $200 credit expires at the end of next year. Do not architect around it — Heroku is the safer anchor.

**Some offers are stale.** GitHub paused new Copilot Student sign-ups in April 2026; verified-before-pause students keep it. Check each offer's live status before claiming.

**Blackfire's student tier excludes Quality and Security add-ons** — you get the Profiler, which is the useful part for a Python service.

**Terms still apply per provider.** "Non-commercial educational use" is the pack's framing; each partner has its own wording. Read the specific offer before running anything a customer depends on.

---

## 5. What I would actually do

1. **Claim Clerk first.** Free Pro with 10,000 MAU and Organizations. It is the highest-value item and it unblocks the one thing that actually gates this product.
2. **Claim Heroku second** — and apply at the *start* of a month, because the $13 begins on the 1st regardless of when you are approved, so a mid-month approval wastes most of the first month.
3. **Build the multi-tenancy layer properly** on Clerk Organizations + Postgres RLS + the CI isolation test. This is the work that turns a demo into a product, and it is now maybe a week instead of a month.
4. **Defer the timed offers.** DigitalOcean's credit starts on redemption and expires in 12 months; the free domain starts on redemption. Claim them when you have something to ship, not now.
5. **Pay only for DeepSeek while validating.** It is the one thing with no free tier, and it is cheap: $0.15/1M input, $0.60/1M output off-peak, with 50× cheaper cache hits.
6. **Set a migration trigger.** The moment you have a paying customer whose data is in the system, move that tenant to commercial tiers. Student credits are for proving the product, not for running it.

---

## Verdict

| Question | Answer |
|---|---|
| Can the free stack carry this? | **Yes for building and validating** — Heroku's $13 covers app + Postgres + Redis for 24 months, Clerk covers auth and tenants for 10,000 users. |
| What does it cost to validate? | **~$5–20/month**, almost entirely DeepSeek. |
| Does it solve the multi-tenancy gate? | **It removes the hardest half.** Clerk Organizations gives you tenants, membership, roles and `org_id`. You still build the Postgres RLS and graph namespacing. |
| Can you run the business on it? | **No** — the pack is non-commercial. Migrate to commercial tiers (~$38/mo fixed, ~74% margin at 10 customers) once you have paying customers. |
| Biggest risk? | **Building a business that structurally depends on credits that expire at graduation.** Use them to validate, then move. |

**The pack does not change the business case — the economics were already good.** What it changes is that **you can now build and prove the hardest part for free**, and Clerk hands you the tenant model that was the real blocker.

**Sources:** GitHub Student Developer Pack listing (education.github.com/pack) · Clerk student offer (clerk.com/github-student-developer-pack) and pricing (clerk.com/articles/clerk-pricing-explained) · Heroku for GitHub Students (heroku.com/github-students) · Blackfire for Students (blackfire.io/students) · Doppler pricing (doppler.com/pricing) · DeepSeek pricing (aipricing.guru, synced 2026-09-20) · pack value guide (perkstack.co, Sept 2026).
