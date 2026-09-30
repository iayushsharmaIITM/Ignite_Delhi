"""PR-4 expand: brain identity, provenance, and job schema (ADDITIVE ONLY).

Introduces the app control-plane schema from the implementation spec §2:
workspaces, durable brain UUIDs, generations, documents/versions, durable
jobs with idempotency + leases, and exact source references. Nothing here
drops or alters existing columns; brain_access and the name-based lookup
paths stay authoritative until the cutover gates pass (PR-7/PR-8).

Ownership invariants use composite foreign keys (spec: "ordinary
single-column FKs are not enough"), e.g. every generation row must carry the
same (brain_id, workspace_id) as its parent brain.

Revision ID: 0002_identity_provenance_jobs
Revises: 0001_baseline
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_identity_provenance_jobs"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- workspaces -------------------------------------------------------
    op.create_table(
        "workspaces",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("clerk_org_id", sa.Text, nullable=True, unique=True),
        sa.Column("personal_user_id", sa.Text, nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "((clerk_org_id IS NULL) != (personal_user_id IS NULL))",
            name="ck_workspaces_exactly_one_identity",
        ),
    )

    # --- brains -----------------------------------------------------------
    op.create_table(
        "brains",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("workspace_id",
                  sa.dialects.postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("slug", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("owner_user_id", sa.Text, nullable=True),
        sa.Column("visibility", sa.Text, nullable=False, server_default="PRIVATE"),
        sa.Column("kind", sa.Text, nullable=False, server_default="UPLOAD"),
        sa.Column("storage_mode", sa.Text, nullable=False, server_default="VERSIONED"),
        sa.Column("state", sa.Text, nullable=False, server_default="CREATING"),
        sa.Column("mutation_generation", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("active_generation_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_brains_workspace_slug"),
        sa.UniqueConstraint("id", "workspace_id", name="uq_brains_id_workspace"),
        sa.CheckConstraint(
            "visibility IN ('PRIVATE','WORKSPACE','DEMO')", name="ck_brains_visibility"),
        sa.CheckConstraint(
            "kind IN ('UPLOAD','CONNECTOR','DEMO')", name="ck_brains_kind"),
        sa.CheckConstraint(
            "storage_mode IN ('VERSIONED','LIVE_SOURCE')", name="ck_brains_storage_mode"),
        sa.CheckConstraint(
            "state IN ('CREATING','READY','UPDATING','SYNCING','DEGRADED_NOT_QUERYABLE',"
            "'FAILED','DELETING','DELETE_FAILED','DELETED')", name="ck_brains_state"),
    )
    op.create_index("ix_brains_workspace", "brains", ["workspace_id"])

    # --- brain_generations --------------------------------------------------
    op.create_table(
        "brain_generations",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("brain_id",
                  sa.dialects.postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("brains.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("workspace_id",
                  sa.dialects.postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generation_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("backend_dataset_name", sa.Text, nullable=False, unique=True),
        sa.Column("backend_dataset_id", sa.Text, nullable=True),
        sa.Column("backend_identity_id", sa.Text, nullable=True),
        sa.Column("state", sa.Text, nullable=False, server_default="BUILDING"),
        sa.Column("publication_mode", sa.Text, nullable=False, server_default="VERSIONED"),
        sa.Column("model_policy_hash", sa.Text, nullable=True),
        sa.Column("embedding_policy_hash", sa.Text, nullable=True),
        sa.Column("image_digest", sa.Text, nullable=True),
        sa.Column("inventory_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("brain_id", "generation_number", name="uq_generation_number"),
        sa.UniqueConstraint("id", "brain_id", "workspace_id", name="uq_generations_ownership"),
        sa.CheckConstraint(
            "state IN ('BUILDING','VERIFYING','VERIFIED','ACTIVE','RETIRED',"
            "'ABANDONED','DELETING','DELETED')", name="ck_generations_state"),
        sa.CheckConstraint(
            "publication_mode IN ('VERSIONED','LIVE_SOURCE')", name="ck_generations_mode"),
    )
    op.create_index("ix_generations_brain", "brain_generations", ["brain_id"])
    # the circular active-generation link, now that the target key exists
    op.create_foreign_key(
        "fk_brains_active_generation", "brains", "brain_generations",
        ["active_generation_id", "id", "workspace_id"],
        ["id", "brain_id", "workspace_id"],
    )

    # --- brain_grants -------------------------------------------------------
    op.create_table(
        "brain_grants",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("brain_id",
                  sa.dialects.postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id",
                  sa.dialects.postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("principal_type", sa.Text, nullable=False),
        sa.Column("principal_id", sa.Text, nullable=False),
        sa.Column("permission", sa.Text, nullable=False),
        sa.Column("granted_by", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("brain_id", "principal_type", "principal_id", name="uq_grant_principal"),
        sa.CheckConstraint(
            "principal_type IN ('USER','WORKSPACE')", name="ck_grants_principal_type"),
        sa.CheckConstraint(
            "permission IN ('READ','WRITE','ADMIN')", name="ck_grants_permission"),
    )

    # --- documents + versions ------------------------------------------------
    op.create_table(
        "documents",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("brain_id",
                  sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id",
                  sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("display_title", sa.Text, nullable=True),
        sa.Column("origin", sa.Text, nullable=False, server_default="UPLOAD"),
        sa.Column("connection_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("external_resource_id", sa.Text, nullable=True),
        sa.Column("lifecycle_state", sa.Text, nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["brain_id", "workspace_id"], ["brains.id", "brains.workspace_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "brain_id", "workspace_id", name="uq_documents_ownership"),
        sa.CheckConstraint(
            "origin IN ('UPLOAD','GMAIL','DRIVE','SLACK','NOTION','CONFLUENCE')", name="ck_documents_origin"),
    )
    op.create_index("ix_documents_brain", "documents", ["brain_id"])
    op.create_index(
        "uq_documents_connector_source", "documents",
        ["connection_id", "origin", "external_resource_id"], unique=True,
        postgresql_where=sa.text("connection_id IS NOT NULL AND external_resource_id IS NOT NULL"),
    )

    op.create_table(
        "document_versions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_id",
                  sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("brain_id",
                  sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id",
                  sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("original_bytes", sa.dialects.postgresql.BYTEA, nullable=True),
        sa.Column("original_sha256", sa.Text, nullable=True),
        sa.Column("exact_extracted_text", sa.Text, nullable=False),
        sa.Column("text_sha256", sa.Text, nullable=False),
        sa.Column("extractor_revision", sa.Text, nullable=False, server_default="documents.py@0002"),
        sa.Column("media_type", sa.Text, nullable=True),
        sa.Column("size_bytes", sa.Integer, nullable=True),
        sa.Column("extraction_report", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_id", "brain_id", "workspace_id"],
                                ["documents.id", "documents.brain_id", "documents.workspace_id"],
                                ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "document_id", "brain_id", "workspace_id", name="uq_docver_ownership"),
        sa.UniqueConstraint("id", "brain_id", "workspace_id", name="uq_docver_ownership3"),
    )
    op.create_index("ix_docver_document", "document_versions", ["document_id"])

    # --- generation <-> document mapping -------------------------------------
    op.create_table(
        "generation_documents",
        sa.Column("generation_id",
                  sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("document_version_id",
                  sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("brain_id",
                  sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id",
                  sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("backend_data_id", sa.Text, nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("generation_id", "document_version_id"),
        sa.ForeignKeyConstraint(["generation_id", "brain_id", "workspace_id"],
                                ["brain_generations.id", "brain_generations.brain_id", "brain_generations.workspace_id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_version_id", "brain_id", "workspace_id"],
                                ["document_versions.id", "document_versions.brain_id", "document_versions.workspace_id"],
                                ondelete="RESTRICT"),
    )
    op.create_index(
        "uq_generation_backend_data", "generation_documents",
        ["generation_id", "backend_data_id"], unique=True,
        postgresql_where=sa.text("backend_data_id IS NOT NULL"),
    )

    # --- durable jobs ---------------------------------------------------------
    op.create_table(
        "brain_jobs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("workspace_id",
                  sa.dialects.postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("brain_id",
                  sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("generation_id",
                  sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False, server_default="QUEUED"),
        sa.Column("expected_mutation_generation", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("request_hash", sa.Text, nullable=True),
        sa.Column("idempotency_key", sa.Text, nullable=False),
        sa.Column("lease_owner", sa.Text, nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_generation", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["brain_id", "workspace_id"], ["brains.id", "brains.workspace_id"]),
        sa.UniqueConstraint("workspace_id", "idempotency_key", name="uq_jobs_idempotency"),
        sa.CheckConstraint(
            "kind IN ('CREATE','UPDATE','REMOVE','REBUILD','DELETE','SYNC')", name="ck_jobs_kind"),
        sa.CheckConstraint(
            "state IN ('QUEUED','EXTRACTING','INGESTING','VERIFYING','SUCCEEDED',"
            "'SUCCEEDED_WITH_EXCLUSIONS','FAILED','RECONCILIATION_REQUIRED',"
            "'CANCEL_REQUESTED','CANCELLED')", name="ck_jobs_state"),
    )
    op.create_index("ix_jobs_state", "brain_jobs", ["state"])
    op.create_index("ix_jobs_brain", "brain_jobs", ["brain_id"])

    op.create_table(
        "brain_job_files",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("job_id",
                  sa.dialects.postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("brain_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brain_id",
                  sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("document_version_id",
                  sa.dialects.postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("client_file_id", sa.Text, nullable=False),
        sa.Column("stage", sa.Text, nullable=False, server_default="QUEUED"),
        sa.Column("outcome", sa.Text, nullable=True),
        sa.Column("backend_data_id", sa.Text, nullable=True),
        sa.Column("warning", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("job_id", "client_file_id", name="uq_job_files_client_id"),
    )

    op.create_table(
        "brain_job_events",
        sa.Column("job_id",
                  sa.dialects.postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("brain_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.BigInteger, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("event", sa.dialects.postgresql.JSONB, nullable=False),
        sa.PrimaryKeyConstraint("job_id", "seq"),
    )

    # --- exact source references ----------------------------------------------
    op.create_table(
        "source_references",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("brain_id",
                  sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id",
                  sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("generation_id",
                  sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("document_version_id",
                  sa.dialects.postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("document_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("backend_data_id", sa.Text, nullable=True),
        sa.Column("backend_chunk_id", sa.Text, nullable=True),
        sa.Column("char_start", sa.Integer, nullable=False),
        sa.Column("char_end", sa.Integer, nullable=False),
        sa.Column("excerpt_sha256", sa.Text, nullable=False),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column("locator", sa.Text, nullable=True),
        sa.Column("valid", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["brain_id", "workspace_id"], ["brains.id", "brains.workspace_id"]),
        sa.CheckConstraint("char_end >= char_start", name="ck_src_ref_offsets"),
    )
    op.create_index("ix_source_refs_docver", "source_references", ["document_version_id"])

    # --- chats: additive brain_id (backfilled in PR-6; FK added there) --------
    op.add_column("chats", sa.Column("brain_id",
                  sa.dialects.postgresql.UUID(as_uuid=False), nullable=True))
    op.create_index("ix_chats_brain_id", "chats", ["brain_id"])


def downgrade() -> None:
    op.drop_index("ix_chats_brain_id", table_name="chats")
    op.drop_column("chats", "brain_id")
    op.drop_table("source_references")
    op.drop_table("brain_job_events")
    op.drop_table("brain_job_files")
    op.drop_table("brain_jobs")
    op.drop_table("generation_documents")
    op.drop_table("document_versions")
    op.drop_table("documents")
    op.drop_table("brain_grants")
    op.drop_constraint("fk_brains_active_generation", "brains", type_="foreignkey")
    op.drop_table("brain_generations")
    op.drop_table("brains")
    op.drop_table("workspaces")
