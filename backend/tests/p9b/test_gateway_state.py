from datetime import UTC, datetime
from uuid import uuid7

import pytest
from pydantic import ValidationError

from deepaha.contracts.phase9b import (
    EgressDecisionSchemaV08,
    ModelAttemptOutcome,
    ModelAttemptResultSchemaV08,
    ModelCallIntentSchemaV08,
    ModelTaskSpecSchemaV08,
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


def test_task_spec_and_egress_decision_are_strict_bounded_contracts() -> None:
    task = ModelTaskSpecSchemaV08(
        model_task_spec_id=uuid7(),
        task_name="extract-opportunity",
        task_version="v1",
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
        created_at=NOW,
    )
    assert task.max_attempts == 2
    with pytest.raises(ValidationError):
        ModelTaskSpecSchemaV08.model_validate(
            {
                **task.model_dump(),
                "provider_capabilities": ["sk-proj-abcdefghijklmnopqrstuv"],
            }
        )

    decision = {
        "egress_decision_id": uuid7(),
        "task_spec_name": task.task_name,
        "task_spec_version": task.task_version,
        "source_bundle_revision_id": uuid7(),
        "target_scope": "OPPORTUNITY",
        "opportunity_id": uuid7(),
        "opportunity_version": 1,
        "opportunity_unit_id": None,
        "opportunity_unit_version_id": None,
        "input_block_ids": [uuid7()],
        "input_block_hashes": ["a" * 64],
        "data_classification_version": "classification-v1",
        "minimizer_version": "minimizer-v1",
        "redactor_version": "redactor-v1",
        "source_policy_snapshot_id": "source-policy-v1",
        "source_policy_snapshot_hash": "b" * 64,
        "provider_policy_snapshot_id": "provider-policy-v1",
        "provider_policy_snapshot_hash": "c" * 64,
        "provider": "fake-provider",
        "provider_region": "local-test",
        "original_input_hash": "d" * 64,
        "actual_payload_hash": "e" * 64,
        "decision": "ALLOW",
        "actor_type": "SYSTEM",
        "actor_identity": None,
        "reason_codes": ["POLICY_ALLOW"],
        "created_at": NOW,
        "expires_at": datetime(2026, 8, 25, 7, 5, tzinfo=UTC),
    }
    assert EgressDecisionSchemaV08.model_validate(decision).decision == "ALLOW"
    with pytest.raises(ValidationError):
        EgressDecisionSchemaV08.model_validate(
            {**decision, "provider": "xoxb-123456789012-abcdefghijklmnopqrstuv"}
        )
    with pytest.raises(ValidationError):
        EgressDecisionSchemaV08.model_validate(
            {**decision, "input_block_hashes": ["a" * 64, "b" * 64]}
        )
