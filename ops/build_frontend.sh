#!/usr/bin/env bash
# Build the React frontend that app.py serves (docs/FRONTEND_FIX_PLAN.md A1).
#
#   ./ops/build_frontend.sh              # npm ci + tsc + vite build
#   ./ops/build_frontend.sh --no-install # reuse node_modules (fast local loop)
#
# WHY THE OUTPUT IS COMMITTED: the app tier has no Node (render.yaml installs
# only requirements.txt; ops_stack_up.sh just runs `python3 app.py`), so the
# bundle must exist in the checkout for `python app.py` to serve it. The cost of
# a committed artifact is silent staleness — CI pays it back by rebuilding and
# diffing frontend/dist (.github/workflows/ci.yml, "dist is in sync" step).
#
# The build is deterministic: same lockfile + same sources produce byte-identical
# files (verified 2026-10-03 by building twice and comparing sha256 of every
# file in dist/). That determinism is what makes the CI diff meaningful.

set -euo pipefail
cd "$(dirname "$0")/.."

INSTALL=1
[ "${1:-}" = "--no-install" ] && INSTALL=0

cd frontend
if [ "$INSTALL" -eq 1 ]; then
  npm ci
fi
npm run build

echo
echo "built frontend/dist:"
ls -1 dist dist/assets | sed 's/^/  /'
echo
echo "committed bundle freshness is enforced in CI: git diff --exit-code -- frontend/dist"
