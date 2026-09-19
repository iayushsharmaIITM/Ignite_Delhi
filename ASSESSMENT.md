# Assessment — "a platform where users build their own company brains"

**Question asked:** evaluate this as a concept on four axes — (1) main technical/product/business
challenges, (2) is it feasible to build, (3) how does it avoid overlapping with the other 11
people on the same problem set, (4) how does it differentiate from existing company-brain apps.

**Verdict: don't pivot. Reframe the narrative instead.** Reasoning below.

---

## 0. A correction that reframes the competitive picture

"Cerebras" is a **wafer-scale AI chip company** — it is not a company-brain product. The real
competitive set is Glean, W.Brain, qKnow, GoSearch, and Microsoft Copilot.

The most important finding: **W.Brain (wbrain.io) is this exact concept, already shipping.**
Self-described "private, multi-tenant AI company knowledge base", self-serve signup, tiered
pricing ($39 / $169 / $649 per month), `tenant_id`-scoped isolation, Kafka ingestion, Qdrant
vectors, connectors for Jira/Slack/Drive/Notion.

Second finding: **Cognee 1.0 is itself the platform.** Its own announcement positions it as
"the open-source memory platform for AI agents", with Managed Cloud, self-hosting, a free cloud
key, MCP integration, and the COGX portability format — plus 6M memories/month across 100+
companies and a Bayer case study. Building "a platform on top of Cognee that lets users create
company brains" means building the layer Cognee already occupies.

---

## 1. The challenges

### Technical
- **Tenant isolation and permission mirroring — the hardest problem.** The brain must never
  answer using documents the asker cannot see. This is the core of Glean's moat. Failure here is
  a security incident, not a bug.
- **Cold start.** A new tenant's brain is empty, so the product is worthless until fed. Our demo
  works because the corpus was curated and deliberately seeded with contradictions. A real user
  uploads three messy PDFs and gets a confidently empty answer. We have already measured the
  adjacent failure: a mid-ingest query invented **"$39 per year"** for a $420,000 contract.
- **Per-tenant cost.** Each tenant owns an LLM, embeddings, vector store, graph and object
  storage. An idle tenant costs real money. W.Brain's $39/month for 5GB implies thin margins.
- **Provisioning latency.** "Create your brain" cannot be instant if it means standing up an
  instance.

### Product
- Copilot is bundled with M365 and already paid for. "Why not just use ChatGPT with my files?"
  must be answerable in one sentence.
- Trust is binary: one confident wrong answer and users stop.
- Contradiction detection requires contradictions. Most corpora are messy, not contradictory.

### Business
- **Distribution is the moat, not technology.** Cognee is open-source — anyone can build the
  same wrapper in a weekend.
- Squeezed from both ends: Glean (enterprise, 100-seat minimum) above, W.Brain ($39/mo
  self-serve) below, Microsoft bundling at zero marginal cost.
- Enterprise wants SOC2/SSO/DPA/VPC; self-serve wants instant value. That is two products.

---

## 2. Feasibility

**As a demo — yes, and ~80% already exists.**
`ingest.py --dataset X` and `ingest_document(dataset=...)` *are* per-brain isolation. We proved
three containers writing three datasets into one shared graph. Missing only: auth, an upload UI,
and a "create brain" flow. Hours of work, not a rewrite.

**As a business — buildable, but entering at the worst point.**
The incumbents' moat is connectors plus permissions: ~80% of the real work, and none of the fun.

---

## 3. Standing out from the other 11

"A platform for company brains" **is** genuinely orthogonal to eleven people each building one
company brain. That part is sound.

**But the rubric does not pay for it.** Ten criteria × 5 points; no novelty or wow criterion.

| | Effect |
|---|---|
| Helps | Scalability (+5), System Architecture (+5) |
| Hurts | Completeness (−5), Reliability (−5), Scope & Prioritisation (−5) |

Net: trades ~10 points of *done and reliable* for ~10 points of *architecturally interesting*,
at much higher variance. We currently hold a verified, failure-tested system. Variance is the
enemy when already holding a winning hand.

**The trade is also unnecessary.** Per-brain isolation across ephemeral containers is already
documented and demonstrated — that *is* the multi-tenant story, at zero new code. Frame it as:
**"the platform is the architecture, not a signup form."**

---

## 4. Differentiation

| Product | Position | Angle |
|---|---|---|
| Glean | Enterprise AI search, 100-seat min, no public pricing | Self-serve gap exists, but its moat is connectors + permissions |
| W.Brain | "Private, multi-tenant AI company knowledge base", $39–649/mo | **This is the exact concept, already shipping** |
| qKnow / GoSearch | RAG + knowledge-graph platforms | Same general space |
| Microsoft Copilot | Bundled with M365 | Already paid for; good enough for most |
| Cognee | "The open-source memory platform for AI agents", managed cloud | **We would be reselling their platform** |

**Blunt finding:** against W.Brain we are not differentiated at feature level, and the platform
layer we would build is the one Cognee already occupies. Do not compete there.

**Where differentiation actually exists — and we already own #1:**
1. **Contradiction detection as the product, not a feature.** Nobody in that table sells "your
   documents disagree, here is exactly where." RAG structurally cannot: it retrieves similar
   text and cannot report that two documents conflict. Built and working.
2. **Vertical depth over horizontal generality.** "Company brain" is crowded; "contradiction and
   provenance for M&A due diligence / audit / compliance" is not.
3. **Ownership and portability** — COGX export is a real enterprise anti-lock-in story.

---

## Recommendation

1. **Do not pivot.** Keep the verified system. Add the platform framing verbally — free, zero risk.
2. If the platform must be *visibly* real, the cheapest credible version is a thin "create a
   brain" flow calling `ingest.py --dataset <name>`. 1–2 hours, **only after the core demo is
   bulletproof, and it must not touch auth or isolation.** Half-built multi-tenancy scores worse
   than none, because it damages precisely the Completeness and Reliability points we are
   currently winning.
3. **For the business idea:** the wedge is contradiction detection inside a specific vertical,
   not a general-purpose platform.
