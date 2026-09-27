"""Server-side persistence: chats, turns, and LLM-call metering (P2).

WHY THIS EXISTS
Chats/attachments lived only in browser localStorage — they did not survive
cache clears, follow across devices, or support accounts. This module adds a
Postgres source of truth with a graceful degradation contract: if the database
is unreachable the API keeps working (persistence marked unavailable) and the
UI falls back to localStorage. Never raise out of this module.

SCHEMA (created idempotently on init)
    chats(id text pk, brain text, title text, created timestamptz,
          updated timestamptz, summary text)
    turns(chat_id text, idx int, role text, text text, sources jsonb,
          attachments jsonb, at timestamptz, pk(chat_id, idx))
    llm_calls(ts timestamptz, brain text, feature text, model text,
          est_prompt_tokens int, est_completion_tokens int, ms int)

Conventions
  * token estimates: len(text) // 4 (characters/4) — labeled ESTIMATE; exact
    provider usage lives with the provider (OpenRouter dashboard) until a
    usage-exposing path exists.
  * turns are stored with their TURNS-array index so client ordering is
    preserved (bot/user interleaving is client state).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://kestrel:kestrel@localhost:5433/kestrel"
)

_status = {"storage": "unavailable", "detail": "not initialised"}


def status() -> dict:
    return dict(_status)


def _conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True)


def init() -> bool:
    """Create the schema. Returns True when storage is available."""
    global _status
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS chats (
                     id text PRIMARY KEY,
                     brain text NOT NULL,
                     title text NOT NULL DEFAULT 'Untitled',
                     summary text,
                     created timestamptz NOT NULL DEFAULT now(),
                     updated timestamptz NOT NULL DEFAULT now()
                   )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS turns (
                     chat_id text NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                     idx int NOT NULL,
                     role text NOT NULL,
                     text text NOT NULL,
                     sources jsonb NOT NULL DEFAULT '[]',
                     attachments jsonb NOT NULL DEFAULT '[]',
                     at timestamptz,
                     PRIMARY KEY (chat_id, idx)
                   )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS llm_calls (
                     ts timestamptz NOT NULL DEFAULT now(),
                     brain text,
                     feature text NOT NULL,
                     model text,
                     est_prompt_tokens int,
                     est_completion_tokens int,
                     ms int
                   )"""
            )
            cur.execute("CREATE INDEX IF NOT EXISTS chats_brain_idx ON chats(brain, updated DESC)")
        _status = {"storage": "postgres", "detail": DATABASE_URL.split("@")[-1]}
        return True
    except Exception as exc:  # noqa: BLE001 - persistence degrades, never raises
        _status = {"storage": "unavailable", "detail": str(exc)[:160]}
        return False


def available() -> bool:
    return _status.get("storage") == "postgres"


def _est_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def upsert_chat(record: dict) -> dict:
    """Insert or update one chat with its full turns array."""
    chat_id = record["id"]
    brain = record.get("brain") or "demo"
    title = (record.get("title") or "Untitled")[:200]
    created = record.get("created")
    turns = record.get("turns") or []
    now = datetime.now(timezone.utc)
    # Authoritative smalltalk strip: greetings can never cite documents. Older
    # turns saved before the smalltalk fix carry stale fake citations — the
    # Python classifier (memory_layer) is the single source of truth here.
    try:
        from memory_layer import _is_smalltalk, _is_social_reply
        for t in turns:
            txt = t.get("text") or ""
            if t.get("role") == "bot" and (_is_smalltalk(txt) or _is_social_reply(txt)):
                t["sources"] = []
    except Exception:  # noqa: BLE001 - classifier unavailable: store as-is
        pass
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO chats (id, brain, title, created, updated)
               VALUES (%s, %s, %s,
                       COALESCE(%s, now()), now())
               ON CONFLICT (id) DO UPDATE
                 SET title = EXCLUDED.title, updated = now()""",
            (chat_id, brain, title, _ts(created)),
        )
        cur.execute("DELETE FROM turns WHERE chat_id = %s", (chat_id,))
        for idx, t in enumerate(turns):
            cur.execute(
                """INSERT INTO turns (chat_id, idx, role, text, sources,
                                       attachments, at)
                   VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, now()))""",
                (
                    chat_id,
                    idx,
                    t.get("role"),
                    t.get("text") or "",
                    json.dumps(t.get("sources") or []),
                    json.dumps(t.get("attachments") or []),
                    _ts(t.get("at")),
                ),
            )
    return {"ok": True, "id": chat_id, "turns": len(turns)}


def list_chats(brain: str | None) -> list:
    where = "WHERE brain = %s" if brain else ""
    args = (brain,) if brain else ()
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""SELECT id, brain, title, created, updated FROM chats {where}
                ORDER BY updated DESC LIMIT 50""",
            args,
        )
        return cur.fetchall()


def get_chat(chat_id: str) -> dict | None:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, brain, title, created, updated FROM chats WHERE id = %s",
            (chat_id,),
        )
        chat = cur.fetchone()
        if not chat:
            return None
        cur.execute(
            """SELECT role, text, sources, attachments, at FROM turns
               WHERE chat_id = %s ORDER BY idx""",
            (chat_id,),
        )
        chat["turns"] = cur.fetchall()
        return chat


def delete_chat(chat_id: str) -> bool:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM chats WHERE id = %s", (chat_id,))
        return cur.rowcount > 0


def save_llm_call(brain: str, feature: str, model: str,
                  est_prompt_tokens: int, est_completion_tokens: int,
                  ms: int) -> None:
    if not available():
        return
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO llm_calls (brain, feature, model,
                       est_prompt_tokens, est_completion_tokens, ms)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (brain, feature, model, est_prompt_tokens,
                 est_completion_tokens, ms),
            )
    except Exception:  # noqa: BLE001 - metering degrades silently
        pass


def usage_summary(days: int = 30) -> list:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT feature, brain, model, COUNT(*) AS calls,
                      SUM(est_prompt_tokens) AS prompt_tokens,
                      SUM(est_completion_tokens) AS completion_tokens,
                      SUM(ms) AS total_ms
               FROM llm_calls
               WHERE ts > now() - (%s || ' days')::interval
               GROUP BY feature, brain, model
               ORDER BY calls DESC""",
            (str(days),),
        )
        return cur.fetchall()


def _ts(value):
    if not value:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, timezone.utc)
    except (TypeError, ValueError):
        return None
