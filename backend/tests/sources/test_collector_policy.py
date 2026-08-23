from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from typing import Self
from uuid import UUID

import pytest

from deepaha.contracts.phase2 import SourceEndpointSchema
from deepaha.sources.collector import collect_http_attempts
from deepaha.sources.transport import (
    HttpRequest,
    HttpResponse,
    HttpxTransport,
    NetworkTransportError,
    NetworkTransportTimeout,
    ResponseTooLarge,
)

NOW = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)
SOURCE_ID = UUID("0198d239-4b00-7000-8000-000000000301")
ENDPOINT_ID = UUID("0198d239-4b00-7000-8000-000000000302")
ARTIFACT_ID = UUID("0198d239-4b00-7000-8000-000000000303")


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


class FakeResolver:
    def __init__(self, addresses: dict[str, tuple[str, ...]] | None = None) -> None:
        self.addresses = addresses or {}
        self.hosts: list[str] = []

    def resolve(self, host: str) -> tuple[str, ...]:
        self.hosts.append(host)
        return self.addresses.get(host, ("93.184.216.34",))


class FakeClock:
    def now(self) -> datetime:
        return NOW


class FakeSleeper:
    def __init__(self) -> None:
        self.delays: list[int] = []

    def sleep(self, seconds: int) -> None:
        self.delays.append(seconds)


class FakeStreamingResponse:
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self.status_code = 200
        self.url = "https://official.example/list"
        self.headers = {
            "Content-Type": "text/html; charset=utf-8",
            "ETag": '"v1"',
            "Last-Modified": "Thu, 21 Aug 2026 09:00:00 GMT",
            "Set-Cookie": "must-not-be-retained=secret",
        }
        self._chunks = chunks

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def iter_bytes(self) -> Iterator[bytes]:
        return iter(self._chunks)


class FakeHttpxClient:
    def __init__(
        self,
        *,
        response: FakeStreamingResponse,
        client_options: list[dict[str, object]],
        stream_calls: list[dict[str, object]],
        **options: object,
    ) -> None:
        client_options.append(options)
        self._response = response
        self._stream_calls = stream_calls

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def stream(self, method: str, url: str, *, headers: dict[str, str]) -> FakeStreamingResponse:
        self._stream_calls.append({"method": method, "url": url, "headers": headers})
        return self._response


@dataclass(frozen=True, slots=True)
class HarnessResult:
    attempts: list[object]
    requests: list[HttpRequest]
    sleeps: list[int]


def endpoint(**changes: object) -> SourceEndpointSchema:
    payload: dict[str, object] = {
        "endpoint_id": str(ENDPOINT_ID),
        "source_id": str(SOURCE_ID),
        "url": "https://official.example/list",
        "allowed_hosts": ["official.example"],
        "expected_media_types": ["text/html"],
        "browser_policy": "NEVER",
        "minimum_interval_seconds": 21600,
        "timeout_seconds": 30,
        "max_attempts": 3,
        "robots_url": "https://official.example/robots.txt",
        "robots_decision": "ALLOWED",
        "robots_checked_at": NOW,
        "content_use_basis": "LINK_ONLY",
        "license_name": None,
        "license_url": None,
        "attribution": "Official example",
        "fixture_storage_allowed": False,
        "usage_note": "Synthetic policy fixture.",
        "policy_version": "2026-08-21.1",
        "active": True,
        "verified_at": NOW,
        "created_at": NOW,
        "updated_at": NOW,
    }
    payload.update(changes)
    return SourceEndpointSchema.model_validate(payload)


def response(
    status: int = 200,
    body: bytes = b"official",
    *,
    url: str = "https://official.example/list",
    media_type: str | None = "text/html; charset=utf-8",
    location: str | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
) -> HttpResponse:
    return HttpResponse(
        status_code=status,
        url=url,
        media_type=media_type,
        etag=etag,
        last_modified=last_modified,
        location=location,
        body=body,
    )


def run_scripted(
    script: list[HttpResponse | Exception],
    *,
    source_active: bool = True,
    rate_limit_elapsed: bool = True,
    previous_artifact_id: UUID | None = None,
    conditional_etag: str | None = None,
    conditional_last_modified: str | None = None,
    policy: SourceEndpointSchema | None = None,
    resolver: FakeResolver | None = None,
) -> HarnessResult:
    transport = ScriptedTransport(script)
    sleeper = FakeSleeper()
    attempts = list(
        collect_http_attempts(
            endpoint=policy or endpoint(),
            source_active=source_active,
            rate_limit_elapsed=rate_limit_elapsed,
            previous_artifact_id=previous_artifact_id,
            conditional_etag=conditional_etag,
            conditional_last_modified=conditional_last_modified,
            transport=transport,
            resolver=resolver or FakeResolver(),
            clock=FakeClock(),
            sleeper=sleeper,
        )
    )
    return HarnessResult(
        attempts=list(attempts),
        requests=transport.requests,
        sleeps=sleeper.delays,
    )


def outcomes(result: HarnessResult) -> list[str]:
    return [str(getattr(attempt, "outcome")) for attempt in result.attempts]


def errors(result: HarnessResult) -> list[str | None]:
    return [getattr(attempt, "error_code") for attempt in result.attempts]


def test_retry_records_every_attempt() -> None:
    result = run_scripted(
        [
            NetworkTransportTimeout(),
            response(503, b"unavailable"),
            response(200, b"official"),
        ]
    )

    assert outcomes(result) == ["FAILED", "FAILED", "SUCCEEDED"]
    assert result.sleeps == [1, 2]
    assert len(result.requests) == 3


def test_unapproved_redirect_stops_before_follow() -> None:
    result = run_scripted([response(302, b"", location="https://evil.example/file")])

    assert errors(result) == ["REDIRECT_HOST_NOT_ALLOWED"]
    assert len(result.requests) == 1


def test_redirect_with_embedded_credentials_stops_before_follow() -> None:
    result = run_scripted(
        [
            response(
                302,
                b"",
                location="https://operator:secret@official.example/file",
            )
        ]
    )

    assert errors(result) == ["REDIRECT_HOST_NOT_ALLOWED"]
    assert len(result.requests) == 1


@pytest.mark.parametrize(
    ("policy_changes", "source_active", "rate_elapsed", "error_code"),
    [
        ({"active": False}, True, True, "ROBOTS_NOT_APPROVED"),
        ({"robots_decision": "UNKNOWN", "active": False}, True, True, "ROBOTS_NOT_APPROVED"),
        (
            {"content_use_basis": "UNKNOWN", "active": False},
            True,
            True,
            "ROBOTS_NOT_APPROVED",
        ),
        ({}, False, True, "ROBOTS_NOT_APPROVED"),
        ({}, True, False, "RATE_LIMIT_NOT_ELAPSED"),
    ],
)
def test_preflight_policy_failure_never_calls_transport(
    policy_changes: dict[str, object],
    source_active: bool,
    rate_elapsed: bool,
    error_code: str,
) -> None:
    result = run_scripted(
        [],
        source_active=source_active,
        rate_limit_elapsed=rate_elapsed,
        policy=endpoint(**policy_changes),
    )

    assert errors(result) == [error_code]
    assert result.requests == []


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "169.254.1.1", "224.0.0.1"])
def test_resolved_non_public_address_is_rejected(address: str) -> None:
    result = run_scripted([], resolver=FakeResolver({"official.example": (address,)}))

    assert errors(result) == ["HOST_NOT_ALLOWED"]
    assert result.requests == []


def test_literal_private_address_is_rejected() -> None:
    private = endpoint(
        url="https://127.0.0.1/list",
        allowed_hosts=["127.0.0.1"],
        robots_url="https://127.0.0.1/robots.txt",
    )

    result = run_scripted([], policy=private)

    assert errors(result) == ["HOST_NOT_ALLOWED"]
    assert result.requests == []


def test_valid_304_references_previous_artifact_and_sends_conditions() -> None:
    result = run_scripted(
        [response(304, b"", media_type=None)],
        previous_artifact_id=ARTIFACT_ID,
        conditional_etag='"v1"',
        conditional_last_modified="Thu, 21 Aug 2026 09:00:00 GMT",
    )

    assert outcomes(result) == ["NOT_MODIFIED"]
    assert getattr(result.attempts[0], "artifact_id") == ARTIFACT_ID
    assert result.requests[0].headers["If-None-Match"] == '"v1"'
    assert "If-Modified-Since" in result.requests[0].headers


def test_304_without_previous_artifact_is_invalid() -> None:
    result = run_scripted([response(304, b"", media_type=None)])

    assert errors(result) == ["NOT_MODIFIED_WITHOUT_ARTIFACT"]


@pytest.mark.parametrize(
    ("script", "error_code"),
    [
        ([response(200, b"")], "EMPTY_RESPONSE"),
        ([response(200, media_type="application/pdf")], "MEDIA_TYPE_NOT_ALLOWED"),
        ([ResponseTooLarge()], "RESPONSE_TOO_LARGE"),
        ([response(404, b"missing")], "HTTP_PERMANENT"),
    ],
)
def test_permanent_failure_records_one_attempt(
    script: list[HttpResponse | Exception], error_code: str
) -> None:
    result = run_scripted(script)

    assert outcomes(result) == ["FAILED"]
    assert errors(result) == [error_code]
    assert result.sleeps == []


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retryable_http_exhaustion_is_bounded(status: int) -> None:
    result = run_scripted([response(status), response(status), response(status)])

    assert outcomes(result) == ["FAILED", "FAILED", "FAILED"]
    assert errors(result)[-1] == "HTTP_RETRYABLE_EXHAUSTED"
    assert result.sleeps == [1, 2]
    assert len(result.requests) == 3


def test_network_error_exhaustion_is_bounded() -> None:
    result = run_scripted(
        [NetworkTransportError(), NetworkTransportError(), NetworkTransportError()]
    )

    assert outcomes(result) == ["FAILED", "FAILED", "FAILED"]
    assert errors(result) == ["NETWORK_ERROR", "NETWORK_ERROR", "NETWORK_ERROR"]
    assert result.sleeps == [1, 2]


def test_each_redirect_host_is_resolved_before_following() -> None:
    policy = endpoint(allowed_hosts=["official.example", "cdn.official.example"])
    resolver = FakeResolver()
    result = run_scripted(
        [
            response(302, b"", location="https://cdn.official.example/file"),
            response(200, url="https://cdn.official.example/file"),
        ],
        policy=policy,
        resolver=resolver,
    )

    assert outcomes(result) == ["SUCCEEDED"]
    assert resolver.hosts == ["official.example", "cdn.official.example"]
    assert len(result.requests) == 2


def test_attempt_iterator_is_lazy_so_persistence_can_happen_before_sleep() -> None:
    transport = ScriptedTransport([NetworkTransportTimeout(), response(200)])
    sleeper = FakeSleeper()
    iterator: Iterator[object] = collect_http_attempts(
        endpoint=endpoint(),
        source_active=True,
        rate_limit_elapsed=True,
        previous_artifact_id=None,
        conditional_etag=None,
        conditional_last_modified=None,
        transport=transport,
        resolver=FakeResolver(),
        clock=FakeClock(),
        sleeper=sleeper,
    )

    first = next(iterator)

    assert getattr(first, "outcome") == "FAILED"
    assert sleeper.delays == []
    second = next(iterator)
    assert getattr(second, "outcome") == "SUCCEEDED"
    assert sleeper.delays == [1]


def test_httpx_transport_is_bounded_and_retains_only_safe_response_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_options: list[dict[str, object]] = []
    stream_calls: list[dict[str, object]] = []
    fake_response = FakeStreamingResponse((b"official",))

    def client_factory(**options: object) -> FakeHttpxClient:
        return FakeHttpxClient(
            response=fake_response,
            client_options=client_options,
            stream_calls=stream_calls,
            **options,
        )

    monkeypatch.setattr("deepaha.sources.transport.httpx2.Client", client_factory)

    result = HttpxTransport().get_once(
        HttpRequest(
            url="https://official.example/list",
            headers={"If-None-Match": '"old"'},
            timeout_seconds=30,
        )
    )

    assert client_options == [{"follow_redirects": False, "trust_env": False, "timeout": 30}]
    sent_headers = stream_calls[0]["headers"]
    assert isinstance(sent_headers, dict)
    assert sent_headers["User-Agent"] == "DeepAha/0.2 (+https://github.com/zjwlxylc/DeepAha)"
    assert sent_headers["If-None-Match"] == '"old"'
    assert result.body == b"official"
    assert result.etag == '"v1"'
    assert not hasattr(result, "set_cookie")


def test_httpx_transport_stops_streaming_when_limit_is_crossed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_response = FakeStreamingResponse((b"abc", b"def"))

    def client_factory(**options: object) -> FakeHttpxClient:
        return FakeHttpxClient(
            response=fake_response,
            client_options=[],
            stream_calls=[],
            **options,
        )

    monkeypatch.setattr("deepaha.sources.transport.httpx2.Client", client_factory)

    with pytest.raises(ResponseTooLarge):
        HttpxTransport().get_once(
            HttpRequest(
                url="https://official.example/list",
                headers={},
                timeout_seconds=30,
                max_bytes=5,
            )
        )
