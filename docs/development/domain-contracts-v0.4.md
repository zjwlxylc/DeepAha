# DeepAha Domain Contracts v0.4

Status: `PROPOSED`

Implementation state: `IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES`

This document describes the Phase 4 candidate contract layered on the exact Phase 3 candidate
commit `5a5847be266980e83eccd8718c23b77e788ee481`. Phase 2 remains `OPEN`, Phase 3 remains
`BLOCKED_BY_PHASE2`, and v0.2/v0.3/v0.4 remain `PROPOSED`. This contract is not released,
stable, or final-verified.

## Compatibility boundary

- `contracts/schemas/v0.1.0`, `v0.2.0`, and `v0.3.0` retain their existing paths and bytes.
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
versioned records. A MatchSnapshot fixes Opportunity and RuleSet versions, ProfileSnapshot ID,
compiler/engine versions, professional catalog/mapping versions, scenario clock, every rule
outcome, EvidenceRef IDs, and a canonical input SHA-256. Re-evaluating identical inputs returns
the same logical snapshot; changing any fixed input produces an explainable new snapshot.

Evaluation fixtures and examples are synthetic. Synthetic results support coverage, boundary,
counterfactual, replay, and error-negative protection checks only. They do not prove real-user
trust, retention, willingness to pay, or production accuracy. The planned `<=0.5%` false-negative
threshold requires a separately governed real annotated evaluation.

## Non-goals

This candidate does not implement a public opportunity index or UI, real user profile collection,
ranking, personal actions, LLM/Model Gateway, Redis/Valkey/Celery, pgvector, OCR, notifications,
feedback, commercialization, production cloud, or Phase 2 live collection changes.

## Upstream Gate closure requirement

If a Phase 2 or Phase 3 closing commit changes a base schema, migration, identifier, evidence
meaning, or replay behavior, Phase 4 must update to the exact Phase 3 closing commit, repeat the
compatibility review, re-export v0.4 only, and rerun the complete root and Phase 4 verification
before any promotion decision. Promotion to `STABLE` or Gate closure requires separate authority
and evidence.
