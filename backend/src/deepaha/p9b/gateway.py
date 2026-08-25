import time
from collections.abc import Callable
from typing import cast
from uuid import UUID, uuid7

from sqlalchemy import RowMapping, select, text
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase9b import ModelAttemptOutcome, ModelCallIntentSchemaV08
from deepaha.p9b.models import ModelCall, ModelTaskSpec
from deepaha.p9b.provider import (
    ProviderAdapter,
    ProviderAttemptResult,
    ProviderInvocation,
    ProviderMessage,
)


class GatewayExecutionError(RuntimeError):
    pass


class GatewayExecutor:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        adapter: ProviderAdapter,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._session_factory = session_factory
        self._adapter = adapter
        self._sleeper = sleeper

    def execute(
        self,
        *,
        intent: ModelCallIntentSchemaV08,
        messages: tuple[ProviderMessage, ...],
    ) -> dict[str, object]:
        if self._adapter.provider != intent.provider:
            raise GatewayExecutionError("Gateway adapter does not match the authorized Provider")
        if not messages:
            raise GatewayExecutionError("Gateway invocation requires a minimized message payload")
        task = self._register_call(intent)
        backoff_ms = task.initial_backoff_ms

        for attempt_number in range(1, task.max_attempts + 1):
            attempt = self._begin_attempt(intent.model_call_id, attempt_number)
            if not cast(bool, attempt["provider_invocation_allowed"]):
                self._finalize_call(intent.model_call_id)
                return self._read_ledger(intent.model_call_id)

            invocation = ProviderInvocation(
                model_call_id=intent.model_call_id,
                attempt_id=cast(UUID, attempt["attempt_id"]),
                model_id=intent.model_id,
                model_snapshot=intent.model_snapshot,
                messages=messages,
                output_schema_version=intent.output_schema_version,
                max_output_tokens=task.max_output_tokens,
                temperature=intent.temperature,
                top_p=intent.top_p,
                seed=intent.seed,
                timeout_ms=task.timeout_ms,
                idempotency_key=None,
            )
            result = self._invoke_provider(invocation)
            self._finish_attempt(intent.model_call_id, attempt_number, result)

            if (
                result.outcome is ModelAttemptOutcome.RETRYABLE_PROVIDER_ERROR
                and attempt_number < task.max_attempts
            ):
                self._sleeper(backoff_ms / 1000)
                backoff_ms = min(
                    int(backoff_ms * task.backoff_multiplier),
                    task.max_backoff_ms,
                )
                continue

            self._finalize_call(intent.model_call_id)
            return self._read_ledger(intent.model_call_id)

        raise GatewayExecutionError("Gateway exhausted attempts without a finalization")

    def _register_call(self, intent: ModelCallIntentSchemaV08) -> ModelTaskSpec:
        with self._session_factory.begin() as session:
            task = session.scalar(
                select(ModelTaskSpec).where(
                    ModelTaskSpec.task_name == intent.task_spec_name,
                    ModelTaskSpec.task_version == intent.task_spec_version,
                )
            )
            if task is None:
                raise GatewayExecutionError("Model TaskSpec does not exist")
            session.add(ModelCall(**intent.model_dump(mode="python")))
            session.flush()
            session.expunge(task)
            return task

    def _begin_attempt(self, model_call_id: UUID, attempt_number: int) -> RowMapping:
        with self._session_factory.begin() as session:
            row = session.execute(
                text(
                    "insert into p9b_model_call_attempts "
                    "(model_call_id, attempt_number, attempt_id, authorization_decision, "
                    "authorization_reason_code, authorization_checked_at, "
                    "provider_invocation_allowed, created_at) values "
                    "(:model_call_id, :attempt_number, :attempt_id, 'AUTHORITY_REJECTED', "
                    "'PENDING_DATABASE_AUTHORIZATION', clock_timestamp(), false, "
                    "clock_timestamp()) returning *"
                ),
                {
                    "model_call_id": model_call_id,
                    "attempt_number": attempt_number,
                    "attempt_id": uuid7(),
                },
            ).mappings().one()
            return row

    def _invoke_provider(self, invocation: ProviderInvocation) -> ProviderAttemptResult:
        return self._adapter.invoke(invocation)

    def _finish_attempt(
        self,
        model_call_id: UUID,
        attempt_number: int,
        result: ProviderAttemptResult,
    ) -> None:
        with self._session_factory.begin() as session:
            session.execute(
                text(
                    "update p9b_model_call_attempts set outcome = :outcome, "
                    "provider_http_status = :provider_http_status, error_code = :error_code, "
                    "provider_response_id = :provider_response_id, "
                    "raw_response_reference_kind = :raw_response_reference_kind, "
                    "raw_response_storage_bucket = :raw_response_storage_bucket, "
                    "raw_response_object_key = :raw_response_object_key, "
                    "raw_response_sha256 = :raw_response_sha256, "
                    "response_hash = :response_hash, parsed_result_hash = :parsed_result_hash, "
                    "input_tokens = :input_tokens, output_tokens = :output_tokens, "
                    "cache_read_tokens = :cache_read_tokens, "
                    "cache_write_tokens = :cache_write_tokens, cost_status = :cost_status, "
                    "monetary_cost = :monetary_cost, latency_ms = :latency_ms, "
                    "completed_at = clock_timestamp() where model_call_id = :model_call_id "
                    "and attempt_number = :attempt_number returning attempt_id"
                ),
                {
                    "outcome": result.outcome.value,
                    "provider_http_status": result.provider_http_status,
                    "error_code": result.error_code,
                    "provider_response_id": result.provider_response_id,
                    "raw_response_reference_kind": result.raw_response_reference_kind,
                    "raw_response_storage_bucket": result.raw_response_storage_bucket,
                    "raw_response_object_key": result.raw_response_object_key,
                    "raw_response_sha256": result.raw_response_sha256,
                    "response_hash": result.response_hash,
                    "parsed_result_hash": result.parsed_result_hash,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "cache_read_tokens": result.cache_read_tokens,
                    "cache_write_tokens": result.cache_write_tokens,
                    "cost_status": result.cost_status,
                    "monetary_cost": result.monetary_cost,
                    "latency_ms": result.latency_ms,
                    "model_call_id": model_call_id,
                    "attempt_number": attempt_number,
                },
            ).one()

    def _finalize_call(self, model_call_id: UUID) -> None:
        with self._session_factory.begin() as session:
            session.execute(
                text(
                    "insert into p9b_model_call_finalizations (model_call_id) "
                    "values (:model_call_id)"
                ),
                {"model_call_id": model_call_id},
            )

    def _read_ledger(self, model_call_id: UUID) -> dict[str, object]:
        with self._session_factory() as session:
            row = session.execute(
                text(
                    "select * from p9b_model_call_ledger_view "
                    "where model_call_id = :model_call_id"
                ),
                {"model_call_id": model_call_id},
            ).mappings().one()
            return dict(row)


__all__ = ["GatewayExecutionError", "GatewayExecutor"]
