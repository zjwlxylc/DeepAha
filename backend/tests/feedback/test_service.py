from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from deepaha.feedback.schemas import FeedbackSubmissionWrite
from deepaha.feedback.service import (
    feedback_input_sha256,
    governed_evidence_ids,
    required_user_purpose,
)
from deepaha.personal.auth import Principal

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
OWNER_ID = UUID("019b0000-0000-7000-8000-000000000711")
RANKING_ID = UUID("019b0000-0000-7000-8000-000000000712")
MATCH_ID = UUID("019b0000-0000-7000-8000-000000000713")
EVIDENCE_A = UUID("019b0000-0000-7000-8000-000000000714")
EVIDENCE_B = UUID("019b0000-0000-7000-8000-000000000715")
PUBLIC_ID = "opp_0123456789abcdef0123456789abcdef"


def submission_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "ranking_snapshot_id": RANKING_ID,
        "match_snapshot_id": MATCH_ID,
        "opportunity_version": 1,
        "user_state_version": 1,
        "event_type": "STRUCTURED_CORRECTION",
        "claim_kind": "EXPLANATION_UNCLEAR",
        "user_statement": " 合成反馈：解释没有指出证据位置。 ",
        "structured_reason_code": "MISSING_EVIDENCE_EXPLANATION",
        "initial_evidence_ref_ids": [EVIDENCE_A],
        "consent_version": "phase7-feedback-consent-v1",
        "consent_scope": "FEEDBACK_REVIEW_AND_VALIDATION",
    }
    values.update(changes)
    return values


def test_submission_is_strict_bounded_and_has_no_authoritative_identity() -> None:
    command = FeedbackSubmissionWrite.model_validate(submission_values())

    assert command.user_statement == "合成反馈：解释没有指出证据位置。"
    assert "user_id" not in FeedbackSubmissionWrite.model_fields
    assert "owner_user_id" not in FeedbackSubmissionWrite.model_fields
    with pytest.raises(ValidationError):
        FeedbackSubmissionWrite.model_validate(submission_values(user_id=OWNER_ID))
    with pytest.raises(ValidationError):
        FeedbackSubmissionWrite.model_validate(submission_values(user_statement="字" * 501))
    with pytest.raises(ValidationError):
        FeedbackSubmissionWrite.model_validate(
            submission_values(consent_version="phase6-consent-v1")
        )
    with pytest.raises(ValidationError, match="reason code"):
        FeedbackSubmissionWrite.model_validate(
            submission_values(structured_reason_code="RANKING_CONTEXT_IRRELEVANT")
        )


def test_claim_kind_maps_to_current_phase6_purpose() -> None:
    assert required_user_purpose("ELIGIBILITY_CORRECTION") == "ELIGIBILITY"
    assert required_user_purpose("OPPORTUNITY_FACT_CORRECTION") == "ELIGIBILITY"
    assert required_user_purpose("EXPLANATION_UNCLEAR") == "ELIGIBILITY"
    assert required_user_purpose("RANKING_IRRELEVANT") == "PERSONAL_RANKING"


def test_feedback_digest_binds_server_owner_route_and_canonical_command() -> None:
    principal = Principal(user_id=OWNER_ID)
    command = FeedbackSubmissionWrite.model_validate(submission_values())
    reordered = FeedbackSubmissionWrite.model_validate(
        submission_values(initial_evidence_ref_ids=[EVIDENCE_A])
    )

    first = feedback_input_sha256(principal, PUBLIC_ID, command)
    assert first == feedback_input_sha256(principal, PUBLIC_ID, reordered)
    assert first != feedback_input_sha256(
        Principal(user_id=UUID("019b0000-0000-7000-8000-000000000799")),
        PUBLIC_ID,
        command,
    )
    assert first != feedback_input_sha256(
        principal,
        "opp_11111111111111111111111111111111",
        command,
    )


def test_governed_evidence_allowlist_uses_source_and_exact_field_evidence_only() -> None:
    allowed = governed_evidence_ids(
        EVIDENCE_A,
        [
            {"field_path": "canonical_title", "evidence_ref_id": str(EVIDENCE_B)},
            {"field_path": "status", "evidence_ref_id": str(EVIDENCE_A)},
        ],
    )

    assert allowed == frozenset({EVIDENCE_A, EVIDENCE_B})
    with pytest.raises(ValueError, match="evidence_ref_id"):
        governed_evidence_ids(EVIDENCE_A, [{"field_path": "status"}])
