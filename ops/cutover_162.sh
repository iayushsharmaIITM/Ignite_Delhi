#!/usr/bin/env bash
# PR-8: cutover runbook — switch the WORKING stack to the 1.6.2 candidate.
# !!! NOT EXECUTED BY THIS PHASE. Requires founder approval of:
#   - docs/baseline evidence (Phase A)
#   - PR-1 restore-drill results
#   - PR-2 candidate test results (this file's preconditions below)
# Rollback is REHEARSAL-PROOF only: old image + restored old state + old config.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "PRECONDITIONS (all must be checked before proceeding):"
echo "  [ ] founder approval recorded"
echo "  [ ] backup fresher than 1h: ls -t var/backups/*/db.sql | head -1"
echo "  [ ] candidate test results green (shadow ask, isolation spike, pagination)"
echo "  [ ] compose.oss.yml updated: image kestrel-cognee:1.6.2-candidate@sha256:<digest>"
echo "  [ ] ENABLE_BACKEND_ACCESS_CONTROL explicitly set (1.6.2 defaults it ON)"
echo "  [ ] token-cap patches verified in candidate (hash-gated build)"
exit 1  # deliberate: this runbook is documentation until unlocked

# --- the switch (only after the gate above is removed) ---
# 1. ./ops/backup.sh                          # fresh backup
# 2. stop app:  lsof -nP -iTCP:8000 -sTCP:LISTEN -t | xargs kill
# 3. docker compose -f compose.oss.yml stop cognee-oss
# 4. docker compose -f compose.oss.yml up -d cognee-oss   # new image; migrations run
#    docker logs -f cognee-oss              # watch migrations to head
# 5. curl localhost:8888/health              # ready + version
# 6. start app (python3 app.py &)            # AUTH_MODE as before
# 7. GATES (all must pass in order):
#    a. curl localhost:8888/api/v1/datasets/  -> company_brain present
#    b. known-answer ask + /api/source open   -> identical citations
#    c. counts: datasets=1, graph_node=93, brain_access=2
# 8. on ANY gate failure -> ROLLBACK:
#    stop cognee-oss; docker compose -f compose.oss.yml down;
#    restore per ops/restore_lab.sh INTO THE LIVE project from the fresh backup;
#    revert compose image line; restart; re-run gates.
#    (git revert alone is NOT rollback — state was migrated.)
# 9. post-cutover: per-brain `rebuild` jobs are SEPARATE founder-approved batches.
