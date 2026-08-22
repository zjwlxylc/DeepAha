from datetime import UTC, date, datetime
from uuid import uuid7

import pytest
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from deepaha.notifications.models import (
    NotificationDeliveryAttemptModel,
    NotificationOutboxModel,
    ReminderPreferenceSnapshotModel,
)
from deepaha.notifications.models import (
    TestInboxEntryModel as InboxEntryModel,
)
from deepaha.opportunities.models import Opportunity, OpportunityEvent, OpportunityVersion
from deepaha.personal.models import (
    PersonalActionSnapshotModel,
    PersonalUserModel,
    UserStateSnapshotModel,
)
from tests.integration.test_phase4_persistence_contract import persist_complete_phase4_graph

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)

PHASE8_TABLES = {
    "reminder_preference_snapshots",
    "reminder_preference_idempotency_records",
    "notification_outbox",
    "notification_delivery_attempts",
    "test_inbox_entries",
}


def _seed_intent_graph(session: Session) -> NotificationOutboxModel:
    rule_set, profile, _, _ = persist_complete_phase4_graph(session)
    opportunity = session.get(Opportunity, rule_set.opportunity_id)
    version1 = session.get(OpportunityVersion, (rule_set.opportunity_id, 1))
    assert opportunity is not None
    assert version1 is not None
    version2 = OpportunityVersion(
        opportunity_id=opportunity.opportunity_id,
        version=2,
        effective_from=NOW,
        source_document_id=version1.source_document_id,
        source_evidence_ref_id=version1.source_evidence_ref_id,
        snapshot=version1.snapshot,
        field_evidence=version1.field_evidence,
        changes=[
            {
                "field_path": "application_window.closes_on",
                "before": "2026-09-20",
                "after": "2026-09-10",
                "evidence_ref_id": str(version1.source_evidence_ref_id),
            }
        ],
        content_sha256="8" * 64,
        review_status="NOT_REQUIRED",
        created_at=NOW,
    )
    session.add(version2)
    session.flush()
    event = OpportunityEvent(
        event_id=uuid7(),
        opportunity_id=opportunity.opportunity_id,
        from_version=1,
        to_version=2,
        event_type="DEADLINE_CHANGED",
        changed_fields=["application_window.closes_on"],
        changes=version2.changes,
        source_document_id=version1.source_document_id,
        source_evidence_ref_id=version1.source_evidence_ref_id,
        detected_at=NOW,
    )
    session.add(event)
    opportunity.current_version = 2
    session.flush()

    user_id = uuid7()
    user_state_id = uuid7()
    user = PersonalUserModel(
        user_id=user_id,
        user_state_id=user_state_id,
        active=True,
        created_at=NOW,
    )
    session.add(user)
    session.flush()
    state = UserStateSnapshotModel(
        user_state_snapshot_id=uuid7(),
        user_state_id=user_state_id,
        user_id=user_id,
        version=1,
        qualification_profile_snapshot_id=profile.profile_snapshot_id,
        qualification_profile_version=profile.version,
        life_stage="EARLY_CAREER",
        goal_types=["PUBLIC_SERVICE_EMPLOYMENT"],
        preference_regions=[],
        preference_types=[],
        skipped_fields=[],
        personalization_enabled=True,
        consent_version="phase6-consent-v1",
        allowed_purposes=["ACTION_TRACKING"],
        scenario_clock=date(2026, 8, 22),
        input_sha256="9" * 64,
        created_at=NOW,
    )
    session.add(state)
    session.flush()
    action = PersonalActionSnapshotModel(
        action_snapshot_id=uuid7(),
        action_id=uuid7(),
        user_id=user_id,
        version=1,
        opportunity_id=opportunity.opportunity_id,
        opportunity_version=2,
        saved=True,
        state="NOT_STARTED",
        material_items=[],
        last_event_id=uuid7(),
        input_sha256="a" * 64,
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
    session.add_all([action, preference])
    session.flush()
    outbox = NotificationOutboxModel(
        reminder_id=uuid7(),
        user_id=user_id,
        opportunity_id=opportunity.opportunity_id,
        event_id=event.event_id,
        from_version=1,
        to_version=2,
        old_closes_on=date(2026, 9, 20),
        new_closes_on=date(2026, 9, 10),
        direction="ADVANCED",
        previous_evidence_ref_id=version1.source_evidence_ref_id,
        current_evidence_ref_id=version2.source_evidence_ref_id,
        action_snapshot_id=action.action_snapshot_id,
        preference_snapshot_id=preference.preference_snapshot_id,
        user_state_snapshot_id=state.user_state_snapshot_id,
        consent_version=state.consent_version,
        detected_at=NOW,
        created_at=NOW,
        reminder_kind="DEADLINE_CHANGED",
        cadence="AS_SOON_AS_GOVERNED",
        target="TEST_INBOX",
        contract_version="0.7.0",
        status="WAITING_GOVERNANCE",
        available_at=None,
        lease_token=None,
        lease_until=None,
        claimed_at=None,
        attempt_count=0,
        next_attempt_at=None,
        last_error_code=None,
        terminal_at=None,
        updated_at=NOW,
    )
    session.add(outbox)
    session.flush()
    return outbox


def test_phase8_tables_and_operational_indexes_exist(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)

    assert set(inspector.get_table_names()) >= PHASE8_TABLES
    outbox_indexes = {item["name"] for item in inspector.get_indexes("notification_outbox")}
    assert outbox_indexes >= {
        "ix_notification_outbox_governance_wait",
        "ix_notification_outbox_available",
        "ix_notification_outbox_expired_lease",
    }
    inbox_indexes = {item["name"] for item in inspector.get_indexes("test_inbox_entries")}
    assert "ix_test_inbox_entries_owner_delivery" in inbox_indexes

    with migrated_engine.connect() as connection:
        rows = connection.execute(
            text(
                "select indexname, indexdef from pg_indexes "
                "where schemaname = current_schema() and indexname = any(:names)"
            ),
            {
                "names": [
                    "ix_reminder_preference_snapshots_owner_latest",
                    "ix_personal_action_snapshots_opportunity_owner_version",
                    "ix_user_state_snapshots_owner_version",
                    "ix_test_inbox_entries_owner_delivery",
                ]
            },
        ).mappings()
        index_definitions = {str(row["indexname"]): str(row["indexdef"]) for row in rows}

    assert "version DESC" in index_definitions["ix_reminder_preference_snapshots_owner_latest"]
    assert (
        "version DESC"
        in index_definitions["ix_personal_action_snapshots_opportunity_owner_version"]
    )
    assert "version DESC" in index_definitions["ix_user_state_snapshots_owner_version"]
    assert (
        "delivered_at DESC, inbox_entry_id DESC"
        in index_definitions["ix_test_inbox_entries_owner_delivery"]
    )


def test_logical_delivery_key_is_unique(session: Session) -> None:
    first = _seed_intent_graph(session)
    duplicate = NotificationOutboxModel(
        **{
            column.name: getattr(first, column.name)
            for column in NotificationOutboxModel.__table__.columns
            if column.name != "reminder_id"
        },
        reminder_id=uuid7(),
    )
    session.add(duplicate)

    with pytest.raises(IntegrityError):
        session.flush()


def test_event_opportunity_version_binding_is_enforced(session: Session) -> None:
    first = _seed_intent_graph(session)
    first.opportunity_id = uuid7()

    with pytest.raises(IntegrityError):
        session.flush()


def test_preference_attempt_and_inbox_are_insert_only(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        outbox = _seed_intent_graph(session)
        attempt = NotificationDeliveryAttemptModel(
            delivery_attempt_id=uuid7(),
            reminder_id=outbox.reminder_id,
            attempt_number=1,
            lease_token=uuid7(),
            adapter="POSTGRES_TEST_INBOX",
            outcome="SUCCEEDED",
            error_code=None,
            started_at=NOW,
            completed_at=NOW,
            contract_version="0.7.0",
        )
        entry = InboxEntryModel(
            inbox_entry_id=uuid7(),
            reminder_id=outbox.reminder_id,
            user_id=outbox.user_id,
            opportunity_id=outbox.opportunity_id,
            opportunity_public_id="opp_00000000000000000000000000000705",
            opportunity_title="Synthetic Phase 8 opportunity",
            event_id=outbox.event_id,
            from_version=outbox.from_version,
            to_version=outbox.to_version,
            old_closes_on=outbox.old_closes_on,
            new_closes_on=outbox.new_closes_on,
            direction=outbox.direction,
            previous_evidence_ref_id=outbox.previous_evidence_ref_id,
            current_evidence_ref_id=outbox.current_evidence_ref_id,
            previous_official_url="https://phase8.example.gov/v1",
            current_official_url="https://phase8.example.gov/v2",
            personal_detail_path=("/me/opportunities/opp_00000000000000000000000000000705"),
            detected_at=NOW,
            delivered_at=NOW,
            target="TEST_INBOX",
            contract_version="0.7.0",
        )
        session.add_all([attempt, entry])
        session.commit()
        preference_id = outbox.preference_snapshot_id
        attempt_id = attempt.delivery_attempt_id
        inbox_id = entry.inbox_entry_id

    statements = (
        (
            "update reminder_preference_snapshots set enabled = false "
            "where preference_snapshot_id = :id",
            preference_id,
        ),
        (
            "delete from notification_delivery_attempts where delivery_attempt_id = :id",
            attempt_id,
        ),
        (
            "update test_inbox_entries set opportunity_title = 'rewritten' "
            "where inbox_entry_id = :id",
            inbox_id,
        ),
    )
    for statement, row_id in statements:
        with pytest.raises(DBAPIError, match="immutable"), migrated_engine.begin() as connection:
            connection.execute(text(statement), {"id": row_id})

    with Session(migrated_engine) as session:
        assert (
            session.scalar(
                select(ReminderPreferenceSnapshotModel.enabled).where(
                    ReminderPreferenceSnapshotModel.preference_snapshot_id == preference_id
                )
            )
            is True
        )
        assert session.get(NotificationDeliveryAttemptModel, attempt_id) is not None
        inbox_entry = session.get(InboxEntryModel, inbox_id)
        assert inbox_entry is not None
        assert inbox_entry.opportunity_title == "Synthetic Phase 8 opportunity"
