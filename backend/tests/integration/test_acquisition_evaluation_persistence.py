from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid7

import pytest
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from deepaha.acquisition.models import AcquisitionEvaluation
from deepaha.artifacts.models import RawArtifact
from deepaha.sources.models import CaptureObservation, Source, SourceEndpoint

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
CONTENT = b"synthetic official notice"
CONTENT_SHA256 = sha256(CONTENT).hexdigest()


def seed_observation(session: Session) -> CaptureObservation:
    source_id = uuid7()
    endpoint_id = uuid7()
    artifact_id = uuid7()
    source = Source(
        source_id=source_id,
        public_id=f"src_{source_id.hex}",
        canonical_url=f"https://acquisition.example.gov/{source_id.hex}/",
        authority_name="Synthetic acquisition authority",
        tier="OFFICIAL_PRIMARY",
        jurisdiction="Synthetic jurisdiction",
        active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    endpoint = SourceEndpoint(
        endpoint_id=endpoint_id,
        source_id=source_id,
        url="https://acquisition.example.gov/list/",
        allowed_hosts=["acquisition.example.gov"],
        expected_media_types=["text/html"],
        browser_policy="NEVER",
        minimum_interval_seconds=21_600,
        timeout_seconds=30,
        max_attempts=2,
        robots_url="https://acquisition.example.gov/robots.txt",
        robots_decision="ALLOWED",
        robots_checked_at=NOW,
        content_use_basis="LINK_ONLY",
        license_name=None,
        license_url=None,
        attribution="Synthetic acquisition authority",
        fixture_storage_allowed=False,
        usage_note="Synthetic persistence test only.",
        policy_version="2026-08-23.1",
        active=True,
        verified_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    artifact = RawArtifact(
        artifact_id=artifact_id,
        source_id=source_id,
        requested_url=endpoint.url,
        resolved_url=endpoint.url,
        retrieved_at=NOW,
        http_status=200,
        media_type="text/html",
        content_sha256=CONTENT_SHA256,
        storage_bucket="deepaha-raw",
        object_key=f"raw/sha256/{CONTENT_SHA256[:2]}/{CONTENT_SHA256}",
        byte_size=len(CONTENT),
        collector_version="1.0.0",
        metadata_schema_version="0.1.0",
    )
    observation = CaptureObservation(
        observation_id=uuid7(),
        collection_run_id=uuid7(),
        attempt_number=1,
        endpoint_id=endpoint_id,
        source_id=source_id,
        requested_url=endpoint.url,
        resolved_url=endpoint.url,
        started_at=NOW,
        completed_at=NOW,
        outcome="SUCCEEDED",
        http_status=200,
        response_etag=None,
        response_last_modified=None,
        artifact_id=artifact_id,
        error_code=None,
        collector_name="synthetic",
        collector_version="1.0.0",
        policy_version=endpoint.policy_version,
    )
    session.add(source)
    session.flush()
    session.add_all([endpoint, artifact])
    session.flush()
    session.add(observation)
    session.flush()
    return observation


def evaluation(observation: CaptureObservation, **changes: object) -> AcquisitionEvaluation:
    values: dict[str, object] = {
        "acquisition_evaluation_id": uuid7(),
        "observation_id": observation.observation_id,
        "endpoint_id": observation.endpoint_id,
        "source_id": observation.source_id,
        "artifact_id": observation.artifact_id,
        "strategy_used": "STATIC_HTTP",
        "validation_status": "VALID",
        "challenge_type": None,
        "redirect_chain": [observation.requested_url, observation.resolved_url],
        "discovered_count": 1,
        "manual_intervention": False,
        "diagnostic_codes": [],
        "validator_name": "deepaha-content-validator",
        "validator_version": "1.0.0",
        "metrics_schema_version": "1.0.0",
        "validation_metrics": {"byte_size": len(CONTENT)},
        "evaluated_at": NOW,
        "contract_version": "1.0.0",
    }
    values.update(changes)
    return AcquisitionEvaluation(**values)


def test_acquisition_evaluation_table_has_expected_bindings(connection: Connection) -> None:
    inspector = inspect(connection)
    foreign_keys = inspector.get_foreign_keys("acquisition_evaluations")
    bindings = {
        tuple(item["constrained_columns"]): tuple(item["referred_columns"]) for item in foreign_keys
    }

    assert bindings[("observation_id", "endpoint_id", "source_id", "artifact_id")] == (
        "observation_id",
        "endpoint_id",
        "source_id",
        "artifact_id",
    )
    assert bindings[("endpoint_id", "source_id")] == ("endpoint_id", "source_id")
    assert bindings[("artifact_id", "source_id")] == ("artifact_id", "source_id")


def test_valid_evaluation_persists_and_observation_is_unique(session: Session) -> None:
    observation = seed_observation(session)
    session.add(evaluation(observation))
    session.flush()
    session.add(evaluation(observation))

    with pytest.raises(IntegrityError):
        session.flush()


def test_evaluation_rejects_cross_bound_artifact(session: Session) -> None:
    first = seed_observation(session)
    second = seed_observation(session)
    session.add(evaluation(first, artifact_id=second.artifact_id))

    with pytest.raises(IntegrityError):
        session.flush()


def test_database_challenge_shape_fails_closed(session: Session) -> None:
    observation = seed_observation(session)
    session.add(
        evaluation(
            observation,
            validation_status="CAPTCHA_REQUIRED",
            challenge_type=None,
            diagnostic_codes=["CAPTCHA_MARKER"],
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_acquisition_evaluation_is_insert_only(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        observation = seed_observation(session)
        row = evaluation(observation)
        session.add(row)
        session.commit()
        row_id = row.acquisition_evaluation_id

    with pytest.raises(DBAPIError, match="immutable"), migrated_engine.begin() as connection:
        connection.execute(
            text(
                "update acquisition_evaluations set discovered_count = 99 "
                "where acquisition_evaluation_id = :row_id"
            ),
            {"row_id": row_id},
        )
