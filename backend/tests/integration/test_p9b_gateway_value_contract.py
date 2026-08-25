import json
from pathlib import Path
from typing import cast
from uuid import UUID, uuid7

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from deepaha.p9b.models import ModelCall, ModelTaskSpec
from tests.integration.p9b_gateway_support import persist_model_call, seed_gateway_authority

pytestmark = pytest.mark.integration
CORPUS = (
    Path(__file__).parents[3]
    / "contracts"
    / "corpora"
    / "v0.8.0"
    / "model-call-ledger-string-values.json"
)


def _cases() -> list[dict[str, object]]:
    payload: object = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return cast(list[dict[str, object]], payload["cases"])


def _begin_attempt(session: Session, call_id: UUID) -> UUID:
    attempt_id = uuid7()
    session.execute(
        text(
            "insert into p9b_model_call_attempts "
            "(model_call_id, attempt_number, attempt_id, authorization_decision, "
            "authorization_reason_code, authorization_checked_at, "
            "provider_invocation_allowed, created_at) values "
            "(:call_id, 1, :attempt_id, 'AUTHORITY_REJECTED', 'PENDING', "
            "clock_timestamp(), false, clock_timestamp())"
        ),
        {"call_id": call_id, "attempt_id": attempt_id},
    )
    return attempt_id


def _finish_success(
    session: Session,
    *,
    attempt_id: UUID,
    provider_response_id: str | None,
    storage_bucket: str | None = None,
    object_key: str | None = None,
    raw_response_sha256: str | None = None,
) -> None:
    internal = object_key is not None
    session.execute(
        text(
            "update p9b_model_call_attempts set outcome = 'SUCCEEDED', "
            "provider_http_status = 200, provider_response_id = :provider_response_id, "
            "raw_response_reference_kind = :reference_kind, "
            "raw_response_storage_bucket = :storage_bucket, "
            "raw_response_object_key = :object_key, raw_response_sha256 = :raw_hash, "
            "response_hash = :response_hash, parsed_result_hash = :parsed_hash, "
            "input_tokens = 10, output_tokens = 20, cache_read_tokens = 0, "
            "cache_write_tokens = 0, cost_status = 'COST_NOT_REPORTED', "
            "monetary_cost = null, latency_ms = 25, completed_at = clock_timestamp() "
            "where attempt_id = :attempt_id"
        ),
        {
            "provider_response_id": provider_response_id,
            "reference_kind": "INTERNAL_OBJECT" if internal else "PROVIDER_RESPONSE_ID",
            "storage_bucket": storage_bucket,
            "object_key": object_key,
            "raw_hash": (
                raw_response_sha256
                if internal and raw_response_sha256 is not None
                else "7" * 64
                if internal
                else None
            ),
            "response_hash": "8" * 64,
            "parsed_hash": "9" * 64,
            "attempt_id": attempt_id,
        },
    )


@pytest.mark.parametrize("case", _cases())
def test_database_value_rules_match_the_shared_corpus(
    session: Session,
    case: dict[str, object],
) -> None:
    allowed = session.scalar(
        text("select p9b_gateway_string_value_allowed(:value, :kind)"),
        {"value": case["value"], "kind": case["kind"]},
    )
    assert allowed is case["allowed"]


@pytest.mark.parametrize(
    (
        "provider_response_id",
        "storage_bucket",
        "object_key",
        "raw_response_sha256",
        "expected_error",
    ),
    [
        (
            "xoxb-123456789012-abcdefghijklmnopqrstuv",
            None,
            None,
            None,
            "CREDENTIAL_MATERIAL_REJECTED",
        ),
        (
            None,
            "model-audit",
            "p9b/result.json?access_token=synthetic-secret",
            None,
            "CREDENTIAL_MATERIAL_REJECTED",
        ),
        (
            None,
            "model-audit",
            "p9b/result.json",
            "A" * 64,
            "RESPONSE_METADATA_REJECTED",
        ),
    ],
)
def test_direct_result_writes_cannot_persist_unsafe_nested_metadata(
    session: Session,
    provider_response_id: str | None,
    storage_bucket: str | None,
    object_key: str | None,
    raw_response_sha256: str | None,
    expected_error: str,
) -> None:
    authority = seed_gateway_authority(session)
    persist_model_call(session, authority.intent)
    attempt_id = _begin_attempt(session, authority.intent.model_call_id)

    _finish_success(
        session,
        attempt_id=attempt_id,
        provider_response_id=provider_response_id,
        storage_bucket=storage_bucket,
        object_key=object_key,
        raw_response_sha256=raw_response_sha256,
    )

    result = session.execute(
        text(
            "select outcome, error_code, provider_response_id, "
            "raw_response_storage_bucket, raw_response_object_key, parsed_result_hash "
            "from p9b_model_call_attempts where attempt_id = :attempt_id"
        ),
        {"attempt_id": attempt_id},
    ).one()
    assert result == (
        "RESPONSE_METADATA_REJECTED",
        expected_error,
        None,
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    ("provider_response_id", "storage_bucket", "object_key"),
    [
        ("chatcmpl-abc123_DEF.456", None, None),
        (None, "model-audit.responses", "p9b/机会/响应 01.json"),
    ],
)
def test_direct_result_writes_keep_legal_provider_and_internal_references(
    session: Session,
    provider_response_id: str | None,
    storage_bucket: str | None,
    object_key: str | None,
) -> None:
    authority = seed_gateway_authority(session)
    persist_model_call(session, authority.intent)
    attempt_id = _begin_attempt(session, authority.intent.model_call_id)

    _finish_success(
        session,
        attempt_id=attempt_id,
        provider_response_id=provider_response_id,
        storage_bucket=storage_bucket,
        object_key=object_key,
    )

    result = session.execute(
        text(
            "select outcome, provider_response_id, raw_response_storage_bucket, "
            "raw_response_object_key from p9b_model_call_attempts "
            "where attempt_id = :attempt_id"
        ),
        {"attempt_id": attempt_id},
    ).one()
    assert result == (
        "SUCCEEDED",
        provider_response_id,
        storage_bucket,
        object_key,
    )


def test_direct_configuration_and_call_writes_cannot_bypass_value_contract(
    session: Session,
) -> None:
    with (
        pytest.raises(DBAPIError, match="P9B_GATEWAY_CONFIGURATION_STRING_INVALID"),
        session.begin_nested(),
    ):
        session.add(
            ModelTaskSpec(
                model_task_spec_id=uuid7(),
                task_name="sk-proj-abcdefghijklmnopqrstuv",
                task_version="v1",
                route_class="R2_BALANCED_REASON",
                allowed_input_block_types=["HTML_ELEMENT"],
                output_schema_version="schema-v1",
                max_input_tokens=100,
                max_output_tokens=100,
                evidence_required=True,
                abstention_allowed=True,
                risk_class="HIGH_IMPACT_CANDIDATE",
                provider_capabilities=["ZERO_RETENTION"],
                egress_policy_id="p9b-egress-v1",
                timeout_ms=1000,
                max_attempts=1,
                initial_backoff_ms=0,
                backoff_multiplier=1.0,
                max_backoff_ms=0,
                max_concurrency=1,
                max_batch_size=1,
                fallback_policy="DISABLED",
                max_fallbacks=0,
                created_at="2026-08-25T00:00:00Z",
            )
        )
        session.flush()

    authority = seed_gateway_authority(session)
    unsafe = authority.intent.model_dump(mode="python")
    unsafe["model_call_id"] = uuid7()
    unsafe["model_id"] = "sk-proj-abcdefghijklmnopqrstuv"
    with (
        pytest.raises(DBAPIError, match="P9B_MODEL_CALL_STRING_INVALID"),
        session.begin_nested(),
    ):
        session.add(ModelCall(**unsafe))
        session.flush()
