"""Native Knowledge Graph: entities, relations, and hierarchical community tables.

Provides first-class Labeled Property Graph (LPG) storage inside PostgreSQL,
enabling schema-constrained extraction, recursive CTE multi-hop traversals, and
100% deterministic provenance citation grounding without external graph containers.

Revision ID: 0007_native_knowledge_graph
Revises: 0006_brain_claim
Create Date: 2026-10-08
"""
from __future__ import annotations

from alembic import op


revision = "0007_native_knowledge_graph"
down_revision = "0006_brain_claim"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. kg_entities: Canonical entities extracted from documents
    op.execute(
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
    op.execute("CREATE INDEX IF NOT EXISTS kg_entities_brain_idx ON kg_entities(brain)")
    op.execute("CREATE INDEX IF NOT EXISTS kg_entities_canonical_idx ON kg_entities(brain, canonical_name)")

    # 2. kg_relations: Directed edges between entities with verified provenance
    op.execute(
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
    op.execute("CREATE INDEX IF NOT EXISTS kg_relations_brain_idx ON kg_relations(brain)")
    op.execute("CREATE INDEX IF NOT EXISTS kg_relations_source_idx ON kg_relations(source_id)")
    op.execute("CREATE INDEX IF NOT EXISTS kg_relations_target_idx ON kg_relations(target_id)")

    # 3. kg_communities: Hierarchical community summaries for global GraphRAG
    op.execute(
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
    op.execute("CREATE INDEX IF NOT EXISTS kg_communities_brain_idx ON kg_communities(brain)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS kg_communities")
    op.execute("DROP TABLE IF EXISTS kg_relations")
    op.execute("DROP TABLE IF EXISTS kg_entities")
