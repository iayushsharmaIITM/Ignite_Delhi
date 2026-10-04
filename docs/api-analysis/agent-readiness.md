# Agent-readiness assessment — Kestrel HTTP API

Method: `postman:agent-ready-apis` (8 pillars, 48 checks, severity weights Critical 4 /
High 2 / Medium 1 / Low 0.5). No Postman MCP tools exist in this session, so the
assessment is computed against the **served** OpenAPI 3.1 document (`GET
/openapi.json`) rather than against Postman's cloud analyzer — the scoring rubric is
theirs, the measurements are ours.

The evaluator is now committed at **`ops/api_readiness.py`** and every verdict in this
file is reproducible with `python3 ops/api_readiness.py --base http://127.0.0.1:8000`.
That is the point of it being committed. The first version lived in `/tmp` and carried
several **hardcoded** pass/fail verdicts (`E4`, `E6`, `P3`, `P4`, `I7`, `PF3`), and when
the contract improved the score moved by amounts nobody could attribute — a number that
cannot be re-derived is not a measurement. Every check is now a function of the
document; a check that genuinely cannot be assessed from the document reports `n/a` and
leaves the denominator, which is honest, instead of being pinned to a verdict, which is
not.

## Score

| Contract state | weighted | percent | criticals | verdict |
|---|---|---|---|---|
| Security scheme + `servers` + info description, no error contract | 36.5 / 64.5 | **56.6%** | E1 | Needs Work |
| **+ error contract** (this pass) | 38.5 / 64.5 | **59.7%** | E1 | Needs Work |

Both rows come from the **same** scorer on the same 45 scored checks (3 `n/a`), the
second by `--ablate-error-contract` to remove exactly what this pass added. That is the
comparison that means something; the earlier pair of numbers in this file (50.0% →
57.6%) came from the pre-commit evaluator with its hardcoded verdicts and is **not
comparable** — it is kept below only because the fixes it describes were real.

Formally not agent-ready either way: the bar is ≥70% *and* zero Critical failures, and
**E1 still fails**. The +3.1 points are small because E1 is binary — going from "5 of 39
operations document a 5xx body" to "39 of 39" moves one check from fail to fail.

Per pillar after this pass: Metadata 2/6 · Errors 4/7 · Introspection 3/7 · Naming 4/6 ·
Predictability 1/6(+2 n/a) · Documentation 3/6 · Performance 2/5 · Discoverability 3/5.

### What this pass actually changed

1. **`responses=` on the five routes whose guarantees this project spent two rounds
   hardening** — `POST /api/chats` (400/401/403/404/409/410/413/422/503), `GET
   /api/chats`, `GET`/`DELETE /api/chats/{chat_id}`, and `POST /api/brains`. Each code
   is listed because the handler raises it, checked by reading every `status_code=` in
   the body and the helpers it calls, not by assumption — which is why `403` is on the
   chat routes and **not** on `POST /api/brains`, where nothing raises it. Codes whose
   meaning differs between two routes carry a per-route `notes=` description: a shared
   409 that talks about chat trimming would be a lie on brain creation.
2. **One shared `ApiError` schema** (`{detail}`, required), referenced by every error
   response above, so a client can parse a failure without guessing at the shape.
3. **`500` declared on all 39 operations, and `401` on all 31 `/api/*` operations that
   gate** — done in `_custom_openapi`'s post-processing rather than as 34 more
   decorator edits, because these two are properties of the app (a crash handler, an
   auth funnel) rather than of one route. The 401 exclusion list is exactly
   `{/api/config, /api/connectors/oauth/{provider}/callback}`: the first is how a client
   learns which auth mode is live, the second is a third party's browser arriving
   without our bearer token. Every other `/api` handler reaches `require_tenant()`,
   verified by reading each handler's body.
4. **A real `500` to document.** `@app.exception_handler(Exception)` now answers an
   unexpected crash as `{"detail": …}` instead of Starlette's plain-text `Internal
   Server Error`, because `frontend/src/lib/api.ts:111` reads failures with
   `res.json().catch(() => null)` — a crash used to produce no server message at all.
   `HTTPException` still goes through FastAPI's handler first, so the deliberate
   409/410/413/503 bodies are untouched. Verified through the ASGI app: `500`,
   `application/json`, and the traceback in the log rather than the response.

### Deliberately not done

- **`operationId` rewriting.** An intermediate pass here replaced FastAPI's generated
  ids with bare handler names. It measured **zero** gain (M1 already passed: FastAPI
  emits a unique id for all 39) and it *lost* information — `chats_list_api_chats_get`
  encodes the method and path, `chats_list` does not. Reverted.
- **`response_model` / success schemas (P1, Critical, 0 of 39).** A response model
  **filters fields**, and these routes return hand-built dicts the React client reads
  key by key. The safe route is documenting `200` schemas without `response_model`,
  which is 39 pieces of hand-written schema with no test behind them — a large enough
  job to be its own round, not something to slip into this one.
- **`tags=` (M4, 0 of 39)** — same objection as before, smaller stakes.

## Fixed in the previous pass (auth, servers, description)

Carried over here because the ablated row above is scored *with* these and *without*
the error contract — they are what took the document from "no auth declared while the
server requires it" to a contract an agent can read:

1. **`ClerkBearer`** (HTTP bearer, JWT) with a description that states the honest
   conditionality: required while the server runs clerk mode, not required while it runs
   `AUTH_MODE=off`, and `GET /api/config` says which mode is live. Declaring it does
   **not** change enforcement — that stays in `require_tenant()`/`auth.active()`.
2. **`servers`**, derived from `PUBLIC_BASE_URL`, which `.env` already carries.
3. **An info description** pointing an agent at `GET /api/config` and `GET /health` as
   the self-describing endpoints, and stating the ownership rule ("knowing an id is not
   ownership") that most of the 4xx codes exist to enforce.

## Still open, in weighted order

**E1 (Critical)** remains the blocker, now for a narrower reason: 31 of 39 operations
document a 4xx body and 39 of 39 document a 5xx one. The 8 with no 4xx are routes that
take no input at all (`GET /health`, `/api/stats`, `/api/connectors/status`…), where a
4xx arguably does not exist — the rubric's bar is "every operation documents its
errors", and on that reading the honest fix is to say so in the description rather than
invent a code.


*(The old item 4 — "E1: 21 of 39 operations declare no error schema" — is what this
pass fixed, so it is gone from this list. Its replacement estimate said "+8 to +10
points and it clears the only critical"; the measured answer was **+3.1 and it cleared
nothing**, because the check is one binary and the remaining gap is the success-schema
half, not the error half. Recording the wrong estimate next to the wrong number is the
useful part.)*

1. **P1 (Critical): 0 of 39 success responses carry a schema.** This is now the real
   blocker and it is the same `response_model`-filters-fields problem described above,
   which is why it wants its own round with its own tests.
2. **E3 (High): no machine-readable error `code` field.** Every error is
   `{"detail": "<sentence>"}`. Sentences are for humans; an agent self-healing a 409
   needs to distinguish "send trim=true" from "another tab got there first". The React
   client and `tests/test_chat_integrity.py` already branch on HTTP status, so a stable
   code string is a compatible addition. (**E4, the human-readable message property,
   now passes** — `ApiError.detail` is required and declared.)
3. **I3 (High): zero enums.** `role` (`user`/`bot`), brain names, and the turn shape are
   all unconstrained in the spec.
4. **PF1 (High): no `X-RateLimit-*` headers declared** — even though the app *has* rate
   limits (`RATE_UPLOAD_PER_MIN`, the ask cap) and returns 429. An agent will fire until
   blocked. Emitting the headers alongside the existing 429 is a small, honest fix in
   `app.py:_check_rate`.
5. **PF3 (Medium): the server sends `Cache-Control`/`ETag` and the contract says
   nothing** — `NoCacheStaticFiles` is real behaviour that a caching agent could use.
5b. **10 of 12 POST operations declare no `requestBody` at all** (`POST /api/chats`,
   `/api/summarize`, `/api/extract`, `/api/actions/draft`, `/api/actions/send`,
   `/api/connectors/slack/{team_id}/post`, `…/disconnect`, `/api/connectors/disconnect`,
   `/api/connectors/import`, `/api/jobs/{job_id}/cancel`). Only `/api/brains` and
   `/api/brains/v2` have one, because those are the two that use `Form`/`UploadFile`; the
   rest call `await request.json()` by hand, so FastAPI has nothing to generate from. This
   is the request-side twin of P1 and it was **found by generating the Postman collection**
   — the generator produced 39 requests and only 2 with a body, which is a measurement
   rather than an opinion. It is also why `POST /api/chats` answers 400 with
   "Request body must be a JSON object": the shape is validated in code, not declared.
6. **M4 (Medium): 0 of 39 operations are tagged.**
7. **DC4/DC5 (Low): no contact or license.** Not invented here — a license field is a
   legal statement and contact details belong to the owner.

## Reading order

- Full endpoint logic for the chat persistence path: `post-api-chats.md` (this
  directory).
- **`ops/api_readiness.py`** — the scorer that produced every number above.
- **`kestrel.postman_collection.json`** (this directory) — 39 requests generated from the
  served document, bearer auth on a `{{bearer_token}}` variable, and a test script on every
  request asserting the status codes the contract documents plus the `{detail}` shape on
  4xx. Import it into Postman; run it against a lab tier, not live.
- Contract truthfulness gates that already exist: `ops/check_secrets.sh`,
  `ops/doc_health.sh`, and CI's `frontend/dist` sync check.
- What the API *guarantees*: `BUGS_AUDIT.md` Round 2 (CH-1…CH-14) and Round 3.
