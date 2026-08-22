from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from deepaha.core.settings import get_settings
from deepaha.main import create_app
from deepaha.personal.models import PersonalActionEventModel
from tests.personal.seed_phase6_browser import seed_phase6_browser
from tests.personal.support import persist_phase6_fixture


@pytest.mark.integration
def test_phase6_browser_seed_refuses_a_nonempty_database(database_url: str) -> None:
    target = urlparse(database_url)
    if target.hostname != "127.0.0.1" or target.port != 55436 or target.path != "/deepaha":
        pytest.skip("requires the exact disposable Phase 6 database")

    identity = seed_phase6_browser(database_url)

    assert len(identity.public_ids) == 3
    with pytest.raises(RuntimeError, match="empty Phase 6"):
        seed_phase6_browser(database_url)


@pytest.mark.integration
def test_official_to_action_vertical_slice_is_replayable_and_audited(
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
    auth = {"Authorization": f"Bearer {identity.token_a}"}
    try:
        with TestClient(application) as client:
            profile = client.put(
                "/api/v1/me/profile",
                headers={**auth, "Idempotency-Key": "phase6-vertical-profile-0001"},
                json=identity.profile_a.model_dump(mode="json"),
            )
            matches = client.post("/api/v1/me/matches", headers=auth)
            match_replay = client.post("/api/v1/me/matches", headers=auth)
            priorities = client.get("/api/v1/me/opportunities", headers=auth)
            public_id = priorities.json()["items"][0]["opportunity"]["public_id"]
            detail = client.get(f"/api/v1/me/opportunities/{public_id}", headers=auth)
            saved = client.put(
                f"/api/v1/me/opportunities/{public_id}/saved",
                headers={**auth, "Idempotency-Key": "phase6-vertical-saved-0001"},
                json={"saved": True},
            )
            saved_replay = client.put(
                f"/api/v1/me/opportunities/{public_id}/saved",
                headers={**auth, "Idempotency-Key": "phase6-vertical-saved-0001"},
                json={"saved": True},
            )
            status = client.put(
                f"/api/v1/me/opportunities/{public_id}/status",
                headers={**auth, "Idempotency-Key": "phase6-vertical-status-0001"},
                json={"state": "PREPARING"},
            )
            materials = client.put(
                f"/api/v1/me/opportunities/{public_id}/materials",
                headers={**auth, "Idempotency-Key": "phase6-vertical-materials-0001"},
                json={
                    "items": [
                        {
                            "material_item_id": "019b0000-0000-7000-8000-000000000951",
                            "label": "合成报名材料",
                            "completed": False,
                            "due_on": "2026-09-10",
                        }
                    ]
                },
            )
            official = client.post(
                f"/api/v1/me/opportunities/{public_id}/official-link",
                headers={**auth, "Idempotency-Key": "phase6-vertical-official-0001"},
            )
            official_replay = client.post(
                f"/api/v1/me/opportunities/{public_id}/official-link",
                headers={**auth, "Idempotency-Key": "phase6-vertical-official-0001"},
            )
    finally:
        get_settings.cache_clear()

    assert profile.status_code == 200
    assert profile.json()["version"] == 1
    assert matches.status_code == 200
    assert match_replay.json()["ranking_snapshot_id"] == matches.json()["ranking_snapshot_id"]
    assert 0 < len(priorities.json()["items"]) <= 3
    assert detail.status_code == 200
    assert detail.json()["eligibility"]["eligibility_result"]["status"] == "ELIGIBLE"
    assert detail.json()["opportunity"]["key_evidence"]
    assert saved.json() == saved_replay.json()
    assert saved.json()["saved"] is True
    assert status.json()["state"] == "PREPARING"
    assert materials.json()["material_items"][0]["label"] == "合成报名材料"
    assert official.json() == official_replay.json()
    assert urlparse(official.json()["official_url"]).hostname == "phase5-fixture.example.test"
    serialized = f"{matches.text}\n{priorities.text}\n{detail.text}".lower()
    for forbidden in ("match_percentage", "model_confidence", "feedback", "reminder"):
        assert forbidden not in serialized
    with Session(migrated_engine) as session:
        event_count = session.scalar(
            select(func.count())
            .select_from(PersonalActionEventModel)
            .where(PersonalActionEventModel.user_id == identity.user_a_id)
        )
    assert event_count == 4
