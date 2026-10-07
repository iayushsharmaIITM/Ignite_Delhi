"""Tests for Native Knowledge Graph recursive CTE retrieval and deterministic grounding.

Run: python3 tests/test_native_graph_retrieval.py
"""

from __future__ import annotations

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
from ontology import EntityType, ExtractedEntity, ExtractedRelation, RelationType
import graph_retriever

PASSED = []
FAILED = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL  {name} - {detail}")


def test_retrieval_and_recursive_walk():
    print("\n[Native Graph Recursive Retrieval]")
    assert storage.init() is True, "Storage init failed"

    test_brain = f"retrieval_brain_{uuid.uuid4().hex[:8]}"

    # Setup a 3-node chain: Bluepeak -> MSA -> SOC 2 Policy
    e_bluepeak = ExtractedEntity(
        name="Bluepeak Inc",
        entity_type=EntityType.ORGANIZATION,
        description="Enterprise client",
        aliases=["Bluepeak"],
    )
    e_msa = ExtractedEntity(
        name="MSA-2025-0114",
        entity_type=EntityType.CONTRACT,
        description="Master Services Agreement",
        aliases=["MSA"],
    )
    e_sec = ExtractedEntity(
        name="SEC-REVIEW-01",
        entity_type=EntityType.POLICY,
        description="Security review requirements",
        aliases=["Security Policy"],
    )

    r1 = ExtractedRelation(
        source_entity="Bluepeak Inc",
        target_entity="MSA-2025-0114",
        relation_type=RelationType.PARTY_TO,
        description="Party to MSA",
        confidence=0.99,
        evidence_text="Bluepeak Inc agrees to the terms of MSA-2025-0114.",
    )
    r2 = ExtractedRelation(
        source_entity="MSA-2025-0114",
        target_entity="SEC-REVIEW-01",
        relation_type=RelationType.GOVERNED_BY,
        description="MSA governed by Security Review Policy",
        confidence=0.95,
        evidence_text="MSA clause 6.1 stipulates adherence to SEC-REVIEW-01.",
    )

    # Ingest chain into DB
    storage.ingest_graph_triples(
        brain=test_brain,
        entities=[e_bluepeak, e_msa],
        relations=[r1],
        source_ref_id="doc1-chunk1",
    )
    storage.ingest_graph_triples(
        brain=test_brain,
        entities=[e_msa, e_sec],
        relations=[r2],
        source_ref_id="doc1-chunk6",
    )

    # 1. Test Seed Entity Lookup
    seeds = graph_retriever.find_seed_entities("Tell me about Bluepeak contract", test_brain)
    check("found Bluepeak as seed", len(seeds) >= 1)
    check("seed name is Bluepeak Inc", any(s["name"] == "Bluepeak Inc" for s in seeds))

    # 2. Test 1-hop neighborhood traversal
    bluepeak_id = next(s["id"] for s in seeds if s["name"] == "Bluepeak Inc")
    one_hop = graph_retriever.traverse_graph_neighborhood([bluepeak_id], test_brain, max_depth=1)
    check("1-hop finds 1 relation", len(one_hop) == 1)
    check("1-hop connects Bluepeak to MSA", one_hop[0]["relation_type"] == "PARTY_TO")
    check("1-hop carries doc1-chunk1 ref", "doc1-chunk1" in one_hop[0].get("source_reference_ids", []))

    # 3. Test 2-hop recursive CTE neighborhood traversal
    two_hop = graph_retriever.traverse_graph_neighborhood([bluepeak_id], test_brain, max_depth=2)
    check("2-hop finds 2 relations", len(two_hop) == 2)
    rel_types = {r["relation_type"] for r in two_hop}
    check("2-hop reaches both PARTY_TO and GOVERNED_BY", rel_types == {"PARTY_TO", "GOVERNED_BY"})

    # 4. Test formatted context and deterministic citations
    ctx_text, cited_refs = graph_retriever.build_graph_context("What governs Bluepeak?", test_brain, max_depth=2)
    check("context contains Bluepeak", "Bluepeak Inc" in ctx_text)
    check("context contains SEC-REVIEW-01", "SEC-REVIEW-01" in ctx_text)
    check("cited refs contains doc1-chunk1", "doc1-chunk1" in cited_refs)
    check("cited refs contains doc1-chunk6", "doc1-chunk6" in cited_refs)

    # Cleanup
    storage.delete_brain_graph(test_brain)


def main():
    test_retrieval_and_recursive_walk()
    print(f"\nResult: {len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        sys.exit(1)


if __name__ == "__main__":
    main()
