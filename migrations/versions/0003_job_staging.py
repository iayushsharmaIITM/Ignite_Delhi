"""PR-7: durable input staging for the v2 create path.

Raw upload bytes are persisted (Postgres blob, beta-scale per spec §2) BEFORE
the 202 returns, so no remote ingestion ever starts without staged inputs.
Originals stay until document_versions captures them and the job completes.

Revision ID: 0003_job_staging
Revises: 0002_identity_provenance_jobs
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_job_staging"
down_revision = "0002_identity_provenance_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brain_job_staging",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("job_id",
                  sa.dialects.postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("brain_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_file_id", sa.Text, nullable=False),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("content_bytes", sa.dialects.postgresql.BYTEA, nullable=False),
        sa.Column("sha256", sa.Text, nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("job_id", "client_file_id", name="uq_staging_client_id"),
    )


def downgrade() -> None:
    op.drop_table("brain_job_staging")
