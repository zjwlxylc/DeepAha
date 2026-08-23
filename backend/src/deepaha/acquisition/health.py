from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.contracts import (
    AcquisitionContract,
    AcquisitionRunSchema,
    OnboardingMode,
    SourceIntegrationEvidenceSchema,
)
from deepaha.acquisition.models import AcquisitionRun, SourceIntegrationEvidence
from deepaha.contracts.common import EntityId, Instant
from deepaha.sources.models import SourceEndpoint


class HealthState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class AcquisitionHealthSummary(AcquisitionContract):
    source_id: EntityId
    endpoint_id: EntityId
    as_of: Instant
    accessibility: HealthState
    discovery: HealthState
    fetch_integrity: HealthState
    parseability: HealthState
    evidenceability: HealthState
    drift: HealthState
    last_valid_success_at: Instant | None
    consecutive_semantic_failures: int = Field(ge=0)
    zero_discovery_runs: int = Field(ge=0)
    selector_drift_runs: int = Field(ge=0)
    run_count: int = Field(ge=0)
    browser_ratio: float = Field(ge=0, le=1)
    manual_ratio: float = Field(ge=0, le=1)


class IntegrationCostGate(AcquisitionContract):
    sample_count: int = Field(ge=5)
    existing_fetcher_reuse_count: int = Field(ge=0)
    recipe_or_thin_count: int = Field(ge=0)
    core_schema_change_count: int = Field(ge=0)
    existing_fetcher_reuse_ratio: float = Field(ge=0, le=1)
    recipe_or_thin_ratio: float = Field(ge=0, le=1)
    status: Literal["PASS", "FAIL"]


class InsufficientIntegrationEvidence(RuntimeError):
    def __init__(self) -> None:
        self.code = "INSUFFICIENT_INTEGRATION_EVIDENCE"
        super().__init__(self.code)


def derive_acquisition_health(
    runs: Sequence[AcquisitionRunSchema],
    *,
    source_id: UUID | str,
    endpoint_id: UUID | str,
    as_of: datetime,
    zero_discovery_grace_runs: int,
    selector_drift_grace_runs: int,
) -> AcquisitionHealthSummary:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must include timezone information")
    if not 0 <= zero_discovery_grace_runs <= 10:
        raise ValueError("zero_discovery_grace_runs is outside the Recipe contract")
    if not 0 <= selector_drift_grace_runs <= 10:
        raise ValueError("selector_drift_grace_runs is outside the Recipe contract")
    ordered = tuple(sorted(runs, key=lambda item: (item.completed_at, item.acquisition_run_id)))
    if any(item.completed_at > as_of for item in ordered):
        raise ValueError("acquisition run completed after as_of")
    if any(
        str(item.source_id) != str(source_id) or str(item.endpoint_id) != str(endpoint_id)
        for item in ordered
    ):
        raise ValueError("acquisition runs do not match requested source and endpoint")
    if not ordered:
        return AcquisitionHealthSummary.model_validate(
            {
                "source_id": source_id,
                "endpoint_id": endpoint_id,
                "as_of": as_of,
                "accessibility": "UNKNOWN",
                "discovery": "UNKNOWN",
                "fetch_integrity": "UNKNOWN",
                "parseability": "UNKNOWN",
                "evidenceability": "UNKNOWN",
                "drift": "UNKNOWN",
                "last_valid_success_at": None,
                "consecutive_semantic_failures": 0,
                "zero_discovery_runs": 0,
                "selector_drift_runs": 0,
                "run_count": 0,
                "browser_ratio": 0.0,
                "manual_ratio": 0.0,
            }
        )

    latest = ordered[-1]
    zero_count = _consecutive_flag_count(ordered, "zero_discovery_flag")
    selector_count = _consecutive_flag_count(ordered, "selector_drift_flag")
    attempts = tuple(attempt for item in ordered for attempt in item.strategy_attempts)
    total_attempts = len(attempts)
    successful_runs = tuple(item for item in ordered if _semantic_success(item))
    consecutive_failures = 0
    for item in reversed(ordered):
        if _semantic_success(item):
            break
        consecutive_failures += 1

    blocked_codes = {
        "CONTENT_CHALLENGE",
        "CAPTCHA_REQUIRED",
        "AUTH_REQUIRED",
        "ACCESS_DENIED",
    }
    accessibility = (
        HealthState.BLOCKED
        if latest.terminal_code in blocked_codes
        else HealthState.HEALTHY
        if _semantic_success(latest)
        else HealthState.DEGRADED
    )
    discovery = (
        HealthState.HEALTHY
        if latest.discovered_count > 0
        else HealthState.DEGRADED
        if latest.zero_discovery_flag
        else HealthState.UNKNOWN
    )
    fetch_integrity = (
        HealthState.HEALTHY
        if latest.strategy_attempts
        and all(attempt.validation_status is not None for attempt in latest.strategy_attempts)
        else HealthState.DEGRADED
    )
    parseability = (
        HealthState.UNKNOWN
        if latest.validated_count == 0
        else HealthState.HEALTHY
        if latest.parsed_count == latest.validated_count
        else HealthState.DEGRADED
    )
    evidenceability = (
        HealthState.UNKNOWN
        if latest.parsed_count == 0
        else HealthState.HEALTHY
        if latest.evidence_count > 0
        else HealthState.DEGRADED
    )
    drift = (
        HealthState.DEGRADED
        if zero_count > zero_discovery_grace_runs or selector_count > selector_drift_grace_runs
        else HealthState.HEALTHY
    )
    return AcquisitionHealthSummary.model_validate(
        {
            "source_id": source_id,
            "endpoint_id": endpoint_id,
            "as_of": as_of,
            "accessibility": accessibility,
            "discovery": discovery,
            "fetch_integrity": fetch_integrity,
            "parseability": parseability,
            "evidenceability": evidenceability,
            "drift": drift,
            "last_valid_success_at": (
                successful_runs[-1].completed_at if successful_runs else None
            ),
            "consecutive_semantic_failures": consecutive_failures,
            "zero_discovery_runs": zero_count,
            "selector_drift_runs": selector_count,
            "run_count": len(ordered),
            "browser_ratio": (
                sum(attempt.strategy == "BROWSER" for attempt in attempts) / total_attempts
                if total_attempts
                else 0.0
            ),
            "manual_ratio": (
                sum(attempt.strategy == "MANUAL" for attempt in attempts) / total_attempts
                if total_attempts
                else 0.0
            ),
        }
    )


def compute_integration_cost_gate(
    evidence: Sequence[SourceIntegrationEvidenceSchema],
) -> IntegrationCostGate:
    ordered = tuple(
        sorted(
            evidence,
            key=lambda item: (item.recorded_at, item.source_integration_evidence_id),
        )
    )
    first_by_source: list[SourceIntegrationEvidenceSchema] = []
    seen_sources: set[UUID] = set()
    for item in ordered:
        if item.source_id in seen_sources:
            continue
        seen_sources.add(item.source_id)
        first_by_source.append(item)
    if len(first_by_source) < 5:
        raise InsufficientIntegrationEvidence
    sample = tuple(first_by_source[:5])
    reuse_count = sum(item.reused_existing_fetcher for item in sample)
    recipe_or_thin_count = sum(
        item.onboarding_mode in {OnboardingMode.RECIPE_ONLY, OnboardingMode.THIN_PLUGIN}
        for item in sample
    )
    schema_count = sum(item.core_schema_changed for item in sample)
    status: Literal["PASS", "FAIL"] = (
        "PASS" if reuse_count >= 3 and recipe_or_thin_count >= 3 and schema_count == 0 else "FAIL"
    )
    return IntegrationCostGate(
        sample_count=5,
        existing_fetcher_reuse_count=reuse_count,
        recipe_or_thin_count=recipe_or_thin_count,
        core_schema_change_count=schema_count,
        existing_fetcher_reuse_ratio=reuse_count / 5,
        recipe_or_thin_ratio=recipe_or_thin_count / 5,
        status=status,
    )


def get_acquisition_health(
    session_factory: sessionmaker[Session],
    *,
    endpoint_id: UUID,
    as_of: datetime,
    zero_discovery_grace_runs: int,
    selector_drift_grace_runs: int,
) -> AcquisitionHealthSummary:
    with session_factory() as session:
        endpoint = session.get(SourceEndpoint, endpoint_id)
        if endpoint is None:
            raise LookupError(f"SourceEndpoint not found: {endpoint_id}")
        rows = session.scalars(
            select(AcquisitionRun)
            .where(
                AcquisitionRun.endpoint_id == endpoint_id,
                AcquisitionRun.completed_at <= as_of,
            )
            .order_by(AcquisitionRun.completed_at, AcquisitionRun.acquisition_run_id)
        ).all()
        schemas = tuple(_run_schema(row) for row in rows)
    return derive_acquisition_health(
        schemas,
        source_id=endpoint.source_id,
        endpoint_id=endpoint.endpoint_id,
        as_of=as_of,
        zero_discovery_grace_runs=zero_discovery_grace_runs,
        selector_drift_grace_runs=selector_drift_grace_runs,
    )


def get_integration_cost_gate(
    session_factory: sessionmaker[Session],
) -> IntegrationCostGate:
    with session_factory() as session:
        rows = session.scalars(
            select(SourceIntegrationEvidence).order_by(
                SourceIntegrationEvidence.recorded_at,
                SourceIntegrationEvidence.source_integration_evidence_id,
            )
        ).all()
        schemas = tuple(_integration_schema(row) for row in rows)
    return compute_integration_cost_gate(schemas)


def _semantic_success(run: AcquisitionRunSchema) -> bool:
    return run.terminal_code == "COMPLETE" and run.validated_count > 0 and run.parsed_count > 0


def _consecutive_flag_count(
    runs: Sequence[AcquisitionRunSchema],
    field: Literal["zero_discovery_flag", "selector_drift_flag"],
) -> int:
    count = 0
    for item in reversed(runs):
        if not getattr(item, field):
            break
        count += 1
    return count


def _run_schema(row: AcquisitionRun) -> AcquisitionRunSchema:
    return AcquisitionRunSchema.model_validate(
        {column.name: getattr(row, column.name) for column in AcquisitionRun.__table__.columns}
    )


def _integration_schema(row: SourceIntegrationEvidence) -> SourceIntegrationEvidenceSchema:
    return SourceIntegrationEvidenceSchema.model_validate(
        {
            column.name: getattr(row, column.name)
            for column in SourceIntegrationEvidence.__table__.columns
        }
    )


__all__ = [
    "AcquisitionHealthSummary",
    "HealthState",
    "InsufficientIntegrationEvidence",
    "IntegrationCostGate",
    "compute_integration_cost_gate",
    "derive_acquisition_health",
    "get_acquisition_health",
    "get_integration_cost_gate",
]
