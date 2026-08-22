from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from deepaha.api.personal import (
    get_action_service,
    get_personal_match_service,
    get_profile_service,
    require_principal,
)
from deepaha.api.personal import router as personal_router
from deepaha.contracts.phase6 import PersonalActionSnapshotSchemaV05
from deepaha.main import create_app
from deepaha.personal.auth import Principal
from deepaha.personal.profile import IdempotencyConflict

NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
USER_A_ID = UUID("019b0000-0000-7000-8000-000000000501")
PUBLIC_ID = "opp_0123456789abcdef0123456789abcdef"
UNKNOWN_PUBLIC_ID = "opp_00000000000000000000000000000000"


def action_snapshot() -> PersonalActionSnapshotSchemaV05:
    return PersonalActionSnapshotSchemaV05.model_validate(
        {
            "action_snapshot_id": "019b0000-0000-7000-8000-000000000801",
            "action_id": "019b0000-0000-7000-8000-000000000802",
            "version": 1,
            "opportunity_id": "019b0000-0000-7000-8000-000000000803",
            "opportunity_version": 1,
            "saved": True,
            "state": "NOT_STARTED",
            "material_items": [],
            "last_event_id": "019b0000-0000-7000-8000-000000000804",
            "input_sha256": "8" * 64,
            "created_at": NOW,
        }
    )


class FakeProfileService:
    def __init__(self) -> None:
        self.last_key: str | None = None

    def get_current(self, _principal: Principal) -> object:
        return None

    def save(self, _principal: Principal, _command: object, *, idempotency_key: str) -> object:
        self.last_key = idempotency_key
        return None


class FakeMatchService:
    def get_latest(self, _principal: Principal) -> None:
        return None


class FakeActionService:
    def __init__(self) -> None:
        self.last_key: str | None = None
        self.conflict = False

    def get_current(self, _principal: Principal, _public_id: str) -> None:
        return None

    def set_saved(
        self,
        _principal: Principal,
        _public_id: str,
        _saved: bool,
        *,
        idempotency_key: str,
    ) -> PersonalActionSnapshotSchemaV05:
        if self.conflict:
            raise IdempotencyConflict("sensitive conflict payload")
        self.last_key = idempotency_key
        return action_snapshot()


@pytest.fixture
def api_client() -> Iterator[
    tuple[TestClient, FakeProfileService, FakeMatchService, FakeActionService]
]:
    application = create_app()
    profile = FakeProfileService()
    match = FakeMatchService()
    action = FakeActionService()
    application.dependency_overrides[require_principal] = lambda: Principal(user_id=USER_A_ID)
    application.dependency_overrides[get_profile_service] = lambda: profile
    application.dependency_overrides[get_personal_match_service] = lambda: match
    application.dependency_overrides[get_action_service] = lambda: action
    with TestClient(application) as client:
        yield client, profile, match, action
    application.dependency_overrides.clear()


def test_personal_write_is_private_rejects_user_id_and_requires_one_key(
    api_client: tuple[TestClient, FakeProfileService, FakeMatchService, FakeActionService],
) -> None:
    client, _, _, action = api_client

    response = client.put(
        f"/api/v1/me/opportunities/{PUBLIC_ID}/saved",
        headers={"Idempotency-Key": "saved-api-request-0001"},
        json={"saved": True},
    )
    missing_key = client.put(
        f"/api/v1/me/opportunities/{PUBLIC_ID}/saved",
        json={"saved": True},
    )
    extra_identity = client.put(
        f"/api/v1/me/opportunities/{PUBLIC_ID}/saved",
        headers={"Idempotency-Key": "saved-api-request-0002"},
        json={"saved": True, "user_id": str(USER_A_ID)},
    )
    repeated_key = client.put(
        f"/api/v1/me/opportunities/{PUBLIC_ID}/saved",
        headers=[
            ("Idempotency-Key", "saved-api-request-0003"),
            ("Idempotency-Key", "saved-api-request-0004"),
        ],
        json={"saved": True},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["saved"] is True
    assert "user_id" not in response.text
    assert action.last_key == "saved-api-request-0001"
    assert missing_key.status_code == 400
    assert extra_identity.status_code == 400
    assert repeated_key.status_code == 400
    assert missing_key.headers["cache-control"] == "private, no-store"
    assert extra_identity.headers["cache-control"] == "private, no-store"
    assert repeated_key.headers["cache-control"] == "private, no-store"


def test_unknown_and_other_owner_action_have_identical_private_problem(
    api_client: tuple[TestClient, FakeProfileService, FakeMatchService, FakeActionService],
) -> None:
    client, _, _, _ = api_client

    other = client.get(f"/api/v1/me/opportunities/{PUBLIC_ID}/action")
    unknown = client.get(f"/api/v1/me/opportunities/{UNKNOWN_PUBLIC_ID}/action")

    assert (other.status_code, other.json()) == (unknown.status_code, unknown.json())
    assert other.status_code == 404
    assert other.headers["cache-control"] == "private, no-store"


def test_idempotency_conflict_is_stable_and_does_not_leak_internal_detail(
    api_client: tuple[TestClient, FakeProfileService, FakeMatchService, FakeActionService],
) -> None:
    client, _, _, action = api_client
    action.conflict = True

    response = client.put(
        f"/api/v1/me/opportunities/{PUBLIC_ID}/saved",
        headers={"Idempotency-Key": "saved-api-request-0001"},
        json={"saved": False},
    )

    assert response.status_code == 409
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["type"].endswith("idempotency-conflict")
    assert "sensitive" not in response.text.lower()


def test_personal_router_has_no_phase7_or_phase8_routes(
    api_client: tuple[TestClient, FakeProfileService, FakeMatchService, FakeActionService],
) -> None:
    _client, _, _, _ = api_client
    paths = {
        str(getattr(route, "path", "")).lower()
        for route in personal_router.routes
        if getattr(route, "path", "")
    }

    assert any(path.startswith("/api/v1/me/") for path in paths)
    for forbidden in ("feedback", "review", "reminder", "notification"):
        assert all(forbidden not in path for path in paths)
