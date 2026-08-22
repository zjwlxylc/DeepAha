# Phase 4 Test Summary

## Evidence state

- Implementation: `IMPLEMENTED`; isolated verifier and CI definitions are present on integrated
  merge commit `09526c61a1a0410e9a9127c989ecfaecf3f0ea02`.
- Engineering Gate: `CLOSED`.
- Release Qualification: `NOT_STARTED`.
- Contract Maturity: `IMPLEMENTED` (not `STABLE`).
- Locally verified: `scripts/verify-phase4.ps1` and `scripts/verify.ps1` passed at
  `2026-08-22T01:33:31Z`.
- remote CI: exact candidate `1160c96f446f92a5cdce97b4aef11a7200262f0b` passed
  [run 32543551989](https://github.com/zjwlxylc/DeepAha/actions/runs/32543551989).
- Synthetic evaluation: actual-engine integration uses fixed fixtures only.

## Final local results

- `scripts/verify-phase4.ps1`: 126 Python files formatted; Ruff passed; mypy passed on 120
  source files; 76 scoped offline tests passed; 13 Phase 4 integration tests passed; 0004
  downgrade/re-upgrade and Alembic drift check passed.
- Synthetic result printed by the verifier: 12 Golden cases, 12 expected statuses reproduced,
  zero unexpected `INELIGIBLE`, zero replay mismatches.
- `scripts/verify.ps1`: backend 323 passed and 122 deselected by marker; Web lint, typecheck,
  Vitest and Next.js production build passed.
- v0.1–v0.4 compatibility suite: 73 passed; the v0.4 derived `source-endpoint` copy now matches
  the authorized v0.2/v0.3 closing-contract bytes.

## Remote job conclusions

| Job | Conclusion |
|---|---|
| `backend-quality` | `success` |
| `web-quality` | `success` |
| `integration` | `success` |
| `phase3-resolution` | `success` |
| `phase4-eligibility` | `success` |

Draft PR [#4](https://github.com/zjwlxylc/DeepAha/pull/4) is
`OPEN/DRAFT/UNMERGED`; no merge, release, Release Qualification or `STABLE` promotion is
authorized.
