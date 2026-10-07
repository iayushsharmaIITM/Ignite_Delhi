# COMPETITOR_ANALYSIS.md — where Kestrel stands, and what to take from whom

**Written:** 30 Sept 2026. Sources: G2 Dashworks-vs-Glean comparison (Aug 2026),
fast.io Notion AI Review 2026, agentwork.com Guru-alternatives piece (Jul 2026),
Lucenia-vs-Glean, glean.com, fueler.io copilot roundup. Links inline.

---

## 1. The landscape

| Competitor | Model | Price | Connectors | Citations | Agents | Deployment |
|---|---|---|---|---|---|---|
| **Glean** | SaaS, enterprise contracts | ~$50+/user/mo, quote-based (often six figures/yr) | **100+ pre-built**, real-time permission sync | Permission-aware, cited answers; the most mature company knowledge graph | Gleanbot in Slack (in-flow answers), agent builder | Cloud only — "black box SaaS", zero deployment flexibility (Lucenia) |
| **Dashworks** | SaaS, mid-market | **~$10–15/user/mo, transparent tiers** | Strong coverage (Slack, Drive, Notion, Jira…) | Permission-aware with citations | Answers + some workflow actions | Cloud |
| **Notion AI** | Bundled into Notion plans | Business $20/user/mo (AI + connectors included) | "AI Connectors" to external apps — newer, shallower | Cited, but broader search is shallower than dedicated platforms | Q&A-oriented, limited actions | Cloud, native to Notion |
| **Microsoft 365 Copilot** | Bundled into M365 | $30/user/mo | M365-native (deep), thin outside | Citations vary by surface | Copilot agents (2026) | Cloud |
| **GoSearch / Guru / Moveworks** | SaaS | varies | federated deployment speed is the pitch | varies | varies | Cloud |

## 2. Where Kestrel already matches or beats them

- **Citations with passage-level provenance** — ours open the source document
  at the cited passage (Glean/Dashworks cite the source; the deep-link-to-passage
  UX is where we are at least at parity).
- **Self-hostable brain** — Glean/Dashworks/Notion are cloud-only. Our brain is
  a container (dev local, pilot Cognee Cloud, prod Hetzner CX22 per PLAN.md) —
  a genuine differentiator for buyers who won't put contracts in someone else's
  cloud.
- **Per-route cost observability** (P5 Langfuse) — none of the SaaS competitors
  expose per-user/per-route token economics; ours is a dashboard. This powers
  the fair-use caps in P7.
- **Transparent pricing lane** — Dashworks proved the mid-market pays for
  transparent per-seat pricing ($10–15). Our ₹999/$12 lane sits exactly there —
  with the honesty of publishable limits (200 answers/mo on Free).
- **DeepSeek-only economics** — the stack runs on ~$0.36/M blended; competitor
  stacks bury OpenAI-class inference in opaque contracts. Our gross margin
  structure (~87% at scale per PLAN.md) survives the pricing lane above.

## 3. What they have that we must match (the honest gaps)

| Gap | Who has it | Our answer (P6/P7) |
|---|---|---|
| **Connector breadth** | Glean 100+, Dashworks ~40 | P6 connectors: Slack (done), Gmail/Drive (OAuth done, sync workers next), then Notion/Jira via the same vault pattern. Breadth is a roadmap, not a rewrite — every connector is one vault provider + one import path |
| **Permission sync** | Glean real-time | We enforce identity at ask-time (fail-closed brain gate) — per-document ACL sync is the post-demo hardening item |
| **In-flow answering** | Gleanbot in Slack | P6 Slack send path exists (env-gated); the natural extension is an @mention responder behind the approval gate |
| **Agent actions on answers** | Glean agent builder (enterprise) | **Our P6 is this**: email/message drafts with typed outputs, send on approval — shipped. The differentiator to market: agents constrained to cited facts (no invention) with the approval gate |
| **Model selection** | Notion AI (model picker) | Token Harbor + provider blocks already make this one env swap |

## 4. The positioning sentence

> Kestrel is the self-hostable company brain: contract-grade citations down to
> the passage, your choice of models (DeepSeek-only economics or BYO), agents
> that act on answers with a human approval gate — at mid-market pricing with
> published limits, on infrastructure the buyer can run themselves.

The wedge against Glean is deployment + price; the wedge against Notion AI is
depth (a real knowledge graph with passage citations, not workspace search);
the wedge against Dashworks is the agent layer with the approval gate and the
open deployment story.

## 5. Next competitive moves (in priority order)

1. **Slack in-flow answering** (post-P6 send path): an @Kestrel responder in
   connected workspaces — Gleanbot parity, and the connector work is 80% done.
2. **Sync workers** (the previous session's plan): Gmail historyId, Drive
   changes, Slack per-channel cursors — turns "import" into "stay current",
   which is what Glean's permission-sync buyers actually evaluate.
3. **Connector count as marketing**: each new vault provider is a landing-page
   line — the vault makes breadth cheap.
4. **Publish the security story**: Fernet-encrypted grants, minimal scopes,
   single-use state binding, per-tenant isolation — the CASA/enterprise
   questionnaire answers exist in the design already (`connectors.py` docstring).

## 6. Sources

- G2 — [Dashworks vs. Glean Comparison 2026](https://www.g2.com)
- [fast.io — Notion AI Review 2026](https://fast.io)
- [agentwork.com — Best Guru Alternatives for AI Search (Jul 2026)](https://agentwork.com)
- [Lucenia vs Glean](https://lucenia.io)
- [fueler.io — AI Copilot Tools roundup (Mar 2026)](https://fueler.io)
