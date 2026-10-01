# Amazon Nova Lite — guarded provider switch

Status: **nova_lite_probe_failed_using_previous_default** (as of 2026-10-01)

## What was changed
- `ops/probe_provider.py` — real-generation probe; sole writer of
  `var/provider_state.json`.
- `llm.py` — Nova pair + `nova_probe_status()`; the route is used ONLY when
  `KESTREL_LLM_ROUTE=nova` AND the probe state is `nova_lite_probe_passed`.
- `app.py /health` — exposes `llm.route`, `llm.active_base`,
  `llm.active_model`, `llm.nova_status`.

## How the probe works
Bedrock OpenAI-compatible endpoint:
`https://bedrock-runtime.<region>.amazonaws.com/openai/v1/chat/completions`
with `Authorization: Bearer <BEDROCK_API_KEY>`. Deterministic prompt:
`Reply with exactly: NOVA_LITE_OK`. Pass requires: HTTP 200 + non-empty
completion containing `NOVA_LITE_OK` + response `model` containing
`nova-lite`. Anything else (auth, region, model-access denial, timeout,
wrong model) = fail.

## Where active provider state lives
`llm._pair()` — reads `KESTREL_LLM_ROUTE`; `nova` requires the probe-passed
state file. `/health.llm` shows what is REALLY active.

## Current probe result — diagnosis (2026-10-01, full ladder)

Classification: **api_key_scope_or_policy_denied** — UPGRADED 2026-10-01 (final):
**unknown_bedrock_access_failure**. The denial survives every eliminable layer:
- Bearer auth (Bedrock API keys for TWO users, both with InvokeModel allows)
- SigV4 auth (real AKIA IAM key) on BOTH the OpenAI-compat route and native
  InvokeModel
- 4 regions × base id + regional profiles; minimal and full bodies
- IAM: AmazonBedrockLimitedAccess (InvokeModel on *) + kestrel-nova-invoke —
  two Allows, zero Denys in identity policies; no permission boundary
- Account: model access enabled-by-default, billing active, $111 credits
DECISIVE (2026-10-01): the **AWS console playground itself fails with
"Operation not allowed"** for Nova Lite — identical to the API result. The
block is account/service-level at AWS, above all credentials and policies.
Founder checks: (1) AWS Organizations → is 799823514509 in an org → SCPs /
AI-service opt-out policies attached? (2) AWS Support ticket (paid plan) with
the reproduction: Nova Lite denied via console playground, OpenAI-compat
endpoint (bearer + SigV4), and native InvokeModel, across 4 regions, with
InvokeModel allowed by two IAM policies and credits/billing active.
Until AWS clears it: Nova Lite stays nova_lite_probe_failed_using_previous_default;
Kestrel generation is down on all routes (Harbor free window resets
2026-10-06 07:29 UTC).

Evidence:
- Auth PASS: invalid model ids return "The provided model identifier is
  invalid" (a different, model-aware error class) while valid ids return
  "Operation not allowed" — the request reaches model evaluation.
- Model id VALID: us-east-1 metadata lists `amazon.nova-lite-v1:0` as ACTIVE
  with ON_DEMAND + INFERENCE_PROFILE support; the same is listed in
  ap-southeast-1.
- Model access NOT the cause: the account reports
  `enableAccessToAllModelsByDefault: true`.
- Region NOT the cause: identical denial in us-east-1, us-west-2, eu-west-1
  (eu profile), ap-southeast-1 (apac profile + base id).
- Request body NOT the cause: minimal body, max_tokens/max_completion_tokens
  and temperature variants all denied identically.
- Operation-level split observed: control-plane `bedrock:ListFoundationModels`
  SUCCEEDS with the same key; runtime `bedrock:InvokeModel` (the OpenAI-compat
  chat route) is denied → the key's IAM principal allows listing but not
  invocation.

Fix (AWS console/CLI, founder action): attach to the API key's IAM principal:
`bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` on
`arn:aws:bedrock:*::foundation-model/amazon.nova-lite-*` (or `*`). Then rerun
`PYTHONPATH=. python3 ops/probe_provider.py` — on PASS, set
`KESTREL_LLM_ROUTE=nova` and restart the app.

## Fallback behavior
Failed/unverified probe → previous default stays active
(`nova_lite_probe_failed_using_previous_default` in /health). NOTE: the
previous default (Token Harbor `deepseek-v4.1-flash:free`) is itself
exhausted until 2026-10-06 07:29 UTC — generation is down on both routes
until the founder funds one or the window resets.

## Rollback
1. Remove `KESTREL_LLM_ROUTE=nova` (or set `auto`).
2. Restore the previous `.env.oss` active block (kept as comments in-file).
No data changes; single-env reversal.
