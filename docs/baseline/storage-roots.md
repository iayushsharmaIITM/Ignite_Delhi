# Storage-root inventory (A10) — 2026-09-30T21:09Z

## Cognee mounts (named volumes)
- 96K	/app/.cognee
- 16M	/cognee-storage

## Bind-mounted patches (must survive image upgrade — PR-2 hash gate)
- /var/lib/docker/volumes/kestrel_brains_cognee_oss_data/_data -> /cognee-storage (rw)
- /Users/_iayushsharma_/Desktop/Kestrel_brains/patches/native_adapter.py -> /app/cognee/infrastructure/llm/structured_output_framework/litellm_native/native_adapter.py (ro)
- /Users/_iayushsharma_/Desktop/Kestrel_brains/patches/stream_completion.py -> /app/cognee/infrastructure/llm/streaming/stream_completion.py (ro)
- /var/lib/docker/volumes/kestrel_brains_cognee_oss_state/_data -> /app/.cognee (rw)

## Graph storage reality (N15 correction)
- GRAPH_DATABASE_* keys present in .env.oss; graph_node/graph_edge/graph_metadata live in kestrel-db (Postgres), NOT a Kuzu file in the container.
- LanceDB/vector + relational caches: inside the container mounts above.

## manifest
- uploads.json dataset keys (10):
  - 100_people (1 entries)
  - _collisions (0 entries)
  - acme_industrial (2 entries)
  - appendtest1 (3 entries)
  - deltest1 (1 entries)
  - hghi (1 entries)
  - namedcite1 (1 entries)
  - new_100_people (1 entries)
  - paytm_ai (2 entries)
  - ux_scratch_del (1 entries)
- total entries: 13
