from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from deepaha.contracts.phase7 import FeedbackAdjudicationDecision
from deepaha.review.auth import ReviewerPrincipal, ReviewerRole
from deepaha.review.schemas import (
    ApprovedLabelWrite,
    ConfidenceAssessmentWrite,
    FeedbackAdjudicationWrite,
)
from deepaha.review.service import (
    ReviewUnavailable,
    adjudication_input_sha256,
    assert_adjudication_consistent,
    evidence_class_for_profile,
    label_input_sha256,
)

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
REVIEWER_ID = UUID("019b0000-0000-7000-8000-000000000701")
CASE_ID = UUID("019b0000-0000-7000-8000-000000000702")
ASSESSMENT_ID = UUID("019b0000-0000-7000-8000-000000000703")
ADJUDICATION_ID = UUID("019b0000-0000-7000-8000-000000000704")
EVIDENCE_A = UUID("019b0000-0000-7000-8000-000000000705")
EVIDENCE_B = UUID("019b0000-0000-7000-8000-000000000706")


def principal(*roles: ReviewerRole) -> ReviewerPrincipal:
    return ReviewerPrincipal(
        reviewer_id=REVIEWER_ID,
        roles=frozenset(roles),
        purposes=frozenset({"FEEDBACK_REVIEW_AND_VALIDATION"}),
        synthetic=True,
    )


def assessment_write(**changes: object) -> ConfidenceAssessmentWrite:
    values: dict[str, object] = {
        "evidence_complete": True,
        "confidence_band": "HIGH",
        "risk_level": "NORMAL",
        "conflict": False,
        "evidence_ref_ids": [EVIDENCE_A],
        "rationale": "合成审核：证据与解释纠错一致。",
    }
    values.update(changes)
    return ConfidenceAssessmentWrite.model_validate(values)


def adjudication_write(**changes: object) -> FeedbackAdjudicationWrite:
    values: dict[str, object] = {
        "confidence_assessment_id": ASSESSMENT_ID,
        "decision": "CONFIRMED",
        "evidence_ref_ids": [EVIDENCE_A],
        "reason": "合成裁决：原解释未明确显示证据位置。",
    }
    values.update(changes)
    return FeedbackAdjudicationWrite.model_validate(values)


def test_reviewer_writes_are_strict_bounded_and_accept_no_actor_or_provenance() -> None:
    assessment = assessment_write()
    adjudication = adjudication_write()
    label = ApprovedLabelWrite.model_validate(
        {
            "feedback_adjudication_id": ADJUDICATION_ID,
            "approved_target_value": "解释应明确显示官方证据入口。",
            "evidence_ref_ids": [EVIDENCE_A],
        }
    )

    assert assessment.evidence_ref_ids == (EVIDENCE_A,)
    assert adjudication.decision is FeedbackAdjudicationDecision.CONFIRMED
    assert "reviewer_id" not in ConfidenceAssessmentWrite.model_fields
    assert "adjudicator_id" not in FeedbackAdjudicationWrite.model_fields
    assert "curator_id" not in ApprovedLabelWrite.model_fields
    assert "evidence_class" not in ApprovedLabelWrite.model_fields
    with pytest.raises(ValidationError):
        assessment_write(reviewer_id=REVIEWER_ID)
    with pytest.raises(ValidationError):
        assessment_write(evidence_ref_ids=[EVIDENCE_A, EVIDENCE_A])
    with pytest.raises(ValidationError):
        adjudication_write(reason="字" * 501)
    with pytest.raises(ValidationError):
        ApprovedLabelWrite.model_validate(
            {
                **label.model_dump(),
                "evidence_class": "CONSENTED_HUMAN_PARTICIPANT",
            }
        )


def test_confirmed_adjudication_requires_complete_nonconflicting_linked_evidence() -> None:
    command = adjudication_write()

    assert_adjudication_consistent(
        assessment_write(),
        command,
        linked_evidence_ids=frozenset({EVIDENCE_A, EVIDENCE_B}),
    )
    for assessment, adjudication, linked in (
        (assessment_write(evidence_complete=False), command, frozenset({EVIDENCE_A})),
        (assessment_write(conflict=True), command, frozenset({EVIDENCE_A})),
        (assessment_write(), command, frozenset({EVIDENCE_B})),
        (
            assessment_write(evidence_ref_ids=[EVIDENCE_B]),
            command,
            frozenset({EVIDENCE_A, EVIDENCE_B}),
        ),
    ):
        with pytest.raises(ReviewUnavailable):
            assert_adjudication_consistent(
                assessment,
                adjudication,
                linked_evidence_ids=linked,
            )


def test_nonterminal_decisions_must_match_assessment_state() -> None:
    assert_adjudication_consistent(
        assessment_write(evidence_complete=False),
        adjudication_write(decision="NEEDS_EVIDENCE", evidence_ref_ids=[]),
        linked_evidence_ids=frozenset(),
    )
    assert_adjudication_consistent(
        assessment_write(conflict=True),
        adjudication_write(decision="CONFLICT"),
        linked_evidence_ids=frozenset({EVIDENCE_A}),
    )
    with pytest.raises(ReviewUnavailable):
        assert_adjudication_consistent(
            assessment_write(),
            adjudication_write(decision="NEEDS_EVIDENCE", evidence_ref_ids=[]),
            linked_evidence_ids=frozenset(),
        )
    with pytest.raises(ReviewUnavailable):
        assert_adjudication_consistent(
            assessment_write(),
            adjudication_write(decision="CONFLICT"),
            linked_evidence_ids=frozenset({EVIDENCE_A}),
        )


def test_review_digests_bind_server_principal_case_and_canonical_command() -> None:
    reviewer = principal(ReviewerRole.FEEDBACK_ADJUDICATOR, ReviewerRole.LABEL_CURATOR)
    adjudication = adjudication_write()
    label = ApprovedLabelWrite.model_validate(
        {
            "feedback_adjudication_id": ADJUDICATION_ID,
            "approved_target_value": "解释应明确显示官方证据入口。",
            "evidence_ref_ids": [EVIDENCE_A],
        }
    )

    first = adjudication_input_sha256(reviewer, CASE_ID, adjudication)
    assert first == adjudication_input_sha256(reviewer, CASE_ID, adjudication)
    assert first != adjudication_input_sha256(
        principal(ReviewerRole.FEEDBACK_ADJUDICATOR),
        UUID("019b0000-0000-7000-8000-000000000799"),
        adjudication,
    )
    assert label_input_sha256(reviewer, CASE_ID, label) != label_input_sha256(
        principal(ReviewerRole.LABEL_CURATOR),
        UUID("019b0000-0000-7000-8000-000000000799"),
        label,
    )


def test_label_evidence_class_is_derived_from_bound_profile() -> None:
    assert evidence_class_for_profile(synthetic=True) == "SYNTHETIC_FEEDBACK_WORKFLOW_ONLY"
    assert evidence_class_for_profile(synthetic=False) == "CONSENTED_HUMAN_PARTICIPANT"
