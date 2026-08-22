"""phase6_personal_action

Revision ID: 20260822_0006
Revises: 20260822_0005
Create Date: 2026-08-22 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260822_0006"
down_revision: str | None = "20260822_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add owner-scoped Phase 6 profile, ranking, and action persistence."""
    op.drop_constraint(
        op.f("ck_profile_snapshots_synthetic_only"),
        "profile_snapshots",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_profile_snapshots_schema_version_v04"),
        "profile_snapshots",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_profile_snapshots_provenance_schema_version"),
        "profile_snapshots",
        "(synthetic is true and profile_schema_version = '0.4.0') or "
        "(synthetic is false and profile_schema_version = '0.5.0')",
    )

    op.create_table(
        "personal_users",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("user_state_id", sa.Uuid(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(user_id) = 7",
            name=op.f("ck_personal_users_user_id_uuid7"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(user_state_id) = 7",
            name=op.f("ck_personal_users_user_state_id_uuid7"),
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_personal_users")),
        sa.UniqueConstraint("user_state_id", name=op.f("uq_personal_users_user_state_id")),
        sa.UniqueConstraint("user_id", "user_state_id", name="uq_personal_users_user_state"),
    )
    op.create_table(
        "personal_auth_sessions",
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "token_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_personal_auth_sessions_token_sha256_format"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name=op.f("ck_personal_auth_sessions_expiry_after_creation"),
        ),
        sa.CheckConstraint(
            "revoked_at is null or revoked_at >= created_at",
            name=op.f("ck_personal_auth_sessions_revocation_after_creation"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["personal_users.user_id"],
            name=op.f("fk_personal_auth_sessions_user_id_personal_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("token_sha256", name=op.f("pk_personal_auth_sessions")),
    )
    op.create_table(
        "user_state_snapshots",
        sa.Column("user_state_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("user_state_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("qualification_profile_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("qualification_profile_version", sa.Integer(), nullable=False),
        sa.Column("life_stage", sa.String(length=24), nullable=True),
        sa.Column("goal_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("preference_regions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("preference_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("skipped_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("personalization_enabled", sa.Boolean(), nullable=False),
        sa.Column("consent_version", sa.String(length=32), nullable=False),
        sa.Column("allowed_purposes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scenario_clock", sa.Date(), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(user_state_snapshot_id) = 7",
            name=op.f("ck_user_state_snapshots_snapshot_id_uuid7"),
        ),
        sa.CheckConstraint(
            "version >= 1",
            name=op.f("ck_user_state_snapshots_positive_version"),
        ),
        sa.CheckConstraint(
            "qualification_profile_version >= 1",
            name=op.f("ck_user_state_snapshots_positive_profile_version"),
        ),
        sa.CheckConstraint(
            "life_stage is null or life_stage in "
            "('STUDENT', 'GRADUATING', 'EARLY_CAREER', 'UNEMPLOYED', 'OTHER')",
            name=op.f("ck_user_state_snapshots_life_stage_values"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(goal_types) = 'array'",
            name=op.f("ck_user_state_snapshots_goal_types_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(preference_regions) = 'array'",
            name=op.f("ck_user_state_snapshots_preference_regions_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(preference_types) = 'array'",
            name=op.f("ck_user_state_snapshots_preference_types_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(skipped_fields) = 'array'",
            name=op.f("ck_user_state_snapshots_skipped_fields_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(allowed_purposes) = 'array' "
            "and jsonb_array_length(allowed_purposes) >= 1",
            name=op.f("ck_user_state_snapshots_allowed_purposes_nonempty_array"),
        ),
        sa.CheckConstraint(
            "consent_version = 'phase6-consent-v1'",
            name=op.f("ck_user_state_snapshots_consent_version_v1"),
        ),
        sa.CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_user_state_snapshots_input_sha256_format"),
        ),
        sa.ForeignKeyConstraint(
            ["qualification_profile_snapshot_id"],
            ["profile_snapshots.profile_snapshot_id"],
            name=op.f(
                "fk_user_state_snapshots_qualification_profile_snapshot_id_profile_snapshots"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "user_state_id"],
            ["personal_users.user_id", "personal_users.user_state_id"],
            name=op.f("fk_user_state_snapshots_user_id_personal_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "user_state_snapshot_id",
            name=op.f("pk_user_state_snapshots"),
        ),
        sa.UniqueConstraint(
            "user_state_id",
            "version",
            name="uq_user_state_snapshots_stream_version",
        ),
        sa.UniqueConstraint(
            "user_id",
            "input_sha256",
            name="uq_user_state_snapshots_owner_input",
        ),
    )
    op.create_table(
        "personal_ranking_snapshots",
        sa.Column("ranking_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("user_state_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("qualification_profile_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("qualification_profile_version", sa.Integer(), nullable=False),
        sa.Column("scenario_clock", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("ranker_version", sa.String(length=64), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("omitted_rule_set_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(ranking_snapshot_id) = 7",
            name=op.f("ck_personal_ranking_snapshots_snapshot_id_uuid7"),
        ),
        sa.CheckConstraint(
            "qualification_profile_version >= 1",
            name=op.f("ck_personal_ranking_snapshots_positive_profile_version"),
        ),
        sa.CheckConstraint(
            "window_end = scenario_clock + 90",
            name=op.f("ck_personal_ranking_snapshots_ninety_day_window"),
        ),
        sa.CheckConstraint(
            "length(btrim(ranker_version)) >= 1",
            name=op.f("ck_personal_ranking_snapshots_ranker_version_nonempty"),
        ),
        sa.CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_personal_ranking_snapshots_input_sha256_format"),
        ),
        sa.CheckConstraint(
            "omitted_rule_set_count >= 0",
            name=op.f("ck_personal_ranking_snapshots_omitted_count_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["personal_users.user_id"],
            name=op.f("fk_personal_ranking_snapshots_user_id_personal_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_state_snapshot_id"],
            ["user_state_snapshots.user_state_snapshot_id"],
            name=op.f("fk_personal_ranking_snapshots_user_state_snapshot_id_user_state_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["qualification_profile_snapshot_id"],
            ["profile_snapshots.profile_snapshot_id"],
            name=op.f(
                "fk_personal_ranking_snapshots_qualification_profile_snapshot_id_profile_snapshots"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "ranking_snapshot_id",
            name=op.f("pk_personal_ranking_snapshots"),
        ),
        sa.UniqueConstraint(
            "ranking_snapshot_id",
            "user_id",
            name="uq_personal_ranking_owner",
        ),
        sa.UniqueConstraint(
            "user_id",
            "input_sha256",
            name="uq_personal_ranking_owner_input",
        ),
    )
    op.create_table(
        "personal_ranking_items",
        sa.Column("ranking_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("match_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("eligibility_status", sa.String(length=24), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.CheckConstraint(
            "ordinal between 1 and 3",
            name=op.f("ck_personal_ranking_items_ordinal_range"),
        ),
        sa.CheckConstraint(
            "opportunity_version >= 1",
            name=op.f("ck_personal_ranking_items_positive_opportunity_version"),
        ),
        sa.CheckConstraint(
            "eligibility_status in ('ELIGIBLE', 'LIKELY_ELIGIBLE', 'UNCERTAIN')",
            name=op.f("ck_personal_ranking_items_actionable_eligibility_values"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reason_codes) = 'array' and jsonb_array_length(reason_codes) >= 1",
            name=op.f("ck_personal_ranking_items_reason_codes_nonempty_array"),
        ),
        sa.ForeignKeyConstraint(
            ["ranking_snapshot_id", "user_id"],
            [
                "personal_ranking_snapshots.ranking_snapshot_id",
                "personal_ranking_snapshots.user_id",
            ],
            name=op.f("fk_personal_ranking_items_ranking_snapshot_id_personal_ranking_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            name=op.f("fk_personal_ranking_items_opportunity_id_opportunity_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["match_snapshot_id"],
            ["match_snapshots.snapshot_id"],
            name=op.f("fk_personal_ranking_items_match_snapshot_id_match_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "ranking_snapshot_id",
            "ordinal",
            name=op.f("pk_personal_ranking_items"),
        ),
        sa.UniqueConstraint(
            "ranking_snapshot_id",
            "opportunity_id",
            name=op.f("uq_personal_ranking_items_ranking_snapshot_id"),
        ),
        sa.UniqueConstraint(
            "ranking_snapshot_id",
            "match_snapshot_id",
            name="uq_personal_ranking_items_match_snapshot",
        ),
    )
    op.create_table(
        "personal_action_snapshots",
        sa.Column("action_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("saved", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("material_items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_event_id", sa.Uuid(), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(action_snapshot_id) = 7",
            name=op.f("ck_personal_action_snapshots_snapshot_id_uuid7"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(action_id) = 7",
            name=op.f("ck_personal_action_snapshots_action_id_uuid7"),
        ),
        sa.CheckConstraint(
            "version >= 1",
            name=op.f("ck_personal_action_snapshots_positive_version"),
        ),
        sa.CheckConstraint(
            "opportunity_version >= 1",
            name=op.f("ck_personal_action_snapshots_positive_opportunity_version"),
        ),
        sa.CheckConstraint(
            "state in ('NOT_STARTED', 'PREPARING', 'APPLIED', 'COMPLETED', 'DISMISSED')",
            name=op.f("ck_personal_action_snapshots_state_values"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(material_items) = 'array'",
            name=op.f("ck_personal_action_snapshots_material_items_array"),
        ),
        sa.CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_personal_action_snapshots_input_sha256_format"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["personal_users.user_id"],
            name=op.f("fk_personal_action_snapshots_user_id_personal_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            name=op.f("fk_personal_action_snapshots_opportunity_id_opportunity_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "action_snapshot_id",
            name=op.f("pk_personal_action_snapshots"),
        ),
        sa.UniqueConstraint(
            "action_snapshot_id",
            "user_id",
            name="uq_personal_action_owner",
        ),
        sa.UniqueConstraint(
            "action_id",
            "version",
            name="uq_personal_action_stream_version",
        ),
        sa.UniqueConstraint(
            "user_id",
            "opportunity_id",
            "input_sha256",
            name="uq_personal_action_owner_input",
        ),
    )
    op.create_table(
        "personal_action_events",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("action_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(event_id) = 7",
            name=op.f("ck_personal_action_events_event_id_uuid7"),
        ),
        sa.CheckConstraint(
            "event_type in ('SAVED_CHANGED', 'OFFICIAL_LINK_OPENED', "
            "'MATERIAL_PLAN_CHANGED', 'ACTION_STATE_CHANGED')",
            name=op.f("ck_personal_action_events_event_type_values"),
        ),
        sa.CheckConstraint(
            "payload_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_personal_action_events_payload_sha256_format"),
        ),
        sa.ForeignKeyConstraint(
            ["action_snapshot_id", "user_id"],
            ["personal_action_snapshots.action_snapshot_id", "personal_action_snapshots.user_id"],
            name=op.f("fk_personal_action_events_action_snapshot_id_personal_action_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_personal_action_events")),
    )
    op.create_table(
        "personal_idempotency_records",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("key_sha256", sa.String(length=64), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("resource_kind", sa.String(length=24), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("response_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(btrim(operation)) >= 1",
            name=op.f("ck_personal_idempotency_records_operation_nonempty"),
        ),
        sa.CheckConstraint(
            "key_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_personal_idempotency_records_key_sha256_format"),
        ),
        sa.CheckConstraint(
            "request_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_personal_idempotency_records_request_sha256_format"),
        ),
        sa.CheckConstraint(
            "resource_kind in ('PROFILE', 'RANKING', 'ACTION', 'ACTION_EVENT')",
            name=op.f("ck_personal_idempotency_records_resource_kind_values"),
        ),
        sa.CheckConstraint(
            "response_version >= 1",
            name=op.f("ck_personal_idempotency_records_positive_response_version"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["personal_users.user_id"],
            name=op.f("fk_personal_idempotency_records_user_id_personal_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "user_id",
            "operation",
            "key_sha256",
            name=op.f("pk_personal_idempotency_records"),
        ),
    )


def downgrade() -> None:
    """Refuse to discard personal profile, ranking, action, or provenance evidence."""
    connection = op.get_bind()
    contains_rows = connection.execute(
        sa.text(
            "SELECT "
            "EXISTS (SELECT 1 FROM personal_users LIMIT 1) OR "
            "EXISTS (SELECT 1 FROM profile_snapshots WHERE synthetic IS FALSE LIMIT 1)"
        )
    ).scalar_one()
    if contains_rows:
        raise RuntimeError("cannot downgrade Phase 6 while personal evidence exists")

    op.drop_table("personal_idempotency_records")
    op.drop_table("personal_action_events")
    op.drop_table("personal_action_snapshots")
    op.drop_table("personal_ranking_items")
    op.drop_table("personal_ranking_snapshots")
    op.drop_table("user_state_snapshots")
    op.drop_table("personal_auth_sessions")
    op.drop_table("personal_users")
    op.drop_constraint(
        op.f("ck_profile_snapshots_provenance_schema_version"),
        "profile_snapshots",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_profile_snapshots_schema_version_v04"),
        "profile_snapshots",
        "profile_schema_version = '0.4.0'",
    )
    op.create_check_constraint(
        op.f("ck_profile_snapshots_synthetic_only"),
        "profile_snapshots",
        "synthetic is true",
    )
