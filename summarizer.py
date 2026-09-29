"""Summarizer (P2): compress older conversation turns into a stable summary.

Uses the platform LLM (llm.py: Token Harbor primary, OpenRouter fallback)
when a key is set; otherwise returns "" and the caller falls back to raw
truncation. Summaries feed the ask-context so multi-turn chats stay bounded
and cache-friendly.
"""

from __future__ import annotations

import asyncio
import time
import os

import requests

import llm


def _key() -> str:
    return llm.api_key()


def _model() -> str:
    return os.getenv("SUMMARIZER_MODEL", llm.default_model())


async def summarize_history(text: str) -> str:
    """Summarize older-turn text (~12K chars max) into a compact brief."""
    import observe  # P5 (fail-open)

    t0 = time.time()
    key = _key()
    if not key or not text.strip():
        return ""
    try:
        # COR-11: this is async-called from request handlers — a blocking
        # 90s POST would freeze every concurrent request (/health included).
        resp = await asyncio.to_thread(
            requests.post,
            llm.chat_url(),
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
        out = (resp.json()["choices"][0]["message"].get("content") or "").strip()
        observe.trace(
            feature="summarize", model=_model(),
            est_prompt=len(text[-12000:]) // 4, est_completion=len(out) // 4,
            ms=int((time.time() - t0) * 1000), ok=True,
        )
        return out
    except Exception as exc:  # noqa: BLE001 - summarization is an enhancement, never fatal
        observe.trace(
            feature="summarize", model=_model(),
            est_prompt=len(text[-12000:]) // 4,
            ms=int((time.time() - t0) * 1000), ok=False, error=str(exc)[:200],
        )
        return 
