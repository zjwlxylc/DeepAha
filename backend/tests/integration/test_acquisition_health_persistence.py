from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from sqlalchemy import Connection, Engine, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.health_evidence import (
    AcquisitionEvidenceConflict,
    AcquisitionEvidenceService,
    RecordIntegrationEvidenceCommand,
    RecordRunCommand,
)
from deepaha.acquisition.models import AcquisitionRun, SourceIntegrationEvidence
from tests.integration.test_acquisition_evaluation_persistence import seed_observation

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


@pytest.fixture
def factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_engine, expire_on_commit=False)


def run_command(source_id: object, endpoint_id: object, **changes: object) -> RecordRunCommand:
    values: dict[str, object] = {
        "acquisition_run_id": "019c0000-0000-7000-8000-000000000601",
        "recipe_id": "019c0000-0000-7000-8000-000000000602",
        "source_id": source_id,
        "endpoint_id": endpoint_id,
        "endpoint_policy_version": "2026-08-23.1",
        "recipe_version": "2026-08-23.recipe.1",
        "started_at": NOW,
        "completed_at": NOW + timedelta(seconds=2),
        "terminal_code": "COMPLETE",
        "request_count": 1,
        "strategy_attempts": [
            {
                "strategy": "STATIC_HTTP",
                "validation_status": "VALID",
                "error_code": None,
            }
        ],
        "discovered_count": 3,
        "validated_count": 1,
        "parsed_count": 1,
        "attachment_count": 1,
        "evidence_count": 2,
        "zero_discovery_flag": False,
        "selector_drift_flag": False,
        "manual_intervention": False,
        "stable_stop_reason": None,
        "contract_version": "1.0.0",
    }
    values.update(changes)
    return RecordRunCommand.model_validate(values)


def integration_command(
    source_id: object,
    endpoint_id: object,
    **changes: object,
) -> RecordIntegrationEvidenceCommand:
    values: dict[str, object] = {
        "recipe_id": "019c0000-0000-7000-8000-000000000602",
        "source_id": source_id,
        "endpoint_id": endpoint_id,
        "recipe_version": "2026-08-23.recipe.1",
        "primary_fetcher": "deepaha-static-http",
        "onboarding_mode": "RECIPE_ONLY",
        "reused_existing_fetcher": True,
        "recipe_line_count": 42,
        "source_specific_production_loc": 0,
        "generic_capability_changes": 0,
        "core_schema_changed": False,
        "onboarding_minutes": 35,
        "total_request_count": 5,
        "browser_request_count": 0,
        "manual_request_count": 0,
        "run_failure_count": 1,
        "maintenance_minutes": 0,
        "recorded_at": NOW,
        "contract_version": "1.0.0",
    }
    values.update(changes)
    return RecordIntegrationEvidenceCommand.model_validate(values)


def test_health_tables_have_exact_source_endpoint_bindings(connection: Connection) -> None:
    inspector = inspect(connection)
    for table in ("acquisition_runs", "source_integration_evidence"):
        foreign_keys = inspector.get_foreign_keys(table)
        bindings = {
            tuple(item["constrained_columns"]): tuple(item["referred_columns"])
            for item in foreign_keys
        }
        assert bindings[("endpoint_id", "source_id")] == ("endpoint_id", "source_id")


def test_run_and_integration_evidence_are_idempotent(factory: sessionmaker[Session]) -> None:
    with factory.begin() as session:
        observation = seed_observation(session)
    service = AcquisitionEvidenceService(factory)
    run = run_command(observation.source_id, observation.endpoint_id)
    integration = integration_command(observation.source_id, observation.endpoint_id)

    first_run = service.record_run(run)
    second_run = service.record_run(run)
    first_integration = service.record_integration(integration)
    second_integration = service.record_integration(integration)

    assert first_run == second_run
    assert first_integration == second_integration
    with factory() as session:
        assert len(session.scalars(select(AcquisitionRun)).all()) == 1
        assert len(session.scalars(select(SourceIntegrationEvidence)).all()) == 1


def test_conflicting_replay_fails_closed(factory: sessionmaker[Session]) -> None:
    with factory.begin() as session:
        observation = seed_observation(session)
    service = AcquisitionEvidenceService(factory)
    service.record_run(run_command(observation.source_id, observation.endpoint_id))
    service.record_integration(integration_command(observation.source_id, observation.endpoint_id))

    with pytest.raises(AcquisitionEvidenceConflict, match="ACQUISITION_EVIDENCE_CONFLICT"):
        service.record_run(
            run_command(observation.source_id, observation.endpoint_id, parsed_count=0)
        )
    with pytest.raises(AcquisitionEvidenceConflict, match="ACQUISITION_EVIDENCE_CONFLICT"):
        service.record_integration(
            integration_command(
                observation.source_id,
                observation.endpoint_id,
                onboarding_minutes=99,
            )
        )


def test_cross_source_binding_and_insert_only_guards(
    factory: sessionmaker[Session], migrated_engine: Engine
) -> None:
    with factory.begin() as session:
        first = seed_observation(session)
        second = seed_observation(session)
        session.add(
            AcquisitionRun(
                **run_command(first.source_id, second.endpoint_id).model_dump(mode="python")
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()

    with factory.begin() as session:
        observation = seed_observation(session)
    row = AcquisitionEvidenceService(factory).record_run(
        run_command(observation.source_id, observation.endpoint_id)
    )
    with pytest.raises(DBAPIError, match="immutable"), migrated_engine.begin() as connection:
        connection.execute(
            text("update acquisition_runs set parsed_count = 0 where acquisition_run_id = :run_id"),
            {"run_id": row.acquisition_run_id},
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"completed_at": NOW - timedelta(seconds=1)},
        {"request_count": 0},
        {"parsed_count": 2},
        {"manual_intervention": True},
        {"terminal_code": "CAPTCHA_REQUIRED", "stable_stop_reason": None},
    ],
)
def test_run_contract_rejects_incoherent_facts(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        run_command(uuid7(), uuid7(), **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"browser_request_count": 6},
        {"manual_request_count": 6},
        {"onboarding_mode": "RECIPE_ONLY", "source_specific_production_loc": 1},
        {"onboarding_mode": "NEW_FETCHER", "reused_existing_fetcher": True},
    ],
)
def test_integration_contract_rejects_incoherent_cost_facts(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        integration_command(uuid7(), uuid7(), **changes)
