## Router sub-agent — non-brain queries bypass retrieval 2026-09-27

Owner request: queries unrelated to the brain must fast-track. Design: the
orchestrator launches a ROUTER sub-agent concurrently with the retrieval
racers — a tiny classification call (fixed instruction prefix, cache-hit
friendly, ~1-2s) deciding BRAIN vs CHAT. CHAT cancels the racers and answers
via a direct completion (time-aware: current datetime in the prompt); BRAIN
lets the racers continue with zero added latency. Router failure or ambiguity
defaults to BRAIN (a misroute to retrieval costs seconds; a misroute to chat
costs trust).

Measured: "What time is it here?" — router bypasses, correct datetime answer,
9s total (was 11-25s through the brain). Brain questions unchanged (5
citations; routing overlapped, not additive).

## Stale-citation healing on restore — 2026-09-27

Chats saved before the smalltalk fix carried fake citations on greetings and
re-rendered them on restore. Fix: restoreHistory now heals local-only chats by
pushing them through the server's authoritative strip (POST -> GET) before
rendering; storage.upsert_chat strips sources from smalltalk AND social-reply
bot turns (memory_layer classifiers are the single source of truth). Narrow
JS guard kept for fully-offline rendering. Verified: stale seeded chat renders
0 citations on both turns.

## Smalltalk classifier v2 — social-vocabulary based 2026-09-27

Owner flagged the logic gap: "hello how are you" fell through the narrow
greeting regex into a 30.8s retrieval that cited random documents for a
greeting. Rewritten as social-vocabulary classification (greetings +
how-are-you + thanks + identity + goodbyes, optional filler words, <=8 words,
greeting+social sequences) instead of exact-string whitelisting. Verified:
22-case matrix, 0 misroutes. Fake citations for greetings are now impossible
(smalltalk path never touches the brain).

## Smalltalk latency root cause — FIXED 2026-09-27

"hii" as a follow-up took 19-26s: the flag died at the recall->_cloud boundary
(the wrapped query defeated the regex) AND the app restart had dropped the
local-brain env. Fixed: flag threaded end-to-end (app raw q -> recall ->
_cloud -> orchestrator), .env now durably points at localhost:8888 (flavor
oss, timeout 1800), greeting template judged on the wrapped query's last line.
Measured: follow-up "hii" completes in 2.2s (was 19-26s); pure greetings are
instant templates; chatty smalltalk = one direct completion.

## P2 — persistence + metering + summarization + fast paths — COMPLETE 2026-09-27

- Postgres 17 in compose (kestrel-db); chats/turns/llm_calls schema in storage.py;
  server-first restore with localStorage offline fallback; deletes sync both ways.
- Token metering: every ask records feature/brain/model/est-tokens/ms into
  llm_calls; GET /api/usage aggregates. Estimates = chars/4 (labeled).
- /api/summarize: real LLM rolling summaries (platform key, gpt-oss-120b).
- Smalltalk fast paths: pure greetings = instant template (0s, was 11-26s);
  chatty smalltalk = direct LLM completion (~5s), NO brain round trip.
- Known: DeepSeek V4.1 Flash recall via OpenRouter flaps 402 upstream
  (works for ingest + raw calls; recall moved to gpt-oss-120b). Revisit with
  a funded OpenRouter balance or a direct DeepSeek API key.
- Brain volume incident recovery documented in P1 entry; new state 246/587.

## P1 — THE FLIP: app answers from OUR local brain — COMPLETE 2026-09-27

- Colima resized to 4 CPU / 8 GB (the 2/4 sizing starved recall into timeouts).
- DeepSeek V4.1 Flash validated for INGESTION via OpenRouter (graph built:
  178/387 nodes/edges, $0.02 spend). Recall on DeepSeek flaps 402 at the
  upstream — recall runs on gpt-oss-120b (both models stay in the registry).
- INCIDENT (diagnosed + recovered): a debug container + hard colima restart
  wiped the brain volume (178/387 lost). Volume ownership fixed (chown 1000),
  corpus re-ingested on gpt-oss-120b. New state: 246 nodes / 587 edges.
- App flipped: `COGNEE_SERVICE_URL=localhost:8888`, flavor oss. Parity verified
  in-browser: real orchestrator worklog, correct answer (Marcus Lee / Priya
  Raghavan), 3 local citations. Battery green (25/25, 13/13, 10/10, smoke 4/4).
- M1.4 measurements: brain container 1.29 GiB RSS (fits 2 GB, comfortable at 8);
  ingest wall ~9 min (12 docs, extraction-dominated); recall ~11.7s warm local
  (beats the 18-26s cloud tenant on this machine).
- Note: app footer says "cloud · ready" — cosmetic: "cloud" = any Cognee API;
  it is actually localhost:8888.

The Phase 1 gate of the old plan is PASSED: the product answers from our own
brain on our own keys. Next per PLAN.md: P2 (Postgres persistence + Langfuse).

# PROGRESS — execution log for BUILD_PLAN.md

Append-only, newest first (BUILD_PLAN.md §4). States are exactly:
`DONE` | `BLOCKED` (points at a BLOCKERS.md entry) | `WAITING-HUMAN` | `SKIPPED`
(SKIPPED only ever carries a one-line reason + recorded human approval).

## Owner decisions 1–4 — DONE 2026-09-28

1. Legacy chats → owner org (b): 26 NULL rows stamped
   org_3JvGk0RrREUOodUd1KkANvi2vGB/creator; chats gained created_by (migration)
   for org-less owners; predicates are org-OR-creator with double-NULL
   grandfathering. Proven: owner lists 27, stranger 0.
2. Demo NOT world-readable: company_brain row flipped to creator-owned
   (shared=false); DEMO blanket-allow removed — every brain, same rule.
   Proven: owner ALLOW, stranger 403, unknown 403.
3. Deletes tightened to org/creator-match (legacy double-NULL still deletable
   until stamped — none remain).
4. Hedged retrieval (1x cost, same speed): GRAPH first, RAG starts only past
   KESTREL_HEDGE_SECONDS=8 or on fast failure; router concurrent as before.
   Proven by stub: fast graph 1 call, slow graph hedges (2 calls, vector wins).
   (One probe detour: live router classified "test q" as chat — correct
   behavior, wrong probe query; re-probed with forced route.)
Infra: colima was down (restarted; volumes intact, 26 chats kept);
test_auth_isolation now runs on isolated kestrel_test_auth DB (fail-closed
made prod-DB testing unsafe — the suite proved it by failing).

## Bug-fix session — BUGS_AUDIT.md 45 + 14 new — DONE 2026-09-28

DeepSeek v4.1 Flash audit validated TRUE 45/45 (3 subagent sweeps + execution
proofs for SEC-1/SEC-2). Own hunt added 14: NEW-1..4 (read-route
normalization gaps, stats traversal, chats brain filter, split-brain) + H1..H10
(H1 was my M0.3 regression — fixed; H2 blocks SEC-8; H9 402-retries; H10
PROVIDER-freeze vs loopback rule). All fixed, each proven by execution or
suite; full battery green (25/25 docs, 13/13 pipe-states, 10/10 tenants, 4/4
smoke, 5/5 auth isolation, UI zero console errors).

Decisions taken (owner-absent, safe defaults): legacy NULL-org rows
grandfathered visible/deletable, new writes server-stamped; demo dataset
explicit allow (fail-closed everything else, incl. DB outage); race kept
(2x-cost documented) with KESTREL_RACE_RETRIEVAL=0 lever; SEC-5 backfill still
wants a real owner call. Incidents: colima VM was down (restarted, 26 chats
intact); one pkill caught the live server (restarted immediately).

## M1.1/M1.2 — warm routes + light-mode trial LIVE on OpenRouter — UPDATE 7, 2026-09-25

Human provided an **OpenRouter key** (free tier, $250 cap, $0 used) for a
light-mode trial and asked that **all provider routes stay warm**.

**Warm-route table (new `provider_check.py`, run inside the container):**

| provider | verdict |
|---|---|
| openrouter | **LIVE** (real key, real answers) |
| openai, groq, cerebras, anthropic, deepseek, z.ai | WARM (401 at dummy key — route proven) |
| bedrock | WARM (account pending verification; key wired) |
| azure | CONFIG-WARM (litellm maps the model string; endpoint testable when the human's resource exists) |
| ollama | SKIP (dormant by design) |

Any new key = uncomment its block in `.env.oss` + restart the container.

**Active: OpenRouter `openai/gpt-oss-120b`** (the human's chosen model; free
pool congested, paid path costs cents; reasoning model ≈118 tok overhead).
Embeddings: keyless fastembed/384.

**INCIDENT (fixed):** after the OpenRouter swap, the whole contract test went
401 — one of my `.env.oss` block-editing rewrites had commented out the
auth-off vars (the commenting loop's stop marker precedes the section it
edits, so it ran to EOF) and the active embedding lines were lost with the
bedrock block. Fixed by surgical rewrite + **post-edit assertions** in the
rewrite script (exactly one active LLM block, embeddings active, auth vars
uncommented). Lesson recorded: never trust string-surgery on the env file —
assert after every edit.

**Contract test vs local OSS: 11/11 PASS** — first fully-real run (terminal
`DATASET_PROCESSING_COMPLETED -> success`, real recall text, zero skips).

**M1.2 light mode: PROVEN.** 2-doc slice (Bluepeak MSA + P1 ticket) ingested
into a scratch dataset on local OSS; flagship question ("Why is the Bluepeak
renewal at risk...") returned a genuine cross-document answer — outage
breaches 99.9% SLA at 99.89%, 10%/20% credit ladder — with evidence chunks
from BOTH documents. Scratch deleted after.

Next: full 12-doc corpus ingest (est. $0.10–0.50 of the cap, ~20–40 min),
then M1.3 (app parity) and M1.4 (measurements).



## M1.1 — ROOT CAUSE IDENTIFIED: AWS account pending verification — UPDATE 6, 2026-09-25

Human confirmed the region is **eu-north-1 (Stockholm)** — `AWS_REGION` set
accordingly in both env files. Container key hash verified byte-exact against
the pasted key (an earlier mismatch was a newline artifact in the checker).

- Probed eu-north-1: `global.xai.grok-4.6` visible (43 profiles; no gpt-oss
  profile anywhere in any region — gpt-oss is region-scoped `openai.*`),
  both grok-4.6 and gpt-oss-120b → `Operation not allowed`.
- **The verdict, stated verbatim by Bedrock itself** in ap-south-1 and
  eu-west-1: *"Your account is currently being verified."* The account is
  new / pending Bedrock use-case verification. That single fact explains
  every refusal since morning across 4 regions, 2 keys, 11 model IDs, and
  both API paths — including the earlier "Too many tokens per day".
- **Nothing remains to fix in our stack.** Keys: correct and authenticated.
  Wiring: verified byte-exact. Config: human's chosen model + fastembed,
  region eu-north-1. The only unblock is AWS finishing account verification
  (user should check email + Bedrock console → Model access → use-case
  status; new accounts require submitting the use-case form).
- When verification clears: `contract_test.py --base http://localhost:8888
  --flavor oss` → M1.2 corpus ingest. Zero rework.



## M1.1 — second Bedrock key tested; wall confirmed account-level — UPDATE 5, 2026-09-25

Human supplied a SECOND long-term Bedrock API key (same account 799823514509).
Swapped into `.env.oss` (only place it lives), container recreated, probed
gpt-oss-120b: **same `Operation not allowed`**.

Two keys × identical refusal × (11 model IDs × both API paths) = the block is
account-level, not key-level. What remains, all on the AWS console side
(us-east-1):
1. **Model access**: Bedrock → Model access — enable `openai.gpt-oss-120b`
   (third-party models need explicit enablement; a brand-new account may
   have nothing enabled, which matches every probe).
2. **Daily token quota**: the first call of the day got "Too many tokens
   per day"; even with access enabled, the day-cap must reset.
When either clears: config is already correct (gpt-oss-120b + fastembed/384);
next action = `python3 contract_test.py --base http://localhost:8888 --flavor oss`
→ M1.2 corpus ingest. No rework.



## M1.1 — Bedrock key + gpt-oss-120b wired; account refuses all invokes today — UPDATE 4, 2026-09-25

Human's model choice: **gpt-oss-120b** on the Bedrock key. Active block is now
`bedrock/openai.gpt-oss-120b-1:0` + keyless fastembed/384. Container healthy.

- Probed BOTH Bedrock API paths (`invoke/` and converse) for gpt-oss-120b:
  both `Operation not allowed`. Cumulative refusal list today (all identical
  error since the first call's daily-token message): sonnet-4, haiku-3.5
  (also EOL), nova-micro, nova-lite, llama3.1-8b, titan-embed-v2,
  grok-4.6 (us + global profiles), gpt-oss-120b (invoke + converse).
- Conclusion stands: the account's daily token wall tripped during probe 1;
  model choice is irrelevant until it lifts (or until model access is
  enabled in the console). Zero rework needed when it does: the active
  config is already the human's choice; next action = contract test → M1.2.
- gpt-oss-120b ALSO runs free on Groq (same weights, `openai/gpt-oss-120b`
  via api.groq.com/v1) — a Groq key would run the identical model today.

## M1.1 — Bedrock key wired; account daily token cap is the blocker — UPDATE 3, 2026-09-25

Human clarified the key is for **Grok** — "grok 6" is **Grok 4.6** on Bedrock.
Listed the account's inference profiles WITH the bearer key (control plane
accepted it: 87 profiles) — the Grok profiles are `us.xai.grok-4.6` and
`global.xai.grok-4.6`.

- Active block now: LLM `bedrock/us.xai.grok-4.6`, embeddings switched to
  **keyless fastembed/384** (Titan was refused on this account; nothing has
  been ingested yet, so the dimension switch is free). Container healthy.
- Both Grok profiles currently return `Operation not allowed` — same as every
  other model after the first call's `Too many tokens per day`. Two
  non-exclusive causes, both on the AWS side: (1) the daily token budget
  tripped in the first probe, (2) xAI model access may not be enabled yet
  (Bedrock console → Model access → enable Grok 4.6).
- When either clears, the setup runs as-is: contract test → M1.2. Block G in
  `.env.oss.example` records the profile IDs and the fastembed pairing.

Human supplied a **long-term Bedrock API key** (CSV in Downloads; stored ONLY
in gitignored `.env.oss` — never echoed, never tracked).

- Active block switched to Bedrock: `AWS_BEARER_TOKEN_BEDROCK` + `AWS_REGION=
  us-east-1`, LLM `bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0`,
  embeddings `bedrock/amazon.titan-embed-text-v2:0` / 1024 dims. The dormant
  ollama block is fully commented out (no var collisions). Template block G
  now documents both auth paths (API key vs SigV4 creds).
- **Auth and routing VERIFIED**: the first direct LiteLLM probe authenticated
  (Bearer accepted) and reached Bedrock's quota layer — no AccessDenied, no
  signature errors, container healthy after recreate (~24s).
- **Blocker: the account's daily token budget.** First sonnet-4 call:
  `Too many tokens per day, please wait before trying again`. Every subsequent
  call (sonnet-4, nova-micro/lite, llama3-1-8b, titan-embed-v2) then returns
  `Operation not allowed` — the error CHANGED after the first call, i.e. the
  day-cap tripped mid-probe. Not a wiring/permission issue.
- Probe matrix recorded for the record: sonnet-4 → quota → not-allowed;
  others → not-allowed; claude-3-5-haiku → end-of-life on this account.
- Nothing to fix in our stack. When the budget resets (or the account raises
  its quota / enables model access in us-east-1), the SAME setup runs as-is:
  rerun `python3 contract_test.py --base http://localhost:8888 --flavor oss`
  then M1.2. Alternative for TODAY: any other provider key (e.g. Groq free)
  is one comment-swap away in `.env.oss`.
- Note: embedding dimensions are baked at first ingest. If the trial starts
  on fastembed/384 and later moves to Titan/1024, the corpus re-ingests.

## M1.1 — swappable-key layer complete; keys still pending — UPDATE 2026-09-25

Human decisions recorded: (a) the swap layer must cover **nine providers** —
OpenAI, Azure, OpenRouter, Groq, Cerebras, Anthropic, AWS Bedrock, DeepSeek,
Z.AI; (b) actual keys come later; (c) the keyless-local experiment was
abandoned mid-pull by human decision ("not important at this step") and the
space cleaned up.

- `.env.oss.example` is now the nine-provider registry (blocks A–I plus the
  keyless-local block), each a comment-swap + restart, no code changes.
- Keyless-local attempt — findings banked before teardown:
  1. Container reaches host Ollama via `host.docker.internal:11434` (verified).
  2. Cognee's `LLMConfig` requires ALL of model/endpoint/key even for Ollama
     — a non-empty dummy (`ollama-local`) satisfies it (in the template).
  3. fastembed model id must be `sentence-transformers/all-MiniLM-L6-v2`
     (384 dims) — bare `all-MiniLM-L6-v2` is rejected by TextEmbedding.
  4. **3B-class local models fail Cognee's strict structured-output schema**
     (llama3.2:3b → `SummarizedContent` ValidationError after LiteLLM
     retries; pipeline never completed). An 8B-class model is the local
     floor; a hosted key is the practical path.
- Cleanup per human instruction: pulled models deleted, partial blobs purged
  (~6GB reclaimed), `brew services stop ollama`. The keyless block is marked
  DORMANT in both env files with exact re-enable steps.
- OSS container remains healthy on :8888 (auth off, contract-verified in
  Phase 0); the app is up for preview on :8000 against the live tenant.
- STILL WAITING-HUMAN: one hosted LLM key (Cerebras block is pre-wired as the
  recommended default) + optional Gemini embedding key. M1.2 (corpus ingest
  into local OSS) starts the moment keys land.

## M1.1 — inference keys for the OSS container — WAITING-HUMAN 2026-09-25

Prep done: `.env.oss.example` template covers LLM_PROVIDER/MODEL/API_KEY/
ENDPOINT + LLM_RATE_LIMIT_REQUESTS=5 and EMBEDDING_PROVIDER/MODEL/DIMENSIONS/
API_KEY; var names confirmed against the running 1.6.1 container code
(`LLM_API_KEY` in settings/preflight/cognify modules, `EMBEDDING_DIMENSIONS`
in preflight). Per card, STOPPING here — human supplies: (1) LLM provider
choice (Cerebras `https://api.cerebras.ai/v1` or Groq) + API key,
(2) embedding choice (Gemini `gemini-embedding-001`/768 + key, or local
fastembed/384). Keys go into gitignored `.env.oss` only, never tracked files.
M1.2+ wait on this card.

Human answers 2026-09-25: (1) ALL of OpenRouter/Groq/Azure/OpenAI/Anthropic
must stay compatible — confirmed, all five route via LiteLLM
(OSS_STACK_AND_COMPETITORS.md §1.3); template now documents one commented
block per provider (A–F), Azure native via `azure/` prefix. (2) Embeddings =
doc default: Gemini `gemini-embedding-001`/768.
STILL WAITING on actual keys: one LLM key (which provider first?) + Gemini
embedding key (or say fastembed to go keyless). Nothing proceeds to M1.2
without `.env.oss` holding working keys.

Structure wired 2026-09-25 (no keys needed, all verified):
- `ingest.py`: `--base`/`--flavor` pass-through (absent = current env/cloud
  behavior byte-for-byte); key requirement waived for loopback targets ONLY
  (local OSS auth-off), cloud still always needs a key. `--help` + import
  clean, battery green.
- `.env.oss` (gitignored): full runtime structure, Cerebras-default LLM +
  Gemini/768 embeddings, both KEY lines blank — two lines to fill on arrival.
- App→OSS plumbing proven keyless: `PROVIDER=cloud
  COGNEE_SERVICE_URL=http://localhost:8888 COGNEE_FLAVOR=oss python3 app.py`
  → `/health` reports `service: localhost:8888, upstream: ready`.
  (Answers need keys — that execution is M1.2/M1.3.)

## PHASE 0 GATE — recorded 2026-09-25

Full `./verify.sh` green (documents 25/25, pipe-states 13/13, tenants 10/10,
smoke 4/4, ui PASS); contract test green on cloud (11/11) AND oss (11/11 +
1 no-llm SKIP by design); findings F1-negative recorded (M0.5). M0.1–M0.5 DONE.
Phase 1 unblocked.

## M0.4 — flavor switch for the two renamed recall fields — DONE 2026-09-25

`cognee_cloud.py` only (recall body): new `flavor()` (`COGNEE_FLAVOR`, default
`cloud`); `recall()` sends `search_type`/`include_references` on oss,
`searchType`/`includeReferences` on cloud. `terminal_kind` untouched.
Check: `contract_test.py --flavor oss --base http://localhost:8888` → PASS
(11/11, 1 SKIP); `--flavor cloud` → PASS (11/11); `./verify.sh --quick` green.

Two empirical confirmations: OSS **rejects** cloud names with 422 (drift is
loud — the switch is required, not cosmetic); cloud **silently accepts** both
(200). OSS keyless recall 422s `LLMAPIKeyNotSetError` — classified in
`probe_recall` as no-llm SKIP (harness refinement to `contract_test.py`,
documented in its docstring; full text checks rerun WITH keys after M1.1).
Note: OSS pipeline reaches COMPLETED keyless — only generation needs the key.

## M0.5 — record what OSS does with `filename` — DONE 2026-09-25

Finding **F1-negative**: OSS v1.6.1 stores `text_<hash>`, NOT the sent
basename — measured on two OSS runs (`text_8b1ffde9…`, `text_2e5c78b6…` vs
sent `probe_filename.md`) plus three cloud runs. Same behavior both flavors,
so `citations.py` content-fingerprint matching stays the primary path in
Phase 1; no code change (zero-code verification card as expected).

## M0.3 — contract_test.py — DONE 2026-09-25

`python3 contract_test.py --flavor cloud` → **11/11 PASS** (was 10/11).
`./verify.sh --quick` → documents 25/25, pipe-states 13/13, tenants 10/10,
smoke 4/4, exit 0.

Root cause of the one FAIL (terminal wait, 300s cap): NOT latency. Raw-payload
diagnostic (scratch `contract_diag_*`, polled every 15s, deleted after) showed
the cloud status endpoint returns a **bare string map** without
`include_error_detail` — `{"<uuid>": "DATASET_PROCESSING_COMPLETED"}` — which
`_status_values()` never yielded (dict-only), so `terminal_kind()` stayed None
even on COMPLETED. Pipeline actually completes in ~35s.

Two edits to unblock:
1. `contract_test.py::_status_payload` now sends `include_error_detail=true`,
   mirroring `cc.status()` (in-card file; the test now replays what the app
   actually sends).
2. `cognee_cloud.py::_status_values` also yields bare string values
   (M0.4-adjacent hardening, human-approved via "continue"; flat
   `{"status": ...}` still yields exactly once; 13/13 pipe-states green).

Findings banked: terminal `DATASET_PROCESSING_COMPLETED -> success`; cloud
stores filename as `text_<hash>` (reconfirms fingerprint design); cloud
silently accepts BOTH recall naming styles (200). Scratch deleted; tenant
left with the five real brains.

Next: M0.4 exactly as carded (flavor switch in `recall()` only).

## M0.3 — contract_test.py — IN PROGRESS 2026-09-25 (handoff point)

`contract_test.py` written per plan §2.3 (wf_smoke.py safety pattern: unique
scratch, collision refusal, finally-deletion). Validated against the CLOUD
tenant: **10/11 checks PASS** in its first real run —

- remember/status/data-items/data-raw/graph/recall(200, no 422) all conform;
  scratch auto-deleted.
- Findings already banked: **cloud stores our filename as `text_<hash>`**
  (confirms citations.py's content-fingerprint design is still required for
  the cloud flavor), and **the cloud tenant silently accepts BOTH recall
  naming styles** (camel and snake) — the drift signal there is silent, not
  loud, so the oss-flavor 422 check is the one that matters.

**The one FAIL:** `pipeline reaches a terminal state (300s cap)` — the status
map never satisfied `terminal_kind()` within 300 s on the cloud tenant.
Recall returned 200 mid-ingest (the known confident-answer trap), so the
skip-line now reports the actual kind rather than claiming "failed pipeline".
Diagnosis so far: NOT a shape issue (data items + raw round-trip work);
likely either (a) tenant queue latency > 300 s for `run_in_background=true`
with the status map possibly staying `{}` (no status key at all) while
queued — `_status_values` yields nothing for `{}`, which would look exactly
like this — or (b) a slow pipeline. A raw-payload diagnostic was started but
cut short for the handoff.

**Next agent, in order:**
1. Rerun the diagnostic (script sketch is in the HANDOFF.md): `remember` on
   a scratch dataset, poll `/api/v1/datasets/status?dataset=<uuid>` every
   15 s, PRINT each distinct raw payload. If `{}` persists, that is the
   answer: empty map while queued. Fix = longer default `--wait-timeout`
   (600–900) plus optionally reporting elapsed-queued as an INFO line; if a
   non-standard state string appears, extend `cognee_cloud._status_values`
   mapping instead (that is an M0.4-adjacent edit — see BUILD_PLAN.md M0.4
   before touching `cognee_cloud.py`).
2. Green cloud run → mark M0.3 DONE, commit.
3. Proceed to M0.4 exactly as carded (flavor switch in `recall()` only).

Leftover scratch from the cancelled diagnostic (`contract_diag_*`) was swept
from the tenant — dataset list verified back to the five real brains.

## M0.2 — local OSS container (pinned, auth off) — DONE 2026-09-25
(human chose Colima via brew when Docker was found absent)

- Installed colima 0.10.3 + docker CLI 29.8.1 + compose 5.5.1 via brew (one
  retry needed: stale brew metadata aborted the first install; `brew update`
  fixed it). Compose plugin symlinked into ~/.docker/cli-plugins.
- `colima start --cpu 2 --memory 4` — VM up (x86 emulation available).
- **Correction to research + plan:** Docker Hub tag is `cognee/cognee:1.6.1`
  — NO `v` prefix (`v1.6.1` does not resolve; found via registry API).
  compose.oss.yml and BUILD_PLAN.md corrected. Digest:
  sha256:db0973f4b913d73daa4061bc19362cde6edc59d1be8243b6667fade364b06428.
- `compose.oss.yml` (gitignored; port 8888:8000, named volume for embedded
  state) + tracked `.env.oss.example` (both auth flags false, fixed JWT
  secret placeholder, commented LLM/embedding block for M1.1).
- Check results:
  - `curl localhost:8888/health` → `{"status":"ready","health":"healthy","version":"1.6.1-local"}` (≈30s after start; first boot runs migrations).
  - `docker compose ps` → Up.
  - **Auth-off proven:** `GET /api/v1/datasets/` unauthenticated → 307 → 200 `[]`.
    Note: OSS canonical path has NO trailing slash (FastAPI redirect); our
    client's trailing-slash URL still works because requests follows redirects.
- Observations (not fixed, per N6): none new.


## M0.1 — verification harness + workspace files — DONE 2026-09-25
(was BLOCKED; the two out-of-scope fixes were approved by the human and applied)

- Environment verified: Python 3.13.3, all requirements importable, port 8000
  free, `playwright-cli` present at check_ui.py's NODE_BIN path, `brew` present.
- `verify.sh` per plan §2.2, refined during the card: forces `PROVIDER=mock`
  for the whole battery, starts/stops its own server, refuses a pre-owned
  port 8000, runs each suite via its own standalone entrypoint (pytest is the
  wrong runner here — collects 2 of 13 and 0 of 10 checks), tenants runs
  `--with-tenants` against the battery's own server.
- **Found and fixed in scope:** stale `__pycache__` bytecode compiled in the
  original Ignite_Delhi workspace, executing since the repo was copied
  (preserved mtimes validated it). Caches cleared — this affected every suite.
- **Approved out-of-scope fixes applied (BLOCKERS.md resolved):**
  1. `test_pipeline_states.py::drive()` now sets/restores
     `memory_layer.PROVIDER` itself — the suite no longer depends on ambient
     `.env` saying `PROVIDER=cloud`; still zero network (status stubbed).
  2. `app.py::delete_brain` now evaluates `require_dataset_access` BEFORE the
     mock-mode guard — unauthorized DELETE gets 401/403 in every mode instead
     of a masking 400. No regression in cloud or authorized paths.
- Check output (`./verify.sh --quick`):

```
== Kestrel verification battery (PROVIDER=mock) ==
[documents] PASS  25/25
[pipe-states] PASS  13/13
[server] up (pid 83199, mock fixtures)
[tenants] PASS  10/10
[smoke] PASS  4/4
[ui] SKIP  (--quick)
== done: 0 failing suite(s) ==
```

- PROGRESS.md and BLOCKERS.md created; `.gitignore` gained
  `.env.oss`, `compose.oss.yml`, `cognee_oss_state/`.
- Observations (not fixed, per N6): `.gitignore` contains a duplicated
  `.playwright-cli/` block; `.zcodeignore` duplicates it as well;
  `create_brain` and `brain_events` share delete_brain's guard-before-authz
  ordering (same class, only delete_brain was approved); `pytest` is not in
  `requirements.txt` (installed globally here; the battery no longer needs it).
