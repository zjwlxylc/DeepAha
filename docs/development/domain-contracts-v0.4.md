# DeepAha Domain Contracts v0.4

Implementation: `IMPLEMENTED`

Engineering Gate: `CLOSED`

Release Qualification: `NOT_STARTED`

Contract Maturity: `IMPLEMENTED` (not `STABLE`)

This document describes the Phase 4 contract layered on the exact Phase 3 closing commit
`8003a1c2ab2485a1173b2d4bb9deafbbab6e949c`, integrated by merge commit
`09526c61a1a0410e9a9127c989ecfaecf3f0ea02`. Local verification and exact candidate SHA
`1160c96f446f92a5cdce97b4aef11a7200262f0b` remote CI support the closed Engineering Gate.
The contract is not released, `STABLE`, or Release Qualified.

## Compatibility boundary

- `contracts/schemas/v0.1.0`, `v0.2.0`, and `v0.3.0` retain their paths and imports. The Phase 3
  closing commit intentionally updates the v0.2/v0.3 `source-endpoint` schema bytes; the v0.4
  compatibility copy was re-exported to the identical closing-contract bytes.
- Python v0.4 types live in `deepaha.contracts.phase4`; no older import is moved or renamed.
- `--version 0.4.0` exports a compatibility collection to `contracts/schemas/v0.4.0` only.
- Phase 4 adds `rule-set`, `rule`, `rule-evidence`, `profile-snapshot`,
  `eligibility-result`, `match-snapshot`, and `evaluation-run` schemas.

## Eligibility and evidence invariants

Eligibility has exactly four states: `ELIGIBLE`, `LIKELY_ELIGIBLE`, `UNCERTAIN`, and
`INELIGIBLE`. An `INELIGIBLE` result requires at least one deterministic conflict backed by an
official EvidenceRef. Missing, ambiguous, conflicting, or semantic-only facts cannot produce an
error-negative conclusion. Eligibility results contain neither ranking scores nor probabilities.

Evidence precedence is fixed:

1. `LATEST_OFFICIAL_CORRECTION` — 600
2. `FORMAL_OFFICIAL_ATTACHMENT` — 500
3. `ORIGINAL_OFFICIAL_NOTICE` — 400
4. `OFFICIAL_FAQ_GUIDANCE` — 300
5. `HUMAN_APPROVED_MAPPING` — 200
6. `LLM_SEMANTIC_INFERENCE` — 100

The final value is reserved for contract-boundary and negative tests. Phase 4 contains no LLM
execution path.

## Version and replay boundary

RuleSet, Rule, ProfileSnapshot, EligibilityResult, MatchSnapshot, and EvaluationRun are immutable
versioned records. A MatchSnapshot fixes Opportunity and RuleSet versions, ProfileSnapshot ID/version,
compiler/engine versions, professional catalog/mapping versions, scenario clock, every rule
outcome, EvidenceRef IDs, and a canonical input SHA-256. Re-evaluating identical inputs returns
the same logical snapshot; changing any fixed input produces an explainable new snapshot.

An EvaluationRun fixes the fixture-manifest SHA-256, scenario clock, component versions, report
SHA-256, ordered case results, each case input SHA-256, MatchSnapshot ID, and integer safety
counts. Its evidence label is always `SYNTHETIC_EVALUATION_ONLY`; unexpected `INELIGIBLE` case
IDs are explicit and never converted into a production-rate claim.

Evaluation fixtures and examples are synthetic. Synthetic results support coverage, boundary,
counterfactual, replay, and error-negative protection checks only. They do not prove real-user
trust, retention, willingness to pay, or production accuracy. The planned `<=0.5%` false-negative
threshold requires a separately governed real annotated evaluation.

## Non-goals

This candidate does not implement a public opportunity index or UI, real user profile collection,
ranking, personal actions, LLM/Model Gateway, Redis/Valkey/Celery, pgvector, OCR, notifications,
feedback, commercialization, production cloud, or Phase 2 live collection changes.

## Closing-baseline integration

The current Phase 2 and Phase 3 closing commits are integrated. Compatibility review covered
schema bytes/imports, migrations, identifiers, evidence semantics and replay behavior; only the
derived v0.4 `source-endpoint` compatibility copy required regeneration. If a later authorized
closing commit supersedes either baseline, merge the new exact Phase 3 commit without rewriting
history, repeat this review, re-export v0.4 only, and rerun the complete root and Phase 4
verification before another promotion decision. `STABLE` still requires separate Release
Qualification evidence and authority.
