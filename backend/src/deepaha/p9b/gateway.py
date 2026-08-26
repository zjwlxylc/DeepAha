import time
from collections.abc import Callable
from typing import cast
from uuid import UUID, uuid7

from sqlalchemy import RowMapping, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase9b import (
    ModelAttemptOutcome,
    ModelCallIntentSchemaV08,
    ModelCallLedgerViewSchemaV08,
)
from deepaha.p9b.hashing import ModelInvocationIdentity, model_invocation_identity
from deepaha.p9b.models import (
    EgressDecision,
    ModelCall,
    ModelTaskSpec,
    ProviderEgressPolicySnapshot,
)
from deepaha.p9b.provider import (
    ProviderAdapter,
    ProviderAttemptResult,
    ProviderInvocation,
    ProviderMessage,
    ProviderOutcomeUnknownError,
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
        task, policy_supports_idempotency = self._load_execution_contract(intent)
        invocation = self._build_invocation(
            intent=intent,
            messages=messages,
            task=task,
            attempt_id=uuid7(),
            policy_supports_idempotency=policy_supports_idempotency,
        )
        identity = model_invocation_identity(invocation)
        trusted_intent = self._register_call(intent, identity)
        self.reconcile_stale_attempts(intent.model_call_id)
        progress = self._read_progress(intent.model_call_id)
        if cast(bool, progress["finalized"]):
            return self._read_ledger(intent.model_call_id)
        attempt_count = cast(int, progress["attempt_count"])
        latest_outcome = cast(str | None, progress["latest_outcome"])
        if attempt_count and latest_outcome is None:
            raise GatewayExecutionError("Model call is already in progress")
        if attempt_count and (
            latest_outcome != ModelAttemptOutcome.RETRYABLE_PROVIDER_ERROR.value
            or attempt_count >= task.max_attempts
        ):
            self._finalize_call(intent.model_call_id)
            return self._read_ledger(intent.model_call_id)

        backoff_ms = task.initial_backoff_ms

        for attempt_number in range(attempt_count + 1, task.max_attempts + 1):
            if attempt_number > attempt_count + 1:
                invocation = self._build_invocation(
                    intent=trusted_intent,
                    messages=messages,
                    task=task,
                    attempt_id=uuid7(),
                    policy_supports_idempotency=policy_supports_idempotency,
                )
                if model_invocation_identity(invocation) != identity:
                    raise GatewayExecutionError(
                        "Gateway retry request identity changed before authorization"
                    )
            attempt = self._begin_attempt(
                trusted_intent.model_call_id,
                attempt_number,
                invocation.attempt_id,
            )
            if not cast(bool, attempt["provider_invocation_allowed"]):
                self._finalize_call(trusted_intent.model_call_id)
                return self._read_ledger(trusted_intent.model_call_id)
            started = time.perf_counter()
            try:
                result = self._invoke_provider(invocation)
            except ProviderOutcomeUnknownError:
                result = ProviderAttemptResult(
                    outcome=ModelAttemptOutcome.PROVIDER_OUTCOME_UNKNOWN,
                    provider_http_status=None,
                    error_code="PROVIDER_OUTCOME_UNKNOWN",
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
                    latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
                )
            self._finish_attempt(trusted_intent.model_call_id, attempt_number, result)

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

            self._finalize_call(trusted_intent.model_call_id)
            return self._read_ledger(trusted_intent.model_call_id)

        raise GatewayExecutionError("Gateway exhausted attempts without a finalization")

    def _load_execution_contract(
        self,
        intent: ModelCallIntentSchemaV08,
    ) -> tuple[ModelTaskSpec, bool]:
        with self._session_factory() as session:
            task = session.scalar(
                select(ModelTaskSpec).where(
                    ModelTaskSpec.task_name == intent.task_spec_name,
                    ModelTaskSpec.task_version == intent.task_spec_version,
                )
            )
            if task is None:
                raise GatewayExecutionError("Model TaskSpec does not exist")
            decision = session.scalar(
                select(EgressDecision).where(
                    EgressDecision.egress_decision_id == intent.egress_decision_id
                )
            )
            if decision is None:
                raise GatewayExecutionError("Egress decision does not exist")
            supports_idempotency = session.scalar(
                select(ProviderEgressPolicySnapshot.supports_idempotency).where(
                    ProviderEgressPolicySnapshot.snapshot_id
                    == decision.provider_policy_snapshot_id,
                    ProviderEgressPolicySnapshot.snapshot_hash
                    == decision.provider_policy_snapshot_hash,
                )
            )
            if supports_idempotency is None:
                raise GatewayExecutionError("Provider egress policy snapshot does not exist")
            session.expunge(task)
            return task, bool(supports_idempotency)

    def _build_invocation(
        self,
        *,
        intent: ModelCallIntentSchemaV08,
        messages: tuple[ProviderMessage, ...],
        task: ModelTaskSpec,
        attempt_id: UUID,
        policy_supports_idempotency: bool,
    ) -> ProviderInvocation:
        return ProviderInvocation(
            model_call_id=intent.model_call_id,
            attempt_id=attempt_id,
            provider=intent.provider,
            model_id=intent.model_id,
            model_snapshot=intent.model_snapshot,
            messages=messages,
            output_schema_version=intent.output_schema_version,
            max_output_tokens=task.max_output_tokens,
            temperature=intent.temperature,
            top_p=intent.top_p,
            seed=intent.seed,
            timeout_ms=task.timeout_ms,
            idempotency_key=(
                str(attempt_id)
                if self._adapter.supports_idempotency and policy_supports_idempotency
                else None
            ),
        )

    def _trusted_intent(
        self,
        intent: ModelCallIntentSchemaV08,
        identity: ModelInvocationIdentity,
    ) -> ModelCallIntentSchemaV08:
        if tuple(intent.canonical_message_hashes) != identity.canonical_message_hashes:
            raise GatewayExecutionError(
                "Gateway canonical message hashes do not match request identity"
            )
        if intent.canonical_request_hash != identity.canonical_request_hash:
            raise GatewayExecutionError(
                "Gateway caller canonical request hash does not match request identity"
            )
        return intent.model_copy(
            update={
                "canonical_message_hashes": list(identity.canonical_message_hashes),
                "canonical_request_hash": identity.canonical_request_hash,
            }
        )

    def _register_call(
        self,
        intent: ModelCallIntentSchemaV08,
        identity: ModelInvocationIdentity,
    ) -> ModelCallIntentSchemaV08:
        with self._session_factory.begin() as session:
            existing = session.scalar(
                select(ModelCall)
                .where(ModelCall.model_call_id == intent.model_call_id)
                .with_for_update()
            )
            if existing is not None:
                self._require_existing_identity(existing, intent, identity)
                self._require_egress_payload(
                    session,
                    existing.egress_decision_id,
                    identity,
                )
                return self._trusted_intent(intent, identity)
            trusted_intent = self._trusted_intent(intent, identity)
            self._require_egress_payload(session, intent.egress_decision_id, identity)
            session.execute(
                insert(ModelCall)
                .values(**trusted_intent.model_dump(mode="python"))
                .on_conflict_do_nothing(index_elements=[ModelCall.model_call_id])
            )
            existing = session.scalar(
                select(ModelCall)
                .where(ModelCall.model_call_id == intent.model_call_id)
                .with_for_update()
            )
            if existing is None:
                raise GatewayExecutionError("Model call registration was not persisted")
            self._require_existing_identity(existing, intent, identity)
            return trusted_intent

    @staticmethod
    def _require_existing_identity(
        existing: ModelCall,
        intent: ModelCallIntentSchemaV08,
        identity: ModelInvocationIdentity,
    ) -> None:
        if (
            existing.egress_decision_id != intent.egress_decision_id
            or existing.canonical_request_hash != identity.canonical_request_hash
            or tuple(existing.canonical_message_hashes) != identity.canonical_message_hashes
            or intent.canonical_request_hash != identity.canonical_request_hash
            or tuple(intent.canonical_message_hashes) != identity.canonical_message_hashes
        ):
            raise GatewayExecutionError(
                "Model call idempotency conflict: Gateway request identity differs"
            )

    @staticmethod
    def _require_egress_payload(
        session: Session,
        egress_decision_id: UUID,
        identity: ModelInvocationIdentity,
    ) -> None:
        decision = session.scalar(
            select(EgressDecision)
            .where(EgressDecision.egress_decision_id == egress_decision_id)
            .with_for_update()
        )
        if decision is None:
            raise GatewayExecutionError("Egress decision does not exist")
        if decision.actual_payload_hash != identity.actual_payload_hash:
            raise GatewayExecutionError(
                "Egress decision actual payload hash does not match Gateway invocation"
            )

    def reconcile_stale_attempts(self, model_call_id: UUID | None = None) -> tuple[UUID, ...]:
        with self._session_factory.begin() as session:
            rows = session.execute(
                text(
                    "select model_call_id from "
                    "p9b_reconcile_stale_model_call_attempts(:model_call_id)"
                ),
                {"model_call_id": model_call_id},
            ).scalars()
            return tuple(rows)

    def _read_progress(self, model_call_id: UUID) -> RowMapping:
        with self._session_factory() as session:
            return (
                session.execute(
                    text(
                        "select exists(select 1 from p9b_model_call_finalizations "
                        "where model_call_id = :model_call_id) as finalized, "
                        "count(*)::integer as attempt_count, "
                        "(array_agg(outcome order by attempt_number desc))[1] as latest_outcome "
                        "from p9b_model_call_attempts where model_call_id = :model_call_id"
                    ),
                    {"model_call_id": model_call_id},
                )
                .mappings()
                .one()
            )

    def _begin_attempt(
        self,
        model_call_id: UUID,
        attempt_number: int,
        attempt_id: UUID,
    ) -> RowMapping:
        with self._session_factory.begin() as session:
            row = (
                session.execute(
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
                        "attempt_id": attempt_id,
                    },
                )
                .mappings()
                .one()
            )
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
                    "values (:model_call_id) on conflict do nothing"
                ),
                {"model_call_id": model_call_id},
            )

    def _read_ledger(self, model_call_id: UUID) -> dict[str, object]:
        with self._session_factory() as session:
            row = (
                session.execute(
                    text(
                        "select * from p9b_model_call_ledger_view "
                        "where model_call_id = :model_call_id"
                    ),
                    {"model_call_id": model_call_id},
                )
                .mappings()
                .one()
            )
            return ModelCallLedgerViewSchemaV08.model_validate(dict(row)).model_dump(mode="python")


__all__ = ["GatewayExecutionError", "GatewayExecutor"]
