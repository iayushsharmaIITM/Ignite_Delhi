# Kestrel Product Context

## Vision
Kestrel is a high-assurance, enterprise-grade AI knowledge workspace. Users organize internal documents, policies, contracts, and transcripts into collections called "brains". Users ask plain-language questions and receive fast, streamed answers grounded in verifiable, 100% checkable citations that open the exact source document and verbatim excerpt.

## Non-Negotiable Invariants
1. **Zero Fabricated Citations:** Every cited source must resolve to an exact document and verified excerpt. No fuzzy guessing, no hallucinated source links.
2. **Deterministic Provenance:** All knowledge graph nodes, edges, and vector chunks are bi-directionally grounded to specific document versions, character offsets, and content hashes.
3. **No Semantic Caching on the Citation Path:** Ever.
4. **Storage Outages Surface Honestly:** Storage failures surface as 503 Service Unavailable, never as silent empty results.
5. **Multi-Tenant Isolation:** Workspaces and brains are strictly isolated by identity and organization ID.
