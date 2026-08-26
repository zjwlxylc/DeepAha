import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from deepaha.local_human_test.extraction import (
    ExtractionValidationError,
    MinimizedExtractionBlock,
    ModelExtractionEnvelope,
    build_extraction_messages,
    parse_provider_envelope,
    validate_candidate_bindings,
)

BLOCK_ID = UUID("019d0000-0000-7000-8000-000000000101")
EVIDENCE_ID = UUID("019d0000-0000-7000-8000-000000000102")
UNKNOWN_BLOCK_ID = UUID("019d0000-0000-7000-8000-000000000999")


def _block(*, content: str = "报名时间为 2026 年 9 月 1 日。") -> MinimizedExtractionBlock:
    return MinimizedExtractionBlock(
        block_id=BLOCK_ID,
        evidence_ref_id=EVIDENCE_ID,
        block_hash="a" * 64,
        evidence_binding_hash="b" * 64,
        block_type="HTML_ELEMENT",
        ordinal=1,
        content=content,
    )


def _response(*, evidence_block_id: UUID = BLOCK_ID) -> bytes:
    content = {
        "schema_version": "0.8.0",
        "facts": [
            {
                "field_name": "application_window",
                "raw_value": "2026 年 9 月 1 日",
                "normalized_value_candidate": {"starts_at": "2026-09-01"},
                "evidence_block_ids": [str(evidence_block_id)],
                "confidence": 0.91,
                "abstained": False,
                "reason_code": "OFFICIAL_TEXT_EXPLICIT",
            }
        ],
        "rules": [],
        "uncertainties": [],
    }
    return json.dumps(
        {
            "id": "synthetic-response-1",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(content, ensure_ascii=False),
                    },
                }
            ],
            "usage": {"prompt_tokens": 50, "completion_tokens": 30},
        },
        ensure_ascii=False,
    ).encode()


def test_prompt_is_immutable_canonical_and_contains_only_minimized_blocks() -> None:
    messages = build_extraction_messages(
        opportunity_id=UUID("019d0000-0000-7000-8000-000000000201"),
        opportunity_version=1,
        blocks=(_block(),),
        max_input_tokens=3_000,
    )

    assert isinstance(messages, tuple)
    assert [message.role for message in messages] == ["system", "user"]
    assert "JSON" in messages[0].content
    assert "0.8.0" in messages[0].content
    assert "evidence_block_ids" in messages[0].content
    for field_name in (
        "canonical_title",
        "type",
        "issuer_name",
        "jurisdiction",
        "status",
        "published_at",
        "application_window",
        "application_deadline",
        "application_url",
        "attachment_urls",
        "locations",
        "recruitment_count",
        "applicant_scope",
        "education_requirements",
        "major_requirements",
        "age_requirements",
        "experience_requirements",
        "credential_requirements",
        "household_registration_requirements",
    ):
        assert f"`{field_name}`" in messages[0].content
    assert "confidence must be a JSON number" in messages[0].content
    assert "one or more exact input block_id values" in messages[0].content
    assert "Return at most 4 facts" in messages[0].content
    assert "Do not spend tokens on reasoning" in messages[0].content
    assert "reason_code must be a non-empty uppercase JSON string" in messages[0].content
    assert "uncertainties must be a JSON array containing only plain strings" in messages[0].content
    assert "Do not emit abstained facts" in messages[0].content
    payload = json.loads(messages[1].content)
    assert payload == {
        "blocks": [
            {
                "block_hash": "a" * 64,
                "block_id": str(BLOCK_ID),
                "block_type": "HTML_ELEMENT",
                "content": "报名时间为 2026 年 9 月 1 日。",
                "ordinal": 1,
            }
        ],
        "target": {
            "opportunity_id": "019d0000-0000-7000-8000-000000000201",
            "opportunity_version": 1,
            "target_scope": "OPPORTUNITY",
        },
    }


def test_prompt_fails_closed_when_budget_cannot_hold_one_complete_block() -> None:
    with pytest.raises(ExtractionValidationError, match="MODEL_INPUT_BUDGET_EXCEEDED"):
        build_extraction_messages(
            opportunity_id=UUID("019d0000-0000-7000-8000-000000000201"),
            opportunity_version=1,
            blocks=(_block(content="很长" * 2_000),),
            max_input_tokens=100,
        )


def test_strict_provider_envelope_and_exact_evidence_binding() -> None:
    response_id, envelope = parse_provider_envelope(_response())
    validated = validate_candidate_bindings(envelope, blocks=(_block(),))

    assert response_id == "synthetic-response-1"
    assert isinstance(validated, ModelExtractionEnvelope)
    assert validated.facts[0].evidence_block_ids == (BLOCK_ID,)


@pytest.mark.parametrize("field_name", ["type", "status"])
def test_publication_identity_fields_are_valid_fact_candidates(field_name: str) -> None:
    payload = json.loads(_response())
    content = json.loads(payload["choices"][0]["message"]["content"])
    content["facts"][0]["field_name"] = field_name
    content["facts"][0]["raw_value"] = "OPEN"
    content["facts"][0]["normalized_value_candidate"] = "OPEN"
    payload["choices"][0]["message"]["content"] = json.dumps(content)

    _response_id, envelope = parse_provider_envelope(json.dumps(payload).encode())

    assert envelope.facts[0].field_name == field_name


def test_unknown_block_rejects_complete_envelope_before_any_persistence() -> None:
    _response_id, envelope = parse_provider_envelope(_response(evidence_block_id=UNKNOWN_BLOCK_ID))

    with pytest.raises(ExtractionValidationError, match="EVIDENCE_BINDING_INVALID"):
        validate_candidate_bindings(envelope, blocks=(_block(),))


def test_unknown_field_and_duplicate_field_are_rejected() -> None:
    payload = json.loads(_response())
    content = json.loads(payload["choices"][0]["message"]["content"])
    content["facts"][0]["field_name"] = "model_invented_field"
    payload["choices"][0]["message"]["content"] = json.dumps(content)
    with pytest.raises(ValidationError):
        parse_provider_envelope(json.dumps(payload).encode())

    content["facts"][0]["field_name"] = "application_window"
    content["facts"].append(dict(content["facts"][0]))
    payload["choices"][0]["message"]["content"] = json.dumps(content)
    _response_id, envelope = parse_provider_envelope(json.dumps(payload).encode())
    with pytest.raises(ExtractionValidationError, match="DUPLICATE_FACT_FIELD"):
        validate_candidate_bindings(envelope, blocks=(_block(),))


def test_abstention_cannot_smuggle_a_normalized_value() -> None:
    payload = json.loads(_response())
    content = json.loads(payload["choices"][0]["message"]["content"])
    fact = content["facts"][0]
    fact["abstained"] = True
    fact["reason_code"] = "UNKNOWN_OFFICIAL_TEXT_AMBIGUOUS"
    payload["choices"][0]["message"]["content"] = json.dumps(content)

    with pytest.raises(ValidationError):
        parse_provider_envelope(json.dumps(payload).encode())
