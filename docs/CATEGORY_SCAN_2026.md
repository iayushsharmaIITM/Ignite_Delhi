# Category scan — the 2026 feature bar and the connector plan

**Asking question:** what must an app in this category have in 2026, and which
connectors make Kestrel stand out rather than merely catch up?

**Method and its limits.** The `feature-dev` and `better-harness` plugins were listed
as unavailable for this session and were not invoked, so this is web research plus a code
inventory, not a plugin run. Every claim in the "Kestrel today" column was checked against
this working tree and cites the file — because the interesting findings came from the check,
not from the articles. Connector counts and the evaluation checklist are the sources' claims,
dated, and are attributed rather than absorbed.

**What Kestrel is:** a signed-in, multi-tenant company brain — upload or connect
documents, ask across them, get an answer whose citations open to the highlighted passage.
AGPL core, flat per-company pricing, target buyer is a 10–100 person services firm.

---

## 1. The 2026 bar, scored against this codebase

The evaluation checklist in [Onyx's 2026 enterprise-search guide](https://onyx.app/insights/enterprise-search-tools-2026)
is the most useful public one, and it maps cleanly onto what this repo already does.

| # | Criterion (2026 buyer expectation) | Kestrel today | Evidence |
|---|---|---|---|
| 1 | **Grounded, index-based RAG with citations** | **Strong — this is the differentiator.** Answers carry openable, passage-highlighted citations; "no fabricated citations" is a cardinal product invariant, and no semantic caching is allowed on the citation path | `AGENTS.md` product invariant; `orchestrator.py` citation prewarmer; `/api/source` resolves and re-checks the path is inside `corpus/` (`app.py:2142`) |
| 2 | **Permission inheritance from the source system** | **Partial, and the gap is structural.** Authorization is *brain*-level (`brain_access`, `brain_grants` with `principal_type`/`principal_id`/`permission`). There is no document-level ACL, so a Google Doc readable by two people answers for the whole org once its brain is shared | `migrations/versions/0002_identity_provenance_jobs.py:113` (`brain_grants`), `storage.py:661` (`brain_access`) |
| 3 | **Connector breadth and depth** | **2 providers.** `google` (Gmail + Drive, read-only) and `slack` (channel history, read). `dropbox` and friends are explicitly rejected as unknown providers | `connectors.py:42` `PROVIDERS = {"google", "slack"}` |
| 4 | **Deployment model: cloud, self-hosted or hybrid** | **Yes — genuinely ahead here.** AGPL core, self-host OSS brain or the cloud tenant, bring-your-own OAuth client | `compose.oss.yml`, `.env.oss`, `OSS_STACK_AND_COMPETITORS.md` |
| 5 | **Model flexibility (no single-LLM lock)** | **Yes.** Provider routing in `llm.py`, `PROVIDER=mock\|cloud`, BYO keys | `llm.py`, `/health` reports `llm.active_model` |
| 6 | **Customizability — can a customer build a connector** | **No.** `PROVIDERS` is a Python dict; adding one is a code change and a deploy. There is no manifest or plugin contract | `connectors.py:42` |
| 7 | **Security & compliance: SOC 2, GDPR/HIPAA, encryption, audit trail** | **Not yet, and no audit log.** Secrets are env-only and the vault stores tokens as Fernet ciphertext, but there is no query/answer audit trail — which is the first thing a 50-person firm's accountant asks about | `connectors.py` vault; no audit table in the live schema |
| 8 | **Enterprise features: SSO, RBAC, analytics, admin, white-label** | **Mixed.** Clerk SSO (Google) and org/person identity: yes. Usage analytics: yes (`/api/usage`). RBAC: brain-level only. Admin console and white-label: no | `auth.py`, `app.py:956` |
| 9 | **Answer-quality measurement (evals) and a trust loop** | **Missing — the most surprising gap.** There is no eval harness, golden question set, or faithfulness check anywhere in the repo. Worse, the trust loop is *decorative*: `MessageActions` (with Helpful / Not helpful) is exported and **imported by nothing**, and there is no server endpoint to record a vote | `frontend/src/components/Animations.tsx:640` has no importer; no feedback route in `app.py` |

**Read of the table.** Kestrel is strong on exactly the axis incumbents are weakest on —
verifiable citations, self-hosting, model freedom — and absent on the two axes that separate
a product from a prototype in this category: **permission depth** and **measured answer
quality**. Connector count is the loudest gap but not the most damaging one; a 50-connector
tool that cannot prove its answers is what Kestrel is positioned against.

---

## 2. The connector landscape, with the numbers

| Product | Connectors | Source |
|---|---|---|
| Glean | 100+ (broadest in market) | Onyx 2026 guide |
| GoSearch | 100+ | Onyx 2026 guide |
| Kore.ai | 100+ (250+ across platform) | Onyx 2026 guide |
| Guru | "hundreds", Slack/Teams-centric | Onyx 2026 guide |
| **Onyx (open-source, closest analogue)** | **40+** — Slack, Confluence, Jira, Google Drive, SharePoint, Salesforce, GitHub, Notion, HubSpot, Zendesk | Onyx 2026 guide |
| Coveo | 17 native + crawler | Onyx 2026 guide |
| Microsoft Copilot | Deep M365 + Box, Confluence, Drive, Salesforce, ServiceNow | Onyx 2026 guide |
| Google Vertex AI Search | Jira, Confluence, Salesforce, web, intranets | Onyx 2026 guide |
| ChatGPT Enterprise | Drive, SharePoint, GitHub, Confluence only | Onyx 2026 guide |
| **Kestrel** | **2** | `connectors.py` |

The useful inference is not "build 40". Onyx reaches 40 because it sells to US enterprise;
its list is SharePoint/ServiceNow/Salesforce-heavy, which is close to irrelevant to a 25-person
Indian CA/law/agency firm. Matching a connector *count* is a losing game; matching the
*workflow* of the buyer is winnable with a fraction of it.

---

## 3. The connector set that actually makes this one stand out

Ranked for the stated buyer (10–100 person services firms: legal, accounting/CA, agencies,
consultancies, IT services), not for an RFP.

**Tier 1 — without these the product cannot answer the question the buyer opens it for.**

1. **WhatsApp Business** — the highest-conviction gap on this list and the one no US
   incumbent has. Client communication, approvals and scope changes for Indian services
   firms live in WhatsApp threads. Every competitor in §2 has zero WhatsApp coverage, and
   it is where "what did the client actually agree to" is answered.
2. **Zoho Mail / Zoho Docs / Zoho Projects** — Zoho is the default office suite for this
   segment at this size, and no product in §2 lists a Zoho connector. This is a
   differentiation claim that is literally true and unmatchable by Glean/Copilot/Vertex.
3. **Notion** — the modern-services default for internal docs; also the cheapest way to look
   credible in a demo, and it is in Onyx's set.
4. **Xero / Tally** — the accounting spine for the CA/bookkeeping half of the target market.
   "Which invoices are overdue and what did the client say about it" is a killer demo query
   that combines two sources.

**Tier 2 — breadth for the enterprise-shaped end of the funnel.**

5. **Google Calendar + Meet transcripts** (the Google connector already exists; this is a
   scope extension, not a new integration).
6. **Microsoft Teams + SharePoint** — required the moment a 100-seat prospect has any
   Windows/M365 footprint.
7. **Jira, Linear, GitHub** — for the IT-services/agency segment; also the sources that make
   "what is blocked" answerable.
8. **HubSpot** — the CRM question ("what did we promise this account") is the one that sells
   to the founder, and it is in Onyx's list.

**Tier 3 — the wedge that turns connectors into a moat.**

9. **A public connector contract.** Today `PROVIDERS` is a Python dict (`connectors.py:42`),
   so a customer with an internal system cannot add it without a fork. A declarative
   connector manifest (auth kind, scope set, entity fetch, ACL passthrough, sync cadence) is
   how a small team beats 100-connector incumbents: their connectors are theirs, yours are
   writable by the people who need them. This is the highest-leverage item in this document
   and it is architecture, not volume.

---

## 4. The standout thesis, in priority order

Four things, in the order that gets a 2-person team furthest per unit of work. Each is
chosen because incumbents structurally cannot follow cheaply.

**1. Permission-aware citations — the honest version of "trust".**
Nearly every product in §2 cites *a* source. Very few can answer "you saw this because
the document is shared with your team, and here is who else can see it." That requires
document-level ACL (§1 row 2), which is missing. It is also the only feature here that
deepens the existing invariant instead of adding a new surface. **Build this first.**

**2. An eval harness and a real feedback loop.**
There is no answer-quality measurement in the repo, and the thumbs UI is dead code with no
endpoint behind it (§1 row 9). This is the cheapest credible win in the whole document: a
golden question set per brain, a faithfulness check that fails CI when an answer cites a
passage that does not support it, and one `POST /api/feedback` that makes the existing
buttons real. Without it, "our answers are better" is unauditable — and the citation
invariant, which *is* real, gets no credit.

**3. An MCP server, so the brain is reachable by agents, not only by humans.**
2026's clearest shift is that the consumer of company knowledge is increasingly another
agent ([MCP server guides](https://toloka.ai/blog/best-mcp-servers-for-ai-agents/),
[enterprise MCP gateways for agent governance](https://www.snowflake.com/en/blog/engineering/enterprise-mcp-gateway-ai-agent-governance/)).
Self-hosted knowledge tools with a first-party, **permission-aware** MCP server are still
rare, and Kestrel is unusually well placed: the API is already documented and machine-readable
(`ops/api_readiness.py`, `ClerkBearer`, per-route error contract), and identity is already
org+person. The gap is that the contract is not yet agent-grade — **59.7% weighted, with
`E1` still Critical and `P1` (0 of 39 success responses carry a schema) the real blocker**
(`docs/api-analysis/agent-readiness.md`). Ship the schemas, then the MCP server on top of the
same `require_tenant()` path, and the claim becomes "the only self-hosted company brain your
agents can query without leaking across tenants."

**4. Own the segment the incumbents' connector lists prove they ignore.**
Zoho + WhatsApp + Tally/Xero + INR pricing + GST-shaped document handling is a connector
portfolio no product in §2 has, because none of them is built for it. That is a category
claim, not a feature — and it is cheaper to defend than a citation-quality arms race.

---

## 5. What not to build

- **Do not chase connector count.** 40+ is Onyx's number for a different buyer; matching it
  spends the whole roadmap on plumbing and buys parity, not distinction.
- **Do not add a general agent framework or a multi-agent builder.** `orchestrator.py` already
  does the retrieval routing that matters here; the category's agent surface is reached via
  MCP (§4.3), not by shipping a builder nobody asked for.
- **Do not build a browser extension, a mobile app, or an internal-search-style admin console**
  before document-level ACL and evals exist. Those are the two things that make the rest
  defensible.
- **Do not advertise SOC 2 before there is an audit trail.** Row 7 is a real gap; the honest
  sequence is audit log → then compliance.

---

## 6. Sources

- [Best Enterprise Search Tools for 2026 — Onyx](https://onyx.app/insights/enterprise-search-tools-2026) — connector counts and the 9-point evaluation checklist used in §1/§2
- [Best Enterprise RAG Platforms for 2026: A Buyer's Guide — Onyx](https://onyx.app/insights/enterprise-rag-platforms-2026)
- [Top 10 enterprise use cases for RAG models in 2026 — Glean](https://www.glean.com/perspectives/top-10-enterprise-use-cases-for-rag-models-in-2026)
- [Enterprise AI search in 2026: what you need to know — Dust](https://dust.tt/blog/enterprise-ai-search)
- [Best enterprise AI search software: top 4 in 2026 — Instaclustr](https://www.instaclustr.com/education/vector-database/best-enterprise-ai-search-software-top-4-in-2026/)
- [Enterprise AI Assistant Options 2026 — Viewpoint Analysis](https://www.viewpointanalysis.com/post/enterprise-ai-assistant-options-2026)
- [Best MCP servers for AI agents in 2026 — Toloka](https://toloka.ai/blog/best-mcp-servers-for-ai-agents/)
- [Enterprise MCP Gateway Guide: governing AI agents — Snowflake](https://www.snowflake.com/en/blog/engineering/enterprise-mcp-gateway-ai-agent-governance/)
- [Best RAG evaluation tools in 2026 — Braintrust](https://www.braintrust.dev/articles/best-rag-evaluation-tools)
- [Enterprise RAG in 2026: knowledge systems, AI agents, trust — Glorious Insight](https://gloriousinsight.co.in/enterprise-rag-2026-knowledge-systems-ai-agents-trust/)
- [Onyx review 2026: enterprise search & RAG assistant — PromptQuorum](https://www.promptquorum.com/power-local-llm/onyx-review)
- [Onyx AI review 2026 — Teamazing](https://www.teamazing.com/blog/onyx-ai-enterprise-review-2026/)
