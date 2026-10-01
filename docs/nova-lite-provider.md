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

## Current probe result
`Operation not allowed` for every Nova model (micro/lite/pro) in every region
where the model exists; invalid ids give a different error — so auth and
routing work and the **account denies Bedrock model invocation**. Fix on the
AWS side: Bedrock console → Model access → enable Amazon Nova Lite (and the
region), or grant the key's policy `bedrock:InvokeModel*`.

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
