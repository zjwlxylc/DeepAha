# Phase 4 Test Summary

## Evidence state

- Implemented: isolated verifier and CI definitions are included in exact candidate
  `94bab9e7397a8ccb43d95da3f68bfa1fc6df9a07`.
- Locally verified: `scripts/verify-phase4.ps1` and `scripts/verify.ps1` passed at
  `2026-08-21T22:41:13Z`.
- remote CI: [run 32534085134](https://github.com/zjwlxylc/DeepAha/actions/runs/32534085134)
  concluded `success`.
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

## Remote job conclusions

| Job | Conclusion |
|---|---|
| `backend-quality` | `success` |
| `web-quality` | `success` |
| `integration` | `success` |
| `phase3-resolution` | `success` |
| `phase4-eligibility` | `success` |

Draft PR [#4](https://github.com/zjwlxylc/DeepAha/pull/4) is
`OPEN/DRAFT/UNMERGED` and remains blocked from merge or promotion.
