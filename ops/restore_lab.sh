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
for i in $(seq 1 20); do curl -sf http://127.0.0.1:8010/health >/dev/null 2>&1 && break; sleep 2; done
Q=$(python3 -c "import urllib.parse; print(urllib.parse.quote('Why is the Bluepeak renewal at risk, and what have we promised them?'))")
curl -s --max-time 120 "http://127.0.0.1:8010/api/ask?q=$Q&dataset=company_brain" > var/lab-demo-ask.ndjson
python3 - <<'PYEOF'
import json
answer, refs = [], []
for line in open('var/lab-demo-ask.ndjson'):
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
    with urllib.request.urlopen(f'http://127.0.0.1:8010/api/source?name={urllib.parse.quote(ref0)}&dataset=company_brain', timeout=30) as r:
        src = json.load(r)
    ok = bool(src.get('ok')) and len(src.get('text','')) > 100
    print(f"GATE source-open:  {'PASS' if ok else 'FAIL'} ({src.get('source')}, {len(src.get('text',''))} chars)")
else:
    print("GATE source-open:  FAIL (no references)")
PYEOF
kill $LAB_APP_PID 2>/dev/null
echo "RESTORE DRILL COMPLETE from $BK"
