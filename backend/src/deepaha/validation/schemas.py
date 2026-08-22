from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, StringConstraints, field_validator, model_validator

from deepaha.contracts.common import EntityId, Instant, Sha256, VersionNumber
from deepaha.contracts.phase1 import ContractModel
from deepaha.contracts.phase7 import (
    FeedbackEvidenceClass,
    HumanValidationMetricsSchemaV06,
    ImprovementDirection,
    SimulationValidationMetricsSchemaV06,
    ValidationOutcome,
)

BoundedChange = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
ComponentVersion = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]


def _unique_ids(value: object) -> object:
    if not isinstance(value, (list, tuple)):
        return value
    normalized = tuple(sorted(value, key=str))
    if len(normalized) != len(set(normalized)):
        raise ValueError("ID collection must not contain duplicates")
    return normalized


class ValidationWriteModel(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ImprovementSelectionWrite(ValidationWriteModel):
    approved_label_ids: tuple[EntityId, ...] = Field(min_length=1, max_length=100)
    direction: Literal[ImprovementDirection.EXPLANATION_CLARITY]
    component: Literal["personal-explanation"]
    input_manifest_sha256: Sha256
    change_statement: BoundedChange

    _normalize_label_ids = field_validator("approved_label_ids", mode="before")(_unique_ids)


class OfflineEvaluationWrite(ValidationWriteModel):
    dataset_id: EntityId
    dataset_version: VersionNumber
    dataset_sha256: Sha256
    baseline_component_version: ComponentVersion
    candidate_component_version: ComponentVersion
    outcome: ValidationOutcome
    result_sha256: Sha256
    evidence_class: Literal[
        FeedbackEvidenceClass.SYNTHETIC_SIMULATION_ONLY,
        FeedbackEvidenceClass.CONSENTED_HUMAN_PARTICIPANT,
    ]


class ShadowEvaluationWrite(ValidationWriteModel):
    offline_evaluation_candidate_id: EntityId
    baseline_component_version: ComponentVersion
    candidate_component_version: ComponentVersion
    outcome: ValidationOutcome
    comparison_sha256: Sha256
    evidence_class: Literal[
        FeedbackEvidenceClass.SYNTHETIC_SIMULATION_ONLY,
        FeedbackEvidenceClass.CONSENTED_HUMAN_PARTICIPANT,
    ]


class SimulationValidationRunWrite(ValidationWriteModel):
    dataset_id: EntityId
    dataset_version: VersionNumber
    dataset_sha256: Sha256
    track: Literal["SIMULATION"]
    evidence_class: Literal[FeedbackEvidenceClass.SYNTHETIC_SIMULATION_ONLY]
    synthetic: Literal[True]
    release_qualification_eligible: Literal[False]
    outcome: ValidationOutcome
    metrics: SimulationValidationMetricsSchemaV06
    started_at: Instant
    completed_at: Instant

    @model_validator(mode="after")
    def validate_time_order(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not be before started_at")
        return self


class HumanValidationRunWrite(ValidationWriteModel):
    dataset_id: EntityId
    dataset_version: VersionNumber
    dataset_sha256: Sha256
    track: Literal["HUMAN_PARTICIPANT"]
    evidence_class: Literal[FeedbackEvidenceClass.CONSENTED_HUMAN_PARTICIPANT]
    synthetic: Literal[False]
    release_qualification_eligible: bool
    outcome: ValidationOutcome
    metrics: HumanValidationMetricsSchemaV06
    started_at: Instant
    completed_at: Instant

    @model_validator(mode="after")
    def validate_time_order(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not be before started_at")
        return self


__all__ = [
    "HumanValidationRunWrite",
    "ImprovementSelectionWrite",
    "OfflineEvaluationWrite",
    "ShadowEvaluationWrite",
    "SimulationValidationRunWrite",
]
