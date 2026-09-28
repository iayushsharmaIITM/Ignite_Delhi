# CLAUDE_CONTEXT.md — complete handoff for Claude Opus 5.5

**Written:** 28 Sept 2026, late evening. **Author:** ZCode (GLM-5.3-Flash),
which built and verified everything described here. **Read this top to bottom
once** — it is the complete state of the project, the history, the decisions,
the traps, and the next steps. Deeper sources are listed in §11.

---

## 1. What this project is

**Kestrel Company Brain** — a FastAPI web app where a company uploads its
documents, a knowledge graph is built (Cognee), and users ask business
questions in a chat that streams grounded answers **with citations back to the
source documents** (click a citation → the source passage opens).

Owner: **Ayush Sharma** (smartyayush333@gmail.com). **Investor demo: tomorrow,
Tuesday 29 Sept.** The product is demo-ready as of tonight — everything in §3
was verified on the live stack within the last hours.

## 2. Architecture (what runs where)

| Component | Tech | Location |
|---|---|---|
| Web/app tier | FastAPI (`app.py`), static UI in `static/` | `127.0.0.1:8000` |
| Brain | Cognee OSS 1.6.1 container (`cognee-oss`), embedded graph (ladybug) | `localhost:8888` via colima |
| Database | Postgres 17 (`kestrel-db`): chats, turns, brain ownership, `llm_calls` metering | `localhost:5433` |
| Auth | Clerk (dev instance `ample-skink-6708`, Pro via GitHub Student Pack), AUTH_MODE=clerk | JWT verified against JWKS in `auth.py` |
| LLMs | Ingest: DeepSeek V4.1 Flash. Recall: gpt-oss-120b. Both via OpenRouter (key in `.env.oss` as LLM_API_KEY) | OpenRouter API |
| OCR (new tonight) | PyMuPDF renders scanned pages locally → one vision call (`openai/gpt-6-luna`, fallbacks free) via OpenRouter | `ocr.py` |
| Containers | Started via `docker compose -f compose.oss.yml up -d` | colima (4 CPU / 8 GB) |

Key files: `app.py` (routes, authz funnel, rate limits) · `memory_layer.py`
(mock|cloud switch, smalltalk classifier, streaming stages) ·
`orchestrator.py` (head agent: router sub-agent + retrieval racers + hedged
retrieval, `KESTREL_HEDGE_SECONDS` default 8) · `citations.py` ·
`documents.py` (upload validation + text extraction) · `ocr.py` (stage-2
vision OCR) · `storage.py` (Postgres) · `auth.py` (Clerk JWT, fail-closed) ·
`static/` (index/upload/brains/graph pages + `shell.js` sidebar +
`ui.js` i18n/theme + `auth.js` Clerk bootstrap) · `verify.sh` · `warmup.py` ·
`DEMO_DAY.md` (**tomorrow's runbook — start there on the morning**).

## 3. Current verified state (all checked today, on the live stack)

- **Demo brain `company_brain`:** 12 documents ingested, graph 93 nodes / 161
  edges live (101/173 in the committed fixture `fixtures/graph.json` — same
  graph, different moments). NOTE: pre-wipe it was 246/587 — the re-ingest ran
  on gpt-oss-120b instead of DeepSeek, which extracts a sparser graph. All
  demo questions answer correctly regardless; a DeepSeek re-ingest (~$0.50,
  off-peak) can restore depth post-demo.
- **Warmup rehearsal: ALL GREEN twice.** Q1 23–25s · Q2 ~38–45s (the one SLOW
  question — present as the "deep question") · Q3 28–34s · Q4 24–29s — every
  answer with citations. Profiled (see §6): retrieval is 90–100% of wall time;
  it's upstream LLM latency variance, not our code.
- **Battery green:** `verify.sh` → documents 25/25, pipe-states 13/13,
  tenants 10/10, smoke 4/4, UI 16/16; auth isolation suite 5/5.
- **Auth live:** sign-in gate works (mounted Clerk form); sessions survive
  reloads/restarts; demo brain is **creator-owned** — only Ayush's account
  (user_3JvGjL6x2VWrmAa0IYcvdckHbMv) can read it; anyone else gets 403 by
  design.
- **Chat attachments now answer:** text files client-side; **PDFs (including
  image-only scans) via server-side extraction + OCR ladder** — attached PDF
  + "what is this about?" names its actual contents. Verified end-to-end
  tonight, including a true image-only PDF.
- **All UI:** Deck dark theme + light theme + system-follow, 6 languages
  (en/hi/es/fr/de/zh), settings menu (language/theme/usage stats/upgrade/
  manage account/disconnect), sliding hover rail in the sidebar, grouped
  cross-brain chat history, exports (MD/TXT/DOCX/PDF), graph explorer.

## 4. History in one minute each

- **19 Sept (P0):** hackathon build on Render Workflows — ingest fan-out,
  citations, exports, sidebar, graph; a 45-bug audit fixed.
- **25 Sept:** 9-provider LLM registry; Bedrock blocked (account pending
  verification — root-caused); OpenRouter light-mode trial live; business
  cases written; **GitHub Student Pack chosen** (Clerk Pro + Heroku credits).
- **26 Sept:** UX overhaul to the "Deck" dark anatomy; **orchestrator with
  retrieval racers + citations prewarmer** (the latency engine); composer;
  sidebar groups.
- **27 Sept (P1–P3):** P1 local-brain flip complete; P2 Postgres persistence +
  token metering + summarizer + smalltalk fast paths (26s greeting → 2.2s);
  P3 Clerk auth backend + UI + the three boot/cache bugs.
- **28 Sept (today):** Muse/opencode audit session fixed **59 defects** (all
  10 SEC incl. two criticals, 9 frontend, 15 correctness, 11 hardening + 14
  self-found) — see `BUGS_AUDIT.md` (historical queue; everything in it is
  fixed) and `PROGRESS.md`. Then ZCode: settings system, WCAG contrast audit
  fixes, gate reload-loop fix, Clerk modal theming, PDF/DOCX answer path,
  OCR ladder, demo runbook. **Team scaffolding (AI_TASKS/AI_RESULTS/etc.) was
  removed at Ayush's request — ZCode is now sole builder.**

## 5. Locked decisions (do not relitigate)

- Clerk Pro auth; **citation path: NO caching/fuzzy matching, ever** (a fuzzy
  hit = a fabricated citation).
- **Single-brain mode locally** — the embedded graph is single-tenant; the
  demo brain is company_brain; **never create new local brains** (it pollutes
  the demo graph, proven 108/108 overlap).
- LLM default DeepSeek V4.1 Flash (ingest) + gpt-oss-120b (recall).
- Brain hosting: dev=local colima · pilot=Cognee Cloud · prod=Hetzner CX22
  (Heroku dynos OOM Cognee — verified failure class).
- Agent layer = Pydantic AI (P6); observability = Langfuse (P5).

## 6. Traps and gotchas (each one cost real time — learn them cheap)

1. **Restarting the app:** kill **by port** — `lsof -nP -iTCP:8000
   -sTCP:LISTEN -t | xargs kill`. `pkill -f "python3 app.py"` does NOT match
   (process is `Python app.py`) → stale server keeps serving old code while
   the new one dies on "address already in use".
2. **Owner sign-in without a password** (demo brain is creator-owned):
   `source .env` → `POST https://api.clerk.com/v1/sign_in_tokens` with
   `{"user_id": "user_3JvGjL6x2VWrmAa0IYcvdckHbMv", "expires_in_seconds": 7200}`
   → open the app → in DevTools:
   `const r = await Clerk.client.signIn.create({strategy:'ticket', ticket:'<TOK>'}); await Clerk.setActive({session: r.createdSessionId});`
   Full recipe in `DEMO_DAY.md` §2.
3. **Clerk session JWTs expire every 60s** — warmup.py takes `--token-file`
   (re-read per request); pair with a loop calling
   `Clerk.session.getToken()`.
4. **Dev instances cannot send SMS to India at all** (and phone was made
   optional at sign-up). Use email/password, Google, or the reserved
   `+15555550100` / code `424242` in dev.
5. **`/static` is no-cache by design** — after editing UI files, just reload.
6. **zsh glob trap:** `ls a* b*` aborts entirely if one pattern matches
   nothing — existence checks must use `test -e` per item (this once produced
   a false "file doesn't exist" in the log).
7. **Scanned PDFs** have no text layer: stage-1 pypdf raises `ExtractEmpty`
   → OCR ladder fires (PyMuPDF local render → vision call). Password-
   protected and truly blank PDFs get honest 400s.
8. **Blindly string-matching error messages breaks silently** when a message
   changes — branch on exception types (this bit once: OCR never fired).
9. **Colima down = containers gone but volumes persist** (`cognee_oss_data`,
   `cognee_oss_state` are docker volumes now — the graph survives recreates;
   `colima start` + compose up restores everything).
10. **The OCR/vision calls and the brain ingest both spend real money/keys** —
    OpenRouter key is in `.env.oss` (LLM_API_KEY). Secrets never go in
    tracked files.

## 7. Open decisions — Ayush's alone

1. **P4 hosting** (next phase): a complete **Render Blueprint**
   (`render.yaml`, both tiers) is committed; PLAN.md locked **Heroku**
   (Student Pack $13/mo × 24). Pick one before P4 starts.
2. **Q2 latency** (~38s warm): accept as the "deep question" or spec a fix —
   the lever is the recall model/retry, and the hedge infrastructure already
   exists (`KESTREL_HEDGE_SECONDS`).
3. **Graph depth:** accept 93/161 or DeepSeek re-ingest post-demo.
4. **SEC-5 backfill:** legacy NULL-org chat rows are grandfathered
   visible/deletable (safe default taken owner-absent); a real owner call can
   tighten it.
5. Old `BUGS.md` **M4 (TOCTOU)** remains open (pre-audit era).

## 8. Verification commands

```bash
./verify.sh                                   # full battery (mock-forced)
python3 -m pytest test_auth_isolation.py -q   # 5/5
python3 warmup.py --token-file /tmp/tok.txt   # needs owner token file (§6.2/§6.3)
python3 -m pytest test_documents.py test_pipeline_states.py -q
```

## 9. Tomorrow morning (Sept 29)

Follow **`DEMO_DAY.md`** exactly: stack start (colima → compose → app),
owner sign-in, warmup with token file → expect ALL GREEN with Q2 ~38s.
Fallback if the tenant misbehaves: `PROVIDER=mock` + committed fixtures
(101/173 graph snapshot) — rehearsed, boring, safe.

## 10. Do NOT do

Do not create local brains; do not re-ingest/delete datasets without Ayush;
do not touch the citation path's semantics; no force-push/history rewrite; no
new dependencies without approval; secrets stay in `.env`/`.env.oss`.

## 11. Deeper reading (in order)

`DEMO_DAY.md` (morning runbook) → `PROGRESS.md` (fix-session record) →
`BUGS_AUDIT.md` (the 45-item audit, all fixed) → `PLAN.md` (locked 7-phase
plan; P1–P3 done, P4 next) → `PROJECT_TIMELINE_AND_STATUS.md` (full history
through 28 Sept morning) → `INDIA_PRICING.md`, `STUDENT_PACK_STACK.md`
(business case) → source: `app.py`, `orchestrator.py`, `memory_layer.py`.

**Git:** single branch `main`, one commit per logical change, history is
clean and green at `e07a219` (OCR ladder). Nothing uncommitted but the
future.
