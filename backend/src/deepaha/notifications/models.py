from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
    desc,
)
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class ReminderPreferenceSnapshotModel(Base):
    __tablename__ = "reminder_preference_snapshots"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(preference_snapshot_id) = 7",
            name="preference_snapshot_id_uuid7",
        ),
        CheckConstraint(
            "uuid_extract_version(preference_id) = 7",
            name="preference_id_uuid7",
        ),
        CheckConstraint("version >= 1", name="positive_version"),
        CheckConstraint(
            "(version = 1 and predecessor_snapshot_id is null) or "
            "(version > 1 and predecessor_snapshot_id is not null)",
            name="predecessor_version_coherence",
        ),
        CheckConstraint(
            "predecessor_snapshot_id is null or predecessor_snapshot_id <> preference_snapshot_id",
            name="predecessor_not_self",
        ),
        CheckConstraint("actor_user_id = user_id", name="actor_is_owner"),
        CheckConstraint(
            "reminder_kind = 'DEADLINE_CHANGED'",
            name="reminder_kind_value",
        ),
        CheckConstraint(
            "cadence = 'AS_SOON_AS_GOVERNED'",
            name="cadence_value",
        ),
        CheckConstraint("target = 'TEST_INBOX'", name="target_value"),
        CheckConstraint(
            "preference_policy_version = 'phase8-deadline-reminder-v1'",
            name="policy_version_value",
        ),
        CheckConstraint("contract_version = '0.7.0'", name="contract_version_value"),
        ForeignKeyConstraint(
            ["predecessor_snapshot_id"],
            ["reminder_preference_snapshots.preference_snapshot_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "preference_id",
            "version",
            name="uq_reminder_preference_stream_version",
        ),
        UniqueConstraint(
            "preference_snapshot_id",
            "user_id",
            name="uq_reminder_preference_snapshot_owner",
        ),
        Index(
            "ix_reminder_preference_snapshots_owner_latest",
            "user_id",
            "reminder_kind",
            desc("version"),
        ),
    )

    preference_snapshot_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    preference_id: Mapped[UUID] = mapped_column(Uuid)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("personal_users.user_id", ondelete="RESTRICT"),
    )
    version: Mapped[int] = mapped_column(Integer)
    predecessor_snapshot_id: Mapped[UUID | None] = mapped_column(Uuid)
    reminder_kind: Mapped[str] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean)
    cadence: Mapped[str] = mapped_column(String(32))
    target: Mapped[str] = mapped_column(String(24))
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("personal_users.user_id", ondelete="RESTRICT"),
    )
    preference_policy_version: Mapped[str] = mapped_column(String(48))
    contract_version: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReminderPreferenceIdempotencyRecordModel(Base):
    __tablename__ = "reminder_preference_idempotency_records"
    __table_args__ = (
        CheckConstraint("length(btrim(operation)) >= 1", name="operation_nonempty"),
        CheckConstraint("key_sha256 ~ '^[0-9a-f]{64}$'", name="key_sha256_format"),
        CheckConstraint(
            "request_sha256 ~ '^[0-9a-f]{64}$'",
            name="request_hash_format",
        ),
        CheckConstraint("resource_kind = 'PREFERENCE'", name="resource_kind_value"),
        CheckConstraint("response_version >= 1", name="positive_version"),
        PrimaryKeyConstraint("user_id", "operation", "key_sha256"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("personal_users.user_id", ondelete="RESTRICT"),
    )
    operation: Mapped[str] = mapped_column(String(64))
    key_sha256: Mapped[str] = mapped_column(String(64))
    request_sha256: Mapped[str] = mapped_column(String(64))
    resource_kind: Mapped[str] = mapped_column(String(24))
    resource_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "reminder_preference_snapshots.preference_snapshot_id",
            ondelete="RESTRICT",
        ),
    )
    response_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NotificationOutboxModel(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(reminder_id) = 7", name="reminder_id_uuid7"),
        CheckConstraint("to_version = from_version + 1", name="consecutive_versions"),
        CheckConstraint(
            "old_closes_on <> new_closes_on and "
            "((direction = 'ADVANCED' and new_closes_on < old_closes_on) or "
            "(direction = 'EXTENDED' and new_closes_on > old_closes_on))",
            name="deadline_direction_coherence",
        ),
        CheckConstraint("reminder_kind = 'DEADLINE_CHANGED'", name="reminder_kind_value"),
        CheckConstraint("cadence = 'AS_SOON_AS_GOVERNED'", name="cadence_value"),
        CheckConstraint("target = 'TEST_INBOX'", name="target_value"),
        CheckConstraint("contract_version = '0.7.0'", name="contract_version_value"),
        CheckConstraint(
            "status in ('WAITING_GOVERNANCE', 'AVAILABLE', 'LEASED', "
            "'DELIVERED', 'SUPPRESSED', 'FAILED')",
            name="status_values",
        ),
        CheckConstraint("attempt_count between 0 and 3", name="attempt_count_range"),
        CheckConstraint(
            "(status = 'LEASED' and lease_token is not null and lease_until is not null "
            "and claimed_at is not null) or "
            "(status <> 'LEASED' and lease_token is null and lease_until is null "
            "and claimed_at is null)",
            name="lease_state_coherence",
        ),
        CheckConstraint(
            "(status in ('DELIVERED', 'SUPPRESSED', 'FAILED') and terminal_at is not null) or "
            "(status not in ('DELIVERED', 'SUPPRESSED', 'FAILED') and terminal_at is null)",
            name="terminal_state_coherence",
        ),
        CheckConstraint(
            "(status = 'WAITING_GOVERNANCE' and available_at is null) or "
            "(status <> 'WAITING_GOVERNANCE' and available_at is not null)",
            name="availability_state_coherence",
        ),
        CheckConstraint(
            "last_error_code is null or last_error_code ~ '^[A-Z][A-Z0-9_]{0,63}$'",
            name="last_error_code_format",
        ),
        ForeignKeyConstraint(
            ["event_id", "opportunity_id", "to_version"],
            [
                "opportunity_events.event_id",
                "opportunity_events.opportunity_id",
                "opportunity_events.to_version",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["opportunity_id", "to_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "user_id",
            "event_id",
            "to_version",
            "reminder_kind",
            "target",
            name="uq_notification_outbox_logical_delivery",
        ),
        Index(
            "ix_notification_outbox_governance_wait",
            "status",
            "created_at",
            "reminder_id",
        ),
        Index(
            "ix_notification_outbox_available",
            "status",
            "next_attempt_at",
            "reminder_id",
        ),
        Index(
            "ix_notification_outbox_expired_lease",
            "status",
            "lease_until",
            "reminder_id",
        ),
    )

    reminder_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("personal_users.user_id", ondelete="RESTRICT"),
    )
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    event_id: Mapped[UUID] = mapped_column(Uuid)
    from_version: Mapped[int] = mapped_column(Integer)
    to_version: Mapped[int] = mapped_column(Integer)
    old_closes_on: Mapped[date] = mapped_column(Date)
    new_closes_on: Mapped[date] = mapped_column(Date)
    direction: Mapped[str] = mapped_column(String(16))
    previous_evidence_ref_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("evidence_refs.evidence_ref_id", ondelete="RESTRICT"),
    )
    current_evidence_ref_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("evidence_refs.evidence_ref_id", ondelete="RESTRICT"),
    )
    action_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("personal_action_snapshots.action_snapshot_id", ondelete="RESTRICT"),
    )
    preference_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "reminder_preference_snapshots.preference_snapshot_id",
            ondelete="RESTRICT",
        ),
    )
    user_state_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user_state_snapshots.user_state_snapshot_id", ondelete="RESTRICT"),
    )
    consent_version: Mapped[str] = mapped_column(String(32))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reminder_kind: Mapped[str] = mapped_column(String(32))
    cadence: Mapped[str] = mapped_column(String(32))
    target: Mapped[str] = mapped_column(String(24))
    contract_version: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32))
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NotificationDeliveryAttemptModel(Base):
    __tablename__ = "notification_delivery_attempts"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(delivery_attempt_id) = 7",
            name="delivery_attempt_id_uuid7",
        ),
        CheckConstraint("attempt_number between 1 and 3", name="attempt_number_range"),
        CheckConstraint("uuid_extract_version(lease_token) = 7", name="lease_token_uuid7"),
        CheckConstraint("adapter = 'POSTGRES_TEST_INBOX'", name="adapter_value"),
        CheckConstraint(
            "outcome in ('SUCCEEDED', 'TRANSIENT_FAILURE', 'PERMANENT_FAILURE')",
            name="outcome_values",
        ),
        CheckConstraint(
            "(outcome = 'SUCCEEDED' and error_code is null) or "
            "(outcome <> 'SUCCEEDED' and error_code is not null)",
            name="outcome_error_coherence",
        ),
        CheckConstraint(
            "error_code is null or error_code ~ '^[A-Z][A-Z0-9_]{0,63}$'",
            name="error_code_format",
        ),
        CheckConstraint("completed_at >= started_at", name="attempt_time_order"),
        CheckConstraint("contract_version = '0.7.0'", name="contract_version_value"),
        UniqueConstraint(
            "reminder_id",
            "attempt_number",
            name="uq_notification_delivery_attempt_number",
        ),
    )

    delivery_attempt_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    reminder_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("notification_outbox.reminder_id", ondelete="RESTRICT"),
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    lease_token: Mapped[UUID] = mapped_column(Uuid)
    adapter: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(24))
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    contract_version: Mapped[str] = mapped_column(String(16))


class TestInboxEntryModel(Base):
    __tablename__ = "test_inbox_entries"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(inbox_entry_id) = 7",
            name="inbox_entry_id_uuid7",
        ),
        CheckConstraint("to_version = from_version + 1", name="consecutive_versions"),
        CheckConstraint(
            "old_closes_on <> new_closes_on and "
            "((direction = 'ADVANCED' and new_closes_on < old_closes_on) or "
            "(direction = 'EXTENDED' and new_closes_on > old_closes_on))",
            name="deadline_direction_coherence",
        ),
        CheckConstraint("target = 'TEST_INBOX'", name="target_value"),
        CheckConstraint("contract_version = '0.7.0'", name="contract_version_value"),
        CheckConstraint("delivered_at >= detected_at", name="delivery_time_order"),
        CheckConstraint(
            "opportunity_public_id ~ '^opp_[0-9a-f]{32}$'",
            name="opportunity_public_id_format",
        ),
        CheckConstraint(
            "personal_detail_path = '/me/opportunities/' || opportunity_public_id",
            name="personal_detail_path_value",
        ),
        CheckConstraint(
            "length(btrim(opportunity_title)) >= 1",
            name="opportunity_title_nonempty",
        ),
        UniqueConstraint("reminder_id", name="uq_test_inbox_entries_reminder"),
        Index(
            "ix_test_inbox_entries_owner_delivery",
            "user_id",
            desc("delivered_at"),
            desc("inbox_entry_id"),
        ),
    )

    inbox_entry_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    reminder_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("notification_outbox.reminder_id", ondelete="RESTRICT"),
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("personal_users.user_id", ondelete="RESTRICT"),
    )
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_public_id: Mapped[str] = mapped_column(String(36))
    opportunity_title: Mapped[str] = mapped_column(String(300))
    event_id: Mapped[UUID] = mapped_column(Uuid)
    from_version: Mapped[int] = mapped_column(Integer)
    to_version: Mapped[int] = mapped_column(Integer)
    old_closes_on: Mapped[date] = mapped_column(Date)
    new_closes_on: Mapped[date] = mapped_column(Date)
    direction: Mapped[str] = mapped_column(String(16))
    previous_evidence_ref_id: Mapped[UUID] = mapped_column(Uuid)
    current_evidence_ref_id: Mapped[UUID] = mapped_column(Uuid)
    previous_official_url: Mapped[str] = mapped_column(String(2048))
    current_official_url: Mapped[str] = mapped_column(String(2048))
    personal_detail_path: Mapped[str] = mapped_column(String(80))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    target: Mapped[str] = mapped_column(String(24))
    contract_version: Mapped[str] = mapped_column(String(16))


__all__ = [
    "NotificationDeliveryAttemptModel",
    "NotificationOutboxModel",
    "ReminderPreferenceIdempotencyRecordModel",
    "ReminderPreferenceSnapshotModel",
    "TestInboxEntryModel",
]
