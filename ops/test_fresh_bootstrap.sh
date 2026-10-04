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
# Assert the schema, do not describe it. This line used to `xargs echo` a count
# under the label "expect 11" while the query behind it named five tables, so the
# script printed PASS whether the upgrade produced seventeen tables or none — and
# AGENTS.md routes every schema change here for proof. Compare against the named
# set instead: storage.init()'s five DDL tables plus everything 0002-0006 create.
# Counting would also pass on a wrong set of the same size.
EXPECTED="brain_access brain_generations brain_grants brain_job_events brain_job_files brain_job_staging brain_jobs brains chats deleted_chats document_versions documents generation_documents llm_calls source_references turns workspaces"
ACTUAL=$(docker exec bootstrap-pg psql -U kestrel -d kestrel -tAc \
  "select tablename from pg_tables where schemaname='public' order by 1")
MISSING=""
for t in $EXPECTED; do
  echo "$ACTUAL" | grep -qx "$t" || MISSING="$MISSING $t"
done
echo "  tables present: $(echo "$ACTUAL" | grep -c .) of $(echo $EXPECTED | wc -w | tr -d ' ') expected"
if [ -n "$MISSING" ]; then
  echo "  MISSING after upgrade:$MISSING"
  docker rm -f bootstrap-pg >/dev/null
  echo "FRESH BOOTSTRAP: FAIL"
  exit 1
fi
docker rm -f bootstrap-pg >/dev/null
echo "FRESH BOOTSTRAP: PASS"
