#!/usr/bin/env bash
# PR-1 restore drill: restore the latest backup into the ISOLATED lab stack
# (project kestrel_lab) and validate. Originals are read-only here.
set -euo pipefail
cd "$(dirname "$0")/.."
BK="${1:-$(ls -1d var/backups/*/ | sort | tail -1)}"
BK="${BK%/}"
echo "restoring from: $BK"

LAB_PG_PASSWORD=$(grep '^GRAPH_DATABASE_PASSWORD=' .env.oss | cut -d= -f2-)
export LAB_PG_PASSWORD

echo "[1/5] lab postgres up"
docker compose -p kestrel_lab -f compose.lab.yml up -d postgres
until docker exec kestrel-lab-db pg_isready -U kestrel -d kestrel >/dev/null 2>&1; do sleep 2; done

echo "[2/5] restore database (app tables + graph_*)"
# The drill has to prove the dump is RESTORABLE, not just present. Loading it
# into a lab database that already has the schema died on
# `relation "alembic_version" already exists`, which is the same failure any
# real restore would hit: a backup restore goes onto an empty target. Drop the
# lab schema first - the lab is a scratch copy by definition, and this script
# never touches the live database.
docker exec -i kestrel-lab-db psql -U kestrel -d kestrel -v ON_ERROR_STOP=1 -q <<'SQL'
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO kestrel;
SQL
docker exec -i kestrel-lab-db psql -U kestrel -d kestrel -v ON_ERROR_STOP=1 -q < "$BK/db.sql"
echo "      restored; rows: brain_access=$(docker exec kestrel-lab-db psql -U kestrel -d kestrel -tAc 'select count(*) from brain_access') chats=$(docker exec kestrel-lab-db psql -U kestrel -d kestrel -tAc 'select count(*) from chats') graph_node=$(docker exec kestrel-lab-db psql -U kestrel -d kestrel -tAc 'select count(*) from graph_node')"

echo "[3/5] restore cognee volumes (both)"
docker run --rm -v kestrel_lab_kestrel_lab_state:/tgt -v "$PWD/$BK":/src:ro alpine sh -c "cd /tgt && tar xzf /src/cognee-state.tgz"
docker run --rm -v kestrel_lab_kestrel_lab_data:/tgt -v "$PWD/$BK":/src:ro alpine sh -c "cd /tgt && tar xzf /src/cognee-data.tgz"

echo "[4/5] lab cognee (${LAB_COGNEE_IMAGE:-cognee/cognee:1.6.1}) up"
docker compose -p kestrel_lab -f compose.lab.yml up -d cognee
for i in $(seq 1 30); do curl -sf http://localhost:8889/health >/dev/null 2>&1 && break; sleep 2; done
curl -s http://localhost:8889/health | head -c 120; echo
echo "datasets on restored copy:"
curl -sL http://localhost:8889/api/v1/datasets/ | python3 -c "import json,sys; [print('  -', x.get('name'), str(x.get('id'))[:8]) for x in json.load(sys.stdin)]"

echo "[5/5] restore validation gates (app against the COPY only)"
AUTH_MODE=off PORT=8010 \
  DATABASE_URL="postgresql://kestrel:${LAB_PG_PASSWORD}@localhost:5434/kestrel" \
  COGNEE_SERVICE_URL=http://localhost:8889 \
  nohup python3 app.py > var/lab-app.log 2>&1 &
LAB_APP_PID=$!
# The gate below can fail; the lab app must not be left running when it does.
# Without this trap a failed drill silently orphaned a python process on :8010.
trap 'kill '"$LAB_APP_PID"' 2>/dev/null || true' EXIT
for i in $(seq 1 20); do curl -sf http://127.0.0.1:8010/health >/dev/null 2>&1 && break; sleep 2; done
Q=$(python3 -c "import urllib.parse; print(urllib.parse.quote('Why is the Bluepeak renewal at risk, and what have we promised them?'))")
# 240s, not 120: the ask itself takes 23-45s on a healthy brain and longer on a
# freshly restored one, and a truncated stream used to look identical to a broken
# restore. rc is captured so a timeout is reported as what it is.
ASK_RC=0
curl -s --max-time 240 "http://127.0.0.1:8010/api/ask?q=$Q&dataset=company_brain" > var/lab-demo-ask.ndjson || ASK_RC=$?
if [ "$ASK_RC" -ne 0 ]; then
  echo "GATE demo-answer: FAIL (ask request ended rc=$ASK_RC — $([ "$ASK_RC" = 28 ] && echo 'timed out after 240s; the brain never streamed an answer' || echo 'request failed'); see var/lab-app.log)"
fi
if python3 - <<'PYEOF'
import json, os
answer, refs = [], []
for line in (open('var/lab-demo-ask.ndjson') if os.path.exists('var/lab-demo-ask.ndjson') else []):
    line = line.strip()
    if not line: continue
    try: ev = json.loads(line)
    except Exception: continue
    if ev.get('type') == 'chunk': answer.append(ev.get('text',''))
    if ev.get('type') == 'references': refs = ev.get('items') or []
    if ev.get('stage') == 'error': print('ASK ERROR:', ev.get('message'))
text = ''.join(answer)
print(f"GATE demo-answer: {'PASS' if len(text) > 200 else 'FAIL'} ({len(text)} chars, {len(refs)} refs)")
ref0 = (refs[0].get('source') if refs else '')
import urllib.request, urllib.parse
ok = False
if ref0:
    # A source that cannot be opened is the product's core promise broken, so it
    # is a gate - but it must REPORT, not raise: an exception here used to abort
    # the whole drill under `set -e` and print nothing at all.
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:8010/api/source?name={urllib.parse.quote(ref0)}&dataset=company_brain', timeout=30) as r:
            src = json.load(r)
        ok = bool(src.get('ok')) and len(src.get('text','')) > 100
        print(f"GATE source-open:  {'PASS' if ok else 'FAIL'} ({src.get('source')}, {len(src.get('text',''))} chars)")
    except Exception as exc:
        src = {}
        ok = False
        print(f"GATE source-open:  FAIL ({type(exc).__name__}: {str(exc)[:120]})")
else:
    print("GATE source-open:  FAIL (no references)")
raise SystemExit(0 if (len(text) > 200 and ok) else 1)
PYEOF
then
  echo "RESTORE DRILL PASS from $BK — the copy answered and opened its source"
else
  echo "RESTORE DRILL FAIL from $BK — the data restored, the copy could not answer."
  echo "  Read the GATE lines above and var/lab-app.log. A LiteLLM TimeoutError in"
  echo "  the lab cognee logs means the LAB brain has no working LLM endpoint: that"
  echo "  is a lab configuration gap, not proof the backup is unusable - the schema,"
  echo "  rows, volumes and dataset all restored and were queried successfully."
  exit 1
fi
