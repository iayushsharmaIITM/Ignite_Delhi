# Track Spec: Native PostgreSQL Knowledge Graph & GraphRAG Engine

## Context & Objectives
Replace the external Cognee OSS container (`:8888`) with a high-performance, deterministic **Native Knowledge Graph Engine (KNGE)** built directly inside Kestrel's FastAPI and PostgreSQL 17 stack.

## Core Requirements
1. **Schema-Constrained Entity & Relation Extraction:**
   - Use structured LLM outputs (Pydantic models) to extract domain entities and relations instead of open-ended string generation.
   - Core entity types: `Organization`, `Person`, `Contract`, `Policy`, `System`, `Deliverable`, `Risk`, `Obligation`.
   - Core relation types: `GOVERNED_BY`, `PARTY_TO`, `MANAGES`, `OWNS`, `PROCESSES_DATA`, `SUPERSEDES`, `REPORTS_TO`.
2. **100% Deterministic Provenance:**
   - Every graph relation stores foreign-key links to `source_references` (`backend_chunk_id`, `char_start`, `char_end`, `page`).
   - When answers traverse the knowledge graph, citations link directly to the underlying document chunks with zero fingerprint guessing or regex parsing.
3. **Transactional Ingestion & Rollback:**
   - Document chunks, entities, and relations are written in a database transaction.
   - If an ingestion fails, the transaction rolls back cleanly, leaving zero orphaned records.
4. **Sub-5ms Graph Traversal:**
   - Local 1- to 3-hop graph neighborhood expansion executed natively via PostgreSQL recursive CTEs.
5. **Seamless UI Compatibility:**
   - `/api/graph` returns standard `{nodes, edges}` JSON matching `GraphView.tsx` with zero frontend regressions.

## Acceptance Criteria
- [ ] Schema migration `0007_native_knowledge_graph.py` adds `kg_entities`, `kg_relations`, `kg_communities` with full composite FKs and cascade constraints.
- [ ] Test suite verifies structured extraction, entity deduplication, and atomic rollback on failure.
- [ ] Test suite verifies multi-hop recursive CTE graph walk and exact chunk citation generation.
- [ ] `./ops/test_fresh_bootstrap.sh` passes on port 5435.
- [ ] `/api/graph` serves nodes and edges from PostgreSQL with sub-10ms response time.
- [ ] `./verify.sh --quick` passes all tiers with 0 failures.
