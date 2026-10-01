"""Shared LLM endpoint resolution: Token Harbor primary, OpenRouter fallback.

Every app-tier LLM call (router, direct chat, summarizer, OCR, agents) is an
OpenAI-compatible POST, so provider selection is one (base_url, api_key,
default_model) triple resolved here — not five copies of env sniffing.
Resolution is by PAIR (base+key always match); per-site MODEL env overrides
(ROUTER_MODEL, SUMMARIZER_MODEL, AGENT_MODEL, KESTREL_OCR_MODELS) are still
honored verbatim when explicitly set.
"""

from __future__ import annotations

import os

HARBOR_BASE = "https://tokenharbor.ai/v1"
HARBOR_MODEL = "deepseek-v4.1-flash:free"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "deepseek/deepseek-v4.1-flash"

# Amazon Nova Lite on AWS Bedrock's OpenAI-compatible endpoint. ACTIVATION IS
# GUARDED: the route is used only when ops/probe_provider.py has written
# nova_lite_probe_passed into var/provider_state.json. No probe pass -> the
# previous default stays active and the status says so (fail closed).
NOVA_BASE_FMT = "https://bedrock-runtime.{region}.amazonaws.com/openai/v1"


def _nova_pair() -> tuple[str, str, str] | None:
    key = os.getenv("BEDROCK_API_KEY", "").strip()
    region = os.getenv("BEDROCK_REGION", "us-east-1").strip()
    model = os.getenv("NOVA_LITE_MODEL", "us.amazon.nova-lite-v1:0").strip()
    if not key:
        return None
    return (NOVA_BASE_FMT.format(region=region), key, model)


def _probe_state() -> dict:
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "var", "provider_state.json")
    try:
        import json
        return json.load(open(path))
    except Exception:  # noqa: BLE001 - no probe file yet: never verified
        return {}


def nova_probe_status() -> str:
    """Inspectable provider-probe status (exact wording per the switch plan):
    nova_lite_configured_not_verified | nova_lite_probe_passed |
    nova_lite_probe_failed_using_previous_default"""
    if not os.getenv("BEDROCK_API_KEY", "").strip():
        return "nova_lite_configured_not_verified"
    return _probe_state().get("nova_lite", "nova_lite_configured_not_verified")


def _pair() -> tuple[str | None, str, str]:
    """Route policy (Phase 4, decision D5/F5): the free Token Harbor
    collection is approved for LOCAL/synthetic use only. In beta/production
    environments (`APP_ENV` != local) the free route is refused outright —
    no silent fallback; the paid OpenRouter DeepSeek route is the only
    generation path."""
    env = os.getenv("APP_ENV", "local").strip().lower()
    th = os.getenv("TOKENHARBOR_API_KEY", "").strip()
    o = os.getenv("OPENROUTER_API_KEY", "").strip()
    if os.getenv("KESTREL_LLM_ROUTE", "").strip().lower() == "nova":
        # guarded: only with a PASSED probe; otherwise fail closed to the
        # previous default and record why (nova_lite_probe_failed_using_previous_default)
        nova = _nova_pair()
        if nova and _probe_state().get("nova_lite") == "nova_lite_probe_passed":
            return nova
        log_reason = "nova_lite_probe_failed_using_previous_default"
    if env in ("beta", "prod", "production"):
        if o:
            return (OPENROUTER_BASE, o, OPENROUTER_MODEL)
        return (None, "", OPENROUTER_MODEL)
    if th:
        return (HARBOR_BASE, th, HARBOR_MODEL)
    if o:
        return (OPENROUTER_BASE, o, OPENROUTER_MODEL)
    return (None, "", OPENROUTER_MODEL)


def base_url() -> str | None:
    return _pair()[0]


def api_key() -> str:
    return _pair()[1]


def default_model() -> str:
    return _pair()[2]


def chat_url() -> str | None:
    base = base_url()
    return base.rstrip("/") + "/chat/completions" if base else None


def headers() -> dict:
    return {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}
