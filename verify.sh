#!/usr/bin/env bash
# The single battery entrypoint (BUILD_PLAN.md section 2.2).
#
#   ./verify.sh           full battery, including the React UI acceptance suite
#   ./verify.sh --quick   skip the browser suites (no browser / CI fast lane)
#   KESTREL_CLERK_GATE=1 DATABASE_URL=<lab 5434> ./verify.sh   + clerk-mode gate
#
# With no DATABASE_URL the battery picks the LAB database if it is reachable and
# refuses to write into the live one unless KESTREL_ALLOW_LIVE_DB=1 — see the
# "which database may this battery write to?" block below.
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

# --- which database may this battery write to? -------------------------------
# The battery WRITES: the UI suite saves chats, and chat-integrity / brain-claim
# insert rows. With no DATABASE_URL the app falls through to .env — the LIVE demo
# database — so every routine `./verify.sh` left test chats inside the demo brain,
# stamped as nobody's (it runs AUTH_MODE=off), which is exactly the population the
# SEC-5 grandfathering rule hands to every tenant. Prefer the lab, refuse to write
# to live unless told, and stay silent when there is no database at all (CI).
if [[ -z "${DATABASE_URL:-}" ]]; then
  LAB_PW=$(grep -m1 '^GRAPH_DATABASE_PASSWORD=' .env.oss 2>/dev/null | cut -d= -f2-)
  if [[ -n "$LAB_PW" ]] && (exec 3<>"/dev/tcp/127.0.0.1/5434") 2>/dev/null; then
    export DATABASE_URL="postgresql://kestrel:${LAB_PW}@localhost:5434/kestrel"
    echo "db: LAB (5434) - the battery writes rows. Set DATABASE_URL to override."
  elif (exec 3<>"/dev/tcp/127.0.0.1/5433") 2>/dev/null \
       && [[ "${KESTREL_ALLOW_LIVE_DB:-0}" != "1" ]]; then
    echo "ABORT: the only reachable database is the LIVE one (5433), and this"
    echo "       battery writes test rows into it."
    echo "       bring up the lab (ops/restore_lab.sh), or insist with"
    echo "       KESTREL_ALLOW_LIVE_DB=1 ./verify.sh"
    exit 2
  else
    echo "db: none reachable - storage-backed suites degrade, which is what CI expects"
  fi
fi

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

# --- 3. connector vault + OAuth contract (in-process, no browser) ------------
# Runs before the live-server suites: it drives app.py through TestClient, so
# it must not race the mock server for the real port.
if python3 connectors_test.py > /tmp/kestrel_verify_conn.log 2>&1; then
  note connectors "PASS  90/90"
else
  note connectors "FAIL — see /tmp/kestrel_verify_conn.log"
  FAILS=$((FAILS + 1))
fi

# --- 4. tenant isolation (live-server test; config written + restored) ------
if python3 test_tenants.py --with-tenants > /tmp/kestrel_verify_tenants.log 2>&1; then
  note tenants "PASS  10/10"
else
  note tenants "FAIL — see /tmp/kestrel_verify_tenants.log"
  FAILS=$((FAILS + 1))
fi

# --- 5. web-tier smoke -------------------------------------------------------
if python3 smoke.py > /tmp/kestrel_verify_smoke.log 2>&1; then
  note smoke "PASS  4/4"
else
  note smoke "FAIL — see /tmp/kestrel_verify_smoke.log"
  FAILS=$((FAILS + 1))
fi

# --- 6. frontend static gates (no browser) -----------------------------------
# The transport invariant (every /api call authenticated, one code path) and the
# CSS-utility invariant (no class that emits nothing). Both are cheap and both
# exist because the port shipped with the opposite of each.
if python3 tests/test_frontend_api_transport.py > /tmp/kestrel_verify_fe_transport.log 2>&1; then
  note frontend-transport "PASS"
else
  note frontend-transport "FAIL — see /tmp/kestrel_verify_fe_transport.log"
  FAILS=$((FAILS + 1))
fi
if python3 tests/test_frontend_css_utilities.py > /tmp/kestrel_verify_fe_css.log 2>&1; then
  note frontend-css "PASS"
else
  note frontend-css "FAIL — see /tmp/kestrel_verify_fe_css.log"
  FAILS=$((FAILS + 1))
fi

# --- 6b. chat integrity (Round 2: CH-1..CH-9) ---------------------------------
# The rules that keep a conversation from being silently rewritten: a save with
# fewer turns than the server holds is refused unless it declares a trim; a
# deleted chat stays deleted (410); DELETE tells the truth (404, not 200
# ok:false); filing a chat under a brain is a brain access; and a bad client
# field cannot turn a save into a 500. It WRITES rows, so it only runs against
# the lab database — the same reason the Clerk gate below is opt-in. Every row
# it creates is `itest-*` and its own finally removes them.
if [[ "${DATABASE_URL:-}" == *5434* ]]; then
  if python3 tests/test_chat_integrity.py > /tmp/kestrel_verify_integrity.log 2>&1; then
    note chat-integrity "PASS"
  else
    note chat-integrity "FAIL — see /tmp/kestrel_verify_integrity.log"
    FAILS=$((FAILS + 1))
  fi
  # M4: creation exclusivity. Same lab-only rule — it writes ownership rows and
  # deletes them again.
  if python3 tests/test_brain_claim.py > /tmp/kestrel_verify_claim.log 2>&1; then
    note brain-claim "PASS"
  else
    note brain-claim "FAIL — see /tmp/kestrel_verify_claim.log"
    FAILS=$((FAILS + 1))
  fi
else
  note chat-integrity "SKIP  (needs DATABASE_URL=<lab 5434> — it writes rows)"
  note brain-claim "SKIP  (needs DATABASE_URL=<lab 5434> — it writes rows)"
fi

# --- 7. React UI acceptance suite (browser) -----------------------------------
# Drives the SERVED bundle: ask/stream/citations/source modal/files sheet/draft/
# menus/keyboard/deep links/history, with the model calls intercepted. This is
# the suite that proves the frontend the product hands a browser actually works.
# check_ui.py (the pre-port legacy suite) was retired here: it depended on a
# playwright-cli binary that no longer exists, drove webkit, and the legacy shell
# is now reachable only via KESTREL_UI=legacy — smoke.py still covers its pages
# over HTTP. See docs/FRONTEND_FIX_PLAN.md D2.
if [ "$QUICK" -eq 1 ]; then
  note ui-react "SKIP  (--quick)"
else
  if python3 check_ui_react.py --base "$BASE" > /tmp/kestrel_verify_ui_react.log 2>&1; then
    note ui-react "PASS"
  else
    note ui-react "FAIL — see /tmp/kestrel_verify_ui_react.log"
    FAILS=$((FAILS + 1))
  fi
fi

# --- 8. Clerk-mode gate (optional: needs the lab database + a browser) --------
# Proves the app works in the LIVE auth configuration, with a control run that
# must 401. Opt-in because it boots its own app on its own port and writes to the
# lab DB (it refuses anything that is not port 5434).
if [ "${KESTREL_CLERK_GATE:-0}" = "1" ]; then
  if python3 tests/test_react_clerk.py > /tmp/kestrel_verify_clerk.log 2>&1; then
    note clerk-gate "PASS"
  else
    note clerk-gate "FAIL — see /tmp/kestrel_verify_clerk.log"
    FAILS=$((FAILS + 1))
  fi
else
  note clerk-gate "SKIP  (set KESTREL_CLERK_GATE=1 with DATABASE_URL=<lab> to run)"
fi

echo "== done: $FAILS failing suite(s) =="
exit $((FAILS > 0))
