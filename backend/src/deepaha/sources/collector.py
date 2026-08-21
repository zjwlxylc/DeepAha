import ipaddress
import socket
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from time import sleep
from typing import Protocol
from urllib.parse import urljoin, urlsplit
from uuid import UUID, uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.artifacts.object_store import ObjectStore
from deepaha.artifacts.observed import import_observed_raw_artifact
from deepaha.artifacts.service import ImportRawArtifactCommand
from deepaha.contracts.phase2 import SourceEndpointSchema
from deepaha.sources.models import CaptureObservation, Source, SourceEndpoint
from deepaha.sources.transport import (
    HostResolver,
    HttpRequest,
    HttpResponse,
    HttpTransport,
    NetworkTransportError,
    NetworkTransportTimeout,
    ResponseTooLarge,
)

RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 5


class Clock(Protocol):
    def now(self) -> datetime:
        raise NotImplementedError


class Sleeper(Protocol):
    def sleep(self, seconds: int) -> None:
        raise NotImplementedError


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SystemSleeper:
    def sleep(self, seconds: int) -> None:
        sleep(seconds)


class SocketHostResolver:
    def resolve(self, host: str) -> tuple[str, ...]:
        try:
            records = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError as error:
            raise NetworkTransportError from error
        return tuple(sorted({str(record[4][0]) for record in records}))


@dataclass(frozen=True, slots=True)
class CollectionAttempt:
    attempt_number: int
    outcome: str
    http_status: int | None
    artifact_id: UUID | None
    error_code: str | None
    started_at: datetime
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class CollectionRunResult:
    collection_run_id: UUID
    attempts: tuple[CollectionAttempt, ...]

    @property
    def final_error_code(self) -> str | None:
        if not self.attempts:
            return None
        return self.attempts[-1].error_code


@dataclass(frozen=True, slots=True)
class _AttemptDecision:
    attempt_number: int
    started_at: datetime
    completed_at: datetime
    outcome: str
    http_status: int | None
    resolved_url: str | None
    response_etag: str | None
    response_last_modified: str | None
    artifact_id: UUID | None
    error_code: str | None
    media_type: str | None
    body: bytes | None
    retryable: bool = False


class _HostPolicyError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def collect_http_attempts(
    *,
    endpoint: SourceEndpointSchema,
    source_active: bool,
    rate_limit_elapsed: bool,
    previous_artifact_id: UUID | None,
    conditional_etag: str | None,
    conditional_last_modified: str | None,
    transport: HttpTransport,
    resolver: HostResolver,
    clock: Clock,
    sleeper: Sleeper,
) -> Iterator[_AttemptDecision]:
    policy_error = _preflight_error(endpoint, source_active, rate_limit_elapsed)
    if policy_error is not None:
        now = clock.now()
        yield _failed_decision(1, now, now, policy_error)
        return

    headers: dict[str, str] = {}
    if conditional_etag is not None:
        headers["If-None-Match"] = conditional_etag
    if conditional_last_modified is not None:
        headers["If-Modified-Since"] = conditional_last_modified

    for attempt_number in range(1, endpoint.max_attempts + 1):
        started_at = clock.now()
        try:
            response = _get_with_redirects(
                endpoint=endpoint,
                headers=headers,
                transport=transport,
                resolver=resolver,
            )
            decision = _classify_response(
                attempt_number=attempt_number,
                started_at=started_at,
                completed_at=clock.now(),
                response=response,
                expected_media_types=endpoint.expected_media_types,
                previous_artifact_id=previous_artifact_id,
            )
        except _HostPolicyError as error:
            decision = _failed_decision(
                attempt_number,
                started_at,
                clock.now(),
                error.code,
            )
        except NetworkTransportTimeout:
            decision = _failed_decision(
                attempt_number,
                started_at,
                clock.now(),
                "NETWORK_TIMEOUT",
                retryable=True,
            )
        except NetworkTransportError:
            decision = _failed_decision(
                attempt_number,
                started_at,
                clock.now(),
                "NETWORK_ERROR",
                retryable=True,
            )
        except ResponseTooLarge:
            decision = _failed_decision(
                attempt_number,
                started_at,
                clock.now(),
                "RESPONSE_TOO_LARGE",
            )

        final_attempt = attempt_number == endpoint.max_attempts
        if decision.retryable and final_attempt and decision.http_status in RETRYABLE_HTTP_STATUSES:
            decision = replace(decision, error_code="HTTP_RETRYABLE_EXHAUSTED")

        yield decision
        if not decision.retryable or final_attempt:
            return
        sleeper.sleep(attempt_number)


class CollectionRunner:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        object_store: ObjectStore,
        transport: HttpTransport,
        resolver: HostResolver,
        clock: Clock,
        sleeper: Sleeper,
        collector_name: str = "deepaha-http",
        collector_version: str = "0.2.0",
    ) -> None:
        self._session_factory = session_factory
        self._object_store = object_store
        self._transport = transport
        self._resolver = resolver
        self._clock = clock
        self._sleeper = sleeper
        self._collector_name = collector_name
        self._collector_version = collector_version

    def collect(self, endpoint_id: UUID) -> CollectionRunResult:
        endpoint, source_active, rate_elapsed, previous = self._load_context(endpoint_id)
        collection_run_id = uuid7()
        attempts: list[CollectionAttempt] = []
        for decision in collect_http_attempts(
            endpoint=endpoint,
            source_active=source_active,
            rate_limit_elapsed=rate_elapsed,
            previous_artifact_id=previous.artifact_id if previous is not None else None,
            conditional_etag=previous.etag if previous is not None else None,
            conditional_last_modified=(previous.last_modified if previous is not None else None),
            transport=self._transport,
            resolver=self._resolver,
            clock=self._clock,
            sleeper=self._sleeper,
        ):
            attempts.append(
                self._persist_decision(
                    endpoint=endpoint,
                    collection_run_id=collection_run_id,
                    decision=decision,
                )
            )
        return CollectionRunResult(collection_run_id=collection_run_id, attempts=tuple(attempts))

    def _load_context(
        self, endpoint_id: UUID
    ) -> tuple[SourceEndpointSchema, bool, bool, _PreviousCapture | None]:
        now = self._clock.now()
        with self._session_factory() as session:
            row = session.get(SourceEndpoint, endpoint_id)
            if row is None:
                raise LookupError(f"SourceEndpoint not found: {endpoint_id}")
            source_active = session.scalar(
                select(Source.active).where(Source.source_id == row.source_id)
            )
            if source_active is None:
                raise RuntimeError("SourceEndpoint owner could not be loaded")
            endpoint = _endpoint_contract(row)
            latest = session.scalar(
                select(CaptureObservation)
                .where(CaptureObservation.endpoint_id == endpoint_id)
                .order_by(CaptureObservation.completed_at.desc())
                .limit(1)
            )
            rate_elapsed = latest is None or (
                (now - latest.completed_at).total_seconds() >= endpoint.minimum_interval_seconds
            )
            previous_row = session.scalar(
                select(CaptureObservation)
                .where(
                    CaptureObservation.endpoint_id == endpoint_id,
                    CaptureObservation.outcome == "SUCCEEDED",
                    CaptureObservation.artifact_id.is_not(None),
                )
                .order_by(CaptureObservation.completed_at.desc())
                .limit(1)
            )
            previous = (
                _PreviousCapture(
                    artifact_id=previous_row.artifact_id,
                    etag=previous_row.response_etag,
                    last_modified=previous_row.response_last_modified,
                )
                if previous_row is not None and previous_row.artifact_id is not None
                else None
            )
            return endpoint, source_active, rate_elapsed, previous

    def _persist_decision(
        self,
        *,
        endpoint: SourceEndpointSchema,
        collection_run_id: UUID,
        decision: _AttemptDecision,
    ) -> CollectionAttempt:
        artifact_id = decision.artifact_id
        with self._session_factory.begin() as session:
            if decision.outcome == "SUCCEEDED":
                if decision.body is None or decision.resolved_url is None:
                    raise RuntimeError("successful attempt has no response evidence")
                imported = import_observed_raw_artifact(
                    session=session,
                    object_store=self._object_store,
                    command=ImportRawArtifactCommand(
                        source_id=endpoint.source_id,
                        requested_url=str(endpoint.url),
                        resolved_url=decision.resolved_url,
                        retrieved_at=decision.completed_at,
                        http_status=decision.http_status,
                        media_type=decision.media_type,
                        content=decision.body,
                        collector_version=self._collector_version,
                        metadata_schema_version="0.2.0",
                    ),
                )
                artifact_id = imported.artifact.artifact_id

            observation = CaptureObservation(
                observation_id=uuid7(),
                collection_run_id=collection_run_id,
                attempt_number=decision.attempt_number,
                endpoint_id=endpoint.endpoint_id,
                source_id=endpoint.source_id,
                requested_url=str(endpoint.url),
                resolved_url=decision.resolved_url,
                started_at=decision.started_at,
                completed_at=decision.completed_at,
                outcome=decision.outcome,
                http_status=decision.http_status,
                response_etag=decision.response_etag,
                response_last_modified=decision.response_last_modified,
                artifact_id=artifact_id,
                error_code=decision.error_code,
                collector_name=self._collector_name,
                collector_version=self._collector_version,
                policy_version=endpoint.policy_version,
            )
            session.add(observation)

        return CollectionAttempt(
            attempt_number=decision.attempt_number,
            outcome=decision.outcome,
            http_status=decision.http_status,
            artifact_id=artifact_id,
            error_code=decision.error_code,
            started_at=decision.started_at,
            completed_at=decision.completed_at,
        )


@dataclass(frozen=True, slots=True)
class _PreviousCapture:
    artifact_id: UUID
    etag: str | None
    last_modified: str | None


def _preflight_error(
    endpoint: SourceEndpointSchema, source_active: bool, rate_limit_elapsed: bool
) -> str | None:
    policy_not_approved = (
        not source_active
        or not endpoint.active
        or endpoint.robots_decision not in {"ALLOWED", "NOT_APPLICABLE"}
        or endpoint.content_use_basis == "UNKNOWN"
    )
    if policy_not_approved:
        return "ROBOTS_NOT_APPROVED"
    if not rate_limit_elapsed:
        return "RATE_LIMIT_NOT_ELAPSED"
    return None


def _get_with_redirects(
    *,
    endpoint: SourceEndpointSchema,
    headers: dict[str, str],
    transport: HttpTransport,
    resolver: HostResolver,
) -> HttpResponse:
    current_url = str(endpoint.url)
    is_redirect = False
    for redirect_count in range(MAX_REDIRECTS + 1):
        _require_public_allowed_url(
            current_url,
            endpoint.allowed_hosts,
            resolver,
            redirect=is_redirect,
        )
        response = transport.get_once(
            HttpRequest(
                url=current_url,
                headers=headers,
                timeout_seconds=endpoint.timeout_seconds,
            )
        )
        if response.status_code not in REDIRECT_STATUSES:
            return response
        if response.location is None or redirect_count == MAX_REDIRECTS:
            return response
        current_url = urljoin(current_url, response.location)
        is_redirect = True
    raise RuntimeError("redirect loop exceeded bounded iteration")


def _require_public_allowed_url(
    url: str,
    allowed_hosts: tuple[str, ...],
    resolver: HostResolver,
    *,
    redirect: bool,
) -> None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    error_code = "REDIRECT_HOST_NOT_ALLOWED" if redirect else "HOST_NOT_ALLOWED"
    if parsed.scheme not in {"http", "https"} or host not in allowed_hosts:
        raise _HostPolicyError(error_code)
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not _is_public_address(literal):
        raise _HostPolicyError(error_code)
    try:
        addresses = resolver.resolve(host)
    except NetworkTransportError:
        raise
    except OSError as error:
        raise NetworkTransportError from error
    if not addresses:
        raise NetworkTransportError
    try:
        resolved = tuple(ipaddress.ip_address(address) for address in addresses)
    except ValueError as error:
        raise NetworkTransportError from error
    if any(not _is_public_address(address) for address in resolved):
        raise _HostPolicyError(error_code)


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        )
        and address.is_global
    )


def _classify_response(
    *,
    attempt_number: int,
    started_at: datetime,
    completed_at: datetime,
    response: HttpResponse,
    expected_media_types: tuple[str, ...],
    previous_artifact_id: UUID | None,
) -> _AttemptDecision:
    if 200 <= response.status_code < 300:
        if not response.body:
            return _failed_decision(
                attempt_number,
                started_at,
                completed_at,
                "EMPTY_RESPONSE",
                response=response,
            )
        actual_media_type = (
            response.media_type.split(";", maxsplit=1)[0].strip().lower()
            if response.media_type is not None
            else None
        )
        expected = {
            value.split(";", maxsplit=1)[0].strip().lower() for value in expected_media_types
        }
        if actual_media_type not in expected:
            return _failed_decision(
                attempt_number,
                started_at,
                completed_at,
                "MEDIA_TYPE_NOT_ALLOWED",
                response=response,
            )
        return _AttemptDecision(
            attempt_number=attempt_number,
            started_at=started_at,
            completed_at=completed_at,
            outcome="SUCCEEDED",
            http_status=response.status_code,
            resolved_url=response.url,
            response_etag=response.etag,
            response_last_modified=response.last_modified,
            artifact_id=None,
            error_code=None,
            media_type=response.media_type,
            body=response.body,
        )

    if response.status_code == 304:
        if previous_artifact_id is None:
            return _failed_decision(
                attempt_number,
                started_at,
                completed_at,
                "NOT_MODIFIED_WITHOUT_ARTIFACT",
                response=response,
            )
        return _AttemptDecision(
            attempt_number=attempt_number,
            started_at=started_at,
            completed_at=completed_at,
            outcome="NOT_MODIFIED",
            http_status=304,
            resolved_url=response.url,
            response_etag=response.etag,
            response_last_modified=response.last_modified,
            artifact_id=previous_artifact_id,
            error_code=None,
            media_type=None,
            body=None,
        )

    if response.status_code in RETRYABLE_HTTP_STATUSES:
        return _failed_decision(
            attempt_number,
            started_at,
            completed_at,
            "HTTP_RETRYABLE_EXHAUSTED",
            response=response,
            retryable=True,
        )

    return _failed_decision(
        attempt_number,
        started_at,
        completed_at,
        "HTTP_PERMANENT",
        response=response,
    )


def _failed_decision(
    attempt_number: int,
    started_at: datetime,
    completed_at: datetime,
    error_code: str,
    *,
    response: HttpResponse | None = None,
    retryable: bool = False,
) -> _AttemptDecision:
    return _AttemptDecision(
        attempt_number=attempt_number,
        started_at=started_at,
        completed_at=completed_at,
        outcome="FAILED",
        http_status=response.status_code if response is not None else None,
        resolved_url=response.url if response is not None else None,
        response_etag=response.etag if response is not None else None,
        response_last_modified=response.last_modified if response is not None else None,
        artifact_id=None,
        error_code=error_code,
        media_type=response.media_type if response is not None else None,
        body=None,
        retryable=retryable,
    )


def _endpoint_contract(row: SourceEndpoint) -> SourceEndpointSchema:
    return SourceEndpointSchema.model_validate(
        {
            "endpoint_id": row.endpoint_id,
            "source_id": row.source_id,
            "url": row.url,
            "allowed_hosts": row.allowed_hosts,
            "expected_media_types": row.expected_media_types,
            "browser_policy": row.browser_policy,
            "minimum_interval_seconds": row.minimum_interval_seconds,
            "timeout_seconds": row.timeout_seconds,
            "max_attempts": row.max_attempts,
            "robots_url": row.robots_url,
            "robots_decision": row.robots_decision,
            "robots_checked_at": row.robots_checked_at,
            "content_use_basis": row.content_use_basis,
            "license_name": row.license_name,
            "license_url": row.license_url,
            "attribution": row.attribution,
            "fixture_storage_allowed": row.fixture_storage_allowed,
            "usage_note": row.usage_note,
            "policy_version": row.policy_version,
            "active": row.active,
            "verified_at": row.verified_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


__all__ = [
    "Clock",
    "CollectionAttempt",
    "CollectionRunResult",
    "CollectionRunner",
    "Sleeper",
    "SocketHostResolver",
    "SystemClock",
    "SystemSleeper",
    "collect_http_attempts",
]
