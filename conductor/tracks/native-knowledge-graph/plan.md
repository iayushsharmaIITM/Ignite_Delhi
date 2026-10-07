# Implementation Plan: Native PostgreSQL Knowledge Graph & GraphRAG Engine

## Phase 1: Database Schema & Migration Foundation
- [x] Task 1.1: Design domain ontology models (`ontology.py`) with Pydantic schemas.
- [x] Task 1.2: Author idempotent Alembic migration `0007_native_knowledge_graph.py` adding `kg_entities`, `kg_relations`, and `kg_communities`.
- [x] Task 1.3: Update `storage.init()` DDL for fresh bootstraps to maintain dual-authority schema invariant.
- [x] Task 1.4: Verify fresh bootstrap with `./ops/test_fresh_bootstrap.sh`.

## Phase 2: Structured Extraction & Transactional Ingest Pipeline
- [x] Task 2.1: Implement `graph_extractor.py` for Pydantic-based entity and relation extraction from text chunks.
- [x] Task 2.2: Implement canonical entity deduplication (fuzzy match + alias resolution).
- [x] Task 2.3: Implement transactional ingest in `storage.py` that writes chunks, entities, and edges atomically.
- [x] Task 2.4: Write unit & integration tests (`tests/test_native_graph_ingest.py`) testing happy-path ingest and rollback on failure.

## Phase 3: Recursive CTE Graph Retrieval & Deterministic Citations
- [x] Task 3.1: Implement `graph_retriever.py` with PostgreSQL recursive CTEs for $k$-hop neighborhood expansion.
- [x] Task 3.2: Connect graph traversal directly to `source_references` for 100% verified citation generation.
- [x] Task 3.3: Implement community clustering and summary synthesis for global corpus questions.
- [x] Task 3.4: Write retrieval tests (`tests/test_native_graph_retrieval.py`) proving multi-hop reasoning and citation accuracy.

## Phase 4: API Adapter & Deprecation of Cognee Tier
- [x] Task 4.1: Adapt `GET /api/graph` in `app.py` to serve nodes and edges directly from `kg_entities` and `kg_relations`.
- [ ] Task 4.2: Update orchestrator retrieval ladder to use native graph retrieval when enabled.
- [ ] Task 4.3: Deprecate `cognee_cloud.py` and remove Cognee container from `compose.oss.yml` (staged for cutover).
- [x] Task 4.4: Run full battery `./verify.sh` and ensure all tiers are green.
