# Kestrel Engineering Workflow

## Engineering Principles
1. **Spec First:** Clear specification with unambiguous acceptance criteria before coding.
2. **Plan Before Code:** Structured phases and tasks with tracked status.
3. **TDD:** Write failing tests, implement minimal code, verify green, refactor.
4. **Conventional Commits:** `<type>(<scope>): <description>` format.
5. **Safe Verification Battery:** Run `./verify.sh --quick` or full `./verify.sh` on isolated/lab tiers. Never write to live database (5433) without explicit instruction.
6. **Zero Secrets Staged:** `./ops/check_secrets.sh --all` must exit 0 before every push.
