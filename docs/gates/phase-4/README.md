# Phase 4 Gate — Rules, Eligibility and Evaluation

Implementation: `IMPLEMENTED`

Engineering Gate: `OPEN` pending exact-SHA remote CI.

Release Qualification: `NOT_STARTED`

Contract Maturity: `IMPLEMENTED` (not `STABLE`)

This stacked implementation includes Phase 3 closing commit
`8003a1c2ab2485a1173b2d4bb9deafbbab6e949c` through explicit merge commit
`09526c61a1a0410e9a9127c989ecfaecf3f0ea02`.

## Evidence state

- Implemented: rules, four-state eligibility, replay and evaluation code exists on the integrated
  closing baseline.
- Locally verified: `scripts/verify-phase4.ps1` and `scripts/verify.ps1` passed at
  `2026-08-22T01:27:25Z`; the contract compatibility suite also passed 73/73.
- remote CI: pending for the exact integrated candidate; Engineering Gate remains `OPEN` until
  all required jobs succeed.
- Synthetic evaluation: fixed CC0 fixtures reproduce 12 expected statuses with zero unexpected
  `INELIGIBLE`; this is not a production accuracy claim.
- Release Qualification has not started because no governed real annotated dataset, real-user
  evidence or production-similar qualification run exists.

## Decision

Phase 4 implementation exists and its closing baseline is integrated. Engineering Gate remains
`OPEN` only for the outstanding exact-SHA remote CI evidence. Release Qualification remains
`NOT_STARTED`; the package does not authorize merge, release, `STABLE`, or establish the planned
`<=0.5%` false-negative threshold.

Draft PR: [#4](https://github.com/zjwlxylc/DeepAha/pull/4), `OPEN`, `DRAFT`, `UNMERGED`;
base `codex/phase-3-opportunity-resolution`, head
`codex/phase-4-rules-eligibility-evaluation`.

## Evidence map

- Acceptance: [acceptance-results.md](./acceptance-results.md)
- Code review: [code-review.md](./code-review.md)
- Tests: [test-summary.md](./test-summary.md)
- Fixed evaluation: [evaluation-summary.md](./evaluation-summary.md)
- Security and compliance: [security-and-compliance.md](./security-and-compliance.md)
- Deferred work: [deferred-decisions.md](./deferred-decisions.md)
- Post-Gate procedure: [operations.md](./operations.md)
