#!/usr/bin/env bash
# The single battery entrypoint (BUILD_PLAN.md section 2.2).
#
#   ./verify.sh           full battery, including the browser UI smoke test
#   ./verify.sh --quick   skip check_ui.py (no browser / CI boxes)
#
# Exit 0 = every suite green. The app tier is started here with PROVIDER=mock
# forced, so the battery never depends on the Cognee tenant being up. An env
# var beats .env (load_dotenv does not override), so the tenant config in
# .env is ignored for the duration of the run.
#
# Suites run via their own documented entrypoints (standalone scripts), NOT
# pytest: pytest collects only 2 of test_pipeline_states.py's 13 checks and
# none of test_tenants.py's 10.
#
# Suite logs land in /tmp/kestrel_verify_*.log — a FAIL line points at one.

set -uo pipefail
cd "$(dirname "$0")"

QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1

export PROVIDER=mock
export AUTH_MODE=off   # the battery tests the product unauthenticated
BASE="http://127.0.0.1:8000"
SERVER_PID=""
FAILS=0

note() { echo "[$1] $2"; }

cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
}
trap cleanup EXIT

# The battery starts its own mock server, so it must own port 8000. A server
# left running from a dev session would silently answer with the CLOUD
# provider (its own env), which would make the battery lie about mock mode.
if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "ABORT: something is already listening on port 8000 — stop it and rerun."
  exit 2
fi

echo "== Kestrel verification battery (PROVIDER=mock) =="

# --- 1. document extraction (no server needed) ------------------------------
if python3 test_documents.py > /tmp/kestrel_verify_docs.log 2>&1; then
  note documents "PASS  25/25"
else
  note documents "FAIL — see /tmp/kestrel_verify_docs.log"
  FAILS=$((FAILS + 1))
fi

# --- 2. pipeline terminal states (unit test, no server needed) --------------
if python3 test_pipeline_states.py > /tmp/kestrel_verify_pipe.log 2>&1; then
  note pipe-states "PASS  13/13"
else
  note pipe-states "FAIL — see /tmp/kestrel_verify_pipe.log"
  FAILS=$((FAILS + 1))
fi

# --- start the mock server once, for tenants + smoke + UI --------------------
python3 app.py > /tmp/kestrel_verify_server.log 2>&1 &
SERVER_PID=$!
up=""
for _ in $(seq 1 30); do
  if curl -sf "$BASE/health" >/dev/null 2>&1; then up=1; break; fi
  sleep 1
done
if [ -z "$up" ]; then
  note server "FAIL — mock server did not come up; see /tmp/kestrel_verify_server.log"
  exit 1
fi
note server "up (pid $SERVER_PID, mock fixtures)"

# --- 3. tenant isolation (live-server test; config written + restored) ------
if python3 test_tenants.py --with-tenants > /tmp/kestrel_verify_tenants.log 2>&1; then
  note tenants "PASS  10/10"
else
  note tenants "FAIL — see /tmp/kestrel_verify_tenants.log"
  FAILS=$((FAILS + 1))
fi

# --- 4. web-tier smoke -------------------------------------------------------
if python3 smoke.py > /tmp/kestrel_verify_smoke.log 2>&1; then
  note smoke "PASS  4/4"
else
  note smoke "FAIL — see /tmp/kestrel_verify_smoke.log"
  FAILS=$((FAILS + 1))
fi

# --- 5. UI smoke --------------------------------------------------------------
if [ "$QUICK" -eq 1 ]; then
  note ui "SKIP  (--quick)"
else
  if python3 check_ui.py > /tmp/kestrel_verify_ui.log 2>&1; then
    note ui "PASS"
  else
    note ui "FAIL — see /tmp/kestrel_verify_ui.log"
    FAILS=$((FAILS + 1))
  fi
fi

echo "== done: $FAILS failing suite(s) =="
exit $((FAILS > 0))
