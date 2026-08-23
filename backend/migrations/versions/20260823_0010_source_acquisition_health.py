"""source_acquisition_health

Revision ID: 20260823_0010
Revises: 20260823_0009
Create Date: 2026-08-23 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260823_0010"
down_revision: str | None = "20260823_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add immutable run and integration-cost evidence beside acquisition evaluations."""
    op.create_table(
        "acquisition_runs",
        sa.Column("acquisition_run_id", sa.Uuid(), nullable=False),
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_policy_version", sa.String(length=64), nullable=False),
        sa.Column("recipe_version", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminal_code", sa.String(length=128), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column(
            "strategy_attempts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("discovered_count", sa.Integer(), nullable=False),
        sa.Column("validated_count", sa.Integer(), nullable=False),
        sa.Column("parsed_count", sa.Integer(), nullable=False),
        sa.Column("attachment_count", sa.Integer(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("zero_discovery_flag", sa.Boolean(), nullable=False),
        sa.Column("selector_drift_flag", sa.Boolean(), nullable=False),
        sa.Column("manual_intervention", sa.Boolean(), nullable=False),
        sa.Column("stable_stop_reason", sa.String(length=128), nullable=True),
        sa.Column("contract_version", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(acquisition_run_id) = 7",
            name=op.f("ck_acquisition_runs_run_id_uuid7"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(recipe_id) = 7",
            name=op.f("ck_acquisition_runs_recipe_id_uuid7"),
        ),
        sa.CheckConstraint(
            "completed_at >= started_at",
            name=op.f("ck_acquisition_runs_timestamp_order"),
        ),
        sa.CheckConstraint(
            "request_count between 0 and 25",
            name=op.f("ck_acquisition_runs_request_count_range"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(strategy_attempts) = 'array' and "
            "jsonb_array_length(strategy_attempts) = request_count and "
            "octet_length(strategy_attempts::text) <= 16384",
            name=op.f("ck_acquisition_runs_strategy_attempts_shape"),
        ),
        sa.CheckConstraint(
            "discovered_count between 0 and 10000 and "
            "validated_count between 0 and request_count and "
            "parsed_count between 0 and validated_count and "
            "attachment_count between 0 and discovered_count and "
            "evidence_count between 0 and 10000",
            name=op.f("ck_acquisition_runs_count_coherence"),
        ),
        sa.CheckConstraint(
            "terminal_code ~ '^[A-Z][A-Z0-9_]{0,127}$' and "
            "(stable_stop_reason is null or "
            "stable_stop_reason ~ '^[A-Z][A-Z0-9_]{0,127}$')",
            name=op.f("ck_acquisition_runs_terminal_code_shape"),
        ),
        sa.CheckConstraint(
            "(terminal_code = 'COMPLETE') = (stable_stop_reason is null)",
            name=op.f("ck_acquisition_runs_stable_stop_reason_state"),
        ),
        sa.CheckConstraint(
            "contract_version = '1.0.0'",
            name=op.f("ck_acquisition_runs_contract_version_value"),
        ),
        sa.ForeignKeyConstraint(
            ["endpoint_id", "source_id"],
            ["source_endpoints.endpoint_id", "source_endpoints.source_id"],
            name=op.f("fk_acquisition_runs_endpoint_id_source_endpoints"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "acquisition_run_id",
            name=op.f("pk_acquisition_runs"),
        ),
    )
    op.create_index(
        "ix_acquisition_runs_endpoint_completed",
        "acquisition_runs",
        ["endpoint_id", sa.text("completed_at DESC"), sa.text("acquisition_run_id DESC")],
        unique=False,
    )
    op.create_table(
        "source_integration_evidence",
        sa.Column("source_integration_evidence_id", sa.Uuid(), nullable=False),
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), nullable=False),
        sa.Column("recipe_version", sa.String(length=64), nullable=False),
        sa.Column("primary_fetcher", sa.String(length=128), nullable=False),
        sa.Column("onboarding_mode", sa.String(length=32), nullable=False),
        sa.Column("reused_existing_fetcher", sa.Boolean(), nullable=False),
        sa.Column("recipe_line_count", sa.Integer(), nullable=False),
        sa.Column("source_specific_production_loc", sa.Integer(), nullable=False),
        sa.Column("generic_capability_changes", sa.Integer(), nullable=False),
        sa.Column("core_schema_changed", sa.Boolean(), nullable=False),
        sa.Column("onboarding_minutes", sa.Integer(), nullable=False),
        sa.Column("total_request_count", sa.Integer(), nullable=False),
        sa.Column("browser_request_count", sa.Integer(), nullable=False),
        sa.Column("manual_request_count", sa.Integer(), nullable=False),
        sa.Column("run_failure_count", sa.Integer(), nullable=False),
        sa.Column("maintenance_minutes", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contract_version", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(source_integration_evidence_id) = 7",
            name=op.f("ck_source_integration_evidence_evidence_id_uuid7"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(recipe_id) = 7",
            name=op.f("ck_source_integration_evidence_recipe_id_uuid7"),
        ),
        sa.CheckConstraint(
            "onboarding_mode in "
            "('RECIPE_ONLY', 'THIN_PLUGIN', 'GENERIC_CAPABILITY', 'NEW_FETCHER')",
            name=op.f("ck_source_integration_evidence_onboarding_mode_values"),
        ),
        sa.CheckConstraint(
            "recipe_line_count between 1 and 10000 and "
            "source_specific_production_loc between 0 and 100000 and "
            "generic_capability_changes between 0 and 100 and "
            "onboarding_minutes between 0 and 100000 and "
            "total_request_count between 0 and 100000 and "
            "browser_request_count between 0 and total_request_count and "
            "manual_request_count between 0 and total_request_count and "
            "run_failure_count between 0 and total_request_count and "
            "maintenance_minutes between 0 and 100000",
            name=op.f("ck_source_integration_evidence_cost_count_coherence"),
        ),
        sa.CheckConstraint(
            "onboarding_mode <> 'RECIPE_ONLY' or "
            "(source_specific_production_loc = 0 and generic_capability_changes = 0)",
            name=op.f("ck_source_integration_evidence_recipe_only_shape"),
        ),
        sa.CheckConstraint(
            "onboarding_mode <> 'THIN_PLUGIN' or source_specific_production_loc > 0",
            name=op.f("ck_source_integration_evidence_thin_plugin_shape"),
        ),
        sa.CheckConstraint(
            "onboarding_mode <> 'NEW_FETCHER' or not reused_existing_fetcher",
            name=op.f("ck_source_integration_evidence_new_fetcher_shape"),
        ),
        sa.CheckConstraint(
            "contract_version = '1.0.0'",
            name=op.f("ck_source_integration_evidence_contract_version_value"),
        ),
        sa.ForeignKeyConstraint(
            ["endpoint_id", "source_id"],
            ["source_endpoints.endpoint_id", "source_endpoints.source_id"],
            name=op.f("fk_source_integration_evidence_endpoint_id_source_endpoints"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "source_integration_evidence_id",
            name=op.f("pk_source_integration_evidence"),
        ),
        sa.UniqueConstraint(
            "source_id",
            "endpoint_id",
            "recipe_version",
            name=op.f("uq_source_integration_evidence_source_id"),
        ),
    )
    op.execute(
        "CREATE TRIGGER acquisition_run_reject_mutation "
        "BEFORE UPDATE OR DELETE ON acquisition_runs "
        "FOR EACH ROW EXECUTE FUNCTION acquisition_reject_immutable_mutation()"
    )
    op.execute(
        "CREATE TRIGGER source_integration_reject_mutation "
        "BEFORE UPDATE OR DELETE ON source_integration_evidence "
        "FOR EACH ROW EXECUTE FUNCTION acquisition_reject_immutable_mutation()"
    )


def downgrade() -> None:
    """Refuse to discard acquisition health or integration evidence."""
    connection = op.get_bind()
    populated = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM acquisition_runs LIMIT 1) OR "
            "EXISTS (SELECT 1 FROM source_integration_evidence LIMIT 1)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("cannot downgrade acquisition health while evidence exists")

    op.execute("DROP TRIGGER source_integration_reject_mutation ON source_integration_evidence")
    op.execute("DROP TRIGGER acquisition_run_reject_mutation ON acquisition_runs")
    op.drop_table("source_integration_evidence")
    op.drop_index("ix_acquisition_runs_endpoint_completed", table_name="acquisition_runs")
    op.drop_table("acquisition_runs")
