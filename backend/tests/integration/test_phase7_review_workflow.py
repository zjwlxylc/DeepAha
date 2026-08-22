from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.api.review import get_review_service
from deepaha.core.settings import get_settings
from deepaha.main import create_app
from deepaha.review.auth import ReviewerRole
from deepaha.review.models import (
    ApprovedFeedbackLabelModel,
    FeedbackAdjudicationModel,
    FeedbackConfidenceAssessmentModel,
    FeedbackReviewCaseSnapshotModel,
    ReviewerIdempotencyRecordModel,
)
from deepaha.review.service import ReviewService
from tests.feedback.support import (
    persist_feedback_prerequisites,
    protected_fact_digest,
    submission_body,
)
from tests.review.support import persist_reviewer

pytestmark = pytest.mark.integration
REVIEWER_TOKEN = "phase7-reviewer-all-roles-token"
OVERDUE_REVIEW_TIME = datetime(2090, 8, 22, 12, 0, tzinfo=UTC)


def test_feedback_is_assessed_adjudicated_and_curated_without_online_mutation(
    migrated_engine: Engine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(migrated_engine) as session:
        owner, _ = persist_feedback_prerequisites(session)
        persist_reviewer(
            session,
            index=1,
            token=REVIEWER_TOKEN,
            roles=tuple(ReviewerRole),
        )
        before = protected_fact_digest(session)
        session.commit()
    monkeypatch.setenv("DEEPAHA_ENVIRONMENT", "test")
    monkeypatch.setenv("DEEPAHA_PERSONAL_AUTH_MODE", "fixture")
    monkeypatch.setenv("DEEPAHA_REVIEWER_AUTH_MODE", "fixture")
    monkeypatch.setenv("DEEPAHA_DATABASE_URL", database_url)
    monkeypatch.setenv("DEEPAHA_OBJECT_STORE_ENDPOINT", "http://127.0.0.1:55005")
    get_settings.cache_clear()
    user_headers = {"Authorization": f"Bearer {owner.token}"}
    review_headers = {"Authorization": f"Bearer {REVIEWER_TOKEN}"}
    application = create_app()
    application.dependency_overrides[get_review_service] = lambda: ReviewService(
        session_factory=sessionmaker(bind=migrated_engine, expire_on_commit=False),
        now_factory=lambda: OVERDUE_REVIEW_TIME,
    )
    try:
        with TestClient(application) as client:
            submitted = client.post(
                f"/api/v1/me/opportunities/{owner.opportunity_public_id}/feedback",
                headers={
                    **user_headers,
                    "Idempotency-Key": "phase7-review-workflow-submit-0001",
                },
                json=submission_body(owner),
            )
            event_id = submitted.json()["feedback"]["feedback_event_id"]
            queue = client.get("/api/v1/review/feedback", headers=review_headers)
            case_id = queue.json()["items"][0]["review_case_id"]
            case = client.get(
                f"/api/v1/review/feedback/{case_id}",
                headers=review_headers,
            )
            assessment_body = {
                "evidence_complete": True,
                "confidence_band": "HIGH",
                "risk_level": "NORMAL",
                "conflict": False,
                "evidence_ref_ids": [str(owner.evidence_ref_id)],
                "rationale": "合成审核：原解释未呈现已绑定的官方证据位置。",
            }
            assessment_headers = {
                **review_headers,
                "Idempotency-Key": "phase7-review-workflow-assess-0001",
            }
            assessed = client.post(
                f"/api/v1/review/feedback/{case_id}/assessments",
                headers=assessment_headers,
                json=assessment_body,
            )
            assessment_replay = client.post(
                f"/api/v1/review/feedback/{case_id}/assessments",
                headers=assessment_headers,
                json=assessment_body,
            )
            assessment_id = assessed.json()["confidence_assessment_id"]
            adjudication_body = {
                "confidence_assessment_id": assessment_id,
                "decision": "CONFIRMED",
                "evidence_ref_ids": [str(owner.evidence_ref_id)],
                "reason": "合成裁决：确认解释清晰度问题，未改变资格结论。",
            }
            adjudication_headers = {
                **review_headers,
                "Idempotency-Key": "phase7-review-workflow-adjudicate-0001",
            }
            adjudicated = client.post(
                f"/api/v1/review/feedback/{case_id}/adjudications",
                headers=adjudication_headers,
                json=adjudication_body,
            )
            adjudication_replay = client.post(
                f"/api/v1/review/feedback/{case_id}/adjudications",
                headers=adjudication_headers,
                json=adjudication_body,
            )
            adjudication_id = adjudicated.json()["feedback_adjudication_id"]
            label_body = {
                "feedback_adjudication_id": adjudication_id,
                "approved_target_value": "解释应明确显示官方证据入口和仍不确定的条件。",
                "evidence_ref_ids": [str(owner.evidence_ref_id)],
            }
            label_headers = {
                **review_headers,
                "Idempotency-Key": "phase7-review-workflow-label-0001",
            }
            labeled = client.post(
                f"/api/v1/review/feedback/{case_id}/labels",
                headers=label_headers,
                json=label_body,
            )
            label_replay = client.post(
                f"/api/v1/review/feedback/{case_id}/labels",
                headers=label_headers,
                json=label_body,
            )
            user_status = client.get(
                f"/api/v1/me/feedback/{event_id}",
                headers=user_headers,
            )
            final_case = client.get(
                f"/api/v1/review/feedback/{case_id}",
                headers=review_headers,
            )
            final_queue = client.get("/api/v1/review/feedback", headers=review_headers)
    finally:
        get_settings.cache_clear()

    assert submitted.status_code == 201
    assert queue.status_code == case.status_code == 200
    assert len(queue.json()["items"]) == 1
    assert case.json()["case"]["overdue"] is True
    assert case.json()["case"]["opportunity_public_id"] == owner.opportunity_public_id
    assert case.json()["match_snapshot_id"] == str(owner.match_snapshot_id)
    assert [item["status"] for item in case.json()["history"]] == ["RECEIVED"]
    assert case.json()["evidence"][0]["evidence_ref_id"] == str(owner.evidence_ref_id)
    assert case.json()["evidence"][0]["actor_kind"] == "USER"
    assert assessed.status_code == adjudicated.status_code == labeled.status_code == 201
    assert assessed.content == assessment_replay.content
    assert adjudicated.content == adjudication_replay.content
    assert labeled.content == label_replay.content
    assert adjudicated.json()["resulting_case_version"] == 2
    assert labeled.json()["evidence_class"] == "SYNTHETIC_FEEDBACK_WORKFLOW_ONLY"
    assert user_status.status_code == final_case.status_code == final_queue.status_code == 200
    assert user_status.json()["feedback"]["status"] == "CONFIRMED"
    assert final_case.json()["case"]["status"] == "CONFIRMED"
    assert [item["status"] for item in final_case.json()["history"]] == [
        "RECEIVED",
        "CONFIRMED",
    ]
    assert final_queue.json()["items"] == []
    serialized_user = user_status.text.lower()
    for forbidden in ("reviewer", "confidence", "risk", "adjudicat", "owner_user_id"):
        assert forbidden not in serialized_user
    for response in (
        submitted,
        queue,
        case,
        assessed,
        adjudicated,
        labeled,
        user_status,
        final_case,
        final_queue,
    ):
        assert response.headers["cache-control"] == "private, no-store"

    with Session(migrated_engine) as session:
        assert protected_fact_digest(session) == before
        assert (
            session.scalar(select(func.count()).select_from(FeedbackConfidenceAssessmentModel)) == 1
        )
        assert session.scalar(select(func.count()).select_from(FeedbackAdjudicationModel)) == 1
        assert session.scalar(select(func.count()).select_from(ApprovedFeedbackLabelModel)) == 1
        assert (
            session.scalar(select(func.count()).select_from(FeedbackReviewCaseSnapshotModel)) == 2
        )
        assert session.scalar(select(func.count()).select_from(ReviewerIdempotencyRecordModel)) == 3
        label = session.get(
            ApprovedFeedbackLabelModel,
            UUID(labeled.json()["approved_feedback_label_id"]),
        )
        assert label is not None
        assert label.match_snapshot_id == owner.match_snapshot_id
        assert label.opportunity_version == owner.opportunity_version
        assert label.evidence_ref_ids == [str(owner.evidence_ref_id)]


def test_confirmed_and_label_preconditions_fail_closed(
    migrated_engine: Engine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(migrated_engine) as session:
        owner, _ = persist_feedback_prerequisites(session)
        persist_reviewer(
            session,
            index=2,
            token=REVIEWER_TOKEN,
            roles=tuple(ReviewerRole),
        )
        session.commit()
    monkeypatch.setenv("DEEPAHA_ENVIRONMENT", "test")
    monkeypatch.setenv("DEEPAHA_PERSONAL_AUTH_MODE", "fixture")
    monkeypatch.setenv("DEEPAHA_REVIEWER_AUTH_MODE", "fixture")
    monkeypatch.setenv("DEEPAHA_DATABASE_URL", database_url)
    get_settings.cache_clear()
    review_headers = {"Authorization": f"Bearer {REVIEWER_TOKEN}"}
    try:
        with TestClient(create_app()) as client:
            submitted = client.post(
                f"/api/v1/me/opportunities/{owner.opportunity_public_id}/feedback",
                headers={
                    "Authorization": f"Bearer {owner.token}",
                    "Idempotency-Key": "phase7-review-preconditions-submit-0001",
                },
                json=submission_body(owner),
            )
            queue = client.get("/api/v1/review/feedback", headers=review_headers)
            case_id = queue.json()["items"][0]["review_case_id"]
            assessed = client.post(
                f"/api/v1/review/feedback/{case_id}/assessments",
                headers={
                    **review_headers,
                    "Idempotency-Key": "phase7-review-preconditions-assess-0001",
                },
                json={
                    "evidence_complete": False,
                    "confidence_band": "LOW",
                    "risk_level": "NORMAL",
                    "conflict": False,
                    "evidence_ref_ids": [],
                    "rationale": "合成审核：当前证据不足。",
                },
            )
            assessment_id = assessed.json()["confidence_assessment_id"]
            invalid_confirm = client.post(
                f"/api/v1/review/feedback/{case_id}/adjudications",
                headers={
                    **review_headers,
                    "Idempotency-Key": "phase7-review-preconditions-confirm-0001",
                },
                json={
                    "confidence_assessment_id": assessment_id,
                    "decision": "CONFIRMED",
                    "evidence_ref_ids": [str(owner.evidence_ref_id)],
                    "reason": "不应确认。",
                },
            )
            invalid_label = client.post(
                f"/api/v1/review/feedback/{case_id}/labels",
                headers={
                    **review_headers,
                    "Idempotency-Key": "phase7-review-preconditions-label-0001",
                },
                json={
                    "feedback_adjudication_id": "019b0000-0000-7000-8000-000000000799",
                    "approved_target_value": "不应创建标签。",
                    "evidence_ref_ids": [str(owner.evidence_ref_id)],
                },
            )
    finally:
        get_settings.cache_clear()

    assert submitted.status_code == 201
    assert assessed.status_code == 201
    assert invalid_confirm.status_code == invalid_label.status_code == 404
    assert invalid_confirm.content == invalid_label.content
    with Session(migrated_engine) as session:
        assert session.scalar(select(func.count()).select_from(FeedbackAdjudicationModel)) == 0
        assert session.scalar(select(func.count()).select_from(ApprovedFeedbackLabelModel)) == 0
