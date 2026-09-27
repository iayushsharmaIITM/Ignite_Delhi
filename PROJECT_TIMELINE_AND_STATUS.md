# PROJECT TIMELINE & STATUS — Kestrel Company Brain

**What this is:** the complete, factual record of every phase of work on the
planned app development — the events, the decisions, the incidents, and exactly
where production stands today (28 Sept 2026). Built from the commit history
(`git log`), PLAN.md (locked 27 Sept), and the live state of the running stack.
Commit hashes are cited so every claim is auditable.

---

## 1. The locked plan (PLAN.md, 75eb852 — 27 Sept, 01:46)

Seven phases, each ending green on the `verify.sh` battery:

| Phase | Scope | Status |
|---|---|---|
| **P1** | The flip — app answers from OUR local Cognee brain | ✅ **COMPLETE** (3d694c1) |
| **P2** | Postgres persistence + token metering + history summarization | ✅ **COMPLETE** (45105b6, e49b42a) |
| **P3** | Clerk auth — sign-in gate, JWT verification, org isolation | ✅ **COMPLETE** (23cf84a, d497757) — one owner action pending |
| **P4** | Heroku deployment + brain hosting + CI + domain | ⬜ **NOT STARTED** — this is the next phase |
| **P5** | Model routing formalization (Langfuse-visible cost split) | ⬜ NOT STARTED (smalltalk routing already shipped early) |
| **P6** | Pydantic AI agents + MCP connectors (Slack, Google) | ⬜ NOT STARTED |
| **P7** | Launch — pricing enforcement, onboarding, AGPL packaging | ⬜ NOT STARTED |

Locked decisions: Clerk Pro auth · Heroku app tier · DeepSeek V4.1 Flash
default (gpt-oss-120b recall) · Pydantic AI agents · Langfuse metering ·
**no semantic caching on the citation path, ever** · brain hosting:
local (dev) → Cognee Cloud (pilot) → Hetzner CX22 (prod).

---

## 2. Act 0 — Foundations: the hackathon build (19 Sept)

Everything from `c4b215e` through `24a2308`. The product existed as a working
demo on Render Workflows before any product plan:

- Cognee + Render Workflows wiring; ingest fan-out made testable against
  scratch datasets (8a44020); `wf_smoke.py` — a workflow probe that cannot
  touch the demo graph (20fa8d7), created after an array-wrapped CLI input
  silently ingested junk into the demo graph and had to be surgically removed.
- Reliability hardening: `/health` proves the key works (8b11681), graph falls
  back to a committed snapshot when the tenant is unreachable (fa2d69e).
- **Upload path:** build a company brain from uploaded documents (a1ac542) —
  the step that turned a demo into a product direction.
- **Citations:** real source citations that open the document with the cited
  passage highlighted (ff72671, d2f0a13).
- Product surface: app shell with left sidebar (f6c0ccf), clickable graph with
  node inspector (17bca97), conversational thread with follow-ups and
  Word/PDF export (d751898, eb9f034), per-brain snapshots (7477a1d),
  per-brain chat history (7f72060), multi-chat sidebar navigation (5439f1b),
  sub-node graph zoom (645c13b), answer-derived suggestions (2dab24e).
- **Code audit + bug report:** a full audit found 3 critical, 5 high, 7 medium
  bugs (694123b); all critical/high and 6 of 7 medium fixed and verified by
  execution (24a2308, 280ec42).

## 3. Act 1 — Research, economics, and the locked plan (25–27 Sept)

- **M1.1 provider hunt:** a swappable 9-provider LLM registry (990e27f);
  Bedrock keys refused repeatedly → root-caused to the AWS account being
  **pending verification** (465c8c6); OpenRouter light-mode trial went LIVE
  (e16746f) — contract 11/11, 2-doc cross-document recall proven on local OSS.
- **Business cases written:** Indic company-brain pricing (f7fc8ec),
  self-hosted Cognee + DeepSeek business case (6b778e8), **GitHub Student
  Developer Pack proposal** (0da0564 — the document that locked Clerk Pro +
  Heroku + the multi-tenancy strategy), global grants survey (ba6f607).
- **PLAN.md locked** (75eb852): the 7-phase consolidation above.

## 4. Act 2 — The UX overhaul to "Deck" (26 Sept)

The owner drove a redesign to match the ZCode-desktop chat anatomy:

- Design system v2 monochrome + falcon amber (ca57183) → Paper theme
  (eca0b76) → **final Deck dark palette** with centered home, composer card,
  user turns as cards, white circular send (a8978fb).
- Composer-centric chat bar per CHATBAR_DESIGN.md: brain switcher,
  in-chat file add, send/stop state machine (d5b731e, 0c4d6c4).
- **The orchestrator (head agent)** — the latency engine of the product:
  retrieval racers (graph vs vector, first answer wins, loser cancelled),
  citations prewarmer overlapped with retrieval (0-warm grounding), (3976297).
- Streaming polish: stick-to-bottom reading model, jump-to-latest pill (75f48a4);
  scroll-linked reading rail (c97729c).
- Sidebar: chats grouped under retractable brain folders, hover-only two-step
  deletes, View/Sort menu (6aac8d1); cross-brain history (ab206d3).
- A root-cause fix worth remembering: stale `Cache-Control` was serving old
  CSS after redesigns (2b90d0a) → `/static` now no-cache.

## 5. Act 3 — P1: the local-brain flip ✅ (27 Sept, 3d694c1)

- DeepSeek V4.1 Flash validated for ingest, gpt-oss-120b for recall.
- The 12-doc corpus ingested into the local Cognee OSS container; a volume
  loss forced a rebuild 178 → **246 nodes / 587 edges**; colima resized to
  4 CPU / 8 GB; graph snapshot committed as fixtures (de9b7c8).
- App parity flip: `COGNEE_SERVICE_URL=localhost:8888`, flavor `oss` —
  all demo questions + citations answer from OUR brain, verified in the
  browser. Battery green.

## 6. Act 4 — P2: persistence, metering, speed ✅ (27 Sept, 45105b6 + e49b42a)

- **Postgres 17** (kestrel-db, port 5433) became the source of truth for
  chats/turns; localStorage demoted to a cache with server-first restore.
- **Token metering:** `llm_calls` table (chars/4 estimates) + `/api/usage`.
- **History summarizer** (`/api/summarize`) for bounded multi-turn context.
- **The smalltalk saga** — the most instructive debugging stretch:
  1. "hii" took 19–26s because the smalltalk flag died at the
     recall→orchestrator boundary → threaded end-to-end, durable `.env`
     flip; **26s → 2.2s** (adf0ff2).
  2. "hello how are you" took 30s and produced **fake citations** → the
     exact-string whitelist was replaced by a **social-vocabulary
     classifier** (greetings/thanks/identity/goodbyes, word-capped);
     e6003b6.
  3. Restore heals local-only chats through the server's authoritative
     strip — stale fake citations on greetings no longer render (de435ff).
- Recall retry on transient 402/5xx (OpenRouter flaps); DeepSeek kept for
  ingest, gpt-oss-120b for recall.

## 7. Act 5 — P3: Clerk auth end-to-end ✅ (27–28 Sept)

**Backend (23cf84a):** `auth.py` (env-gated, JWKS-verified, fail-closed, test
seam), brain ownership in Postgres (shared vs org-owned), org-scoped chat
listing, identity gate in `require_tenant` + `brain_allowed` in the dataset
funnel. Isolation suite passing (roundtrip, fail-closed, cross-org 403, chat
scoping).

**The UI build and its three real bugs** (d497757) — found by instrumenting
the actual clerk-js bundle, not by guessing:
1. The sign-in form never rendered because **`window.Clerk.load()` was never
   called** — script-eval only reads the publishable key; the FAPI call list
   proved Clerk never reached the network. One explicit boot call fixed it.
2. **The JWKS cache stored the timestamp but never the keys** — the first
   authenticated request worked, every request for the next 10 minutes
   KeyError'd and failed closed (401). Regression test added.
3. The P3 refactor left `tenant.allows` referencing a renamed binding — every
   legacy-tenants request 500'd. Battery caught it; fixed.

**Verified live end-to-end:** mounted sign-in form → phone sign-in (Clerk's
reserved dev number +41555550100, code 424242) → session token → backend JWKS
verification → 200s; without token → 401. Session survives reloads and app
restarts.

**The reload-loop incident (471a243):** after signing in via the Account
Portal and redirecting back, clerk-js's client reload makes the `user` ref
transiently null; the gate treated that as signed-out and mounted `<SignIn>`
while a session existed — Clerk answered by redirecting to `afterSignIn`,
i.e. a full page reload, forever. Fix: signed-in means **"client holds
sessions"**, and the form mounts only with zero sessions. Verified: the
portal round-trip now lands stable (12s+ sampled, zero flaps).

**Settings system (9856e1a)** — matching the owner's reference anatomy:
sidebar user row (avatar, name, gear) → **Language** (English default +
हिन्दी, Español, Français, Deutsch, 中文 — live re-render, persisted),
**App theme** (system default with live `prefers-color-scheme`, dark, light),
**Usage stats** (real `/api/usage`: per feature/brain/model calls, tokens,
compute time), **Upgrade** (Free/Pro ₹999/Business ₹1,999 — honest
"coming soon" until Clerk Billing plans publish), **Manage account** (Clerk
profile modal), **Disconnect** (sign-out, gate returns). Plus `static/ui.js`
(theme + i18n applied before first paint) and `static/auth.js` (shared Clerk
bootstrap — the upload/brains/graph pages silently 401'd before this).

**Readability (16a7165):** a WCAG audit found real failures — dark
`--muted-2` at 2.4–3.3:1, light `--muted-2` at 2.4–3.0:1, light accent text
at 2.7:1, the send button white-on-white in light. All fixed (light accent
deepened to #b45309); the Clerk gate is now theme-matched in both themes.

**Clerk surfaces (d0afe1c, 0a039bc):** the Account modal follows the app
theme (it was called without an appearance), and the "Primary" badges —
measured at white 8% alpha on 0.4% background, i.e. invisible — are styled
by our own theme-aware CSS in both themes.

**The slide animation (040c4aa):** a gliding hover rail in the sidebar — one
element slides between rows with spring easing and shrinks to a 2px
cursor-tracking tick in the gutter, fading on leave; degrades to static
hover if JS fails; `prefers-reduced-motion` respected.

**Old chats verified valid:** a pre-auth-format chat restores from local
storage, appears in the sidebar, and *continues* — new messages sync to the
server under the signed-in identity (`org_id = %s OR org_id IS NULL` keeps
org-less chats visible). Listing is identity-scoped; opening by exact id is
not yet org-checked (P4 hardening item).

---

## 8. WHERE PRODUCTION STANDS — 28 September 2026

**Staging today = the local machine. Nothing is deployed to Heroku yet.**

| Component | Status | Where it runs |
|---|---|---|
| FastAPI app tier | ✅ running | `127.0.0.1:8000` (Python 3.13, `app.py`) |
| Cognee OSS brain | ✅ running, healthy | `cognee-oss` container (cognee/cognee:1.6.1), port 8888 via colima (4 CPU / 8 GB), graph 246 nodes / 587 edges |
| Postgres 17 | ✅ running | `kestrel-db` container, port 5433 — chats/turns/brains/llm_calls |
| Auth | ✅ live | Clerk dev instance `ample-skink-6708` (Pro via Student Pack); AUTH_MODE=clerk; JWKS verification + isolation suite 5/5 |
| Verification | ✅ green | verify.sh: documents 25/25 · pipe-states 13/13 · tenants 10/10 · smoke 4/4 · UI pass |
| Domains / TLS / Heroku | ⬜ none | P4 not started — no Procfile, no CI, no deploy target yet |
| Owner actions pending | 2 | (1) Enable **Organizations** in the Clerk dashboard (unlocks live org isolation + retire `tenants.py`); (2) make **phone optional at sign-up** (Configure → User attributes → Phone number → off for sign-up) — dev instances also cannot SMS India, which is what blocked sign-up |

**Bottom line:** P1–P3 are complete and proven; the product is a signed-in,
multi-theme, multi-language, metered, Postgres-backed brain running entirely
on the local machine. The next eventful step is **P4: Heroku deployment**
(container/eco dyno + Postgres Mini + env vars + CI + domain), with the brain
either staying local for the pilot or moving to a Cognee Cloud tenant —
Hetzner CX22 for production (Heroku dynos OOM Cognee; that failure class is
verified and documented in PLAN.md).

---

## 9. Incidents worth remembering (each fixed, each with a lesson)

| Incident | Root cause | Fix |
|---|---|---|
| "hii" answered in 26s | flag died at the recall→orchestrator boundary | threaded end-to-end; durable `.env` flip (adf0ff2) |
| Greetings cited documents | exact-string greeting whitelist | social-vocabulary classifier v2 (e6003e6/de435ff) |
| Stale CSS after redesigns | heuristic static caching | `/static` no-cache (2b90d0a) |
| Sign-in form never rendered | `Clerk.load()` never called | explicit boot + verified FAPI calls (d497757) |
| Auth 401s for 10-min windows | JWKS cache stored ts, not keys | fixed + regression test (d497757) |
| Tenants suite 500s | renamed binding left dangling | `identity.allows` (d497757) |
| Gate reload-loop after portal sign-in | mounting `<SignIn>` while a session existed | session-aware state + zero-session mount guard (471a243) |
| "Primary" badges invisible | Clerk internal alpha tokens | our own CSS override (0a039bc) |
| Unreadable greys both themes | WCAG failures in the palette | measured audit + new light accent (16a7165) |
| Junk ingested into the demo graph | array-wrapped CLI input | `wf_smoke.py` guardrails (20fa8d7) |
