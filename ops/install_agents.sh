#!/usr/bin/env bash
# Install the scheduled ops jobs, in the only way macOS lets them run.
#
#   ops/install_agents.sh      install / refresh both agents
#   ops/install_agents.sh --verify   report what launchd actually says, change nothing
#
# WHY AN INSTALLER INSTEAD OF COMMITTED PLISTS
# launchd cannot read ~/Desktop: the job dies with exit 126 and "Operation not
# permitted" before the script's first line runs. Verified on this machine on both
# the nightly backup and the login stack-up job. So the executable copy has to live
# OUTSIDE the repo, in ~/Library/Application Support/Kestrel, and the plist has to
# point there. Committing a plist with the repo path in it would install a job that
# is guaranteed to fail - which is exactly the bug this replaces.
#
# Consequence worth stating: editing ops/kestrel_nightly_backup.sh does nothing
# until this script is re-run. --verify says whether the installed copy matches.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SUPPORT="$HOME/Library/Application Support/Kestrel"
AGENTS="$HOME/Library/LaunchAgents"
UID_N=$(id -u)

mkdir -p "$SUPPORT" "$AGENTS"; chmod 700 "$SUPPORT"

verify_only=0
[ "${1:-}" = "--verify" ] && verify_only=1

report_agent() {
  local label="$1" out line
  out=$(launchctl print "gui/$UID_N/$label" 2>/dev/null || true)
  if [ -z "$out" ]; then
    echo "  $label: NOT loaded"
    return
  fi
  line=$(printf '%s\n' "$out" | grep -m1 'last exit code' || true)
  case "$line" in
    *'never exited'*) echo "  $label: loaded, has not run yet" ;;
    *'= 0'*)          echo "  $label: loaded, last run OK" ;;
    *)  echo "  $label: loaded, ${line:-no exit code recorded}  <- investigate" ;;
  esac
}

echo "== Kestrel scheduled jobs =="
echo "repo:    $REPO"
echo "runtime: $SUPPORT"
echo

if [ "$verify_only" = "0" ]; then
  install -m 700 "$REPO/ops/kestrel_nightly_backup.sh" "$SUPPORT/kestrel_nightly_backup.sh"

  cat > "$AGENTS/com.kestrel.backup.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.kestrel.backup</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string>
    <string>$SUPPORT/kestrel_nightly_backup.sh</string>
  </array>
  <!-- 03:17 local. If the machine is asleep, launchd runs the missed job on the
       next wake rather than skipping it. -->
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>3</integer>
    <key>Minute</key><integer>17</integer>
  </dict>
  <key>StandardOutPath</key><string>$SUPPORT/launchd.log</string>
  <key>StandardErrorPath</key><string>$SUPPORT/launchd.log</string>
</dict></plist>
PLIST
  plutil -lint "$AGENTS/com.kestrel.backup.plist" >/dev/null

  launchctl bootout "gui/$UID_N/com.kestrel.backup" 2>/dev/null
  launchctl bootstrap "gui/$UID_N" "$AGENTS/com.kestrel.backup.plist" \
    && echo "installed: com.kestrel.backup (nightly 03:17, backups in ~/Kestrel_backups)"
  echo
fi

echo "state:"
report_agent com.kestrel.backup

# The stack-up job is the one this script cannot fix, and pretending otherwise is
# how it stayed broken: report it plainly, with the two real remedies.
if [ -f "$AGENTS/com.kestrel.stackup.plist" ]; then
  if grep -q "Desktop" "$AGENTS/com.kestrel.stackup.plist" 2>/dev/null; then
    echo "  com.kestrel.stackup: points inside the repo (~/Desktop), so launchd"
    echo "    cannot execute it - 'Operation not permitted', exit 126. Left as is."
    echo "    To make self-healing real, one of:"
    echo "      1) grant Full Disk Access to /bin/bash (System Settings > Privacy);"
    echo "      2) move the project out of ~/Desktop (also removes the iCloud-sync"
    echo "         and TCC surprises from the whole stack); or"
    echo "      3) keep healing manual: run ops_stack_up.sh, or trigger it from a"
    echo "         terminal, which already has the permission."
  else
    echo "  com.kestrel.stackup: installed (not pointing inside the repo)"
  fi
fi

echo
if [ -x "$SUPPORT/kestrel_nightly_backup.sh" ]; then
  "$SUPPORT/kestrel_nightly_backup.sh" --status || true
fi
