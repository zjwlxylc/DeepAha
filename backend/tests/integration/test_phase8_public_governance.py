from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.notifications.candidates import DeadlineReminderCandidateService
from deepaha.notifications.models import (
    NotificationDeliveryAttemptModel,
    NotificationOutboxModel,
    ReminderPreferenceSnapshotModel,
)
from deepaha.notifications.models import (
    TestInboxEntryModel as InboxEntryModel,
)
from deepaha.notifications.worker import ReminderWorker
from deepaha.opportunities.models import Opportunity, OpportunityEvent
from deepaha.personal.models import (
    PersonalActionSnapshotModel,
    PersonalUserModel,
    UserStateSnapshotModel,
)
from deepaha.profiles.models import ProfileSnapshotModel
from deepaha.public_catalog.models import PublicCatalogEntry
from deepaha.sources.models import Source
from tests.public_catalog.support import persist_phase5_fixture

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 22, 4, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class ReminderSeed:
    reminder_id: UUID
    user_id: UUID
    opportunity_id: UUID
    event_id: UUID
    action_id: UUID
    preference_id: UUID
    user_state_id: UUID


def seed_governed_reminder(
    factory: sessionmaker[Session],
    *,
    catalog_version: int = 2,
) -> ReminderSeed:
    with factory.begin() as session:
        persist_phase5_fixture(session)
        event = session.scalar(
            select(OpportunityEvent).where(OpportunityEvent.event_type == "DEADLINE_CHANGED")
        )
        assert event is not None and event.from_version == 1 and event.to_version == 2
        opportunity = session.get(Opportunity, event.opportunity_id)
        assert opportunity is not None
        catalog = session.get(PublicCatalogEntry, event.opportunity_id)
        assert catalog is not None
        catalog.opportunity_version = catalog_version

        before_event = event.detected_at - timedelta(minutes=1)
        user_id = uuid7()
        user_state_id = uuid7()
        profile_id = uuid7()
        profile_snapshot_id = uuid7()
        action_id = uuid7()
        preference_id = uuid7()
        user = PersonalUserModel(
            user_id=user_id,
            user_state_id=user_state_id,
            active=True,
            created_at=before_event,
        )
        profile = ProfileSnapshotModel(
            profile_snapshot_id=profile_snapshot_id,
            profile_id=profile_id,
            version=1,
            synthetic=True,
            persona_family_id=None,
            attributes={},
            scenario_clock=date(2026, 8, 21),
            profile_schema_version="0.4.0",
            created_at=before_event,
            created_by="phase8-worker-test",
            reviewed_by="phase8-worker-test",
            change_note="Synthetic engineering fixture only.",
        )
        session.add_all([user, profile])
        session.flush()
        state = UserStateSnapshotModel(
            user_state_snapshot_id=uuid7(),
            user_state_id=user_state_id,
            user_id=user_id,
            version=1,
            qualification_profile_snapshot_id=profile_snapshot_id,
            qualification_profile_version=1,
            life_stage="EARLY_CAREER",
            goal_types=["STATE_OWNED_ENTERPRISE_JOB"],
            preference_regions=[],
            preference_types=[],
            skipped_fields=[],
            personalization_enabled=True,
            consent_version="phase6-consent-v1",
            allowed_purposes=["ACTION_TRACKING"],
            scenario_clock=date(2026, 8, 21),
            input_sha256="a" * 64,
            created_at=before_event,
        )
        action = PersonalActionSnapshotModel(
            action_snapshot_id=uuid7(),
            action_id=action_id,
            user_id=user_id,
            version=1,
            opportunity_id=event.opportunity_id,
            opportunity_version=1,
            saved=True,
            state="NOT_STARTED",
            material_items=[],
            last_event_id=uuid7(),
            input_sha256="b" * 64,
            created_at=before_event,
        )
        preference = ReminderPreferenceSnapshotModel(
            preference_snapshot_id=uuid7(),
            preference_id=preference_id,
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
            created_at=before_event,
        )
        session.add_all([state, action, preference])
        session.flush()
        reminder_ids = DeadlineReminderCandidateService().capture_for_event(
            session,
            event,
            created_at=event.detected_at,
        )
        assert len(reminder_ids) == 1
        return ReminderSeed(
            reminder_id=reminder_ids[0],
            user_id=user_id,
            opportunity_id=event.opportunity_id,
            event_id=event.event_id,
            action_id=action_id,
            preference_id=preference_id,
            user_state_id=user_state_id,
        )


def test_old_catalog_version_waits_without_attempt_or_inbox(migrated_engine: Engine) -> None:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed = seed_governed_reminder(factory, catalog_version=1)

    summary = ReminderWorker(session_factory=factory, clock=lambda: NOW).run_once()

    assert summary.waiting_governance == 1
    assert summary.promoted == 0
    with factory() as session:
        outbox = session.get(NotificationOutboxModel, seed.reminder_id)
        assert outbox is not None and outbox.status == "WAITING_GOVERNANCE"
        assert (
            session.scalar(select(func.count()).select_from(NotificationDeliveryAttemptModel)) == 0
        )
        assert session.scalar(select(func.count()).select_from(InboxEntryModel)) == 0


def test_exact_governed_version_promotes_and_delivers(migrated_engine: Engine) -> None:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed = seed_governed_reminder(factory, catalog_version=1)
    worker = ReminderWorker(session_factory=factory, clock=lambda: NOW)
    assert worker.run_once().waiting_governance == 1
    with factory.begin() as session:
        catalog = session.get(PublicCatalogEntry, seed.opportunity_id)
        assert catalog is not None
        catalog.opportunity_version = 2

    summary = worker.run_once()

    assert summary.promoted == 1
    assert summary.delivered == 1
    with factory() as session:
        outbox = session.get(NotificationOutboxModel, seed.reminder_id)
        assert outbox is not None and outbox.status == "DELIVERED"
        assert session.scalar(select(func.count()).select_from(InboxEntryModel)) == 1


@pytest.mark.parametrize(
    "invalid_state",
    ["not_published", "missing_entry", "incomplete", "non_official"],
)
def test_non_public_or_unrelated_catalog_does_not_promote(
    migrated_engine: Engine,
    invalid_state: str,
) -> None:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed = seed_governed_reminder(factory)
    with factory.begin() as session:
        if invalid_state == "not_published":
            opportunity = session.get(Opportunity, seed.opportunity_id)
            assert opportunity is not None
            opportunity.publication_status = "INTERNAL"
        elif invalid_state == "missing_entry":
            catalog = session.get(PublicCatalogEntry, seed.opportunity_id)
            assert catalog is not None
            session.delete(catalog)
        elif invalid_state == "incomplete":
            opportunity = session.get(Opportunity, seed.opportunity_id)
            assert opportunity is not None
            opportunity.canonical_title = "projection-mismatch"
        else:
            for source in session.scalars(select(Source)):
                source.tier = "TRUSTED_SECONDARY"

    assert ReminderWorker(session_factory=factory, clock=lambda: NOW).run_once().promoted == 0

    with factory() as session:
        outbox = session.get(NotificationOutboxModel, seed.reminder_id)
        assert outbox is not None and outbox.status == "WAITING_GOVERNANCE"
