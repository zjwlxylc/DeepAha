from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from uuid import UUID, uuid7

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from deepaha.p9b.models import (
    EgressDecision,
    ModelCall,
    ModelTaskSpec,
    ProviderEgressPolicySnapshot,
    SourceEgressPolicySnapshot,
)
from tests.integration.test_p9b_b0_persistence import NOW, frozen_bundle, seed_graph

pytestmark = pytest.mark.integration


@dataclass(frozen=True, slots=True)
class CallSeed:
    model_call_id: UUID
    source_bundle_revision_id: UUID


def _seed_call(session: Session, *, expired: bool = False) -> CallSeed:
    graph = seed_graph(session, suffix=f"gateway-state-{uuid7()}")
    revision = frozen_bundle(session, graph)
    database_now = session.scalar(select(text("clock_timestamp()")))
    assert database_now is not None
    task_name = f"extract-{uuid7()}"
    task_version = "v1"
    provider = f"fake-provider-{uuid7()}"
    source_snapshot_id = f"source-policy-{uuid7()}"
    provider_snapshot_id = f"provider-policy-{uuid7()}"
    source_snapshot_hash = sha256(source_snapshot_id.encode()).hexdigest()
    provider_snapshot_hash = sha256(provider_snapshot_id.encode()).hexdigest()
    block_id = uuid7()
    block_hash = "3" * 64
    egress_decision_id = uuid7()
    model_call_id = uuid7()
    valid_until = database_now + timedelta(hours=1)
    decision_expiry = (
        database_now - timedelta(seconds=1)
        if expired
        else database_now + timedelta(minutes=5)
    )

    session.add_all(
        [
            ModelTaskSpec(
                model_task_spec_id=uuid7(),
                task_name=task_name,
                task_version=task_version,
                route_class="R2_BALANCED_REASON",
                allowed_input_block_types=["HTML_ELEMENT"],
                output_schema_version="schema-v1",
                max_input_tokens=2048,
                max_output_tokens=256,
                evidence_required=True,
                abstention_allowed=True,
                risk_class="HIGH_IMPACT_CANDIDATE",
                provider_capabilities=["ZERO_RETENTION"],
                egress_policy_id="p9b-egress-v1",
                timeout_ms=5000,
                max_attempts=2,
                initial_backoff_ms=10,
                backoff_multiplier=2.0,
                max_backoff_ms=100,
                max_concurrency=1,
                max_batch_size=1,
                fallback_policy="DISABLED",
                max_fallbacks=0,
                created_at=database_now,
            ),
            SourceEgressPolicySnapshot(
                snapshot_id=source_snapshot_id,
                snapshot_hash=source_snapshot_hash,
                source_bundle_revision_id=revision.source_bundle_revision_id,
                allows_egress=True,
                valid_from=database_now - timedelta(hours=1),
                valid_until=valid_until,
                recorded_by="human:security-reviewer",
                created_at=database_now,
            ),
            ProviderEgressPolicySnapshot(
                snapshot_id=provider_snapshot_id,
                snapshot_hash=provider_snapshot_hash,
                provider=provider,
                region="local-test",
                active=True,
                zero_retention=True,
                training_use=False,
                supports_idempotency=False,
                allowed_classifications=["PUBLIC_OFFICIAL_GENERAL"],
                retention_class="ZERO_RETENTION",
                valid_from=database_now - timedelta(hours=1),
                valid_until=valid_until,
                recorded_by="human:security-reviewer",
                created_at=database_now,
            ),
        ]
    )
    session.flush()
    session.add(
        EgressDecision(
            egress_decision_id=egress_decision_id,
            task_spec_name=task_name,
            task_spec_version=task_version,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            target_scope="OPPORTUNITY",
            opportunity_id=graph.opportunity_id,
            opportunity_version=graph.opportunity_version,
            opportunity_unit_id=None,
            opportunity_unit_version_id=None,
            input_block_ids=[block_id],
            input_block_hashes=[block_hash],
            data_classification_version="classification-v1",
            minimizer_version="minimizer-v1",
            redactor_version="redactor-v1",
            source_policy_snapshot_id=source_snapshot_id,
            source_policy_snapshot_hash=source_snapshot_hash,
            provider_policy_snapshot_id=provider_snapshot_id,
            provider_policy_snapshot_hash=provider_snapshot_hash,
            provider=provider,
            provider_region="local-test",
            original_input_hash="6" * 64,
            actual_payload_hash="7" * 64,
            decision="ALLOW",
            actor_type="SYSTEM",
            actor_identity=None,
            reason_codes=["POLICY_ALLOW"],
            created_at=database_now,
            expires_at=decision_expiry,
        )
    )
    session.flush()
    session.add(
        ModelCall(
            model_call_id=model_call_id,
            task_spec_name=task_name,
            task_spec_version=task_version,
            provider=provider,
            model_id="fake-model",
            model_snapshot="fake-model-2026-08-25",
            adapter_name="fake-adapter",
            adapter_version="v1",
            runtime_version="python-3.14",
            canonical_request_hash="1" * 64,
            canonical_message_hashes=["2" * 64],
            input_block_ids=[block_id],
            input_block_hashes=[block_hash],
            source_bundle_revision_id=revision.source_bundle_revision_id,
            target_scope="OPPORTUNITY",
            opportunity_id=graph.opportunity_id,
            opportunity_version=graph.opportunity_version,
            opportunity_unit_id=None,
            opportunity_unit_version_id=None,
            unit_segmentation_version=None,
            prompt_version="prompt-v1",
            output_schema_version="schema-v1",
            parser_version="parser-v1",
            contract_version="contract-v1",
            temperature=0.0,
            top_p=1.0,
            seed=42,
            egress_decision_id=egress_decision_id,
            validation_pipeline_version="validation-v1",
            retention_class="ZERO_RETENTION",
            registered_at=database_now,
        )
    )
    session.flush()
    return CallSeed(model_call_id, revision.source_bundle_revision_id)


def _begin_attempt(session: Session, call_id: UUID, *, forced_authorized: bool = True) -> UUID:
    attempt_id = uuid7()
    session.execute(
        text(
            "insert into p9b_model_call_attempts "
            "(model_call_id, attempt_number, attempt_id, authorization_decision, "
            "authorization_reason_code, authorization_checked_at, "
            "provider_invocation_allowed, created_at) values "
            "(:call_id, 1, :attempt_id, :authorization, 'FORGED_BY_CALLER', "
            "'2000-01-01T00:00:00Z', :allowed, '2000-01-01T00:00:00Z')"
        ),
        {
            "call_id": call_id,
            "attempt_id": attempt_id,
            "authorization": "AUTHORIZED" if forced_authorized else "AUTHORITY_REJECTED",
            "allowed": forced_authorized,
        },
    )
    return attempt_id


def test_replacement_state_tables_and_read_only_ledger_view_exist(session: Session) -> None:
    objects = session.execute(
        text(
            "select to_regclass('p9b_model_calls'), "
            "to_regclass('p9b_model_call_attempts'), "
            "to_regclass('p9b_model_call_finalizations'), "
            "to_regclass('p9b_model_call_ledger_view'), "
            "to_regclass('p9b_model_call_ledgers')"
        )
    ).one()
    assert objects[:4] == (
        "p9b_model_calls",
        "p9b_model_call_attempts",
        "p9b_model_call_finalizations",
        "p9b_model_call_ledger_view",
    )
    assert objects[4] is None
    with pytest.raises(DBAPIError, match="cannot insert into view"):
        session.execute(
            text("insert into p9b_model_call_ledger_view (model_call_id) values (:call_id)"),
            {"call_id": uuid7()},
        )


def test_database_derives_attempt_authority_and_cannot_be_forged_by_direct_sql(
    session: Session,
) -> None:
    valid = _seed_call(session)
    valid_attempt_id = _begin_attempt(session, valid.model_call_id, forced_authorized=False)
    valid_attempt = session.execute(
        text(
            "select authorization_decision, authorization_reason_code, "
            "authorization_checked_at, provider_invocation_allowed, outcome "
            "from p9b_model_call_attempts where attempt_id = :attempt_id"
        ),
        {"attempt_id": valid_attempt_id},
    ).one()
    assert valid_attempt.authorization_decision == "AUTHORIZED"
    assert valid_attempt.authorization_reason_code == "AUTHORIZED"
    assert valid_attempt.authorization_checked_at.year == 2026
    assert valid_attempt.provider_invocation_allowed is True
    assert valid_attempt.outcome is None

    expired = _seed_call(session, expired=True)
    expired_attempt_id = _begin_attempt(session, expired.model_call_id, forced_authorized=True)
    expired_attempt = session.execute(
        text(
            "select authorization_decision, provider_invocation_allowed, outcome "
            "from p9b_model_call_attempts where attempt_id = :attempt_id"
        ),
        {"attempt_id": expired_attempt_id},
    ).one()
    assert expired_attempt == ("AUTHORITY_REJECTED", False, "AUTHORITY_REJECTED")

    session.execute(
        text(
            "insert into p9b_model_call_finalizations "
            "(model_call_id, status, disposition, reason_code, finalized_at) values "
            "(:call_id, 'SUCCEEDED', 'COMPLETED', 'FORGED', '2000-01-01T00:00:00Z')"
        ),
        {"call_id": expired.model_call_id},
    )
    finalization = session.execute(
        text(
            "select status, disposition, reason_code from p9b_model_call_finalizations "
            "where model_call_id = :call_id"
        ),
        {"call_id": expired.model_call_id},
    ).one()
    assert finalization == (
        "TERMINAL_FAILED",
        "AUTHORITY_REJECTED",
        "P9B_EGRESS_AUTHORITY_EXPIRED_OR_MISMATCH",
    )


def test_invalid_provider_metadata_becomes_audited_terminal_failure(session: Session) -> None:
    call = _seed_call(session)
    attempt_id = _begin_attempt(session, call.model_call_id)
    session.execute(
        text(
            "update p9b_model_call_attempts set outcome = 'SUCCEEDED', "
            "provider_http_status = 200, provider_response_id = :unsafe, "
            "raw_response_reference_kind = 'PROVIDER_RESPONSE_ID', "
            "response_hash = :response_hash, parsed_result_hash = :parsed_hash, "
            "input_tokens = 10, output_tokens = 20, cache_read_tokens = 0, "
            "cache_write_tokens = 0, cost_status = 'COST_NOT_REPORTED', "
            "monetary_cost = null, latency_ms = 25, completed_at = :completed_at "
            "where attempt_id = :attempt_id"
        ),
        {
            "unsafe": "Authorization: Bearer abcdefghijklmnop",
            "response_hash": "8" * 64,
            "parsed_hash": "9" * 64,
            "completed_at": NOW,
            "attempt_id": attempt_id,
        },
    )
    attempt = session.execute(
        text(
            "select outcome, error_code, provider_response_id, parsed_result_hash "
            "from p9b_model_call_attempts where attempt_id = :attempt_id"
        ),
        {"attempt_id": attempt_id},
    ).one()
    assert attempt == (
        "RESPONSE_METADATA_REJECTED",
        "CREDENTIAL_MATERIAL_REJECTED",
        None,
        None,
    )

    with pytest.raises(DBAPIError, match="P9B_ATTEMPT_RESULT_ALREADY_TERMINAL"):
        session.execute(
            text(
                "update p9b_model_call_attempts set outcome = 'TERMINAL_PROVIDER_ERROR' "
                "where attempt_id = :attempt_id"
            ),
            {"attempt_id": attempt_id},
        )

    session.rollback()
    call = _seed_call(session)
    attempt_id = _begin_attempt(session, call.model_call_id)
    session.execute(
        text(
            "update p9b_model_call_attempts set outcome = 'SUCCEEDED', "
            "provider_http_status = 200, provider_response_id = :unsafe, "
            "raw_response_reference_kind = 'PROVIDER_RESPONSE_ID', "
            "response_hash = :response_hash, parsed_result_hash = :parsed_hash, "
            "input_tokens = 10, output_tokens = 20, cache_read_tokens = 0, "
            "cache_write_tokens = 0, cost_status = 'COST_NOT_REPORTED', "
            "latency_ms = 25, completed_at = :completed_at "
            "where attempt_id = :attempt_id"
        ),
        {
            "unsafe": "Authorization: Bearer abcdefghijklmnop",
            "response_hash": "8" * 64,
            "parsed_hash": "9" * 64,
            "completed_at": NOW,
            "attempt_id": attempt_id,
        },
    )
    session.execute(
        text("insert into p9b_model_call_finalizations (model_call_id) values (:call_id)"),
        {"call_id": call.model_call_id},
    )
    ledger = session.execute(
        text(
            "select status, terminal_disposition, attempt_count, retry_count, "
            "attempts->0->>'outcome' as first_outcome "
            "from p9b_model_call_ledger_view where model_call_id = :call_id"
        ),
        {"call_id": call.model_call_id},
    ).one()
    assert ledger == (
        "TERMINAL_FAILED",
        "RESPONSE_METADATA_REJECTED",
        1,
        0,
        "RESPONSE_METADATA_REJECTED",
    )
