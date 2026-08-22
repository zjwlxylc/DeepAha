from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from deepaha.api.feedback import get_feedback_service
from deepaha.api.personal import require_principal
from deepaha.feedback.schemas import (
    FeedbackEvidenceSummary,
    FeedbackStatusDetail,
    FeedbackStatusPage,
    FeedbackStatusSummary,
)
from deepaha.feedback.service import FeedbackIdempotencyConflict
from deepaha.main import create_app
from deepaha.personal.auth import Principal

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
USER_A_ID = UUID("019b0000-0000-7000-8000-000000000711")
FEEDBACK_EVENT_ID = UUID("019b0000-0000-7000-8000-000000000716")
EVIDENCE_LINK_ID = UUID("019b0000-0000-7000-8000-000000000717")
EVIDENCE_REF_ID = UUID("019b0000-0000-7000-8000-000000000714")
RANKING_ID = UUID("019b0000-0000-7000-8000-000000000712")
MATCH_ID = UUID("019b0000-0000-7000-8000-000000000713")
PUBLIC_ID = "opp_0123456789abcdef0123456789abcdef"
UNKNOWN_ID = UUID("019b0000-0000-7000-8000-000000000799")


def summary() -> FeedbackStatusSummary:
    return FeedbackStatusSummary.model_validate(
        {
            "feedback_event_id": FEEDBACK_EVENT_ID,
            "opportunity_public_id": PUBLIC_ID,
            "opportunity_version": 1,
            "event_type": "STRUCTURED_CORRECTION",
            "claim_kind": "EXPLANATION_UNCLEAR",
            "status": "RECEIVED",
            "created_at": NOW,
            "status_updated_at": NOW,
        }
    )


def detail() -> FeedbackStatusDetail:
    return FeedbackStatusDetail(
        feedback=summary(),
        evidence=(
            FeedbackEvidenceSummary.model_validate(
                {
                    "feedback_evidence_link_id": EVIDENCE_LINK_ID,
                    "evidence_ref_id": EVIDENCE_REF_ID,
                    "relation": "SUPPORTS",
                    "note": None,
                    "created_at": NOW,
                }
            ),
        ),
    )


class FakeFeedbackService:
    def __init__(self) -> None:
        self.last_key: str | None = None
        self.conflict = False
        self.missing = False

    def submit(
        self,
        _principal: Principal,
        _public_id: str,
        _command: object,
        *,
        idempotency_key: str,
    ) -> FeedbackStatusDetail:
        if self.conflict:
            raise FeedbackIdempotencyConflict("sensitive SQL and token detail")
        self.last_key = idempotency_key
        return detail()

    def append_evidence(
        self,
        _principal: Principal,
        _feedback_event_id: UUID,
        _command: object,
        *,
        idempotency_key: str,
    ) -> FeedbackStatusDetail | None:
        self.last_key = idempotency_key
        return None if self.missing else detail()

    def list_owned(self, _principal: Principal) -> FeedbackStatusPage:
        return FeedbackStatusPage(items=(summary(),))

    def get_owned(
        self,
        _principal: Principal,
        _feedback_event_id: UUID,
    ) -> FeedbackStatusDetail | None:
        return None if self.missing else detail()


@pytest.fixture
def api_client() -> Iterator[tuple[TestClient, FakeFeedbackService]]:
    application = create_app()
    service = FakeFeedbackService()
    application.dependency_overrides[require_principal] = lambda: Principal(user_id=USER_A_ID)
    application.dependency_overrides[get_feedback_service] = lambda: service
    with TestClient(application) as client:
        yield client, service
    application.dependency_overrides.clear()


def submission_body(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "ranking_snapshot_id": str(RANKING_ID),
        "match_snapshot_id": str(MATCH_ID),
        "opportunity_version": 1,
        "user_state_version": 1,
        "event_type": "STRUCTURED_CORRECTION",
        "claim_kind": "EXPLANATION_UNCLEAR",
        "user_statement": "合成反馈：解释没有指出证据位置。",
        "structured_reason_code": "MISSING_EVIDENCE_EXPLANATION",
        "initial_evidence_ref_ids": [str(EVIDENCE_REF_ID)],
        "consent_version": "phase7-feedback-consent-v1",
        "consent_scope": "FEEDBACK_REVIEW_AND_VALIDATION",
    }
    values.update(changes)
    return values


def test_submit_is_private_rejects_identity_and_requires_exactly_one_key(
    api_client: tuple[TestClient, FakeFeedbackService],
) -> None:
    client, service = api_client

    response = client.post(
        f"/api/v1/me/opportunities/{PUBLIC_ID}/feedback",
        headers={"Idempotency-Key": "phase7-feedback-submit-0001"},
        json=submission_body(),
    )
    missing_key = client.post(
        f"/api/v1/me/opportunities/{PUBLIC_ID}/feedback",
        json=submission_body(),
    )
    forged = client.post(
        f"/api/v1/me/opportunities/{PUBLIC_ID}/feedback",
        headers={"Idempotency-Key": "phase7-feedback-submit-0002"},
        json=submission_body(user_id=str(USER_A_ID)),
    )
    repeated = client.post(
        f"/api/v1/me/opportunities/{PUBLIC_ID}/feedback",
        headers=[
            ("Idempotency-Key", "phase7-feedback-submit-0003"),
            ("Idempotency-Key", "phase7-feedback-submit-0004"),
        ],
        json=submission_body(),
    )

    assert response.status_code == 201
    assert response.headers["cache-control"] == "private, no-store"
    assert service.last_key == "phase7-feedback-submit-0001"
    for invalid in (missing_key, forged, repeated):
        assert invalid.status_code == 400
        assert invalid.headers["cache-control"] == "private, no-store"
    serialized = response.text.lower()
    for forbidden in ("user_id", "reviewer", "confidence", "token", "sql"):
        assert forbidden not in serialized


def test_list_get_and_append_use_owner_safe_private_projection(
    api_client: tuple[TestClient, FakeFeedbackService],
) -> None:
    client, service = api_client

    page = client.get("/api/v1/me/feedback")
    loaded = client.get(f"/api/v1/me/feedback/{FEEDBACK_EVENT_ID}")
    appended = client.post(
        f"/api/v1/me/feedback/{FEEDBACK_EVENT_ID}/evidence",
        headers={"Idempotency-Key": "phase7-feedback-evidence-0001"},
        json={
            "evidence_ref_id": str(EVIDENCE_REF_ID),
            "relation": "SUPPORTS",
            "note": "合成证据补充。",
        },
    )

    assert page.status_code == loaded.status_code == appended.status_code == 200
    assert service.last_key == "phase7-feedback-evidence-0001"
    for response in (page, loaded, appended):
        assert response.headers["cache-control"] == "private, no-store"
        assert "reviewer" not in response.text.lower()
        assert "confidence" not in response.text.lower()


def test_unknown_and_other_owner_feedback_are_byte_identical_404(
    api_client: tuple[TestClient, FakeFeedbackService],
) -> None:
    client, service = api_client
    service.missing = True

    other = client.get(f"/api/v1/me/feedback/{FEEDBACK_EVENT_ID}")
    unknown = client.get(f"/api/v1/me/feedback/{UNKNOWN_ID}")
    other_append = client.post(
        f"/api/v1/me/feedback/{FEEDBACK_EVENT_ID}/evidence",
        headers={"Idempotency-Key": "phase7-feedback-evidence-0002"},
        json={
            "evidence_ref_id": str(EVIDENCE_REF_ID),
            "relation": "SUPPORTS",
            "note": None,
        },
    )

    assert other.status_code == unknown.status_code == other_append.status_code == 404
    assert other.content == unknown.content == other_append.content
    assert other.headers["cache-control"] == "private, no-store"


def test_feedback_idempotency_conflict_does_not_leak_internal_detail(
    api_client: tuple[TestClient, FakeFeedbackService],
) -> None:
    client, service = api_client
    service.conflict = True

    response = client.post(
        f"/api/v1/me/opportunities/{PUBLIC_ID}/feedback",
        headers={"Idempotency-Key": "phase7-feedback-submit-0001"},
        json=submission_body(),
    )

    assert response.status_code == 409
    assert response.headers["cache-control"] == "private, no-store"
    assert "sensitive" not in response.text.lower()
    assert "sql" not in response.text.lower()
    assert "token" not in response.text.lower()
