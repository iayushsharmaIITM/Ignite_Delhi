#!/usr/bin/env bash
# Continuous-commit helper.
#
# Why this exists: a single bulk commit at the end can trigger a plagiarism
# investigation at SIH-style events. Commit every 15-20 minutes instead.
# Usage:  ./commit.sh "added graph retrieval"
set -euo pipefail

MSG="${1:-wip}"
STAMP=$(date +"%H:%M")

git add -A
if git diff --cached --quiet; then
  echo "nothing to commit"
  exit 0
fi

git commit -m "${MSG} [${STAMP}]"
echo "committed: ${MSG} [${STAMP}]"
