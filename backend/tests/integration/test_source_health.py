from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest
from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.sources.health import get_source_health
from deepaha.sources.models import CaptureObservation, Source, SourceEndpoint

pytestmark = pytest.mark.integration
AS_OF = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def add_endpoint(session: Session) -> tuple[SourceEndpoint, RawArtifact]:
    source_id = uuid7()
    endpoint_id = uuid7()
    artifact_id = uuid7()
    digest = source_id.hex * 2
    source = Source(
        source_id=source_id,
        public_id=f"src_{source_id.hex}",
        canonical_url=f"https://health.example/{source_id.hex}",
        authority_name="Synthetic health authority",
        tier="OFFICIAL_PRIMARY",
        jurisdiction=None,
        active=True,
        created_at=AS_OF - timedelta(days=2),
        updated_at=AS_OF - timedelta(days=2),
    )
    endpoint = SourceEndpoint(
        endpoint_id=endpoint_id,
        source_id=source_id,
        url=f"https://health.example/{source_id.hex}/list",
        allowed_hosts=["health.example"],
        expected_media_types=["text/html"],
        browser_policy="NEVER",
        minimum_interval_seconds=21600,
        timeout_seconds=30,
        max_attempts=3,
        robots_url="https://health.example/robots.txt",
        robots_decision="ALLOWED",
        robots_checked_at=AS_OF - timedelta(days=2),
        content_use_basis="LINK_ONLY",
        license_name=None,
        license_url=None,
        attribution=None,
        fixture_storage_allowed=False,
        usage_note="Synthetic health fixture.",
        policy_version="2026-08-21.1",
        active=True,
        verified_at=AS_OF - timedelta(days=2),
        created_at=AS_OF - timedelta(days=2),
        updated_at=AS_OF - timedelta(days=2),
    )
    artifact = RawArtifact(
        artifact_id=artifact_id,
        source_id=source_id,
        requested_url=endpoint.url,
        resolved_url=endpoint.url,
        retrieved_at=AS_OF - timedelta(hours=2),
        http_status=200,
        media_type="text/html",
        content_sha256=digest,
        storage_bucket="deepaha-raw",
        object_key=f"raw/sha256/{digest[:2]}/{digest}",
        byte_size=64,
        collector_version="test/0.2.0",
        metadata_schema_version="0.2.0",
    )
    session.add_all([source, endpoint])
    session.flush()
    session.add(artifact)
    session.flush()
    return endpoint, artifact


def add_observation(
    session: Session,
    endpoint: SourceEndpoint,
    artifact: RawArtifact,
    *,
    outcome: str,
    completed_at: datetime,
) -> None:
    has_artifact = outcome in {"SUCCEEDED", "NOT_MODIFIED"}
    session.add(
        CaptureObservation(
            observation_id=uuid7(),
            collection_run_id=uuid7(),
            attempt_number=1,
            endpoint_id=endpoint.endpoint_id,
            source_id=endpoint.source_id,
            requested_url=endpoint.url,
            resolved_url=endpoint.url,
            started_at=completed_at - timedelta(seconds=1),
            completed_at=completed_at,
            outcome=outcome,
            http_status=304 if outcome == "NOT_MODIFIED" else 200,
            response_etag='"v1"' if has_artifact else None,
            response_last_modified=None,
            artifact_id=artifact.artifact_id if has_artifact else None,
            error_code=None if has_artifact else "NETWORK_TIMEOUT",
            collector_name="test",
            collector_version="0.2.0",
            policy_version="2026-08-21.1",
        )
    )
    session.flush()


def test_health_is_derived_from_observations(session: Session) -> None:
    endpoint, artifact = add_endpoint(session)
    add_observation(
        session,
        endpoint,
        artifact,
        outcome="SUCCEEDED",
        completed_at=AS_OF - timedelta(hours=2),
    )
    add_observation(
        session,
        endpoint,
        artifact,
        outcome="FAILED",
        completed_at=AS_OF - timedelta(hours=1),
    )
    add_observation(
        session,
        endpoint,
        artifact,
        outcome="FAILED",
        completed_at=AS_OF - timedelta(minutes=30),
    )

    value = get_source_health(session, endpoint.endpoint_id, AS_OF)

    assert (value.attempts_24h, value.successes_24h, value.consecutive_failures) == (3, 1, 2)
    assert value.failures_24h == 2
    assert value.last_attempt_at == AS_OF - timedelta(minutes=30)
    assert value.last_success_at == AS_OF - timedelta(hours=2)
    assert value.latest_artifact_id == artifact.artifact_id
    assert value.latest_content_sha256 == artifact.content_sha256
    assert value.latest_object_key == artifact.object_key


def test_not_modified_is_valid_without_replacing_last_artifact(session: Session) -> None:
    endpoint, artifact = add_endpoint(session)
    add_observation(
        session,
        endpoint,
        artifact,
        outcome="SUCCEEDED",
        completed_at=AS_OF - timedelta(hours=7),
    )
    add_observation(
        session,
        endpoint,
        artifact,
        outcome="NOT_MODIFIED",
        completed_at=AS_OF - timedelta(hours=1),
    )

    value = get_source_health(session, endpoint.endpoint_id, AS_OF)

    assert value.successes_24h == 1
    assert value.not_modified_24h == 1
    assert value.failures_24h == 0
    assert value.consecutive_failures == 0
    assert value.last_success_at == AS_OF - timedelta(hours=1)
    assert value.latest_artifact_id == artifact.artifact_id


def test_rows_older_than_24_hours_and_future_rows_are_excluded(session: Session) -> None:
    endpoint, artifact = add_endpoint(session)
    add_observation(
        session,
        endpoint,
        artifact,
        outcome="SUCCEEDED",
        completed_at=AS_OF - timedelta(hours=25),
    )
    add_observation(
        session,
        endpoint,
        artifact,
        outcome="FAILED",
        completed_at=AS_OF - timedelta(hours=23),
    )
    add_observation(
        session,
        endpoint,
        artifact,
        outcome="SUCCEEDED",
        completed_at=AS_OF + timedelta(minutes=1),
    )

    value = get_source_health(session, endpoint.endpoint_id, AS_OF)

    assert value.attempts_24h == 1
    assert value.failures_24h == 1
    assert value.successes_24h == 0
    assert value.last_attempt_at == AS_OF - timedelta(hours=23)
    assert value.consecutive_failures == 1


def test_health_requires_an_existing_endpoint(session: Session) -> None:
    missing = UUID("0198d239-4b00-7000-8000-000000000499")

    with pytest.raises(LookupError, match="SourceEndpoint not found"):
        get_source_health(session, missing, AS_OF)
