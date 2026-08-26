from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from deepaha.contracts.phase9b import ModelAttemptOutcome
from deepaha.p9b.ledger_values import (
    require_error_code,
    require_object_key,
    require_provider_response_id,
    require_sha256,
    require_storage_bucket,
)


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
    provider: str
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

    def __post_init__(self) -> None:
        if self.error_code is not None:
            require_error_code(self.error_code)
        if self.provider_response_id is not None:
            require_provider_response_id(self.provider_response_id)
        if self.raw_response_storage_bucket is not None:
            require_storage_bucket(self.raw_response_storage_bucket)
        if self.raw_response_object_key is not None:
            require_object_key(self.raw_response_object_key)
        for digest in (
            self.raw_response_sha256,
            self.response_hash,
            self.parsed_result_hash,
        ):
            if digest is not None:
                require_sha256(digest)
        if self.raw_response_reference_kind not in {
            None,
            "INTERNAL_OBJECT",
            "PROVIDER_RESPONSE_ID",
        }:
            raise ValueError("raw_response_reference_kind is invalid")


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
