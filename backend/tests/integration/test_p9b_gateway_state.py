import time
from uuid import UUID, uuid7

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from tests.integration.p9b_gateway_support import (
    persist_model_call,
    seed_gateway_authority,
)

pytestmark = pytest.mark.integration


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
    valid = seed_gateway_authority(session)
    persist_model_call(session, valid.intent)
    valid_attempt_id = _begin_attempt(
        session,
        valid.intent.model_call_id,
        forced_authorized=False,
    )
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

    expired = seed_gateway_authority(session, expiry_seconds=1.0)
    persist_model_call(session, expired.intent)
    time.sleep(1.2)
    expired_attempt_id = _begin_attempt(
        session,
        expired.intent.model_call_id,
        forced_authorized=True,
    )
    expired_attempt = session.execute(
        text(
            "select authorization_decision, provider_invocation_allowed, outcome, "
            "authorization_checked_at "
            "from p9b_model_call_attempts where attempt_id = :attempt_id"
        ),
        {"attempt_id": expired_attempt_id},
    ).one()
    assert expired_attempt[:3] == ("AUTHORITY_REJECTED", False, "AUTHORITY_REJECTED")
    assert expired_attempt.authorization_checked_at >= expired.expires_at

    session.execute(
        text(
            "insert into p9b_model_call_finalizations "
            "(model_call_id, status, disposition, reason_code, finalized_at) values "
            "(:call_id, 'SUCCEEDED', 'COMPLETED', 'FORGED', '2000-01-01T00:00:00Z')"
        ),
        {"call_id": expired.intent.model_call_id},
    )
    finalization = session.execute(
        text(
            "select status, disposition, reason_code from p9b_model_call_finalizations "
            "where model_call_id = :call_id"
        ),
        {"call_id": expired.intent.model_call_id},
    ).one()
    assert finalization == (
        "TERMINAL_FAILED",
        "AUTHORITY_REJECTED",
        "P9B_EGRESS_AUTHORITY_EXPIRED_OR_MISMATCH",
    )


def test_invalid_provider_metadata_becomes_audited_terminal_failure(session: Session) -> None:
    authority = seed_gateway_authority(session)
    persist_model_call(session, authority.intent)
    attempt_id = _begin_attempt(session, authority.intent.model_call_id)
    session.execute(
        text(
            "update p9b_model_call_attempts set outcome = 'SUCCEEDED', "
            "provider_http_status = 200, provider_response_id = :unsafe, "
            "raw_response_reference_kind = 'PROVIDER_RESPONSE_ID', "
            "response_hash = :response_hash, parsed_result_hash = :parsed_hash, "
            "input_tokens = 10, output_tokens = 20, cache_read_tokens = 0, "
            "cache_write_tokens = 0, cost_status = 'COST_NOT_REPORTED', "
            "monetary_cost = null, latency_ms = 25, completed_at = clock_timestamp() "
            "where attempt_id = :attempt_id"
        ),
        {
            "unsafe": "Authorization: Bearer abcdefghijklmnop",
            "response_hash": "8" * 64,
            "parsed_hash": "9" * 64,
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
    authority = seed_gateway_authority(session)
    persist_model_call(session, authority.intent)
    attempt_id = _begin_attempt(session, authority.intent.model_call_id)
    session.execute(
        text(
            "update p9b_model_call_attempts set outcome = 'SUCCEEDED', "
            "provider_http_status = 200, provider_response_id = :unsafe, "
            "raw_response_reference_kind = 'PROVIDER_RESPONSE_ID', "
            "response_hash = :response_hash, parsed_result_hash = :parsed_hash, "
            "input_tokens = 10, output_tokens = 20, cache_read_tokens = 0, "
            "cache_write_tokens = 0, cost_status = 'COST_NOT_REPORTED', "
            "latency_ms = 25, completed_at = clock_timestamp() "
            "where attempt_id = :attempt_id"
        ),
        {
            "unsafe": "Authorization: Bearer abcdefghijklmnop",
            "response_hash": "8" * 64,
            "parsed_hash": "9" * 64,
            "attempt_id": attempt_id,
        },
    )
    session.execute(
        text("insert into p9b_model_call_finalizations (model_call_id) values (:call_id)"),
        {"call_id": authority.intent.model_call_id},
    )
    ledger = session.execute(
        text(
            "select status, terminal_disposition, attempt_count, retry_count, "
            "attempts->0->>'outcome' as first_outcome "
            "from p9b_model_call_ledger_view where model_call_id = :call_id"
        ),
        {"call_id": authority.intent.model_call_id},
    ).one()
    assert ledger == (
        "TERMINAL_FAILED",
        "RESPONSE_METADATA_REJECTED",
        1,
        0,
        "RESPONSE_METADATA_REJECTED",
    )
