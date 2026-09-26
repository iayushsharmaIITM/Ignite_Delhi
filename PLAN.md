# PLAN.md — the complete product build plan (locked 27 Sept 2026)

Consolidates BUILD_PLAN.md (OSS migration), CHATBAR/UX work (shipped), and the
economics research into ONE execution plan. Decisions below are LOCKED by the
owner; each phase has acceptance tests and nothing skips the `verify.sh` battery.

---

## LOCKED DECISIONS

| Decision | Choice | Why |
|---|---|---|
| Auth | **Clerk Pro** (free via GitHub Student Pack, 10k MAU) | Orgs = workspaces; replaces `tenants.py`; zero cost for 24 months |
| App hosting | **Heroku** ($13/mo credit × 24 mo from the pack) | App tier is light; credit covers it |
| LLM default | **DeepSeek V4.1 Flash** ($0.15/$0.003-hit/$0.60) + gpt-oss-120b fallback block | Cheapest agentic economics; cache-hit friendly; validated via registry |
| Agent layer | **Pydantic AI** (phase A6) | App owns the loop, typed outputs, native MCP, usage limits |
| Observability | **Langfuse** (Cloud free tier → self-host later) | Cost per user/feature/brain becomes a dashboard, not estimates |
| Token efficiency | **History summarization + model routing** | Caps input growth; right model per query class |
| NO semantic caching on the citation path | ever | A fuzzy cache hit = a fabricated citation. Disqualifying |
| Brain hosting | dev=local colima · pilot=Cognee Cloud tenant · prod=€5 Hetzner | Heroku 512MB–1GB dynos OOM Cognee (verified class of failure); 2GB = $50/mo not worth it |

## MONEY (the honest table)

| Line | Pilot | At 50 users |
|---|---|---|
| Heroku app dyno (Eco) + Postgres Mini | $10/mo — **credit covers** | ~$10–25/mo |
| Brain (Hetzner CX22, prod) | — (local/cloud tenant) | €6/mo |
| DeepSeek tokens (measured model) | ~$2–6/mo | ~$25–45/mo |
| Clerk / Langfuse (pack + free tier) | $0 | $0 until 10k MAU |
| **Total real spend** | **≈ $2–6/mo** | **≈ $40–75/mo** vs revenue at ₹999×50 = $565 → ~87% margin |

---

## PHASES (execution order; each ends green on verify.sh + its acceptance)

### P1 — The flip: app answers from OUR brain (1 session)
1. Validate DeepSeek V4.1 Flash in-pipeline: registry block, one live question,
   check extraction JSON + cache-hit pricing in response usage. Fallback stays gpt-oss.
2. Full 12-doc corpus ingest into local brain (off-peak), snapshot graph.
3. App parity flip (`COGNEE_SERVICE_URL=localhost:8888`, flavor oss): all 4 demo
   questions + citations answer locally. ← M1.3 + Phase 1 gate of the old plan.
4. Measure (M1.4): memory, cold start, first-recall latency — feeds prod sizing.

### P2 — Persistence + metering (1–2 days)
1. Postgres schema (chats, turns, attachments, workspaces) — server-side chat
   storage; localStorage becomes a cache, not the source of truth.
2. **Langfuse** wrapper on every LLM call in the orchestrator: per-user, per-brain,
   per-feature token cost + latency. The pricing model becomes observable.
3. History **summarization**: past ~8K tokens of a chat → rolling summary
   (cheap DeepSeek call), prefix kept stable for cache hits.

### P3 — Clerk auth (1–2 days)
1. Clerk app (Pro): sign-in, organizations = workspaces.
2. FastAPI middleware: verify Clerk session JWT (JWKS), attach user+org.
3. Map Clerk org → brains (org_id on brains, chats); `tenants.py` retired.
4. Acceptance: two Clerk users in two orgs can never read each other's brains
   (the old 10/10 isolation suite, rerun against Clerk identities).

### P4 — Heroku deployment (1 day + brain decision)
1. App: Heroku container/eco dyno, Postgres Mini, env vars, `/health` check.
2. Brain: pilot on Cognee Cloud tenant (zero cost) OR local; prod on Hetzner CX22
   (docker compose, same compose.oss.yml pattern) — app reaches it over HTTPS.
3. Domain (Namecheap pack year) + TLS.
4. CI: GitHub Actions runs verify.sh + contract_test on every push.
5. Acceptance: `smoke.py --base https://<domain>` 4/4 from cold.

### P5 — Model routing (1 day, extends the orchestrator)
Router classifies before delegation:
- smalltalk → no retrieval, refs off (exists)
- factual/grounded → DeepSeek V4.1 Flash
- extraction/ingest → DeepSeek off-peak batch window
- premium request → user's BYOK key (when P6 ships)
Acceptance: Langfuse shows per-route cost split; router is data-driven, not vibes.

### P6 — Agent actions layer, Pydantic AI (3–5 days)
1. `agents/` package: Pydantic AI agents with typed outputs + usage limits.
2. Email-composition agent (real LLM drafts — replaces the removed heuristics),
   chat-update agent; per-answer action buttons call agents.
3. MCP connectors: Slack first (official MCP), then Google (Gmail/Drive) —
   sync into brains with the existing ingest pipeline; approval gate on any send.
4. Acceptance: a question → agent drafts an email citing the exact sources;
   connector sync lands in the brain and is answerable; nothing sends without approval.

### P7 — Launch (2–3 days)
Pricing enforcement (Free fair-use caps measured by Langfuse), onboarding,
README/quickstart, AGPL-3.0 + docker-compose quickstart, hosted-free-tier story.

---

## WHAT IS ALREADY DONE (do not rebuild)
Chat product (ZCode-anatomy UI, streaming, stick-to-bottom), orchestrator with
racers + prewarmer (citations 33–100ms warm), 9-provider key registry, local
brain built + contract-verified 11/11, verify.sh battery (25/25, 13/13, 10/10,
smoke 4/4, UI 16/16), smalltalk gate, attachments→context+ingest, exports,
grouped cross-brain history with retract/delete/sort.

## ORDER OF EXECUTION
P1 → P2 → P3 → P4 → P5 → P6 → P7. P1 uses the OpenRouter key for ingest
(~$0.50) then flips to DeepSeek for steady-state.
