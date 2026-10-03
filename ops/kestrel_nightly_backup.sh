#!/usr/bin/env bash
# Nightly Kestrel backup that actually survives macOS.
#
#   kestrel_nightly_backup.sh            take a backup
#   kestrel_nightly_backup.sh --status   print OK / FAIL / STALE and exit non-zero
#
# WHY THIS FILE LIVES OUTSIDE THE REPO WHEN IT RUNS
# launchd agents cannot read ~/Desktop at all: macOS denies it, and the job dies
# with exit 126 and "Operation not permitted" on the very first line. That is how
# the nightly backup and the login stack-up job were both silently broken. So the
# installed copy of this script runs from ~/Library/Application Support/Kestrel,
# writes to ~/Kestrel_backups, and reads NOTHING inside ~/Desktop - only docker.
# That also means a deleted working tree no longer takes the backups with it.
#
# Install with: ops/install_agents.sh   (it copies this file and the plists into
# place; editing this file without re-running the installer changes nothing).
set -uo pipefail

# launchd hands jobs a minimal PATH. docker and colima live in /opt/homebrew/bin
# on Apple Silicon (or /usr/local/bin), so without this the job reports
# "docker-daemon" failure on a machine where docker works perfectly from a
# terminal - a failure that looks like an outage and is really a search path.
PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"
export PATH

DEST_ROOT="${KESTREL_BACKUP_DIR:-$HOME/Kestrel_backups}"
KEEP="${KESTREL_BACKUP_KEEP:-14}"
STATUS="$DEST_ROOT/backup.status"
LOG="$DEST_ROOT/backup.log"
DB_CONTAINER="${KESTREL_DB_CONTAINER:-kestrel-db}"
STATE_VOLUME="${KESTREL_STATE_VOLUME:-kestrel_brains_cognee_oss_state}"
DATA_VOLUME="${KESTREL_DATA_VOLUME:-kestrel_brains_cognee_oss_data}"

mkdir -p "$DEST_ROOT"
chmod 700 "$DEST_ROOT"

if [ "${1:-}" = "--status" ]; then
  if [ ! -f "$STATUS" ]; then
    echo "STALE  no backup has ever been taken by this job ($STATUS missing)"
    exit 1
  fi
  line=$(cat "$STATUS")
  stamp=${line#* }
  # The receipt is written in UTC and `date -j -f` parses as LOCAL time unless
  # told otherwise - without the TZ override a fresh backup looked 5.5h old on
  # an IST machine, which is the difference between "OK" and a false alarm.
  when=$(TZ=UTC date -j -f "%Y-%m-%dT%H:%M:%SZ" "${stamp%% *}" +%s 2>/dev/null || echo 0)
  age_h=$(( ( $(date +%s) - when ) / 3600 ))
  case "$line" in
    OK*)
      if [ "$age_h" -gt 36 ]; then
        echo "STALE  last good backup is ${age_h}h old (>36h). $line"
        exit 1
      fi
      echo "OK     last good backup ${age_h}h ago. $line"
      exit 0 ;;
    *)  echo "FAIL   $line (${age_h}h ago)"; exit 1 ;;
  esac
fi

TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$DEST_ROOT/$TS"
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

run() {   # run <step> <cmd...> — one failure marks the whole run FAIL, loudly
  # Status goes to STDERR on purpose: callers redirect stdout into the dump file,
  # and an "ok" note printed into db.sql corrupts the backup. It happened; the
  # terminator check below is what catches it if it ever can again.
  local label="$1"; shift
  if ! "$@"; then
    echo "FAIL $NOW step=$label" > "$STATUS"
    echo "backup FAILED at: $label" >&2
    return 1
  fi
  echo "  ok: $label" >&2
}

echo "=== backup $TS -> $OUT ==="
mkdir -p "$OUT" || exit 1

# The daemon must be up for any of this to work; say so instead of blaming each
# step for the same cause.
if ! docker ps >/dev/null 2>&1; then
  echo "FAIL $NOW step=docker-daemon" > "$STATUS"
  echo "docker is not reachable - is colima up? (colima start)"
  exit 1
fi

run "pg_dump" docker exec "$DB_CONTAINER" pg_dump -U kestrel -d kestrel > "$OUT/db.sql"
run "state-volume" docker run --rm -v "$STATE_VOLUME:/src:ro" -v "$OUT":/out alpine \
  tar cf /out/cognee-state.tar -C /src .
run "data-volume" docker run --rm -v "$DATA_VOLUME:/src:ro" -v "$OUT":/out alpine \
  tar cf /out/cognee-data.tar -C /src .
# The dump and tars are worthless if they cannot be read back, so the last steps
# inspect the artefacts instead of trusting that a command exited 0: the archive
# must list, and the dump must END with pg_dump's own terminator — a truncated or
# polluted dump "succeeds" at write time and only fails on the day it is needed.
run "verify-archives" tar tf "$OUT/cognee-state.tar" >/dev/null 2>&1
run "verify-dump" sh -c "tail -3 '$OUT/db.sql' | grep -q 'PostgreSQL database dump complete'"

( cd "$OUT" && shasum -a 256 * | sort > SHA256SUMS )

SIZE=$(du -sh "$OUT" | cut -f1)
echo "OK $NOW size=$SIZE path=$OUT" > "$STATUS"

# retention — newest $KEEP only, and never anything whose name is not a
# timestamp, so a stray directory in the backup root cannot be deleted here
TOTAL=$(ls -1d "$DEST_ROOT"/*/ 2>/dev/null | wc -l | tr -d ' ')
if [ "${TOTAL:-0}" -gt "$KEEP" ]; then
  ls -1d "$DEST_ROOT"/*/ | head -n "$((TOTAL - KEEP))" | while read -r d; do
    case "$d" in
      *"/"[0-9]"T"[0-9]*Z/) rm -rf -- "$d" && echo "  pruned $(basename "$d")" ;;
    esac
  done
fi

{ echo "=== $NOW OK $SIZE ==="; } >> "$LOG"
tail -c 100000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
echo "BACKUP OK: $OUT ($SIZE)"
