from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from deepaha.api.review import get_review_service, require_reviewer_principal
from deepaha.main import create_app
from deepaha.review.auth import ReviewerPrincipal, ReviewerRole
from deepaha.review.schemas import (
    ApprovedLabelResult,
    ConfidenceAssessmentResult,
    FeedbackAdjudicationResult,
    ReviewCaseDetail,
    ReviewCaseHistoryItem,
    ReviewEvidenceItem,
    ReviewQueueItem,
    ReviewQueuePage,
)
from deepaha.review.service import ReviewIdempotencyConflict

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
REVIEWER_ID = UUID("019b0000-0000-7000-8000-000000000701")
CASE_ID = UUID("019b0000-0000-7000-8000-000000000702")
EVENT_ID = UUID("019b0000-0000-7000-8000-000000000703")
ASSESSMENT_ID = UUID("019b0000-0000-7000-8000-000000000704")
ADJUDICATION_ID = UUID("019b0000-0000-7000-8000-000000000705")
LABEL_ID = UUID("019b0000-0000-7000-8000-000000000706")
EVIDENCE_ID = UUID("019b0000-0000-7000-8000-000000000707")


def principal(*roles: ReviewerRole) -> ReviewerPrincipal:
    return ReviewerPrincipal(
        reviewer_id=REVIEWER_ID,
        roles=frozenset(roles),
        purposes=frozenset({"FEEDBACK_REVIEW_AND_VALIDATION"}),
        synthetic=True,
    )


def queue_item() -> ReviewQueueItem:
    return ReviewQueueItem.model_validate(
        {
            "review_case_id": CASE_ID,
            "feedback_event_id": EVENT_ID,
            "version": 1,
            "status": "RECEIVED",
            "priority": 2,
            "due_at": NOW - timedelta(minutes=1),
            "overdue": True,
            "claim_kind": "EXPLANATION_UNCLEAR",
            "opportunity_public_id": "opp_0123456789abcdef0123456789abcdef",
            "opportunity_title": "合成青年发展计划",
            "opportunity_version": 1,
            "created_at": NOW - timedelta(days=2),
        }
    )


class FakeReviewService:
    def __init__(self) -> None:
        self.missing = False
        self.conflict = False
        self.last_key: str | None = None

    def list_queue(self, _principal: ReviewerPrincipal) -> ReviewQueuePage:
        return ReviewQueuePage(items=(queue_item(),))

    def get_case(
        self,
        _principal: ReviewerPrincipal,
        _review_case_id: UUID,
    ) -> ReviewCaseDetail | None:
        if self.missing:
            return None
        return ReviewCaseDetail(
            case=queue_item(),
            user_statement="合成反馈：解释未显示证据位置。",
            structured_reason_code="MISSING_EVIDENCE_EXPLANATION",
            match_snapshot_id=UUID("019b0000-0000-7000-8000-000000000708"),
            history=(
                ReviewCaseHistoryItem.model_validate(
                    {
                        "version": 1,
                        "status": "RECEIVED",
                        "priority": 2,
                        "due_at": NOW,
                        "transition_reason": "INITIAL_SUBMISSION",
                        "created_at": NOW,
                    }
                ),
            ),
            evidence=(
                ReviewEvidenceItem.model_validate(
                    {
                        "evidence_ref_id": EVIDENCE_ID,
                        "document_id": UUID("019b0000-0000-7000-8000-000000000709"),
                        "locator_kind": "TEXT_QUOTE",
                        "locator_value": "合成官方证据位置",
                        "relation": "SUPPORTS",
                        "actor_kind": "USER",
                        "note": None,
                        "created_at": NOW,
                    }
                ),
            ),
            latest_assessment=None,
            latest_adjudication=None,
            approved_label_id=None,
        )

    def append_assessment(
        self,
        _principal: ReviewerPrincipal,
        _review_case_id: UUID,
        _command: object,
        *,
        idempotency_key: str,
    ) -> ConfidenceAssessmentResult | None:
        self.last_key = idempotency_key
        if self.missing:
            return None
        return ConfidenceAssessmentResult.model_validate(
            {
                "confidence_assessment_id": ASSESSMENT_ID,
                "review_case_id": CASE_ID,
                "review_case_version": 1,
                "evidence_complete": True,
                "confidence_band": "HIGH",
                "risk_level": "NORMAL",
                "conflict": False,
                "evidence_ref_ids": [EVIDENCE_ID],
                "rationale": "合成审核：证据完整。",
                "created_at": NOW,
            }
        )

    def append_adjudication(
        self,
        _principal: ReviewerPrincipal,
        _review_case_id: UUID,
        _command: object,
        *,
        idempotency_key: str,
    ) -> FeedbackAdjudicationResult | None:
        self.last_key = idempotency_key
        if self.conflict:
            raise ReviewIdempotencyConflict("sensitive token and SQL")
        if self.missing:
            return None
        return FeedbackAdjudicationResult.model_validate(
            {
                "feedback_adjudication_id": ADJUDICATION_ID,
                "review_case_id": CASE_ID,
                "review_case_version": 1,
                "confidence_assessment_id": ASSESSMENT_ID,
                "decision": "CONFIRMED",
                "evidence_ref_ids": [EVIDENCE_ID],
                "reason": "合成裁决：确认解释问题。",
                "created_at": NOW,
                "resulting_case_version": 2,
            }
        )

    def create_label(
        self,
        _principal: ReviewerPrincipal,
        _review_case_id: UUID,
        _command: object,
        *,
        idempotency_key: str,
    ) -> ApprovedLabelResult | None:
        self.last_key = idempotency_key
        if self.missing:
            return None
        return ApprovedLabelResult.model_validate(
            {
                "approved_feedback_label_id": LABEL_ID,
                "feedback_event_id": EVENT_ID,
                "feedback_adjudication_id": ADJUDICATION_ID,
                "claim_kind": "EXPLANATION_UNCLEAR",
                "approved_target_value": "解释应明确显示官方证据入口。",
                "evidence_ref_ids": [EVIDENCE_ID],
                "evidence_class": "SYNTHETIC_FEEDBACK_WORKFLOW_ONLY",
                "created_at": NOW,
            }
        )


@pytest.fixture
def api_client() -> Iterator[tuple[TestClient, FakeReviewService]]:
    application = create_app()
    service = FakeReviewService()
    application.dependency_overrides[require_reviewer_principal] = lambda: principal(
        ReviewerRole.FEEDBACK_REVIEWER,
        ReviewerRole.FEEDBACK_ADJUDICATOR,
        ReviewerRole.LABEL_CURATOR,
    )
    application.dependency_overrides[get_review_service] = lambda: service
    with TestClient(application) as client:
        yield client, service
    application.dependency_overrides.clear()


def assessment_body() -> dict[str, object]:
    return {
        "evidence_complete": True,
        "confidence_band": "HIGH",
        "risk_level": "NORMAL",
        "conflict": False,
        "evidence_ref_ids": [str(EVIDENCE_ID)],
        "rationale": "合成审核：证据完整。",
    }


def adjudication_body() -> dict[str, object]:
    return {
        "confidence_assessment_id": str(ASSESSMENT_ID),
        "decision": "CONFIRMED",
        "evidence_ref_ids": [str(EVIDENCE_ID)],
        "reason": "合成裁决：确认解释问题。",
    }


def label_body() -> dict[str, object]:
    return {
        "feedback_adjudication_id": str(ADJUDICATION_ID),
        "approved_target_value": "解释应明确显示官方证据入口。",
        "evidence_ref_ids": [str(EVIDENCE_ID)],
    }


def test_review_queue_and_case_are_minimal_private_projections(
    api_client: tuple[TestClient, FakeReviewService],
) -> None:
    client, _service = api_client

    queue = client.get("/api/v1/review/feedback")
    case = client.get(f"/api/v1/review/feedback/{CASE_ID}")

    assert queue.status_code == case.status_code == 200
    for response in (queue, case):
        assert response.headers["cache-control"] == "private, no-store"
        serialized = response.text.lower()
        for forbidden in ("owner_user_id", "token", "session", "email", "phone"):
            assert forbidden not in serialized


def test_each_review_write_requires_one_idempotency_key_and_no_actor_identity(
    api_client: tuple[TestClient, FakeReviewService],
) -> None:
    client, service = api_client
    requests = (
        ("assessments", assessment_body()),
        ("adjudications", adjudication_body()),
        ("labels", label_body()),
    )

    for index, (suffix, body) in enumerate(requests, start=1):
        key = f"phase7-review-write-{index:04d}"
        response = client.post(
            f"/api/v1/review/feedback/{CASE_ID}/{suffix}",
            headers={"Idempotency-Key": key},
            json=body,
        )
        missing_key = client.post(
            f"/api/v1/review/feedback/{CASE_ID}/{suffix}",
            json=body,
        )
        forged = client.post(
            f"/api/v1/review/feedback/{CASE_ID}/{suffix}",
            headers={"Idempotency-Key": f"phase7-review-forged-{index:04d}"},
            json={**body, "reviewer_id": str(REVIEWER_ID)},
        )

        assert response.status_code == 201
        assert response.headers["cache-control"] == "private, no-store"
        assert service.last_key == key
        assert missing_key.status_code == forged.status_code == 400
        assert missing_key.headers["cache-control"] == "private, no-store"


def test_role_denial_precedes_case_lookup_and_unknown_cases_are_identical_private_404(
    api_client: tuple[TestClient, FakeReviewService],
) -> None:
    client, service = api_client
    service.missing = True
    unknown_id = UUID("019b0000-0000-7000-8000-000000000799")

    missing = client.get(f"/api/v1/review/feedback/{CASE_ID}")
    unknown = client.get(f"/api/v1/review/feedback/{unknown_id}")
    assert missing.status_code == unknown.status_code == 404
    assert missing.content == unknown.content
    assert missing.headers["cache-control"] == "private, no-store"

    application = create_app()
    application.dependency_overrides[require_reviewer_principal] = lambda: principal(
        ReviewerRole.FEEDBACK_REVIEWER
    )
    application.dependency_overrides[get_review_service] = lambda: service
    with TestClient(application) as denied_client:
        known_denied = denied_client.post(
            f"/api/v1/review/feedback/{CASE_ID}/adjudications",
            headers={"Idempotency-Key": "phase7-review-denied-0001"},
            json=adjudication_body(),
        )
        unknown_denied = denied_client.post(
            f"/api/v1/review/feedback/{unknown_id}/adjudications",
            headers={"Idempotency-Key": "phase7-review-denied-0002"},
            json=adjudication_body(),
        )
    assert known_denied.status_code == unknown_denied.status_code == 403
    assert known_denied.content == unknown_denied.content


def test_review_conflict_and_invalid_shape_do_not_leak_internal_detail(
    api_client: tuple[TestClient, FakeReviewService],
) -> None:
    client, service = api_client
    service.conflict = True

    conflict = client.post(
        f"/api/v1/review/feedback/{CASE_ID}/adjudications",
        headers={"Idempotency-Key": "phase7-review-conflict-0001"},
        json=adjudication_body(),
    )
    invalid = client.post(
        f"/api/v1/review/feedback/{CASE_ID}/assessments",
        headers={"Idempotency-Key": "phase7-review-invalid-0001"},
        json={**assessment_body(), "rationale": ""},
    )

    assert conflict.status_code == 409
    assert invalid.status_code == 400
    for response in (conflict, invalid):
        assert response.headers["cache-control"] == "private, no-store"
        assert "sensitive" not in response.text.lower()
        assert "sql" not in response.text.lower()
        assert "token" not in response.text.lower()
