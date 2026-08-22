import hashlib
from datetime import UTC, date, datetime
from uuid import uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.api.personal import require_principal
from deepaha.core.settings import get_settings
from deepaha.main import create_app
from deepaha.notifications.models import (
    NotificationDeliveryAttemptModel,
    NotificationOutboxModel,
    ReminderPreferenceIdempotencyRecordModel,
    ReminderPreferenceSnapshotModel,
)
from deepaha.notifications.models import (
    TestInboxEntryModel as InboxEntryModel,
)
from deepaha.notifications.worker import ReminderWorker
from deepaha.personal.auth import Principal
from deepaha.personal.models import (
    PersonalActionSnapshotModel,
    PersonalUserModel,
    UserStateSnapshotModel,
)
from tests.integration.test_phase8_public_governance import (
    ReminderSeed,
    seed_governed_reminder,
)

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 22, 4, tzinfo=UTC)


def _phase8_digest(session: Session) -> str:
    models = (
        ReminderPreferenceSnapshotModel,
        ReminderPreferenceIdempotencyRecordModel,
        NotificationOutboxModel,
        NotificationDeliveryAttemptModel,
        InboxEntryModel,
    )
    values: list[str] = []
    for model in models:
        rows = session.execute(select(model.__table__)).mappings()
        model_values = (
            f"{model.__tablename__}:{sorted((str(key), str(value)) for key, value in row.items())}"
            for row in rows
        )
        values.extend(sorted(model_values))
    return hashlib.sha256("\n".join(values).encode()).hexdigest()


def _add_foreign_inbox(factory: sessionmaker[Session], owner: ReminderSeed) -> Principal:
    user_id = uuid7()
    user_state_id = uuid7()
    with factory.begin() as session:
        original_outbox = session.get(NotificationOutboxModel, owner.reminder_id)
        original_inbox = session.scalar(
            select(InboxEntryModel).where(InboxEntryModel.reminder_id == owner.reminder_id)
        )
        original_state = session.get(
            UserStateSnapshotModel,
            original_outbox.user_state_snapshot_id if original_outbox is not None else None,
        )
        assert original_outbox is not None and original_inbox is not None
        assert original_state is not None
        session.add(
            PersonalUserModel(
                user_id=user_id,
                user_state_id=user_state_id,
                active=True,
                created_at=NOW,
            )
        )
        session.flush()
        state = UserStateSnapshotModel(
            user_state_snapshot_id=uuid7(),
            user_state_id=user_state_id,
            user_id=user_id,
            version=1,
            qualification_profile_snapshot_id=original_state.qualification_profile_snapshot_id,
            qualification_profile_version=original_state.qualification_profile_version,
            life_stage="EARLY_CAREER",
            goal_types=["STATE_OWNED_ENTERPRISE_JOB"],
            preference_regions=[],
            preference_types=[],
            skipped_fields=[],
            personalization_enabled=True,
            consent_version="phase6-consent-v1",
            allowed_purposes=["ACTION_TRACKING"],
            scenario_clock=date(2026, 8, 22),
            input_sha256="e" * 64,
            created_at=NOW,
        )
        action = PersonalActionSnapshotModel(
            action_snapshot_id=uuid7(),
            action_id=uuid7(),
            user_id=user_id,
            version=1,
            opportunity_id=original_outbox.opportunity_id,
            opportunity_version=original_outbox.to_version,
            saved=True,
            state="NOT_STARTED",
            material_items=[],
            last_event_id=uuid7(),
            input_sha256="f" * 64,
            created_at=NOW,
        )
        preference = ReminderPreferenceSnapshotModel(
            preference_snapshot_id=uuid7(),
            preference_id=uuid7(),
            user_id=user_id,
            version=1,
            predecessor_snapshot_id=None,
            reminder_kind="DEADLINE_CHANGED",
            enabled=True,
            cadence="AS_SOON_AS_GOVERNED",
            target="TEST_INBOX",
            actor_user_id=user_id,
            preference_policy_version="phase8-deadline-reminder-v1",
            contract_version="0.7.0",
            created_at=NOW,
        )
        session.add_all([state, action, preference])
        session.flush()
        reminder_id = uuid7()
        session.add(
            NotificationOutboxModel(
                reminder_id=reminder_id,
                user_id=user_id,
                opportunity_id=original_outbox.opportunity_id,
                event_id=original_outbox.event_id,
                from_version=original_outbox.from_version,
                to_version=original_outbox.to_version,
                old_closes_on=original_outbox.old_closes_on,
                new_closes_on=original_outbox.new_closes_on,
                direction=original_outbox.direction,
                previous_evidence_ref_id=original_outbox.previous_evidence_ref_id,
                current_evidence_ref_id=original_outbox.current_evidence_ref_id,
                action_snapshot_id=action.action_snapshot_id,
                preference_snapshot_id=preference.preference_snapshot_id,
                user_state_snapshot_id=state.user_state_snapshot_id,
                consent_version=state.consent_version,
                detected_at=original_outbox.detected_at,
                created_at=NOW,
                reminder_kind="DEADLINE_CHANGED",
                cadence="AS_SOON_AS_GOVERNED",
                target="TEST_INBOX",
                contract_version="0.7.0",
                status="DELIVERED",
                available_at=NOW,
                lease_token=None,
                lease_until=None,
                claimed_at=None,
                attempt_count=1,
                next_attempt_at=None,
                last_error_code=None,
                terminal_at=NOW,
                updated_at=NOW,
            )
        )
        session.flush()
        session.add(
            InboxEntryModel(
                inbox_entry_id=uuid7(),
                reminder_id=reminder_id,
                user_id=user_id,
                opportunity_id=original_inbox.opportunity_id,
                opportunity_public_id=original_inbox.opportunity_public_id,
                opportunity_title="Foreign synthetic reminder",
                event_id=original_inbox.event_id,
                from_version=original_inbox.from_version,
                to_version=original_inbox.to_version,
                old_closes_on=original_inbox.old_closes_on,
                new_closes_on=original_inbox.new_closes_on,
                direction=original_inbox.direction,
                previous_evidence_ref_id=original_inbox.previous_evidence_ref_id,
                current_evidence_ref_id=original_inbox.current_evidence_ref_id,
                previous_official_url=original_inbox.previous_official_url,
                current_official_url=original_inbox.current_official_url,
                personal_detail_path=original_inbox.personal_detail_path,
                detected_at=original_inbox.detected_at,
                delivered_at=NOW,
                target="TEST_INBOX",
                contract_version="0.7.0",
            )
        )
    return Principal(user_id=user_id)


def test_get_inbox_is_owner_scoped_and_has_no_read_side_effect(
    migrated_engine: Engine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed = seed_governed_reminder(factory)
    delivered = ReminderWorker(session_factory=factory, clock=lambda: NOW).run_once()
    assert delivered.delivered == 1
    foreign = _add_foreign_inbox(factory, seed)
    with factory() as session:
        before = _phase8_digest(session)

    monkeypatch.setenv("DEEPAHA_DATABASE_URL", database_url)
    get_settings.cache_clear()
    application = create_app()
    application.dependency_overrides[require_principal] = lambda: Principal(user_id=seed.user_id)
    try:
        with TestClient(application) as client:
            response = client.get("/api/v1/me/reminder-inbox")
            application.dependency_overrides[require_principal] = lambda: foreign
            foreign_response = client.get("/api/v1/me/reminder-inbox")
    finally:
        get_settings.cache_clear()

    with factory() as session:
        after = _phase8_digest(session)
    assert before == after
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["count"] == 1
    assert response.json()["items"][0]["user_id"] == str(seed.user_id)
    assert "Foreign synthetic reminder" not in response.text
    assert foreign_response.json()["count"] == 1
    assert foreign_response.json()["items"][0]["user_id"] == str(foreign.user_id)
