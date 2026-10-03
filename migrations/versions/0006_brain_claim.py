"""Make brain creation exclusive: a name is CLAIMED before the work starts.

BUGS.md M4 (open since 22 Sep) was that `cognee_cloud.exists(name)` is a probe,
not a reservation: two concurrent `POST /api/brains` with the same new name both
saw "does not exist", both ingested, and the ownership row then credited the
dataset to whichever writer inserted first - so the other org's documents ended
up inside a brain it could no longer reach, and neither request was wrong by the
rules as they stood.

`status` + `claimed_at` turn the existing ownership row into that reservation:
'creating' means the name is spoken for and the work is in flight, 'ready' means
the dataset exists. Default 'ready', so every row written before this revision
keeps its meaning.

Revision ID: 0006_brain_claim
Revises: 0005_chat_tombstones
Create Date: 2026-10-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_brain_claim"
down_revision = "0005_chat_tombstones"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE brain_access ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'ready'")
    op.execute("ALTER TABLE brain_access ADD COLUMN IF NOT EXISTS claimed_at timestamptz")
    # Only ever one live claim per name - the primary key already guarantees it,
    # but this makes the intent readable in the schema itself.
    op.execute("CREATE INDEX IF NOT EXISTS brain_access_claim_idx ON brain_access(brain, status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS brain_access_claim_idx")
    op.execute("ALTER TABLE brain_access DROP COLUMN IF EXISTS claimed_at")
    op.execute("ALTER TABLE brain_access DROP COLUMN IF EXISTS status")
