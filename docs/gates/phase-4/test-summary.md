# Phase 4 Test Summary

## Evidence state

- Implemented: isolated verifier and CI definitions are included in the Task 9 candidate.
- Locally verified: `scripts/verify-phase4.ps1` and `scripts/verify.ps1` passed.
- remote CI: pending an exact Actions run and job conclusion.
- Synthetic evaluation: actual-engine integration uses fixed fixtures only.
- Blocked: passing tests cannot close upstream or Phase 4 Gates.

## Final local results

- `scripts/verify-phase4.ps1`: 126 Python files formatted; Ruff passed; mypy passed on 120
  source files; 76 scoped offline tests passed; 13 Phase 4 integration tests passed; 0004
  downgrade/re-upgrade and Alembic drift check passed.
- Synthetic result printed by the verifier: 12 Golden cases, 12 expected statuses reproduced,
  zero unexpected `INELIGIBLE`, zero replay mismatches.
- `scripts/verify.ps1`: backend 319 passed and 120 deselected by marker; Web lint, typecheck,
  Vitest and Next.js production build passed.
- Fixture regeneration before the final verifier: 6 JSON hashes unchanged.
- v0.1/v0.2/v0.3 schema working-tree diff: empty.

The exact evidence-commit SHA and remote CI URLs remain pending until this document is committed
and pushed.
