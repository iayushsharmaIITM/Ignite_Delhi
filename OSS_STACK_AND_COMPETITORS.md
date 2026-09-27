# Open-source Cognee, one swappable API key, free connectors — and who else is doing this

**Research only — no application code was changed.** Researched 25 Sept 2026, from
current vendor docs, pricing pages, GitHub repos and analyst/third-party coverage.
Every load-bearing claim carries its source; flagged items are marked **unverified**.

**Questions asked:**

1. Can we move off the Cognee Cloud tenant onto **open-source Cognee**, with one
   API key that works across **OpenAI, Azure OpenAI and OpenRouter**?
2. Can we wire up the **connectors** — Gmail, Google Sheets, Drive, Docs, Slack, and
   the rest that "company brain" products integrate — **for free**?
3. Is anyone in the market already doing **actionable knowledge chats + AI-agent-assisted
   actions** for this category?

**The short answers:**

| Question | Answer |
|---|---|
| Open-source Cognee with a swappable key? | **Yes.** OSS Cognee ships the same `/api/v1` REST API our app already speaks; LLM choice is LiteLLM-routed, so OpenAI, Azure and OpenRouter are all documented configurations. |
| Gmail/Sheets/Drive/Docs/Slack for free? | **Yes, with one real cost hidden in Google's OAuth verification** (CASA, ~$540–1,800/yr) — avoidable at pilot scale via testing mode or the BYO-client pattern. Slack is genuinely free. |
| Competitors doing chat + agent actions? | **The category is hot (Glean $300M ARR), but the exact combo — openable citation chips + one-click per-answer actions at SMB price — is unoccupied.** Nearest: Onyx, Dust, Notion AI, Lindy. No India-focused player found. |

---

## Part 1 — Moving from Cognee Cloud to open-source Cognee

### 1.1 What OSS Cognee is today (Sept 2026)

- **v1.6.1 "Google Sync & Visualization"** (released 2026-09-24), **Apache-2.0**, ~31k stars,
  Python 3.10–3.14 (github.com/topoteretes/cognee).
- Ships a **FastAPI server**: `uvicorn cognee.api.client:app --host 0.0.0.0 --port 8000`,
  or the Docker image **`cognee/cognee`** (there is no separate `cognee-api` image; this
  one *is* the API server) — docs.cognee.ai/guides/deploy-rest-api-server,
  docs.cognee.ai/how-to-guides/cognee-sdk/deployment/docker.
- **Docker Compose**: one core service (ports 8000 + debug 5678, `/health` healthcheck)
  plus opt-in profiles: `postgres` (pgvector/pgvector:pg17), `neo4j`, `redis`, `mcp`
  (cognee-mcp, 8001), `ui` (cognee-ui, 3000).
- **Stores** — default embedded vs production:

| Layer | Default (embedded, one container) | Production options |
|---|---|---|
| Relational | SQLite | Postgres (`--profile postgres`) |
| Vector | LanceDB | pgvector, Turso |
| Graph | Ladybug (code default; `.env.template` sets `kuzu`) | Neo4j, Kuzu, Neptune, Turso, Postgres |

Cognee 1.0's headline: the entire memory layer runs on a single Postgres with pgvector
(cognee.ai/cognee-1-0-announcement) — which matches the "one box" economics in
SELFHOST_BUSINESS_CASE.md.

### 1.2 The key fact: our app's REST client keeps working

Our `cognee_cloud.py` is a thin `requests` client against
`https://<tenant>.aws.cognee.ai/api/v1/...`. The OSS API server exposes the **same
`/api/v1` endpoint set** — `POST /remember`, `POST /recall`, `GET /datasets`,
`GET /datasets/{id}/graph` are all present in the repo's routers and in the official
API reference, which documents "Local Docker / Self-Hosted Development at
http://localhost:8000/api/v1" alongside cloud tenants
(docs.cognee.ai/api-reference/introduction, docs.cognee.ai/guides/deploy-rest-api-server).

**Migration deltas for our app:**

| Thing | Cloud tenant | OSS local |
|---|---|---|
| Base URL | `https://<tenant>.aws.cognee.ai` | `http://localhost:8000` (the `/api/v1` prefix is mandatory — 404 without it) |
| Auth | `X-Api-Key` header | **Unauthenticated by default** (`REQUIRE_AUTHENTICATION=false`); if enabled, `Authorization: Bearer` from `/api/v1/auth/login`. Our extra `X-Api-Key` header is simply ignored |
| LLM / embeddings | Owned by the tenant | **Ours to configure** — this is the whole point |
| Ops | Cognee's problem | Ours — backups, upgrades, uptime (the known trade) |

So the "our app uses cognee open source" step is genuinely small: run the container,
point `COGNEE_SERVICE_URL` at it, and move the model credentials onto our own key.

### 1.3 One API key, three providers — the LiteLLM routing

Cognee routes all model calls through **LiteLLM**, configured by four env vars:
**`LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_ENDPOINT`** (plus `LLM_API_VERSION`,
temperature, per-stage routing, fallbacks) — docs.cognee.ai/setup-configuration/llm-providers.
The docs state: *"Any model reachable through an OpenAI-compatible endpoint can be
configured."*

| We want | Configuration (documented) |
|---|---|
| **OpenAI** | `LLM_PROVIDER="openai"`, `LLM_MODEL="openai/gpt-..."`, `LLM_API_KEY="sk-..."` |
| **Azure OpenAI** | `LLM_PROVIDER="openai"`, `LLM_MODEL="azure/gpt-4o-mini"`, `LLM_ENDPOINT="https://<resource>.openai.azure.com/openai/deployments/<model>"`, `LLM_API_VERSION="2024-12-01-preview"`, `LLM_API_KEY="az-..."` — **native, no proxy needed** (LiteLLM's `azure/` prefix) |
| **OpenRouter** | `LLM_PROVIDER="custom"`, `LLM_MODEL="openrouter/deepseek/deepseek-r1"`, `LLM_ENDPOINT="https://openrouter.ai/api/v1"`, `LLM_API_KEY="sk-or-..."` — **documented natively in Cognee's provider list** |
| Groq / Ollama / vLLM / any OpenAI-compatible | `LLM_PROVIDER="custom"` or `"ollama"` + `LLM_ENDPOINT`; also MCP Sampling |

**Embeddings** are configured independently (`EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`,
`EMBEDDING_DIMENSIONS`, `EMBEDDING_API_KEY`, optional `EMBEDDING_ENDPOINT`): openai,
azure, **gemini**, mistral, bedrock, **ollama**, **fastembed**, huggingface, and
`openai_compatible` for any endpoint — docs.cognee.ai/setup-configuration/embedding-providers.
Free options: Gemini embedding (`gemini/gemini-embedding-001`, 768 dims, Google labelled
"Free / Very Low Tier"), fully local fastembed (`all-MiniLM-L6-v2`, 384 dims), or Ollama
(`nomic-embed-text`). A complete **$0 stack with no cloud key at all** (Ollama LLM +
fastembed) is documented at docs.cognee.ai/guides/local-setup.
Gotcha: `EMBEDDING_DIMENSIONS` must match the vector collection schema or writes fail
(Cognee falls back to 3072).

### 1.4 Free inference tiers (Sept 2026)

| Provider | Free allowance | OpenAI-compatible? |
|---|---|---|
| **Cerebras** | Free tier: **5 RPM, 30K TPM uncached / 90K total, ~1M tokens/day**; models `gpt-oss-120b` (65k ctx), `qwen-3.8-27b` (inference-docs.cerebras.ai/support/rate-limits). Pricing page also shows a $5 one-time credit; the two may coexist — treat the exact daily cap as **partially unverified** | Yes — base `https://api.cerebras.ai/v1` |
| **Groq** | Free/developer: 30 RPM, 1,000 req/day, 8K TPM, 200K tokens/day (`gpt-oss-120b`, `qwen3.8-27b`) — console.groq.com/docs/rate-limits | Yes |
| **Gemini API** | Gemini 3 Flash 10 RPM / 1,500 req/day; Flash-Lite 15 RPM / 1,000/day; Pro moved to paid May 2026 (pecollective.com/tools/gemini-free-tier-guide; official page now shows dynamic per-project limits) | Native + OpenAI-compat endpoint |
| **OpenRouter** | `:free` models (currently ~24, e.g. `qwen/qwen3.8-27b:free`, `z-ai/glm-5.2:free`): **20 RPM; 50 req/day** unless you've bought ≥$10 lifetime credit, then **1,000 req/day** — openrouter.ai/docs/limits | Yes |
| **GitHub Models** | **Retired** — fully shut down 30 July 2026 (github.blog changelog) | n/a |
| **Azure OpenAI** | No free tier; new accounts $200/30-day credit; **Azure for Students: $100/12 months, includes Azure OpenAI** — azure.microsoft.com/en-us/free/students | Different path scheme — use the native `azure/` config above |

**Practical read:** on free tiers alone, **Cerebras ~1M tokens/day** (if the cap holds) or
**Groq 200K tokens/day** are the best zero-cost LLMs, both OpenAI-compatible so they slot
straight into `LLM_ENDPOINT`; Gemini free tier covers chat+embeddings at low RPM; OpenRouter
is the swapper — one key, every model, but near-useless free volume without $10 of credit
(which unlocks 1,000 free-model req/day).

**Recommended zero-cost stack:** Cognee OSS (one container, SQLite+LanceDB+embedded graph)
→ Cerebras or Groq for the LLM → Gemini or fastembed for embeddings → our FastAPI tier
unchanged, `COGNEE_SERVICE_URL=http://localhost:8000`. Total spend: **$0/month**, exactly
the Hetzner-at-$11 upgrade path already costed in SELFHOST_BUSINESS_CASE.md.

---

## Part 2 — The connectors: Gmail, Sheets, Drive, Docs, Slack and friends, for free

### 2.1 What Cognee OSS itself already ingests

- `cognee.add()` accepts **raw text, local files and directories, S3 URIs/prefixes,
  HTTP(S) URLs**, all Docling-supported formats, plus code files via a code-graph
  pipeline; **GitHub/GitLab repo URLs** are shallow-cloned and ingested
  (docs.cognee.ai/core-concepts/main-operations/legacy-operations/add; repo `base_config.py`).
- **In the OSS repo's `cognee/modules/integrations/`**: **Slack** (full OAuth app +
  events + `/api/v1/slack` routers + a root-level `slack-app-manifest.yml`), **Gmail**,
  **Google Drive** (v1.6.1 is literally "Google Sync"), **Linear**, **GitHub**.
- **Notion has no backend module in OSS** — only a frontend logo; it appears
  **cloud-only (unverified)**. Cognee's pricing page lists "Slack, Notion, Linear,
  Google Drive" under the paid cloud plan while the cloud integrations doc currently
  shows only **Slack live** with **22 connectors "upcoming"** (docs.cognee.ai/cognee-cloud/ui/integrations
  — flagged discrepancy with the marketing page).
- A **dlt integration** adds SQL sources (Postgres, MySQL, MSSQL, Oracle, Redshift…)
  plus Gmail, with Notion/Drive referenced — docs.cognee.ai/integrations/dlt-integration.

So a meaningful slice of the connector work already exists in OSS — Slack and Google
are the two we can lean on directly.

### 2.2 Google Workspace (Gmail, Drive, Docs, Sheets) — the APIs are free; OAuth is the cost

**All four APIs are free at standard usage.** 2026 wrinkles: quota tables were revised
for projects created on/after 1 May 2026, and Google's limits pages now state that
exceeding quota will start **charging the billing account "later in 2026"** (90 days'
notice promised).

| API | Default quota (2026) |
|---|---|
| Gmail | 6,000 quota units/min/user/project; 80M/day/project; `messages.send`/`drafts.send` 100 (developers.google.com/workspace/gmail/api/reference/quota) |
| Drive | 1,000,000 units/min/project; 750 GB/day upload (developers.google.com/workspace/drive/api/guides/limits) |
| Sheets | 300 read + 300 write req/min/project; 60/60 per user (developers.google.com/workspace/sheets/api/limits) |
| Docs | 3,000 read + 600 write req/min/project; 300/60 per user (developers.google.com/workspace/docs/api/limits — page rendered localized; **numbers worth re-confirming in console**) |

For a company-brain workload these are ample. **The real gate is Gmail's restricted
scopes → OAuth verification:**

- Creating the Cloud project + consent screen is free, but a *production* app with
  Gmail restricted scopes needs an **annual CASA security assessment by a
  Google-authorized lab**. The cheap route is **CASA Tier 2 self-scan, ~$540–$1,800/year**
  (full lab audits cost far more; assessments expire every 12 months)
  (developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification;
  deepstrike.io/blog/google-casa-security-assessment-2025).
- **Testing-mode escape hatch:** up to **100 test users** and **refresh tokens expire
  after 7 days** — workable for pilots, painful for production
  (developers.google.com/identity/protocols/oauth2/production-readiness/overview).
- Publishing unverified → users see the danger screen and a **100-total-user cap**.
- "Internal" app type skips verification but only works inside **one** Workspace org —
  not viable for multi-tenant B2B.
- **What indie/OSS products actually do: BYO-client.** Each customer creates their own
  Google OAuth client/service account and pastes credentials in. This is exactly how
  **Onyx** does Gmail and Drive (docs.onyx.app/admins/connectors/official/gmail and
  /google_drive/service_account) — zero verification cost for us, and it sidesteps CASA
  entirely because we never hold the customer-scoped app. The Google Workspace
  Marketplace has no listing fee but is **not** a CASA bypass for restricted scopes.

### 2.3 Slack — genuinely free, with two plan gotchas

- The **Web API is free to call** (per-method tiered rate limits); a standard OAuth
  bot token reads channel history (`conversations.history`) and posts
  (`chat.postMessage`) — docs.slack.dev/apis/web-api/rate-limits,
  docs.slack.dev/authentication/installing-with-oauth.
- **Free-plan workspaces keep only 90 days of message history** and allow only **10
  third-party app installations** — so a free-Slack customer's brain ingests the last
  90 days (slack.com/help/articles/27204752526611, /115002422943).
- **Slack has an official MCP server** (remote, `https://mcp.slack.com/mcp`,
  Streamable HTTP + OAuth 2.0) exposing search, messages, users, canvases, files,
  tables — docs.slack.dev/ai/slack-mcp-server. An npm stdio proxy `@slack/slack-mcp`
  is referenced in third-party roundups (**unverified** — npm blocked direct fetch).

### 2.4 MCP as the connector layer — now the most credible free path

2026's big shift: **Google itself now runs official remote MCP servers** for Gmail,
Drive, Docs, Sheets, Slides, Calendar, Chat and People (Developer Preview, OAuth 2.0,
free quota; enable per-API "MCP APIs" in Cloud Console)
(developers.google.com/workspace/guides/configure-mcp-servers).

| Source | Server | Free? |
|---|---|---|
| Gmail, Drive, Docs, Sheets, Calendar | **Google official remote MCP** (dev preview) | Yes (remote, free quota) |
| Gmail (local) | GongRzhe/Gmail-MCP-Server (OSS) | Yes, self-hosted |
| Slack | Official remote (`mcp.slack.com/mcp`) | Yes |
| Notion | Official hosted (`mcp.notion.com/mcp`) + OSS local server (makenotion/notion-mcp-server) | Yes |
| Linear | Official remote (`mcp.linear.app/mcp`) | Yes |
| Jira/Confluence | Official Atlassian remote (`mcp.atlassian.com/v2/mcp`) — **metered via AI Gateway credits, not free at scale**; OSS alternative sooperset/mcp-atlassian | OSS one is free |
| Drive/Slack reference servers | Archived in modelcontextprotocol/servers (`servers-archived`) | — |

**Python viability: yes** — the official MCP Python SDK (FastMCP) both builds servers
and drives them as a client (github.com/modelcontextprotocol/python-sdk,
gofastmcp.com/clients/client), so our FastAPI backend can spawn local MCP servers or
call remote HTTP MCP endpoints directly.

### 2.5 Connector platforms (the "Composio-style" shortcut)

| Platform | Free / self-host | Notes |
|---|---|---|
| **Composio** | Cloud free tier: **100K tool calls/mo, 3 seats** (a Scalekit post claims 20K for pre-Aug-2026 accounts — **flagged discrepancy**); SDK is MIT but the platform is **not self-hostable** | composio.dev/pricing, github.com/composiohq/composio |
| **Sim** (sim.ai) | **Apache-2.0, fully self-hostable free** (Docker Compose), ~30k stars, 1,000+ integrations | github.com/simstudioai/sim |
| **Nango** | Open source, self-host free with limited features; 1,000+ API templates for OAuth + unified APIs | github.com/nangohq/nango |
| **Onyx (ex-Danswer)** | **MIT-ish OSS with 40+ connectors free in self-host — Gmail, Slack, Drive, Confluence, Jira, Notion, Linear, GitHub…** Only permission auto-sync is Enterprise | docs.onyx.app/admins/connectors/overview, onyx.app/connectors |
| Unipile / Apideck / Alloy / Blockot | Paid; not zero-budget relevant (Unipile: no free tier, no Slack/Drive) | unipile.com/pricing-api |

**Onyx's OSS connector code is the best free blueprint to copy** for Gmail/Slack/Drive
ingestion patterns (BYO-client OAuth, incremental sync). By contrast AnythingLLM has no
Gmail/Slack, Khoj syncs files + Notion only, Open WebUI does connectors via MCP/community.

### 2.6 What the "brain" companies integrate (table stakes, 2026)

Slack, Google Drive, Notion, Confluence, Jira, Linear, GitHub, Gmail. Glean advertises
**275+ connectors** (glean.com/platform/connectors); Coda Brain claimed 500+ tools via
X-Ray sync (coda.io/blog). Mem0 / Zep / Letta are developer infrastructure — no
connector marketplaces.

**About "Cerebras":** it is an **inference-chip/provider company, not a connector
company** — no connector ecosystem exists there (cerebras.ai/pricing). Treat the mention
as a mix-up; its relevance to us is the free/fast OpenAI-compatible **inference** tier in
Part 1, not connectors.

### 2.7 The free-est connector path for our app

1. **Slack**: Cognee's own OSS Slack integration (or official Slack MCP server) — free.
2. **Google (Gmail/Drive/Docs/Sheets)**: **BYO-client pattern** like Onyx — each customer's
   own OAuth client in our app, free APIs, no CASA while piloting (testing mode covers
   100 users); Google's official MCP servers as an alternative ingestion layer.
3. **Notion / Linear / GitHub / Jira**: official remote MCP servers + sooperset/mcp-atlassian,
   driven from our Python backend via the MCP SDK.
4. **If we want prebuilt plumbing**: self-host **Sim** or **Nango** free; **Composio's**
   100K free tool calls/mo as a pragmatic stopgap for exotic connectors.
5. Sequence for us: **Slack + Drive first** (both have first-class free paths and are the
   two sources the demo story already leans on), Gmail when we accept the OAuth-verification
   decision, Sheets/Docs for read-side enrichment.

---

## Part 3 — Competitors: actionable knowledge chats + agent-assisted actions

### 3.1 The matrix

| Product | Knowledge chat w/ citations | Agent actions | Open-source? | 2026 pricing | Verdict |
|---|---|---|---|---|---|
| **Glean** | Yes | Agents: scheduled routines, multi-step, Slack/ServiceNow; described as "read-focused, limited write" | No | ~$50–75/user/mo, ~100-seat minimums, $60k–240k+/yr (**third-party figures**); $300M ARR (TechCrunch, May 2026) | Feature-closest, price-furthest |
| **Onyx** (ex-Danswer) | Yes — "precise source citations" | Custom agents + MCP/OpenAPI tool actions, 40+ connectors | **Yes — self-host free** | Cloud $20–25/seat/mo | **Overall closest** |
| **Dust** | Yes — cited replies via web/Slack | Cross-platform task execution by company agents | No | Pro ~€30/seat/mo, Max ~€150 | **Very close**; ≤100-employee mid-market |
| **Notion AI** | Yes — "AI citations" on cross-app Q&A | Custom Agents on triggers/schedules, Autofill — background workflows, not per-answer one-click | No | Business $20/user/mo + credit system | Closest big-co analogue |
| **Lindy** | RAG knowledge base; citations unspecified | Email triage/auto-reply, Slack posting, CRM updates | No | Free tier; $49/mo Pro — flat, SMB-priced | Action engine, citation-weak |
| **Dashworks / GoSearch** | Yes — source links / inline citations | No-code multi-step agents | No | $12–20/user/mo | Mid-market budget pair |
| **Moveworks** (ServiceNow) | Conversational retrieval | Task routing, request automation | No | ~$100k–500k contracts | Enterprise-only |
| **M365 Copilot + Copilot Studio** | Grounded, citations inconsistent (MS Q&A, Feb 2026) | Drafts in Word/Outlook, Excel, Teams; custom agents | No | $21–30/user/mo + M365 base; Studio from $200/tenant/mo | The incumbent default |
| **Gemini for Workspace** | Permission-aware search (Enterprise) | Gmail/Docs drafting, cross-app workflows | No | ~$7–22/user/mo bundled | Cheap, not citation-first |
| **Guru** | Knowledge-verified answers | Knowledge Agents (Q&A, not write-actions) | No | ~$250/mo real floor (10 seats) | Adjacent, action-light |
| **Viktor** | Context aggregation, not citation-first | Drafts briefs/CRM/support replies across 3,000+ apps; human approval per action | No | n/a | Action-layer rival ("Glean ends the workflow at the answer. Viktor begins it there") |
| **Zapier Agents / Gumloop / n8n / Make** | No citation-grounded chat | Workflow automation | n8n (and Dify) only | $20–37/mo | Complementary infra, not the combo |
| **Mem0 / Zep / Letta / Cognee / Supermemory** | No end-user product | N/A — memory/graph infrastructure | Mostly Apache-2.0 | Mem0 cloud $249/mo, Zep $1,250/yr | Not competitors — potential suppliers |

Notes: Coda Brain was **absorbed into Superhuman** ("Superhuman Docs") and its action
philosophy deliberately limits delegation (observer.com). **Relay.app is shutting down
mid-2026.** Qatalog was absorbed into ClickUp.

### 3.2 The market frame

- Gartner: **40% of enterprise apps will feature task-specific AI agents by 2026** (from
  <5% in 2025); agentic AI sits on the 2026 Hype Cycle; there's a 2026 Market Guide for
  Enterprise AI Search.
- TechCrunch (Feb 2026): "the enterprise AI land grab is on — Glean is building the layer
  beneath the interface," i.e. the category has shifted **from search to action**.
- Sana Labs frames the leaders (Sana, Agentforce, Copilot Studio, Kore.ai, UiPath, AWS Q,
  Moveworks) as turning search into a "system of action."

### 3.3 The gap (our opening)

**Nobody found ships our exact combo**: openable, **passage-highlighted citation chips on
every answer** + **one-click actions derived from that answer** (email draft citing the
exact facts, Slack-ready update, next-steps checklist) + **SMB pricing**.

- Glean/Moveworks: right features, enterprise-only contracts.
- Microsoft/Google: actions bundled everywhere, but not citation-first UX (Microsoft's
  own Q&A threads show broken citations).
- Onyx and Dust: nearest on both axes — but Onyx's actions are generic tool calls, not
  curated per-answer affordances, and its passage-highlight depth is **unverified**;
  Dust is ~€30/seat and mid-market-focused.
- **India: no dedicated "company brain + actions" competitor surfaced.** The nearest
  India-built player is Zoho Zia — broad, embedded in Zoho's suite, not citation-first.
  (Absence of evidence, not evidence of absence.)

**Positioning, plainly:** the incumbents charge $20–75/user/month and sell to 100+
seats. A citation-first, action-per-answer product at Indian SMB price points
(₹1,499–1,999/mo as costed in INDIA_PRICING.md), running on $0 free-tier infrastructure
(Part 1) with free connectors (Part 2), sits in genuinely unoccupied space — the
"Glean-ends-at-the-answer / Viktor-begins-there" fusion at a price neither will follow
us to.

---

## Verdict table

| Question | Verdict |
|---|---|
| Cognee OSS instead of the cloud tenant? | **Yes — same REST API, one container, ~$0.** Point `COGNEE_SERVICE_URL` at `http://localhost:8000`, keep our client. |
| One API key for OpenAI / Azure / OpenRouter? | **Yes, documented natively** (`LLM_PROVIDER`/`LLM_MODEL`/`LLM_API_KEY`/`LLM_ENDPOINT` via LiteLLM). Plus any OpenAI-compatible endpoint: Cerebras, Groq, Ollama. |
| Gmail / Sheets / Drive / Docs / Slack for free? | **Slack: fully free.** Google: APIs free, quotas ample; the cost is Gmail-scope OAuth verification (CASA ~$540–1,800/yr) — dodged at pilot scale via testing mode / BYO-client (the Onyx pattern), and Google's official MCP servers are a new free ingestion layer. |
| Other connectors (Notion, Linear, Jira, GitHub)? | Official remote MCP servers (free; Atlassian's is metered) + OSS alternatives; Sim/Nango self-hosted plumbing; Composio's 100K free calls/mo as a stopgap. |
| "Cerebras" connectors? | **Mix-up — Cerebras sells inference, not connectors.** Its free ~1M tokens/day OpenAI-compatible tier is the useful part for us. |
| Competitors doing actionable knowledge chats + agent actions? | **Yes, the category is real and consolidating** (Glean $300M ARR; Coda→Superhuman; Qatalog→ClickUp; Relay shutting down). **No one does our citation-first + per-answer-actions combo at SMB/India price.** Nearest: **Onyx** (open-source twin), **Dust**, **Notion AI**, **Lindy** (actions only). No India-focused competitor found. |

---

**Sources (primary):** github.com/topoteretes/cognee · docs.cognee.ai (deploy-rest-api-server,
api-reference/introduction, setup-configuration/llm-providers, setup-configuration/embedding-providers,
guides/local-setup, integrations/dlt-integration, cognee-cloud/ui/integrations) · cognee.ai/pricing ·
inference-docs.cerebras.ai · console.groq.com/docs/rate-limits · ai.google.dev/gemini-api/docs/rate-limits ·
openrouter.ai/docs/limits · azure.microsoft.com/en-us/free/students · developers.google.com/workspace
(Gmail/Drive/Sheets/Docs limits; OAuth2 production-readiness; configure-mcp-servers) · docs.slack.dev
(web-api rate limits, Slack MCP server) · modelcontextprotocol/python-sdk · composio.dev/pricing ·
github.com/simstudioai/sim · github.com/nangohq/nango · docs.onyx.app (connectors, pricing) ·
glean.com/platform/connectors · gosearch.ai/blog/glean-pricing-explained · techcrunch.com (Feb/May 2026) ·
notion.com/product/ai · myclaw.ai/blog/dust-ai · toolwise.ai/tools/lindy-ai · gartner.com (2025-08-26
press release, 2026 Hype Cycle) · observer.com (Superhuman, July 2026) · zoho.com/zia.
