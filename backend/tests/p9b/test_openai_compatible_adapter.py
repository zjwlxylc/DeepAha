import json
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import httpx2
import pytest
from pydantic import SecretStr

from deepaha.artifacts.local_file import LocalFileObjectStore
from deepaha.contracts.phase9b import ModelAttemptOutcome
from deepaha.local_human_test.provider_config import ResolvedProviderConfig
from deepaha.p9b.openai_compatible import (
    HttpxProviderTransport,
    OpenAICompatibleProviderAdapter,
    ProviderAdapterError,
    ProviderHttpRequest,
    ProviderHttpResponse,
    ProviderTransportAfterSendError,
    ProviderTransportBeforeSendError,
)
from deepaha.p9b.provider import ProviderInvocation, ProviderMessage, ProviderOutcomeUnknownError

MODEL_CALL_ID = UUID("019b0000-0000-7000-8000-000000000901")
ATTEMPT_ID = UUID("019b0000-0000-7000-8000-000000000902")
SECRET = "synthetic-provider-secret-not-real"
PARSED_CONTENT: dict[str, list[object]] = {
    "facts": [],
    "rules": [],
    "uncertainties": [],
}


def response_body(
    *,
    content: str | None = None,
    finish_reason: str = "stop",
    usage: dict[str, object] | None = None,
) -> bytes:
    payload = {
        "id": "chatcmpl_synthetic_001",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content if content is not None else json.dumps(PARSED_CONTENT),
                },
                "finish_reason": finish_reason,
            }
        ],
        "usage": usage
        if usage is not None
        else {
            "prompt_tokens": 17,
            "completion_tokens": 11,
            "prompt_cache_hit_tokens": 3,
        },
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def invocation(**overrides: object) -> ProviderInvocation:
    values: dict[str, object] = {
        "model_call_id": MODEL_CALL_ID,
        "attempt_id": ATTEMPT_ID,
        "provider": "deepseek",
        "model_id": "deepseek-v4-flash",
        "model_snapshot": "deepseek-v4-flash@configured",
        "messages": (
            ProviderMessage(role="system", content="Return JSON only."),
            ProviderMessage(role="user", content="Extract the official facts."),
        ),
        "output_schema_version": "local-human-test-extraction-v1",
        "max_output_tokens": 3000,
        "temperature": 0.0,
        "top_p": 1.0,
        "seed": 42,
        "timeout_ms": 90_000,
        "idempotency_key": "attempt-synthetic-001",
    }
    values.update(overrides)
    return ProviderInvocation(**values)  # type: ignore[arg-type]


def provider_config(**overrides: object) -> ResolvedProviderConfig:
    values: dict[str, object] = {
        "provider": "deepseek",
        "base_url": "https://platform.example.invalid",
        "protocol": "openai_chat_completions",
        "model_id": "deepseek-v4-flash",
        "model_snapshot": "deepseek-v4-flash@configured",
        "api_key": SecretStr(SECRET),
    }
    values.update(overrides)
    return ResolvedProviderConfig.model_validate(values)


@dataclass
class RecordingTransport:
    response: ProviderHttpResponse | None = None
    error: Exception | None = None
    requests: list[ProviderHttpRequest] | None = None

    def send(self, request: ProviderHttpRequest) -> ProviderHttpResponse:
        if self.requests is None:
            self.requests = []
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def make_adapter(
    tmp_path: Path,
    transport: RecordingTransport,
) -> OpenAICompatibleProviderAdapter:
    return OpenAICompatibleProviderAdapter(
        config=provider_config(),
        object_store=LocalFileObjectStore(root=tmp_path, bucket="deepaha-model-audit"),
        transport=transport,
        monotonic=lambda: 1.025 if transport.requests else 1.0,
    )


def observed_response(status_code: int, body: bytes) -> ProviderHttpResponse:
    return ProviderHttpResponse(status_code=status_code, headers={}, body=body)


def test_adapter_sends_exact_invocation_and_stores_raw_response(tmp_path: Path) -> None:
    body = response_body()
    transport = RecordingTransport(response=observed_response(200, body))
    adapter = make_adapter(tmp_path, transport)

    result = adapter.invoke(invocation())

    assert len(transport.requests or []) == 1
    request = (transport.requests or [])[0]
    assert request.url == "https://platform.example.invalid/chat/completions"
    assert request.timeout_seconds == 90
    assert request.headers == {
        "Accept": "application/json",
        "Authorization": f"Bearer {SECRET}",
        "Content-Type": "application/json",
        "Idempotency-Key": "attempt-synthetic-001",
    }
    assert request.json_body == {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": "Extract the official facts."},
        ],
        "max_tokens": 3000,
        "temperature": 0.0,
        "top_p": 1.0,
        "seed": 42,
        "response_format": {"type": "json_object"},
    }
    assert result.outcome is ModelAttemptOutcome.SUCCEEDED
    assert result.provider_response_id is None
    assert result.raw_response_reference_kind == "INTERNAL_OBJECT"
    assert result.raw_response_object_key == (
        f"provider-responses/{MODEL_CALL_ID}/{ATTEMPT_ID}.json"
    )
    assert result.raw_response_sha256 == sha256(body).hexdigest()
    assert result.response_hash == sha256(body).hexdigest()
    assert result.parsed_result_hash == sha256(
        json.dumps(PARSED_CONTENT, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert result.input_tokens == 17
    assert result.output_tokens == 11
    assert result.cache_read_tokens == 3
    assert result.cache_write_tokens == 0
    assert result.cost_status == "COST_NOT_REPORTED"
    assert result.monetary_cost is None
    assert result.latency_ms == 25
    assert (
        LocalFileObjectStore(root=tmp_path, bucket="deepaha-model-audit").get_bytes(
            key=result.raw_response_object_key
        )
        == body
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"provider": "another-provider"}, "Provider"),
        ({"model_id": "another-model"}, "model"),
        ({"model_snapshot": "another-snapshot"}, "snapshot"),
    ],
)
def test_configuration_mismatch_is_rejected_before_transport(
    tmp_path: Path,
    overrides: dict[str, object],
    message: str,
) -> None:
    transport = RecordingTransport(response=observed_response(200, response_body()))
    adapter = make_adapter(tmp_path, transport)

    with pytest.raises(ProviderAdapterError, match=message):
        adapter.invoke(invocation(**overrides))

    assert transport.requests in (None, [])


@pytest.mark.parametrize(
    ("status_code", "outcome", "error_code"),
    [
        (400, ModelAttemptOutcome.TERMINAL_PROVIDER_ERROR, "PROVIDER_REQUEST_REJECTED"),
        (401, ModelAttemptOutcome.TERMINAL_PROVIDER_ERROR, "PROVIDER_AUTHENTICATION_REJECTED"),
        (403, ModelAttemptOutcome.TERMINAL_PROVIDER_ERROR, "PROVIDER_AUTHENTICATION_REJECTED"),
        (408, ModelAttemptOutcome.RETRYABLE_PROVIDER_ERROR, "PROVIDER_TEMPORARILY_UNAVAILABLE"),
        (429, ModelAttemptOutcome.RETRYABLE_PROVIDER_ERROR, "PROVIDER_RATE_LIMITED"),
        (500, ModelAttemptOutcome.RETRYABLE_PROVIDER_ERROR, "PROVIDER_TEMPORARILY_UNAVAILABLE"),
    ],
)
def test_observed_http_errors_are_sanitized_and_audited(
    tmp_path: Path,
    status_code: int,
    outcome: ModelAttemptOutcome,
    error_code: str,
) -> None:
    body = b'{"error":{"message":"synthetic upstream detail"}}'
    adapter = make_adapter(
        tmp_path,
        RecordingTransport(response=observed_response(status_code, body)),
    )

    result = adapter.invoke(invocation())

    assert result.outcome is outcome
    assert result.error_code == error_code
    assert result.provider_http_status == status_code
    assert result.raw_response_sha256 == sha256(body).hexdigest()
    assert "synthetic upstream detail" not in repr(result)
    assert SECRET not in repr(result)


def test_failure_before_send_is_retryable_without_raw_reference(tmp_path: Path) -> None:
    adapter = make_adapter(
        tmp_path,
        RecordingTransport(error=ProviderTransportBeforeSendError("synthetic")),
    )

    result = adapter.invoke(invocation())

    assert result.outcome is ModelAttemptOutcome.RETRYABLE_PROVIDER_ERROR
    assert result.error_code == "PROVIDER_CONNECTION_FAILED"
    assert result.provider_http_status is None
    assert result.raw_response_reference_kind is None


def test_failure_after_send_is_unknown_and_does_not_echo_secret(tmp_path: Path) -> None:
    adapter = make_adapter(
        tmp_path,
        RecordingTransport(error=ProviderTransportAfterSendError(SECRET)),
    )

    with pytest.raises(ProviderOutcomeUnknownError) as captured:
        adapter.invoke(invocation())

    assert SECRET not in str(captured.value)


def test_invalid_assistant_json_is_audited_but_not_succeeded(tmp_path: Path) -> None:
    body = response_body(content="not-json")
    adapter = make_adapter(
        tmp_path,
        RecordingTransport(response=observed_response(200, body)),
    )

    result = adapter.invoke(invocation())

    assert result.outcome is ModelAttemptOutcome.INVALID_JSON_RESPONSE
    assert result.error_code == "PROVIDER_ASSISTANT_JSON_INVALID"
    assert result.parsed_result_hash is None
    assert result.raw_response_sha256 == sha256(body).hexdigest()


def test_output_limit_and_missing_usage_fail_closed(tmp_path: Path) -> None:
    limited = make_adapter(
        tmp_path / "limited",
        RecordingTransport(
            response=observed_response(200, response_body(finish_reason="length"))
        ),
    ).invoke(invocation())
    missing_usage = make_adapter(
        tmp_path / "usage",
        RecordingTransport(
            response=observed_response(200, response_body(usage={}))
        ),
    ).invoke(invocation(attempt_id=UUID("019b0000-0000-7000-8000-000000000903")))

    assert limited.outcome is ModelAttemptOutcome.OUTPUT_LIMIT_EXCEEDED
    assert limited.error_code == "PROVIDER_OUTPUT_LIMIT_EXCEEDED"
    assert missing_usage.outcome is ModelAttemptOutcome.RESPONSE_METADATA_REJECTED
    assert missing_usage.error_code == "PROVIDER_USAGE_METADATA_INVALID"


def test_httpx_transport_posts_exact_json_without_external_network() -> None:
    observed: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        observed.append(request)
        return httpx2.Response(200, content=b'{"ok":true}', request=request)

    transport = HttpxProviderTransport(transport=httpx2.MockTransport(handler))
    request = ProviderHttpRequest(
        url="https://provider.example.invalid/chat/completions",
        headers={"Authorization": f"Bearer {SECRET}"},
        json_body={"model": "synthetic-model", "messages": []},
        timeout_seconds=90,
    )

    response = transport.send(request)

    assert response.status_code == 200
    assert response.body == b'{"ok":true}'
    assert len(observed) == 1
    assert observed[0].method == "POST"
    assert json.loads(observed[0].content) == request.json_body


@pytest.mark.parametrize(
    ("error_factory", "expected_error"),
    [
        (
            lambda request: httpx2.ConnectError("synthetic connect", request=request),
            ProviderTransportBeforeSendError,
        ),
        (
            lambda request: httpx2.ReadError("synthetic read", request=request),
            ProviderTransportAfterSendError,
        ),
    ],
)
def test_httpx_transport_distinguishes_before_and_after_send_failures(
    error_factory: Callable[[httpx2.Request], Exception],
    expected_error: type[Exception],
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise error_factory(request)

    transport = HttpxProviderTransport(transport=httpx2.MockTransport(handler))
    request = ProviderHttpRequest(
        url="https://provider.example.invalid/chat/completions",
        headers={},
        json_body={},
        timeout_seconds=90,
    )

    with pytest.raises(expected_error):
        transport.send(request)


def test_httpx_transport_rejects_oversized_observed_response() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"Content-Length": "10000001"},
            content=b"{}",
            request=request,
        )

    transport = HttpxProviderTransport(transport=httpx2.MockTransport(handler))

    with pytest.raises(ProviderTransportAfterSendError):
        transport.send(
            ProviderHttpRequest(
                url="https://provider.example.invalid/chat/completions",
                headers={},
                json_body={},
                timeout_seconds=90,
            )
        )
