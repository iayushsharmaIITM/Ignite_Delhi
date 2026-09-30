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


def _pair() -> tuple[str | None, str, str]:
    """Route policy (Phase 4, decision D5/F5): the free Token Harbor
    collection is approved for LOCAL/synthetic use only. In beta/production
    environments (`APP_ENV` != local) the free route is refused outright —
    no silent fallback; the paid OpenRouter DeepSeek route is the only
    generation path."""
    env = os.getenv("APP_ENV", "local").strip().lower()
    th = os.getenv("TOKENHARBOR_API_KEY", "").strip()
    o = os.getenv("OPENROUTER_API_KEY", "").strip()
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
