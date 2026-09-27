"""Summarizer (P2): compress older conversation turns into a stable summary.

Uses the platform LLM via OpenRouter (the same key that powers the local
brain) when OPENROUTER_API_KEY is set; otherwise returns "" and the caller
falls back to raw truncation. Summaries feed the ask-context so multi-turn
chats stay bounded and cache-friendly.
"""

from __future__ import annotations

import os

import requests

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


def _key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "").strip()


def _model() -> str:
    return os.getenv("SUMMARIZER_MODEL", "openai/gpt-oss-120b")


async def summarize_history(text: str) -> str:
    """Summarize older-turn text (~12K chars max) into a compact brief."""
    key = _key()
    if not key or not text.strip():
        return ""
    try:
        resp = requests.post(
            f"{OPENROUTER_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": _model(),
                "messages": [
                    {"role": "system",
                     "content": "Summarize this company-brain conversation fragment "
                                "into a compact brief of the facts, owners and dates. "
                                "Keep names exactly. Max 150 words."},
                    {"role": "user", "content": text[-12000:]},
                ],
                "max_tokens": 400,
            },
            timeout=90,
        )
        resp.raise_for_status()
        return (resp.json()["choices"][0]["message"].get("content") or "").strip()
    except Exception:  # noqa: BLE001 - summarization is an enhancement, never fatal
        return ""
