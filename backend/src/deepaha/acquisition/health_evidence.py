from typing import Self
from uuid import uuid7

from pydantic import model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.contracts import (
    AcquisitionContract,
    AcquisitionRunSchema,
    OnboardingMode,
    SourceIntegrationEvidenceSchema,
)
from deepaha.acquisition.models import AcquisitionRun, SourceIntegrationEvidence
from deepaha.contracts.common import EntityId, Instant, NonEmptyString


class RecordRunCommand(AcquisitionRunSchema):
    pass


class RecordIntegrationEvidenceCommand(AcquisitionContract):
    recipe_id: EntityId
    source_id: EntityId
    endpoint_id: EntityId
    recipe_version: NonEmptyString
    primary_fetcher: NonEmptyString
    onboarding_mode: OnboardingMode
    reused_existing_fetcher: bool
    recipe_line_count: int
    source_specific_production_loc: int
    generic_capability_changes: int
    core_schema_changed: bool
    onboarding_minutes: int
    total_request_count: int
    browser_request_count: int
    manual_request_count: int
    run_failure_count: int
    maintenance_minutes: int
    recorded_at: Instant
    contract_version: str

    @model_validator(mode="after")
    def require_schema_shape(self) -> Self:
        self.to_schema(uuid7())
        return self

    def to_schema(self, evidence_id: EntityId) -> SourceIntegrationEvidenceSchema:
        return SourceIntegrationEvidenceSchema.model_validate(
            {
                "source_integration_evidence_id": evidence_id,
                **self.model_dump(mode="python"),
            }
        )


class AcquisitionEvidenceConflict(RuntimeError):
    def __init__(self) -> None:
        self.code = "ACQUISITION_EVIDENCE_CONFLICT"
        super().__init__(self.code)


class AcquisitionEvidenceService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record_run(self, command: RecordRunCommand) -> AcquisitionRunSchema:
        candidate = AcquisitionRunSchema.model_validate(command.model_dump(mode="python"))
        with self._session_factory.begin() as session:
            existing = session.get(AcquisitionRun, command.acquisition_run_id)
            if existing is not None:
                persisted = _run_schema(existing)
                if persisted != candidate:
                    raise AcquisitionEvidenceConflict
                return persisted
            session.add(_run_row(candidate))
            return candidate

    def record_integration(
        self, command: RecordIntegrationEvidenceCommand
    ) -> SourceIntegrationEvidenceSchema:
        with self._session_factory.begin() as session:
            existing = session.scalar(
                select(SourceIntegrationEvidence).where(
                    SourceIntegrationEvidence.source_id == command.source_id,
                    SourceIntegrationEvidence.endpoint_id == command.endpoint_id,
                    SourceIntegrationEvidence.recipe_version == command.recipe_version,
                )
            )
            candidate = command.to_schema(
                existing.source_integration_evidence_id if existing is not None else uuid7()
            )
            if existing is not None:
                persisted = _integration_schema(existing)
                if persisted != candidate:
                    raise AcquisitionEvidenceConflict
                return persisted
            session.add(_integration_row(candidate))
            return candidate


def _run_row(schema: AcquisitionRunSchema) -> AcquisitionRun:
    return AcquisitionRun(
        acquisition_run_id=schema.acquisition_run_id,
        recipe_id=schema.recipe_id,
        source_id=schema.source_id,
        endpoint_id=schema.endpoint_id,
        endpoint_policy_version=schema.endpoint_policy_version,
        recipe_version=schema.recipe_version,
        started_at=schema.started_at,
        completed_at=schema.completed_at,
        terminal_code=schema.terminal_code,
        request_count=schema.request_count,
        strategy_attempts=[item.model_dump(mode="json") for item in schema.strategy_attempts],
        discovered_count=schema.discovered_count,
        validated_count=schema.validated_count,
        parsed_count=schema.parsed_count,
        attachment_count=schema.attachment_count,
        evidence_count=schema.evidence_count,
        zero_discovery_flag=schema.zero_discovery_flag,
        selector_drift_flag=schema.selector_drift_flag,
        manual_intervention=schema.manual_intervention,
        stable_stop_reason=schema.stable_stop_reason,
        contract_version=schema.contract_version,
    )


def _run_schema(row: AcquisitionRun) -> AcquisitionRunSchema:
    return AcquisitionRunSchema.model_validate(
        {column.name: getattr(row, column.name) for column in AcquisitionRun.__table__.columns}
    )


def _integration_row(schema: SourceIntegrationEvidenceSchema) -> SourceIntegrationEvidence:
    values = schema.model_dump(mode="python")
    values["onboarding_mode"] = schema.onboarding_mode.value
    return SourceIntegrationEvidence(**values)


def _integration_schema(row: SourceIntegrationEvidence) -> SourceIntegrationEvidenceSchema:
    return SourceIntegrationEvidenceSchema.model_validate(
        {
            column.name: getattr(row, column.name)
            for column in SourceIntegrationEvidence.__table__.columns
        }
    )


__all__ = [
    "AcquisitionEvidenceConflict",
    "AcquisitionEvidenceService",
    "RecordIntegrationEvidenceCommand",
    "RecordRunCommand",
]
