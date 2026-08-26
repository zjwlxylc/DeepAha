"""local_human_test_control_plane

Revision ID: 20260826_0030
Revises: 20260825_0029
Create Date: 2026-08-26 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260826_0030"
down_revision: str | None = "20260825_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _extend_reviewer_authority()
    _extend_public_catalog_kind()
    _create_run_table()
    _create_item_table()
    _create_review_decision_table()


def downgrade() -> None:
    connection = op.get_bind()
    contains_control_rows = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM local_human_test_runs LIMIT 1) OR "
            "EXISTS (SELECT 1 FROM local_human_test_items LIMIT 1) OR "
            "EXISTS (SELECT 1 FROM local_human_test_review_decisions LIMIT 1)"
        )
    ).scalar_one()
    contains_local_catalog_rows = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM public_catalog_entries "
            "WHERE collection_kind = 'LOCAL_HUMAN_REVIEWED' LIMIT 1)"
        )
    ).scalar_one()
    contains_local_reviewer_values = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM reviewer_accounts "
            "WHERE roles ? 'LOCAL_TEST_OPERATOR' "
            "OR allowed_purposes ? 'OPPORTUNITY_FACT_VALIDATION' LIMIT 1)"
        )
    ).scalar_one()
    if contains_control_rows or contains_local_catalog_rows or contains_local_reviewer_values:
        raise RuntimeError("cannot downgrade local human-test control plane while evidence exists")

    op.drop_table("local_human_test_review_decisions")
    op.drop_table("local_human_test_items")
    op.drop_table("local_human_test_runs")
    _restore_public_catalog_kind()
    _restore_reviewer_authority()


def _extend_reviewer_authority() -> None:
    op.drop_constraint(
        op.f("ck_reviewer_accounts_roles_values"),
        "reviewer_accounts",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_reviewer_accounts_allowed_purposes_value"),
        "reviewer_accounts",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_reviewer_accounts_roles_values"),
        "reviewer_accounts",
        'roles <@ \'["FEEDBACK_REVIEWER", "FEEDBACK_ADJUDICATOR", '
        '"LABEL_CURATOR", "VALIDATION_REVIEWER", "LOCAL_TEST_OPERATOR"]\'::jsonb',
    )
    op.create_check_constraint(
        op.f("ck_reviewer_accounts_allowed_purposes_values"),
        "reviewer_accounts",
        "jsonb_typeof(allowed_purposes) = 'array' and "
        "jsonb_array_length(allowed_purposes) >= 1 and "
        "allowed_purposes <@ "
        "'[\"FEEDBACK_REVIEW_AND_VALIDATION\", "
        "\"OPPORTUNITY_FACT_VALIDATION\"]'::jsonb",
    )


def _restore_reviewer_authority() -> None:
    op.drop_constraint(
        op.f("ck_reviewer_accounts_allowed_purposes_values"),
        "reviewer_accounts",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_reviewer_accounts_roles_values"),
        "reviewer_accounts",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_reviewer_accounts_roles_values"),
        "reviewer_accounts",
        'roles <@ \'["FEEDBACK_REVIEWER", "FEEDBACK_ADJUDICATOR", '
        '"LABEL_CURATOR", "VALIDATION_REVIEWER"]\'::jsonb',
    )
    op.create_check_constraint(
        op.f("ck_reviewer_accounts_allowed_purposes_value"),
        "reviewer_accounts",
        "allowed_purposes = '[\"FEEDBACK_REVIEW_AND_VALIDATION\"]'::jsonb",
    )


def _extend_public_catalog_kind() -> None:
    op.drop_constraint(
        op.f("ck_public_catalog_entries_collection_kind_values"),
        "public_catalog_entries",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_public_catalog_entries_collection_kind_values"),
        "public_catalog_entries",
        "collection_kind in ('REAL_GOLD', 'LICENSE_SAFE_FIXTURE', "
        "'LOCAL_HUMAN_REVIEWED')",
    )


def _restore_public_catalog_kind() -> None:
    op.drop_constraint(
        op.f("ck_public_catalog_entries_collection_kind_values"),
        "public_catalog_entries",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_public_catalog_entries_collection_kind_values"),
        "public_catalog_entries",
        "collection_kind in ('REAL_GOLD', 'LICENSE_SAFE_FIXTURE')",
    )


def _create_run_table() -> None:
    op.create_table(
        "local_human_test_runs",
        sa.Column("run_id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("mode", sa.String(length=24), nullable=False),
        sa.Column(
            "recipe_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "provider_config_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("budget", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("official_request_count", sa.Integer(), nullable=False),
        sa.Column("llm_call_count", sa.Integer(), nullable=False),
        sa.Column("created_by_reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_reason_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "uuid_extract_version(run_id) = 7",
            name=op.f("ck_local_human_test_runs_run_id_uuid7"),
        ),
        sa.CheckConstraint(
            "mode in ('LIVE_OFFICIAL', 'OFFICIAL_REPLAY')",
            name=op.f("ck_local_human_test_runs_mode_values"),
        ),
        sa.CheckConstraint(
            "status in ('CREATED', 'RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED', "
            "'CANCELLED')",
            name=op.f("ck_local_human_test_runs_status_values"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(recipe_ids) = 'array' and jsonb_array_length(recipe_ids) >= 1",
            name=op.f("ck_local_human_test_runs_recipe_ids_nonempty_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(provider_config_snapshot) = 'object'",
            name=op.f("ck_local_human_test_runs_provider_config_snapshot_object"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(budget) = 'object'",
            name=op.f("ck_local_human_test_runs_budget_object"),
        ),
        sa.CheckConstraint(
            "official_request_count between 0 and 9 and llm_call_count between 0 and 8",
            name=op.f("ck_local_human_test_runs_counter_ranges"),
        ),
        sa.CheckConstraint(
            "(lease_owner is null and lease_expires_at is null) or "
            "(lease_owner is not null and lease_expires_at is not null)",
            name=op.f("ck_local_human_test_runs_lease_state"),
        ),
        sa.CheckConstraint(
            "terminal_reason_code is null or "
            "terminal_reason_code ~ '^[A-Z][A-Z0-9_]{0,127}$'",
            name=op.f("ck_local_human_test_runs_terminal_reason_code_format"),
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name=op.f("ck_local_human_test_runs_timestamp_order"),
        ),
        sa.CheckConstraint(
            "completed_at is null or completed_at >= created_at",
            name=op.f("ck_local_human_test_runs_completion_timestamp_order"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_reviewer_id"],
            ["reviewer_accounts.reviewer_id"],
            name=op.f("fk_local_human_test_runs_created_by_reviewer_id_reviewer_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id", name=op.f("pk_local_human_test_runs")),
    )


def _create_item_table() -> None:
    op.create_table(
        "local_human_test_items",
        sa.Column("item_id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("recipe_id", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("endpoint_id", sa.Uuid(), nullable=True),
        sa.Column("acquisition_evaluation_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("opportunity_id", sa.Uuid(), nullable=True),
        sa.Column("source_bundle_revision_id", sa.Uuid(), nullable=True),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=True),
        sa.Column("model_call_id", sa.Uuid(), nullable=True),
        sa.Column("verified_fact_set_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(item_id) = 7",
            name=op.f("ck_local_human_test_items_item_id_uuid7"),
        ),
        sa.CheckConstraint(
            "length(btrim(recipe_id)) >= 1",
            name=op.f("ck_local_human_test_items_recipe_id_nonempty"),
        ),
        sa.CheckConstraint(
            "status in ('CREATED', 'ACQUIRING', 'BOOTSTRAP_REVIEW', 'EXTRACTING', "
            "'FACT_REVIEW', 'RULE_REVIEW', 'READY_TO_PUBLISH', 'COMPLETED', "
            "'ACQUISITION_REJECTED', 'FAILED_CONFIG', 'PARTIAL_BUDGET_EXHAUSTED', "
            "'UNKNOWN_OUTCOME', 'MODEL_OUTPUT_INVALID', 'EVIDENCE_BINDING_INVALID', "
            "'FAILED', 'CANCELLED')",
            name=op.f("ck_local_human_test_items_status_values"),
        ),
        sa.CheckConstraint(
            "error_code is null or error_code ~ '^[A-Z][A-Z0-9_]{0,127}$'",
            name=op.f("ck_local_human_test_items_error_code_format"),
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name=op.f("ck_local_human_test_items_timestamp_order"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["local_human_test_runs.run_id"],
            name=op.f("fk_local_human_test_items_run_id_local_human_test_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.source_id"],
            name=op.f("fk_local_human_test_items_source_id_sources"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["endpoint_id"],
            ["source_endpoints.endpoint_id"],
            name=op.f("fk_local_human_test_items_endpoint_id_source_endpoints"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["acquisition_evaluation_id"],
            ["acquisition_evaluations.acquisition_evaluation_id"],
            name=op.f(
                "fk_local_human_test_items_acquisition_evaluation_id_acquisition_evaluations"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.document_id"],
            name=op.f("fk_local_human_test_items_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.opportunity_id"],
            name=op.f("fk_local_human_test_items_opportunity_id_opportunities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_bundle_revision_id"],
            ["source_bundle_revisions.source_bundle_revision_id"],
            name=op.f(
                "fk_local_human_test_items_source_bundle_revision_id_source_bundle_revisions"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_run_id"],
            ["extraction_runs.extraction_run_id"],
            name=op.f("fk_local_human_test_items_extraction_run_id_extraction_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["model_call_id"],
            ["p9b_model_calls.model_call_id"],
            name=op.f("fk_local_human_test_items_model_call_id_p9b_model_calls"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["verified_fact_set_id"],
            ["versioned_verified_fact_sets.verified_fact_set_id"],
            name=op.f(
                "fk_local_human_test_items_verified_fact_set_id_versioned_verified_fact_sets"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_local_human_test_items")),
        sa.UniqueConstraint(
            "run_id",
            "recipe_id",
            name="uq_local_human_test_items_run_recipe",
        ),
    )


def _create_review_decision_table() -> None:
    op.create_table(
        "local_human_test_review_decisions",
        sa.Column(
            "decision_id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("decision_kind", sa.String(length=24), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(decision_id) = 7",
            name=op.f("ck_local_human_test_review_decisions_decision_id_uuid7"),
        ),
        sa.CheckConstraint(
            "decision_kind in ('BOOTSTRAP', 'FACT', 'RULE', 'PUBLISH')",
            name=op.f("ck_local_human_test_review_decisions_decision_kind_values"),
        ),
        sa.CheckConstraint(
            "length(btrim(idempotency_key)) >= 1",
            name=op.f("ck_local_human_test_review_decisions_idempotency_key_nonempty"),
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_local_human_test_review_decisions_request_hash_format"),
        ),
        sa.CheckConstraint(
            "length(btrim(reason)) >= 1",
            name=op.f("ck_local_human_test_review_decisions_reason_nonempty"),
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["local_human_test_items.item_id"],
            name=op.f(
                "fk_local_human_test_review_decisions_item_id_local_human_test_items"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["reviewer_accounts.reviewer_id"],
            name=op.f(
                "fk_local_human_test_review_decisions_reviewer_id_reviewer_accounts"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "decision_id",
            name=op.f("pk_local_human_test_review_decisions"),
        ),
        sa.UniqueConstraint(
            "item_id",
            "decision_kind",
            "idempotency_key",
            name="uq_local_human_test_review_decisions_idempotency",
        ),
    )
