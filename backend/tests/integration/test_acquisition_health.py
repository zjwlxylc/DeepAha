from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.health import (
    HealthState,
    get_acquisition_health,
    get_integration_cost_gate,
)
from deepaha.acquisition.health_evidence import (
    AcquisitionEvidenceService,
    RecordIntegrationEvidenceCommand,
)
from tests.integration.test_acquisition_evaluation_persistence import seed_observation
from tests.integration.test_acquisition_health_persistence import (
    integration_command,
    run_command,
)

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 23, 15, 0, tzinfo=UTC)


@pytest.fixture
def factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_engine, expire_on_commit=False)


def test_persisted_runs_derive_health_at_fixed_as_of(factory: sessionmaker[Session]) -> None:
    with factory.begin() as session:
        observation = seed_observation(session)
    service = AcquisitionEvidenceService(factory)
    service.record_run(run_command(observation.source_id, observation.endpoint_id))

    health = get_acquisition_health(
        factory,
        endpoint_id=observation.endpoint_id,
        as_of=NOW + timedelta(hours=1),
        zero_discovery_grace_runs=1,
        selector_drift_grace_runs=0,
    )

    assert health.source_id == observation.source_id
    assert health.accessibility is HealthState.HEALTHY
    assert health.last_valid_success_at is not None


def test_persisted_first_five_integration_evidence_computes_gate(
    factory: sessionmaker[Session],
) -> None:
    service = AcquisitionEvidenceService(factory)
    commands: list[RecordIntegrationEvidenceCommand] = []
    for index in range(5):
        with factory.begin() as session:
            observation = seed_observation(session)
        changes: dict[str, object] = {
            "recipe_id": f"019c0000-0000-7000-8000-{index + 980:012d}",
            "recipe_version": f"recipe-v{index}",
            "recorded_at": NOW + timedelta(minutes=index),
        }
        if index == 4:
            changes.update(
                onboarding_mode="NEW_FETCHER",
                primary_fetcher="new-fetcher",
                reused_existing_fetcher=False,
            )
        commands.append(
            integration_command(
                observation.source_id,
                observation.endpoint_id,
                **changes,
            )
        )
    for item in commands:
        service.record_integration(item)

    gate = get_integration_cost_gate(factory)

    assert gate.sample_count == 5
    assert gate.existing_fetcher_reuse_count == 4
    assert gate.recipe_or_thin_count == 4
    assert gate.status == "PASS"
