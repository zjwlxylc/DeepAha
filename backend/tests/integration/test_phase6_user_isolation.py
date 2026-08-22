import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from deepaha.core.settings import get_settings
from deepaha.main import create_app
from tests.personal.support import persist_phase6_fixture

pytestmark = pytest.mark.integration
UNKNOWN_PUBLIC_ID = "opp_00000000000000000000000000000000"


def test_user_id_forgery_cannot_cross_personal_boundary(
    migrated_engine: Engine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(migrated_engine) as session:
        identity = persist_phase6_fixture(session)
        session.commit()
    monkeypatch.setenv("DEEPAHA_ENVIRONMENT", "test")
    monkeypatch.setenv("DEEPAHA_PERSONAL_AUTH_MODE", "fixture")
    monkeypatch.setenv("DEEPAHA_DATABASE_URL", database_url)
    monkeypatch.setenv("DEEPAHA_OBJECT_STORE_ENDPOINT", "http://127.0.0.1:55004")
    get_settings.cache_clear()
    application = create_app()
    auth_a = {"Authorization": f"Bearer {identity.token_a}"}
    auth_b = {"Authorization": f"Bearer {identity.token_b}"}
    try:
        with TestClient(application) as client:
            for auth, profile, key in (
                (auth_a, identity.profile_a, "phase6-isolation-profile-a"),
                (auth_b, identity.profile_b, "phase6-isolation-profile-b"),
            ):
                response = client.put(
                    "/api/v1/me/profile",
                    headers={**auth, "Idempotency-Key": key},
                    json=profile.model_dump(mode="json"),
                )
                assert response.status_code == 200
                assert client.post("/api/v1/me/matches", headers=auth).status_code == 200
            priorities_a = client.get("/api/v1/me/opportunities", headers=auth_a)
            public_id = priorities_a.json()["items"][0]["opportunity"]["public_id"]
            saved_a = client.put(
                f"/api/v1/me/opportunities/{public_id}/saved",
                headers={**auth_a, "Idempotency-Key": "phase6-isolation-saved-a"},
                json={"saved": True},
            )
            forged_read = client.get(
                f"/api/v1/me/opportunities/{public_id}/action",
                headers=auth_a,
                params={"user_id": str(identity.user_b_id)},
            )
            other_owner = client.get(
                f"/api/v1/me/opportunities/{public_id}/action",
                headers=auth_b,
            )
            unknown = client.get(
                f"/api/v1/me/opportunities/{UNKNOWN_PUBLIC_ID}/action",
                headers=auth_b,
            )
            detail_b = client.get(
                f"/api/v1/me/opportunities/{public_id}",
                headers=auth_b,
            )
            forged_write = client.put(
                f"/api/v1/me/opportunities/{public_id}/saved",
                headers={**auth_a, "Idempotency-Key": "phase6-isolation-forged-write"},
                json={"saved": False, "user_id": str(identity.user_b_id)},
            )
    finally:
        get_settings.cache_clear()

    assert saved_a.status_code == 200
    assert forged_read.status_code == 200
    assert forged_read.json()["saved"] is True
    assert "user_id" not in forged_read.text
    assert (other_owner.status_code, other_owner.json()) == (
        unknown.status_code,
        unknown.json(),
    )
    assert other_owner.status_code == 404
    assert detail_b.status_code == 200
    assert detail_b.json()["eligibility"]["eligibility_result"]["status"] == "UNCERTAIN"
    assert detail_b.json()["action"] is None
    assert forged_write.status_code == 400
    for response in (saved_a, forged_read, other_owner, unknown, detail_b, forged_write):
        assert response.headers["cache-control"] == "private, no-store"
