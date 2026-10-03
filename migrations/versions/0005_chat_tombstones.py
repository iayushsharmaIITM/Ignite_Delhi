"""Remember deleted chats so a stale client cannot bring one back (CH-2).

A chat was deleted by removing its row, and nothing recorded that it had ever
existed. Any later POST carrying that id — the tab that still held the
conversation, another device, the local-only restore push — inserted a fresh
`chats` row and re-inserted the client's own turn window. From the user's side
the chat they deleted kept coming back, and the DELETE that said so was a 200
{"ok": false} nobody read. The tombstone makes deletion a durable fact; the
route refuses a save against a deleted id with 409.

Tombstones are pruned after 90 days by storage.init(), so the table cannot grow
without bound while still covering any tab that might realistically reopen.

Revision ID: 0005_chat_tombstones
Revises: 0004_turn_detail
Create Date: 2026-10-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_chat_tombstones"
down_revision = "0004_turn_detail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # if_not_exists because storage.init() creates this same table with
    # CREATE TABLE IF NOT EXISTS. Two authorities own this schema, so every
    # migration has to survive running on a database the app already bootstrapped;
    # without this, `alembic upgrade head` died on `relation "deleted_chats"
    # already exists` — which is the Heroku release-phase order (boot, then
    # migrate), so it would have failed the first deploy.
    op.create_table(
        "deleted_chats",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_by_org", sa.Text, nullable=True),
        sa.Column("deleted_by_user", sa.Text, nullable=True),
        if_not_exists=True,
    )
    # CH-10 parity: brain_id arrives from 0002 on a migrated database, but
    # storage.init() never created it, so a bootstrapped database had no such
    # column and ops/backfill.py broke there. IF NOT EXISTS keeps both paths
    # converging on one shape, and the type matches 0002 (uuid) rather than the
    # `text` this line used to declare.
    op.execute("ALTER TABLE chats ADD COLUMN IF NOT EXISTS brain_id uuid")


def downgrade() -> None:
    op.drop_table("deleted_chats")
