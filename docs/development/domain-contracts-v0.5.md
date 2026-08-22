# DeepAha Domain Contracts v0.5

Implementation: `IMPLEMENTED`

Engineering Gate: `OPEN`

Release Qualification: `NOT_STARTED`

Contract Maturity: `IMPLEMENTED` (not `STABLE`)

This document describes the additive Phase 6 contract layered on exact Phase 5 head
`8d9b36c96174bffb303e7f981bd1775ebd8fa672`. Local verification applies through
`66aaaac94ae8062740452daed6f855ee2b56f083`; remote exact-SHA evidence is pending.

## Compatibility boundary

- `contracts/schemas/v0.1.0` through `v0.4.0` remain byte-unchanged with the same import paths.
- Python v0.5 types live in `deepaha.contracts.phase6`; older modules are not moved or renamed.
- `--version 0.5.0` exports the v0.4 compatibility collection plus four new Phase 6 schemas.
- New persisted personal ProfileSnapshot rows are non-synthetic v0.5; existing v0.4 synthetic rows
  retain their schema/provenance boundary.

## UserState and purpose boundary

`UserStateSnapshotSchemaV05` is immutable and versioned. It binds the exact qualification profile
snapshot/version, nullable attributes, soft preferences, explicitly skipped fields, consent
version, allowed purposes, personalization switch, scenario clock and canonical input SHA-256.
Missing optional fields remain `None`; skipped and provided values cannot conflict.

The contract contains no name, phone, email, government identifier or free-form biography.
Services derive the owner from authentication and enforce current purposes on ranking/action reads
and writes. The contract does not define production identity or account lifecycle.

## Match and ranking boundary

Phase 6 reuses the v0.4 EligibilityResult and MatchSnapshot. One personal ranking snapshot fixes the
UserState/Profile versions, scenario clock, inclusive 90-day end, deterministic ranker version,
input hash and up to three ordered items. Every item points to an exact OpportunityVersion and
MatchSnapshot. `INELIGIBLE` cannot enter the priority list.

No v0.5 field represents a score, match percentage, probability, model confidence or LLM verdict.
Soft preference changes can reorder items but cannot change the underlying eligibility result.

## Personal action boundary

`PersonalActionSnapshotSchemaV05` stores an immutable version of saved state, explicit action state,
at most 20 structured material items, OpportunityVersion and last audit event. Event types are
limited to saved change, official-link open, material-plan change and action-state change. Writes
require owner scope and an idempotency key.

There is no feedback text/review state, reminder schedule, notification, Outbox, payment or
production release contract.

## Evidence status

The two profiles and three opportunities used in engineering tests are fixed CC0 synthetic inputs.
They do not prove real-user completion, comprehension, action or eligibility accuracy. v0.5 cannot
be marked `STABLE` until corresponding Release Qualification is `QUALIFIED`.
