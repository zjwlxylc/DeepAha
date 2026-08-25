import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from threading import Event, Thread

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase9b import ModelAttemptOutcome, ModelCallIntentSchemaV08
from deepaha.p9b.gateway import GatewayExecutionError, GatewayExecutor
from deepaha.p9b.provider import (
    ProviderAttemptResult,
    ProviderInvocation,
    ProviderMessage,
    ProviderOutcomeUnknownError,
)
from tests.integration.p9b_gateway_support import persist_model_call, seed_gateway_authority

pytestmark = pytest.mark.integration


@dataclass
class StubProviderAdapter:
    provider: str
    results: list[ProviderAttemptResult]
    on_invoke: Callable[[ProviderInvocation], None] | None = None
    supports_idempotency: bool = False
    call_count: int = 0
    requests: list[ProviderInvocation] | None = None
    error: Exception | None = None

    def invoke(self, request: ProviderInvocation) -> ProviderAttemptResult:
        self.call_count += 1
        if self.requests is not None:
            self.requests.append(request)
        if self.on_invoke is not None:
            self.on_invoke(request)
        if self.error is not None:
            raise self.error
        return self.results.pop(0)


@pytest.fixture
def owned_session_factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_engine, expire_on_commit=False)


def _result(outcome: ModelAttemptOutcome) -> ProviderAttemptResult:
    succeeded = outcome is ModelAttemptOutcome.SUCCEEDED
    return ProviderAttemptResult(
        outcome=outcome,
        provider_http_status=200 if succeeded else 503,
        error_code=None if succeeded else "PROVIDER_TEMPORARILY_UNAVAILABLE",
        provider_response_id="response_01JTEST" if succeeded else None,
        raw_response_reference_kind="PROVIDER_RESPONSE_ID" if succeeded else None,
        raw_response_storage_bucket=None,
        raw_response_object_key=None,
        raw_response_sha256=None,
        response_hash="8" * 64 if succeeded else None,
        parsed_result_hash="9" * 64 if succeeded else None,
        input_tokens=10,
        output_tokens=20 if succeeded else 0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_status="REPORTED",
        monetary_cost=Decimal("0.001000"),
        latency_ms=25,
    )


def _execute(
    factory: sessionmaker[Session],
    adapter: StubProviderAdapter,
    intent: ModelCallIntentSchemaV08,
    *,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    executor = GatewayExecutor(
        session_factory=factory,
        adapter=adapter,
        sleeper=sleeper,
    )
    return executor.execute(
        intent=intent,
        messages=(ProviderMessage(role="user", content="minimized official block"),),
    )


def test_expired_before_first_attempt_never_invokes_provider(
    owned_session_factory: sessionmaker[Session],
) -> None:
    with owned_session_factory.begin() as session:
        authority = seed_gateway_authority(session, expiry_seconds=0.05)
    time.sleep(0.08)
    adapter = StubProviderAdapter(
        provider=authority.intent.provider,
        results=[],
    )

    ledger = _execute(owned_session_factory, adapter, authority.intent)

    assert adapter.call_count == 0
    assert ledger["status"] == "TERMINAL_FAILED"
    assert ledger["terminal_disposition"] == "AUTHORITY_REJECTED"
    assert ledger["attempt_count"] == 1


def test_retry_expiry_retains_first_provider_outcome_and_blocks_second_call(
    owned_session_factory: sessionmaker[Session],
) -> None:
    with owned_session_factory.begin() as session:
        authority = seed_gateway_authority(session, expiry_seconds=0.12)
    adapter = StubProviderAdapter(
        provider=authority.intent.provider,
        results=[_result(ModelAttemptOutcome.RETRYABLE_PROVIDER_ERROR)],
    )

    ledger = _execute(
        owned_session_factory,
        adapter,
        authority.intent,
        sleeper=lambda _: time.sleep(0.15),
    )

    assert adapter.call_count == 1
    assert ledger["status"] == "TERMINAL_FAILED"
    assert ledger["terminal_disposition"] == "AUTHORITY_REJECTED"
    assert [item["outcome"] for item in ledger["attempts"]] == [
        "RETRYABLE_PROVIDER_ERROR",
        "AUTHORITY_REJECTED",
    ]


def test_valid_authority_retries_and_succeeds(
    owned_session_factory: sessionmaker[Session],
) -> None:
    with owned_session_factory.begin() as session:
        authority = seed_gateway_authority(session, expiry_seconds=5)
    adapter = StubProviderAdapter(
        provider=authority.intent.provider,
        results=[
            _result(ModelAttemptOutcome.RETRYABLE_PROVIDER_ERROR),
            _result(ModelAttemptOutcome.SUCCEEDED),
        ],
    )

    ledger = _execute(
        owned_session_factory,
        adapter,
        authority.intent,
        sleeper=lambda _: None,
    )

    assert adapter.call_count == 2
    assert ledger["status"] == "SUCCEEDED"
    assert ledger["terminal_disposition"] == "COMPLETED"
    assert ledger["attempt_count"] == 2
    assert ledger["retry_count"] == 1


def test_revision_invalidation_after_dispatch_keeps_attempt_audit_but_never_succeeds(
    owned_session_factory: sessionmaker[Session],
) -> None:
    with owned_session_factory.begin() as session:
        authority = seed_gateway_authority(session, expiry_seconds=5)

    def invalidate_after_dispatch(_: ProviderInvocation) -> None:
        with owned_session_factory.begin() as session:
            session.execute(
                text(
                    "update source_bundle_revisions set status = 'INVALIDATED' "
                    "where source_bundle_revision_id = :revision_id"
                ),
                {"revision_id": authority.source_bundle_revision_id},
            )

    adapter = StubProviderAdapter(
        provider=authority.intent.provider,
        results=[_result(ModelAttemptOutcome.SUCCEEDED)],
        on_invoke=invalidate_after_dispatch,
    )

    ledger = _execute(owned_session_factory, adapter, authority.intent)

    assert adapter.call_count == 1
    assert ledger["status"] == "TERMINAL_FAILED"
    assert ledger["terminal_disposition"] == "REVISION_INVALIDATED_AFTER_DISPATCH"
    assert ledger["attempts"][0]["outcome"] == "SUCCEEDED"
    with owned_session_factory() as session:
        historical, current = session.execute(
            text(
                "select p9b_egress_decision_authorized_at(egress_decision_id, created_at), "
                "p9b_egress_decision_authorized_at(egress_decision_id, clock_timestamp()) "
                "from p9b_egress_decisions where egress_decision_id = :decision_id"
            ),
            {"decision_id": authority.intent.egress_decision_id},
        ).one()
    assert historical is True
    assert current is False


def test_attempt_authorization_and_revision_invalidation_share_one_lock_order(
    migrated_engine: Engine,
    owned_session_factory: sessionmaker[Session],
) -> None:
    with owned_session_factory.begin() as session:
        authority = seed_gateway_authority(session, expiry_seconds=5)
        persist_model_call(session, authority.intent)

    begin_connection = migrated_engine.connect()
    begin_transaction = begin_connection.begin()
    invalidation_started = Event()
    invalidation_outcome: dict[str, object] = {}
    attempt_id = authority.intent.model_call_id
    try:
        begin_connection.execute(
            text(
                "insert into p9b_model_call_attempts "
                "(model_call_id, attempt_number, attempt_id, authorization_decision, "
                "authorization_reason_code, authorization_checked_at, "
                "provider_invocation_allowed, created_at) values "
                "(:call_id, 1, :attempt_id, 'AUTHORITY_REJECTED', 'PENDING', "
                "clock_timestamp(), false, clock_timestamp())"
            ),
            {
                "call_id": authority.intent.model_call_id,
                "attempt_id": attempt_id,
            },
        )

        def invalidate() -> None:
            invalidation_started.set()
            try:
                with owned_session_factory.begin() as session:
                    session.execute(
                        text(
                            "update source_bundle_revisions set status = 'INVALIDATED' "
                            "where source_bundle_revision_id = :revision_id"
                        ),
                        {"revision_id": authority.source_bundle_revision_id},
                    )
                invalidation_outcome["status"] = "COMMITTED"
            except Exception as error:  # noqa: BLE001 - test records the DB outcome
                invalidation_outcome["error"] = error

        thread = Thread(target=invalidate, daemon=True)
        thread.start()
        assert invalidation_started.wait(timeout=2)
        thread.join(timeout=0.15)
        assert thread.is_alive(), "invalidation did not wait for begin-attempt Revision lock"
        begin_transaction.commit()
        thread.join(timeout=3)
        assert not thread.is_alive()
        assert invalidation_outcome == {"status": "COMMITTED"}
    finally:
        if begin_transaction.is_active:
            begin_transaction.rollback()
        begin_connection.close()

    with owned_session_factory.begin() as session:
        session.execute(
            text(
                "update p9b_model_call_attempts set outcome = 'SUCCEEDED', "
                "provider_http_status = 200, provider_response_id = 'response_01JLOCK', "
                "raw_response_reference_kind = 'PROVIDER_RESPONSE_ID', "
                "response_hash = :response_hash, parsed_result_hash = :parsed_hash, "
                "input_tokens = 10, output_tokens = 20, cache_read_tokens = 0, "
                "cache_write_tokens = 0, cost_status = 'COST_NOT_REPORTED', "
                "monetary_cost = null, latency_ms = 25, completed_at = clock_timestamp() "
                "where model_call_id = :call_id and attempt_number = 1"
            ),
            {
                "response_hash": "8" * 64,
                "parsed_hash": "9" * 64,
                "call_id": authority.intent.model_call_id,
            },
        )
        session.execute(
            text("insert into p9b_model_call_finalizations (model_call_id) values (:call_id)"),
            {"call_id": authority.intent.model_call_id},
        )
        ledger = session.execute(
            text(
                "select status, terminal_disposition, attempts->0->>'outcome' "
                "from p9b_model_call_ledger_view where model_call_id = :call_id"
            ),
            {"call_id": authority.intent.model_call_id},
        ).one()
        assert ledger == (
            "TERMINAL_FAILED",
            "REVISION_INVALIDATED_AFTER_DISPATCH",
            "SUCCEEDED",
        )


def test_no_second_provider_entry_point_exists_in_gateway_execution(
    owned_session_factory: sessionmaker[Session],
) -> None:
    with owned_session_factory.begin() as session:
        authority = seed_gateway_authority(session, expiry_seconds=5)
    adapter = StubProviderAdapter(
        provider=authority.intent.provider,
        results=[_result(ModelAttemptOutcome.SUCCEEDED)],
    )

    first = _execute(owned_session_factory, adapter, authority.intent)

    assert first["status"] == "SUCCEEDED"
    assert adapter.call_count == 1


def test_same_call_id_and_request_hash_are_idempotent(
    owned_session_factory: sessionmaker[Session],
) -> None:
    with owned_session_factory.begin() as session:
        authority = seed_gateway_authority(session, expiry_seconds=5)
    adapter = StubProviderAdapter(
        provider=authority.intent.provider,
        results=[_result(ModelAttemptOutcome.SUCCEEDED)],
    )

    first = _execute(owned_session_factory, adapter, authority.intent)
    second = _execute(owned_session_factory, adapter, authority.intent)

    assert first == second
    assert adapter.call_count == 1


def test_same_call_id_with_different_request_hash_is_an_idempotency_conflict(
    owned_session_factory: sessionmaker[Session],
) -> None:
    with owned_session_factory.begin() as session:
        authority = seed_gateway_authority(session, expiry_seconds=5)
    adapter = StubProviderAdapter(
        provider=authority.intent.provider,
        results=[_result(ModelAttemptOutcome.SUCCEEDED)],
    )
    _execute(owned_session_factory, adapter, authority.intent)
    conflicting = authority.intent.model_copy(
        update={"canonical_request_hash": "a" * 64}
    )

    with pytest.raises(GatewayExecutionError, match="idempotency conflict"):
        _execute(owned_session_factory, adapter, conflicting)

    assert adapter.call_count == 1


def test_provider_idempotency_key_is_the_database_attempt_id_only_when_supported(
    owned_session_factory: sessionmaker[Session],
) -> None:
    with owned_session_factory.begin() as session:
        authority = seed_gateway_authority(
            session,
            expiry_seconds=5,
            supports_idempotency=True,
        )
    requests: list[ProviderInvocation] = []
    adapter = StubProviderAdapter(
        provider=authority.intent.provider,
        results=[_result(ModelAttemptOutcome.SUCCEEDED)],
        supports_idempotency=True,
        requests=requests,
    )

    ledger = _execute(owned_session_factory, adapter, authority.intent)

    assert ledger["status"] == "SUCCEEDED"
    assert len(requests) == 1
    assert requests[0].idempotency_key == str(requests[0].attempt_id)

    with owned_session_factory.begin() as session:
        unsupported = seed_gateway_authority(
            session,
            expiry_seconds=5,
            supports_idempotency=False,
        )
    unsupported_requests: list[ProviderInvocation] = []
    adapter = StubProviderAdapter(
        provider=unsupported.intent.provider,
        results=[_result(ModelAttemptOutcome.SUCCEEDED)],
        supports_idempotency=True,
        requests=unsupported_requests,
    )

    _execute(owned_session_factory, adapter, unsupported.intent)

    assert unsupported_requests[0].idempotency_key is None


def test_ambiguous_transport_without_idempotency_is_unknown_and_never_retried(
    owned_session_factory: sessionmaker[Session],
) -> None:
    with owned_session_factory.begin() as session:
        authority = seed_gateway_authority(session, expiry_seconds=5, max_attempts=2)
    adapter = StubProviderAdapter(
        provider=authority.intent.provider,
        results=[],
        error=ProviderOutcomeUnknownError("connection lost after dispatch"),
    )

    ledger = _execute(owned_session_factory, adapter, authority.intent)

    assert adapter.call_count == 1
    assert ledger["status"] == "TERMINAL_FAILED"
    assert ledger["terminal_disposition"] == "PROVIDER_OUTCOME_UNKNOWN"
    assert ledger["attempt_count"] == 1
    assert ledger["attempts"][0]["outcome"] == "PROVIDER_OUTCOME_UNKNOWN"


def test_stale_dispatched_attempt_is_atomically_reconciled_to_unknown(
    owned_session_factory: sessionmaker[Session],
) -> None:
    with owned_session_factory.begin() as session:
        authority = seed_gateway_authority(
            session,
            expiry_seconds=5,
            max_attempts=2,
            timeout_ms=100,
        )
    crashed = StubProviderAdapter(
        provider=authority.intent.provider,
        results=[],
        error=RuntimeError("worker process terminated"),
    )
    with pytest.raises(RuntimeError, match="worker process terminated"):
        _execute(owned_session_factory, crashed, authority.intent)
    time.sleep(0.15)
    replacement = StubProviderAdapter(
        provider=authority.intent.provider,
        results=[],
    )

    ledger = _execute(owned_session_factory, replacement, authority.intent)

    assert crashed.call_count == 1
    assert replacement.call_count == 0
    assert ledger["status"] == "TERMINAL_FAILED"
    assert ledger["terminal_disposition"] == "PROVIDER_OUTCOME_UNKNOWN"
    assert ledger["attempts"][0]["error_code"] == "DISPATCH_DEADLINE_EXCEEDED"
    reconciler = GatewayExecutor(
        session_factory=owned_session_factory,
        adapter=replacement,
    )
    assert reconciler.reconcile_stale_attempts(authority.intent.model_call_id) == ()
    with owned_session_factory() as session:
        finalization_count = session.scalar(
            text(
                "select count(*) from p9b_model_call_finalizations "
                "where model_call_id = :call_id"
            ),
            {"call_id": authority.intent.model_call_id},
        )
    assert finalization_count == 1


def test_concurrent_reentry_never_duplicates_an_inflight_provider_attempt(
    owned_session_factory: sessionmaker[Session],
) -> None:
    with owned_session_factory.begin() as session:
        authority = seed_gateway_authority(session, expiry_seconds=5)
    entered = Event()
    release = Event()
    outcome: dict[str, object] = {}

    def block_provider(_: ProviderInvocation) -> None:
        entered.set()
        assert release.wait(timeout=3)

    adapter = StubProviderAdapter(
        provider=authority.intent.provider,
        results=[_result(ModelAttemptOutcome.SUCCEEDED)],
        on_invoke=block_provider,
    )

    def first_execution() -> None:
        try:
            outcome["ledger"] = _execute(
                owned_session_factory,
                adapter,
                authority.intent,
            )
        except Exception as error:  # noqa: BLE001 - test records thread outcome
            outcome["error"] = error

    thread = Thread(target=first_execution, daemon=True)
    thread.start()
    assert entered.wait(timeout=3)
    try:
        with pytest.raises(GatewayExecutionError, match="already in progress"):
            _execute(owned_session_factory, adapter, authority.intent)
        assert adapter.call_count == 1
    finally:
        release.set()
        thread.join(timeout=3)

    assert not thread.is_alive()
    assert "error" not in outcome
    assert outcome["ledger"]["status"] == "SUCCEEDED"
