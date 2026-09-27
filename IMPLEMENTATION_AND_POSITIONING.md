# Implementation, hosting, positioning — the build plan for Kestrel Brains

**Research only — no application code was changed.** Researched 25 Sept 2026 from
current vendor docs, GitHub source at Cognee tag `v1.6.1`, and pricing/coverage pages.
This elaborates `OSS_STACK_AND_COMPETITORS.md` (Part 3 there is superseded by Part D
here). Every load-bearing claim carries its source; flagged items are **unverified**.

**Questions asked:**

1. What shall be implemented, in what sequence, and what are the challenges?
2. How do we host the servers (incl. open-source Cognee) — running, but thin: the load
   sits on client-side API keys and free tiers, **not** on a fat always-on VM we babysit.
3. The full competitor picture, and our clear position inside it.
4. Platform strategy: open source + paid cloud, or paid cloud only?

**The short answers:**

| Question | Answer |
|---|---|
| Implementation sequence | **9 phases**, starting with a day-1 API contract test, then local OSS parity → externalized state → hosted deploy → BYOK → tenancy → Slack → Google → actions → open-source release. |
| Hosting without a fat VM | **Cloud Run (scale-to-zero) + Neon free Postgres + graph store, with BYOK inference.** Free tiers changed in 2026 — most "free" container hosts are dead or too small; the honest fallback is one €5–11/mo box, which is thin, not fat. |
| The catch in "load on the client" | Cognee's LLM config is **process-global** — per-user API keys don't swap per request. The fix is a **hybrid BYOK architecture**: Cognee does ingestion/graph retrieval on our (free-tier) key; **answer generation happens in our own FastAPI using the user's key**. |
| Competitors | The category is consolidating and suite vendors are bundling AI into base plans; **every India-founded player is $25k+/yr enterprise-only** — the ₹1,500/mo SMB band is empty. YC has now tagged "company brain" as a category — it is claimable. |
| Platform strategy | **Open source from day 1 (AGPL-3.0 core) + free hosted BYOK tier + paid convenience cloud** (₹999 / ₹1,999 per-company flat). This is the Chatwoot/ToolJet playbook, and BYOK makes the hosted tier nearly free to run. |

---

## Part A — The target architecture: thin server, client-carried load

The owner's constraint: servers running and reachable, but the expensive load
(LLM inference) is carried by **client-side API keys** and **free inference tiers**,
not by a VM we pay for and keep warm.

```
  Browser (client device)
    │  user's own API key (BYOK) — OpenAI / Azure / OpenRouter / Cerebras / Groq
    ▼
  Our FastAPI app tier (thin, free host)         ← serves UI, auth, actions
    │  X-Api-Key / Bearer
    ▼
  Cognee OSS API server (scale-to-zero host)     ← remember / recall / graph
    │        ingestion LLM = OUR free-tier key (Cerebras ~1M tok/day)
    │        answer LLM   = USER's key (hybrid, see below)
    ▼
  Externalized state (no local disk):
    Neon free Postgres (relational + pgvector)   +  graph store (see Part C)
```

**The one structural problem, stated plainly:** Cognee's LLM configuration is
**process-global** — read at startup, providers cached; the docs state that changing
the model later via `cognee.config.set_llm_config()` does not re-trigger provider
resolution (docs.cognee.ai/setup-configuration/llm-providers). So "each user's key
drives each request" cannot be done inside Cognee directly. Three workarounds exist:

| Option | How | Verdict |
|---|---|---|
| **Hybrid BYOK (recommended)** | Cognee does ingestion + graph/vector retrieval on **our** free-tier key; **answer generation moves into our own FastAPI**, which calls the user's provider directly with the per-request key. Cognee's retrieval-only search types feed it context. | Cleanest fit for Cognee's architecture; also makes our citation/action layer (already in app.py) the natural place for generation. |
| LiteLLM proxy "clientside credentials" | Run a LiteLLM proxy; Cognee's `LLM_ENDPOINT` points at it; user keys pass per-request via `extra_body` (docs.litellm.ai/docs/proxy/clientside_auth). | Works for ingestion AND generation under user keys, but adds another service to host and a fast-moving dependency. |
| One Cognee process per tenant | Process-per-user with its own env. | RAM-costly; wrong for a thin-server goal. |

**Browser-direct calls are also possible but second choice:** OpenRouter and Anthropic
support CORS from browsers; OpenAI requires the `dangerouslyAllowBrowser` opt-in;
Gemini's compatibility endpoint has mixed CORS reports; Groq/Cerebras **unverified**.
Fine for a power-user mode; the server proxy is safer default (keys never sit in
localStorage, per-key abuse is capped, and we can rate-limit). Precedents for BYOK UX:
TypingMind (one-time $39–99 license, users pay providers directly — typingmind.com/buy),
LibreChat (free OSS, user credentials encrypted at rest via `CREDS_KEY`/`CREDS_IV` —
librechat.ai/docs/configuration/dotenv).

**Who pays for what, in the recommended split:**

| Work | Key that pays | Why |
|---|---|---|
| Ingestion (extraction, graph building — the token-heavy part) | **Ours, free tier** | Cerebras free: 5 RPM / 30–90K TPM / ~1M tokens/day (inference-docs.cerebras.ai/support/rate-limits); Groq free: 30 RPM, 14.4K req/day, 500K tokens/day (console.groq.com/docs/rate-limits — earlier "1k req/day" figures are outdated). Slow but free; Cognee has a built-in limiter (`LLM_RATE_LIMIT_REQUESTS=5`) and retry/backoff. |
| Answer generation | **User's key (BYOK)** | Billed to the user's OpenAI/Azure/OpenRouter account; our marginal hosted cost ≈ 0. |
| Embeddings | Ours or user's | Gemini embedding free tier, or local fastembed; `EMBEDDING_DIMENSIONS` must match the model (known traps, Part B). |

---

## Part B — Implementation: what to build, in what sequence, and the challenges

### B.1 What changes in our code (the API contract, verified against Cognee v1.6.1)

Our `cognee_cloud.py` client keeps its shape — the OSS API server exposes the same
`/api/v1` routes — but the contract is not byte-identical. Verified from the v1.6.1
routers (github.com/topoteretes/cognee/tree/v1.6.1/cognee/api/v1):

| Our client sends today | OSS v1.6.1 expects | Change needed |
|---|---|---|
| `POST /remember` multipart `raw_data`, `datasetName`, `run_in_background`, `filename` | Same path; also accepts `datasetId`, `node_set`, `chunk_size`, `external_metadata`… | None for our fields |
| `POST /recall` JSON `query`, `searchType`, `datasets: [name]`, `includeReferences` | Same path but **`search_type`**, **`include_references`**; `datasets` takes **names** (UUIDs optional via `dataset_ids`) | Rename two fields — this is the day-1 contract test |
| `GET /datasets/status?dataset=<uuid>&include_error_detail=true` | `?dataset=<uuid>` (repeatable) + `?pipeline=`; no `include_error_detail` (ignored harmlessly) | None |
| Terminal states `DATASET_PROCESSING_COMPLETED / _FAILED / _ERRORED` | `…_INITIATED(legacy) / _STARTED / _COMPLETED / _ERRORED` — **no `_FAILED`** | Map `_FAILED` → `_ERRORED` in `terminal_kind()` |
| `X-Api-Key` header | **First-class auth backend in OSS** (per-user keys minted at `/api/v1/auth/api-keys`) — or ignored when auth is off | None; later this *replaces* our hand-rolled `tenants.py` |
| Data items `name` | Normalized **basename** of the uploaded filename | Strip directories client-side before ingest |
| `GET /datasets/{id}/data`, `/data/{id}/raw` | Same | None — citations.py survives |

**Two defaults that will bite silently:**
- **Auth is ON by default** in v1.6.1 (`ENABLE_BACKEND_ACCESS_CONTROL` defaults true;
  `REQUIRE_AUTHENTICATION` inherits). To run unauthenticated you must set BOTH to
  false; otherwise every call needs `POST /api/v1/auth/login` → Bearer token
  (github.com/topoteretes/cognee/blob/v1.6.1/cognee/modules/users/methods/get_authenticated_user.py).
- **JWT secrets became random-per-process in v1.6.0** — set a fixed
  `FASTAPI_USERS_JWT_SECRET` or every restart invalidates all sessions
  (docs.cognee.ai/changelog).

**Bonus we get for free:** OSS v1.6.1 ships **real multi-user/tenancy** — email/password
accounts, tenants, dataset ACLs (`POST /api/v1/permissions/tenants`), per-dataset
provisioning of graph/vector stores, and API-key auth
(docs.cognee.ai/core-concepts/multi-user-mode/permissions-system/users). Our Phase 5
becomes "adopt Cognee's user system" rather than "build one." Caveat: isolation has had
real bugs fixed recently (multi-tenant role-lookup exposure #5035 fixed in v1.6.0;
provenance leakage fixed in v1.6.1) — assume actively-hardened, not proven, and run
adversarial tenant tests.

### B.2 The build sequence (each phase has an acceptance test and a de-risking step)

| Phase | Build | Acceptance test | Riskiest unknown → de-risk |
|---|---|---|---|
| **0** | Contract test script: point our client at a local `cognee/cognee:v1.6.1` container, replay remember→status→recall→graph→data with the renamed fields | One script passes against OSS, fails loudly on any shape drift | Field renames + `_ERRORED` enum — found now, not mid-migration |
| **1** | Local parity run: auth off, embedded SQLite+LanceDB+Kuzu, our free-tier LLM key, ingest `corpus/`, rebuild the demo brain | `smoke.py`-equivalent passes: answer with citations; `citations.py` resolves via `/data/{id}/raw` | Memory footprint on a laptop — measure before choosing a host |
| **2** | Externalized state: `DB_PROVIDER=postgres` (Neon), `VECTOR_DB_PROVIDER=pgvector`, graph per Part C, fixed JWT secret, volume/DB backups | Kill the container; datasets and recalls survive; pg_dump restore works | Postgres-graph handler maturity (docs still label Postgres-as-graph "demo"; the v1.6.1 `.env.template` exposes `GRAPH_DATASET_DATABASE_HANDLER=postgres_graph_shared` — **verify on the pinned image before committing**) |
| **3** | Hosted deploy (Part C): app tier + Cognee tier + Neon + graph; `render.yaml`-style config for the chosen host | `smoke.py --base <url>` 4/4 from a cold start; measure cold-start latency | Cloud Run timeout during long ingestion (unverified ceiling) → ingest in background, poll status |
| **4** | **BYOK, hybrid:** settings UI for provider+key; answer generation moves into app.py calling the user's key; ingestion stays on our free-tier key with `LLM_RATE_LIMIT_REQUESTS` tuned | Two users with different keys see their own billing; ingestion unaffected | CORS/provider quirks if we later go browser-direct — keep server-proxy default |
| **5** | Tenancy: turn Cognee access control ON; our app proxies login/API-keys; per-user datasets; retire `tenants.py` | Tenant A's query never returns Tenant B content (incl. recall without a datasets filter — that path silently searched everything before v1.6.0) | Residual cross-tenant bugs (#5035 precedent) → adversarial suite in CI |
| **6** | Slack: enable Cognee's OSS Slack integration (`SLACK_CLIENT_ID/SECRET/…`, public HTTPS, `INTEGRATION_CREDENTIALS_KEY`) | `/cognee-remember` ingests; tokens encrypted at rest | **Bulk channel-history import is only an open PR (#4951)** — decide: DIY history fetcher vs wait |
| **7** | Google: enable Gmail (`gmail.readonly`, incremental history cursors) + Drive (`drive.readonly`, folder allowlist, change cursors) — both shipped in v1.6.1 | Sync advances cursor; deletion propagates; citations name real Gmail/Drive items | No dedicated Sheets/Docs connectors; Drive's handling of native Google formats **unverified** → test with a real Sheet/Doc |
| **8** | Actions layer: MCP tools (Slack MCP, Google remote MCP) for *send* actions; Cognee's tool-calls (`TOOL_CALLS_ENABLED`, default OFF, SELECT-only) stays read-only | Email draft → "send via Gmail MCP" with approval gate; Slack update → post | Write-actions need per-user OAuth tokens — reuse connector token store |
| **9** | Packaging: AGPL-3.0 repo, docker-compose quickstart, pinned `cognee/cognee:v1.6.1`, secrets externalized, smoke CI against new Cognee tags | A stranger clones and runs the whole stack with one compose file and their own key | Upstream churn (~2 releases/month) → upgrade deliberately, never `latest` |

### B.3 Challenges and mitigations (the honest table)

| Challenge | Evidence | Mitigation |
|---|---|---|
| **Version churn** — 12 tagged releases in 6 weeks; v1.6.0 alone dropped `context_format`, randomized JWT secrets, removed graphiti | docs.cognee.ai/changelog | Pin exact image tag; read release notes per bump; contract test from Phase 0 guards us |
| **Memory spikes** — compose limit 8GB; `graph-summary` OOM'd on Neo4j (#4832); first boot (migrations + model fetch) can OOM small boxes | github.com/topoteretes/cognee/issues/4832; bitdoze.com/cognee-self-host | 2 vCPU / 4–8GB for the Cognee tier; small batches; `DATABASE_MAX_LRU_CACHE_SIZE`/`DATASET_QUEUE_MAX_CONCURRENT` = 1–2 |
| **Embedding dimension traps** — custom dims fail inside the uvicorn process (#4313, #4364); silent fallback to 3072 (#3490) | GitHub issues | Test the exact `EMBEDDING_DIMENSIONS` end-to-end before bulk ingest |
| **Free-tier rate limits vs ingestion** — extraction runs per chunk and "dominates token use" (env.template); Cerebras 5 RPM caps ~300 extraction calls/hour | inference-docs.cerebras.ai; cognee .env.template | `LLM_RATE_LIMIT_REQUESTS=5` + built-in retry/backoff; expect hours per moderate corpus on free tiers; batch off-peak |
| **Single worker** — `entrypoint.sh` hardcodes gunicorn `-w 1`; one slow request stalls all (#5001: 0.39s → 8.9s) | github.com/topoteretes/cognee/issues/5001 | Keep ingestion backgrounded; app tier separate from Cognee tier so the UI never stalls |
| **SQLite/embedded-store concurrency** — WAL + timeouts only within one process; "not a mechanism for sharing between multiple Cognee processes"; Postgres advisory locks added in v1.6.0 for exactly this | docs.cognee.ai/setup-configuration/relational-databases | Postgres from Phase 2 onward; never multiple Cognee workers on SQLite |
| **Background tasks are in-process asyncio**, drained on shutdown (`BACKGROUND_DRAIN_TIMEOUT_SECONDS=8`) — no external queue | docker-compose.yml | One Cognee instance (`max-instances=1`); long ingests tolerate restarts via status polling |
| **Cold starts** — auto-migrations on startup; GLiNER/torch first-fetch; first-recall retries were added client-side (#3542/#3546) | GitHub issues | Warm-up ping (our `warmup.py` already exists); measure, don't assume |
| **Backups** — no one-step restore; file state lives in two named volumes; Postgres via pg_dump; `GET /api/v1/activity/export/{dataset_id}` for graph runs | docs.cognee.ai/guides/deploy-rest-api-server | Externalize state (Phase 2) so backups are pg_dump + volume snapshots; keep our `snapshot.py` fixtures as the demo fallback |
| **Gmail OAuth verification (CASA)** — ~$540–1,800/yr for restricted scopes in production | developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification | BYO-client (the Onyx pattern) or testing-mode (100 users) while piloting — from the prior report |
| **Nobody has published running Cognee OSS on Render/HF/Cloud Run** — we would be trailblazing | searched Sept 2026, only VPS guides exist | Phase 3 is deliberately early and small; keep the Hetzner fallback ready |

---

## Part C — Hosting: where the servers actually run

### C.1 The 2026 free-tier reality (verified — several things died or shrank)

| Platform | Specs / behavior | Verdict for us |
|---|---|---|
| **Google Cloud Run** | Scale-to-zero; free tier 2M requests + 180k vCPU-s + 360k GiB-s/mo; **no persistent disk** (stateless only) | **The Cognee-tier candidate** — viable only with all state in Neon + a network graph store; 360k GiB-s ≈ ~25 h/mo at 4GB then pennies |
| **Hugging Face Spaces** | 2 vCPU / 16GB CPU-basic; **2026 gotcha: creating Docker/Gradio Spaces now requires a paid plan** (PRO $9/mo); outbound restricted to ports 80/443/8080 | Only with PRO; otherwise out |
| **Render free** | 0.1 CPU / **512MB**, spins down after 15 min; persistent disk is paid | **512MB kills the Cognee container** — but it is fine for our thin FastAPI app tier |
| **Fly.io** | **Free tier dead for new orgs** — usage-based, cheapest baseline ≈ $2/mo + volumes | Viable near-free; adds ops |
| **Koyeb free** | 0.1 vCPU / 512MB / 2GB SSD, sleeps after 1h | Too small for Cognee |
| **Railway** | No free tier; $5 trial credit, Hobby $5/mo | Simple paid option |
| **Oracle Always Free** | Now **2 ARM OCPU / 12GB** (cut from 4/24), 200GB block; always-on; signup/capacity lottery | The only genuinely-free always-on VM — but it IS a VM we babysit; keep as plan C |
| **Azure F1** | 1GB RAM / **60 CPU-min/day** | Disqualified — ingestion alone blows the CPU budget |

### C.2 The state stores

| Layer | Free option | Caveats |
|---|---|---|
| Relational + vectors | **Neon free**: 0.5GB/project, 100 CU-h/mo, autosuspend after 5 min (resume sub-second), pgvector supported | 0.5GB is the binding cap at 10–50 users; Supabase free (also 500MB) pauses after **1 week** inactivity — worse |
| Graph | **Neo4j Aura Free**: still exists ($0, node/relationship limits, auto-pause; exact pause/delete policy **unverified**) | Kuzu/Ladybug needs a persistent volume (single writer, "not suitable for concurrent access" per Cognee docs); FalkorDB Cloud free auto-deletes after 7 days idle — demo-grade |
| Graph-on-Postgres | `GRAPH_DATASET_DATABASE_HANDLER=postgres_graph_shared` (schema-per-dataset) in v1.6.1's `.env.template` | Docs still call Postgres-as-graph "demo, not production-ready" — **the single most important thing to verify in Phase 2**; if it holds up, the whole stack is Cloud Run + Neon and nothing else |

### C.3 Recommended deployments

**Pilot (satisfies "thin, hosted, client-carried load") — ~$0–3/mo:**

```
Render free           → our FastAPI app tier (thin; sleep is fine, 512MB is enough)
Cloud Run (max 1)     → cognee/cognee:v1.6.1 (cold start on query; ingestion in background)
Neon free             → Postgres + pgvector
Neo4j Aura Free       → graph   (or postgres_graph_shared if Phase 2 verifies it)
User's API key        → answer generation (hybrid BYOK, Part A)
Cerebras/Groq free    → ingestion LLM
```

**Production-ish at 10–50 users — the honest fallback (~€5–11/mo):**
One Hetzner/Contabo box (2–4 vCPU, 4–8GB) running app + Cognee + Postgres + Kuzu on
local disk. No cold starts, no caps, no pause lotteries. This is a **thin single server,
not a fat VM** — and at this size it beats every free option on experience. The prior
report's economics (~$14/mo all-in) still hold.

**What to avoid:** Render free for Cognee (512MB), Azure F1 (60 CPU-min/day), FalkorDB
free (auto-delete), unpinned `cognee:latest`.

---

## Part D — The full competitive picture and our position

### D.1 Expanded matrix (supersedes the prior report's Part 3; all prior rows still apply)

| Product | Citations | Agent actions | OSS? | 2026 pricing | Segment / India angle |
|---|---|---|---|---|---|
| Atlassian Rovo | Yes (Jira/Confluence grounded) | Yes (agents + Rovo Dev) | No | Bundled Standard–Enterprise; 25/70/150 credits/user, $0.01 overage; Rovo Dev $20/seat | Atlassian shops |
| Slack AI | Yes (search answers cite messages) | Weak (summaries/search) | No | No add-on — bundled in Business+ (~₹557/user/mo) & Enterprise+ | Slack shops; INR pricing |
| Salesforce Agentforce | Weak in chat UI | Strong | No | $2/conversation, ~$0.10/action, or ~$125/user/mo | Enterprise |
| Perplexity Enterprise Pro | Strong (web); internal-doc depth **[U]** | No | No | $40/seat/mo | Prosumer→ent |
| Zoom AI Companion 2.0 | Recaps only | Minimal | No | Free with paid plans; Custom add-on $12/user/mo | Zoom shops |
| ClickUp Brain | Enterprise search; depth **[U]** | Some (agents, notetaker) | No | Brain $9/user/mo; "Everything AI" $28 | PM users |
| Coda → Superhuman Docs | Docs AI | Limited | No | Prosumer docs pricing; brand retired in merger | Absorbed |
| Sana Labs | Grounding; formal citations **[U]** | Yes (multi-agent) | No | Custom, est. $50–150k+/yr | Ent sales |
| TextQL → Aster | BI/data agent | Data actions | No | $17M Series A 2026 | Ent data |
| Qatalog | — | — | — | **Acquired by ClickUp, Nov 2025** | Consolidated away |
| Sourcegraph / GitHub Copilot | Code knowledge | Code actions | Partial | Sourcegraph from $16k/yr; Copilot $0/$10/$19/$39 → usage billing | Code-only analogue |
| **Kore.ai** | RAG knowledge | Strong agent platform | No | ~$50k–300k/yr | **India-founded [U]**; enterprise, regulated |
| **Yellow.ai** | CX/EX focus | Yes | No | Free: 1 agent + 500 sessions, $0.99/resolution; paid $3–10k+/mo | **India-founded [U]** |
| **Leena AI** | Knowledge assistant | HR/IT actions | No | ~$150/employee + 1,000-employee min **[U]** | **India-founded [U]**; ent HR/IT |
| **Atomicwork** | Yes — "cite and verify sourced answers" | Yes ($1/answer, $2/access, $3/resolution) | No | From $25k/yr; "steep base costs exclude small businesses" | **India-founded** (Bengaluru eng, $25M Khosla) — nearest India rival, and it explicitly skips SMBs |
| **Zoho Zia Agents** | Ecosystem answers | Yes (Agent Studio) | No | Platform free; token metering, 30M free tokens/mo; **supports BYOK provider keys** | Chennai; closest India analogue — and it validates our BYOK model |
| DevRev | Knowledge + support | Yes (AgentOS) | No | Usage-based; free startup tier | **India-founded [U]** |
| Memory Store (YC P26) | "Company brain" hub | Context for AI tools | **[U]** | **[U]** | YC-backed; **category validation — YC publicly tagged "company brain"** |

**Plus the prior report's rows:** Glean (~$50–75/user/mo, $300M ARR, enterprise-only), **Onyx** (open-source, citations + agents, cloud $20–25/seat — overall closest), **Dust** (~€30/seat, cited replies + acting agents), Notion AI ($20/user/mo, credit-metered agents), Lindy (flat $49/mo, action-strong/citation-weak), Dashworks/GoSearch ($12–20/user/mo), Guru (~$250/mo floor), Moveworks ($100k+), M365 Copilot ($21–30 + base, inconsistent citations), Gemini for Workspace, Mem0/Zep/Letta/Cognee/Supermemory (infrastructure, not competitors).

### D.2 What the expanded picture says

1. **Suite bundling is killing the standalone "AI add-on" at the top** — Slack AI, Atlassian Rovo, Zoom Companion are now bundled into base plans. The standalone winners are either open-source (Onyx) or workflow-native (Lindy).
2. **Every India-founded enterprise AI player prices at $25k+/yr** (Kore.ai, Yellow.ai, Leena AI, Atomicwork, DevRev). Atomicwork — the nearest India rival, with "cite and verify" language nearly identical to ours — *explicitly excludes small businesses*. **The ₹1,500/mo Indian SMB band is empty.**
3. **The category has a name now.** YC lists a "company brain" startup and publicly tagged the category — the term is entering the mainstream but **no vendor owns it for SMBs**. Claiming "the open-source company brain" is available.
4. **Zoho Zia supporting BYOK provider keys** is independent validation of the BYOK model for exactly our market.

### D.3 Our position, stated plainly

- **Category to claim:** *the open-source company brain*.
- **One-line pitch:** *"Kestrel is your company's brain with a paper trail: every answer opens the exact highlighted passage in your source documents and ships one-click actions — email drafts, Slack updates, next steps. Self-host it free with your own API keys, or host with us at SMB prices."*
- **Vs Onyx (nearest overall):** they cite at document level; we open the passage, highlighted. Their actions are generic tool calls; ours are curated per-answer affordances. Their cloud is $20–25/user/mo; ours is flat ₹999–1,999 **per company**. Their edge: maturity, 40+ connectors, brand. Our edge: citation depth + graph multi-hop + price.
- **Vs Dust:** ~10× cheaper at 10 seats; self-host trust; they are EU-enterprise oriented.
- **Vs Lindy:** they automate; we prove. Citation-first vs action-first.
- **Vs Atomicwork (India, nearest rival):** they are $25k+/yr ITSM for enterprise; we are ₹1,499/mo whole-company brain for a 20-person firm. Same "cite and verify" instinct, opposite market.
- **Buyer persona:** the **ops lead / founder's chief of staff at a 10–100-person services firm** (agencies, SaaS, CA/legal firms) who personally hunts across contracts, tickets and meeting notes. Indirect evidence that this buyer self-hosts for privacy: current coverage of SMB self-hosted AI viability (aiadvisoryboard.me, 2026) and the large self-host adoption of India-founded OSS (Chatwoot 37k stars, ToolJet ~41k stars).

---

## Part E — Platform strategy: open source + paid cloud, or paid cloud only?

**Recommendation (decisive): open source from day 1 + free hosted BYOK tier + paid convenience cloud.**

### E.1 Why open-core, for this product, now

| Reason | Evidence |
|---|---|
| **The buyer's documents are the product.** Privacy-driven self-host demand among SMBs is real in 2026; Indian-founded OSS (Chatwoot, ToolJet, Appsmith) built large self-host adoption on exactly this trust | aiadvisoryboard.me/blog/objection-privacy-compliance-2026-self-hosted-options; github.com/chatwoot/chatwoot; github.com/ToolJet/ToolJet |
| **Open source drove India OSS GTMs before us** | Chatwoot (MIT core, cloud $0/$19/$39/$99/agent), Appsmith (Free/$15/user/$2,500-per-100), ToolJet (AGPL, ~41k stars, enterprise tier) — stars → trust → cloud |
| **BYOK makes the hosted tier nearly free to run**, so a free hosted tier is viable — the TypingMind/LibreChat/Zoho-Zia pattern | typingmind.com/buy; librechat.ai; zoho.com/agents/pricing.html |
| **Nobody owns "company brain" for SMBs yet** | YC category tag; empty ₹1,500/mo band (D.2) |

### E.2 License choice

- **AGPL-3.0 for our core (recommended)** — the ToolJet/Documenso/Metabase pattern: blocks cloud resellers from hosting our code commercially, keeps genuine self-hosters free. Cognee is Apache-2.0, which permits this.
- Fallback if distribution ever matters more than protection: MIT + an `ee/` folder (Chatwoot model).
- Avoid fair-code/BSL for now (n8n's license explicitly forbids paid hosting — heavier legal surface than a solo operation needs).
- Cautionary tale: **Cal.com went closed-source in April 2026**, keeping only a stripped MIT fork — open-core is a commitment; the mitigations are below.

### E.3 What the paid cloud sells (the standard gated list)

Free/OSS: full brain — ingestion, graph, citations, chat actions, BYOK, self-host connectors (DIY OAuth).
**Paid cloud gates the convenience, not the capability:**
managed OAuth connectors (Gmail/Drive/Slack done for you — dodging CASA is *our* problem, not the customer's), SSO/SAML, SCIM, audit logs, granular RBAC, priority support, retention/compliance. This is exactly what Onyx, Chatwoot and Appsmith gate.

### E.4 Pricing (flat per-company, not per-seat — the anti-Onyx move)

| Tier | Price | What |
|---|---|---|
| Free | ₹0 | Self-host (AGPL) OR hosted BYOK: 1 workspace, DIY connectors |
| Pro | **₹999/mo** | Hosted BYOK + managed connectors + action history |
| Team | **₹1,999/mo** | + SSO, audit logs, more connectors |
| Commercial license | quote | For hosters who want to resell without AGPL obligations |

At ₹1,999 flat for a 20-person company that is **~₹100/seat** vs Onyx's ~₹1,700+/seat —
the price anchor is Slack Business+ (₹557/user/mo), not enterprise search.

### E.5 The risks, honestly

- **Solo-team OSS support burden** — mitigate by gating connector complexity (self-hosters get sync-but-DIY), pinning Cognee, and keeping paid strictly "convenience + connectors."
- **Cloud cannibalization** — minimal: the hosted free tier costs us ~₹0 to run (BYOK + free infra), so even cannibalized users are cheap.
- **Cal.com-style retreat** — the escape hatch is that the paid cloud is genuinely separable (connectors + auth + hosting); the core can stay open without dragging the business.

---

## Verdict table

| Question | Verdict |
|---|---|
| What to implement first | Phase 0 contract test, then local OSS parity — both are days, not weeks, because the REST shape survives. The risky parts are graph-on-Postgres maturity and per-user BYOK. |
| Biggest architectural decision | **Hybrid BYOK**: Cognee for ingestion/retrieval on our free-tier key; answer generation in our FastAPI on the user's key. Cognee's process-global LLM config makes anything else a fight. |
| Hosting | Pilot: Render-free app tier + Cloud Run Cognee + Neon + Aura Free (~$0–3/mo). Real users: one €5–11 Hetzner box. Avoid: HF free Docker (now paid), Fly (free dead), Render/Koyeb free for Cognee (512MB), Oracle (it's a VM we babysit). |
| Do we still build tenancy ourselves? | No — Cognee v1.6.1 ships users/tenants/ACLs/API-keys; we adopt it and retire `tenants.py`, with adversarial isolation tests. |
| Competitors | Nobody has our combo; the India SMB band is empty; Atomicwork is nearest in spirit but enterprise-only; YC just legitimized the "company brain" category name. |
| Platform | **Open source (AGPL-3.0) + free hosted BYOK + paid convenience cloud at flat ₹999/₹1,999.** The Chatwoot/ToolJet playbook, with BYOK making the free tier cost ~₹0 to run. |

**Primary sources:** github.com/topoteretes/cognee @ v1.6.1 (routers, docker-compose, .env.template, entrypoint, issues #4832 #4313 #4364 #3490 #5001 #5035 #4951 #4167) · docs.cognee.ai (changelog, deploy-rest-api-server, llm-providers, relational-databases, graph-stores, multi-user-mode, integrations slack/gmail/drive/linear/github, api-reference) · inference-docs.cerebras.ai/support/rate-limits · console.groq.com/docs/rate-limits · docs.litellm.ai/docs/proxy/clientside_auth · cloud.google.com/run pricing via cloudchipr.com · neon.com/pricing · supabase.com/pricing · neo4j.com/pricing · render.com/docs/free · huggingface.co/docs/hub/spaces-overview + /pro · docs.fly.io/about/pricing · terminalbytes.com/oracle-cloud-free-tier-changes-2026 · learn.microsoft.com (Azure limits) · sqlite.org/whentouse.html · bitdoze.com/cognee-self-host · typingmind.com/buy · librechat.ai/docs/configuration/dotenv · openai/openai-node README · simonw.substack.com (Anthropic CORS) · zoho.com/agents/pricing.html · getmacha.com (Atomicwork, Kore.ai) · cloudtalk.io (Yellow.ai) · eesel.ai (Leena AI) · ycombinator.com/companies/memory-store · slack.com/pricing · atlassian.com/licensing/rovo · clickup.com/brain/pricing · github.com/onyx-dot-app/onyx + onyx.app/pricing · dust.tt/pricing · chatwoot.com/pricing · appsmith.com/pricing · github.com/ToolJet/ToolJet · metabase.com/license · docs.n8n.io/n8n-community-license · cal.com/blog/cal-diy-open-source-to-closed-source · aiadvisoryboard.me/blog/objection-privacy-compliance-2026-self-hosted-options.
