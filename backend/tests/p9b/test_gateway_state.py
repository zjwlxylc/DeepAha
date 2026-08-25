from datetime import UTC, datetime
from uuid import uuid7

import pytest
from pydantic import ValidationError

from deepaha.contracts.phase9b import (
    ModelAttemptOutcome,
    ModelAttemptResultSchemaV08,
    ModelCallIntentSchemaV08,
    RawResponseReferenceKind,
    RawResponseReferenceSchemaV08,
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


def test_model_call_intent_is_strict_and_generation_parameters_are_numeric() -> None:
    intent = ModelCallIntentSchemaV08.model_validate(_call_intent())
    assert intent.temperature == 0.0
    assert intent.top_p == 1.0
    assert intent.seed == 42

    with pytest.raises(ValidationError):
        ModelCallIntentSchemaV08.model_validate({**_call_intent(), "undeclared": "value"})
    with pytest.raises(ValidationError):
        ModelCallIntentSchemaV08.model_validate({**_call_intent(), "temperature": "cold"})


def test_raw_response_reference_is_structured_not_an_arbitrary_url() -> None:
    internal = RawResponseReferenceSchemaV08(
        kind=RawResponseReferenceKind.INTERNAL_OBJECT,
        storage_bucket="model-audit",
        object_key="p9b/calls/response.json",
        content_sha256="4" * 64,
        provider_response_id=None,
    )
    assert internal.object_key == "p9b/calls/response.json"

    provider = RawResponseReferenceSchemaV08(
        kind=RawResponseReferenceKind.PROVIDER_RESPONSE_ID,
        storage_bucket=None,
        object_key=None,
        content_sha256=None,
        provider_response_id="response_01JTEST",
    )
    assert provider.provider_response_id == "response_01JTEST"

    with pytest.raises(ValidationError):
        RawResponseReferenceSchemaV08(
            kind=RawResponseReferenceKind.INTERNAL_OBJECT,
            storage_bucket=None,
            object_key="https://provider.example/response?token=secret",
            content_sha256="4" * 64,
            provider_response_id=None,
        )


def test_attempt_result_requires_terminal_outcome_shape() -> None:
    result = ModelAttemptResultSchemaV08(
        outcome=ModelAttemptOutcome.SUCCEEDED,
        provider_http_status=200,
        error_code=None,
        raw_response_reference=RawResponseReferenceSchemaV08(
            kind=RawResponseReferenceKind.PROVIDER_RESPONSE_ID,
            storage_bucket=None,
            object_key=None,
            content_sha256=None,
            provider_response_id="response_01JTEST",
        ),
        response_hash="5" * 64,
        parsed_result_hash="6" * 64,
        input_tokens=10,
        output_tokens=20,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_status="COST_NOT_REPORTED",
        monetary_cost=None,
        latency_ms=25,
        completed_at=NOW,
    )
    assert result.outcome is ModelAttemptOutcome.SUCCEEDED

    with pytest.raises(ValidationError):
        ModelAttemptResultSchemaV08.model_validate(
            {**result.model_dump(), "response_hash": None}
        )
