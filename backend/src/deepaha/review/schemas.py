from typing import Annotated

from pydantic import ConfigDict, Field, StringConstraints, field_validator, model_validator

from deepaha.contracts.common import (
    EntityId,
    Instant,
    NonEmptyString,
    OpportunityPublicId,
    VersionNumber,
)
from deepaha.contracts.phase1 import ContractModel
from deepaha.contracts.phase7 import (
    FeedbackActorKind,
    FeedbackAdjudicationDecision,
    FeedbackClaimKind,
    FeedbackConfidenceBand,
    FeedbackEvidenceClass,
    FeedbackEvidenceRelation,
    FeedbackReviewStatus,
    FeedbackRiskLevel,
)

BoundedRationale = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
BoundedTarget = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


def _unique_ids(value: object) -> object:
    if not isinstance(value, (list, tuple)):
        return value
    normalized = tuple(sorted(value, key=str))
    if len(normalized) != len(set(normalized)):
        raise ValueError("evidence IDs must not contain duplicates")
    return normalized


class ReviewApiModel(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConfidenceAssessmentWrite(ReviewApiModel):
    evidence_complete: bool
    confidence_band: FeedbackConfidenceBand
    risk_level: FeedbackRiskLevel
    conflict: bool
    evidence_ref_ids: tuple[EntityId, ...] = Field(max_length=20)
    rationale: BoundedRationale

    _normalize_evidence_ref_ids = field_validator("evidence_ref_ids", mode="before")(_unique_ids)

    @model_validator(mode="after")
    def validate_complete_evidence(self) -> ConfidenceAssessmentWrite:
        if self.evidence_complete and not self.evidence_ref_ids:
            raise ValueError("complete assessment requires evidence")
        return self


class FeedbackAdjudicationWrite(ReviewApiModel):
    confidence_assessment_id: EntityId
    decision: FeedbackAdjudicationDecision
    evidence_ref_ids: tuple[EntityId, ...] = Field(max_length=20)
    reason: BoundedRationale

    _normalize_evidence_ref_ids = field_validator("evidence_ref_ids", mode="before")(_unique_ids)

    @model_validator(mode="after")
    def validate_confirmed_evidence(self) -> FeedbackAdjudicationWrite:
        if self.decision is FeedbackAdjudicationDecision.CONFIRMED and not self.evidence_ref_ids:
            raise ValueError("CONFIRMED adjudication requires evidence")
        return self


class ApprovedLabelWrite(ReviewApiModel):
    feedback_adjudication_id: EntityId
    approved_target_value: BoundedTarget
    evidence_ref_ids: tuple[EntityId, ...] = Field(min_length=1, max_length=20)

    _normalize_evidence_ref_ids = field_validator("evidence_ref_ids", mode="before")(_unique_ids)


class ReviewQueueItem(ReviewApiModel):
    review_case_id: EntityId
    feedback_event_id: EntityId
    version: VersionNumber
    status: FeedbackReviewStatus
    priority: Annotated[int, Field(ge=1, le=3)]
    due_at: Instant
    overdue: bool
    claim_kind: FeedbackClaimKind
    opportunity_public_id: OpportunityPublicId
    opportunity_title: NonEmptyString
    opportunity_version: VersionNumber
    created_at: Instant


class ReviewCaseHistoryItem(ReviewApiModel):
    version: VersionNumber
    status: FeedbackReviewStatus
    priority: Annotated[int, Field(ge=1, le=3)]
    due_at: Instant
    transition_reason: str
    created_at: Instant


class ReviewEvidenceItem(ReviewApiModel):
    evidence_ref_id: EntityId
    document_id: EntityId
    locator_kind: NonEmptyString
    locator_value: str | None
    relation: FeedbackEvidenceRelation
    actor_kind: FeedbackActorKind
    note: str | None
    created_at: Instant


class ConfidenceAssessmentResult(ReviewApiModel):
    confidence_assessment_id: EntityId
    review_case_id: EntityId
    review_case_version: VersionNumber
    evidence_complete: bool
    confidence_band: FeedbackConfidenceBand
    risk_level: FeedbackRiskLevel
    conflict: bool
    evidence_ref_ids: tuple[EntityId, ...]
    rationale: BoundedRationale
    created_at: Instant


class FeedbackAdjudicationResult(ReviewApiModel):
    feedback_adjudication_id: EntityId
    review_case_id: EntityId
    review_case_version: VersionNumber
    confidence_assessment_id: EntityId
    decision: FeedbackAdjudicationDecision
    evidence_ref_ids: tuple[EntityId, ...]
    reason: BoundedRationale
    created_at: Instant
    resulting_case_version: VersionNumber


class ApprovedLabelResult(ReviewApiModel):
    approved_feedback_label_id: EntityId
    feedback_event_id: EntityId
    feedback_adjudication_id: EntityId
    claim_kind: FeedbackClaimKind
    approved_target_value: BoundedTarget
    evidence_ref_ids: tuple[EntityId, ...]
    evidence_class: FeedbackEvidenceClass
    created_at: Instant


class ReviewCaseDetail(ReviewApiModel):
    case: ReviewQueueItem
    user_statement: BoundedRationale | None
    structured_reason_code: str
    match_snapshot_id: EntityId
    history: tuple[ReviewCaseHistoryItem, ...]
    evidence: tuple[ReviewEvidenceItem, ...]
    latest_assessment: ConfidenceAssessmentResult | None
    latest_adjudication: FeedbackAdjudicationResult | None
    approved_label_id: EntityId | None


class ReviewQueuePage(ReviewApiModel):
    items: tuple[ReviewQueueItem, ...]


__all__ = [
    "ApprovedLabelResult",
    "ApprovedLabelWrite",
    "ConfidenceAssessmentResult",
    "ConfidenceAssessmentWrite",
    "FeedbackAdjudicationResult",
    "FeedbackAdjudicationWrite",
    "ReviewCaseDetail",
    "ReviewCaseHistoryItem",
    "ReviewEvidenceItem",
    "ReviewQueueItem",
    "ReviewQueuePage",
]
