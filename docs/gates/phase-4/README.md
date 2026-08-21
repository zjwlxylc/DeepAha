# Phase 4 Gate — Rules, Eligibility and Evaluation

Status: `IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES`

This is a stacked candidate built from Phase 3 candidate commit
`5a5847be266980e83eccd8718c23b77e788ee481`. The exact verified candidate SHA is
`94bab9e7397a8ccb43d95da3f68bfa1fc6df9a07`.

## Evidence state

- Implemented: candidate rules, four-state eligibility, replay and evaluation code exists.
- Locally verified: isolated Phase 4 verifier and root verifier passed at
  `2026-08-21T22:41:13Z` on the exact pushed candidate SHA.
- remote CI: [Actions run 32534085134](https://github.com/zjwlxylc/DeepAha/actions/runs/32534085134)
  completed successfully; `backend-quality`, `web-quality`, `integration`,
  `phase3-resolution`, and `phase4-eligibility` all concluded `success`.
- Synthetic evaluation: fixed CC0 fixtures reproduce 12 expected statuses with zero unexpected
  `INELIGIBLE`; this is not a production accuracy claim.
- Blocked: Phase 2 is `OPEN`; Phase 3 is `BLOCKED_BY_PHASE2`; v0.2, v0.3 and v0.4 remain
  `PROPOSED`.

## Decision

Phase 4 is a reviewable candidate only. This package does not close the Phase 3 or Phase 4 Gate,
promote any contract to `STABLE`, authorize merge or release, or establish the planned `<=0.5%`
false-negative threshold. Any Phase 2 or Phase 3 closing-commit contract change requires rebasing
onto the exact closing commit, compatibility review and complete re-verification.

Draft PR: [#4](https://github.com/zjwlxylc/DeepAha/pull/4), `OPEN`, `DRAFT`, `UNMERGED`;
base `codex/phase-3-opportunity-resolution`, head
`codex/phase-4-rules-eligibility-evaluation`.

## Evidence map

- Acceptance: [acceptance-results.md](./acceptance-results.md)
- Tests: [test-summary.md](./test-summary.md)
- Fixed evaluation: [evaluation-summary.md](./evaluation-summary.md)
- Security and compliance: [security-and-compliance.md](./security-and-compliance.md)
- Deferred work: [deferred-decisions.md](./deferred-decisions.md)
- Post-Gate procedure: [operations.md](./operations.md)
