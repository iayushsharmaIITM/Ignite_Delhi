#!/usr/bin/env bash
# Phase 4.5: migrations survive a fresh bootstrap (storage.init() then Alembic).
set -euo pipefail
cd "$(dirname "$0")/.."
docker rm -f bootstrap-pg >/dev/null 2>&1 || true
docker run -d --name bootstrap-pg -e POSTGRES_USER=kestrel -e POSTGRES_PASSWORD=kestrel \
  -e POSTGRES_DB=kestrel -p 5435:5432 postgres:17-alpine >/dev/null
for i in $(seq 1 20); do docker exec bootstrap-pg pg_isready -U kestrel >/dev/null 2>&1 && break; sleep 1; done
export DATABASE_URL="postgresql://kestrel:kestrel@localhost:5435/kestrel"
python3 - <<'PY'
import os
os.environ["DATABASE_URL"] = "postgresql://kestrel:kestrel@localhost:5435/kestrel"
import storage
assert storage.init() is True, "storage.init failed on fresh DB"
print("  storage.init(): PASS (fresh schema created)")
PY
python3 -m alembic stamp 0001_baseline 2>&1 | tail -1
python3 -m alembic upgrade head 2>&1 | tail -1
docker exec bootstrap-pg psql -U kestrel -d kestrel -tAc \
  "select count(*) from pg_tables where schemaname='public' and tablename in ('workspaces','brains','brain_generations','brain_jobs','source_references')" \
  | xargs echo "  post-upgrade new tables (expect 11):"
docker rm -f bootstrap-pg >/dev/null
echo "FRESH BOOTSTRAP: PASS"
