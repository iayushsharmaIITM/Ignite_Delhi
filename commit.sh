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

# `git add -A` is exactly how a pasted API key reaches history, and this helper
# commits every 15-20 minutes, so the guard runs against the stage area — what is
# about to be committed, and nothing else. KESTREL_ALLOW_SECRETS=1 skips it for a
# verified false positive; say why in the message when you use it.
if [ "${KESTREL_ALLOW_SECRETS:-0}" != "1" ]; then
  if ! ops/check_secrets.sh --staged; then
    echo
    echo "commit blocked by the secret guard (nothing was committed, stage area intact)"
    exit 1
  fi
fi

git commit -m "${MSG} [${STAMP}]"
echo "committed: ${MSG} [${STAMP}]"
