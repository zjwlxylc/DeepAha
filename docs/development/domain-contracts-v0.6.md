# DeepAha Domain Contracts v0.6

Implementation: `IMPLEMENTED`

Engineering Gate: `CLOSED`

Release Qualification: `NOT_STARTED`

Contract Maturity: `IMPLEMENTED` (not `STABLE`)

This additive Phase 7 contract is implemented on exact Phase 6 ancestor
`7f2cebc2afcfc6cb7061ed5bb91d79b824e91a3d`. Engineering evidence applies through exact candidate
`63536985d5b03b3ad5dbb5bea1cf82120ee866fc`; GitHub Actions run `32571667136` completed all eight
required jobs successfully. This does not make v0.6 `STABLE`.

## Compatibility boundary

- `contracts/schemas/v0.1.0` through `v0.5.0` remain byte-unchanged.
- Python v0.6 types live in `deepaha.contracts.phase7`; older modules/imports remain available.
- `--version 0.6.0` exports 11 new Phase 7 schemas and one strict synthetic example.
- v0.6 is necessary because v0.5 has no review identity, confidence/adjudication, label asset,
  dual-track run or non-deploying release decision.

## Immutable governance chain

The contract keeps distinct immutable/versioned facts:

```text
FeedbackEvent -> FeedbackEvidenceLink -> FeedbackReviewCaseSnapshot
  -> FeedbackConfidenceAssessment -> FeedbackAdjudication
  -> ApprovedFeedbackLabel -> ImprovementCandidate
  -> OfflineEvaluationCandidate -> ShadowTestCandidate -> ReleaseGateDecision
```

FeedbackEvent binds exact ranking, MatchSnapshot, OpportunityVersion, UserState version, consent,
contract version and canonical input digest. Review results never become fields on the raw event.
Evidence links accept only governed EvidenceRefs for the bound version.

## Identity and decision boundary

Personal and reviewer identities are server-derived and purpose-limited. Labels require confirmed
authenticated adjudication and retain real/synthetic provenance. Neither a label nor a validation
candidate mutates an online RuleSet, EligibilityResult, MatchSnapshot, ranking or OpportunityVersion.
There is no LLM final decision or online-learning field/path.

## Dual-track boundary

Simulation and consented-human ValidationRuns use different evidence classes and metric contracts.
The fixed CC0 engineering fixture has one workflow, one `EXPLANATION_CLARITY` direction and zero
human participants. Synthetic-only evidence forces `HOLD_MISSING_HUMAN_EVIDENCE` and cannot qualify
Release Qualification.

v0.6 cannot become `STABLE` unless its corresponding Release Qualification is later `QUALIFIED`.
