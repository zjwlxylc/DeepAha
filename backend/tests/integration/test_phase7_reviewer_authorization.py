from uuid import uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from deepaha.core.settings import get_settings
from deepaha.main import create_app
from deepaha.review.auth import ReviewerRole
from tests.feedback.support import persist_feedback_prerequisites, submission_body
from tests.review.support import persist_reviewer

pytestmark = pytest.mark.integration
REVIEW_TOKEN = "phase7-review-only-token"
ADJUDICATE_TOKEN = "phase7-adjudicate-only-token"
CURATE_TOKEN = "phase7-curate-only-token"


def test_personal_and_reviewer_credentials_are_separate_and_roles_are_per_operation(
    migrated_engine: Engine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(migrated_engine) as session:
        owner, _ = persist_feedback_prerequisites(session)
        persist_reviewer(
            session,
            index=3,
            token=REVIEW_TOKEN,
            roles=(ReviewerRole.FEEDBACK_REVIEWER,),
        )
        persist_reviewer(
            session,
            index=4,
            token=ADJUDICATE_TOKEN,
            roles=(ReviewerRole.FEEDBACK_ADJUDICATOR,),
        )
        persist_reviewer(
            session,
            index=5,
            token=CURATE_TOKEN,
            roles=(ReviewerRole.LABEL_CURATOR,),
        )
        session.commit()
    monkeypatch.setenv("DEEPAHA_ENVIRONMENT", "test")
    monkeypatch.setenv("DEEPAHA_PERSONAL_AUTH_MODE", "fixture")
    monkeypatch.setenv("DEEPAHA_REVIEWER_AUTH_MODE", "fixture")
    monkeypatch.setenv("DEEPAHA_DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            submitted = client.post(
                f"/api/v1/me/opportunities/{owner.opportunity_public_id}/feedback",
                headers={
                    "Authorization": f"Bearer {owner.token}",
                    "Idempotency-Key": "phase7-review-auth-submit-0001",
                },
                json=submission_body(owner),
            )
            event_id = submitted.json()["feedback"]["feedback_event_id"]
            personal_on_review = client.get(
                "/api/v1/review/feedback",
                headers={"Authorization": f"Bearer {owner.token}"},
            )
            reviewer_on_personal = client.get(
                f"/api/v1/me/feedback/{event_id}",
                headers={"Authorization": f"Bearer {REVIEW_TOKEN}"},
            )
            queue = client.get(
                "/api/v1/review/feedback",
                headers={"Authorization": f"Bearer {REVIEW_TOKEN}"},
            )
            case_id = queue.json()["items"][0]["review_case_id"]
            unknown_id = uuid7()
            missing = client.get(
                f"/api/v1/review/feedback/{unknown_id}",
                headers={"Authorization": f"Bearer {REVIEW_TOKEN}"},
            )
            known_review_denied = client.post(
                f"/api/v1/review/feedback/{case_id}/adjudications",
                headers={
                    "Authorization": f"Bearer {REVIEW_TOKEN}",
                    "Idempotency-Key": "phase7-review-auth-denied-0001",
                },
                json={
                    "confidence_assessment_id": str(uuid7()),
                    "decision": "REJECTED",
                    "evidence_ref_ids": [],
                    "reason": "合成拒绝原因。",
                },
            )
            unknown_review_denied = client.post(
                f"/api/v1/review/feedback/{unknown_id}/adjudications",
                headers={
                    "Authorization": f"Bearer {REVIEW_TOKEN}",
                    "Idempotency-Key": "phase7-review-auth-denied-0002",
                },
                json={
                    "confidence_assessment_id": str(uuid7()),
                    "decision": "REJECTED",
                    "evidence_ref_ids": [],
                    "reason": "合成拒绝原因。",
                },
            )
            adjudicator_queue = client.get(
                "/api/v1/review/feedback",
                headers={"Authorization": f"Bearer {ADJUDICATE_TOKEN}"},
            )
            curator_queue = client.get(
                "/api/v1/review/feedback",
                headers={"Authorization": f"Bearer {CURATE_TOKEN}"},
            )
            adjudicator_label = client.post(
                f"/api/v1/review/feedback/{case_id}/labels",
                headers={
                    "Authorization": f"Bearer {ADJUDICATE_TOKEN}",
                    "Idempotency-Key": "phase7-review-auth-denied-0003",
                },
                json={
                    "feedback_adjudication_id": str(uuid7()),
                    "approved_target_value": "不应创建。",
                    "evidence_ref_ids": [str(owner.evidence_ref_id)],
                },
            )
            curator_assessment = client.post(
                f"/api/v1/review/feedback/{case_id}/assessments",
                headers={
                    "Authorization": f"Bearer {CURATE_TOKEN}",
                    "Idempotency-Key": "phase7-review-auth-denied-0004",
                },
                json={
                    "evidence_complete": False,
                    "confidence_band": "LOW",
                    "risk_level": "NORMAL",
                    "conflict": False,
                    "evidence_ref_ids": [],
                    "rationale": "不应评估。",
                },
            )
    finally:
        get_settings.cache_clear()

    assert submitted.status_code == 201
    assert personal_on_review.status_code == reviewer_on_personal.status_code == 401
    assert queue.status_code == 200
    assert missing.status_code == 404
    assert known_review_denied.status_code == unknown_review_denied.status_code == 403
    assert known_review_denied.content == unknown_review_denied.content
    assert adjudicator_queue.status_code == curator_queue.status_code == 403
    assert adjudicator_queue.content == curator_queue.content
    assert adjudicator_label.status_code == curator_assessment.status_code == 403
    for response in (
        personal_on_review,
        reviewer_on_personal,
        queue,
        missing,
        known_review_denied,
        unknown_review_denied,
        adjudicator_queue,
        curator_queue,
        adjudicator_label,
        curator_assessment,
    ):
        assert response.headers["cache-control"] == "private, no-store"
        serialized = response.text.lower()
        for forbidden in ("owner_user_id", "token_sha256", "session", "sql"):
            assert forbidden not in serialized
