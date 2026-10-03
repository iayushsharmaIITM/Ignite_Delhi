# Agent-readiness assessment — Kestrel HTTP API

Method: `postman:agent-ready-apis` (8 pillars, 48 checks, severity weights
Critical 4 / High 2 / Medium 1 / Low 0.5). No Postman MCP tools exist in this
session, so the assessment was computed locally against the **served** OpenAPI 3.1
document (`GET /openapi.json`) rather than against Postman's cloud analyzer — the
scoring rubric is theirs, the measurements are ours.

The check-by-check evaluator used to produce these numbers is a throwaway script at
`/tmp/api_ready.py`; it is not committed. Promoting it into the battery is an
explicit decision, because an API-contract gate would then fail on every added
untyped route.

## Score

| | weighted | percent | verdict |
|---|---|---|---|
| Before (contract as served before this pass) | 33.0 / 66.0 | **50.0%** | Needs Work |
| After (security scheme + servers + description) | 38.0 / 66.0 | **57.6%** | Needs Work |

Formally **not agent-ready** in both cases: the threshold is ≥70% *and* zero
critical failures, and one Critical check (E1, error/response schemas) still fails.
The +7.6 points came from three checks, not from a rescore: `D1` authentication
documented, `DC2` server URLs, `DC3` complete info block.

Per pillar after the change: Metadata 2/6 · Errors 2/7 · Introspection 3/7 ·
Naming 5/6 · Predictability 2/6 · Documentation 4/6 · Performance 2/5 ·
Discoverability 3/5.

## What was wrong, and what is fixed

**Fixed in this pass** (`app.py`, OpenAPI metadata only — no route behavior changed;
verified by running the demo path against the modified server):

1. **The contract advertised no authentication while the server required it.**
   `AUTH_MODE=clerk` rejects every unauthenticated request with 401, and
   `/openapi.json` declared `securitySchemes: {}`. An agent could only learn this
   by failing. Now declares `ClerkBearer` (HTTP bearer, JWT) with a description that
   states the honest conditionality: required while the server runs clerk mode, not
   required while it runs `AUTH_MODE=off`, and `GET /api/config` says which mode is
   live. Declaring it does **not** change enforcement — that stays in
   `require_tenant()`/`auth.active()`.
2. **No `servers` entry**, so a consumer had to guess the base URL. Now derived from
   `PUBLIC_BASE_URL`, which `.env` already carries.
3. **No description.** The info block now points an agent at `GET /api/config` and
   `GET /health` as the self-describing endpoints, and states the ownership rule
   ("knowing an id is not ownership") that most of the 4xx codes exist to enforce.

**Not fixed — and deliberately so:**

4. **E1 (Critical): 21 of 39 operations declare no error schema, and no operation
   declares a typed success schema.** This is the single blocking item. The
   temptation is `response_model=...` on each route — do not do that casually.
   FastAPI's response models *filter* fields, so adding one to a route that returns
   a hand-built dict can silently drop keys the React client reads. The correct
   repair is `responses={409: {...}, 410: {...}, 503: {...}}` documentation on the
   routes whose contract this project just spent a round hardening (`POST /api/chats`
   at `app.py:627` returns 400/409/410/413/422/503 that the spec does not mention),
   plus one shared error schema. Estimated +8 to +10 points and it clears the only
   critical.
5. **E3/E4**: no machine-readable error `code` field. Every error today is
   `{"detail": "<sentence>"}`. Sentences are for humans; an agent self-healing a
   409 needs to distinguish "send trim=true" from "another tab got there first".
   `tests/test_chat_integrity.py` and the React client already branch on HTTP status,
   so a stable code string is a compatible addition.
6. **I3 (High): zero enums.** `role` (`user`/`bot`), brain names, and the turn shape
   are all unconstrained in the spec.
7. **PF1 (High): no `X-RateLimit-*` headers declared** — even though the app *has*
   rate limits (`RATE_UPLOAD_PER_MIN`, ask cap) and returns 429. An agent will fire
   until blocked. Emitting the headers alongside the existing 429 is a small, honest
   fix in `app.py:_check_rate`.
8. **M4/M5: 0 of 39 operations are tagged.** Adding `tags=` means touching every
   decorator; better done once alongside #4 than piecemeal.
9. **DC4/DC5**: no contact or license. Not invented here — a license field is a legal
   statement, and contact details belong to the owner.

## Reading order

- Full endpoint logic for the chat persistence path: `post-api-chats.md` (this
  directory).
- Contract truthfulness gate that already exists: `ops/check_secrets.sh`,
  `ops/doc_health.sh`, and CI's `frontend/dist` sync check.
- What the API *guarantees*: `BUGS_AUDIT.md` Round 2 (CH-1…CH-14) and Round 3.
