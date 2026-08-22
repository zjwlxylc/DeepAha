from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    ConfigDict,
    Field,
    RootModel,
    StringConstraints,
    field_validator,
    model_validator,
)

from deepaha.contracts.common import EntityId, Instant, NonEmptyString, Sha256, VersionNumber
from deepaha.contracts.phase1 import ContractModel

BoundedNote = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
]
BoundedStatement = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class Phase7ContractModel(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FeedbackEventType(StrEnum):
    STRUCTURED_CORRECTION = "STRUCTURED_CORRECTION"
    EXPLICIT_EVALUATION = "EXPLICIT_EVALUATION"


class FeedbackClaimKind(StrEnum):
    ELIGIBILITY_CORRECTION = "ELIGIBILITY_CORRECTION"
    OPPORTUNITY_FACT_CORRECTION = "OPPORTUNITY_FACT_CORRECTION"
    EXPLANATION_UNCLEAR = "EXPLANATION_UNCLEAR"
    RANKING_IRRELEVANT = "RANKING_IRRELEVANT"


class FeedbackConsentScope(StrEnum):
    FEEDBACK_REVIEW_AND_VALIDATION = "FEEDBACK_REVIEW_AND_VALIDATION"


class FeedbackEvidenceRelation(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"


class FeedbackActorKind(StrEnum):
    USER = "USER"
    REVIEWER = "REVIEWER"


class FeedbackReviewStatus(StrEnum):
    RECEIVED = "RECEIVED"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"
    CONFLICT = "CONFLICT"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class FeedbackConfidenceBand(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FeedbackRiskLevel(StrEnum):
    NORMAL = "NORMAL"
    HIGH_IMPACT = "HIGH_IMPACT"


class FeedbackReviewPurpose(StrEnum):
    FEEDBACK_REVIEW_AND_VALIDATION = "FEEDBACK_REVIEW_AND_VALIDATION"


class FeedbackAdjudicationDecision(StrEnum):
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"
    CONFLICT = "CONFLICT"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class FeedbackEvidenceClass(StrEnum):
    SYNTHETIC_FEEDBACK_WORKFLOW_ONLY = "SYNTHETIC_FEEDBACK_WORKFLOW_ONLY"
    SYNTHETIC_SIMULATION_ONLY = "SYNTHETIC_SIMULATION_ONLY"
    CONSENTED_HUMAN_PARTICIPANT = "CONSENTED_HUMAN_PARTICIPANT"


class ImprovementDirection(StrEnum):
    EXPLANATION_CLARITY = "EXPLANATION_CLARITY"
    OPPORTUNITY_FACT_QUALITY = "OPPORTUNITY_FACT_QUALITY"
    ELIGIBILITY_RULE_CANDIDATE = "ELIGIBILITY_RULE_CANDIDATE"
    RANKING_POLICY_CANDIDATE = "RANKING_POLICY_CANDIDATE"


class ValidationOutcome(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"


class ReleaseGateDecision(StrEnum):
    HOLD_MISSING_HUMAN_EVIDENCE = "HOLD_MISSING_HUMAN_EVIDENCE"
    HOLD_ENGINEERING_FAILURE = "HOLD_ENGINEERING_FAILURE"
    REJECTED = "REJECTED"
    CANDIDATE_ACCEPTED_FOR_FUTURE_IMPLEMENTATION = "CANDIDATE_ACCEPTED_FOR_FUTURE_IMPLEMENTATION"


def _unique_ids(value: object) -> object:
    if not isinstance(value, (list, tuple)):
        return value
    if len(value) != len(set(value)):
        raise ValueError("ID collection must not contain duplicates")
    return tuple(value)


class FeedbackEventSchemaV06(Phase7ContractModel):
    feedback_event_id: EntityId
    owner_user_id: EntityId
    ranking_snapshot_id: EntityId
    match_snapshot_id: EntityId
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    user_state_snapshot_id: EntityId
    user_state_version: VersionNumber
    event_type: FeedbackEventType
    claim_kind: FeedbackClaimKind
    user_statement: BoundedStatement | None
    structured_reason_code: NonEmptyString
    consent_version: Literal["phase7-feedback-consent-v1"]
    consent_scope: Literal[FeedbackConsentScope.FEEDBACK_REVIEW_AND_VALIDATION]
    contract_version: Literal["0.6.0"]
    input_sha256: Sha256
    created_at: Instant


class FeedbackEvidenceLinkSchemaV06(Phase7ContractModel):
    feedback_evidence_link_id: EntityId
    feedback_event_id: EntityId
    evidence_ref_id: EntityId
    document_id: EntityId
    relation: FeedbackEvidenceRelation
    actor_kind: FeedbackActorKind
    actor_id: EntityId
    note: BoundedNote | None
    input_sha256: Sha256
    created_at: Instant


class FeedbackReviewCaseSnapshotSchemaV06(Phase7ContractModel):
    review_case_snapshot_id: EntityId
    review_case_id: EntityId
    feedback_event_id: EntityId
    version: VersionNumber
    status: FeedbackReviewStatus
    priority: Annotated[int, Field(ge=1, le=3)]
    due_at: Instant
    assigned_reviewer_id: EntityId | None
    transition_reason: BoundedNote
    input_sha256: Sha256
    created_at: Instant

    @model_validator(mode="after")
    def validate_due_time(self) -> Self:
        if self.due_at < self.created_at:
            raise ValueError("due_at must not be before created_at")
        return self


class FeedbackConfidenceAssessmentSchemaV06(Phase7ContractModel):
    confidence_assessment_id: EntityId
    review_case_id: EntityId
    review_case_version: VersionNumber
    evidence_complete: bool
    confidence_band: FeedbackConfidenceBand
    risk_level: FeedbackRiskLevel
    conflict: bool
    evidence_ref_ids: tuple[EntityId, ...]
    rationale: BoundedStatement
    reviewer_id: EntityId
    review_purpose: Literal[FeedbackReviewPurpose.FEEDBACK_REVIEW_AND_VALIDATION]
    input_sha256: Sha256
    created_at: Instant

    _normalize_evidence_ref_ids = field_validator("evidence_ref_ids", mode="before")(_unique_ids)

    @model_validator(mode="after")
    def validate_complete_evidence(self) -> Self:
        if self.evidence_complete and not self.evidence_ref_ids:
            raise ValueError("complete assessment requires evidence_ref_ids")
        return self


class FeedbackAdjudicationSchemaV06(Phase7ContractModel):
    feedback_adjudication_id: EntityId
    review_case_id: EntityId
    review_case_version: VersionNumber
    confidence_assessment_id: EntityId
    decision: FeedbackAdjudicationDecision
    evidence_ref_ids: tuple[EntityId, ...]
    reason: BoundedStatement
    adjudicator_id: EntityId
    review_purpose: Literal[FeedbackReviewPurpose.FEEDBACK_REVIEW_AND_VALIDATION]
    input_sha256: Sha256
    created_at: Instant

    _normalize_evidence_ref_ids = field_validator("evidence_ref_ids", mode="before")(_unique_ids)

    @model_validator(mode="after")
    def validate_confirmed_evidence(self) -> Self:
        if self.decision is FeedbackAdjudicationDecision.CONFIRMED and not self.evidence_ref_ids:
            raise ValueError("CONFIRMED adjudication requires evidence_ref_ids")
        return self


class ApprovedFeedbackLabelSchemaV06(Phase7ContractModel):
    approved_feedback_label_id: EntityId
    feedback_event_id: EntityId
    feedback_adjudication_id: EntityId
    match_snapshot_id: EntityId
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    claim_kind: FeedbackClaimKind
    approved_target_value: BoundedStatement
    evidence_ref_ids: tuple[EntityId, ...]
    evidence_class: Literal[
        FeedbackEvidenceClass.SYNTHETIC_FEEDBACK_WORKFLOW_ONLY,
        FeedbackEvidenceClass.CONSENTED_HUMAN_PARTICIPANT,
    ]
    content_sha256: Sha256
    created_at: Instant

    _normalize_evidence_ref_ids = field_validator("evidence_ref_ids", mode="before")(_unique_ids)

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if not self.evidence_ref_ids:
            raise ValueError("approved label requires evidence_ref_ids")
        return self


class ImprovementCandidateSchemaV06(Phase7ContractModel):
    improvement_candidate_id: EntityId
    validation_cycle_id: EntityId
    approved_label_ids: tuple[EntityId, ...]
    direction: ImprovementDirection
    component: NonEmptyString
    input_manifest_sha256: Sha256
    change_statement: BoundedStatement
    candidate_sha256: Sha256
    evidence_class: Literal[
        FeedbackEvidenceClass.SYNTHETIC_FEEDBACK_WORKFLOW_ONLY,
        FeedbackEvidenceClass.CONSENTED_HUMAN_PARTICIPANT,
    ]
    selected: Literal[True]
    created_at: Instant

    _normalize_approved_label_ids = field_validator("approved_label_ids", mode="before")(
        _unique_ids
    )

    @model_validator(mode="after")
    def validate_labels(self) -> Self:
        if not self.approved_label_ids:
            raise ValueError("selected improvement candidate requires approved_label_ids")
        return self


class OfflineEvaluationCandidateSchemaV06(Phase7ContractModel):
    offline_evaluation_candidate_id: EntityId
    improvement_candidate_id: EntityId
    dataset_id: EntityId
    dataset_version: VersionNumber
    dataset_sha256: Sha256
    baseline_component_version: NonEmptyString
    candidate_component_version: NonEmptyString
    outcome: ValidationOutcome
    result_sha256: Sha256
    evidence_class: Literal[
        FeedbackEvidenceClass.SYNTHETIC_SIMULATION_ONLY,
        FeedbackEvidenceClass.CONSENTED_HUMAN_PARTICIPANT,
    ]
    created_at: Instant


class ShadowTestCandidateSchemaV06(Phase7ContractModel):
    shadow_test_candidate_id: EntityId
    improvement_candidate_id: EntityId
    offline_evaluation_candidate_id: EntityId
    baseline_component_version: NonEmptyString
    candidate_component_version: NonEmptyString
    outcome: ValidationOutcome
    comparison_sha256: Sha256
    evidence_class: Literal[
        FeedbackEvidenceClass.SYNTHETIC_SIMULATION_ONLY,
        FeedbackEvidenceClass.CONSENTED_HUMAN_PARTICIPANT,
    ]
    created_at: Instant


class SimulationValidationMetricsSchemaV06(Phase7ContractModel):
    case_count: Annotated[int, Field(ge=0)]
    expected_status_reproduced_count: Annotated[int, Field(ge=0)]
    unexpected_ineligible_count: Annotated[int, Field(ge=0)]
    unexpected_ineligible_case_ids: tuple[NonEmptyString, ...]
    replay_mismatch_count: Annotated[int, Field(ge=0)]
    candidate_difference_count: Annotated[int, Field(ge=0)]

    @field_validator("unexpected_ineligible_case_ids", mode="before")
    @classmethod
    def normalize_case_ids(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        normalized = tuple(str(item).strip() for item in value)
        if len(normalized) != len(set(normalized)):
            raise ValueError("unexpected case IDs must not contain duplicates")
        return normalized

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.expected_status_reproduced_count > self.case_count:
            raise ValueError("reproduced count must not exceed case count")
        if self.unexpected_ineligible_count != len(self.unexpected_ineligible_case_ids):
            raise ValueError("unexpected INELIGIBLE count must equal exact case ID count")
        if self.replay_mismatch_count > self.case_count:
            raise ValueError("replay mismatch count must not exceed case count")
        if self.candidate_difference_count > self.case_count:
            raise ValueError("candidate difference count must not exceed case count")
        return self


class HumanValidationMetricsSchemaV06(Phase7ContractModel):
    participant_count: Annotated[int, Field(gt=0)]
    structured_feedback_count: Annotated[int, Field(ge=0)]
    comprehension_review_count: Annotated[int, Field(ge=0)]
    cognitive_load_review_count: Annotated[int, Field(ge=0)]
    high_intent_action_count: Annotated[int, Field(ge=0)]
    withdrawal_exclusion_count: Annotated[int, Field(ge=0)]


class SimulationValidationRunSchemaV06(Phase7ContractModel):
    validation_run_id: EntityId
    validation_cycle_id: EntityId
    improvement_candidate_id: EntityId
    dataset_id: EntityId
    dataset_version: VersionNumber
    dataset_sha256: Sha256
    track: Literal["SIMULATION"]
    evidence_class: Literal[FeedbackEvidenceClass.SYNTHETIC_SIMULATION_ONLY]
    synthetic: Literal[True]
    release_qualification_eligible: Literal[False]
    outcome: ValidationOutcome
    metrics: SimulationValidationMetricsSchemaV06
    input_sha256: Sha256
    started_at: Instant
    completed_at: Instant

    @model_validator(mode="after")
    def validate_time_order(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not be before started_at")
        return self


class HumanValidationRunSchemaV06(Phase7ContractModel):
    validation_run_id: EntityId
    validation_cycle_id: EntityId
    improvement_candidate_id: EntityId
    dataset_id: EntityId
    dataset_version: VersionNumber
    dataset_sha256: Sha256
    track: Literal["HUMAN_PARTICIPANT"]
    evidence_class: Literal[FeedbackEvidenceClass.CONSENTED_HUMAN_PARTICIPANT]
    synthetic: Literal[False]
    release_qualification_eligible: bool
    outcome: ValidationOutcome
    metrics: HumanValidationMetricsSchemaV06
    input_sha256: Sha256
    started_at: Instant
    completed_at: Instant

    @model_validator(mode="after")
    def validate_time_order(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not be before started_at")
        return self


class ValidationRunSchemaV06(
    RootModel[
        Annotated[
            SimulationValidationRunSchemaV06 | HumanValidationRunSchemaV06,
            Field(discriminator="track"),
        ]
    ]
):
    model_config = ConfigDict(frozen=True)


class ReleaseGateDecisionSchemaV06(Phase7ContractModel):
    release_gate_decision_id: EntityId
    validation_cycle_id: EntityId
    improvement_candidate_id: EntityId
    offline_evaluation_candidate_id: EntityId
    shadow_test_candidate_id: EntityId
    simulation_validation_run_id: EntityId | None
    human_validation_run_id: EntityId | None
    decision: ReleaseGateDecision
    rationale: BoundedStatement
    input_sha256: Sha256
    created_at: Instant

    @model_validator(mode="after")
    def validate_track_requirements(self) -> Self:
        if self.decision is ReleaseGateDecision.CANDIDATE_ACCEPTED_FOR_FUTURE_IMPLEMENTATION and (
            self.simulation_validation_run_id is None or self.human_validation_run_id is None
        ):
            raise ValueError("candidate acceptance requires both validation tracks")
        if self.decision is ReleaseGateDecision.HOLD_MISSING_HUMAN_EVIDENCE:
            if self.simulation_validation_run_id is None:
                raise ValueError("missing-human hold requires a simulation validation run")
            if self.human_validation_run_id is not None:
                raise ValueError("missing-human hold cannot reference a human validation run")
        return self
