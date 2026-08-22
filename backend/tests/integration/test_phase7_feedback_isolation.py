from uuid import uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from deepaha.core.settings import get_settings
from deepaha.feedback.models import FeedbackEventModel
from deepaha.main import create_app
from tests.feedback.support import persist_feedback_prerequisites, submission_body

pytestmark = pytest.mark.integration


def test_user_cannot_submit_read_or_supplement_another_owners_feedback(
    migrated_engine: Engine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(migrated_engine) as session:
        owner_a, owner_b = persist_feedback_prerequisites(session)
        session.commit()
    monkeypatch.setenv("DEEPAHA_ENVIRONMENT", "test")
    monkeypatch.setenv("DEEPAHA_PERSONAL_AUTH_MODE", "fixture")
    monkeypatch.setenv("DEEPAHA_DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            created = client.post(
                f"/api/v1/me/opportunities/{owner_a.opportunity_public_id}/feedback",
                headers={
                    "Authorization": f"Bearer {owner_a.token}",
                    "Idempotency-Key": "phase7-isolation-submit-a-0001",
                },
                json=submission_body(owner_a),
            )
            event_id = created.json()["feedback"]["feedback_event_id"]
            unknown_id = uuid7()
            owner_b_auth = {"Authorization": f"Bearer {owner_b.token}"}
            other = client.get(
                f"/api/v1/me/feedback/{event_id}",
                headers=owner_b_auth,
            )
            unknown = client.get(
                f"/api/v1/me/feedback/{unknown_id}",
                headers=owner_b_auth,
            )
            other_append = client.post(
                f"/api/v1/me/feedback/{event_id}/evidence",
                headers={
                    **owner_b_auth,
                    "Idempotency-Key": "phase7-isolation-evidence-b-0001",
                },
                json={
                    "evidence_ref_id": str(owner_b.evidence_ref_id),
                    "relation": "SUPPORTS",
                    "note": None,
                },
            )
            unknown_append = client.post(
                f"/api/v1/me/feedback/{unknown_id}/evidence",
                headers={
                    **owner_b_auth,
                    "Idempotency-Key": "phase7-isolation-evidence-b-0002",
                },
                json={
                    "evidence_ref_id": str(owner_b.evidence_ref_id),
                    "relation": "SUPPORTS",
                    "note": None,
                },
            )
            forged_ranking = client.post(
                f"/api/v1/me/opportunities/{owner_a.opportunity_public_id}/feedback",
                headers={
                    **owner_b_auth,
                    "Idempotency-Key": "phase7-isolation-submit-b-0001",
                },
                json=submission_body(owner_a),
            )
            forged_identity = client.post(
                f"/api/v1/me/opportunities/{owner_b.opportunity_public_id}/feedback",
                headers={
                    **owner_b_auth,
                    "Idempotency-Key": "phase7-isolation-submit-b-0002",
                },
                json=submission_body(owner_b, owner_user_id=str(owner_a.user_id)),
            )
    finally:
        get_settings.cache_clear()

    assert created.status_code == 201
    assert other.status_code == unknown.status_code == 404
    assert other.content == unknown.content
    assert other_append.status_code == unknown_append.status_code == 404
    assert other_append.content == unknown_append.content == other.content
    assert forged_ranking.status_code == 404
    assert forged_identity.status_code == 400
    for response in (other, unknown, other_append, unknown_append, forged_ranking):
        assert response.headers["cache-control"] == "private, no-store"
        serialized = response.text.lower()
        for forbidden in ("owner", "user_id", "reviewer", "token", "sql"):
            assert forbidden not in serialized

    with Session(migrated_engine) as session:
        assert session.scalar(select(func.count()).select_from(FeedbackEventModel)) == 1
        event = session.scalar(select(FeedbackEventModel))
        assert event is not None
        assert event.owner_user_id == owner_a.user_id
