#!/usr/bin/env bash
# Doc-freshness gate: assert that instruction documents agree with the repo.
#
#   ops/doc_health.sh            exit 0 unless a documented route is wrong
#
# Why a script and not a review: this project has ~20 markdown documents written
# across two eras, and a stale one is not a cosmetic problem — an agent obeys it.
# CLAUDE_CONTEXT.md used to route verification through `pytest`, which verify.sh
# itself declares collects 2 of 13 checks, so following the doc produced a
# false-green verification. That class of defect is cheap to detect mechanically
# and expensive to notice by reading.
#
# FAIL  = the document contradicts a canonical owner in this repo (fix the doc).
# WARN  = a real divergence whose resolution is an owner decision (fix nothing here).
set -uo pipefail
cd "$(dirname "$0")/.."

FAILS=0
CHECKS=0
check() {  # check <id> <expect-pass-shell-test> <message>
  local id="$1" test="$2" msg="$3"
  CHECKS=$((CHECKS + 1))
  if eval "$test"; then
    echo "  PASS  $id"
  else
    echo "  FAIL  $id — $msg"
    FAILS=$((FAILS + 1))
  fi
}

warn() {  # warn <id> <condition-that-induces-the-warning> <message>
  CHECKS=$((CHECKS + 1))
  if eval "$2"; then
    echo "  WARN  $1 — $3"
  else
    echo "  PASS  $1"
  fi
}

# 1. The entrypoint must route verification through the battery, not pytest.
check entrypoint-routes-battery \
  '[ -f AGENTS.md ] && grep -q "\./verify\.sh" AGENTS.md' \
  "AGENTS.md missing or does not name ./verify.sh"

check context-doc-does-not-prescribe-pytest \
  '! grep -qn "python3 -m pytest test_" CLAUDE_CONTEXT.md' \
  "CLAUDE_CONTEXT.md tells agents to verify with pytest; verify.sh says pytest collects 2 of 13 checks"

# 2. verify.sh owns the "how to run suites" truth; keep the statement alive.
check battery-states-pytest-limit \
  'grep -q "pytest collects only" verify.sh' \
  "verify.sh no longer documents why pytest is not the entrypoint"

# 3. A pinned revision inside a context doc goes stale within a day.
check no-pinned-revision-claim \
  '! grep -qE "green at .?[0-9a-f]{7}" CLAUDE_CONTEXT.md' \
  "CLAUDE_CONTEXT.md pins project state to a commit hash"

# 4. The docs that carry current status must not both claim to be current.
check progress-is-newest-first \
  'head -1 PROGRESS.md | grep -q "^## "' \
  "PROGRESS.md no longer starts with a dated entry"

# Owner-decision divergences: real, reported, not this script's to resolve.
warn n3-compose-oss-tracked \
  'git ls-files --error-unmatch compose.oss.yml >/dev/null 2>&1' \
  "BUILD_PLAN.md N3 says compose.oss.yml must be gitignored; it is tracked (no secret-shaped content, so this is a policy call, not a leak)"

warn render-path-vs-oss-runtime \
  'grep -q "COGNEE_FLAVOR=oss" .env 2>/dev/null' \
  "render.yaml targets the Cognee Cloud tenant while .env runs the OSS container: two backends, one repo"

warn heroku-target-has-no-procfile \
  '[ ! -f Procfile ] && grep -qi "heroku" PLAN.md' \
  "PLAN P4 is Heroku but no Procfile exists yet — see docs/architecture/deployment-topology.md"

echo
if [ "$FAILS" -gt 0 ]; then
  echo "doc health: $FAILS FAILING of $CHECKS checks"
  exit 1
fi
echo "doc health: all documented routes agree with the repo ($CHECKS checks, warnings aside)"
