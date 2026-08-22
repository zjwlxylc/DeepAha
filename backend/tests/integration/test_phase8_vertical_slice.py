from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from deepaha.core.settings import get_settings
from deepaha.main import create_app
from deepaha.notifications.candidates import DeadlineReminderCandidateService
from deepaha.notifications.models import (
    NotificationDeliveryAttemptModel,
    NotificationOutboxModel,
)
from deepaha.notifications.models import (
    TestInboxEntryModel as InboxEntryModel,
)
from deepaha.notifications.worker import ReminderWorker
from deepaha.opportunities.models import OpportunityEvent
from tests.notifications.seed_phase8_browser import seed_phase8_browser
from tests.notifications.support import (
    Phase8EngineeringReport,
    govern_phase8_fixture_version,
    load_phase8_deadline_fixture,
    prepare_phase8_prechange,
    resolve_phase8_change,
)

pytestmark = pytest.mark.integration


def test_phase8_browser_seed_is_synthetic_and_refuses_reuse(
    migrated_engine: Engine,
    database_url: str,
) -> None:
    identity = seed_phase8_browser(database_url)

    assert identity.route == "/me/reminders"
    assert identity.bearer_token
    with pytest.raises(RuntimeError, match="empty Phase 8 fixture scope"):
        seed_phase8_browser(database_url)


def test_exact_deadline_change_vertical_slice_is_governed_replayable_and_private(
    migrated_engine: Engine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, _manifest = load_phase8_deadline_fixture()
    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    prechange = prepare_phase8_prechange(factory)
    context = resolve_phase8_change(factory, prechange)

    with factory() as session:
        candidate = session.get(NotificationOutboxModel, context.reminder_id)
        assert candidate is not None and candidate.status == "WAITING_GOVERNANCE"
        candidate_count = session.scalar(select(func.count()).select_from(NotificationOutboxModel))
        attempts_before = session.scalar(
            select(func.count()).select_from(NotificationDeliveryAttemptModel)
        )
        inbox_before = session.scalar(select(func.count()).select_from(InboxEntryModel))

    waiting_summary = ReminderWorker(
        session_factory=factory,
        clock=lambda: fixture.scenario_clock,
    ).run_once()
    assert waiting_summary.waiting_governance == 1
    assert waiting_summary.delivered == 0

    govern_phase8_fixture_version(factory, context)
    delivered_summary = ReminderWorker(
        session_factory=factory,
        clock=lambda: fixture.scenario_clock,
    ).run_once()

    monkeypatch.setenv("DEEPAHA_ENVIRONMENT", "test")
    monkeypatch.setenv("DEEPAHA_PERSONAL_AUTH_MODE", "fixture")
    monkeypatch.setenv("DEEPAHA_DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            response = client.get(
                "/api/v1/me/reminder-inbox",
                headers={"Authorization": f"Bearer {context.bearer_token}"},
            )
    finally:
        get_settings.cache_clear()

    with factory() as session:
        event = session.get(OpportunityEvent, context.event_id)
        assert event is not None
        replay = DeadlineReminderCandidateService().capture_for_event(
            session,
            event,
            created_at=event.detected_at,
        )
        delivery_attempts = session.scalar(
            select(func.count()).select_from(NotificationDeliveryAttemptModel)
        )
        inbox_entries = session.scalar(select(func.count()).select_from(InboxEntryModel))

    assert replay == (context.reminder_id,)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["count"] == 1
    entry = response.json()["items"][0]
    assert entry["user_id"] == str(context.user_id)
    assert entry["from_version"] == fixture.opportunity.from_version
    assert entry["to_version"] == fixture.opportunity.to_version
    assert entry["old_closes_on"] == fixture.opportunity.old_closes_on.isoformat()
    assert entry["new_closes_on"] == fixture.opportunity.new_closes_on.isoformat()
    assert entry["previous_evidence_ref_id"] == str(fixture.opportunity.previous_evidence_ref_id)
    assert entry["current_evidence_ref_id"] == str(fixture.opportunity.current_evidence_ref_id)

    report = Phase8EngineeringReport(
        audiences=len(fixture.audiences),
        counterexamples=sum(item.expected_reminder_count == 0 for item in fixture.audiences),
        candidates=candidate_count or 0,
        waiting_before_governance=waiting_summary.waiting_governance,
        attempts_before_governance=attempts_before or 0,
        inbox_before_governance=inbox_before or 0,
        promoted=delivered_summary.promoted,
        claimed=delivered_summary.claimed,
        delivered=delivered_summary.delivered,
        delivery_attempts=delivery_attempts or 0,
        inbox_entries=inbox_entries or 0,
        replay_mismatches=int(replay != (context.reminder_id,)),
    )
    assert asdict(report) == fixture.expected_engineering_counts
