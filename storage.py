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
                """CREATE TABLE IF NOT EXISTS brain_access (
                     brain text PRIMARY KEY,
                     org_id text,
                     created_by text,
                     is_shared boolean NOT NULL DEFAULT false,
                     created timestamptz NOT NULL DEFAULT now()
                   )""")
            cur.execute("ALTER TABLE chats ADD COLUMN IF NOT EXISTS org_id text")
            cur.execute("CREATE INDEX IF NOT EXISTS chats_org_idx ON chats(org_id)")
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


def _norm_brain(raw) -> str:
    """Local brain-name normalizer (mirrors app.safe_dataset without the
    import — app imports storage, so storage cannot import app)."""
    import re as _re
    name = (raw or "").strip().lower()
    name = _re.sub(r"[\s\-.]+", "_", name)
    name = _re.sub(r"[^a-z0-9_]", "", name)
    name = _re.sub(r"_{2,}", "_", name).strip("_")
    return name if _re.fullmatch(r"[a-z0-9][a-z0-9_]{2,39}", name) else ""


def _est_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def upsert_chat(record: dict, org: str | None = None,
                brain: str | None = None) -> dict:
    """Insert or update one chat with its full turns array.

    SEC-5: `org`/`brain` are server-stamped by the caller (identity + route).
    A client-supplied org_id in the record is IGNORED — the server wins, so a
    client can neither omit ownership nor self-declare into another org.
    `brain` is normalized server-side (NEW-4); legacy rows keep whatever case
    they were stored with until rewritten.
    """
    chat_id = record["id"]
    raw_brain = brain if brain is not None else record.get("brain")
    brain = _norm_brain(raw_brain) or "demo"
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
    # SEC-10: the rewrite (DELETE + re-INSERTs) runs in ONE transaction on a
    # non-autocommit connection — a crash mid-rewrite rolls back to the old
    # turns instead of committing an empty chat. (Module convention is
    # never-raise; here a failure must propagate as rollback, so this block
    # manages its own connection rather than using the autocommit helper.)
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO chats (id, brain, org_id, title, created, updated)
                   VALUES (%s, %s, %s, %s,
                           COALESCE(%s, now()), now())
                   ON CONFLICT (id) DO UPDATE
                     SET title = EXCLUDED.title, updated = now(),
                         brain = EXCLUDED.brain,
                         org_id = COALESCE(EXCLUDED.org_id, chats.org_id)""",
                (chat_id, brain, org, title, _ts(created)),
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
    finally:
        conn.close()
    return {"ok": True, "id": chat_id, "turns": len(turns)}


def list_chats(brain: str | None, org: str | None = None) -> list:
    clauses, args = [], []
    if brain:
        clauses.append("brain = %s"); args.append(brain)
    if org is not None:                      # auth on: only this org's chats
        clauses.append("(org_id = %s OR org_id IS NULL)")
        args.append(org)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""SELECT id, brain, title, created, updated FROM chats {where}
                ORDER BY updated DESC LIMIT 50""", args)
        return cur.fetchall()


def _org_clause(org: str | None) -> tuple:
    """Ownership predicate with legacy grandfathering.

    Rows stamped with an org are visible only to that org. Pre-P3 rows have
    org_id NULL and stay visible to everyone (the demo history depends on
    it) — but only until the backfill assigns them; see SEC-5. With org=None
    (auth off) there is no predicate at all: unchanged single-user behavior.
    """
    if org is None:
        return "", []
    return "(org_id = %s OR org_id IS NULL)", [org]


def get_chat(chat_id: str, org: str | None = None) -> dict | None:
    with _conn() as conn, conn.cursor() as cur:
        pred, args = _org_clause(org)
        cur.execute(
            "SELECT id, brain, title, created, updated FROM chats WHERE id = %s"
            + (" AND " + pred if pred else ""),
            (chat_id, *args),
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


def delete_chat(chat_id: str, org: str | None = None) -> bool:
    """Delete a chat. Stamped rows require an org match; legacy NULL rows are
    deletable by any authenticated caller (they are effectively public until
    the SEC-5 backfill — and undeletable-by-anyone would be worse)."""
    with _conn() as conn, conn.cursor() as cur:
        if org is None:
            cur.execute("DELETE FROM chats WHERE id = %s", (chat_id,))
        else:
            cur.execute(
                """DELETE FROM chats WHERE id = %s
                   AND (org_id = %s OR org_id IS NULL)""",
                (chat_id, org),
            )
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


def register_brain(brain: str, org_id: str | None, created_by: str | None,
                   shared: bool = False) -> None:
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO brain_access (brain, org_id, created_by, is_shared)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (brain) DO NOTHING""",
                (brain, org_id, created_by, shared),
            )
    except Exception:  # noqa: BLE001
        pass


def brain_access(brain: str) -> dict | None:
    try:
        with _conn() as conn, conn.cursor() as cur:
            # H2: created_by must be readable — the org-less-creator rule
            # (SEC-8) checks it, and without this column it always saw None.
            cur.execute("SELECT brain, org_id, created_by, is_shared FROM brain_access WHERE brain = %s",
                        (brain,))
            return cur.fetchone()
    except Exception:  # noqa: BLE001
        return None


def usage_summary(days: int = 30, org: str | None = None) -> list:
    """Metering. LOW-4: scoped to the caller's org when known — brains the
    org owns, shared brains, and legacy unregistered brains (grandfathered
    visible, same rule as chats). org=None keeps the old platform-wide view
    for auth-off mode."""
    scope, args = "", [str(days)]
    if org is not None:
        scope = """AND (brain IN (SELECT brain FROM brain_access
                                  WHERE org_id = %s OR is_shared)
                       OR brain NOT IN (SELECT brain FROM brain_access))"""
        args.append(org)
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""SELECT feature, brain, model, COUNT(*) AS calls,
                       SUM(est_prompt_tokens) AS prompt_tokens,
                       SUM(est_completion_tokens) AS completion_tokens,
                       SUM(ms) AS total_ms
                FROM llm_calls
                WHERE ts > now() - (%s || ' days')::interval {scope}
                GROUP BY feature, brain, model
                ORDER BY calls DESC""",
            args,
        )
        return cur.fetchall()


def _ts(value):
    if not value:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        # SEC-10: out-of-range client timestamps must drop the field, not 500
        # the save (fromtimestamp raises OSError/OverflowError, not ValueError).
        return None
