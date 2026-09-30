"""Kestrel app-schema baseline (as of 2026-10-01, commit ed91d64+).

The pre-existing schema (chats, turns, brain_access, llm_calls,
connector_credentials, slack_workspaces, graph_node/edge/metadata) was created
by storage.init()'s idempotent DDL, NOT by Alembic. This migration is therefore
a NO-OP marker: databases created before Alembic are `alembic stamp 0001`-ed;
fresh databases keep using storage.init() and then stamp. Structural changes
begin at 0002.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-01
"""
from __future__ import annotations

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
