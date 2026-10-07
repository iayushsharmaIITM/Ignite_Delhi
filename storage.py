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
import time
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://kestrel:kestrel@localhost:5433/kestrel"
)

_status = {"storage": "unavailable", "detail": "not initialised"}
_last_init_try = 0.0
_INIT_RETRY_SECONDS = 30.0

# The most turns one chat may hold. Defined once here so the route that rejects
# a bigger save and the client that trims to fit cannot drift apart.
MAX_TURNS = 500


class OwnershipError(Exception):
    """Raised when a write targets a chat owned by someone else (S1)."""


class TruncationError(Exception):
    """CH-1: a save that would delete stored turns.

    The rewrite is delete-and-reinsert, and the React client used to send only
    its last 60 turns — so the 61st message silently destroyed the first ones,
    permanently, with no error anywhere. A save that carries FEWER turns than
    the database holds is now refused unless the client says it trimmed on
    purpose (which it only does past the server's own cap).
    """

    def __init__(self, chat_id: str, stored: int, incoming: int):
        super().__init__(f"{chat_id}: {incoming} incoming turns vs {stored} stored")
        self.chat_id, self.stored, self.incoming = chat_id, stored, incoming


class ResurrectError(Exception):
    """CH-2: a save re-creating a chat that was deleted.

    Without a tombstone, POST with a previously-deleted id inserted a fresh
    `chats` row and the client's own turn window — so a chat the user deleted
    came back, which is exactly what "it always stays" looked like from the UI.
    """

    def __init__(self, chat_id: str):
        super().__init__(chat_id)
        self.chat_id = chat_id


# CH-8: routes map this to a 503 instead of letting a raw driver error become
# a 500. `available()` alone cannot catch a mid-life outage — once Postgres is
# healthy it reports True for the life of the process.
db_error = psycopg.Error


def mark_down(reason: str = "query failed") -> None:
    """CH-8: a failed query means stop trusting the cached verdict, so the
    next `available()` re-probes (throttled) instead of promising postgres."""
    global _status
    if _status.get("storage") == "postgres":
        _status = {"storage": "unavailable", "detail": reason[:160]}
        global _last_init_try
        _last_init_try = 0.0


def status() -> dict:
    return dict(_status)


def available() -> bool:
    # O2: the one-shot init at import never retried — a slow Postgres at boot
    # degraded the process for its whole lifetime. Retry lazily (throttled)
    # so the process heals itself when the database arrives.
    global _last_init_try
    if _status.get("storage") == "postgres":
        return True
    now = time.time()
    if now - _last_init_try < _INIT_RETRY_SECONDS:
        return False
    _last_init_try = now
    return init()


def _conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True)


def init() -> bool:
    """Create the schema. Returns True when storage is available."""
    global _status
    try:
        with _conn() as conn, conn.cursor() as cur:
            # Columns added after a table already exists need an explicit
            # ALTER; the alembic revision 0004_turn_detail does the same for
            # databases that are migration-managed.
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
                     -- Turn detail the client has always sent: the engine's
                     -- working-log steps, the measured duration, the stopped
                     -- marker and the error state. Without these columns a
                     -- restored chat lost its logs, its "stopped" label and
                     -- rendered failures as answers (they were dropped on save).
                     steps jsonb NOT NULL DEFAULT '[]',
                     worked_ms int,
                     stopped boolean NOT NULL DEFAULT false,
                     error boolean NOT NULL DEFAULT false,
                     PRIMARY KEY (chat_id, idx)
                   )"""
            )
            for ddl in (
                "ALTER TABLE turns ADD COLUMN IF NOT EXISTS steps jsonb NOT NULL DEFAULT '[]'",
                "ALTER TABLE turns ADD COLUMN IF NOT EXISTS worked_ms int",
                "ALTER TABLE turns ADD COLUMN IF NOT EXISTS stopped boolean NOT NULL DEFAULT false",
                "ALTER TABLE turns ADD COLUMN IF NOT EXISTS error boolean NOT NULL DEFAULT false",
            ):
                cur.execute(ddl)
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
            # Item-1 backfill support: person-level ownership for org-less
            # users (their identity has org None, so org_id cannot hold them).
            cur.execute("ALTER TABLE chats ADD COLUMN IF NOT EXISTS created_by text")
            cur.execute("CREATE INDEX IF NOT EXISTS chats_created_by_idx ON chats(created_by)")
            # O10: brain_access predates created_by on old volumes — without
            # this guard the SELECT fails, brain_access() returns None, and
            # fail-closed 403s EVERY brain after an upgrade. Same class of
            # guard the chats table already had; brain_access never got one.
            cur.execute("ALTER TABLE brain_access ADD COLUMN IF NOT EXISTS created_by text")
            cur.execute("ALTER TABLE brain_access ADD COLUMN IF NOT EXISTS org_id text")
            cur.execute("ALTER TABLE brain_access ADD COLUMN IF NOT EXISTS is_shared boolean NOT NULL DEFAULT false")
            # M4: a brain name is CLAIMED (status='creating') before any work
            # starts, so two concurrent creates cannot both pass an exists()
            # probe. Mirrors migration 0006 for bootstrapped databases.
            cur.execute("ALTER TABLE brain_access ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'ready'")
            cur.execute("ALTER TABLE brain_access ADD COLUMN IF NOT EXISTS claimed_at timestamptz")
            # CH-2: the deletion tombstone. `chats`/`turns` cannot remember what
            # was removed, so a POST with a deleted id re-created the chat.
            cur.execute(
                """CREATE TABLE IF NOT EXISTS deleted_chats (
                     id text PRIMARY KEY,
                     deleted_at timestamptz NOT NULL DEFAULT now(),
                     deleted_by_org text,
                     deleted_by_user text
                   )""")
            # Retention: long enough that a stale tab or another device cannot
            # resurrect a chat the user deleted, short enough that a year of
            # deletions does not grow a permanent table.
            cur.execute("DELETE FROM deleted_chats WHERE deleted_at < now() - interval '90 days'")
            # CH-10: `brain_id` arrives from migration 0002 but nothing in
            # init() created it, so a bootstrapped (non-migrated) database had
            # no such column and ops/backfill.py failed there.
            #
            # uuid, matching migration 0002: this line said `text` while 0002 said
            # UUID, so the type of chats.brain_id depended on whether a database
            # was migrated or bootstrapped. IF NOT EXISTS will not retype an
            # existing column, so databases created under the old line keep text —
            # harmless, because nothing compares brain_id as a uuid, and no
            # conversion is run here. New databases from either path now agree.
            cur.execute("ALTER TABLE chats ADD COLUMN IF NOT EXISTS brain_id uuid")
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
            cur.execute(
                """CREATE TABLE IF NOT EXISTS audit_logs (
                     id SERIAL PRIMARY KEY,
                     timestamp timestamptz NOT NULL DEFAULT now(),
                     actor_id text,
                     org_id text,
                     action text NOT NULL,
                     resource_type text NOT NULL,
                     resource_id text,
                     details jsonb DEFAULT '{}'::jsonb,
                     ip_address text
                   )"""
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_org_ts ON audit_logs (org_id, timestamp DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS chats_brain_idx ON chats(brain, updated DESC)")
            # O5: metering grows one row per ask with no index and no purge —
            # unbounded disk, linearly slower /api/usage. Index the hot filter
            # and retain 180 days (provider dashboards remain the audit source).
            cur.execute("CREATE INDEX IF NOT EXISTS llm_calls_ts_idx ON llm_calls(ts)")
            cur.execute("DELETE FROM llm_calls WHERE ts < now() - interval '180 days'")

            # Native Knowledge Graph tables (matching migration 0007_native_knowledge_graph)
            cur.execute(
                """CREATE TABLE IF NOT EXISTS kg_entities (
                     id text PRIMARY KEY,
                     brain text NOT NULL,
                     name text NOT NULL,
                     canonical_name text NOT NULL,
                     entity_type text NOT NULL,
                     description text NOT NULL DEFAULT '',
                     aliases jsonb NOT NULL DEFAULT '[]',
                     metadata jsonb NOT NULL DEFAULT '{}',
                     created_at timestamptz NOT NULL DEFAULT now(),
                     CONSTRAINT uq_kg_entities_brain_canonical UNIQUE(brain, canonical_name, entity_type)
                   )"""
            )
            cur.execute("CREATE INDEX IF NOT EXISTS kg_entities_brain_idx ON kg_entities(brain)")
            cur.execute("CREATE INDEX IF NOT EXISTS kg_entities_canonical_idx ON kg_entities(brain, canonical_name)")

            cur.execute(
                """CREATE TABLE IF NOT EXISTS kg_relations (
                     id text PRIMARY KEY,
                     brain text NOT NULL,
                     source_id text NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
                     target_id text NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
                     relation_type text NOT NULL,
                     description text NOT NULL DEFAULT '',
                     confidence double precision NOT NULL DEFAULT 1.0,
                     evidence_text text NOT NULL DEFAULT '',
                     source_reference_ids jsonb NOT NULL DEFAULT '[]',
                     metadata jsonb NOT NULL DEFAULT '{}',
                     created_at timestamptz NOT NULL DEFAULT now(),
                     CONSTRAINT uq_kg_relations_triple UNIQUE(brain, source_id, target_id, relation_type)
                   )"""
            )
            cur.execute("CREATE INDEX IF NOT EXISTS kg_relations_brain_idx ON kg_relations(brain)")
            cur.execute("CREATE INDEX IF NOT EXISTS kg_relations_source_idx ON kg_relations(source_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS kg_relations_target_idx ON kg_relations(target_id)")

            cur.execute(
                """CREATE TABLE IF NOT EXISTS kg_communities (
                     id text PRIMARY KEY,
                     brain text NOT NULL,
                     level int NOT NULL DEFAULT 0,
                     name text NOT NULL,
                     summary text NOT NULL,
                     entity_ids jsonb NOT NULL DEFAULT '[]',
                     created_at timestamptz NOT NULL DEFAULT now()
                   )"""
            )
            cur.execute("CREATE INDEX IF NOT EXISTS kg_communities_brain_idx ON kg_communities(brain)")
        _status = {"storage": "postgres", "detail": DATABASE_URL.split("@")[-1]}
        return True
    except Exception as exc:  # noqa: BLE001 - persistence degrades, never raises
        _status = {"storage": "unavailable", "detail": str(exc)[:160]}
        return False


def _demo() -> str:
    """S7: the demo fallback must BE DEMO_DATASET (COGNEE_DATASET or
    company_brain) — the old literal "demo" filed chats under a key no read
    path ever lists, silently split-braining them."""
    return os.getenv("COGNEE_DATASET", "company_brain")


def _norm_brain(raw) -> str:
    """Local brain-name normalizer (mirrors app.safe_dataset without the
    import — app imports storage, so storage cannot import app). Maps the UI
    'demo' alias to the real dataset; unknown/empty falls back per _demo()."""
    import re as _re
    name = (raw or "").strip().lower()
    name = _re.sub(r"[\s\-.]+", "_", name)
    name = _re.sub(r"[^a-z0-9_]", "", name)
    name = _re.sub(r"_{2,}", "_", name).strip("_")
    if not _re.fullmatch(r"[a-z0-9][a-z0-9_]{2,39}", name):
        return ""
    return _demo() if name == "demo" else name


def _est_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def upsert_chat(record: dict, org: str | None = None,
                brain: str | None = None,
                created_by: str | None = None) -> dict:
    """Insert or update one chat with its full turns array.

    SEC-5: `org`/`brain`/`created_by` are server-stamped by the caller
    (identity + route). A client-supplied org_id in the record is IGNORED —
    the server wins, so a client can neither omit ownership nor self-declare
    into another org. `brain` is normalized server-side (NEW-4).
    """
    chat_id = record["id"]
    raw_brain = brain if brain is not None else record.get("brain")
    brain = _norm_brain(raw_brain) or _demo()
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
            # S1: an existing chat owned by someone else cannot be overwritten
            # or re-stamped — knowing the id is not ownership. Legacy
            # double-NULL rows are first-stamp-wins (public until stamped).
            #
            # FOR UPDATE is what makes the two guards below real. They are
            # SELECT-then-write under READ COMMITTED, so without a lock a
            # concurrent delete or save could commit between the check and the
            # rewrite: the tombstone check would pass on a row about to be
            # deleted, and the turn count would be stale by the time the DELETE
            # below ran — which is the exact history loss CH-1 exists to refuse.
            # Locking the parent first serialises every writer on this chat
            # (delete_chat and the cascade both need the same row).
            cur.execute("SELECT org_id, created_by FROM chats WHERE id = %s "
                        "FOR UPDATE",
                        (chat_id,))
            prior = cur.fetchone()
            if prior and (prior["org_id"] or prior["created_by"]):
                if not ((org and prior["org_id"] == org)
                        or (created_by and prior["created_by"] == created_by)):
                    raise OwnershipError(chat_id)
            # CH-2: a deleted id stays deleted. The client still holding it gets
            # a 410 and starts a new conversation instead of resurrecting the
            # chat the user threw away (another tab, or this tab's own stale
            # save tick, used to bring the whole thread back).
            cur.execute("SELECT 1 FROM deleted_chats WHERE id = %s", (chat_id,))
            if cur.fetchone():
                raise ResurrectError(chat_id)
            # CH-1: a save carrying FEWER turns than the database holds would
            # delete history in the rewrite below. Refuse unless the client says
            # it trimmed deliberately (it only does past MAX_TURNS).
            cur.execute("SELECT count(*) AS n FROM turns WHERE chat_id = %s",
                        (chat_id,))
            stored = (cur.fetchone() or {}).get("n") or 0
            if stored and len(turns) < stored and not record.get("trim"):
                raise TruncationError(chat_id, stored, len(turns))
            cur.execute(
                """INSERT INTO chats (id, brain, org_id, created_by, title, created, updated)
                   VALUES (%s, %s, %s, %s, %s,
                           COALESCE(%s, now()), now())
                   ON CONFLICT (id) DO UPDATE
                     SET title = EXCLUDED.title, updated = now(),
                         brain = EXCLUDED.brain,
                         org_id = COALESCE(EXCLUDED.org_id, chats.org_id),
                         created_by = COALESCE(EXCLUDED.created_by, chats.created_by)""",
                (chat_id, brain, org, created_by, title, _ts(created)),
            )
            cur.execute("DELETE FROM turns WHERE chat_id = %s", (chat_id,))
            for idx, t in enumerate(turns):
                cur.execute(
                    """INSERT INTO turns (chat_id, idx, role, text, sources,
                                           attachments, at, steps, worked_ms,
                                           stopped, error)
                       VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, now()),
                               %s, %s, %s, %s)""",
                    (
                        chat_id,
                        idx,
                        t.get("role"),
                        t.get("text") or "",
                        json.dumps(t.get("sources") or []),
                        json.dumps(t.get("attachments") or []),
                        _ts(t.get("at")),
                        json.dumps(t.get("steps") or []),
                        _ms(t.get("workedMs")),
                        bool(t.get("stopped")),
                        bool(t.get("error")),
                    ),
                )
    finally:
        conn.close()
    return {"ok": True, "id": chat_id, "turns": len(turns)}


def list_chats(brain: str | None, org: str | None = None,
               user_id: str | None = None, limit: int = 200) -> list:
    """Newest first. `limit` is caller-controlled but bounded (the sidebar asks
    for more when the user expands a folder; the old hard LIMIT 50 silently hid
    history behind a cap the UI never mentioned)."""
    limit = max(1, min(int(limit or 200), 500))
    clauses, args = [], []
    if brain:
        clauses.append("brain = %s"); args.append(brain)
    pred, pargs = _owner_clause(org, user_id)
    if pred:                                        # auth on: only owned chats
        clauses.append(pred); args.extend(pargs)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""SELECT id, brain, title, created, updated FROM chats {where}
                ORDER BY updated DESC, id LIMIT %s""", (*args, limit))
        return cur.fetchall()


def _owner_clause(org: str | None, user_id: str | None) -> tuple:
    """Ownership predicate: org match OR creator match, with legacy
    grandfathering.

    Stamped rows are visible only to their org / creator. Pre-P3 rows have
    BOTH NULL and stay visible to everyone (the demo history depends on it)
    until the item-1 backfill stamps the creator. With org=None AND
    user_id=None (auth off) there is no predicate: unchanged single-user
    behavior.
    """
    if org is None and user_id is None:
        return "", []
    return ("(org_id = %s OR created_by = %s OR (org_id IS NULL AND created_by IS NULL))",
            [org, user_id])


def get_chat(chat_id: str, org: str | None = None,
             user_id: str | None = None) -> dict | None:
    """Read one chat with its turns.

    CH-8: this used to run as two statements on an AUTOCOMMIT connection, so a
    concurrent delete could land between them — the row read as existing with an
    empty (or gone) turn set. One connection and one transaction is NOT enough:
    Postgres' default READ COMMITTED takes a fresh snapshot per STATEMENT, so the
    second read would still see a turns table the first read never saw. The chat
    row is therefore locked FOR SHARE for the whole read: `delete_chat` (and
    `save_chat`'s rewrite) must lock the same row to run, so neither can commit
    mid-read. Share locks still allow two readers at once, and the turns SELECT
    needs no lock of its own because the cascade cannot get past the parent.
    """
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        with conn, conn.cursor() as cur:
            pred, args = _owner_clause(org, user_id)
            cur.execute(
                "SELECT id, brain, title, created, updated FROM chats WHERE id = %s"
                + (" AND " + pred if pred else "")
                + " FOR SHARE",
                (chat_id, *args),
            )
            chat = cur.fetchone()
            if not chat:
                return None
            cur.execute(
                """SELECT role, text, sources, attachments, at, steps,
                          worked_ms AS "workedMs", stopped, error
                   FROM turns WHERE chat_id = %s ORDER BY idx""",
                (chat_id,),
            )
            chat["turns"] = cur.fetchall()
        return chat
    finally:
        conn.close()


def delete_chat(chat_id: str, org: str | None = None,
                user_id: str | None = None) -> bool:
    """Delete a chat. Stamped rows require an org or creator match (item 3:
    tightened to org-match-only semantics — legacy double-NULL rows stay
    deletable until the backfill stamps them, since undeletable-by-anyone
    would be worse).

    CH-2: the deletion is remembered in `deleted_chats` inside the same
    transaction, so a later POST with the same id cannot re-create the chat.
    """
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        with conn, conn.cursor() as cur:
            if org is None and user_id is None:
                cur.execute("DELETE FROM chats WHERE id = %s", (chat_id,))
            else:
                cur.execute(
                    """DELETE FROM chats WHERE id = %s
                       AND (org_id = %s OR created_by = %s
                            OR (org_id IS NULL AND created_by IS NULL))""",
                    (chat_id, org, user_id),
                )
            if not cur.rowcount:
                return False
            cur.execute(
                """INSERT INTO deleted_chats (id, deleted_by_org, deleted_by_user)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET deleted_at = now(),
                     deleted_by_org = EXCLUDED.deleted_by_org,
                     deleted_by_user = EXCLUDED.deleted_by_user""",
                (chat_id, org, user_id),
            )
        return True
    finally:
        conn.close()


def count_chats(brain: str | None = None, org: str | None = None,
               user_id: str | None = None) -> int:
    """CH-7: the un-capped count, so the API can say "showing N of M" instead
    of a cap nobody mentioned. Separate from list_chats rather than a window
    function, which would change that function's row shape for every caller."""
    clauses, args = [], []
    if brain:
        clauses.append("brain = %s"); args.append(brain)
    pred, pargs = _owner_clause(org, user_id)
    if pred:
        clauses.append(pred); args.extend(pargs)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) AS n FROM chats {where}", args)
        return (cur.fetchone() or {}).get("n", 0)


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


# A claim held by its own creator is always re-enterable — a failed upload must
# not lock its author out. A claim held by SOMEONE ELSE can only be retaken after
# this long, and only because the caller asks while the dataset does NOT exist,
# which means that create died mid-flight and left nothing behind.
CLAIM_STALE_SECONDS = 900


def claim_brain(brain: str, org_id: str | None, created_by: str | None) -> str:
    """Reserve a brain name for this identity BEFORE the work starts (M4).

    The atomic INSERT ... ON CONFLICT DO NOTHING is the whole point: `exists()`
    can only ever answer a question about the past, so two concurrent creates
    both heard "new" and both ingested - the loser's documents ended up inside a
    brain it could no longer reach, and the ownership row credited the dataset to
    whichever writer inserted first.

    Returns:
      'claimed'      the name was unclaimed; this caller may create it
      'owned'        this identity already has a ready brain of that name
      'retry'        this creator's own in-flight claim, taken again now
      'stolen'       a dead creator's stale claim on a name with no dataset
      'taken'        someone else is creating it right now - fail closed
      'unavailable'  storage is down; the caller must not proceed unclaimed
    """
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO brain_access
                             (brain, org_id, created_by, is_shared, status, claimed_at)
                   VALUES (%s, %s, %s, false, 'creating', now())
                   ON CONFLICT (brain) DO NOTHING
                   RETURNING brain""",
                (brain, org_id, created_by),
            )
            if cur.fetchone():
                return "claimed"
            cur.execute(
                """SELECT org_id, created_by, status,
                          extract(epoch FROM (now() - claimed_at)) AS age
                   FROM brain_access WHERE brain = %s""",
                (brain,),
            )
            row = cur.fetchone()
            if row is None:                       # raced away, or no such row
                return "taken"
            mine = bool((org_id and row["org_id"] == org_id)
                        or (created_by and row["created_by"] == created_by))
            if row["status"] == "ready":
                return "owned" if mine else "taken"
            if mine:
                cur.execute(
                    "UPDATE brain_access SET claimed_at = now() "
                    "WHERE brain = %s AND status = 'creating'",
                    (brain,),
                )
                return "retry" if cur.rowcount else "taken"
            if (row["age"] or 0) > CLAIM_STALE_SECONDS:
                # A create that started more than CLAIM_STALE_SECONDS ago with no
                # dataset to show for it never finished. Hand the name over rather
                # than poisoning it forever - the SEC-9 lesson seen from the other
                # side: a dead claim must not lock out the next legitimate user.
                cur.execute(
                    """UPDATE brain_access
                          SET org_id = %s, created_by = %s, claimed_at = now()
                        WHERE brain = %s AND status = 'creating'
                          AND extract(epoch FROM (now() - claimed_at)) > %s""",
                    (org_id, created_by, brain, CLAIM_STALE_SECONDS),
                )
                return "stolen" if cur.rowcount else "taken"
            return "taken"
    except Exception:  # noqa: BLE001 - a claim we cannot record is not a claim
        return "unavailable"


def release_brain_claim(brain: str, org_id: str | None,
                        created_by: str | None) -> None:
    """Drop OUR OWN in-flight claim after a failed create.

    Without this a rejected upload squats the name forever - the SEC-9 failure,
    seen from the other side: an ownership row for a brain that does not exist
    locks out the next person who legitimately uses that name.
    """
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                """DELETE FROM brain_access
                    WHERE brain = %s AND status = 'creating'
                      AND org_id IS NOT DISTINCT FROM %s
                      AND created_by IS NOT DISTINCT FROM %s""",
                (brain, org_id, created_by),
            )
    except Exception:  # noqa: BLE001
        pass


def mark_brain_ready(brain: str) -> None:
    """A confirmed dataset: flip the claim to 'ready' and stop timing it.

    The `status = 'creating'` predicate is what keeps this one-way. Without it a
    late call (a retry, or a create that lost its race and reached the success
    path anyway) could flip a row that another org had claimed in the meantime, or
    reset `claimed_at` on a brain that has been ready for weeks — which hands the
    name to whoever holds the stale timestamp.
    """
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE brain_access SET status = 'ready', claimed_at = NULL "
                "WHERE brain = %s AND status = 'creating'",
                (brain,),
            )
    except Exception:  # noqa: BLE001
        pass


def unregister_brain(brain: str) -> None:
    """Delete the ownership row. S2: delete_brain calls this AFTER the tenant
    dataset is gone — otherwise the stale row squats the name forever (a
    re-create by anyone else 403s on the dead owner's row, since register is
    DO NOTHING on conflict)."""
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM brain_access WHERE brain = %s", (brain,))
    except Exception:  # noqa: BLE001
        pass


def brain_access(brain: str) -> dict | None:
    """The ownership row for a brain, or None when the query ran and found no row.

    A FAILED query raises (S8, and the CH-8 rule the rest of this module already
    follows). It used to return None on any exception, and `brain_allowed()` reads None
    as "no such brain" — so during a Postgres outage every authenticated user was told
    the brain they own does not exist, and `/api/source` 404ed for the same reason.
    A successful query with no row still returns None. (It does NOT make the two denials
    identical: unknown and foreign brains already answer different 403 details, which is
    the enumeration oracle ACL Phase 1A exists to close, not something this change
    touches.) O10 note: on a volume whose brain_access table predates `created_by`, this
    now surfaces as a 503 rather than a wall of 403s — the honest reading of "the schema
    is not ready", not a permission verdict.
    """
    try:
        with _conn() as conn, conn.cursor() as cur:
            # H2: created_by must be readable — the org-less-creator rule
            # (SEC-8) checks it, and without this column it always saw None.
            cur.execute("SELECT brain, org_id, created_by, is_shared, status FROM brain_access WHERE brain = %s",
                        (brain,))
            return cur.fetchone()
    except db_error as exc:
        mark_down(f"brain_access: {exc}")
        raise


def usage_summary(days: int = 30, org: str | None = None,
                  user_id: str | None = None) -> list:
    """Metering. LOW-4: scoped to the caller — brains the org owns, brains
    the user created, shared brains, and legacy unregistered brains
    (grandfathered visible, same rule as chats). No identity keeps the old
    platform-wide view for auth-off mode."""
    scope, args = "", [str(days)]
    if org is not None or user_id is not None:
        scope = """AND (brain IN (SELECT brain FROM brain_access
                                  WHERE org_id = %s OR created_by = %s OR is_shared)
                       OR brain NOT IN (SELECT brain FROM brain_access))"""
        args.extend([org, user_id])
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
    """Parse a client timestamp. Two shapes arrive (CH-5): a live turn sends a
    millisecond epoch, a RESTORED turn sends back the ISO string the server
    gave it. Only the numeric shape was understood, so ISO fell through to
    None — and `at` is COALESCEd with now() — which meant re-saving a restored
    chat silently restamped every old turn with the current time. The damage
    was invisible (the client parses ISO fine for display) until the sidebar
    order changed.

    SEC-10: out-of-range values drop the field rather than 500ing the save
    (fromtimestamp raises OSError/OverflowError, not ValueError).
    """
    if not value:
        return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass  # an epoch carried as a string falls through to the numeric path
    try:
        return datetime.fromtimestamp(float(value) / 1000, timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _ms(value):
    """CH-9: `workedMs` is client-supplied. int("abc") used to escape upsert
    and 500 the whole save; a bad duration is worth nothing, so drop it."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Native Knowledge Graph Engine (KNGE) storage methods
# ---------------------------------------------------------------------------

def ingest_graph_triples(
    brain: str,
    entities: list,
    relations: list,
    source_ref_id: str | None = None,
) -> tuple[bool, int, int]:
    """Atomically ingest extracted entities and relationships into PostgreSQL.

    Guarantees:
    - Atomicity: executed inside ONE explicit database transaction.
    - Idempotency: ON CONFLICT merges aliases and appends source_reference_ids.
    - Deterministic Provenance: source_ref_id is attached to every created edge.
    """
    import uuid
    import json
    import graph_extractor

    if not entities and not relations:
        return True, 0, 0

    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False)
    inserted_e = 0
    inserted_r = 0

    try:
        with conn.cursor() as cur:
            # 1. Upsert entities and build canonical lookup map
            name_to_id: dict[str, str] = {}
            for e in entities:
                raw_name = getattr(e, "name", "")
                c_name = graph_extractor.canonicalize_entity_name(raw_name)
                if not c_name:
                    continue

                e_id = str(uuid.uuid4())
                e_type = getattr(e, "entity_type", "Concept")
                if hasattr(e_type, "value"):
                    e_type = e_type.value
                e_desc = getattr(e, "description", "") or ""
                e_aliases = getattr(e, "aliases", []) or []

                cur.execute(
                    """INSERT INTO kg_entities (id, brain, name, canonical_name, entity_type, description, aliases, metadata, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, '{}'::jsonb, now())
                       ON CONFLICT (brain, canonical_name, entity_type)
                       DO UPDATE SET
                         description = CASE WHEN EXCLUDED.description <> '' THEN EXCLUDED.description ELSE kg_entities.description END,
                         aliases = (SELECT jsonb_agg(DISTINCT elem) FROM jsonb_array_elements_text(kg_entities.aliases || EXCLUDED.aliases) elem)
                       RETURNING id""",
                    (e_id, brain, raw_name, c_name, str(e_type), e_desc, json.dumps(e_aliases)),
                )
                row = cur.fetchone()
                final_id = row["id"] if row else e_id
                name_to_id[c_name] = final_id
                name_to_id[raw_name.strip().lower()] = final_id
                inserted_e += 1

            # 2. Upsert relationships
            source_refs = [source_ref_id] if source_ref_id else []
            for r in relations:
                src_name = getattr(r, "source_entity", "")
                tgt_name = getattr(r, "target_entity", "")
                src_c = graph_extractor.canonicalize_entity_name(src_name)
                tgt_c = graph_extractor.canonicalize_entity_name(tgt_name)

                src_id = name_to_id.get(src_c) or name_to_id.get(src_name.strip().lower())
                tgt_id = name_to_id.get(tgt_c) or name_to_id.get(tgt_name.strip().lower())

                # If an entity wasn't in the chunk's entity list, look it up in this brain
                if not src_id:
                    cur.execute("SELECT id FROM kg_entities WHERE brain = %s AND canonical_name = %s", (brain, src_c))
                    row = cur.fetchone()
                    if row:
                        src_id = row["id"]
                if not tgt_id:
                    cur.execute("SELECT id FROM kg_entities WHERE brain = %s AND canonical_name = %s", (brain, tgt_c))
                    row = cur.fetchone()
                    if row:
                        tgt_id = row["id"]

                if not src_id or not tgt_id or src_id == tgt_id:
                    continue

                r_id = str(uuid.uuid4())
                r_type = getattr(r, "relation_type", "RELATED_TO")
                if hasattr(r_type, "value"):
                    r_type = r_type.value
                r_desc = getattr(r, "description", "") or ""
                r_conf = float(getattr(r, "confidence", 1.0) or 1.0)
                r_evid = getattr(r, "evidence_text", "") or ""

                cur.execute(
                    """INSERT INTO kg_relations (id, brain, source_id, target_id, relation_type, description, confidence, evidence_text, source_reference_ids, metadata, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, '{}'::jsonb, now())
                       ON CONFLICT (brain, source_id, target_id, relation_type)
                       DO UPDATE SET
                         confidence = EXCLUDED.confidence,
                         evidence_text = CASE WHEN EXCLUDED.evidence_text <> '' THEN EXCLUDED.evidence_text ELSE kg_relations.evidence_text END,
                         source_reference_ids = (SELECT jsonb_agg(DISTINCT elem) FROM jsonb_array_elements_text(kg_relations.source_reference_ids || EXCLUDED.source_reference_ids) elem)""",
                    (r_id, brain, src_id, tgt_id, str(r_type), r_desc, r_conf, r_evid, json.dumps(source_refs)),
                )
                inserted_r += 1

        conn.commit()
        return True, inserted_e, inserted_r
    except Exception as exc:
        conn.rollback()
        mark_down(f"ingest_graph_triples: {exc}")
        raise
    finally:
        conn.close()


def get_brain_graph(brain: str, limit: int = 500) -> dict:
    """Retrieve the Labeled Property Graph for a brain in {nodes: [], edges: []} format."""
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT id, name as label, entity_type as type, description, aliases, created_at
                   FROM kg_entities
                   WHERE brain = %s
                   ORDER BY created_at ASC
                   LIMIT %s""",
                (brain, limit),
            )
            nodes = cur.fetchall() or []

            cur.execute(
                """SELECT id, source_id as source, target_id as target, relation_type as label,
                          description, confidence, evidence_text, source_reference_ids
                   FROM kg_relations
                   WHERE brain = %s
                   LIMIT %s""",
                (brain, limit * 2),
            )
            edges = cur.fetchall() or []

            return {"nodes": nodes, "edges": edges}
    except Exception as exc:
        mark_down(f"get_brain_graph: {exc}")
        return {"nodes": [], "edges": [], "error": str(exc)}


def delete_brain_graph(brain: str) -> bool:
    """Delete all knowledge graph entities, relations, and communities for a brain."""
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM kg_entities WHERE brain = %s", (brain,))
            cur.execute("DELETE FROM kg_communities WHERE brain = %s", (brain,))
        return True
    except Exception as exc:
        mark_down(f"delete_brain_graph: {exc}")
        return False

