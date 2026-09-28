#!/bin/bash
# Kestrel self-healing stack startup — runs at login (LaunchAgent).
# Idempotent: every step checks before acting. Safe to run any time.
LOG=/tmp/kestrel_stackup.log
{
echo "=== stack up $(date) ==="
colima list 2>/dev/null | grep -q "default.*Running" || { echo "starting colima"; colima start; }
docker compose -f "$(dirname "$0")/compose.oss.yml" up -d 2>>$LOG
# wait briefly for the brain to go healthy (it gates the demo)
for i in $(seq 1 24); do
  S=$(docker inspect cognee-oss --format '{{.State.Health.Status}}' 2>/dev/null)
  [ "$S" = "healthy" ] && break
  sleep 5
done
echo "cognee: $S"
lsof -nP -iTCP:8000 -sTCP:LISTEN -t >/dev/null 2>&1 || {
  echo "starting app"; cd "$(dirname "$0")" && nohup python3 app.py > /tmp/kestrel_app.log 2>&1 & sleep 5
}
curl -s -m 5 http://127.0.0.1:8000/health >/dev/null && echo "app: up" || echo "app: DOWN"
} >> "$LOG" 2>&1
