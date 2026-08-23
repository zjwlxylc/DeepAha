from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.core.settings import Settings
from deepaha.sources.collector import CollectionRunner
from deepaha.sources.models import CaptureObservation, Source, SourceEndpoint
from deepaha.sources.transport import (
    HttpRequest,
    HttpResponse,
    NetworkTransportTimeout,
)

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)


class ScriptedTransport:
    def __init__(self, script: list[HttpResponse | Exception]) -> None:
        self.script = iter(script)
        self.requests: list[HttpRequest] = []

    def get_once(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        value = next(self.script)
        if isinstance(value, Exception):
            raise value
        return value


class PublicResolver:
    def resolve(self, host: str) -> tuple[str, ...]:
        assert host == "official.example"
        return ("93.184.216.34",)


class AdvancingClock:
    def __init__(self) -> None:
        self.value = NOW

    def now(self) -> datetime:
        return self.value

    def advance(self, *, hours: int) -> None:
        self.value += timedelta(hours=hours)


class FakeSleeper:
    def __init__(self) -> None:
        self.delays: list[int] = []

    def sleep(self, seconds: int) -> None:
        self.delays.append(seconds)


@pytest.fixture(scope="module")
def object_store() -> S3ObjectStore:
    store = S3ObjectStore(Settings())
    store.ensure_bucket()
    return store


@pytest.fixture
def owned_session_factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_engine, expire_on_commit=False)


def create_endpoint(factory: sessionmaker[Session]) -> SourceEndpoint:
    source_id = uuid7()
    endpoint_id = uuid7()
    source = Source(
        source_id=source_id,
        public_id=f"src_{source_id.hex}",
        canonical_url=f"https://official.example/source/{source_id.hex}",
        authority_name="Synthetic official authority",
        tier="OFFICIAL_PRIMARY",
        jurisdiction="Synthetic jurisdiction",
        active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    endpoint = SourceEndpoint(
        endpoint_id=endpoint_id,
        source_id=source_id,
        url="https://official.example/list",
        allowed_hosts=["official.example"],
        expected_media_types=["text/html"],
        browser_policy="NEVER",
        minimum_interval_seconds=21600,
        timeout_seconds=30,
        max_attempts=3,
        robots_url="https://official.example/robots.txt",
        robots_decision="ALLOWED",
        robots_checked_at=NOW,
        content_use_basis="LINK_ONLY",
        license_name=None,
        license_url=None,
        attribution="Synthetic official authority",
        fixture_storage_allowed=False,
        usage_note="Synthetic collection integration fixture.",
        policy_version="2026-08-21.1",
        active=True,
        verified_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    with factory.begin() as session:
        session.add_all([source, endpoint])
    return endpoint


def response(
    status: int,
    body: bytes,
    *,
    etag: str | None = None,
    media_type: str | None = "text/html; charset=utf-8",
) -> HttpResponse:
    return HttpResponse(
        status_code=status,
        url="https://official.example/list",
        media_type=media_type,
        etag=etag,
        last_modified=None,
        location=None,
        body=body,
    )


def runner_for(
    *,
    factory: sessionmaker[Session],
    object_store: S3ObjectStore,
    transport: ScriptedTransport,
    clock: AdvancingClock,
    sleeper: FakeSleeper | None = None,
) -> CollectionRunner:
    return CollectionRunner(
        session_factory=factory,
        object_store=object_store,
        transport=transport,
        resolver=PublicResolver(),
        clock=clock,
        sleeper=sleeper or FakeSleeper(),
    )


def observations_for(factory: sessionmaker[Session], endpoint_id: UUID) -> list[CaptureObservation]:
    with factory() as session:
        return list(
            session.scalars(
                select(CaptureObservation)
                .where(CaptureObservation.endpoint_id == endpoint_id)
                .order_by(CaptureObservation.started_at, CaptureObservation.attempt_number)
            )
        )


def test_same_bytes_create_two_observations_one_artifact(
    owned_session_factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint = create_endpoint(owned_session_factory)
    clock = AdvancingClock()
    runner = runner_for(
        factory=owned_session_factory,
        object_store=object_store,
        transport=ScriptedTransport(
            [
                response(200, b"official"),
                response(200, b"official", media_type="text/html; charset=gbk"),
            ]
        ),
        clock=clock,
    )

    runner.collect(endpoint.endpoint_id)
    clock.advance(hours=6)
    runner.collect(endpoint.endpoint_id)

    rows = observations_for(owned_session_factory, endpoint.endpoint_id)
    assert len(rows) == 2
    assert rows[0].artifact_id == rows[1].artifact_id
    with owned_session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(RawArtifact)
                .where(RawArtifact.source_id == endpoint.source_id)
            )
            == 1
        )


def test_final_failure_persists_every_failed_attempt_and_no_artifact(
    owned_session_factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint = create_endpoint(owned_session_factory)
    sleeper = FakeSleeper()
    runner = runner_for(
        factory=owned_session_factory,
        object_store=object_store,
        transport=ScriptedTransport(
            [NetworkTransportTimeout(), response(503, b"no"), response(503, b"no")]
        ),
        clock=AdvancingClock(),
        sleeper=sleeper,
    )

    result = runner.collect(endpoint.endpoint_id)

    rows = observations_for(owned_session_factory, endpoint.endpoint_id)
    assert len(rows) == 3
    assert all(row.outcome == "FAILED" and row.artifact_id is None for row in rows)
    assert result.final_error_code == "HTTP_RETRYABLE_EXHAUSTED"
    assert sleeper.delays == [1, 2]
    with owned_session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(RawArtifact)
                .where(RawArtifact.source_id == endpoint.source_id)
            )
            == 0
        )


def test_304_references_previous_artifact_and_uses_etag(
    owned_session_factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint = create_endpoint(owned_session_factory)
    clock = AdvancingClock()
    transport = ScriptedTransport(
        [response(200, b"official-v1", etag='"v1"'), response(304, b"", media_type=None)]
    )
    runner = runner_for(
        factory=owned_session_factory,
        object_store=object_store,
        transport=transport,
        clock=clock,
    )

    runner.collect(endpoint.endpoint_id)
    clock.advance(hours=6)
    runner.collect(endpoint.endpoint_id)

    rows = observations_for(owned_session_factory, endpoint.endpoint_id)
    assert [row.outcome for row in rows] == ["SUCCEEDED", "NOT_MODIFIED"]
    assert rows[0].artifact_id == rows[1].artifact_id
    assert transport.requests[1].headers["If-None-Match"] == '"v1"'


def test_rate_limit_failure_is_persisted_without_transport_call(
    owned_session_factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint = create_endpoint(owned_session_factory)
    clock = AdvancingClock()
    transport = ScriptedTransport([response(200, b"official")])
    runner = runner_for(
        factory=owned_session_factory,
        object_store=object_store,
        transport=transport,
        clock=clock,
    )

    runner.collect(endpoint.endpoint_id)
    result = runner.collect(endpoint.endpoint_id)

    assert result.final_error_code == "RATE_LIMIT_NOT_ELAPSED"
    assert len(transport.requests) == 1
    assert [
        row.error_code for row in observations_for(owned_session_factory, endpoint.endpoint_id)
    ] == [
        None,
        "RATE_LIMIT_NOT_ELAPSED",
    ]


def test_policy_bound_dynamic_url_is_preserved_in_observation(
    owned_session_factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint = create_endpoint(owned_session_factory)
    requested_url = "https://official.example/detail/notice-1"
    runner = runner_for(
        factory=owned_session_factory,
        object_store=object_store,
        transport=ScriptedTransport([response(200, b"official detail", media_type="text/html")]),
        clock=AdvancingClock(),
    )

    result = runner.collect(endpoint.endpoint_id, requested_url=requested_url)

    with owned_session_factory() as session:
        observation = session.get(CaptureObservation, result.attempts[0].observation_id)
        assert observation is not None
        assert observation.requested_url == requested_url
        assert observation.resolved_url == "https://official.example/list"
    assert result.attempts[0].redirect_chain == (
        requested_url,
        "https://official.example/list",
    )
