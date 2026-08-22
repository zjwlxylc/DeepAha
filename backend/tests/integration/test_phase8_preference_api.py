from datetime import UTC, datetime
from uuid import uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.api.personal import require_principal
from deepaha.core.settings import get_settings
from deepaha.main import create_app
from deepaha.notifications.models import (
    NotificationOutboxModel,
    ReminderPreferenceIdempotencyRecordModel,
    ReminderPreferenceSnapshotModel,
)
from deepaha.notifications.preferences import (
    ReminderPreferenceIdempotencyConflict,
    ReminderPreferenceService,
)
from deepaha.opportunities.models import Opportunity
from deepaha.personal.auth import Principal
from deepaha.personal.models import PersonalActionSnapshotModel, PersonalUserModel
from tests.integration.test_phase4_persistence_contract import persist_complete_phase4_graph
from tests.integration.test_phase6_profile_persistence import (
    TOKEN_A,
    USER_A_ID,
    USER_A_STATE_ID,
    USER_B_ID,
    seed_users,
)

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 22, 13, 0, tzinfo=UTC)


def test_preference_snapshots_are_append_only_idempotent_and_owner_scoped(
    migrated_engine: Engine,
) -> None:
    seed_users(migrated_engine)
    service = ReminderPreferenceService(
        session_factory=sessionmaker(bind=migrated_engine, expire_on_commit=False),
        id_factory=uuid7,
        now_factory=lambda: NOW,
    )
    principal_a = Principal(user_id=USER_A_ID)
    principal_b = Principal(user_id=USER_B_ID)

    assert service.get_current(principal_a) is None
    first = service.set_enabled(
        principal_a,
        True,
        idempotency_key="deadline-reminder-request-0001",
    )
    replay = service.set_enabled(
        principal_a,
        True,
        idempotency_key="deadline-reminder-request-0001",
    )
    no_op = service.set_enabled(
        principal_a,
        True,
        idempotency_key="deadline-reminder-request-0002",
    )
    changed = service.set_enabled(
        principal_a,
        False,
        idempotency_key="deadline-reminder-request-0003",
    )

    assert first.enabled is True
    assert replay.preference_snapshot_id == first.preference_snapshot_id
    assert no_op.preference_snapshot_id == first.preference_snapshot_id
    assert changed.enabled is False
    assert changed.version == 2
    assert changed.preference_id == first.preference_id
    assert changed.predecessor_snapshot_id == first.preference_snapshot_id
    assert service.get_current(principal_a) == changed
    assert service.get_current(principal_b) is None
    with pytest.raises(ReminderPreferenceIdempotencyConflict):
        service.set_enabled(
            principal_a,
            False,
            idempotency_key="deadline-reminder-request-0001",
        )

    with Session(migrated_engine) as session:
        snapshots = session.scalar(
            select(func.count())
            .select_from(ReminderPreferenceSnapshotModel)
            .where(ReminderPreferenceSnapshotModel.user_id == USER_A_ID)
        )
        idempotency_records = session.scalar(
            select(func.count())
            .select_from(ReminderPreferenceIdempotencyRecordModel)
            .where(ReminderPreferenceIdempotencyRecordModel.user_id == USER_A_ID)
        )
        outbox_rows = session.scalar(select(func.count()).select_from(NotificationOutboxModel))

    assert snapshots == 2
    assert idempotency_records == 3
    assert outbox_rows == 0


def test_saving_an_opportunity_does_not_enable_reminders(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        rule_set, _profile, _eligibility, _evaluation = persist_complete_phase4_graph(session)
        opportunity = session.get(Opportunity, rule_set.opportunity_id)
        assert opportunity is not None
        session.add(
            PersonalUserModel(
                user_id=USER_A_ID,
                user_state_id=USER_A_STATE_ID,
                active=True,
                created_at=NOW,
            )
        )
        session.flush()
        session.add(
            PersonalActionSnapshotModel(
                action_snapshot_id=uuid7(),
                action_id=uuid7(),
                user_id=USER_A_ID,
                version=1,
                opportunity_id=opportunity.opportunity_id,
                opportunity_version=rule_set.opportunity_version,
                saved=True,
                state="NOT_STARTED",
                material_items=[],
                last_event_id=uuid7(),
                input_sha256="b" * 64,
                created_at=NOW,
            )
        )
        session.commit()

    service = ReminderPreferenceService(
        session_factory=sessionmaker(bind=migrated_engine, expire_on_commit=False),
        id_factory=uuid7,
        now_factory=lambda: NOW,
    )

    assert service.get_current(Principal(user_id=USER_A_ID)) is None
    with Session(migrated_engine) as session:
        assert session.scalar(select(func.count()).select_from(NotificationOutboxModel)) == 0


def test_preference_api_derives_owner_and_fails_closed(
    migrated_engine: Engine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_users(migrated_engine)
    monkeypatch.setenv("DEEPAHA_ENVIRONMENT", "test")
    monkeypatch.setenv("DEEPAHA_PERSONAL_AUTH_MODE", "fixture")
    monkeypatch.setenv("DEEPAHA_DATABASE_URL", database_url)
    get_settings.cache_clear()
    application = create_app()
    auth = {"Authorization": f"Bearer {TOKEN_A}"}
    path = "/api/v1/me/reminder-preferences/deadline-change"

    try:
        with TestClient(application) as client:
            unauthenticated = client.get(path)
            duplicate_authorization = client.get(
                path,
                headers=[
                    ("Authorization", f"Bearer {TOKEN_A}"),
                    ("Authorization", f"Bearer {TOKEN_A}"),
                ],
            )
            absent = client.get(path, headers=auth)
            enabled = client.put(
                path,
                headers={**auth, "Idempotency-Key": "deadline-reminder-api-0001"},
                json={"enabled": True},
            )
            replay = client.put(
                path,
                headers={**auth, "Idempotency-Key": "deadline-reminder-api-0001"},
                json={"enabled": True},
            )
            conflict = client.put(
                path,
                headers={**auth, "Idempotency-Key": "deadline-reminder-api-0001"},
                json={"enabled": False},
            )
            application.dependency_overrides[require_principal] = lambda: Principal(
                user_id=USER_B_ID
            )
            other_owner = client.get(path)
    finally:
        get_settings.cache_clear()

    assert unauthenticated.status_code == 401
    assert duplicate_authorization.status_code == 401
    assert absent.status_code == 200
    assert absent.json() is None
    assert enabled.status_code == 200
    assert enabled.json() == replay.json()
    assert enabled.json()["user_id"] == str(USER_A_ID)
    assert enabled.json()["cadence"] == "AS_SOON_AS_GOVERNED"
    assert enabled.json()["target"] == "TEST_INBOX"
    assert conflict.status_code == 409
    assert other_owner.status_code == 200
    assert other_owner.json() is None
    for response in (
        unauthenticated,
        duplicate_authorization,
        absent,
        enabled,
        replay,
        conflict,
        other_owner,
    ):
        assert response.headers["cache-control"] == "private, no-store"
