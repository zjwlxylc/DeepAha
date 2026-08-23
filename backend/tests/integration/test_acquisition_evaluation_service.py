from datetime import UTC, datetime
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.contracts import ValidationResult
from deepaha.acquisition.evaluations import (
    AcquisitionEvaluationConflict,
    EvaluationNotPermitted,
    EvaluationService,
    RecordEvaluationCommand,
)
from tests.integration.test_acquisition_evaluation_persistence import seed_observation

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)


@pytest.fixture
def factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_engine, expire_on_commit=False)


def validation_result(*, status: str = "VALID") -> ValidationResult:
    challenge_type = None
    diagnostics: list[str] = []
    if status == "CAPTCHA_REQUIRED":
        challenge_type = "CAPTCHA"
        diagnostics = ["CAPTCHA_MARKER"]
    return ValidationResult.model_validate(
        {
            "status": status,
            "challenge_type": challenge_type,
            "discovered_count": 1,
            "diagnostic_codes": diagnostics,
            "metrics": {"byte_size": 25},
            "validator_name": "deepaha-content-validator",
            "validator_version": "1.0.0",
            "metrics_schema_version": "1.0.0",
            "contract_version": "1.0.0",
        }
    )


def command(observation_id: UUID, **changes: object) -> RecordEvaluationCommand:
    values: dict[str, object] = {
        "observation_id": observation_id,
        "strategy_used": "STATIC_HTTP",
        "redirect_chain": ("https://acquisition.example.gov/list/",),
        "manual_intervention": False,
        "validation_result": validation_result(),
        "evaluated_at": NOW,
    }
    values.update(changes)
    return RecordEvaluationCommand.model_validate(values)


def test_exact_evaluation_replay_returns_one_immutable_row(
    factory: sessionmaker[Session],
) -> None:
    with factory.begin() as session:
        observation = seed_observation(session)
    service = EvaluationService(factory)

    first = service.record(command(observation.observation_id))
    second = service.record(command(observation.observation_id))

    assert first == second
    assert first.observation_id == observation.observation_id


def test_conflicting_evaluation_replay_fails_closed(factory: sessionmaker[Session]) -> None:
    with factory.begin() as session:
        observation = seed_observation(session)
    service = EvaluationService(factory)
    service.record(command(observation.observation_id))

    with pytest.raises(AcquisitionEvaluationConflict, match="ACQUISITION_EVALUATION_CONFLICT"):
        service.record(
            command(
                observation.observation_id,
                validation_result=validation_result(status="CAPTCHA_REQUIRED"),
            )
        )


def test_failed_transport_observation_cannot_be_evaluated(
    factory: sessionmaker[Session],
) -> None:
    with factory.begin() as session:
        observation = seed_observation(session)
        observation.observation_id = uuid7()
        observation.collection_run_id = uuid7()
        observation.outcome = "FAILED"
        observation.http_status = None
        observation.artifact_id = None
        observation.error_code = "NETWORK_TIMEOUT"

    with pytest.raises(EvaluationNotPermitted, match="EVALUATION_NOT_PERMITTED"):
        EvaluationService(factory).record(command(observation.observation_id))
