from uuid import uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.contracts import (
    AcquisitionContract,
    AcquisitionEvaluationSchema,
    FetchStrategy,
    ValidationResult,
)
from deepaha.acquisition.models import AcquisitionEvaluation
from deepaha.contracts.common import EntityId, Instant
from deepaha.sources.models import CaptureObservation


class RecordEvaluationCommand(AcquisitionContract):
    observation_id: EntityId
    strategy_used: FetchStrategy
    redirect_chain: tuple[str, ...]
    manual_intervention: bool
    validation_result: ValidationResult
    evaluated_at: Instant


class AcquisitionEvaluationConflict(RuntimeError):
    def __init__(self) -> None:
        self.code = "ACQUISITION_EVALUATION_CONFLICT"
        super().__init__(self.code)


class EvaluationNotPermitted(RuntimeError):
    def __init__(self) -> None:
        self.code = "EVALUATION_NOT_PERMITTED"
        super().__init__(self.code)


class EvaluationService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(self, command: RecordEvaluationCommand) -> AcquisitionEvaluationSchema:
        with self._session_factory.begin() as session:
            observation = session.get(CaptureObservation, command.observation_id)
            if observation is None:
                raise LookupError(f"CaptureObservation not found: {command.observation_id}")
            if observation.outcome not in {"SUCCEEDED", "NOT_MODIFIED"} or (
                observation.artifact_id is None
            ):
                raise EvaluationNotPermitted

            existing = session.scalar(
                select(AcquisitionEvaluation).where(
                    AcquisitionEvaluation.observation_id == observation.observation_id
                )
            )
            candidate = AcquisitionEvaluationSchema.model_validate(
                {
                    "acquisition_evaluation_id": (
                        existing.acquisition_evaluation_id if existing is not None else uuid7()
                    ),
                    "observation_id": observation.observation_id,
                    "source_id": observation.source_id,
                    "endpoint_id": observation.endpoint_id,
                    "artifact_id": observation.artifact_id,
                    "strategy_used": command.strategy_used,
                    "validation_status": command.validation_result.status,
                    "challenge_type": command.validation_result.challenge_type,
                    "redirect_chain": command.redirect_chain,
                    "discovered_count": command.validation_result.discovered_count,
                    "manual_intervention": command.manual_intervention,
                    "diagnostic_codes": command.validation_result.diagnostic_codes,
                    "validator_name": command.validation_result.validator_name,
                    "validator_version": command.validation_result.validator_version,
                    "metrics_schema_version": command.validation_result.metrics_schema_version,
                    "validation_metrics": command.validation_result.metrics,
                    "evaluated_at": command.evaluated_at,
                    "contract_version": "1.0.0",
                }
            )
            if existing is not None:
                persisted = _schema(existing)
                if persisted != candidate:
                    raise AcquisitionEvaluationConflict
                return persisted

            session.add(_row(candidate))
            return candidate


def _row(schema: AcquisitionEvaluationSchema) -> AcquisitionEvaluation:
    return AcquisitionEvaluation(
        acquisition_evaluation_id=schema.acquisition_evaluation_id,
        observation_id=schema.observation_id,
        endpoint_id=schema.endpoint_id,
        source_id=schema.source_id,
        artifact_id=schema.artifact_id,
        strategy_used=schema.strategy_used.value,
        validation_status=schema.validation_status.value,
        challenge_type=(schema.challenge_type.value if schema.challenge_type is not None else None),
        redirect_chain=[str(url) for url in schema.redirect_chain],
        discovered_count=schema.discovered_count,
        manual_intervention=schema.manual_intervention,
        diagnostic_codes=list(schema.diagnostic_codes),
        validator_name=schema.validator_name,
        validator_version=schema.validator_version,
        metrics_schema_version=schema.metrics_schema_version,
        validation_metrics=dict(schema.validation_metrics),
        evaluated_at=schema.evaluated_at,
        contract_version=schema.contract_version,
    )


def _schema(row: AcquisitionEvaluation) -> AcquisitionEvaluationSchema:
    return AcquisitionEvaluationSchema.model_validate(
        {
            "acquisition_evaluation_id": row.acquisition_evaluation_id,
            "observation_id": row.observation_id,
            "endpoint_id": row.endpoint_id,
            "source_id": row.source_id,
            "artifact_id": row.artifact_id,
            "strategy_used": row.strategy_used,
            "validation_status": row.validation_status,
            "challenge_type": row.challenge_type,
            "redirect_chain": row.redirect_chain,
            "discovered_count": row.discovered_count,
            "manual_intervention": row.manual_intervention,
            "diagnostic_codes": row.diagnostic_codes,
            "validator_name": row.validator_name,
            "validator_version": row.validator_version,
            "metrics_schema_version": row.metrics_schema_version,
            "validation_metrics": row.validation_metrics,
            "evaluated_at": row.evaluated_at,
            "contract_version": row.contract_version,
        }
    )


__all__ = [
    "AcquisitionEvaluationConflict",
    "EvaluationNotPermitted",
    "EvaluationService",
    "RecordEvaluationCommand",
]
