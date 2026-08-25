from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from deepaha.contracts.phase9b import ModelAttemptOutcome


class ProviderOutcomeUnknownError(RuntimeError):
    """The request may have reached the Provider but no outcome was observed."""


@dataclass(frozen=True, slots=True)
class ProviderMessage:
    role: Literal["system", "user", "assistant"]
    content: str

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("Provider message content must not be empty")


@dataclass(frozen=True, slots=True)
class ProviderInvocation:
    model_call_id: UUID
    attempt_id: UUID
    model_id: str
    model_snapshot: str
    messages: tuple[ProviderMessage, ...]
    output_schema_version: str
    max_output_tokens: int
    temperature: float
    top_p: float
    seed: int
    timeout_ms: int
    idempotency_key: str | None


@dataclass(frozen=True, slots=True)
class ProviderAttemptResult:
    outcome: ModelAttemptOutcome
    provider_http_status: int | None
    error_code: str | None
    provider_response_id: str | None
    raw_response_reference_kind: str | None
    raw_response_storage_bucket: str | None
    raw_response_object_key: str | None
    raw_response_sha256: str | None
    response_hash: str | None
    parsed_result_hash: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_status: Literal["REPORTED", "COST_NOT_REPORTED"]
    monetary_cost: Decimal | None
    latency_ms: int


class ProviderAdapter(Protocol):
    provider: str
    supports_idempotency: bool

    def invoke(self, request: ProviderInvocation) -> ProviderAttemptResult: ...


class RecordedResponseAdapter:
    """Deterministic adapter used for replay and controlled engineering verification."""

    supports_idempotency = True

    def __init__(
        self,
        *,
        provider: str,
        responses: dict[str, ProviderAttemptResult],
    ) -> None:
        self.provider = provider
        self._responses = dict(responses)

    def invoke(self, request: ProviderInvocation) -> ProviderAttemptResult:
        response = self._responses.get(str(request.attempt_id))
        if response is None:
            raise LookupError("recorded Provider response does not exist for attempt")
        return response


__all__ = [
    "ProviderAdapter",
    "ProviderAttemptResult",
    "ProviderInvocation",
    "ProviderMessage",
    "ProviderOutcomeUnknownError",
    "RecordedResponseAdapter",
]
