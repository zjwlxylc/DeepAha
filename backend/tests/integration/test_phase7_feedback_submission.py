from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from deepaha.core.settings import get_settings
from deepaha.feedback.models import (
    FeedbackEventModel,
    FeedbackEvidenceLinkModel,
    FeedbackIdempotencyRecordModel,
)
from deepaha.main import create_app
from deepaha.personal.models import UserStateSnapshotModel
from deepaha.review.models import FeedbackReviewCaseSnapshotModel
from tests.feedback.support import (
    NOW,
    persist_feedback_prerequisites,
    protected_fact_digest,
    submission_body,
)

pytestmark = pytest.mark.integration


def test_feedback_submission_is_atomic_idempotent_version_bound_and_non_mutating(
    migrated_engine: Engine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(migrated_engine) as session:
        owner, _ = persist_feedback_prerequisites(session)
        before = protected_fact_digest(session)
        session.commit()
    monkeypatch.setenv("DEEPAHA_ENVIRONMENT", "test")
    monkeypatch.setenv("DEEPAHA_PERSONAL_AUTH_MODE", "fixture")
    monkeypatch.setenv("DEEPAHA_DATABASE_URL", database_url)
    monkeypatch.setenv("DEEPAHA_OBJECT_STORE_ENDPOINT", "http://127.0.0.1:55005")
    get_settings.cache_clear()
    headers = {
        "Authorization": f"Bearer {owner.token}",
        "Idempotency-Key": "phase7-feedback-submit-0001",
    }
    try:
        with TestClient(create_app()) as client:
            submitted = client.post(
                f"/api/v1/me/opportunities/{owner.opportunity_public_id}/feedback",
                headers=headers,
                json=submission_body(owner),
            )
            replay = client.post(
                f"/api/v1/me/opportunities/{owner.opportunity_public_id}/feedback",
                headers=headers,
                json=submission_body(owner),
            )
            conflict = client.post(
                f"/api/v1/me/opportunities/{owner.opportunity_public_id}/feedback",
                headers=headers,
                json=submission_body(owner, user_statement="合成的不同反馈。"),
            )
            feedback_event_id = submitted.json()["feedback"]["feedback_event_id"]
            listed = client.get(
                "/api/v1/me/feedback",
                headers={"Authorization": f"Bearer {owner.token}"},
            )
            loaded = client.get(
                f"/api/v1/me/feedback/{feedback_event_id}",
                headers={"Authorization": f"Bearer {owner.token}"},
            )
            appended = client.post(
                f"/api/v1/me/feedback/{feedback_event_id}/evidence",
                headers={
                    "Authorization": f"Bearer {owner.token}",
                    "Idempotency-Key": "phase7-feedback-evidence-0001",
                },
                json={
                    "evidence_ref_id": str(owner.evidence_ref_id),
                    "relation": "CONTRADICTS",
                    "note": "合成证据补充。",
                },
            )
            invalid_evidence = client.post(
                f"/api/v1/me/opportunities/{owner.opportunity_public_id}/feedback",
                headers={
                    "Authorization": f"Bearer {owner.token}",
                    "Idempotency-Key": "phase7-feedback-submit-0002",
                },
                json=submission_body(
                    owner,
                    initial_evidence_ref_ids=["019b0000-0000-7000-8000-000000000799"],
                ),
            )
            stale_version = client.post(
                f"/api/v1/me/opportunities/{owner.opportunity_public_id}/feedback",
                headers={
                    "Authorization": f"Bearer {owner.token}",
                    "Idempotency-Key": "phase7-feedback-submit-0003",
                },
                json=submission_body(owner, opportunity_version=2),
            )
    finally:
        get_settings.cache_clear()

    assert submitted.status_code == 201
    assert submitted.content == replay.content
    assert conflict.status_code == 409
    assert listed.status_code == loaded.status_code == appended.status_code == 200
    assert listed.json()["items"][0]["feedback_event_id"] == feedback_event_id
    assert loaded.json()["feedback"]["status"] == "RECEIVED"
    assert len(appended.json()["evidence"]) == 2
    assert invalid_evidence.status_code == stale_version.status_code == 404
    for response in (submitted, replay, conflict, listed, loaded, appended):
        assert response.headers["cache-control"] == "private, no-store"
    serialized = f"{submitted.text}\n{listed.text}\n{loaded.text}\n{appended.text}".lower()
    for forbidden in ("owner_user_id", "reviewer", "confidence", "token", "sql"):
        assert forbidden not in serialized

    with Session(migrated_engine) as session:
        assert protected_fact_digest(session) == before
        assert session.scalar(select(func.count()).select_from(FeedbackEventModel)) == 1
        assert session.scalar(select(func.count()).select_from(FeedbackEvidenceLinkModel)) == 2
        assert (
            session.scalar(select(func.count()).select_from(FeedbackReviewCaseSnapshotModel)) == 1
        )
        assert session.scalar(select(func.count()).select_from(FeedbackIdempotencyRecordModel)) == 2
        event = session.get(FeedbackEventModel, UUID(feedback_event_id))
        assert event is not None
        assert event.ranking_snapshot_id == owner.ranking_snapshot_id
        assert event.match_snapshot_id == owner.match_snapshot_id
        assert event.opportunity_version == owner.opportunity_version
        assert event.user_state_version == owner.user_state_version


def test_current_purpose_revocation_fails_closed_without_creating_feedback(
    migrated_engine: Engine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(migrated_engine) as session:
        owner, _ = persist_feedback_prerequisites(session)
        current = session.scalar(
            select(UserStateSnapshotModel).where(
                UserStateSnapshotModel.user_id == owner.user_id,
                UserStateSnapshotModel.version == 1,
            )
        )
        assert current is not None
        session.add(
            UserStateSnapshotModel(
                user_state_snapshot_id=UUID("019b0000-0000-7000-8000-000000000798"),
                user_state_id=current.user_state_id,
                user_id=current.user_id,
                version=2,
                qualification_profile_snapshot_id=current.qualification_profile_snapshot_id,
                qualification_profile_version=current.qualification_profile_version,
                life_stage=current.life_stage,
                goal_types=current.goal_types,
                preference_regions=current.preference_regions,
                preference_types=current.preference_types,
                skipped_fields=current.skipped_fields,
                personalization_enabled=current.personalization_enabled,
                consent_version=current.consent_version,
                allowed_purposes=["PERSONAL_RANKING"],
                scenario_clock=current.scenario_clock,
                input_sha256="9" * 64,
                created_at=NOW,
            )
        )
        session.commit()
    monkeypatch.setenv("DEEPAHA_ENVIRONMENT", "test")
    monkeypatch.setenv("DEEPAHA_PERSONAL_AUTH_MODE", "fixture")
    monkeypatch.setenv("DEEPAHA_DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            response = client.post(
                f"/api/v1/me/opportunities/{owner.opportunity_public_id}/feedback",
                headers={
                    "Authorization": f"Bearer {owner.token}",
                    "Idempotency-Key": "phase7-feedback-purpose-0001",
                },
                json=submission_body(owner),
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 404
    with Session(migrated_engine) as session:
        assert session.scalar(select(func.count()).select_from(FeedbackEventModel)) == 0
