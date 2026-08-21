"""phase3_opportunity_history

Revision ID: 20260822_0003
Revises: 20260821_0002
Create Date: 2026-08-22 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260822_0003"
down_revision: str | None = "20260821_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOCUMENT_ROLES = (
    "'PRIMARY_NOTICE', 'ATTACHMENT', 'POSITION_TABLE', 'CORRECTION', "
    "'DEADLINE_EXTENSION', 'CANCELLATION', 'RESULT', 'OFFICIAL_GUIDANCE'"
)
EVIDENCE_FOREIGN_KEY_COLUMNS = ["source_evidence_ref_id", "source_document_id"]
EVIDENCE_FOREIGN_KEY_TARGET = ["evidence_refs.evidence_ref_id", "evidence_refs.document_id"]
PHASE3_TABLES = (
    "opportunity_versions",
    "opportunity_events",
    "document_opportunity_links",
    "opportunity_resolution_candidates",
    "opportunity_aliases",
    "opportunity_identity_actions",
    "opportunity_identity_action_members",
)


def upgrade() -> None:
    """Add immutable Opportunity history and identity audit tables."""
    op.create_unique_constraint(
        op.f("uq_evidence_refs_evidence_ref_id"),
        "evidence_refs",
        ["evidence_ref_id", "document_id"],
    )

    op.create_table(
        "opportunity_versions",
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=False),
        sa.Column("source_evidence_ref_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("field_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version >= 1",
            name=op.f("ck_opportunity_versions_positive_version"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(snapshot) = 'object'",
            name=op.f("ck_opportunity_versions_snapshot_object"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(field_evidence) = 'array'",
            name=op.f("ck_opportunity_versions_field_evidence_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(changes) = 'array' and jsonb_array_length(changes) >= 1",
            name=op.f("ck_opportunity_versions_changes_nonempty_array"),
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_opportunity_versions_content_sha256_format"),
        ),
        sa.CheckConstraint(
            "review_status in ('NOT_REQUIRED', 'PENDING', 'APPROVED', 'REJECTED')",
            name=op.f("ck_opportunity_versions_review_status_values"),
        ),
        sa.CheckConstraint(
            "created_at >= effective_from",
            name=op.f("ck_opportunity_versions_timestamp_order"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.opportunity_id"],
            name=op.f("fk_opportunity_versions_opportunity_id_opportunities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            EVIDENCE_FOREIGN_KEY_COLUMNS,
            EVIDENCE_FOREIGN_KEY_TARGET,
            name=op.f("fk_opportunity_versions_source_evidence_ref_id_evidence_refs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "opportunity_id",
            "version",
            name=op.f("pk_opportunity_versions"),
        ),
        sa.UniqueConstraint(
            "opportunity_id",
            "content_sha256",
            name=op.f("uq_opportunity_versions_opportunity_id"),
        ),
    )

    op.create_table(
        "opportunity_identity_actions",
        sa.Column("action_id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("action_type", sa.String(length=24), nullable=False),
        sa.Column("reversal_of_action_id", sa.Uuid(), nullable=True),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.Column("source_evidence_ref_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(action_id) = 7",
            name=op.f("ck_opportunity_identity_actions_action_id_uuid7"),
        ),
        sa.CheckConstraint(
            "action_type in ('MERGE', 'SPLIT', 'MERGE_REVERSAL', 'SPLIT_REVERSAL')",
            name=op.f("ck_opportunity_identity_actions_action_type_values"),
        ),
        sa.CheckConstraint(
            "(action_type in ('MERGE', 'SPLIT') and reversal_of_action_id is null) or "
            "(action_type in ('MERGE_REVERSAL', 'SPLIT_REVERSAL') and "
            "reversal_of_action_id is not null)",
            name=op.f("ck_opportunity_identity_actions_reversal_shape"),
        ),
        sa.CheckConstraint(
            "length(btrim(actor)) >= 1",
            name=op.f("ck_opportunity_identity_actions_actor_nonempty"),
        ),
        sa.CheckConstraint(
            "length(btrim(reason)) >= 1",
            name=op.f("ck_opportunity_identity_actions_reason_nonempty"),
        ),
        sa.CheckConstraint(
            "(source_document_id is null) = (source_evidence_ref_id is null)",
            name=op.f("ck_opportunity_identity_actions_source_evidence_pair"),
        ),
        sa.ForeignKeyConstraint(
            ["reversal_of_action_id"],
            ["opportunity_identity_actions.action_id"],
            name=op.f(
                "fk_opportunity_identity_actions_reversal_of_action_id_opportunity_identity_actions"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            EVIDENCE_FOREIGN_KEY_COLUMNS,
            EVIDENCE_FOREIGN_KEY_TARGET,
            name=op.f("fk_opportunity_identity_actions_source_evidence_ref_id_evidence_refs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("action_id", name=op.f("pk_opportunity_identity_actions")),
        sa.UniqueConstraint(
            "reversal_of_action_id",
            name=op.f("uq_opportunity_identity_actions_reversal_of_action_id"),
        ),
    )

    op.create_table(
        "opportunity_events",
        sa.Column("event_id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("from_version", sa.Integer(), nullable=True),
        sa.Column("to_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("changed_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=False),
        sa.Column("source_evidence_ref_id", sa.Uuid(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(event_id) = 7",
            name=op.f("ck_opportunity_events_event_id_uuid7"),
        ),
        sa.CheckConstraint(
            "event_type in ('CREATED', 'UPDATED', 'CORRECTED', 'DEADLINE_CHANGED', "
            "'ATTACHMENT_REPLACED', 'CANCELLED', 'REOPENED')",
            name=op.f("ck_opportunity_events_event_type_values"),
        ),
        sa.CheckConstraint(
            "(event_type = 'CREATED' and from_version is null and to_version = 1) or "
            "(event_type <> 'CREATED' and from_version is not null and "
            "to_version = from_version + 1)",
            name=op.f("ck_opportunity_events_version_transition"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(changed_fields) = 'array' and jsonb_array_length(changed_fields) >= 1",
            name=op.f("ck_opportunity_events_changed_fields_nonempty_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(changes) = 'array' and jsonb_array_length(changes) >= 1",
            name=op.f("ck_opportunity_events_changes_nonempty_array"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id", "to_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            name=op.f("fk_opportunity_events_opportunity_id_opportunity_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id", "from_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            name="fk_opportunity_events_from_version_opportunity_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            EVIDENCE_FOREIGN_KEY_COLUMNS,
            EVIDENCE_FOREIGN_KEY_TARGET,
            name=op.f("fk_opportunity_events_source_evidence_ref_id_evidence_refs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_opportunity_events")),
        sa.UniqueConstraint(
            "opportunity_id",
            "to_version",
            name=op.f("uq_opportunity_events_opportunity_id"),
        ),
    )

    op.create_table(
        "document_opportunity_links",
        sa.Column("link_id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("resolution_key", sa.Text(), nullable=False),
        sa.Column("resolver_version", sa.String(length=64), nullable=False),
        sa.Column("source_evidence_ref_id", sa.Uuid(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by_identity_action_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "uuid_extract_version(link_id) = 7",
            name=op.f("ck_document_opportunity_links_link_id_uuid7"),
        ),
        sa.CheckConstraint(
            f"role in ({DOCUMENT_ROLES})",
            name=op.f("ck_document_opportunity_links_role_values"),
        ),
        sa.CheckConstraint(
            "length(btrim(resolution_key)) >= 1",
            name=op.f("ck_document_opportunity_links_resolution_key_nonempty"),
        ),
        sa.CheckConstraint(
            "length(btrim(resolver_version)) >= 1",
            name=op.f("ck_document_opportunity_links_resolver_version_nonempty"),
        ),
        sa.CheckConstraint(
            "(ended_at is null) = (ended_by_identity_action_id is null)",
            name=op.f("ck_document_opportunity_links_ended_pair"),
        ),
        sa.CheckConstraint(
            "ended_at is null or ended_at >= linked_at",
            name=op.f("ck_document_opportunity_links_timestamp_order"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.document_id"],
            name=op.f("fk_document_opportunity_links_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.opportunity_id"],
            name=op.f("fk_document_opportunity_links_opportunity_id_opportunities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ended_by_identity_action_id"],
            ["opportunity_identity_actions.action_id"],
            name=op.f(
                "fk_document_opportunity_links_ended_by_identity_action_id_"
                "opportunity_identity_actions"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_evidence_ref_id", "document_id"],
            EVIDENCE_FOREIGN_KEY_TARGET,
            name=op.f("fk_document_opportunity_links_source_evidence_ref_id_evidence_refs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("link_id", name=op.f("pk_document_opportunity_links")),
        sa.UniqueConstraint(
            "document_id",
            "opportunity_id",
            "role",
            name=op.f("uq_document_opportunity_links_document_id"),
        ),
    )
    op.create_index(
        "uq_document_opportunity_links_active_document",
        "document_opportunity_links",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("ended_at is null"),
    )

    op.create_table(
        "opportunity_resolution_candidates",
        sa.Column("candidate_id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column(
            "candidate_opportunity_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("proposed_role", sa.String(length=32), nullable=False),
        sa.Column("proposed_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("resolver_version", sa.String(length=64), nullable=False),
        sa.Column("source_evidence_ref_id", sa.Uuid(), nullable=False),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(candidate_id) = 7",
            name=op.f("ck_opportunity_resolution_candidates_candidate_id_uuid7"),
        ),
        sa.CheckConstraint(
            f"proposed_role in ({DOCUMENT_ROLES})",
            name=op.f("ck_opportunity_resolution_candidates_proposed_role_values"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(candidate_opportunity_ids) = 'array'",
            name=op.f("ck_opportunity_resolution_candidates_candidate_ids_array"),
        ),
        sa.CheckConstraint(
            "proposed_snapshot is null or jsonb_typeof(proposed_snapshot) = 'object'",
            name=op.f("ck_opportunity_resolution_candidates_proposed_snapshot_object"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reason_codes) = 'array' and jsonb_array_length(reason_codes) >= 1",
            name=op.f("ck_opportunity_resolution_candidates_reason_codes_array"),
        ),
        sa.CheckConstraint(
            "length(btrim(resolver_version)) >= 1",
            name=op.f("ck_opportunity_resolution_candidates_resolver_version_nonempty"),
        ),
        sa.CheckConstraint(
            "review_status = 'PENDING'",
            name=op.f("ck_opportunity_resolution_candidates_review_status_pending"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.document_id"],
            name=op.f("fk_opportunity_resolution_candidates_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_evidence_ref_id", "document_id"],
            EVIDENCE_FOREIGN_KEY_TARGET,
            name=op.f("fk_opportunity_resolution_candidates_source_evidence_ref_id_evidence_refs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "candidate_id",
            name=op.f("pk_opportunity_resolution_candidates"),
        ),
    )

    op.create_table(
        "opportunity_aliases",
        sa.Column("alias_id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("alias_type", sa.String(length=16), nullable=False),
        sa.Column("alias_value", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("source_document_id", sa.Uuid(), nullable=False),
        sa.Column("source_evidence_ref_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(alias_id) = 7",
            name=op.f("ck_opportunity_aliases_alias_id_uuid7"),
        ),
        sa.CheckConstraint(
            "alias_type in ('TITLE', 'URL', 'EXTERNAL_ID')",
            name=op.f("ck_opportunity_aliases_alias_type_values"),
        ),
        sa.CheckConstraint(
            "length(btrim(alias_value)) >= 1",
            name=op.f("ck_opportunity_aliases_alias_value_nonempty"),
        ),
        sa.CheckConstraint(
            "length(btrim(normalized_value)) >= 1",
            name=op.f("ck_opportunity_aliases_normalized_value_nonempty"),
        ),
        sa.CheckConstraint(
            "alias_type <> 'EXTERNAL_ID' or source_id is not null",
            name=op.f("ck_opportunity_aliases_external_id_source_required"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.opportunity_id"],
            name=op.f("fk_opportunity_aliases_opportunity_id_opportunities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.source_id"],
            name=op.f("fk_opportunity_aliases_source_id_sources"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            EVIDENCE_FOREIGN_KEY_COLUMNS,
            EVIDENCE_FOREIGN_KEY_TARGET,
            name=op.f("fk_opportunity_aliases_source_evidence_ref_id_evidence_refs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("alias_id", name=op.f("pk_opportunity_aliases")),
    )
    op.create_index(
        "uq_opportunity_aliases_url",
        "opportunity_aliases",
        ["alias_type", "normalized_value"],
        unique=True,
        postgresql_where=sa.text("alias_type = 'URL'"),
    )
    op.create_index(
        "uq_opportunity_aliases_external_id",
        "opportunity_aliases",
        ["alias_type", "source_id", "normalized_value"],
        unique=True,
        postgresql_where=sa.text("alias_type = 'EXTERNAL_ID'"),
    )

    op.create_table(
        "opportunity_identity_action_members",
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "role in ('SOURCE', 'TARGET', 'PARENT', 'CHILD')",
            name=op.f("ck_opportunity_identity_action_members_role_values"),
        ),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["opportunity_identity_actions.action_id"],
            name=op.f(
                "fk_opportunity_identity_action_members_action_id_opportunity_identity_actions"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.opportunity_id"],
            name=op.f("fk_opportunity_identity_action_members_opportunity_id_opportunities"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "action_id",
            "opportunity_id",
            "role",
            name=op.f("pk_opportunity_identity_action_members"),
        ),
    )

    op.create_foreign_key(
        "fk_opportunities_current_version_opportunity_versions",
        "opportunities",
        "opportunity_versions",
        ["opportunity_id", "current_version"],
        ["opportunity_id", "version"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade() -> None:
    """Remove Phase 3 only when its append-only history is empty."""
    connection = op.get_bind()
    for table_name in PHASE3_TABLES:
        contains_rows = connection.scalar(
            sa.text(f"select exists(select 1 from {table_name} limit 1)")
        )
        if contains_rows:
            raise RuntimeError(f"cannot downgrade Phase 3 while {table_name} contains v0.3 data")

    op.drop_constraint(
        "fk_opportunities_current_version_opportunity_versions",
        "opportunities",
        type_="foreignkey",
    )
    op.drop_table("opportunity_identity_action_members")
    op.drop_index("uq_opportunity_aliases_external_id", table_name="opportunity_aliases")
    op.drop_index("uq_opportunity_aliases_url", table_name="opportunity_aliases")
    op.drop_table("opportunity_aliases")
    op.drop_table("opportunity_resolution_candidates")
    op.drop_index(
        "uq_document_opportunity_links_active_document",
        table_name="document_opportunity_links",
    )
    op.drop_table("document_opportunity_links")
    op.drop_table("opportunity_events")
    op.drop_table("opportunity_identity_actions")
    op.drop_table("opportunity_versions")
    op.drop_constraint(
        op.f("uq_evidence_refs_evidence_ref_id"),
        "evidence_refs",
        type_="unique",
    )
