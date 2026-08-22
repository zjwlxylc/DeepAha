from datetime import timedelta
from secrets import token_urlsafe

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from deepaha.core.settings import get_settings
from deepaha.main import create_app
from deepaha.personal.auth import token_digest
from deepaha.personal.models import PersonalAuthSessionModel
from tests.integration.test_phase6_personal_match_replay import persist_public_rule_sets
from tests.integration.test_phase6_profile_persistence import (
    NOW,
    TOKEN_A,
    USER_B_ID,
    profile_command,
    seed_users,
)
from tests.public_catalog.support import persist_phase5_fixture

pytestmark = pytest.mark.integration
UNKNOWN_PUBLIC_ID = "opp_00000000000000000000000000000000"


def test_personal_api_vertical_flow_is_private_and_owner_scoped(
    migrated_engine: Engine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_users(migrated_engine)
    token_b = token_urlsafe(32)
    with Session(migrated_engine) as session:
        public_ids = persist_phase5_fixture(session)
        persist_public_rule_sets(session)
        session.add(
            PersonalAuthSessionModel(
                token_sha256=token_digest(token_b),
                user_id=USER_B_ID,
                expires_at=NOW + timedelta(days=1),
                revoked_at=None,
                created_at=NOW,
            )
        )
        session.commit()
    public_id = public_ids[0]
    monkeypatch.setenv("DEEPAHA_ENVIRONMENT", "test")
    monkeypatch.setenv("DEEPAHA_PERSONAL_AUTH_MODE", "fixture")
    monkeypatch.setenv("DEEPAHA_DATABASE_URL", database_url)
    monkeypatch.setenv("DEEPAHA_OBJECT_STORE_ENDPOINT", "http://127.0.0.1:55004")
    get_settings.cache_clear()
    application = create_app()
    auth_a = {"Authorization": f"Bearer {TOKEN_A}"}
    auth_b = {"Authorization": f"Bearer {token_b}"}

    try:
        with TestClient(application) as client:
            unauthenticated = client.get("/api/v1/me/profile")
            profile = client.put(
                "/api/v1/me/profile",
                headers={**auth_a, "Idempotency-Key": "profile-api-request-0001"},
                json=profile_command().model_dump(mode="json"),
            )
            matches = client.post("/api/v1/me/matches", headers=auth_a)
            priorities = client.get("/api/v1/me/opportunities", headers=auth_a)
            detail = client.get(
                f"/api/v1/me/opportunities/{public_id}",
                headers=auth_a,
            )
            saved = client.put(
                f"/api/v1/me/opportunities/{public_id}/saved",
                headers={**auth_a, "Idempotency-Key": "saved-api-request-0001"},
                json={"saved": True},
            )
            status = client.put(
                f"/api/v1/me/opportunities/{public_id}/status",
                headers={**auth_a, "Idempotency-Key": "status-api-request-0001"},
                json={"state": "PREPARING"},
            )
            materials = client.put(
                f"/api/v1/me/opportunities/{public_id}/materials",
                headers={
                    **auth_a,
                    "Idempotency-Key": "materials-api-request-0001",
                },
                json={
                    "items": [
                        {
                            "material_item_id": ("019b0000-0000-7000-8000-000000000901"),
                            "label": "合成报名表",
                            "completed": False,
                            "due_on": None,
                        }
                    ]
                },
            )
            official = client.post(
                f"/api/v1/me/opportunities/{public_id}/official-link",
                headers={
                    **auth_a,
                    "Idempotency-Key": "official-link-api-request-0001",
                },
            )
            official_replay = client.post(
                f"/api/v1/me/opportunities/{public_id}/official-link",
                headers={
                    **auth_a,
                    "Idempotency-Key": "official-link-api-request-0001",
                },
            )
            action = client.get(
                f"/api/v1/me/opportunities/{public_id}/action",
                headers=auth_a,
            )
            other_owner = client.get(
                f"/api/v1/me/opportunities/{public_id}/action",
                headers=auth_b,
            )
            unknown = client.get(
                f"/api/v1/me/opportunities/{UNKNOWN_PUBLIC_ID}/action",
                headers=auth_b,
            )
            invalid_identity = client.put(
                f"/api/v1/me/opportunities/{public_id}/saved",
                headers={**auth_a, "Idempotency-Key": "saved-api-request-0002"},
                json={"saved": False, "user_id": str(USER_B_ID)},
            )
    finally:
        get_settings.cache_clear()

    assert unauthenticated.status_code == 401
    assert profile.status_code == 200
    assert matches.status_code == 200
    assert len(matches.json()["items"]) == 2
    assert priorities.status_code == 200
    assert len(priorities.json()["items"]) == 2
    assert detail.status_code == 200
    assert detail.json()["opportunity"]["public_id"] == public_id
    assert detail.json()["eligibility"]["eligibility_result"]["status"] == "ELIGIBLE"
    assert detail.json()["opportunity"]["key_evidence"]
    assert detail.json()["opportunity"]["application_url"].startswith("https://")
    assert saved.status_code == 200
    assert status.status_code == 200
    assert status.json()["state"] == "PREPARING"
    assert materials.status_code == 200
    assert materials.json()["material_items"][0]["label"] == "合成报名表"
    assert official.status_code == 200
    assert official.json() == official_replay.json()
    assert official.json()["official_url"].startswith("https://phase5-fixture.example.test/")
    assert action.status_code == 200
    assert action.json()["saved"] is True
    assert (other_owner.status_code, other_owner.json()) == (
        unknown.status_code,
        unknown.json(),
    )
    assert other_owner.status_code == 404
    assert invalid_identity.status_code == 400
    for response in (
        unauthenticated,
        profile,
        matches,
        priorities,
        detail,
        saved,
        status,
        materials,
        official,
        official_replay,
        action,
        other_owner,
        unknown,
        invalid_identity,
    ):
        assert response.headers["cache-control"] == "private, no-store"
    serialized = f"{matches.text}\n{priorities.text}\n{detail.text}".lower()
    for forbidden in (
        "match_percentage",
        "matching_percentage",
        "model_confidence",
        "feedback",
        "reminder",
        "notification",
    ):
        assert forbidden not in serialized
