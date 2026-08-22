import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase8 import (
    DeadlineChangeReminderIntentSchemaV07,
)
from deepaha.contracts.phase8 import (
    TestInboxEntrySchemaV07 as InboxEntrySchemaV07,
)
from deepaha.notifications.adapters import (
    PermanentDeliveryError,
    PostgresTestInboxAdapter,
    TransientDeliveryError,
)
from deepaha.notifications.models import (
    NotificationDeliveryAttemptModel,
    NotificationOutboxModel,
    ReminderPreferenceSnapshotModel,
)
from deepaha.notifications.models import (
    TestInboxEntryModel as InboxEntryModel,
)
from deepaha.notifications.worker import ReminderWorker, ReminderWorkerRunSummary
from deepaha.personal.models import PersonalActionSnapshotModel, UserStateSnapshotModel
from deepaha.public_catalog.models import PublicCatalogEntry
from tests.integration.test_phase8_public_governance import seed_governed_reminder

pytestmark = pytest.mark.integration


class MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, *, minutes: int) -> None:
        self.now += timedelta(minutes=minutes)


class AlwaysTransientAdapter:
    def deliver(self, session: Session, intent: object, *, delivered_at: datetime) -> None:
        del session, intent, delivered_at
        raise TransientDeliveryError("TEST_TRANSIENT")


def test_retry_schedule_is_exact_and_third_transient_fails(migrated_engine: Engine) -> None:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed = seed_governed_reminder(factory)
    clock = MutableClock(datetime(2026, 8, 22, 4, tzinfo=UTC))
    worker = ReminderWorker(
        session_factory=factory,
        adapter=AlwaysTransientAdapter(),
        clock=clock,
    )

    assert worker.run_once().retried == 1
    with factory() as session:
        outbox = session.get(NotificationOutboxModel, seed.reminder_id)
        assert outbox is not None
        assert outbox.attempt_count == 1
        assert outbox.next_attempt_at == clock.now + timedelta(minutes=1)
    clock.advance(minutes=1)
    assert worker.run_once().retried == 1
    with factory() as session:
        outbox = session.get(NotificationOutboxModel, seed.reminder_id)
        assert outbox is not None
        assert outbox.attempt_count == 2
        assert outbox.next_attempt_at == clock.now + timedelta(minutes=5)
    clock.advance(minutes=5)
    assert worker.run_once().failed == 1
    with factory() as session:
        outbox = session.get(NotificationOutboxModel, seed.reminder_id)
        assert outbox is not None
        assert outbox.status == "FAILED"
        assert outbox.attempt_count == 3
        assert (
            session.scalar(select(func.count()).select_from(NotificationDeliveryAttemptModel)) == 3
        )


@pytest.mark.parametrize("revocation", ["disabled", "unsaved", "purpose_revoked"])
def test_latest_user_control_suppresses_without_delivery(
    migrated_engine: Engine,
    revocation: str,
) -> None:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed = seed_governed_reminder(factory)
    with factory.begin() as session:
        if revocation == "disabled":
            previous_preference = session.scalar(
                select(ReminderPreferenceSnapshotModel).where(
                    ReminderPreferenceSnapshotModel.user_id == seed.user_id
                )
            )
            assert previous_preference is not None
            changed_at = previous_preference.created_at - timedelta(minutes=1)
            session.add(
                ReminderPreferenceSnapshotModel(
                    preference_snapshot_id=uuid7(),
                    preference_id=seed.preference_id,
                    user_id=seed.user_id,
                    version=2,
                    predecessor_snapshot_id=previous_preference.preference_snapshot_id,
                    reminder_kind="DEADLINE_CHANGED",
                    enabled=False,
                    cadence="AS_SOON_AS_GOVERNED",
                    target="TEST_INBOX",
                    actor_user_id=seed.user_id,
                    preference_policy_version="phase8-deadline-reminder-v1",
                    contract_version="0.7.0",
                    created_at=changed_at,
                )
            )
        elif revocation == "unsaved":
            previous_action = session.scalar(
                select(PersonalActionSnapshotModel).where(
                    PersonalActionSnapshotModel.user_id == seed.user_id
                )
            )
            assert previous_action is not None
            changed_at = previous_action.created_at - timedelta(minutes=1)
            session.add(
                PersonalActionSnapshotModel(
                    action_snapshot_id=uuid7(),
                    action_id=seed.action_id,
                    user_id=seed.user_id,
                    version=2,
                    opportunity_id=seed.opportunity_id,
                    opportunity_version=2,
                    saved=False,
                    state="NOT_STARTED",
                    material_items=[],
                    last_event_id=uuid7(),
                    input_sha256="c" * 64,
                    created_at=changed_at,
                )
            )
        else:
            previous_state = session.scalar(
                select(UserStateSnapshotModel).where(UserStateSnapshotModel.user_id == seed.user_id)
            )
            assert previous_state is not None
            changed_at = previous_state.created_at - timedelta(minutes=1)
            session.add(
                UserStateSnapshotModel(
                    user_state_snapshot_id=uuid7(),
                    user_state_id=seed.user_state_id,
                    user_id=seed.user_id,
                    version=2,
                    qualification_profile_snapshot_id=(
                        previous_state.qualification_profile_snapshot_id
                    ),
                    qualification_profile_version=previous_state.qualification_profile_version,
                    life_stage=previous_state.life_stage,
                    goal_types=previous_state.goal_types,
                    preference_regions=[],
                    preference_types=[],
                    skipped_fields=[],
                    personalization_enabled=True,
                    consent_version="phase6-consent-v1",
                    allowed_purposes=["PROFILE_PERSONALIZATION"],
                    scenario_clock=previous_state.scenario_clock,
                    input_sha256="d" * 64,
                    created_at=changed_at,
                )
            )

    summary = ReminderWorker(
        session_factory=factory,
        clock=lambda: datetime(2026, 8, 22, 4, tzinfo=UTC),
    ).run_once()

    assert summary.suppressed == 1
    with factory() as session:
        outbox = session.get(NotificationOutboxModel, seed.reminder_id)
        assert outbox is not None and outbox.status == "SUPPRESSED"
        assert outbox.last_error_code == "USER_CONTROL_SUPPRESSED"
        assert (
            session.scalar(select(func.count()).select_from(NotificationDeliveryAttemptModel)) == 0
        )
        assert session.scalar(select(func.count()).select_from(InboxEntryModel)) == 0


class AlwaysPermanentAdapter:
    def deliver(self, session: Session, intent: object, *, delivered_at: datetime) -> None:
        del session, intent, delivered_at
        raise PermanentDeliveryError("TEST_PERMANENT")


class InvalidContractAdapter:
    def deliver(self, session: Session, intent: object, *, delivered_at: datetime) -> None:
        del session, intent, delivered_at
        DeadlineChangeReminderIntentSchemaV07.model_validate({})


class InvalidPersistenceAdapter:
    def deliver(self, session: Session, intent: object, *, delivered_at: datetime) -> None:
        del intent, delivered_at
        session.execute(
            text("insert into test_inbox_entries (inbox_entry_id) values (:entry_id)"),
            {"entry_id": uuid7()},
        )


class InsertThenCrashAdapter(PostgresTestInboxAdapter):
    def deliver(
        self,
        session: Session,
        intent: DeadlineChangeReminderIntentSchemaV07,
        *,
        delivered_at: datetime,
    ) -> InboxEntrySchemaV07:
        super().deliver(session, intent, delivered_at=delivered_at)
        raise RuntimeError("Bearer secret exception payload")


def test_permanent_failure_consumes_one_attempt_and_fails(migrated_engine: Engine) -> None:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed = seed_governed_reminder(factory)

    summary = ReminderWorker(
        session_factory=factory,
        adapter=AlwaysPermanentAdapter(),
        clock=lambda: datetime(2026, 8, 22, 4, tzinfo=UTC),
    ).run_once()

    assert summary.failed == 1
    with factory() as session:
        outbox = session.get(NotificationOutboxModel, seed.reminder_id)
        assert outbox is not None
        assert outbox.status == "FAILED"
        assert outbox.attempt_count == 1
        assert outbox.last_error_code == "TEST_PERMANENT"


@pytest.mark.parametrize(
    ("adapter", "error_code"),
    [
        (InvalidContractAdapter(), "ADAPTER_CONTRACT_INVALID"),
        (
            InvalidPersistenceAdapter(),
            "ADAPTER_PERSISTENCE_INVALID",
        ),
    ],
)
def test_deterministic_adapter_errors_are_audited_and_bounded(
    migrated_engine: Engine,
    adapter: Any,
    error_code: str,
) -> None:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed = seed_governed_reminder(factory)
    now = datetime(2026, 8, 22, 4, tzinfo=UTC)

    summary = ReminderWorker(
        session_factory=factory,
        adapter=adapter,
        clock=lambda: now,
    ).run_once()

    assert summary.failed == 1
    with factory() as session:
        outbox = session.get(NotificationOutboxModel, seed.reminder_id)
        assert outbox is not None
        assert outbox.status == "FAILED"
        assert outbox.attempt_count == 1
        assert outbox.last_error_code == error_code
        attempt = session.scalar(select(NotificationDeliveryAttemptModel))
        assert attempt is not None
        assert attempt.outcome == "PERMANENT_FAILURE"
        assert attempt.error_code == error_code
        assert session.scalar(select(func.count()).select_from(InboxEntryModel)) == 0


def test_expired_lease_does_not_consume_retry_budget(migrated_engine: Engine) -> None:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed = seed_governed_reminder(factory)
    now = datetime(2026, 8, 22, 4, tzinfo=UTC)
    with factory.begin() as session:
        row = session.get(NotificationOutboxModel, seed.reminder_id)
        assert row is not None
        row.status = "LEASED"
        row.available_at = now - timedelta(minutes=2)
        row.lease_token = uuid7()
        row.lease_until = now - timedelta(seconds=1)
        row.claimed_at = now - timedelta(minutes=1)
        row.updated_at = now - timedelta(minutes=1)

    summary = ReminderWorker(session_factory=factory, clock=lambda: now).run_once()

    assert summary.delivered == 1
    with factory() as session:
        row = session.get(NotificationOutboxModel, seed.reminder_id)
        assert row is not None and row.attempt_count == 1


def test_governance_loss_after_claim_returns_to_wait_without_attempt(
    migrated_engine: Engine,
) -> None:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed = seed_governed_reminder(factory)
    now = datetime(2026, 8, 22, 4, tzinfo=UTC)
    worker = ReminderWorker(session_factory=factory, clock=lambda: now)
    claims, _, _, _ = worker._promote_recover_and_claim(now=now, limit=50)
    assert len(claims) == 1
    with factory.begin() as session:
        catalog = session.get(PublicCatalogEntry, seed.opportunity_id)
        assert catalog is not None
        catalog.opportunity_version = 1

    assert worker._process_claim(claims[0], now=now) == "WAITING_GOVERNANCE"

    with factory() as session:
        row = session.get(NotificationOutboxModel, seed.reminder_id)
        assert row is not None
        assert row.status == "WAITING_GOVERNANCE"
        assert row.attempt_count == 0
        assert (
            session.scalar(select(func.count()).select_from(NotificationDeliveryAttemptModel)) == 0
        )


def test_adapter_crash_rolls_back_inbox_and_does_not_log_payload(
    migrated_engine: Engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed = seed_governed_reminder(factory)
    now = datetime(2026, 8, 22, 4, tzinfo=UTC)
    logger = logging.getLogger("phase8-worker-recovery-test")
    logger.disabled = False
    caplog.set_level(logging.ERROR, logger=logger.name)

    summary = ReminderWorker(
        session_factory=factory,
        adapter=InsertThenCrashAdapter(),
        clock=lambda: now,
        logger=logger,
    ).run_once()

    assert summary.delivered == 0
    assert "WORKER_PROCESSING_ROLLBACK" in caplog.text
    assert "Bearer secret exception payload" not in caplog.text
    with factory() as session:
        row = session.get(NotificationOutboxModel, seed.reminder_id)
        assert row is not None and row.status == "LEASED"
        assert (
            session.scalar(select(func.count()).select_from(NotificationDeliveryAttemptModel)) == 0
        )
        assert session.scalar(select(func.count()).select_from(InboxEntryModel)) == 0


def test_committed_inbox_replay_converges_without_duplicate(migrated_engine: Engine) -> None:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed = seed_governed_reminder(factory)
    now = datetime(2026, 8, 22, 4, tzinfo=UTC)
    adapter = PostgresTestInboxAdapter()
    with factory.begin() as session:
        row = session.get(NotificationOutboxModel, seed.reminder_id)
        assert row is not None
        intent = ReminderWorker._intent(row)
        first = adapter.deliver(session, intent, delivered_at=now)
        second = adapter.deliver(session, intent, delivered_at=now)
        assert first.inbox_entry_id == second.inbox_entry_id

    summary = ReminderWorker(
        session_factory=factory,
        adapter=adapter,
        clock=lambda: now,
    ).run_once()

    assert summary.delivered == 1
    with factory() as session:
        row = session.get(NotificationOutboxModel, seed.reminder_id)
        assert row is not None and row.status == "DELIVERED"
        assert session.scalar(select(func.count()).select_from(InboxEntryModel)) == 1


def test_schema_valid_outbox_tamper_fails_before_delivery(migrated_engine: Engine) -> None:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed = seed_governed_reminder(factory)
    now = datetime(2026, 8, 22, 4, tzinfo=UTC)
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "alter table notification_outbox disable trigger phase8_reject_outbox_fact_mutation"
            )
        )
        connection.execute(
            text(
                "update notification_outbox set old_closes_on = :wrong_date "
                "where reminder_id = :reminder_id"
            ),
            {"wrong_date": date(2026, 9, 6), "reminder_id": seed.reminder_id},
        )
        connection.execute(
            text(
                "alter table notification_outbox enable trigger phase8_reject_outbox_fact_mutation"
            )
        )

    summary = ReminderWorker(session_factory=factory, clock=lambda: now).run_once()

    assert summary.failed == 1
    with factory() as session:
        row = session.get(NotificationOutboxModel, seed.reminder_id)
        assert row is not None
        assert row.status == "FAILED"
        assert row.attempt_count == 0
        assert row.last_error_code == "REMINDER_BINDING_INVALID"
        assert session.scalar(select(func.count()).select_from(InboxEntryModel)) == 0


def test_existing_inbox_mismatch_is_a_permanent_failure(migrated_engine: Engine) -> None:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed = seed_governed_reminder(factory)
    now = datetime(2026, 8, 22, 4, tzinfo=UTC)
    adapter = PostgresTestInboxAdapter()
    with factory() as session:
        row = session.get(NotificationOutboxModel, seed.reminder_id)
        assert row is not None
        contract = adapter.deliver(session, ReminderWorker._intent(row), delivered_at=now)
        session.rollback()
    payload = contract.model_dump()
    payload["opportunity_title"] = "Mismatched replay title"
    payload["previous_official_url"] = str(payload["previous_official_url"])
    payload["current_official_url"] = str(payload["current_official_url"])
    payload["direction"] = payload["direction"].value
    payload["target"] = payload["target"].value
    with factory.begin() as session:
        session.add(InboxEntryModel(**payload))

    summary = ReminderWorker(
        session_factory=factory,
        adapter=adapter,
        clock=lambda: now,
    ).run_once()

    assert summary.failed == 1
    with factory() as session:
        row = session.get(NotificationOutboxModel, seed.reminder_id)
        assert row is not None
        assert row.status == "FAILED"
        assert row.attempt_count == 1
        assert row.last_error_code == "TEST_INBOX_REPLAY_MISMATCH"
        assert session.scalar(select(func.count()).select_from(InboxEntryModel)) == 1


def test_concurrent_workers_create_one_attempt_and_one_inbox(migrated_engine: Engine) -> None:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed = seed_governed_reminder(factory)
    now = datetime(2026, 8, 22, 4, tzinfo=UTC)

    def run_worker(_: int) -> ReminderWorkerRunSummary:
        return ReminderWorker(session_factory=factory, clock=lambda: now).run_once()

    with ThreadPoolExecutor(max_workers=2) as executor:
        summaries = tuple(executor.map(run_worker, range(2)))

    assert sum(summary.delivered for summary in summaries) == 1
    with factory() as session:
        row = session.get(NotificationOutboxModel, seed.reminder_id)
        assert row is not None and row.status == "DELIVERED"
        assert (
            session.scalar(select(func.count()).select_from(NotificationDeliveryAttemptModel)) == 1
        )
        assert session.scalar(select(func.count()).select_from(InboxEntryModel)) == 1


def test_live_lease_is_not_stolen_by_another_token(migrated_engine: Engine) -> None:
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    seed = seed_governed_reminder(factory)
    now = datetime(2026, 8, 22, 4, tzinfo=UTC)
    live_token = UUID("019b0000-0000-7000-8000-000000000891")
    with factory.begin() as session:
        row = session.get(NotificationOutboxModel, seed.reminder_id)
        assert row is not None
        row.status = "LEASED"
        row.available_at = now
        row.lease_token = live_token
        row.lease_until = now + timedelta(minutes=1)
        row.claimed_at = now
        row.updated_at = now

    summary = ReminderWorker(session_factory=factory, clock=lambda: now).run_once()

    assert summary.claimed == 0
    with factory() as session:
        row = session.get(NotificationOutboxModel, seed.reminder_id)
        assert row is not None and row.lease_token == live_token and row.attempt_count == 0
