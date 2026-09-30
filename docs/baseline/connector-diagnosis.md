# Connector diagnosis — Cognee 1.6.1 container (A7, 2026-09-30T21:10Z)

## Package check (the cause)
```
google_* packages installed:  0
```
- The 9 /api/v1/integrations/* routes ARE present in the image (openapi.json probe).
- Packages absent → any sync after authorize raises ImportError. Confirms Addendum A.1(1) ASSUMPTION.

## Reproduced authorization failure (no data altered)
```
GET /api/v1/integrations/status:
```
{"integrations":[{"provider":"github","connected":false,"accountLabel":null,"providerAccountId":null,"connectedAt":null,"syncStatus":null,"lastSyncedAt":null,"syncCounts":null},{"provider":"gmail","connected":false,"accountLabel":null,"providerAccountId":null,"connectedAt":null,"syncStatus":null,"lastSyncedAt":null,"syncCounts":null},{"provider":"google_drive","connected":false,"accountLabel":null
```

POST /api/v1/integrations/google_drive/authorize (no GOOGLE_* configured — expect 503 per changelog):
```
{"detail":"google_drive integration is not configured on this server."}
HTTP 503
```

## ZCode failure classification (spec §3)
- Stage: dependency/import (packages missing from published image). NOT a build failure, auth failure, or Kestrel ownership issue.
- Fix path: derived image with COGNEE_EXTRAS (PR-2); runtime pip install rejected (lost on recreate).
- No state was created: a 503 at authorize creates no connection records (verified: connector_credentials=0, slack_workspaces=4 pre-existing, unchanged).
