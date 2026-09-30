#!/usr/bin/env bash
# PR-8 cutover gate script — EXECUTABLE preconditions and postconditions.
# Every check exits nonzero on failure. This script STOPS at the unlock gate:
# remove the UNLOCKED sentinel check (or create ops/.cutover_unlocked) only
# after the founder approves and Phases 0-5 evidence exists.
set -uo pipefail
cd "$(dirname "$0")/.."
FAIL=0
ck() { # ck "label" cmd...
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "  PASS  $label"; else echo "  FAIL  $label"; FAIL=1; fi
}

echo "== cutover preconditions =="
ck "founder unlock sentinel exists" test -f ops/.cutover_unlocked
ck "backup newer than 2h" bash -c '[ -n "$(ls -t var/backups/*/db.sql 2>/dev/null | head -1)" ] && [ $(( $(date +%s) - $(stat -f %m "$(ls -t var/backups/*/db.sql | head -1)") )) -lt 7200 ]'
ck "backup checksums present" bash -c 'B=$(ls -td var/backups/*/ | head -1); test -f "$B/SHA256SUMS"'
ck "candidate image present" docker image inspect kestrel-cognee:1.6.2-candidate >/dev/null
ck "candidate digest recorded" grep -q "9afe3416a2df" docs/baseline/runtime.md docs/*.md var/evidence/* 2>/dev/null
ck "ENABLE_BACKEND_ACCESS_CONTROL pinned in .env.oss" grep -q "^ENABLE_BACKEND_ACCESS_CONTROL=false" .env.oss
ck "live app healthy" curl -sf --max-time 5 http://127.0.0.1:8000/health >/dev/null
ck "live tenant has company_brain" bash -c 'curl -sL --max-time 10 http://localhost:8888/api/v1/datasets/ | grep -q company_brain'
ck "pagination contract marker" bash -c 'grep -rq "PAGINATION CONTRACT .* PASS" var/ docs/ 2>/dev/null'
ck "v2 happy path SUCCEEDED marker" bash -c 'grep -rq "V2 HAPPY PATH .* PASS" var/evidence/ docs/ 2>/dev/null'
ck "lease-recovery tests pass marker" bash -c 'grep -rq "PHASE 1 LEASE RECOVERY: PASS" var/ docs/ 2>/dev/null'
[ "$FAIL" -eq 0 ] || { echo "PRECONDITIONS FAILED — cutover refused"; exit 1; }

echo "== executing switch =="
docker exec cognee-oss sh -c 'cd / && find /app/.cognee /cognee-storage -type f | sort | xargs sha256sum 2>/dev/null | sha256sum' | tee var/cutover-pre-checksum.txt
lsof -nP -iTCP:8000 -sTCP:LISTEN -t | xargs kill 2>/dev/null; sleep 2
docker compose -f compose.oss.yml stop cognee-oss
LAB_PG_PASSWORD=x docker compose -f compose.cutover.yml -p kestrel_brains up -d cognee-oss 2>&1 | tail -1
for i in $(seq 1 60); do curl -sf http://localhost:8888/health >/dev/null 2>&1 && break; sleep 3; done
echo "== postconditions =="
ck "candidate health ready" bash -c 'curl -s --max-time 5 http://localhost:8888/health | grep -q "\"ready\""'
ck "datasets survived" bash -c 'curl -sL --max-time 10 http://localhost:8888/api/v1/datasets/ | grep -q company_brain'
(nohup python3 app.py > /tmp/kestrel_app.log 2>&1 &); sleep 7
ck "app healthy post-switch" curl -sf --max-time 5 http://127.0.0.1:8000/health >/dev/null
echo "NOW RUN MANUALLY: known-answer ask + source-open + count reconciliation,"
echo "then record digests. On ANY failure: ROLLBACK per ops/rollback_drill.sh."
exit "$FAIL"
