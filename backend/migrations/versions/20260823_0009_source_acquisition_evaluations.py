"""source_acquisition_evaluations

Revision ID: 20260823_0009
Revises: 20260822_0008
Create Date: 2026-08-23 22:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260823_0009"
down_revision: str | None = "20260822_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add immutable semantic truth beside Phase 2 transport observations."""
    op.create_unique_constraint(
        "uq_capture_observations_acquisition_binding",
        "capture_observations",
        ["observation_id", "endpoint_id", "source_id", "artifact_id"],
    )
    op.create_table(
        "acquisition_evaluations",
        sa.Column(
            "acquisition_evaluation_id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("observation_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_used", sa.String(length=32), nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.Column("challenge_type", sa.String(length=32), nullable=True),
        sa.Column(
            "redirect_chain",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("discovered_count", sa.Integer(), nullable=True),
        sa.Column("manual_intervention", sa.Boolean(), nullable=False),
        sa.Column(
            "diagnostic_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("validator_name", sa.String(length=128), nullable=False),
        sa.Column("validator_version", sa.String(length=64), nullable=False),
        sa.Column("metrics_schema_version", sa.String(length=64), nullable=False),
        sa.Column(
            "validation_metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contract_version", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(acquisition_evaluation_id) = 7",
            name=op.f("ck_acquisition_evaluations_acquisition_evaluation_id_uuid7"),
        ),
        sa.CheckConstraint(
            "strategy_used in ('STRUCTURED', 'STATIC_HTTP', 'BROWSER', "
            "'OFFICIAL_ALTERNATIVE', 'MANUAL')",
            name=op.f("ck_acquisition_evaluations_strategy_used_values"),
        ),
        sa.CheckConstraint(
            "validation_status in ('VALID', 'CONTENT_CHALLENGE', 'CAPTCHA_REQUIRED', "
            "'AUTH_REQUIRED', 'ACCESS_DENIED', 'UNEXPECTED_CONTENT', "
            "'ZERO_DISCOVERY_SUSPECT', 'SELECTOR_DRIFT')",
            name=op.f("ck_acquisition_evaluations_validation_status_values"),
        ),
        sa.CheckConstraint(
            "challenge_type is null or challenge_type in "
            "('JAVASCRIPT_COOKIE', 'CAPTCHA', 'AUTHENTICATION', 'ACCESS_CONTROL')",
            name=op.f("ck_acquisition_evaluations_challenge_type_values"),
        ),
        sa.CheckConstraint(
            "(validation_status = 'CONTENT_CHALLENGE' and challenge_type is not null and "
            "challenge_type = 'JAVASCRIPT_COOKIE') or "
            "(validation_status = 'CAPTCHA_REQUIRED' and challenge_type is not null and "
            "challenge_type = 'CAPTCHA') or "
            "(validation_status = 'AUTH_REQUIRED' and challenge_type is not null and "
            "challenge_type = 'AUTHENTICATION') or "
            "(validation_status = 'ACCESS_DENIED' and challenge_type is not null and "
            "challenge_type = 'ACCESS_CONTROL') or "
            "(validation_status in ('VALID', 'UNEXPECTED_CONTENT', "
            "'ZERO_DISCOVERY_SUSPECT', 'SELECTOR_DRIFT') and challenge_type is null)",
            name=op.f("ck_acquisition_evaluations_challenge_state"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(redirect_chain) = 'array' and "
            "jsonb_array_length(redirect_chain) between 1 and 11",
            name=op.f("ck_acquisition_evaluations_redirect_chain_shape"),
        ),
        sa.CheckConstraint(
            "discovered_count is null or discovered_count between 0 and 10000",
            name=op.f("ck_acquisition_evaluations_discovered_count_range"),
        ),
        sa.CheckConstraint(
            "(strategy_used = 'MANUAL') = manual_intervention",
            name=op.f("ck_acquisition_evaluations_manual_intervention_state"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(diagnostic_codes) = 'array' and "
            "jsonb_array_length(diagnostic_codes) <= 32",
            name=op.f("ck_acquisition_evaluations_diagnostic_codes_shape"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(validation_metrics) = 'object' and "
            "octet_length(validation_metrics::text) <= 4096",
            name=op.f("ck_acquisition_evaluations_validation_metrics_shape"),
        ),
        sa.CheckConstraint(
            "contract_version = '1.0.0'",
            name=op.f("ck_acquisition_evaluations_contract_version_value"),
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id", "source_id"],
            ["raw_artifacts.artifact_id", "raw_artifacts.source_id"],
            name=op.f("fk_acquisition_evaluations_artifact_id_raw_artifacts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["endpoint_id", "source_id"],
            ["source_endpoints.endpoint_id", "source_endpoints.source_id"],
            name=op.f("fk_acquisition_evaluations_endpoint_id_source_endpoints"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["observation_id", "endpoint_id", "source_id", "artifact_id"],
            [
                "capture_observations.observation_id",
                "capture_observations.endpoint_id",
                "capture_observations.source_id",
                "capture_observations.artifact_id",
            ],
            name=op.f("fk_acquisition_evaluations_observation_id_capture_observations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "acquisition_evaluation_id",
            name=op.f("pk_acquisition_evaluations"),
        ),
        sa.UniqueConstraint(
            "observation_id",
            name=op.f("uq_acquisition_evaluations_observation_id"),
        ),
    )
    op.create_index(
        "ix_acquisition_evaluations_endpoint_evaluated",
        "acquisition_evaluations",
        ["endpoint_id", sa.text("evaluated_at DESC"), sa.text("acquisition_evaluation_id DESC")],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION acquisition_reject_immutable_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'Acquisition semantic fact is immutable';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER acquisition_reject_mutation
        BEFORE UPDATE OR DELETE ON acquisition_evaluations
        FOR EACH ROW EXECUTE FUNCTION acquisition_reject_immutable_mutation()
        """
    )


def downgrade() -> None:
    """Refuse to discard semantic acquisition evidence."""
    connection = op.get_bind()
    populated = connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM acquisition_evaluations LIMIT 1)")
    ).scalar_one()
    if populated:
        raise RuntimeError("cannot downgrade source acquisition while evaluations exist")

    op.execute("DROP TRIGGER acquisition_reject_mutation ON acquisition_evaluations")
    op.execute("DROP FUNCTION acquisition_reject_immutable_mutation()")
    op.drop_index(
        "ix_acquisition_evaluations_endpoint_evaluated",
        table_name="acquisition_evaluations",
    )
    op.drop_table("acquisition_evaluations")
    op.drop_constraint(
        "uq_capture_observations_acquisition_binding",
        "capture_observations",
        type_="unique",
    )
