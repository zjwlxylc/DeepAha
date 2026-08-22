from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, StringConstraints, field_validator, model_validator

from deepaha.contracts.common import EntityId, Instant, OpportunityPublicId, VersionNumber
from deepaha.contracts.phase1 import ContractModel
from deepaha.contracts.phase7 import (
    FeedbackClaimKind,
    FeedbackConsentScope,
    FeedbackEventType,
    FeedbackEvidenceRelation,
    FeedbackReviewStatus,
)

BoundedEvidenceNote = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
]
BoundedStatement = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class FeedbackApiModel(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FeedbackReasonCode(StrEnum):
    ELIGIBILITY_RESULT_INCORRECT = "ELIGIBILITY_RESULT_INCORRECT"
    OPPORTUNITY_FACT_OUTDATED = "OPPORTUNITY_FACT_OUTDATED"
    MISSING_EVIDENCE_EXPLANATION = "MISSING_EVIDENCE_EXPLANATION"
    RANKING_CONTEXT_IRRELEVANT = "RANKING_CONTEXT_IRRELEVANT"


REASON_BY_CLAIM = {
    FeedbackClaimKind.ELIGIBILITY_CORRECTION: FeedbackReasonCode.ELIGIBILITY_RESULT_INCORRECT,
    FeedbackClaimKind.OPPORTUNITY_FACT_CORRECTION: FeedbackReasonCode.OPPORTUNITY_FACT_OUTDATED,
    FeedbackClaimKind.EXPLANATION_UNCLEAR: FeedbackReasonCode.MISSING_EVIDENCE_EXPLANATION,
    FeedbackClaimKind.RANKING_IRRELEVANT: FeedbackReasonCode.RANKING_CONTEXT_IRRELEVANT,
}


class FeedbackSubmissionWrite(FeedbackApiModel):
    ranking_snapshot_id: EntityId
    match_snapshot_id: EntityId
    opportunity_version: VersionNumber
    user_state_version: VersionNumber
    event_type: FeedbackEventType
    claim_kind: FeedbackClaimKind
    user_statement: BoundedStatement | None
    structured_reason_code: FeedbackReasonCode
    initial_evidence_ref_ids: tuple[EntityId, ...] = Field(max_length=10)
    consent_version: Literal["phase7-feedback-consent-v1"]
    consent_scope: Literal[FeedbackConsentScope.FEEDBACK_REVIEW_AND_VALIDATION]

    @field_validator("initial_evidence_ref_ids", mode="before")
    @classmethod
    def normalize_evidence_ids(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        normalized = tuple(sorted(value, key=str))
        if len(normalized) != len(set(normalized)):
            raise ValueError("initial evidence IDs must not contain duplicates")
        return normalized

    @model_validator(mode="after")
    def validate_reason_for_claim(self) -> Self:
        if REASON_BY_CLAIM[self.claim_kind] is not self.structured_reason_code:
            raise ValueError("structured reason code does not match claim kind")
        return self


class FeedbackEvidenceWrite(FeedbackApiModel):
    evidence_ref_id: EntityId
    relation: FeedbackEvidenceRelation
    note: BoundedEvidenceNote | None


class FeedbackStatusSummary(FeedbackApiModel):
    feedback_event_id: EntityId
    opportunity_public_id: OpportunityPublicId
    opportunity_version: VersionNumber
    event_type: FeedbackEventType
    claim_kind: FeedbackClaimKind
    status: FeedbackReviewStatus
    created_at: Instant
    status_updated_at: Instant


class FeedbackEvidenceSummary(FeedbackApiModel):
    feedback_evidence_link_id: EntityId
    evidence_ref_id: EntityId
    relation: FeedbackEvidenceRelation
    note: BoundedEvidenceNote | None
    created_at: Instant


class FeedbackStatusDetail(FeedbackApiModel):
    feedback: FeedbackStatusSummary
    evidence: tuple[FeedbackEvidenceSummary, ...]


class FeedbackStatusPage(FeedbackApiModel):
    items: tuple[FeedbackStatusSummary, ...]


__all__ = [
    "FeedbackEvidenceSummary",
    "FeedbackEvidenceWrite",
    "FeedbackReasonCode",
    "FeedbackStatusDetail",
    "FeedbackStatusPage",
    "FeedbackStatusSummary",
    "FeedbackSubmissionWrite",
]
