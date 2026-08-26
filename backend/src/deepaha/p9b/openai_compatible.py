import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Literal, Protocol, cast

import httpx2

from deepaha.artifacts.object_store import ObjectMetadata, ObjectStore
from deepaha.contracts.phase9b import ModelAttemptOutcome
from deepaha.local_human_test.provider_config import ResolvedProviderConfig
from deepaha.p9b.hashing import canonical_json_bytes
from deepaha.p9b.ledger_values import require_provider_response_id
from deepaha.p9b.provider import (
    ProviderAttemptResult,
    ProviderInvocation,
    ProviderOutcomeUnknownError,
)

MAX_PROVIDER_RESPONSE_BYTES = 10_000_000


class ProviderAdapterError(ValueError):
    """The configured adapter cannot execute the authorized invocation."""


class ProviderTransportBeforeSendError(RuntimeError):
    """The Provider request was not sent."""


class ProviderTransportAfterSendError(RuntimeError):
    """The Provider request may have been sent without a complete response."""


@dataclass(frozen=True, slots=True)
class ProviderHttpRequest:
    url: str
    headers: Mapping[str, str] = field(repr=False)
    json_body: Mapping[str, object] = field(repr=False)
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class ProviderHttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes

    def __post_init__(self) -> None:
        if not 100 <= self.status_code <= 599:
            raise ValueError("Provider HTTP status is invalid")


class ProviderTransport(Protocol):
    def send(self, request: ProviderHttpRequest) -> ProviderHttpResponse: ...


@dataclass(frozen=True, slots=True)
class _ProviderUsage:
    prompt_tokens: int
    completion_tokens: int
    prompt_cache_hit_tokens: int
    monetary_cost: Decimal | None


class HttpxProviderTransport:
    def __init__(self, *, transport: httpx2.BaseTransport | None = None) -> None:
        self._transport = transport

    def send(self, request: ProviderHttpRequest) -> ProviderHttpResponse:
        try:
            with (
                httpx2.Client(
                    follow_redirects=False,
                    trust_env=False,
                    transport=self._transport,
                ) as client,
                client.stream(
                    "POST",
                    request.url,
                    headers=request.headers,
                    json=request.json_body,
                    timeout=request.timeout_seconds,
                ) as response,
            ):
                declared_length = response.headers.get("Content-Length")
                if declared_length is not None:
                    try:
                        if int(declared_length) > MAX_PROVIDER_RESPONSE_BYTES:
                            raise ProviderTransportAfterSendError(
                                "Provider response exceeded the audit limit"
                            )
                    except ValueError:
                        pass
                body = bytearray()
                for chunk in response.iter_bytes():
                    if len(body) + len(chunk) > MAX_PROVIDER_RESPONSE_BYTES:
                        raise ProviderTransportAfterSendError(
                            "Provider response exceeded the audit limit"
                        )
                    body.extend(chunk)
                return ProviderHttpResponse(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    body=bytes(body),
                )
        except ProviderTransportAfterSendError:
            raise
        except (httpx2.ConnectError, httpx2.ConnectTimeout, httpx2.PoolTimeout) as error:
            raise ProviderTransportBeforeSendError("Provider connection failed") from error
        except (
            httpx2.ReadError,
            httpx2.ReadTimeout,
            httpx2.WriteError,
            httpx2.WriteTimeout,
            httpx2.RemoteProtocolError,
        ) as error:
            raise ProviderTransportAfterSendError(
                "Provider outcome is unknown after dispatch"
            ) from error
        except (httpx2.TransportError, httpx2.TimeoutException) as error:
            raise ProviderTransportAfterSendError(
                "Provider outcome is unknown after dispatch"
            ) from error


class OpenAICompatibleProviderAdapter:
    supports_idempotency = True

    def __init__(
        self,
        *,
        config: ResolvedProviderConfig,
        object_store: ObjectStore,
        transport: ProviderTransport | None = None,
        monotonic: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.provider = config.provider
        self._config = config
        self._object_store = object_store
        self._transport = transport or HttpxProviderTransport()
        self._monotonic = monotonic

    def invoke(self, request: ProviderInvocation) -> ProviderAttemptResult:
        self._validate_invocation(request)
        http_request = ProviderHttpRequest(
            url=f"{str(self._config.base_url).rstrip('/')}/chat/completions",
            headers=self._headers(request),
            json_body=invocation_payload(request),
            timeout_seconds=request.timeout_ms / 1000,
        )
        started = self._monotonic()
        try:
            response = self._transport.send(http_request)
        except ProviderTransportBeforeSendError:
            return self._failure_without_response(
                outcome=ModelAttemptOutcome.RETRYABLE_PROVIDER_ERROR,
                error_code="PROVIDER_CONNECTION_FAILED",
                latency_ms=self._latency_ms(started),
            )
        except ProviderTransportAfterSendError as error:
            raise ProviderOutcomeUnknownError(
                "Provider outcome is unknown after dispatch"
            ) from error

        latency_ms = self._latency_ms(started)
        metadata = self._store_response(request, response.body)
        response_hash = sha256(response.body).hexdigest()
        if not 200 <= response.status_code <= 299:
            outcome, error_code = self._http_error(response.status_code)
            return self._observed_failure(
                outcome=outcome,
                error_code=error_code,
                status_code=response.status_code,
                metadata=metadata,
                response_hash=response_hash,
                latency_ms=latency_ms,
            )
        return self._parse_success(
            response=response,
            metadata=metadata,
            response_hash=response_hash,
            latency_ms=latency_ms,
        )

    def _validate_invocation(self, request: ProviderInvocation) -> None:
        if request.provider != self._config.provider:
            raise ProviderAdapterError("Provider does not match configured Provider")
        if request.model_id != self._config.model_id:
            raise ProviderAdapterError("Provider model does not match configured model")
        if request.model_snapshot != self._config.model_snapshot:
            raise ProviderAdapterError("Provider model snapshot does not match configured snapshot")
        if self._config.protocol != "openai_chat_completions":
            raise ProviderAdapterError("Provider protocol is unsupported")

    def _headers(self, request: ProviderInvocation) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._config.api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        if request.idempotency_key is not None:
            headers["Idempotency-Key"] = request.idempotency_key
        return headers

    def _store_response(
        self,
        request: ProviderInvocation,
        body: bytes,
    ) -> ObjectMetadata:
        self._object_store.ensure_bucket()
        digest = sha256(body).hexdigest()
        return self._object_store.put_bytes_if_absent(
            key=f"provider-responses/{request.model_call_id}/{request.attempt_id}.json",
            content=body,
            media_type="application/json",
            sha256=digest,
        )

    def _parse_success(
        self,
        *,
        response: ProviderHttpResponse,
        metadata: ObjectMetadata,
        response_hash: str,
        latency_ms: int,
    ) -> ProviderAttemptResult:
        observed = metadata
        try:
            envelope = json.loads(response.body)
        except UnicodeDecodeError, json.JSONDecodeError:
            return self._observed_failure(
                outcome=ModelAttemptOutcome.INVALID_JSON_RESPONSE,
                error_code="PROVIDER_RESPONSE_JSON_INVALID",
                status_code=response.status_code,
                metadata=observed,
                response_hash=response_hash,
                latency_ms=latency_ms,
            )
        if not isinstance(envelope, dict):
            return self._metadata_rejected(
                response, observed, response_hash, latency_ms, "PROVIDER_RESPONSE_SHAPE_INVALID"
            )
        provider_response_id = envelope.get("id")
        try:
            if not isinstance(provider_response_id, str):
                raise ValueError
            require_provider_response_id(provider_response_id)
        except ValueError:
            return self._metadata_rejected(
                response,
                observed,
                response_hash,
                latency_ms,
                "PROVIDER_RESPONSE_ID_INVALID",
            )
        usage = self._usage(envelope.get("usage"))
        if usage is None:
            return self._metadata_rejected(
                response,
                observed,
                response_hash,
                latency_ms,
                "PROVIDER_USAGE_METADATA_INVALID",
            )
        choices = envelope.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            return self._metadata_rejected(
                response,
                observed,
                response_hash,
                latency_ms,
                "PROVIDER_RESPONSE_SHAPE_INVALID",
                usage=usage,
            )
        choice = choices[0]
        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            return self._observed_failure(
                outcome=ModelAttemptOutcome.OUTPUT_LIMIT_EXCEEDED,
                error_code="PROVIDER_OUTPUT_LIMIT_EXCEEDED",
                status_code=response.status_code,
                metadata=observed,
                response_hash=response_hash,
                latency_ms=latency_ms,
                usage=usage,
            )
        message = choice.get("message")
        if (
            finish_reason != "stop"
            or not isinstance(message, dict)
            or message.get("role") != "assistant"
            or not isinstance(message.get("content"), str)
        ):
            return self._metadata_rejected(
                response,
                observed,
                response_hash,
                latency_ms,
                "PROVIDER_RESPONSE_SHAPE_INVALID",
                usage=usage,
            )
        try:
            parsed = json.loads(message["content"])
        except json.JSONDecodeError:
            return self._observed_failure(
                outcome=ModelAttemptOutcome.INVALID_JSON_RESPONSE,
                error_code="PROVIDER_ASSISTANT_JSON_INVALID",
                status_code=response.status_code,
                metadata=observed,
                response_hash=response_hash,
                latency_ms=latency_ms,
                usage=usage,
            )
        if not isinstance(parsed, dict):
            return self._observed_failure(
                outcome=ModelAttemptOutcome.INVALID_CANDIDATE_SHAPE,
                error_code="PROVIDER_ASSISTANT_SHAPE_INVALID",
                status_code=response.status_code,
                metadata=observed,
                response_hash=response_hash,
                latency_ms=latency_ms,
                usage=usage,
            )
        cost_status, monetary_cost = self._cost(usage)
        return ProviderAttemptResult(
            outcome=ModelAttemptOutcome.SUCCEEDED,
            provider_http_status=response.status_code,
            error_code=None,
            provider_response_id=None,
            raw_response_reference_kind="INTERNAL_OBJECT",
            raw_response_storage_bucket=observed.bucket,
            raw_response_object_key=observed.key,
            raw_response_sha256=observed.sha256,
            response_hash=response_hash,
            parsed_result_hash=sha256(canonical_json_bytes(parsed)).hexdigest(),
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cache_read_tokens=usage.prompt_cache_hit_tokens,
            cache_write_tokens=0,
            cost_status=cost_status,
            monetary_cost=monetary_cost,
            latency_ms=latency_ms,
        )

    def _metadata_rejected(
        self,
        response: ProviderHttpResponse,
        metadata: ObjectMetadata,
        response_hash: str,
        latency_ms: int,
        error_code: str,
        *,
        usage: _ProviderUsage | None = None,
    ) -> ProviderAttemptResult:
        return self._observed_failure(
            outcome=ModelAttemptOutcome.RESPONSE_METADATA_REJECTED,
            error_code=error_code,
            status_code=response.status_code,
            metadata=metadata,
            response_hash=response_hash,
            latency_ms=latency_ms,
            usage=usage,
        )

    @staticmethod
    def _usage(value: object) -> _ProviderUsage | None:
        if not isinstance(value, dict):
            return None
        required = ("prompt_tokens", "completion_tokens")
        if any(
            not isinstance(value.get(name), int)
            or isinstance(value.get(name), bool)
            or cast(int, value.get(name)) < 0
            for name in required
        ):
            return None
        cache_read = value.get("prompt_cache_hit_tokens", 0)
        if not isinstance(cache_read, int) or isinstance(cache_read, bool) or cache_read < 0:
            return None
        monetary_cost = None
        reported_cost = value.get("monetary_cost")
        if reported_cost is not None:
            try:
                cost = Decimal(str(reported_cost))
            except InvalidOperation, ValueError:
                return None
            if not cost.is_finite() or cost < 0:
                return None
            monetary_cost = cost
        return _ProviderUsage(
            prompt_tokens=cast(int, value["prompt_tokens"]),
            completion_tokens=cast(int, value["completion_tokens"]),
            prompt_cache_hit_tokens=cache_read,
            monetary_cost=monetary_cost,
        )

    @staticmethod
    def _cost(
        usage: _ProviderUsage,
    ) -> tuple[Literal["REPORTED", "COST_NOT_REPORTED"], Decimal | None]:
        if usage.monetary_cost is not None:
            return "REPORTED", usage.monetary_cost
        return "COST_NOT_REPORTED", None

    @staticmethod
    def _http_error(status_code: int) -> tuple[ModelAttemptOutcome, str]:
        if status_code in {401, 403}:
            return (
                ModelAttemptOutcome.TERMINAL_PROVIDER_ERROR,
                "PROVIDER_AUTHENTICATION_REJECTED",
            )
        if status_code == 429:
            return ModelAttemptOutcome.RETRYABLE_PROVIDER_ERROR, "PROVIDER_RATE_LIMITED"
        if status_code in {408, 425} or 500 <= status_code <= 599:
            return (
                ModelAttemptOutcome.RETRYABLE_PROVIDER_ERROR,
                "PROVIDER_TEMPORARILY_UNAVAILABLE",
            )
        return ModelAttemptOutcome.TERMINAL_PROVIDER_ERROR, "PROVIDER_REQUEST_REJECTED"

    def _observed_failure(
        self,
        *,
        outcome: ModelAttemptOutcome,
        error_code: str,
        status_code: int,
        metadata: ObjectMetadata,
        response_hash: str,
        latency_ms: int,
        usage: _ProviderUsage | None = None,
    ) -> ProviderAttemptResult:
        usage = usage or _ProviderUsage(0, 0, 0, None)
        cost_status, monetary_cost = self._cost(usage)
        return ProviderAttemptResult(
            outcome=outcome,
            provider_http_status=status_code,
            error_code=error_code,
            provider_response_id=None,
            raw_response_reference_kind="INTERNAL_OBJECT",
            raw_response_storage_bucket=metadata.bucket,
            raw_response_object_key=metadata.key,
            raw_response_sha256=metadata.sha256,
            response_hash=response_hash,
            parsed_result_hash=None,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cache_read_tokens=usage.prompt_cache_hit_tokens,
            cache_write_tokens=0,
            cost_status=cost_status,
            monetary_cost=monetary_cost,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _failure_without_response(
        *,
        outcome: ModelAttemptOutcome,
        error_code: str,
        latency_ms: int,
    ) -> ProviderAttemptResult:
        return ProviderAttemptResult(
            outcome=outcome,
            provider_http_status=None,
            error_code=error_code,
            provider_response_id=None,
            raw_response_reference_kind=None,
            raw_response_storage_bucket=None,
            raw_response_object_key=None,
            raw_response_sha256=None,
            response_hash=None,
            parsed_result_hash=None,
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cache_write_tokens=0,
            cost_status="COST_NOT_REPORTED",
            monetary_cost=None,
            latency_ms=latency_ms,
        )

    def _latency_ms(self, started: float) -> int:
        return max(0, round((self._monotonic() - started) * 1000))


def invocation_payload(request: ProviderInvocation) -> dict[str, object]:
    return {
        "model": request.model_id,
        "messages": [
            {"role": message.role, "content": message.content} for message in request.messages
        ],
        "max_tokens": request.max_output_tokens,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "seed": request.seed,
        "response_format": {"type": "json_object"},
    }


__all__ = [
    "HttpxProviderTransport",
    "invocation_payload",
    "OpenAICompatibleProviderAdapter",
    "ProviderAdapterError",
    "ProviderHttpRequest",
    "ProviderHttpResponse",
    "ProviderTransport",
    "ProviderTransportAfterSendError",
    "ProviderTransportBeforeSendError",
]
