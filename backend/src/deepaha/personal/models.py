from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class PersonalUserModel(Base):
    __tablename__ = "personal_users"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(user_id) = 7", name="user_id_uuid7"),
        CheckConstraint("uuid_extract_version(user_state_id) = 7", name="user_state_id_uuid7"),
        UniqueConstraint("user_state_id"),
        UniqueConstraint("user_id", "user_state_id", name="uq_personal_users_user_state"),
    )

    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_state_id: Mapped[UUID] = mapped_column(Uuid)
    active: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PersonalAuthSessionModel(Base):
    __tablename__ = "personal_auth_sessions"
    __table_args__ = (
        CheckConstraint("token_sha256 ~ '^[0-9a-f]{64}$'", name="token_sha256_format"),
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        CheckConstraint(
            "revoked_at is null or revoked_at >= created_at",
            name="revocation_after_creation",
        ),
    )

    token_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("personal_users.user_id", ondelete="RESTRICT"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserStateSnapshotModel(Base):
    __tablename__ = "user_state_snapshots"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(user_state_snapshot_id) = 7",
            name="snapshot_id_uuid7",
        ),
        CheckConstraint("version >= 1", name="positive_version"),
        CheckConstraint("qualification_profile_version >= 1", name="positive_profile_version"),
        CheckConstraint(
            "life_stage is null or life_stage in "
            "('STUDENT', 'GRADUATING', 'EARLY_CAREER', 'UNEMPLOYED', 'OTHER')",
            name="life_stage_values",
        ),
        CheckConstraint("jsonb_typeof(goal_types) = 'array'", name="goal_types_array"),
        CheckConstraint(
            "jsonb_typeof(preference_regions) = 'array'",
            name="preference_regions_array",
        ),
        CheckConstraint(
            "jsonb_typeof(preference_types) = 'array'",
            name="preference_types_array",
        ),
        CheckConstraint("jsonb_typeof(skipped_fields) = 'array'", name="skipped_fields_array"),
        CheckConstraint(
            "jsonb_typeof(allowed_purposes) = 'array' "
            "and jsonb_array_length(allowed_purposes) >= 1",
            name="allowed_purposes_nonempty_array",
        ),
        CheckConstraint("consent_version = 'phase6-consent-v1'", name="consent_version_v1"),
        CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="input_sha256_format"),
        ForeignKeyConstraint(
            ["user_id", "user_state_id"],
            ["personal_users.user_id", "personal_users.user_state_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("user_state_id", "version", name="uq_user_state_snapshots_stream_version"),
        UniqueConstraint("user_id", "input_sha256", name="uq_user_state_snapshots_owner_input"),
    )

    user_state_snapshot_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_state_id: Mapped[UUID] = mapped_column(Uuid)
    user_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    qualification_profile_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("profile_snapshots.profile_snapshot_id", ondelete="RESTRICT"),
    )
    qualification_profile_version: Mapped[int] = mapped_column(Integer)
    life_stage: Mapped[str | None] = mapped_column(String(24))
    goal_types: Mapped[list[str]] = mapped_column(JSONB)
    preference_regions: Mapped[list[str]] = mapped_column(JSONB)
    preference_types: Mapped[list[str]] = mapped_column(JSONB)
    skipped_fields: Mapped[list[str]] = mapped_column(JSONB)
    personalization_enabled: Mapped[bool] = mapped_column(Boolean)
    consent_version: Mapped[str] = mapped_column(String(32))
    allowed_purposes: Mapped[list[str]] = mapped_column(JSONB)
    scenario_clock: Mapped[date] = mapped_column(Date)
    input_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PersonalRankingSnapshotModel(Base):
    __tablename__ = "personal_ranking_snapshots"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(ranking_snapshot_id) = 7", name="snapshot_id_uuid7"),
        CheckConstraint("qualification_profile_version >= 1", name="positive_profile_version"),
        CheckConstraint("window_end = scenario_clock + 90", name="ninety_day_window"),
        CheckConstraint("length(btrim(ranker_version)) >= 1", name="ranker_version_nonempty"),
        CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="input_sha256_format"),
        CheckConstraint("omitted_rule_set_count >= 0", name="omitted_count_nonnegative"),
        UniqueConstraint("ranking_snapshot_id", "user_id", name="uq_personal_ranking_owner"),
        UniqueConstraint("user_id", "input_sha256", name="uq_personal_ranking_owner_input"),
    )

    ranking_snapshot_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("personal_users.user_id", ondelete="RESTRICT"),
    )
    user_state_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user_state_snapshots.user_state_snapshot_id", ondelete="RESTRICT"),
    )
    qualification_profile_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("profile_snapshots.profile_snapshot_id", ondelete="RESTRICT"),
    )
    qualification_profile_version: Mapped[int] = mapped_column(Integer)
    scenario_clock: Mapped[date] = mapped_column(Date)
    window_end: Mapped[date] = mapped_column(Date)
    ranker_version: Mapped[str] = mapped_column(String(64))
    input_sha256: Mapped[str] = mapped_column(String(64))
    omitted_rule_set_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PersonalRankingItemModel(Base):
    __tablename__ = "personal_ranking_items"
    __table_args__ = (
        CheckConstraint("ordinal between 1 and 3", name="ordinal_range"),
        CheckConstraint("opportunity_version >= 1", name="positive_opportunity_version"),
        CheckConstraint(
            "eligibility_status in ('ELIGIBLE', 'LIKELY_ELIGIBLE', 'UNCERTAIN')",
            name="actionable_eligibility_values",
        ),
        CheckConstraint(
            "jsonb_typeof(reason_codes) = 'array' and jsonb_array_length(reason_codes) >= 1",
            name="reason_codes_nonempty_array",
        ),
        ForeignKeyConstraint(
            ["ranking_snapshot_id", "user_id"],
            [
                "personal_ranking_snapshots.ranking_snapshot_id",
                "personal_ranking_snapshots.user_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            ondelete="RESTRICT",
        ),
        PrimaryKeyConstraint("ranking_snapshot_id", "ordinal"),
        UniqueConstraint(
            "ranking_snapshot_id",
            "opportunity_id",
            name="uq_personal_ranking_items_ranking_snapshot_id",
        ),
        UniqueConstraint(
            "ranking_snapshot_id",
            "match_snapshot_id",
            name="uq_personal_ranking_items_match_snapshot",
        ),
    )

    ranking_snapshot_id: Mapped[UUID] = mapped_column(Uuid)
    ordinal: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    match_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("match_snapshots.snapshot_id", ondelete="RESTRICT"),
    )
    eligibility_status: Mapped[str] = mapped_column(String(24))
    reason_codes: Mapped[list[str]] = mapped_column(JSONB)
    deadline: Mapped[date] = mapped_column(Date)


class PersonalActionSnapshotModel(Base):
    __tablename__ = "personal_action_snapshots"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(action_snapshot_id) = 7", name="snapshot_id_uuid7"),
        CheckConstraint("uuid_extract_version(action_id) = 7", name="action_id_uuid7"),
        CheckConstraint("version >= 1", name="positive_version"),
        CheckConstraint("opportunity_version >= 1", name="positive_opportunity_version"),
        CheckConstraint(
            "state in ('NOT_STARTED', 'PREPARING', 'APPLIED', 'COMPLETED', 'DISMISSED')",
            name="state_values",
        ),
        CheckConstraint("jsonb_typeof(material_items) = 'array'", name="material_items_array"),
        CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="input_sha256_format"),
        ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("action_snapshot_id", "user_id", name="uq_personal_action_owner"),
        UniqueConstraint("action_id", "version", name="uq_personal_action_stream_version"),
        UniqueConstraint(
            "user_id", "opportunity_id", "input_sha256", name="uq_personal_action_owner_input"
        ),
    )

    action_snapshot_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    action_id: Mapped[UUID] = mapped_column(Uuid)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("personal_users.user_id", ondelete="RESTRICT"),
    )
    version: Mapped[int] = mapped_column(Integer)
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    saved: Mapped[bool] = mapped_column(Boolean)
    state: Mapped[str] = mapped_column(String(24))
    material_items: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    last_event_id: Mapped[UUID] = mapped_column(Uuid)
    input_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PersonalActionEventModel(Base):
    __tablename__ = "personal_action_events"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(event_id) = 7", name="event_id_uuid7"),
        CheckConstraint(
            "event_type in ('SAVED_CHANGED', 'OFFICIAL_LINK_OPENED', "
            "'MATERIAL_PLAN_CHANGED', 'ACTION_STATE_CHANGED')",
            name="event_type_values",
        ),
        CheckConstraint("payload_sha256 ~ '^[0-9a-f]{64}$'", name="payload_sha256_format"),
        ForeignKeyConstraint(
            ["action_snapshot_id", "user_id"],
            ["personal_action_snapshots.action_snapshot_id", "personal_action_snapshots.user_id"],
            ondelete="RESTRICT",
        ),
    )

    event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    action_id: Mapped[UUID] = mapped_column(Uuid)
    action_snapshot_id: Mapped[UUID] = mapped_column(Uuid)
    user_id: Mapped[UUID] = mapped_column(Uuid)
    event_type: Mapped[str] = mapped_column(String(32))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PersonalIdempotencyRecordModel(Base):
    __tablename__ = "personal_idempotency_records"
    __table_args__ = (
        CheckConstraint("length(btrim(operation)) >= 1", name="operation_nonempty"),
        CheckConstraint("key_sha256 ~ '^[0-9a-f]{64}$'", name="key_sha256_format"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_sha256_format"),
        CheckConstraint(
            "resource_kind in ('PROFILE', 'RANKING', 'ACTION', 'ACTION_EVENT')",
            name="resource_kind_values",
        ),
        CheckConstraint("response_version >= 1", name="positive_response_version"),
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
    resource_id: Mapped[UUID] = mapped_column(Uuid)
    response_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = [
    "PersonalActionEventModel",
    "PersonalActionSnapshotModel",
    "PersonalAuthSessionModel",
    "PersonalIdempotencyRecordModel",
    "PersonalRankingItemModel",
    "PersonalRankingSnapshotModel",
    "PersonalUserModel",
    "UserStateSnapshotModel",
]
