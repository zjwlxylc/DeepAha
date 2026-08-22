# Phase 7 Dual-track Validation Evidence

## Synthetic engineering track

The only executed workflow uses
`backend/tests/fixtures/feedback/phase7-feedback.json`, whose manifest fixes:

- `synthetic = true`;
- `contains_personal_data = false`;
- `business_truth = false`;
- `release_qualification_eligible = false`;
- `workflow_count = 1`;
- `direction_count = 1`;
- `human_participant_count = 0`.

Its evidence class is `SYNTHETIC_FEEDBACK_WORKFLOW_ONLY`. It creates an explicit synthetic reviewer
adjudication and approved label only to prove the governed workflow. Integer replay/case counts are
engineering evidence, never a trust, comprehension, action, retention, payment or market metric.

The fixture selects `EXPLANATION_CLARITY` as its sole direction. This prevents multi-variable
confounding in the executable slice but is not approval to change a real explanation component.

## Human-participant track

Status: `NOT_STARTED`. Real participants: `0`.

The human contract requires evidence class `CONSENTED_HUMAN_PARTICIPANT` and separate governed
participant counts for structured feedback, comprehension, cognitive load, high-intent action and
withdrawal/exclusion. It rejects synthetic manifests, simulation profile IDs and simulation metric
names. No human ValidationRun is created by the fixture or verifier.

## Gate result

The immutable offline and shadow candidates are separate from the selected improvement. Because the
human track is absent, the only valid decision is:

```text
HOLD_MISSING_HUMAN_EVIDENCE
```

`CANDIDATE_ACCEPTED_FOR_FUTURE_IMPLEMENTATION` would only authorize a later versioned engineering
candidate; it would still not deploy or mutate a live component. No such acceptance exists here.
Release Qualification remains `NOT_STARTED`.
