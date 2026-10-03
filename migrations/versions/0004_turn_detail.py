"""Turn detail the client has always sent: steps, worked_ms, stopped, error.

The turns table only stored role/text/sources/attachments/at, so everything the
UI needs to re-render an answer's working log — the engine's steps with their
measured durations, the "stopped" marker, and the error state — was dropped on
save and missing after a reload. The API contract never changed (the client kept
sending these fields); the columns did not exist to receive them.

Revision ID: 0004_turn_detail
Revises: 0003_job_staging
Create Date: 2026-10-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_turn_detail"
down_revision = "0003_job_staging"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default so existing rows get a valid value instead of NULL, and
    # IF NOT EXISTS because storage.init() may have already added these columns
    # on a database that was bootstrapped rather than migrated.
    op.execute("ALTER TABLE turns ADD COLUMN IF NOT EXISTS steps jsonb NOT NULL DEFAULT '[]'")
    op.execute("ALTER TABLE turns ADD COLUMN IF NOT EXISTS worked_ms int")
    op.execute("ALTER TABLE turns ADD COLUMN IF NOT EXISTS stopped boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE turns ADD COLUMN IF NOT EXISTS error boolean NOT NULL DEFAULT false")


def downgrade() -> None:
    op.drop_column("turns", "error")
    op.drop_column("turns", "stopped")
    op.drop_column("turns", "worked_ms")
    op.drop_column("turns", "steps")
