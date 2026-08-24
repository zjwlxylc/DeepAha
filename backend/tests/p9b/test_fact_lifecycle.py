from datetime import UTC, datetime
from uuid import UUID

import pytest

from deepaha.contracts.phase9b import (
    ExtractionCandidateSchemaV08,
    ExtractionRunSchemaV08,
    ExtractionTargetScope,
    FactVerificationDecisionSchemaV08,
)
from deepaha.p9b.facts import (
    FactLifecycleError,
    ensure_independent_verification,
    extraction_input_block_set_hash,
)

NOW = datetime(2026, 8, 24, 15, 0, tzinfo=UTC)


def uuid7(index: int) -> UUID:
    return UUID(f"019c0000-0000-7000-8000-{index:012x}")


def test_extraction_run_binds_real_parent_identity_and_ordered_blocks() -> None:
    block_ids = [uuid7(10), uuid7(11)]
    values = {
        "extraction_run_id": uuid7(1),
        "source_bundle_revision_id": uuid7(2),
        "target_scope": "OPPORTUNITY",
        "opportunity_id": uuid7(3),
        "opportunity_version": 4,
        "opportunity_unit_id": None,
        "opportunity_unit_version_id": None,
        "unit_segmentation_version": None,
        "task_spec_version": "p9b-extraction-task-v0.8.0",
        "extractor_kind": "DETERMINISTIC",
        "component_version": "deterministic-fields/0.8.0",
        "producer_identity": "component:deterministic-fields/0.8.0",
        "producer_response_id": None,
        "ordered_input_block_ids": block_ids,
        "input_block_set_hash": extraction_input_block_set_hash(block_ids),
        "evidence_binding_hash": "a" * 64,
        "started_at": NOW,
        "completed_at": NOW,
        "status": "SUCCEEDED",
    }

    run = ExtractionRunSchemaV08.model_validate(values)

    assert run.opportunity_version == 4
    assert not hasattr(run, "opportunity_version_id")
    with pytest.raises(ValueError, match="input_block_set_hash"):
        ExtractionRunSchemaV08.model_validate({**values, "input_block_set_hash": "b" * 64})


def test_unit_run_requires_exact_unit_version_binding() -> None:
    values = {
        "extraction_run_id": uuid7(20),
        "source_bundle_revision_id": uuid7(21),
        "target_scope": "UNIT",
        "opportunity_id": uuid7(22),
        "opportunity_version": 1,
        "opportunity_unit_id": uuid7(23),
        "opportunity_unit_version_id": uuid7(24),
        "unit_segmentation_version": "unit-segmentation/0.8.0",
        "task_spec_version": "p9b-extraction-task-v0.8.0",
        "extractor_kind": "MODEL",
        "component_version": "recorded-provider/0.8.0",
        "producer_identity": "model:recorded-provider:test-model",
        "producer_response_id": "response-fixture-001",
        "ordered_input_block_ids": [uuid7(25)],
        "input_block_set_hash": extraction_input_block_set_hash([uuid7(25)]),
        "evidence_binding_hash": "c" * 64,
        "started_at": NOW,
        "completed_at": NOW,
        "status": "SUCCEEDED",
    }

    assert ExtractionRunSchemaV08.model_validate(values).target_scope == "UNIT"
    with pytest.raises(ValueError, match="UNIT"):
        ExtractionRunSchemaV08.model_validate({**values, "opportunity_unit_version_id": None})


def test_candidate_abstention_is_fact_unknown_not_a_fifth_eligibility_state() -> None:
    candidate = ExtractionCandidateSchemaV08(
        candidate_id=uuid7(30),
        extraction_run_id=uuid7(31),
        target_scope=ExtractionTargetScope.OPPORTUNITY,
        opportunity_id=uuid7(32),
        opportunity_version=1,
        opportunity_unit_id=None,
        opportunity_unit_version_id=None,
        field_name="application_deadline",
        raw_value=None,
        normalized_value_candidate=None,
        evidence_block_ids=[uuid7(33)],
        evidence_ref_ids=[uuid7(34)],
        confidence=None,
        abstained=True,
        candidate_reason_code="UNKNOWN_SOURCE_CONFLICT",
        schema_version="0.8.0",
        created_at=NOW,
    )

    assert candidate.abstained is True
    assert candidate.candidate_reason_code.startswith("UNKNOWN_")
    with pytest.raises(ValueError, match="normalized_value_candidate"):
        ExtractionCandidateSchemaV08.model_validate(
            {**candidate.model_dump(mode="python"), "normalized_value_candidate": "2026-09-01"}
        )


def test_candidate_producer_cannot_verify_its_own_evidence() -> None:
    with pytest.raises(FactLifecycleError, match="independent"):
        ensure_independent_verification(
            producer_identity="model:provider:model-a",
            producer_response_id="response-001",
            verifier_identity="model:provider:model-a",
            verifier_response_id="response-002",
        )
    with pytest.raises(FactLifecycleError, match="response"):
        ensure_independent_verification(
            producer_identity="model:provider:model-a",
            producer_response_id="response-001",
            verifier_identity="human:reviewer-01",
            verifier_response_id="response-001",
        )

    ensure_independent_verification(
        producer_identity="model:provider:model-a",
        producer_response_id="response-001",
        verifier_identity="human:reviewer-01",
        verifier_response_id=None,
    )


def test_verification_approval_requires_supported_evidence_and_passed_precedence() -> None:
    values = {
        "decision_id": uuid7(40),
        "candidate_id": uuid7(41),
        "decision": "APPROVE",
        "verification_method": "HUMAN",
        "verifier_identity": "human:reviewer-01",
        "verifier_response_id": None,
        "reason_code": "OFFICIAL_EVIDENCE_CONFIRMED",
        "evidence_support_result": "SUPPORTED",
        "precedence_check_result": "PASSED",
        "decided_at": NOW,
    }

    assert FactVerificationDecisionSchemaV08.model_validate(values).decision == "APPROVE"
    with pytest.raises(ValueError, match="APPROVE"):
        FactVerificationDecisionSchemaV08.model_validate(
            {**values, "evidence_support_result": "UNKNOWN"}
        )
