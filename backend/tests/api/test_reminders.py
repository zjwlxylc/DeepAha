from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from deepaha.api.personal import require_principal
from deepaha.api.reminders import get_reminder_inbox_service, get_reminder_preference_service
from deepaha.api.reminders import router as reminder_router
from deepaha.contracts.phase8 import ReminderPreferenceSnapshotSchemaV07
from deepaha.main import create_app
from deepaha.notifications.preferences import ReminderPreferenceIdempotencyConflict
from deepaha.notifications.schemas import ReminderInboxPage
from deepaha.personal.auth import Principal

NOW = datetime(2026, 8, 22, 13, 0, tzinfo=UTC)
USER_A_ID = UUID("019b0000-0000-7000-8000-000000000501")


def preference_snapshot(*, enabled: bool = True) -> ReminderPreferenceSnapshotSchemaV07:
    return ReminderPreferenceSnapshotSchemaV07.model_validate(
        {
            "preference_snapshot_id": "019b0000-0000-7000-8000-000000000811",
            "preference_id": "019b0000-0000-7000-8000-000000000812",
            "user_id": str(USER_A_ID),
            "version": 1,
            "predecessor_snapshot_id": None,
            "reminder_kind": "DEADLINE_CHANGED",
            "enabled": enabled,
            "cadence": "AS_SOON_AS_GOVERNED",
            "target": "TEST_INBOX",
            "actor_user_id": str(USER_A_ID),
            "preference_policy_version": "phase8-deadline-reminder-v1",
            "contract_version": "0.7.0",
            "created_at": NOW,
        }
    )


class FakeReminderPreferenceService:
    def __init__(self) -> None:
        self.current: ReminderPreferenceSnapshotSchemaV07 | None = None
        self.last_write: tuple[Principal, bool, str] | None = None
        self.conflict = False

    def get_current(
        self,
        _principal: Principal,
    ) -> ReminderPreferenceSnapshotSchemaV07 | None:
        return self.current

    def set_enabled(
        self,
        principal: Principal,
        enabled: bool,
        *,
        idempotency_key: str,
    ) -> ReminderPreferenceSnapshotSchemaV07:
        if self.conflict:
            raise ReminderPreferenceIdempotencyConflict("sensitive conflict payload")
        self.last_write = (principal, enabled, idempotency_key)
        self.current = preference_snapshot(enabled=enabled)
        return self.current


class FakeReminderInboxService:
    def __init__(self) -> None:
        self.last_principal: Principal | None = None

    def list_for_owner(self, principal: Principal, *, limit: int = 50) -> ReminderInboxPage:
        self.last_principal = principal
        assert limit == 50
        return ReminderInboxPage(items=(), count=0)


@pytest.fixture
def api_client() -> Iterator[
    tuple[TestClient, FakeReminderPreferenceService, FakeReminderInboxService]
]:
    application = create_app()
    service = FakeReminderPreferenceService()
    inbox_service = FakeReminderInboxService()
    application.dependency_overrides[require_principal] = lambda: Principal(user_id=USER_A_ID)
    application.dependency_overrides[get_reminder_preference_service] = lambda: service
    application.dependency_overrides[get_reminder_inbox_service] = lambda: inbox_service
    with TestClient(application) as client:
        yield client, service, inbox_service
    application.dependency_overrides.clear()


def test_get_absent_preference_is_private_json_null(
    api_client: tuple[TestClient, FakeReminderPreferenceService, FakeReminderInboxService],
) -> None:
    client, _service, _inbox_service = api_client

    response = client.get("/api/v1/me/reminder-preferences/deadline-change")

    assert response.status_code == 200
    assert response.json() is None
    assert response.headers["cache-control"] == "private, no-store"


def test_put_accepts_only_enabled_and_one_idempotency_key(
    api_client: tuple[TestClient, FakeReminderPreferenceService, FakeReminderInboxService],
) -> None:
    client, service, _inbox_service = api_client
    path = "/api/v1/me/reminder-preferences/deadline-change"

    response = client.put(
        path,
        headers={"Idempotency-Key": "deadline-reminder-request-0001"},
        json={"enabled": True},
    )
    missing_key = client.put(path, json={"enabled": False})
    repeated_key = client.put(
        path,
        headers=[
            ("Idempotency-Key", "deadline-reminder-request-0002"),
            ("Idempotency-Key", "deadline-reminder-request-0003"),
        ],
        json={"enabled": False},
    )
    extra_identity = client.put(
        path,
        headers={"Idempotency-Key": "deadline-reminder-request-0004"},
        json={"enabled": True, "user_id": str(USER_A_ID)},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["cadence"] == "AS_SOON_AS_GOVERNED"
    assert response.json()["target"] == "TEST_INBOX"
    assert service.last_write == (
        Principal(user_id=USER_A_ID),
        True,
        "deadline-reminder-request-0001",
    )
    for invalid in (missing_key, repeated_key, extra_identity):
        assert invalid.status_code == 400
        assert invalid.headers["cache-control"] == "private, no-store"


def test_idempotency_conflict_is_stable_and_private(
    api_client: tuple[TestClient, FakeReminderPreferenceService, FakeReminderInboxService],
) -> None:
    client, service, _inbox_service = api_client
    service.conflict = True

    response = client.put(
        "/api/v1/me/reminder-preferences/deadline-change",
        headers={"Idempotency-Key": "deadline-reminder-request-0001"},
        json={"enabled": False},
    )

    assert response.status_code == 409
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["type"].endswith("idempotency-conflict")
    assert "sensitive" not in response.text.lower()


def test_get_inbox_is_private_owner_scoped_and_read_only(
    api_client: tuple[TestClient, FakeReminderPreferenceService, FakeReminderInboxService],
) -> None:
    client, _preference_service, inbox_service = api_client

    response = client.get("/api/v1/me/reminder-inbox")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {"items": [], "count": 0}
    assert inbox_service.last_principal == Principal(user_id=USER_A_ID)


def test_get_inbox_fails_closed_without_personal_authentication() -> None:
    application = create_app()
    inbox_service = FakeReminderInboxService()
    application.dependency_overrides[get_reminder_inbox_service] = lambda: inbox_service

    with TestClient(application) as client:
        response = client.get("/api/v1/me/reminder-inbox")

    assert response.status_code == 401
    assert response.headers["cache-control"] == "private, no-store"
    assert inbox_service.last_principal is None


def test_reminder_router_exposes_only_preferences_and_read_only_inbox() -> None:
    routes = [route for route in reminder_router.routes if getattr(route, "path", None)]
    paths = {str(getattr(route, "path")) for route in routes}
    methods = set().union(*(getattr(route, "methods", set()) or set() for route in routes))

    assert paths == {
        "/api/v1/me/reminder-preferences/deadline-change",
        "/api/v1/me/reminder-inbox",
    }
    assert methods == {"GET", "PUT"}
