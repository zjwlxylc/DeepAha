from datetime import datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.contracts.phase8 import (
    DeadlineChangeReminderIntentSchemaV07,
)
from deepaha.contracts.phase8 import (
    TestInboxEntrySchemaV07 as InboxEntrySchemaV07,
)
from deepaha.notifications.adapters import PostgresTestInboxAdapter
from deepaha.notifications.candidates import DeadlineReminderCandidateService
from deepaha.notifications.models import (
    NotificationDeliveryAttemptModel,
    NotificationOutboxModel,
)
from deepaha.notifications.models import (
    TestInboxEntryModel as InboxEntryModel,
)
from deepaha.notifications.worker import ReminderWorker
from deepaha.opportunities.models import Opportunity, OpportunityEvent, OpportunityVersion
from tests.notifications.support import (
    govern_phase8_fixture_version,
    load_phase8_deadline_fixture,
    prepare_phase8_prechange,
    resolve_phase8_change,
)

pytestmark = pytest.mark.integration


class CandidateFlushFailure(DeadlineReminderCandidateService):
    def capture_for_event(
        self,
        session: Session,
        event: OpportunityEvent,
        *,
        created_at: datetime,
    ) -> tuple[UUID, ...]:
        result = super().capture_for_event(
            session,
            event,
            created_at=created_at,
        )
        if event.to_version == 7:
            session.flush()
            raise RuntimeError("injected candidate flush failure")
        return result


class InsertThenCrashAdapter(PostgresTestInboxAdapter):
    def deliver(
        self,
        session: Session,
        intent: DeadlineChangeReminderIntentSchemaV07,
        *,
        delivered_at: datetime,
    ) -> InboxEntrySchemaV07:
        super().deliver(session, intent, delivered_at=delivered_at)
        raise RuntimeError("injected pre-commit crash")


def test_candidate_failure_rolls_back_version_event_projection_and_outbox(
    migrated_engine: Engine,
) -> None:
    fixture, _manifest = load_phase8_deadline_fixture()
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    prechange = prepare_phase8_prechange(
        factory,
        candidate_service=CandidateFlushFailure(),
    )

    with pytest.raises(RuntimeError, match="candidate flush failure"):
        resolve_phase8_change(factory, prechange)

    with factory() as session:
        opportunity = session.get(Opportunity, prechange.opportunity_id)
        assert opportunity is not None
        assert opportunity.current_version == fixture.opportunity.from_version
        assert (
            session.get(
                OpportunityVersion,
                (prechange.opportunity_id, fixture.opportunity.to_version),
            )
            is None
        )
        event_count = session.scalar(
            select(func.count())
            .select_from(OpportunityEvent)
            .where(
                OpportunityEvent.opportunity_id == prechange.opportunity_id,
                OpportunityEvent.to_version == fixture.opportunity.to_version,
            )
        )
        assert event_count == 0
        assert session.scalar(select(func.count()).select_from(NotificationOutboxModel)) == 0


def test_crash_before_adapter_commit_recovers_after_lease_without_duplicates(
    migrated_engine: Engine,
) -> None:
    fixture, _manifest = load_phase8_deadline_fixture()
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    context = resolve_phase8_change(factory, prepare_phase8_prechange(factory))
    govern_phase8_fixture_version(factory, context)

    crashed = ReminderWorker(
        session_factory=factory,
        adapter=InsertThenCrashAdapter(),
        clock=lambda: fixture.scenario_clock,
    ).run_once()

    assert crashed.claimed == 1 and crashed.delivered == 0
    with factory() as session:
        outbox = session.get(NotificationOutboxModel, context.reminder_id)
        assert outbox is not None and outbox.status == "LEASED"
        assert (
            session.scalar(select(func.count()).select_from(NotificationDeliveryAttemptModel)) == 0
        )
        assert session.scalar(select(func.count()).select_from(InboxEntryModel)) == 0

    recovered = ReminderWorker(
        session_factory=factory,
        clock=lambda: fixture.scenario_clock + timedelta(seconds=61),
    ).run_once()

    assert recovered.delivered == 1
    with factory() as session:
        outbox = session.get(NotificationOutboxModel, context.reminder_id)
        assert outbox is not None and outbox.status == "DELIVERED"
        assert outbox.attempt_count == 1
        assert (
            session.scalar(select(func.count()).select_from(NotificationDeliveryAttemptModel)) == 1
        )
        assert session.scalar(select(func.count()).select_from(InboxEntryModel)) == 1
