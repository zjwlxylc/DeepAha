import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid7

import pytest
from pydantic import ValidationError

from deepaha.contracts.phase9b import (
    EgressBlockClassificationSchemaV08,
    ModelAttemptOutcome,
    ModelCallIntentSchemaV08,
    ProviderEgressPolicySnapshotSchemaV08,
    RawResponseReferenceKind,
    RawResponseReferenceSchemaV08,
    RetentionClass,
    SourceEgressPolicySnapshotSchemaV08,
)
from deepaha.p9b.ledger_values import is_gateway_string_value_allowed
from deepaha.p9b.provider import ProviderAttemptResult

CORPUS = (
    Path(__file__).parents[3]
    / "contracts"
    / "corpora"
    / "v0.8.0"
    / "model-call-ledger-string-values.json"
)
NOW = datetime(2026, 8, 25, 7, 0, tzinfo=UTC)


def _call_intent() -> dict[str, object]:
    return {
        "model_call_id": uuid7(),
        "task_spec_name": "extract-opportunity",
        "task_spec_version": "v1",
        "provider": "fake-provider",
        "model_id": "fake-model",
        "model_snapshot": "fake-model-2026-08-25",
        "adapter_name": "fake-adapter",
        "adapter_version": "v1",
        "runtime_version": "python-3.14",
        "canonical_request_hash": "1" * 64,
        "canonical_message_hashes": ["2" * 64],
        "input_block_ids": [uuid7()],
        "input_block_hashes": ["3" * 64],
        "source_bundle_revision_id": uuid7(),
        "target_scope": "OPPORTUNITY",
        "opportunity_id": uuid7(),
        "opportunity_version": 1,
        "opportunity_unit_id": None,
        "opportunity_unit_version_id": None,
        "unit_segmentation_version": None,
        "prompt_version": "prompt-v1",
        "output_schema_version": "schema-v1",
        "parser_version": "parser-v1",
        "contract_version": "contract-v1",
        "temperature": 0.0,
        "top_p": 1.0,
        "seed": 42,
        "egress_decision_id": uuid7(),
        "validation_pipeline_version": "validation-v1",
        "retention_class": "ZERO_RETENTION",
        "registered_at": NOW,
    }


def _cases() -> list[dict[str, object]]:
    payload: object = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return cast(list[dict[str, object]], payload["cases"])


@pytest.mark.parametrize("case", _cases())
def test_python_value_rules_match_the_shared_corpus(case: dict[str, object]) -> None:
    assert (
        is_gateway_string_value_allowed(
            str(case["value"]),
            str(case["kind"]),
        )
        is case["allowed"]
    )


def test_nested_and_top_level_ledger_contracts_reject_credential_material() -> None:
    with pytest.raises(ValidationError):
        RawResponseReferenceSchemaV08(
            kind=RawResponseReferenceKind.PROVIDER_RESPONSE_ID,
            storage_bucket=None,
            object_key=None,
            content_sha256=None,
            provider_response_id="xoxb-123456789012-abcdefghijklmnopqrstuv",
        )
    with pytest.raises(ValidationError):
        RawResponseReferenceSchemaV08(
            kind=RawResponseReferenceKind.INTERNAL_OBJECT,
            storage_bucket="model-audit",
            object_key="p9b/result.json?access_token=synthetic-secret",
            content_sha256="4" * 64,
            provider_response_id=None,
        )
    with pytest.raises(ValidationError):
        ModelCallIntentSchemaV08.model_validate(
            {**_call_intent(), "model_id": "sk-proj-abcdefghijklmnopqrstuv"}
        )


def test_provider_result_rejects_unsafe_flattened_response_metadata() -> None:
    with pytest.raises(ValueError, match="provider_response_id"):
        ProviderAttemptResult(
            outcome=ModelAttemptOutcome.SUCCEEDED,
            provider_http_status=200,
            error_code=None,
            provider_response_id="https://provider.example/result?api_key=secret",
            raw_response_reference_kind="PROVIDER_RESPONSE_ID",
            raw_response_storage_bucket=None,
            raw_response_object_key=None,
            raw_response_sha256=None,
            response_hash="5" * 64,
            parsed_result_hash="6" * 64,
            input_tokens=1,
            output_tokens=1,
            cache_read_tokens=0,
            cache_write_tokens=0,
            cost_status="COST_NOT_REPORTED",
            monetary_cost=None,
            latency_ms=1,
        )


def test_legal_provider_and_internal_references_remain_accepted() -> None:
    provider = RawResponseReferenceSchemaV08(
        kind=RawResponseReferenceKind.PROVIDER_RESPONSE_ID,
        storage_bucket=None,
        object_key=None,
        content_sha256=None,
        provider_response_id="response_01JTEST",
    )
    internal = RawResponseReferenceSchemaV08(
        kind=RawResponseReferenceKind.INTERNAL_OBJECT,
        storage_bucket="model-audit.responses",
        object_key="p9b/机会/响应 01.json",
        content_sha256="4" * 64,
        provider_response_id=None,
    )
    assert provider.provider_response_id == "response_01JTEST"
    assert internal.object_key == "p9b/机会/响应 01.json"


def test_all_authority_configuration_contracts_reject_unsafe_identifiers() -> None:
    with pytest.raises(ValidationError):
        EgressBlockClassificationSchemaV08(
            classification_id=uuid7(),
            block_id=uuid7(),
            block_hash="1" * 64,
            classification_version="classification-v1",
            classifications=["PUBLIC_OFFICIAL_GENERAL"],
            contains_user_data=False,
            classifier_identity="ghp_abcdefghijklmnopqrstuvwxyz123456",
            created_at=NOW,
        )
    with pytest.raises(ValidationError):
        SourceEgressPolicySnapshotSchemaV08(
            snapshot_id="source-policy-v1",
            snapshot_hash="2" * 64,
            source_bundle_revision_id=uuid7(),
            allows_egress=True,
            valid_from=NOW,
            valid_until=datetime(2026, 8, 25, 8, 0, tzinfo=UTC),
            recorded_by="glpat-abcdefghijklmnopqrstuvwxyz123456",
            created_at=NOW,
        )
    with pytest.raises(ValidationError):
        ProviderEgressPolicySnapshotSchemaV08(
            snapshot_id="provider-policy-v1",
            snapshot_hash="3" * 64,
            provider="xoxb-123456789012-abcdefghijklmnopqrstuv",
            region="local-test",
            active=True,
            zero_retention=True,
            training_use=False,
            supports_idempotency=True,
            allowed_classifications=["PUBLIC_OFFICIAL_GENERAL"],
            retention_class=RetentionClass.ZERO_RETENTION,
            valid_from=NOW,
            valid_until=datetime(2026, 8, 25, 8, 0, tzinfo=UTC),
            recorded_by="human:security-reviewer",
            created_at=NOW,
        )
