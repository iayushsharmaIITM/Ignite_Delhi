#!/usr/bin/env bash
# Refuse to commit (or to keep in the repo) anything that looks like a key.
#
#   ops/check_secrets.sh --staged   # what commit.sh runs before every commit
#   ops/check_secrets.sh --all      # what CI runs over every tracked file
#   ops/check_secrets.sh --file PATH
#
# Why this exists as a script: commit.sh runs `git add -A`. That is exactly the
# shape of command that quietly commits a pasted API key, because "it is only
# local" stops being true the moment the helper pushes. .env and .env.oss are
# gitignored, so the risk was never the config files themselves — it is the key
# that gets pasted into a route, a fixture, a test, or a commit message.
#
# High-signal patterns only. A false positive costs a minute here; a missed real
# key costs a rotation, an incident note, and the customer's trust.
set -uo pipefail
cd "$(dirname "$0")/.."

# Clerk/OpenAI-style secret keys, cloud provider ids, provider tokens, private
# keys. Publishable keys (pk_test_/pk_live_ followed by Clerk's base64 form) are
# deliberately NOT in here: they ship in the page HTML by design.
PATTERNS='sk-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY|secret_[a-z0-9]{20,}|SG\.[A-Za-z0-9_-]{20,}'

# File names that must never be tracked, whatever their contents. Templates are
# the deliberate exception: `.env.example` is meant to be committed, so it is
# exempt from the NAME rule but still scanned for content below - a real key
# pasted into a template is caught exactly like one pasted into a route.
NAME_RE='(^|/)(\.env\.[a-z]+|\.env|credentials[a-z._-]*|secrets\.[a-z]+|id_rsa[a-z._-]*|service-account[a-z._-]*\.json|[^/]*\.(pem|p12|pfx|key))$'
TEMPLATE_RE='\.(example|sample|template|dist)$'

FAIL=0

# Fail closed: a detector that silently errors would report "clean", which is
# worse than no detector at all. If the pattern cannot match its own example, or
# grep rejects it, stop rather than green-lighting the commit.
if ! printf 'sk-abcdefghijklmnopqrstuvwxyz1234' | grep -qE "$PATTERNS" 2>/dev/null; then
  echo "secret detector is broken (self-test failed) - refusing to judge anything"
  exit 2
fi

scan() {                       # scan <label> <text>
  local label="$1" text="$2" hit err
  err=$(mktemp)
  hit=$(printf '%s\n' "$text" | grep -nIE "$PATTERNS" 2>"$err" || true)
  if [[ -s "$err" ]]; then
    echo "  SCAN ERROR in $label: $(head -1 "$err")"
    FAIL=1
  fi
  rm -f "$err"
  if [[ -n "$hit" ]]; then
    echo "  SECRET-LIKE $label:"
    printf '%s\n' "$hit" | sed -e 's/^/      /' | cut -c1-160
    FAIL=1
  fi
}

case "${1:---staged}" in
  --staged)
    files=$(git diff --cached --name-only --diff-filter=ACM || true)
    for f in $files; do
      if printf '%s' "$f" | grep -qE "$NAME_RE" \
         && ! printf '%s' "$f" | grep -qE "$TEMPLATE_RE"; then
        echo "  SECRET-LIKE filename is never safe to track: $f"
        FAIL=1
        continue
      fi
      # only ADDED lines: an existing false positive in context must not block
      # an unrelated change
      added=$(git diff --cached -U0 -- "$f" | grep '^+' | grep -v '^+++' || true)
      scan "$f" "$added"
    done
    ;;
  --all)
    # every tracked file's current content
    for f in $(git ls-files); do
      if printf '%s' "$f" | grep -qE "$NAME_RE" \
         && ! printf '%s' "$f" | grep -qE "$TEMPLATE_RE"; then
        echo "  SECRET-LIKE filename is tracked: $f"
        FAIL=1
        continue
      fi
      case "$f" in
        *.png|*.jpg|*.jpeg|*.gif|*.woff*|*.tgz|*.zip|*.pdf|*.ico) continue ;;
      esac
      # hand the whole file to the scanner; pre-filtering with the same pattern
      # would swallow a grep error and report a false "clean"
      scan "$f" "$(cat -- "$f" 2>/dev/null || true)"
    done
    ;;
  --file)
    scan "$2" "$(cat "$2" 2>/dev/null || true)"
    ;;
  *)
    echo "usage: ops/check_secrets.sh [--staged|--all|--file PATH]"; exit 2 ;;
esac

if [[ $FAIL -ne 0 ]]; then
  echo
  echo "BLOCKED: something above looks like a credential."
  echo "  - if it IS a secret: move it to .env (gitignored) and rotate it —"
  echo "    assume anything that reached a stage area is already exposed."
  echo "  - if it is NOT (a fixture, a doc sample): set KESTREL_ALLOW_SECRETS=1"
  echo "    for this one commit and say why in the message."
  exit 1
fi
echo "secrets: clean"
