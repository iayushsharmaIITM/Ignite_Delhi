#!/usr/bin/env bash
# PR-1: consistent local backup of the Kestrel stack (copies only — reads
# every source, writes only to var/backups/<ts>/). Originals are never
# touched. Key recovery material (env files) is copied with 0600 perms; the
# directory is gitignored.
set -euo pipefail
cd "$(dirname "$0")/.."
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="var/backups/$TS"
mkdir -p "$OUT"

echo "[1/5] Postgres (app tables + graph_* in ONE consistent dump)…"
docker exec kestrel-db pg_dump -U kestrel -d kestrel > "$OUT/db.sql"
echo "      $(wc -l < "$OUT/db.sql") lines"

echo "[2/5] Cognee mounts (both, per the 28 Sep lesson)…"
docker run --rm -v kestrel_brains_cognee_oss_state:/src:ro -v "$PWD/$OUT":/out alpine \
  tar czf /out/cognee-state.tgz -C /src . 
docker run --rm -v kestrel_brains_cognee_oss_data:/src:ro -v "$PWD/$OUT":/out alpine \
  tar czf /out/cognee-data.tgz -C /src .

echo "[3/5] Citation manifest…"
cp cognee_oss_state/uploads.json "$OUT/uploads.json"

echo "[4/5] Key recovery material (local only, 0600)…"
cp .env "$OUT/env.app" 2>/dev/null || echo "      (no .env)"
cp .env.oss "$OUT/env.oss" 2>/dev/null || echo "      (no .env.oss)"
chmod 600 "$OUT"/env.* 2>/dev/null || true

echo "[5/5] Integrity manifest…"
( cd "$OUT" && shasum -a 256 * | sort > SHA256SUMS )
docker exec cognee-oss sh -c 'cd / && find /app/.cognee /cognee-storage -type f | sort | xargs sha256sum 2>/dev/null | sha256sum' \
  | awk '{print "live-state-checksum: " $1}' > "$OUT/LIVE_STATE_CHECKSUM.txt"
ls -la "$OUT" | tail -n +2

# --- retention ---------------------------------------------------------------
# A backup scheme nobody prunes turns into a full disk, and a full disk is how
# backups stop quietly. Keep the newest KESTREL_BACKUP_KEEP (default 14) and
# delete only timestamp-shaped directories under var/backups - the guard below
# aborts rather than rm-ing anything if the working directory is not that path.
KEEP="${KESTREL_BACKUP_KEEP:-14}"
# The script already cd'd to the repo root, so this is <root>/var/backups.
cd var/backups || { echo "retention: no var/backups directory - nothing to prune"; exit 0; }
case "$(pwd)" in
  */Kestrel_brains/var/backups) : ;;
  *) echo "RETENTION ABORT: not inside var/backups (got $(pwd)) - nothing deleted"; exit 1 ;;
esac
TOTAL=$(ls -1d */ 2>/dev/null | wc -l | tr -d ' ')
echo "retention: $TOTAL backup(s) present, keeping the newest $KEEP"
if [ "$TOTAL" -gt "$KEEP" ]; then
  ls -1d */ | head -n "$((TOTAL - KEEP))" | while read -r d; do
    case "$d" in
      *[0-9]T*[0-9]Z/) rm -rf -- "$d" && echo "      pruned $d" ;;
      *) echo "      kept (unexpected name, not touching): $d" ;;
    esac
  done
fi

echo "BACKUP OK: $OUT"
