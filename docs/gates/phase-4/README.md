# Phase 4 Gate — Rules, Eligibility and Evaluation

Status: `IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES`

This is a stacked candidate built from Phase 3 candidate commit
`5a5847be266980e83eccd8718c23b77e788ee481`. The implemented code checkpoint before this
evidence package is `fe96cabda9f34187b02604a725d8da7c57b30cd3`.

## Evidence state

- Implemented: candidate rules, four-state eligibility, replay and evaluation code exists.
- Locally verified: isolated Phase 4 verifier and root verifier passed on the Task 9 candidate
  worktree based on `fe96cabda9f34187b02604a725d8da7c57b30cd3`.
- remote CI: pending the Task 9 evidence commit and stacked draft PR.
- Synthetic evaluation: fixed CC0 fixtures reproduce 12 expected statuses with zero unexpected
  `INELIGIBLE`; this is not a production accuracy claim.
- Blocked: Phase 2 is `OPEN`; Phase 3 is `BLOCKED_BY_PHASE2`; v0.2, v0.3 and v0.4 remain
  `PROPOSED`.

## Decision

Phase 4 is a reviewable candidate only. This package does not close the Phase 3 or Phase 4 Gate,
promote any contract to `STABLE`, authorize merge or release, or establish the planned `<=0.5%`
false-negative threshold. Any Phase 2 or Phase 3 closing-commit contract change requires rebasing
onto the exact closing commit, compatibility review and complete re-verification.

## Evidence map

- Acceptance: [acceptance-results.md](./acceptance-results.md)
- Tests: [test-summary.md](./test-summary.md)
- Fixed evaluation: [evaluation-summary.md](./evaluation-summary.md)
- Security and compliance: [security-and-compliance.md](./security-and-compliance.md)
- Deferred work: [deferred-decisions.md](./deferred-decisions.md)
- Post-Gate procedure: [operations.md](./operations.md)
