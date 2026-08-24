# P9-B Fact Promotion & Dormant Unit Rules — Code Review

Date: 2026-08-24 (Asia/Shanghai)

## Review boundary

This review covers migration `20260824_0013`, v0.8 extraction/fact/rule contracts, FactLifecycle and
RulePromotion services, PostgreSQL guards, dormant UnitRuleSet persistence and the Slice verifier.
It does not approve Gold labels, benchmark results, external model egress, production eligibility or
Release Qualification.

The environment does not authorize a separate review agent. This is an explicit second-pass diff
review, not independent human annotation, adjudication or accountable product approval.

## Findings resolved before commit

| Original severity | Finding | Resolution and regression evidence |
| --- | --- | --- |
| P1 | Autogeneration placed the two prerequisite unique constraints after new composite foreign keys. | Both constraints now precede all dependent tables; clean-database upgrade and drift checks pass. |
| P1 | The cyclic transition-to-dependency FK used `use_alter` but was not emitted by the generated table operation, and its derived name exceeded PostgreSQL's identifier limit. | Migration explicitly creates a short named FK after both tables; `alembic check` reports no drift. |
| P1 | Service code copied relation/precedence graph versions, but a direct FactSet insert was not DB-bound to the frozen revision snapshot. | FactSet insert guard now requires exact frozen revision graph versions; a PostgreSQL negative test exercises rejection. |
| P1 | RuleCandidate Evidence subset validation existed in the service but not at transaction commit. | A deferred DB guard proves each candidate EvidenceRef is reachable through a selected VerifiedFact. |
| P2 | Initial integration setup omitted the mandatory Phase 3 first-version change item. | The synthetic fixture now satisfies the unchanged Phase 3 contract; no production code was relaxed. |

## Final review result

- P0: `0`
- P1: `0`
- P2: `0`
- Migration: forward/additive; populated fact history refuses downgrade.
- Legacy read paths: no P9-B import/query was added to Phase 4–8 production readers.
- Unit rules: compile boundary rejects legacy RuleSet output; persistence is fixed to `DORMANT`.
- Gold/human boundary: all identities and labels in tests are explicitly synthetic engineering
  fixtures; real independent evidence remains `0 / NOT_OBSERVED`.
- Secret/content review: no credential file was read; no provider request or real response body was
  added.

Verdict: `FACT_PROMOTION_DIFF_REVIEW_PASS`, subject to the fresh formal verifier evidence in
`P9B_FACT_PROMOTION_TEST_SUMMARY.md` and a dedicated local commit.
