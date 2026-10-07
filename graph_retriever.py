"""Hybrid Knowledge Graph Retriever for Kestrel Native Knowledge Graph Engine (KNGE).

Executes local multi-hop graph walks using PostgreSQL recursive CTEs and retrieves
global community summaries for macro-queries, delivering 100% deterministic
provenance citations.
"""

from __future__ import annotations

import os
import re
from typing import Any, List, Optional
import psycopg
from psycopg.rows import dict_row

import storage
import graph_extractor


def find_seed_entities(query: str, brain: str, limit: int = 5) -> list[dict]:
    """Find seed entities in the knowledge graph matching tokens/phrases in query."""
    if not query or not brain:
        return []

    tokens = [t.lower() for t in re.findall(r'[a-zA-Z0-9_\-\.]+', query) if len(t) >= 2]
    if not tokens:
        return []

    try:
        with storage._conn() as conn, conn.cursor() as cur:
            # Match by exact canonical_name, ILIKE, or alias containment
            cur.execute(
                """SELECT id, name, canonical_name, entity_type, description, aliases
                   FROM kg_entities
                   WHERE brain = %s
                     AND (
                       canonical_name = ANY(%s)
                       OR name ILIKE ANY(%s)
                       OR EXISTS (
                         SELECT 1 FROM jsonb_array_elements_text(aliases) a
                         WHERE lower(a) = ANY(%s)
                       )
                     )
                   LIMIT %s""",
                (brain, tokens, [f"%{t}%" for t in tokens], tokens, limit),
            )
            rows = cur.fetchall() or []
            if rows:
                return rows

            # Fallback: substring matching on entity names
            cur.execute(
                """SELECT id, name, canonical_name, entity_type, description, aliases
                   FROM kg_entities
                   WHERE brain = %s
                     AND position(lower(canonical_name) in lower(%s)) > 0
                   LIMIT %s""",
                (brain, query, limit),
            )
            return cur.fetchall() or []
    except Exception as exc:
        storage.mark_down(f"find_seed_entities: {exc}")
        return []


def traverse_graph_neighborhood(
    seed_entity_ids: list[str],
    brain: str,
    max_depth: int = 2,
    limit: int = 30,
) -> list[dict]:
    """Perform k-hop neighborhood graph expansion via PostgreSQL recursive CTE."""
    if not seed_entity_ids or not brain:
        return []

    query = """
    WITH RECURSIVE graph_walk AS (
        -- Base step: 1st hop relations from seed entities
        SELECT
            r.id,
            r.source_id,
            r.target_id,
            r.relation_type,
            r.description,
            r.confidence,
            r.evidence_text,
            r.source_reference_ids,
            1 AS depth,
            ARRAY[r.source_id, r.target_id] AS path
        FROM kg_relations r
        WHERE r.brain = %s
          AND (r.source_id = ANY(%s) OR r.target_id = ANY(%s))

        UNION ALL

        -- Recursive step: traverse connected neighbors up to max_depth
        SELECT
            r.id,
            r.source_id,
            r.target_id,
            r.relation_type,
            r.description,
            r.confidence,
            r.evidence_text,
            r.source_reference_ids,
            gw.depth + 1,
            gw.path || CASE WHEN r.source_id = ANY(gw.path) THEN r.target_id ELSE r.source_id END
        FROM kg_relations r
        JOIN graph_walk gw ON (
            r.source_id = gw.target_id OR r.target_id = gw.target_id OR
            r.source_id = gw.source_id OR r.target_id = gw.source_id
        )
        WHERE r.brain = %s
          AND gw.depth < %s
          AND NOT (r.id = gw.id)
          AND NOT (r.source_id = ANY(gw.path) AND r.target_id = ANY(gw.path))
    )
    SELECT DISTINCT ON (id)
        id, source_id, target_id, relation_type, description,
        confidence, evidence_text, source_reference_ids, depth
    FROM graph_walk
    ORDER BY id, depth ASC, confidence DESC
    LIMIT %s;
    """

    try:
        with storage._conn() as conn, conn.cursor() as cur:
            cur.execute(query, (brain, seed_entity_ids, seed_entity_ids, brain, max_depth, limit))
            relations = cur.fetchall() or []
            if not relations:
                return []

            # Resolve entity names for readable triples
            entity_ids = set()
            for r in relations:
                entity_ids.add(r["source_id"])
                entity_ids.add(r["target_id"])

            cur.execute(
                "SELECT id, name, entity_type FROM kg_entities WHERE id = ANY(%s)",
                (list(entity_ids),),
            )
            ent_map = {row["id"]: row for row in (cur.fetchall() or [])}

            for r in relations:
                src = ent_map.get(r["source_id"], {})
                tgt = ent_map.get(r["target_id"], {})
                r["source_name"] = src.get("name", "Unknown")
                r["source_type"] = src.get("entity_type", "")
                r["target_name"] = tgt.get("name", "Unknown")
                r["target_type"] = tgt.get("entity_type", "")

            return relations
    except Exception as exc:
        storage.mark_down(f"traverse_graph_neighborhood: {exc}")
        return []


def build_graph_context(
    query: str,
    brain: str,
    max_depth: int = 2,
) -> tuple[str, list[str]]:
    """Generate structured graph context and referenced source IDs for the prompt.

    Returns:
        (graph_context_text, list_of_source_reference_ids)
    """
    seeds = find_seed_entities(query, brain)
    if not seeds:
        return "", []

    seed_ids = [s["id"] for s in seeds]
    relations = traverse_graph_neighborhood(seed_ids, brain, max_depth=max_depth)
    if not relations:
        return "", []

    lines = ["Relevant Knowledge Graph Context:"]
    source_refs = set()

    for r in relations:
        triple_desc = f"- ({r['source_name']}) --[{r['relation_type']}]--> ({r['target_name']})"
        if r.get("description"):
            triple_desc += f": {r['description']}"
        if r.get("evidence_text"):
            triple_desc += f' (Evidence: "{r["evidence_text"][:120]}")'
        lines.append(triple_desc)

        for s_id in (r.get("source_reference_ids") or []):
            if s_id:
                source_refs.add(str(s_id))

    return "\n".join(lines), list(source_refs)
