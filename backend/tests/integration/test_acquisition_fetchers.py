from datetime import UTC, datetime
from hashlib import sha256

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.contracts import FetchRequest
from deepaha.acquisition.fetchers import (
    FetchPolicyMismatch,
    OfficialAlternativeFetcher,
    StaticHttpFetcher,
)
from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.core.settings import Settings
from deepaha.sources.collector import CollectionRunner
from deepaha.sources.transport import NetworkTransportTimeout
from tests.integration.test_collection_service import (
    AdvancingClock,
    FakeSleeper,
    PublicResolver,
    ScriptedTransport,
    create_endpoint,
    response,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def object_store() -> S3ObjectStore:
    value = S3ObjectStore(Settings())
    value.ensure_bucket()
    return value


@pytest.fixture
def factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_engine, expire_on_commit=False)


def request(endpoint_id: object, source_id: object, **changes: object) -> FetchRequest:
    values: dict[str, object] = {
        "request_id": "019c0000-0000-7000-8000-000000000201",
        "source_id": source_id,
        "endpoint_id": endpoint_id,
        "requested_url": "https://official.example/detail/notice-1",
        "strategy": "STATIC_HTTP",
        "allowed_hosts": ["official.example"],
        "expected_media_types": ["text/html"],
        "timeout_seconds": 20,
        "max_attempts": 2,
        "max_bytes": 1_000_000,
        "policy_version": "2026-08-21.1",
        "contract_version": "1.0.0",
    }
    values.update(changes)
    return FetchRequest.model_validate(values)


def fetcher(
    factory: sessionmaker[Session],
    object_store: S3ObjectStore,
    transport: ScriptedTransport,
) -> StaticHttpFetcher:
    runner = CollectionRunner(
        session_factory=factory,
        object_store=object_store,
        transport=transport,
        resolver=PublicResolver(),
        clock=AdvancingClock(),
        sleeper=FakeSleeper(),
    )
    return StaticHttpFetcher(session_factory=factory, collection_runner=runner)


def official_alternative_fetcher(
    factory: sessionmaker[Session],
    object_store: S3ObjectStore,
    transport: ScriptedTransport,
) -> OfficialAlternativeFetcher:
    runner = CollectionRunner(
        session_factory=factory,
        object_store=object_store,
        transport=transport,
        resolver=PublicResolver(),
        clock=AdvancingClock(),
        sleeper=FakeSleeper(),
    )
    return OfficialAlternativeFetcher(session_factory=factory, collection_runner=runner)


def test_static_fetcher_reuses_collector_and_returns_object_reference(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint = create_endpoint(factory)
    body = b"official detail from generic fetcher"
    transport = ScriptedTransport(
        [
            response(
                200,
                body,
                media_type="text/html; charset=utf-8",
                etag='"v1"',
            )
        ]
    )

    result = fetcher(factory, object_store, transport).fetch(
        request(endpoint.endpoint_id, endpoint.source_id)
    )

    assert result.outcome == "SUCCEEDED"
    assert result.observation_id is not None
    assert result.artifact_id is not None
    assert result.body is None
    assert (
        result.body_object_key
        == f"raw/sha256/{sha256(body).hexdigest()[:2]}/{sha256(body).hexdigest()}"
    )
    assert result.content_sha256 == sha256(body).hexdigest()
    assert result.safe_headers == {"etag": '"v1"'}
    assert [item.url for item in transport.requests] == ["https://official.example/detail/notice-1"]


def test_static_fetcher_persists_nonempty_unexpected_mime_for_semantic_validation(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint = create_endpoint(factory)
    body = b"not actually expected html"
    transport = ScriptedTransport([response(200, body, media_type="application/pdf")])

    result = fetcher(factory, object_store, transport).fetch(
        request(endpoint.endpoint_id, endpoint.source_id)
    )

    assert result.outcome == "SUCCEEDED"
    assert result.media_type == "application/pdf"
    assert result.body_object_key is not None


def test_static_fetcher_returns_bounded_transport_failure_without_artifact(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint = create_endpoint(factory)
    transport = ScriptedTransport([NetworkTransportTimeout(), NetworkTransportTimeout()])

    result = fetcher(factory, object_store, transport).fetch(
        request(endpoint.endpoint_id, endpoint.source_id)
    )

    assert result.outcome == "FAILED"
    assert result.error_code == "NETWORK_TIMEOUT"
    assert result.body is None
    assert result.body_object_key is None
    assert result.content_sha256 is None
    assert len(transport.requests) == 2


def test_static_fetcher_rejects_request_that_does_not_replay_endpoint_policy(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint = create_endpoint(factory)
    transport = ScriptedTransport([])

    with pytest.raises(FetchPolicyMismatch, match="FETCH_POLICY_MISMATCH"):
        fetcher(factory, object_store, transport).fetch(
            request(
                endpoint.endpoint_id,
                endpoint.source_id,
                allowed_hosts=["official.example", "cdn.official.example"],
            )
        )

    assert transport.requests == []


def test_static_fetcher_uses_fetch_time_from_injected_collector_clock(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint = create_endpoint(factory)
    result = fetcher(
        factory,
        object_store,
        ScriptedTransport([response(200, b"official time")]),
    ).fetch(request(endpoint.endpoint_id, endpoint.source_id))

    assert result.fetched_at == datetime(2026, 8, 21, 9, 0, tzinfo=UTC)


def test_official_alternative_reuses_the_same_policy_bound_http_collection(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint = create_endpoint(factory)
    body = b"official alternative discovery"
    transport = ScriptedTransport([response(200, body)])

    result = official_alternative_fetcher(factory, object_store, transport).fetch(
        request(
            endpoint.endpoint_id,
            endpoint.source_id,
            strategy="OFFICIAL_ALTERNATIVE",
        )
    )

    assert result.strategy == "OFFICIAL_ALTERNATIVE"
    assert result.fetcher_name == "deepaha-official-alternative"
    assert result.fetcher_version == "1.0.0"
    assert result.content_sha256 == sha256(body).hexdigest()
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    ("selected_fetcher", "strategy"),
    [("STATIC", "OFFICIAL_ALTERNATIVE"), ("ALTERNATIVE", "STATIC_HTTP")],
)
def test_policy_bound_http_fetchers_reject_a_different_declared_strategy(
    factory: sessionmaker[Session],
    object_store: S3ObjectStore,
    selected_fetcher: str,
    strategy: str,
) -> None:
    endpoint = create_endpoint(factory)
    transport = ScriptedTransport([])
    selected = (
        fetcher(factory, object_store, transport)
        if selected_fetcher == "STATIC"
        else official_alternative_fetcher(factory, object_store, transport)
    )

    with pytest.raises(FetchPolicyMismatch, match="FETCH_POLICY_MISMATCH"):
        selected.fetch(request(endpoint.endpoint_id, endpoint.source_id, strategy=strategy))

    assert transport.requests == []
