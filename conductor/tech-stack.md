# Kestrel Technical Stack

## Backend
- **Framework:** FastAPI (Python 3.11+)
- **Primary Database:** PostgreSQL 17 (`pgvector`, JSONB, composite FKs)
- **Migrations:** Alembic
- **Task & Job Execution:** Asyncio worker threads + transactional job queue (`brain_jobs`)
- **Identity & Auth:** Clerk session JWT verification (JWKS fail-closed) + tenant key mode
- **LLM & Vision:** Multi-provider gateway (Token Harbor, OpenRouter, Apple Vision local)

## Frontend
- **Framework:** React 19 + TypeScript + Vite
- **Styling:** Tailwind CSS v4 + bespoke design system (`DESIGN.md`)
- **Components:** Radix UI / shadcn/ui primitives
- **Graph Visualization:** Bespoke Canvas/SVG progressive force simulation (`GraphView.tsx`)

## Knowledge Graph & Search
- **Data Model:** Labeled Property Graph (LPG) backed natively by PostgreSQL 17
- **Retrieval:** Hybrid GraphRAG (local entity neighborhood traversal via recursive CTEs + vector chunk similarity + global community summaries)
- **Deprecation Target:** Cognee OSS container (`:8888`) and LiteLLM patches
