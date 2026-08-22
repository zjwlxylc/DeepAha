# DeepAha Domain Contract v0.3

Implementation Status: `IMPLEMENTED`

Engineering Gate: `CLOSED`

Release Qualification: `NOT_STARTED`

Contract Maturity: `IMPLEMENTED` (not `STABLE`)

This document defines the implemented Phase 3 contract for Opportunity resolution,
immutable versions, change events and audited identity actions. Phase 2 closing commit
`6c8a8fb63c68cfbb0f4cf54b6032bfb49a0ef65c` is an ancestor of the Phase 3 branch and the
integrated contract has been revalidated. This is not a stable or released contract:
Phase 3 Release Qualification has not started.

## Compatibility boundary

- v0.1 and v0.2 Python import paths and canonical checked-in Schema bytes remain owned by
  their versions; v0.3 does not overwrite either directory.
- v0.3 re-exports the v0.2-compatible schema set and adds six Phase 3 objects.
- Exporting v0.3 writes only `contracts/schemas/v0.3.0/`.
- The exporter default remains v0.1; callers must explicitly request `--version 0.3.0`.
- All examples are synthetic and assert no real source or business fact.

## Core invariant

The Phase 3 chain is:

```text
Document + EvidenceRef
  -> DocumentOpportunityLink or OpportunityResolutionCandidate
  -> OpportunityVersion
  -> OpportunityEvent
  -> current Opportunity projection
```

`Document` is not `Opportunity`. A primary notice, attachment, position table,
correction, deadline extension and cancellation can refer to one stable Opportunity.
History is append-only: current projection changes never overwrite a Version, Event,
alias or identity action.

## Controlled values

```text
OpportunityDocumentRole =
  PRIMARY_NOTICE | ATTACHMENT | POSITION_TABLE | CORRECTION |
  DEADLINE_EXTENSION | CANCELLATION | RESULT | OFFICIAL_GUIDANCE

ResolutionDisposition = CREATED | LINKED | NEEDS_REVIEW

OpportunityEventType =
  CREATED | UPDATED | CORRECTED | DEADLINE_CHANGED |
  ATTACHMENT_REPLACED | CANCELLED | REOPENED

OpportunityAliasType = TITLE | URL | EXTERNAL_ID

OpportunityReviewStatus = NOT_REQUIRED | PENDING | APPROVED | REJECTED

OpportunityIdentityActionType =
  MERGE | SPLIT | MERGE_REVERSAL | SPLIT_REVERSAL

OpportunityIdentityMemberRole = SOURCE | TARGET | PARENT | CHILD
```

`SnapshotField` is limited to:

```text
canonical_title
type
issuer_name
jurisdiction
status
published_at
application_window.opens_on
application_window.closes_on
application_window.timezone
application_url
attachment_urls
locations
```

No eligibility, profile or ranking field belongs to v0.3.

## OpportunitySnapshot

| Field | Type | Rule |
| --- | --- | --- |
| `canonical_title` | non-empty string | Required |
| `type` | `OpportunityTypeV02` | Required |
| `issuer_name` | non-empty string | Required |
| `jurisdiction` | non-empty string or null | No inference from missing text |
| `status` | `OpportunityStatus` | Required |
| `published_at` | timezone-aware instant or null | Normalized to UTC |
| `application_window.opens_on` | local date or null | Must not be after `closes_on` |
| `application_window.closes_on` | local date or null | Must not be before `opens_on` |
| `application_window.timezone` | IANA timezone or null | Unknown zones are rejected |
| `application_url` | absolute HTTP(S) URL or null | Required only when evidenced |
| `attachment_urls` | unique URL tuple | Sorted during validation |
| `locations` | unique non-empty string tuple | Sorted during validation |

## OpportunityFieldEvidence

| Field | Type | Rule |
| --- | --- | --- |
| `field_path` | `SnapshotField` | One current evidence item per field |
| `precedence` | integer 100–600 | Derived by the system, not user confidence |
| `evidence_ref_id` | UUIDv7 | References a persisted `EvidenceRef` |
| `effective_at` | timezone-aware instant | Normalized to UTC |

Precedence follows the fixed product rule:

```text
600 latest official correction
500 formal official attachment or position table
400 original official primary notice
300 official FAQ or guidance
200 human-approved mapping
100 deterministic semantic candidate
```

Phase 3 does not implement LLM extraction. The lowest level is reserved for later
candidate generation and cannot produce an automatic hard merge or final fact.

## OpportunityFieldChange

| Field | Type | Rule |
| --- | --- | --- |
| `field_path` | `SnapshotField` | Controlled field path |
| `before` | JSON value or null | Previous canonical value |
| `after` | JSON value or null | New canonical value |
| `evidence_ref_id` | UUIDv7 | Evidence for the proposed value |

`before` and `after` must differ. A first version represents newly established fields
with `before = null`.

## OpportunityVersion

| Field | Type | Rule |
| --- | --- | --- |
| `opportunity_id` | UUIDv7 | Stable internal identity |
| `version` | positive integer | Starts at 1 and is continuous per Opportunity |
| `effective_from` | instant | Business effective time |
| `source_document_id` | UUIDv7 | Triggering Document |
| `source_evidence_ref_id` | UUIDv7 | Triggering EvidenceRef |
| `snapshot` | `OpportunitySnapshot` | Full canonical snapshot |
| `field_evidence` | tuple | Unique field paths |
| `changes` | non-empty tuple | Unique field paths with matching evidence |
| `content_sha256` | lowercase SHA-256 | Canonical `snapshot + field_evidence` digest |
| `review_status` | `OpportunityReviewStatus` | Review state for this version |
| `created_at` | instant | Must not precede `effective_from` |

Version rows are immutable. Creating a later version never updates or deletes an older
version.

## OpportunityEvent

| Field | Type | Rule |
| --- | --- | --- |
| `event_id` | UUIDv7 | Immutable event identity |
| `opportunity_id` | UUIDv7 | Stable Opportunity identity |
| `from_version` | positive integer or null | Null only for creation |
| `to_version` | positive integer | Target Version |
| `event_type` | `OpportunityEventType` | Controlled change class |
| `changed_fields` | non-empty unique tuple | Must equal change order |
| `changes` | non-empty tuple | Field-level diff |
| `source_document_id` | UUIDv7 | Triggering Document |
| `source_evidence_ref_id` | UUIDv7 | Triggering EvidenceRef |
| `detected_at` | instant | Detection time |

`CREATED` requires `from_version = null` and `to_version = 1`. Every other event
requires `to_version = from_version + 1`. One version transition has one event.

## DocumentOpportunityLink

| Field | Type | Rule |
| --- | --- | --- |
| `link_id` | UUIDv7 | Immutable link identity |
| `document_id` | UUIDv7 | Linked Document |
| `opportunity_id` | UUIDv7 | Linked Opportunity |
| `role` | `OpportunityDocumentRole` | Document meaning in the lifecycle |
| `resolution_key` | non-empty string | Deterministic winning key |
| `resolver_version` | non-empty string | Resolver code version |
| `source_evidence_ref_id` | UUIDv7 | Evidence used for the link |
| `linked_at` | instant | Start of active interval |
| `ended_at` | instant or null | End of active interval |
| `ended_by_identity_action_id` | UUIDv7 or null | Action that ended the interval |

The two end fields must both be present or both be absent. Ending a link preserves the
historical row.

## OpportunityResolutionCandidate

| Field | Type | Rule |
| --- | --- | --- |
| `candidate_id` | UUIDv7 | Candidate identity |
| `document_id` | UUIDv7 | Input Document |
| `candidate_opportunity_ids` | unique UUIDv7 tuple | May be empty when no safe identity exists |
| `proposed_role` | `OpportunityDocumentRole` | Proposed relation |
| `proposed_snapshot` | snapshot or null | Parsed proposal, not accepted fact |
| `reason_codes` | non-empty unique string tuple | Machine-readable reasons |
| `resolver_version` | non-empty string | Resolver code version |
| `source_evidence_ref_id` | UUIDv7 | Evidence for review |
| `review_status` | `PENDING` | Phase 3 automatic path cannot approve |
| `created_at` | instant | Candidate creation time |

Candidates do not create a formal Version or change the current projection.

## OpportunityAlias

| Field | Type | Rule |
| --- | --- | --- |
| `alias_id` | UUIDv7 | Immutable alias identity |
| `opportunity_id` | UUIDv7 | Owning Opportunity |
| `alias_type` | `TITLE`, `URL` or `EXTERNAL_ID` | Controlled type |
| `alias_value` | non-empty string | Original value |
| `normalized_value` | non-empty string | Matching value |
| `source_id` | UUIDv7 or null | Required for `EXTERNAL_ID` |
| `source_document_id` | UUIDv7 | Origin Document |
| `source_evidence_ref_id` | UUIDv7 | Origin EvidenceRef |
| `created_at` | instant | Creation time |

`public_id` is never represented as a movable alias. A merge changes canonical identity
resolution only; it does not overwrite or reuse any public ID.

## OpportunityIdentityAction

| Field | Type | Rule |
| --- | --- | --- |
| `action_id` | UUIDv7 | Immutable action identity |
| `action_type` | merge/split/reversal enum | Controlled action |
| `members` | unique Opportunity members | Role cardinalities below |
| `reversal_of_action_id` | UUIDv7 or null | Required only for reversal |
| `actor` | non-empty string | Human or controlled system actor |
| `reason` | non-empty string | Auditable reason |
| `source_document_id` | UUIDv7 or null | Paired with evidence |
| `source_evidence_ref_id` | UUIDv7 or null | Paired with Document |
| `occurred_at` | instant | Action time |

- Merge and merge reversal have exactly one target and at least one source.
- Split and split reversal have exactly one parent and at least two children.
- A normal action forbids `reversal_of_action_id`; a reversal requires it.
- Reversal members copy the original action members. The contract validates their shape;
  the persistence service validates exact equality and single reversal.
- Identity actions never delete Opportunities, public IDs, Versions or Events.

## Stable identity and conservative resolution

Stable public IDs use the first accepted primary strong key:

```text
opp_ + first_32_lowercase_hex(
  sha256("deepaha:opportunity:v0.3:" + primary_identity_key)
)
```

The Resolver can auto-link only a unique official strong key: explicit related Document,
source-scoped external ID, or canonical official URL. A conflicting strong key, weak
fingerprint, insufficient primary key, non-primary create attempt or lower-authority
conflict becomes `NEEDS_REVIEW`. Title similarity alone never hard-merges Opportunities.

## Gate and promotion rule

The v0.3 implementation and Engineering Gate are complete on the integrated Phase 2
closing baseline. That engineering conclusion does not qualify real-world resolution or
change-detection performance. Phase 3 Release Qualification remains `NOT_STARTED`, so
v0.3 remains `IMPLEMENTED`; it cannot become `STABLE`, merge or release on this evidence.
