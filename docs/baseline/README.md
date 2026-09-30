# Phase A — Baseline & Diagnosis Evidence Pack

_Collected 2026-09-30 21:07–21:15 UTC by ZCode. Read-only except: the live app
_tier was stopped for ~3 minutes to run verify.sh (port 8000), then restarted —
_health verified, demo state checksum byte-identical before/after._

## Preservation gates (Addendum §3) — all PASS
| Gate | Result | Evidence |
|---|---|---|
| Behavior: full battery | PASS — documents 25/25, pipe-states 13/13, connectors 90/90, tenants 10/10, smoke 4/4, ui PASS (exit 0) | var/baseline-verify.log (sanitized copy: baseline-verify-summary.txt) |
| Data: demo corpus immutable | PASS — checksum e525486e…599a00 identical before/after | var/demo-state-*.txt |
| Data: known-answer + citation opens | PASS — 1148-char answer, 3 refs, source opens from corpus (1881 chars) | demo-ask-evidence.json |
| Auth: live Clerk mode preserved | PASS — app restarted with provider=cloud auth=ok upstream=ready | this file |
| Connectors: honest unavailable state | PASS — 503 'not configured' captured; connector_credentials stayed 0 | connector-diagnosis.md |
| Ops: live demo preserved | PASS — app running at end of phase, port 8000 | this file |

## Artifacts

## Headline findings
1. Connector blocker root cause CONFIRMED: 1.6.1 image ships /api/v1/integrations/* routes without the google packages (pip count = 0); authorize → 503. Fix = derived image with COGNEE_EXTRAS (PR-2).
2. Storage topology CORRECTED: graph lives in Postgres (graph_node=93, graph_edge=161 in kestrel-db) per GRAPH_DATABASE_* env — not Kuzu-in-container. Backup design = one pg_dump + two Cognee mounts.
3. Reconciliation drift LIVE: tenant=1 dataset (company_brain); brain_access=2 (company_brain, acme_isolated); uploads.json=10 keys/13 entries — all stale (deleted test brains); 2 chats reference nonexistent brains (hghi, kestrel_full). No repair performed — backfill phase.
4. Env hygiene: 5 duplicate key names in .env.oss (LLM_PROVIDER/MODEL/ENDPOINT/API_KEY/RATE_LIMIT_REQUESTS) — last-block-wins is live (#6/N15).
5. Artifact provenance: container self-reports 1.6.1-local; digests pinned in runtime.md. 1.6.2 tag EXISTS in registry (amd64+arm64).
6. Version drift: runtime fastapi 0.115.0 vs requirements.txt 0.141.1 (app runs system python3.13, no venv). Record-only.
7. llm_calls metering by feature:
- ask = 197