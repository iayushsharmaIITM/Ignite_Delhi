"""Tests for Native Knowledge Graph extraction and transactional ingestion.

Run: python3 tests/test_native_graph_ingest.py
"""

from __future__ import annotations

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force auth-off, mock provider, and target LAB database on 5434 for unit tests
os.environ["AUTH_MODE"] = "off"
os.environ["PROVIDER"] = "mock"
if "DATABASE_URL" not in os.environ:
    pw = ""
    env_oss = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env.oss")
    if os.path.exists(env_oss):
        for line in open(env_oss):
            if line.startswith("GRAPH_DATABASE_PASSWORD="):
                pw = line.split("=", 1)[1].strip()
                break
    os.environ["DATABASE_URL"] = f"postgresql://kestrel:{pw}@localhost:5434/kestrel"

import storage
from ontology import EntityType, ExtractedEntity, ExtractedRelation, ExtractionResult, RelationType
import graph_extractor

PASSED = []
FAILED = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL  {name} - {detail}")


def test_entity_canonicalization():
    print("\n[Entity Canonicalization]")
    check(
        "whitespace and casing normalized",
        graph_extractor.canonicalize_entity_name("  Bluepeak   Technologies Inc. ") == "bluepeak technologies inc",
    )
    check(
        "punctuation trimmed",
        graph_extractor.canonicalize_entity_name('"Pulse API"') == "pulse api",
    )
    check(
        "acronym preserves meaning",
        graph_extractor.canonicalize_entity_name("S.O.C. 2") == "soc 2",
    )


def test_extraction_parsing():
    print("\n[Structured Extraction Parsing]")
    sample_json = """
    {
      "entities": [
        {
          "name": "Bluepeak Inc",
          "entity_type": "Organization",
          "description": "Customer party to the MSA",
          "aliases": ["Bluepeak"]
        },
        {
          "name": "MSA-2025-0114",
          "entity_type": "Contract",
          "description": "Master Services Agreement between Kestrel and Bluepeak",
          "aliases": ["MSA"]
        }
      ],
      "relations": [
        {
          "source_entity": "Bluepeak Inc",
          "target_entity": "MSA-2025-0114",
          "relation_type": "PARTY_TO",
          "description": "Party to Master Services Agreement",
          "confidence": 0.98,
          "evidence_text": "This Master Services Agreement is entered into by Bluepeak Inc."
        }
      ]
    }
    """
    result = graph_extractor.parse_extraction_json(sample_json)
    check("parsed 2 entities", len(result.entities) == 2)
    check("entity 0 is Organization", result.entities[0].entity_type == EntityType.ORGANIZATION)
    check("parsed 1 relation", len(result.relations) == 1)
    check("relation is PARTY_TO", result.relations[0].relation_type == RelationType.PARTY_TO)
    check("evidence preserved", "Bluepeak Inc" in result.relations[0].evidence_text)


def test_transactional_storage_ingest():
    print("\n[Transactional Storage Ingest]")
    assert storage.init() is True, "Storage init failed"

    test_brain = f"test_brain_{uuid.uuid4().hex[:8]}"

    entities = [
        ExtractedEntity(
            name="Acme Corp",
            entity_type=EntityType.ORGANIZATION,
            description="Software enterprise",
            aliases=["Acme"],
        ),
        ExtractedEntity(
            name="SEC-REVIEW-01",
            entity_type=EntityType.POLICY,
            description="Security review policy",
            aliases=[],
        ),
    ]
    relations = [
        ExtractedRelation(
            source_entity="Acme Corp",
            target_entity="SEC-REVIEW-01",
            relation_type=RelationType.GOVERNED_BY,
            description="Acme is governed by SEC-REVIEW-01",
            confidence=0.99,
            evidence_text="All Acme entities are governed by SEC-REVIEW-01",
        )
    ]

    # Ingest happy path
    ok, count_e, count_r = storage.ingest_graph_triples(
        brain=test_brain,
        entities=entities,
        relations=relations,
        source_ref_id="ref-12345",
    )
    check("ingest reported success", ok is True)
    check("inserted 2 entities", count_e == 2)
    check("inserted 1 relation", count_r == 1)

    # Verify query
    graph = storage.get_brain_graph(test_brain)
    check("graph contains 2 nodes", len(graph.get("nodes", [])) == 2)
    check("graph contains 1 edge", len(graph.get("edges", [])) == 1)

    # Verify edge has source_reference_ids
    edge = graph["edges"][0]
    check("edge has source_reference_ids", "ref-12345" in edge.get("source_reference_ids", []))
    check("edge has evidence_text", "SEC-REVIEW-01" in edge.get("evidence_text", ""))

    # Verify deletion cascade
    storage.delete_brain_graph(test_brain)
    graph_after = storage.get_brain_graph(test_brain)
    check("deleted brain leaves 0 nodes", len(graph_after.get("nodes", [])) == 0)
    check("deleted brain leaves 0 edges", len(graph_after.get("edges", [])) == 0)


def test_transaction_rollback():
    print("\n[Transactional Rollback on Failure]")
    test_brain = f"rollback_brain_{uuid.uuid4().hex[:8]}"
    entities = [
        ExtractedEntity(name="Transient Corp A", entity_type=EntityType.ORGANIZATION),
        ExtractedEntity(name="Transient Corp B", entity_type=EntityType.ORGANIZATION),
    ]
    # Craft an invalid relation that forces an error during relation processing
    class BrokenRelation:
        source_entity = "Transient Corp A"
        target_entity = "Transient Corp B"
        relation_type = "RELATED_TO"
        description = "Test"
        confidence = "not_a_valid_float_value"  # Triggers ValueError during float() conversion
        evidence_text = ""

    try:
        storage.ingest_graph_triples(
            brain=test_brain,
            entities=entities,
            relations=[BrokenRelation()],
        )
    except Exception:
        pass

    # Verify that the entire transaction rolled back and Transient Corp was NOT persisted
    graph = storage.get_brain_graph(test_brain)
    check("failed ingest leaves 0 entities in db", len(graph.get("nodes", [])) == 0)
    check("failed ingest leaves 0 relations in db", len(graph.get("edges", [])) == 0)


def main():
    test_entity_canonicalization()
    test_extraction_parsing()
    test_transactional_storage_ingest()
    test_transaction_rollback()

    print(f"\nResult: {len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        sys.exit(1)


if __name__ == "__main__":
    main()
