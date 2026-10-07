"""End-to-End integration test for Native PostgreSQL Knowledge Graph Engine (KNGE).

Tests:
1. Storage graph initialization and demo seeding
2. Ingestion pipeline (entities, relations, provenance)
3. API endpoints: GET /api/graph and GET /api/stats
4. Hybrid GraphRAG retrieval with multi-hop context
5. UI contract compatibility for GraphView.tsx

Run: python3 tests/test_native_graph_e2e.py
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
import graph_extractor
import graph_retriever
from ontology import ExtractedEntity, ExtractedRelation, EntityType, RelationType
from starlette.testclient import TestClient
import app as app_module

PASSED = []
FAILED = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL  {name} - {detail}")


def test_storage_and_seeding():
    print("\n[Storage & Demo Seeding]")
    assert storage.init() is True, "storage.init failed"

    seeded = storage.seed_demo_graph_if_empty("company_brain")
    check("demo graph seeded", seeded > 0, f"seeded count: {seeded}")

    demo_graph = storage.get_brain_graph("company_brain")
    nodes = demo_graph.get("nodes", [])
    edges = demo_graph.get("edges", [])
    check("demo graph has nodes (>= 100)", len(nodes) >= 100, f"node count: {len(nodes)}")
    check("demo graph has edges (>= 150)", len(edges) >= 150, f"edge count: {len(edges)}")


def test_api_endpoints():
    print("\n[API Endpoints: /api/graph & /api/stats]")
    client = TestClient(app_module.app)

    # 1. GET /api/graph for company_brain
    res = client.get("/api/graph?dataset=company_brain")
    check("GET /api/graph returns 200", res.status_code == 200, f"status: {res.status_code}")
    data = res.json()
    check("served from postgres source", data.get("source") == "postgres", f"source: {data.get('source')}")
    check("nodes list present and non-empty", len(data.get("nodes", [])) > 0)
    check("edges list present and non-empty", len(data.get("edges", [])) > 0)

    # 2. Validate GraphView.tsx contract shape
    sample_node = data["nodes"][0]
    check("node has id", "id" in sample_node)
    check("node has label", "label" in sample_node)
    check("node has type", "type" in sample_node)

    sample_edge = data["edges"][0]
    check("edge has source", "source" in sample_edge)
    check("edge has target", "target" in sample_edge)
    check("edge has label", "label" in sample_edge)

    # 3. GET /api/stats for company_brain
    res_stats = client.get("/api/stats?dataset=company_brain")
    check("GET /api/stats returns 200", res_stats.status_code == 200)
    stats_data = res_stats.json()
    check("stats reports ok=True", stats_data.get("ok") is True)
    check("stats node count matches", stats_data.get("nodes", 0) >= 100)
    check("stats edge count matches", stats_data.get("edges", 0) >= 150)


def test_custom_brain_ingest_and_retrieval():
    print("\n[Custom Brain Ingest & Multi-Hop Retrieval]")
    test_brain = f"e2e_brain_{uuid.uuid4().hex[:8]}"

    # Ingest entities and relations
    entities = [
        ExtractedEntity(
            name="Fernwood Technologies",
            entity_type=EntityType.ORGANIZATION,
            description="Enterprise customer",
            aliases=["Fernwood"],
        ),
        ExtractedEntity(
            name="Contract SOW-2026-99",
            entity_type=EntityType.CONTRACT,
            description="Statement of work for deployment",
            aliases=["SOW-2026"],
        ),
        ExtractedEntity(
            name="SLA-Credit-Policy",
            entity_type=EntityType.POLICY,
            description="SLA outage credit policy",
            aliases=["SLA Policy"],
        ),
    ]

    relations = [
        ExtractedRelation(
            source_entity="Fernwood Technologies",
            target_entity="Contract SOW-2026-99",
            relation_type=RelationType.PARTY_TO,
            description="Signed SOW deployment",
            confidence=0.98,
            evidence_text="Fernwood Technologies executes SOW-2026-99 for cloud services.",
        ),
        ExtractedRelation(
            source_entity="Contract SOW-2026-99",
            target_entity="SLA-Credit-Policy",
            relation_type=RelationType.GOVERNED_BY,
            description="SOW incorporates SLA credits",
            confidence=0.95,
            evidence_text="All service outages under this SOW are governed by SLA-Credit-Policy.",
        ),
    ]

    ok, n_ent, n_rel = storage.ingest_graph_triples(
        brain=test_brain,
        entities=entities,
        relations=relations,
        source_ref_id="fernwood_sow.md",
    )
    check("custom brain ingested successfully", ok is True)
    check("inserted 3 entities", n_ent == 3)
    check("inserted 2 relations", n_rel == 2)

    # Test recursive multi-hop retrieval
    ctx, refs = graph_retriever.build_graph_context("Does SLA credit apply to Fernwood?", test_brain, max_depth=2)
    check("retrieval found multi-hop context", bool(ctx))
    check("context connects Fernwood to SLA-Credit-Policy", "Fernwood Technologies" in ctx and "SLA-Credit-Policy" in ctx)
    check("provenance citations captured fernwood_sow.md", "fernwood_sow.md" in refs)

    # Clean up
    storage.delete_brain_graph(test_brain)
    after = storage.get_brain_graph(test_brain)
    check("custom brain wiped cleanly after test", len(after.get("nodes", [])) == 0)


def main():
    test_storage_and_seeding()
    test_api_endpoints()
    test_custom_brain_ingest_and_retrieval()

    print(f"\nResult: {len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        sys.exit(1)


if __name__ == "__main__":
    main()
