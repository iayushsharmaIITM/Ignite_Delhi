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

# The app tier runs on its OWN port. It used to be 8000 — the live demo's port —
# so with the demo running this battery started a server that could not bind,
# found $BASE/health answering anyway (the LIVE app), and marched on testing that:
# PROVIDER=cloud, AUTH_MODE=clerk, and a green result that described somebody
# else's process. Refuse to share the port, and after startup insist that the
# thing answering is the mock tier we just launched.
PORT="${KESTREL_VERIFY_PORT:-8020}"
export PORT
BASE="http://127.0.0.1:${PORT}"
export BASE           # test_tenants.py reads BASE from the environment
if (exec 3<>"/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null; then
  echo "ABORT: 127.0.0.1:${PORT} is already listening."
  echo "       This battery must not test a server it did not start — the suites"
  echo "       assume PROVIDER=mock and AUTH_MODE=off, which the live app is not."
  echo "       Stop it, or pick another port: KESTREL_VERIFY_PORT=8021 ./verify.sh"
  exit 2
fi
SERVER_PID=""
FAILS=0
RAN=0
SKIPPED=0
SKIPLIST=""

# One port is the managed surface: :8000, brought up and idempotently by
# ops_stack_up.sh. Everything else that answers HTTP here is either this battery's
# own short-lived fixture or a leftover somebody forgot to stop — and leftovers are
# how a "preview" ends up being a second app tier with different auth, on a different
# database, that nobody is managing. Report them instead of letting them accumulate.
STRAYS=""
for P in 8010 8011 8021 8022 8025 8028 8030 8031; do
  PID=$(lsof -nP -iTCP:$P -sTCP:LISTEN -t 2>/dev/null | head -1)
  [ -n "$PID" ] && STRAYS="$STRAYS $P(pid$PID)"
done
if [ -n "$STRAYS" ]; then
  echo "note: app tiers listening besides :8000 and this fixture on :$PORT ->$STRAYS"
  echo "      :8000 is the one managed port (ops_stack_up.sh). Stop leftovers rather"
  echo "      than adding ports; a stray tier has different auth and often a different"
  echo "      database, which is how previews start lying."
fi

note() {
  echo "[$1] $2"
  # Count the verdicts, not just the failures. Until now a run could print SKIP
  # six times, exit 0, and read as a clean battery; the exit code only ever
  # tracked FAILS, so "half the tiers stood down" and "everything passed" were
  # the same green. The tally goes in the closing line so the number of tiers
  # that actually guarded the change is visible next to the verdict.
  case "$2" in
    PASS*|FAIL*) RAN=$((RAN + 1)) ;;
    SKIP*) SKIPPED=$((SKIPPED + 1)); SKIPLIST="$SKIPLIST $1" ;;
  esac
  # The first hosted CI run failed two suites and said only
  # "FAIL — see /tmp/kestrel_verify_docs.log" — a pointer to a file that exists on a
  # GitHub runner and nowhere else. Print the tail inline so the reason survives the
  # jump from the machine that ran it to the person reading it.
  case "$2" in
    FAIL*) local log="${2##*see }"
           if [ -f "$log" ]; then
             echo "  ---- tail of $log ----"
             tail -c 2000 "$log" | sed 's/^/  | /'
             echo "  ---- end ----"
           fi ;;
  esac
}

# Count what the suite actually reported instead of typing a denominator into this
# file. The labels used to read "PASS  25/25" as a literal, so a suite could gain or
# lose checks — or skip one — and the battery would still print a number nobody
# measured. Empty output means the suite does not use the PASS/FAIL line format, and
# the label falls back to a bare PASS rather than a guess.
tally() {
  local log="$1" p f
  [ -f "$log" ] || return 0
  p=$(grep -c '^  PASS' "$log" 2>/dev/null || true)
  f=$(grep -c '^  FAIL' "$log" 2>/dev/null || true)
  p=${p:-0}; f=${f:-0}
  [ "$p" -gt 0 ] && printf '%s/%s' "$p" "$((p + f))"
}

cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
}
trap cleanup EXIT

# The battery used to abort when anything held :8000, because a server left over
# from a dev session would answer with the CLOUD provider (its own env) and make
# the battery lie about mock mode. Right hazard, wrong remedy: it also meant the
# battery could not run while the demo was up, which is when it matters most. The
# app tier now starts on its own port and /health is checked for PROVIDER=mock
# below, so a foreign server cannot be mistaken for ours at all.

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
    echo "       Bring up the lab (ops/restore_lab.sh). KESTREL_ALLOW_LIVE_DB=1"
    echo "       overrides this, and per AGENTS.md setting it is the owner's call,"
    echo "       in the same terms as deleting or re-ingesting — not a retry flag."
    exit 2
  else
    echo "db: none reachable - storage-backed suites degrade, which is what CI expects"
  fi
fi

# The same refusal, applied to a URL the CALLER exported. It used to live only
# inside the branch above, so `DATABASE_URL=<live 5433> ./verify.sh` skipped the
# check entirely and the documents / pipeline-states / tenants / smoke / frontend
# tiers wrote straight into the production database — while AGENTS.md said this
# battery "refuses to run against the live database". Right hazard, half-implemented:
# the guard has to judge the URL that is actually in effect, whoever set it.
if [[ "${DATABASE_URL:-}" == *5433* && "${KESTREL_ALLOW_LIVE_DB:-0}" != "1" ]]; then
  echo "ABORT: DATABASE_URL names the LIVE database (5433) and this battery writes"
  echo "       test rows. That is true whether this script chose the URL or the"
  echo "       caller exported it."
  echo "       Point it at the lab: DATABASE_URL=<lab 5434> ./verify.sh"
  echo "       KESTREL_ALLOW_LIVE_DB=1 overrides, and is the owner's call to make."
  exit 2
fi

# --- 1. document extraction (no server needed) ------------------------------
if python3 test_documents.py > /tmp/kestrel_verify_docs.log 2>&1; then
  note documents "PASS  $(tally /tmp/kestrel_verify_docs.log)"
else
  note documents "FAIL — see /tmp/kestrel_verify_docs.log"
  FAILS=$((FAILS + 1))
fi

# --- 2. pipeline terminal states (unit test, no server needed) --------------
if python3 test_pipeline_states.py > /tmp/kestrel_verify_pipe.log 2>&1; then
  note pipe-states "PASS  $(tally /tmp/kestrel_verify_pipe.log)"
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
# Answering is not the same as being ours. A foreign :8000 answers too.
HEALTH=$(curl -sf "$BASE/health" 2>/dev/null || true)
if ! printf '%s' "$HEALTH" | grep -qE '"provider": ?"mock"'; then
  note server "FAIL — $BASE is not the mock tier this battery started: ${HEALTH:0:120}"
  cleanup
  exit 1
fi
note server "up (pid $SERVER_PID, mock fixtures, :$PORT)"

# --- 3. connector vault + OAuth contract (in-process, no browser) ------------
# Runs before the live-server suites: it drives app.py through TestClient, so
# it must not race the mock server for the real port.
# Lab-only from here on. The suite deletes connector_credentials rows for owner '|',
# which is the key a single-user install keeps its own grants under, and standalone
# storage.DATABASE_URL resolves to the LIVE tier (:5433) — the table it created there
# is the evidence. It now refuses anything but 5434, so the battery has to say why it
# is skipping rather than reporting a failure it caused by having no lab database.
if [[ "${DATABASE_URL:-}" == *5434* ]]; then
  if python3 connectors_test.py > /tmp/kestrel_verify_conn.log 2>&1; then
    note connectors "PASS  $(tally /tmp/kestrel_verify_conn.log)"
  else
    note connectors "FAIL — see /tmp/kestrel_verify_conn.log"
    FAILS=$((FAILS + 1))
  fi
else
  note connectors "SKIP  (needs DATABASE_URL=<lab 5434> — it deletes vault rows)"
fi

# --- 4. tenant isolation (live-server test; config written + restored) ------
if python3 test_tenants.py --with-tenants > /tmp/kestrel_verify_tenants.log 2>&1; then
  note tenants "PASS  $(tally /tmp/kestrel_verify_tenants.log)"
else
  note tenants "FAIL — see /tmp/kestrel_verify_tenants.log"
  FAILS=$((FAILS + 1))
fi

# --- 5. web-tier smoke -------------------------------------------------------
if python3 smoke.py --base "$BASE" > /tmp/kestrel_verify_smoke.log 2>&1; then
  note smoke "PASS  $(tally /tmp/kestrel_verify_smoke.log)"
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

# --- 6b. phatic routing (hermetic: no database, no provider, no browser) ------
# The answer engine's greeting/thanks path. It is gated here because it was merged
# working and shipped broken: the web tier classified the question AFTER prepending
# its own local-time note, so every greeting in the real app paid a full retrieval
# round trip. The tier pins PROVIDER=mock and refuses a non-lab DATABASE_URL, so it
# can never reach the live tenant or spend real inference.
if python3 tests/test_phatic.py > /tmp/kestrel_verify_phatic.log 2>&1; then
  note phatic "PASS  $(tally /tmp/kestrel_verify_phatic.log)"
else
  note phatic "FAIL — see /tmp/kestrel_verify_phatic.log"
  FAILS=$((FAILS + 1))
fi

# --- 6b2. source precedence (hermetic: no provider call, no browser) -----------
# /api/source used to read corpus/<filename> off disk before it consulted the
# authorised brain, so a customer document sharing a demo corpus filename opened
# the demo's text: a confidently wrong source, which is the invariant this product
# is sold on. The tier pins PROVIDER=mock and refuses a non-lab DATABASE_URL, and
# it also holds the demo brain to its original order — corpus first, tenant map
# never touched, because that fallthrough used to cost ~20s.
if python3 tests/test_source_precedence.py > /tmp/kestrel_verify_source_prec.log 2>&1; then
  note source-precedence "PASS  $(tally /tmp/kestrel_verify_source_prec.log)"
else
  note source-precedence "FAIL — see /tmp/kestrel_verify_source_prec.log"
  FAILS=$((FAILS + 1))
fi

# --- 6b3. citation collisions (hermetic: temp corpus, temp manifest) ----------
# A citation's filename is recovered from the first 120 normalised characters of the
# document, which is not unique. Two files sharing a prefix used to resolve to the
# alphabetically later one, an empty corpus file used to adopt every document whose
# raw fetch failed, and uploads.json's own _collisions table — written since COR-8 to
# record exactly this — had no reader at all (A-57). Ambiguous now means unresolved,
# which is the one outcome the no-fabricated-citations invariant permits. The tier also
# fails if the shipped demo corpus ever gains a colliding pair, because that silently
# costs a real document its citation.
if python3 tests/test_citation_collisions.py > /tmp/kestrel_verify_citation_coll.log 2>&1; then
  note citation-collisions "PASS  $(tally /tmp/kestrel_verify_citation_coll.log)"
else
  note citation-collisions "FAIL — see /tmp/kestrel_verify_citation_coll.log"
  FAILS=$((FAILS + 1))
fi

# --- 6b4. durable citation identity (hermetic: the DB query is a named seam) ---------
# Two ways a citation could name a document the answer did not come from. The durable
# lookup selected limit 1 with no ORDER BY, and backend_data_id identifies CONTENT — so
# the same file in two brains, or two generations of one brain, matched twice and the
# citation named whichever row the planner reached. And /api/source re-read the NEWEST
# version of a filename, so an answer produced from version A kept opening version B
# after a re-upload. Now a clash resolves to nothing, and a citation that knows its
# version opens exactly that one. Driven through citations._rows, so it proves the SQL
# and the branch logic with no database in sight.
if python3 tests/test_durable_identity.py > /tmp/kestrel_verify_durable_id.log 2>&1; then
  note durable-identity "PASS  $(tally /tmp/kestrel_verify_durable_id.log)"
else
  note durable-identity "FAIL — see /tmp/kestrel_verify_durable_id.log"
  FAILS=$((FAILS + 1))
fi

# --- 6b5. storage outage contract (hermetic: the connection is a stub) ---------------
# brain_access() caught every exception and returned None, and brain_allowed() reads
# None as "Unknown brain" — so a Postgres outage told every authenticated user that the
# brain they own does not exist, and /api/source 404ed for the same reason. Access still
# fails CLOSED (nothing is served while storage is down), but an outage now answers 503
# and says so, while a missing row and a foreign row keep the identical 403 so nothing
# about existence becomes probeable. AGENTS.md already states the rule; this is the tier
# that enforces it.
if python3 tests/test_storage_outage.py > /tmp/kestrel_verify_storage_outage.log 2>&1; then
  note storage-outage "PASS  $(tally /tmp/kestrel_verify_storage_outage.log)"
else
  note storage-outage "FAIL — see /tmp/kestrel_verify_storage_outage.log"
  FAILS=$((FAILS + 1))
fi

# --- 6b6. rebuild publish fence (A-58/E13, hermetic) ---------------------------
# Both publish fences described a CREATE (brain.state == 'CREATING'), but a REBUILD
# starts from a brain that is deliberately left READY so a failed rebuild cannot break
# a live company brain — so no rebuild could ever publish, in the job path or the
# recovery path. One predicate now carries the rule, and this tier pins both halves:
# the rebuild is allowed through, and the create's double-publish guard is not loosened.
if python3 tests/test_rebuild_publish.py > /tmp/kestrel_verify_rebuild_fence.log 2>&1; then
  note rebuild-fence "PASS  $(tally /tmp/kestrel_verify_rebuild_fence.log)"
else
  note rebuild-fence "FAIL — see /tmp/kestrel_verify_rebuild_fence.log"
  FAILS=$((FAILS + 1))
fi

# --- 6b7. numbered citations invariant gate (Phase 7, hermetic) -----------------------
# Every inline marker [N] or [^N] must correspond to an actual resolved source in
# references (1-based index). Out-of-bounds or unresolved markers return None/unresolved
# rather than guessing a document name. Pinned version lookups 404 on miss rather than
# substituting another version, and storage outages surface as 503 rather than empty/denial.
if python3 tests/test_numbered_citations.py > /tmp/kestrel_verify_num_citations.log 2>&1; then
  note numbered-citations "PASS  $(tally /tmp/kestrel_verify_num_citations.log)"
else
  note numbered-citations "FAIL — see /tmp/kestrel_verify_num_citations.log"
  FAILS=$((FAILS + 1))
fi

# --- 6b8. live slack & external connectors (P6, hermetic / lab-safe) -----------------
# Slack multi-workspace, scope negotiation, public & private channel discovery,
# conversation history, live message posting, and citable connector import into brains.
# Disconnects cleanly revoke grants and purge stored credentials from the vault.
if python3 tests/test_slack_live_connector.py > /tmp/kestrel_verify_slack_connector.log 2>&1; then
  note slack-connector "PASS  $(tally /tmp/kestrel_verify_slack_connector.log)"
else
  note slack-connector "FAIL — see /tmp/kestrel_verify_slack_connector.log"
  FAILS=$((FAILS + 1))
fi

# --- 6b9. legacy visibility, characterised (NOT a security gate) --------------
# B05/B06/X-USAGE came in as vulnerabilities and are documented grandfathering: a row
# with both owner columns NULL is readable by every authenticated identity, membership
# OR creator is enough, and a brain nobody registered still shows in a scoped usage
# summary. Ayush's call was "demonstrate, change nothing". This tier is the
# demonstration: it says who can see what today, in the exact SQL that decides it, so
# that a future change is a decision and not a line someone edited by accident. A PASS
# here is NOT an assertion that the behaviour is correct.
if python3 tests/test_legacy_visibility.py > /tmp/kestrel_verify_legacy_vis.log 2>&1; then
  note legacy-visibility "PASS  $(tally /tmp/kestrel_verify_legacy_vis.log) / characterisation only"
else
  note legacy-visibility "FAIL — see /tmp/kestrel_verify_legacy_vis.log"
  FAILS=$((FAILS + 1))
fi

# --- 6a. doc freshness --------------------------------------------------------
# A stale route inside an instruction document is not cosmetic: an agent obeys it.
# CLAUDE_CONTEXT.md used to tell agents to verify with pytest, which this file's own
# header says collects 2 of 13 checks — following the doc produced a false green.
if bash ops/doc_health.sh > /tmp/kestrel_verify_doc_health.log 2>&1; then
  DW=$(grep -c '^  WARN' /tmp/kestrel_verify_doc_health.log 2>/dev/null || true)
  note doc-health "PASS  $(tally /tmp/kestrel_verify_doc_health.log)${DW:+ / $DW warn}"
else
  note doc-health "FAIL — see /tmp/kestrel_verify_doc_health.log"
  FAILS=$((FAILS + 1))
fi

# --- 6c. chat integrity (Round 2: CH-1..CH-9) ---------------------------------
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
  # P3 Clerk isolation (cross-identity brain access). Lab-only like the two above:
  # it creates its own database and refuses any other server. It used to be
  # reachable only from a pytest line in CLAUDE_CONTEXT.md, while running the file
  # directly printed nothing and exited 0 — a green that measured nothing.
  if python3 test_auth_isolation.py > /tmp/kestrel_verify_auth_iso.log 2>&1; then
    note auth-isolation "PASS  $(tally /tmp/kestrel_verify_auth_iso.log)"
  else
    note auth-isolation "FAIL — see /tmp/kestrel_verify_auth_iso.log"
    FAILS=$((FAILS + 1))
  fi
  # Three more security gates that had been sitting unwired: each one asserts a
  # real invariant, runs clean standalone, and was invoked by nothing — no battery
  # tier, no CI step, only a human who happened to know. An invariant suite that
  # only a human can run reads as coverage while detecting nothing, which is the
  # same failure H-2 recorded for chat-integrity.
  #   route-authz          brain-scoped allow/deny + source path traversal (6 asserts)
  #   lifecycle-identity   Phase 0 regression: identity carried through the lifecycle
  #   lease-recovery       orphaned/uncertain jobs are not blindly retried
  #   v2-authz             the durable /api/brains/v2 job path, allow AND deny
  # v2-authz joined this round: it was in the tree, set its own KESTREL_JOBS_V2
  # flag, proved the allow/deny/404 directions and cleaned up after itself, and
  # nothing ran it — while UPGRADE_COMPLETION_REPORT.md listed it as delivered
  # coverage. The v2 path is now genuinely covered rather than believed.
  for gate in tests/test_route_authz.py tests/test_lifecycle_identity.py tests/test_lease_recovery.py tests/test_v2_authz.py; do
    name=$(basename "$gate" .py | sed 's/^test_//' | tr '_' '-')
    log="/tmp/kestrel_verify_${name}.log"
    if python3 "$gate" > "$log" 2>&1; then
      note "$name" "PASS"
    else
      note "$name" "FAIL — see $log"
      FAILS=$((FAILS + 1))
    fi
  done
else
  note chat-integrity "SKIP  (needs DATABASE_URL=<lab 5434> — it writes rows)"
  note brain-claim "SKIP  (needs DATABASE_URL=<lab 5434> — it writes rows)"
  note auth-isolation "SKIP  (needs DATABASE_URL=<lab 5434> — it creates a database)"
  for name in route-authz lifecycle-identity lease-recovery v2-authz; do
    note "$(echo $name | tr '_' '-')" "SKIP  (needs DATABASE_URL=<lab 5434> — it writes rows)"
  done
fi

# --- 7. React UI acceptance suite (browser) -----------------------------------
# Drives the SERVED bundle: ask/stream/citations/source modal/files sheet/draft/
# menus/keyboard/deep links/history, with the model calls intercepted. This is
# the suite that proves the frontend the product hands a browser actually works.
# check_ui.py (the pre-port legacy suite) was retired here: it depended on a
# playwright-cli binary that no longer exists and drove the legacy chat shell.
# CORRECTED on this pass: the comment used to warn "deleting static/ would break a
# primary nav item, because /graph serves static/graph.html regardless of UI_MODE".
# That was true, and it was the reason the last legacy page survived the chat
# shell. It no longer is: the graph's force layout, camera, node disclosure and
# inspector were ported into React's GraphView, gated in the section below, and
# static/ is gone. /graph now redirects into the app like /brains and /upload.
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

echo "== done: ran $RAN tier(s), skipped $SKIPPED, failing $FAILS =="
if [ "$SKIPPED" -gt 0 ]; then
  echo "   did not run:$SKIPLIST"
  echo "   Green here means the tiers that ran found nothing. It does not mean the"
  echo "   skipped ones agree: they stood down for want of a lab database, a browser"
  echo "   or an opt-in flag. Widen the lane with DATABASE_URL=<lab 5434>"
  echo "   (and KESTREL_CLERK_GATE=1) and read this line before believing a PASS."
fi
exit $((FAILS > 0))
