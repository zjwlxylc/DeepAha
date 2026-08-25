"""p9b_replacement_gateway_state

Revision ID: 20260825_0026
Revises: 20260825_0025
Create Date: 2026-08-25 16:00:00
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260825_0026"
down_revision: str | None = "20260825_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        r"""
        DO $$
        BEGIN
            IF to_regclass('public.p9b_model_call_ledgers') IS NOT NULL THEN
                RAISE EXCEPTION 'P9B_REPLACEMENT_LEGACY_GATEWAY_SCHEMA_PRESENT';
            END IF;
        END;
        $$
        """
    )
    _create_egress_authority_tables()
    _create_model_call_tables()
    _create_gateway_state_functions()
    _create_gateway_state_triggers()
    _create_ledger_view()


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text(
            "select exists(select 1 from p9b_model_calls limit 1) "
            "or exists(select 1 from p9b_egress_decisions limit 1) "
            "or exists(select 1 from p9b_model_task_specs limit 1) "
            "or exists(select 1 from p9b_source_egress_policy_snapshots limit 1) "
            "or exists(select 1 from p9b_provider_egress_policy_snapshots limit 1)"
        )
    ).scalar_one():
        raise RuntimeError("cannot downgrade replacement Gateway state with history")

    op.execute("DROP VIEW p9b_model_call_ledger_view")
    op.execute("DROP TRIGGER p9b_model_call_finalizations_derive ON p9b_model_call_finalizations")
    op.execute(
        "DROP TRIGGER p9b_model_call_finalizations_immutable ON p9b_model_call_finalizations"
    )
    op.execute("DROP TRIGGER p9b_model_call_attempts_guard ON p9b_model_call_attempts")
    op.execute("DROP TRIGGER p9b_model_calls_immutable ON p9b_model_calls")
    for table_name in (
        "p9b_egress_decisions",
        "p9b_provider_egress_policy_snapshots",
        "p9b_source_egress_policy_snapshots",
        "p9b_egress_block_classifications",
        "p9b_model_task_specs",
    ):
        op.execute(f"DROP TRIGGER {table_name}_immutable ON {table_name}")
    op.execute("DROP FUNCTION p9b_derive_model_call_finalization()")
    op.execute("DROP FUNCTION p9b_guard_model_call_attempt()")
    op.execute("DROP FUNCTION p9b_gateway_contains_credential_material(text)")
    op.drop_table("p9b_model_call_finalizations")
    op.drop_table("p9b_model_call_attempts")
    op.drop_table("p9b_model_calls")
    op.drop_table("p9b_egress_decisions")
    op.drop_table("p9b_provider_egress_policy_snapshots")
    op.drop_table("p9b_source_egress_policy_snapshots")
    op.drop_table("p9b_egress_block_classifications")
    op.drop_table("p9b_model_task_specs")


def _create_egress_authority_tables() -> None:
    op.create_table(
        "p9b_model_task_specs",
        sa.Column("model_task_spec_id", sa.Uuid(), nullable=False),
        sa.Column("task_name", sa.String(length=64), nullable=False),
        sa.Column("task_version", sa.String(length=32), nullable=False),
        sa.Column("route_class", sa.String(length=32), nullable=False),
        sa.Column("allowed_input_block_types", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("output_schema_version", sa.String(length=64), nullable=False),
        sa.Column("max_input_tokens", sa.Integer(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("evidence_required", sa.Boolean(), nullable=False),
        sa.Column("abstention_allowed", sa.Boolean(), nullable=False),
        sa.Column("risk_class", sa.String(length=32), nullable=False),
        sa.Column("provider_capabilities", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("egress_policy_id", sa.String(length=64), nullable=False),
        sa.Column("timeout_ms", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("initial_backoff_ms", sa.Integer(), nullable=False),
        sa.Column("backoff_multiplier", sa.Float(), nullable=False),
        sa.Column("max_backoff_ms", sa.Integer(), nullable=False),
        sa.Column("max_concurrency", sa.Integer(), nullable=False),
        sa.Column("max_batch_size", sa.Integer(), nullable=False),
        sa.Column("fallback_policy", sa.String(length=32), nullable=False),
        sa.Column("max_fallbacks", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(model_task_spec_id) = 7",
            name=op.f("ck_p9b_model_task_specs_id_uuid7"),
        ),
        sa.CheckConstraint(
            "route_class in ('R1_LOW_COST_EXTRACT', 'R2_BALANCED_REASON', 'R3_STRONG_CANDIDATE')",
            name=op.f("ck_p9b_model_task_specs_route_class_values"),
        ),
        sa.CheckConstraint(
            "max_input_tokens >= 1 and max_output_tokens >= 1",
            name=op.f("ck_p9b_model_task_specs_token_bounds"),
        ),
        sa.CheckConstraint(
            "timeout_ms between 100 and 120000", name=op.f("ck_p9b_model_task_specs_timeout_bounds")
        ),
        sa.CheckConstraint(
            "max_attempts between 1 and 3", name=op.f("ck_p9b_model_task_specs_attempt_bounds")
        ),
        sa.CheckConstraint(
            "initial_backoff_ms between 0 and 10000",
            name=op.f("ck_p9b_model_task_specs_initial_backoff_bounds"),
        ),
        sa.CheckConstraint(
            "backoff_multiplier between 1 and 4",
            name=op.f("ck_p9b_model_task_specs_backoff_multiplier_bounds"),
        ),
        sa.CheckConstraint(
            "max_backoff_ms between initial_backoff_ms and 30000",
            name=op.f("ck_p9b_model_task_specs_max_backoff_bounds"),
        ),
        sa.CheckConstraint(
            "max_concurrency between 1 and 8",
            name=op.f("ck_p9b_model_task_specs_concurrency_bounds"),
        ),
        sa.CheckConstraint(
            "max_batch_size between 1 and 16", name=op.f("ck_p9b_model_task_specs_batch_bounds")
        ),
        sa.CheckConstraint(
            "fallback_policy = 'DISABLED' and max_fallbacks = 0",
            name=op.f("ck_p9b_model_task_specs_fallback_disabled"),
        ),
        sa.PrimaryKeyConstraint("model_task_spec_id", name=op.f("pk_p9b_model_task_specs")),
        sa.UniqueConstraint(
            "task_name", "task_version", name=op.f("uq_p9b_model_task_specs_task_name")
        ),
    )
    op.create_table(
        "p9b_egress_block_classifications",
        sa.Column("classification_id", sa.Uuid(), nullable=False),
        sa.Column("block_id", sa.Uuid(), nullable=False),
        sa.Column("block_hash", sa.String(length=64), nullable=False),
        sa.Column("classification_version", sa.String(length=64), nullable=False),
        sa.Column("classifications", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("contains_user_data", sa.Boolean(), nullable=False),
        sa.Column("classifier_identity", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(classification_id) = 7",
            name=op.f("ck_p9b_egress_block_classifications_id_uuid7"),
        ),
        sa.CheckConstraint(
            "block_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_p9b_egress_block_classifications_block_hash_format"),
        ),
        sa.ForeignKeyConstraint(["block_id"], ["document_blocks.block_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint(
            "classification_id", name=op.f("pk_p9b_egress_block_classifications")
        ),
        sa.UniqueConstraint(
            "block_id",
            "block_hash",
            "classification_version",
            name=op.f("uq_p9b_egress_block_classifications_block_id"),
        ),
    )
    op.create_table(
        "p9b_source_egress_policy_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("source_bundle_revision_id", sa.Uuid(), nullable=False),
        sa.Column("allows_egress", sa.Boolean(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "snapshot_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_p9b_source_egress_policy_snapshots_snapshot_hash_format"),
        ),
        sa.CheckConstraint(
            "valid_until > valid_from",
            name=op.f("ck_p9b_source_egress_policy_snapshots_valid_window"),
        ),
        sa.ForeignKeyConstraint(
            ["source_bundle_revision_id"],
            ["source_bundle_revisions.source_bundle_revision_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("snapshot_id", name=op.f("pk_p9b_source_egress_policy_snapshots")),
        sa.UniqueConstraint(
            "snapshot_hash", name=op.f("uq_p9b_source_egress_policy_snapshots_snapshot_hash")
        ),
    )
    op.create_table(
        "p9b_provider_egress_policy_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("region", sa.String(length=64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("zero_retention", sa.Boolean(), nullable=False),
        sa.Column("training_use", sa.Boolean(), nullable=False),
        sa.Column("supports_idempotency", sa.Boolean(), nullable=False),
        sa.Column("allowed_classifications", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("retention_class", sa.String(length=40), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "snapshot_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_p9b_provider_egress_policy_snapshots_snapshot_hash_format"),
        ),
        sa.CheckConstraint(
            "valid_until > valid_from",
            name=op.f("ck_p9b_provider_egress_policy_snapshots_valid_window"),
        ),
        sa.CheckConstraint(
            "retention_class in ('ZERO_RETENTION', 'PROVIDER_TRANSIENT_RETENTION', 'INTERNAL_ENCRYPTED_AUDIT')",
            name=op.f("ck_p9b_provider_egress_policy_snapshots_retention_class_values"),
        ),
        sa.PrimaryKeyConstraint(
            "snapshot_id", name=op.f("pk_p9b_provider_egress_policy_snapshots")
        ),
        sa.UniqueConstraint(
            "snapshot_hash", name=op.f("uq_p9b_provider_egress_policy_snapshots_snapshot_hash")
        ),
    )
    op.create_table(
        "p9b_egress_decisions",
        sa.Column("egress_decision_id", sa.Uuid(), nullable=False),
        sa.Column("task_spec_name", sa.String(length=64), nullable=False),
        sa.Column("task_spec_version", sa.String(length=32), nullable=False),
        sa.Column("source_bundle_revision_id", sa.Uuid(), nullable=False),
        sa.Column("target_scope", sa.String(length=16), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("opportunity_unit_id", sa.Uuid(), nullable=True),
        sa.Column("opportunity_unit_version_id", sa.Uuid(), nullable=True),
        sa.Column("input_block_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("input_block_hashes", postgresql.ARRAY(sa.String(length=64)), nullable=False),
        sa.Column("data_classification_version", sa.String(length=64), nullable=False),
        sa.Column("minimizer_version", sa.String(length=64), nullable=False),
        sa.Column("redactor_version", sa.String(length=64), nullable=False),
        sa.Column("source_policy_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("source_policy_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("provider_policy_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("provider_policy_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_region", sa.String(length=64), nullable=False),
        sa.Column("original_input_hash", sa.String(length=64), nullable=False),
        sa.Column("actual_payload_hash", sa.String(length=64), nullable=True),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_identity", sa.String(length=128), nullable=True),
        sa.Column("reason_codes", postgresql.ARRAY(sa.String(length=64)), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "uuid_extract_version(egress_decision_id) = 7",
            name=op.f("ck_p9b_egress_decisions_id_uuid7"),
        ),
        sa.CheckConstraint(
            "target_scope in ('OPPORTUNITY', 'UNIT')",
            name=op.f("ck_p9b_egress_decisions_target_scope_values"),
        ),
        sa.CheckConstraint(
            "(target_scope = 'UNIT') = (opportunity_unit_id is not null and opportunity_unit_version_id is not null)",
            name=op.f("ck_p9b_egress_decisions_unit_target_shape"),
        ),
        sa.CheckConstraint(
            "decision in ('ALLOW', 'REDACT_AND_ALLOW', 'DENY', 'LOCAL_NO_EGRESS')",
            name=op.f("ck_p9b_egress_decisions_decision_values"),
        ),
        sa.CheckConstraint(
            "original_input_hash ~ '^[0-9a-f]{64}$' and (actual_payload_hash is null or actual_payload_hash ~ '^[0-9a-f]{64}$')",
            name=op.f("ck_p9b_egress_decisions_hash_formats"),
        ),
        sa.CheckConstraint(
            "(decision in ('ALLOW', 'REDACT_AND_ALLOW')) = (actual_payload_hash is not null and expires_at is not null)",
            name=op.f("ck_p9b_egress_decisions_allowed_payload_shape"),
        ),
        sa.ForeignKeyConstraint(
            ["task_spec_name", "task_spec_version"],
            ["p9b_model_task_specs.task_name", "p9b_model_task_specs.task_version"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_bundle_revision_id", "opportunity_id", "opportunity_version"],
            [
                "source_bundle_revisions.source_bundle_revision_id",
                "source_bundle_revisions.opportunity_id",
                "source_bundle_revisions.opportunity_version",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "opportunity_unit_id",
                "opportunity_unit_version_id",
                "opportunity_id",
                "opportunity_version",
            ],
            [
                "opportunity_unit_versions.opportunity_unit_id",
                "opportunity_unit_versions.opportunity_unit_version_id",
                "opportunity_unit_versions.opportunity_id",
                "opportunity_unit_versions.opportunity_version",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("egress_decision_id", name=op.f("pk_p9b_egress_decisions")),
    )


def _create_model_call_tables() -> None:
    op.create_table(
        "p9b_model_calls",
        sa.Column("model_call_id", sa.Uuid(), nullable=False),
        sa.Column("task_spec_name", sa.String(length=64), nullable=False),
        sa.Column("task_spec_version", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("model_snapshot", sa.String(length=128), nullable=False),
        sa.Column("adapter_name", sa.String(length=64), nullable=False),
        sa.Column("adapter_version", sa.String(length=32), nullable=False),
        sa.Column("runtime_version", sa.String(length=64), nullable=False),
        sa.Column("canonical_request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "canonical_message_hashes", postgresql.ARRAY(sa.String(length=64)), nullable=False
        ),
        sa.Column("input_block_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("input_block_hashes", postgresql.ARRAY(sa.String(length=64)), nullable=False),
        sa.Column("source_bundle_revision_id", sa.Uuid(), nullable=False),
        sa.Column("target_scope", sa.String(length=16), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("opportunity_unit_id", sa.Uuid(), nullable=True),
        sa.Column("opportunity_unit_version_id", sa.Uuid(), nullable=True),
        sa.Column("unit_segmentation_version", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("output_schema_version", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("contract_version", sa.String(length=64), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("top_p", sa.Float(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("egress_decision_id", sa.Uuid(), nullable=False),
        sa.Column("validation_pipeline_version", sa.String(length=64), nullable=False),
        sa.Column("retention_class", sa.String(length=40), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(model_call_id) = 7", name=op.f("ck_p9b_model_calls_id_uuid7")
        ),
        sa.CheckConstraint(
            "canonical_request_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_p9b_model_calls_request_hash_format"),
        ),
        sa.CheckConstraint(
            "target_scope in ('OPPORTUNITY', 'UNIT')",
            name=op.f("ck_p9b_model_calls_target_scope_values"),
        ),
        sa.CheckConstraint(
            "temperature between 0 and 2", name=op.f("ck_p9b_model_calls_temperature_bounds")
        ),
        sa.CheckConstraint("top_p between 0 and 1", name=op.f("ck_p9b_model_calls_top_p_bounds")),
        sa.CheckConstraint(
            "retention_class in ('ZERO_RETENTION', 'PROVIDER_TRANSIENT_RETENTION', 'INTERNAL_ENCRYPTED_AUDIT')",
            name=op.f("ck_p9b_model_calls_retention_class_values"),
        ),
        sa.ForeignKeyConstraint(
            ["egress_decision_id"], ["p9b_egress_decisions.egress_decision_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_bundle_revision_id", "opportunity_id", "opportunity_version"],
            [
                "source_bundle_revisions.source_bundle_revision_id",
                "source_bundle_revisions.opportunity_id",
                "source_bundle_revisions.opportunity_version",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("model_call_id", name=op.f("pk_p9b_model_calls")),
    )
    op.create_table(
        "p9b_model_call_attempts",
        sa.Column("model_call_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("egress_decision_id", sa.Uuid(), nullable=False),
        sa.Column("source_bundle_revision_id", sa.Uuid(), nullable=False),
        sa.Column("source_policy_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("source_policy_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("provider_policy_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("provider_policy_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("authorization_decision", sa.String(length=24), nullable=False),
        sa.Column("authorization_reason_code", sa.String(length=64), nullable=False),
        sa.Column("authorization_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatch_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_invocation_allowed", sa.Boolean(), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=True),
        sa.Column("provider_http_status", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("provider_response_id", sa.String(length=256), nullable=True),
        sa.Column("raw_response_reference_kind", sa.String(length=32), nullable=True),
        sa.Column("raw_response_storage_bucket", sa.String(length=128), nullable=True),
        sa.Column("raw_response_object_key", sa.String(length=512), nullable=True),
        sa.Column("raw_response_sha256", sa.String(length=64), nullable=True),
        sa.Column("response_hash", sa.String(length=64), nullable=True),
        sa.Column("parsed_result_hash", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_status", sa.String(length=24), nullable=True),
        sa.Column("monetary_cost", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(attempt_id) = 7",
            name=op.f("ck_p9b_model_call_attempts_attempt_id_uuid7"),
        ),
        sa.CheckConstraint(
            "attempt_number between 1 and 3",
            name=op.f("ck_p9b_model_call_attempts_attempt_number_bounds"),
        ),
        sa.CheckConstraint(
            "authorization_decision in ('AUTHORIZED', 'AUTHORITY_REJECTED')",
            name=op.f("ck_p9b_model_call_attempts_authorization_values"),
        ),
        sa.CheckConstraint(
            "outcome is null or outcome in ('AUTHORITY_REJECTED', 'SUCCEEDED', 'RETRYABLE_PROVIDER_ERROR', 'TERMINAL_PROVIDER_ERROR', 'PROVIDER_OUTCOME_UNKNOWN', 'RESPONSE_METADATA_REJECTED', 'OUTPUT_LIMIT_EXCEEDED', 'INVALID_JSON_RESPONSE', 'INVALID_CANDIDATE_SHAPE', 'OUTPUT_SCHEMA_VALIDATION_FAILED')",
            name=op.f("ck_p9b_model_call_attempts_outcome_values"),
        ),
        sa.CheckConstraint(
            "(authorization_decision = 'AUTHORIZED') = provider_invocation_allowed",
            name=op.f("ck_p9b_model_call_attempts_authorization_dispatch_shape"),
        ),
        sa.CheckConstraint(
            "(outcome is null) = (completed_at is null)",
            name=op.f("ck_p9b_model_call_attempts_completion_shape"),
        ),
        sa.CheckConstraint(
            "response_hash is null or response_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_p9b_model_call_attempts_response_hash_format"),
        ),
        sa.CheckConstraint(
            "parsed_result_hash is null or parsed_result_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_p9b_model_call_attempts_parsed_hash_format"),
        ),
        sa.ForeignKeyConstraint(
            ["model_call_id"], ["p9b_model_calls.model_call_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["egress_decision_id"], ["p9b_egress_decisions.egress_decision_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint(
            "model_call_id", "attempt_number", name=op.f("pk_p9b_model_call_attempts")
        ),
        sa.UniqueConstraint("attempt_id", name=op.f("uq_p9b_model_call_attempts_attempt_id")),
    )
    op.create_table(
        "p9b_model_call_finalizations",
        sa.Column("model_call_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("disposition", sa.String(length=48), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('SUCCEEDED', 'TERMINAL_FAILED')",
            name=op.f("ck_p9b_model_call_finalizations_status_values"),
        ),
        sa.CheckConstraint(
            "disposition in ('COMPLETED', 'AUTHORITY_REJECTED', 'PROVIDER_TERMINAL', 'PROVIDER_OUTCOME_UNKNOWN', 'RESPONSE_METADATA_REJECTED', 'ATTEMPTS_EXHAUSTED', 'REVISION_INVALIDATED_AFTER_DISPATCH')",
            name=op.f("ck_p9b_model_call_finalizations_disposition_values"),
        ),
        sa.ForeignKeyConstraint(
            ["model_call_id"], ["p9b_model_calls.model_call_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("model_call_id", name=op.f("pk_p9b_model_call_finalizations")),
    )


def _create_gateway_state_functions() -> None:
    op.execute(
        r"""
        CREATE FUNCTION p9b_gateway_contains_credential_material(value text)
        RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
            SELECT value ~ '[[:cntrl:]]'
                OR value ~* '(^|[^a-z0-9_])(authorization|proxy-authorization|cookie|set-cookie)[[:space:]]*[:=]'
                OR value ~* '(^|[^a-z0-9_])(bearer|basic)[[:space:]]+[a-z0-9._~+/-]{8,}=*'
                OR value ~* '(^|[^a-z0-9_])(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|secret[_-]?key|password|credential)[[:space:]]*[:=]'
                OR value ~* '(^|[^a-z0-9_])sk-(proj-)?[a-z0-9_-]{8,}'
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION p9b_guard_model_call_attempt()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            call_row p9b_model_calls%ROWTYPE;
            decision_row p9b_egress_decisions%ROWTYPE;
            task_row p9b_model_task_specs%ROWTYPE;
            revision_status text;
            authorization_time timestamptz := clock_timestamp();
            expected_attempt integer;
            authorized boolean := false;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'P9B_MODEL_CALL_ATTEMPT_HISTORY_IMMUTABLE';
            END IF;

            IF TG_OP = 'INSERT' THEN
                IF EXISTS (
                    SELECT 1 FROM p9b_model_call_finalizations
                    WHERE model_call_id = NEW.model_call_id
                ) THEN
                    RAISE EXCEPTION 'P9B_MODEL_CALL_ALREADY_FINALIZED';
                END IF;
                SELECT * INTO call_row FROM p9b_model_calls
                WHERE model_call_id = NEW.model_call_id;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'P9B_MODEL_CALL_NOT_FOUND';
                END IF;
                SELECT status INTO revision_status
                FROM source_bundle_revisions
                WHERE source_bundle_revision_id = call_row.source_bundle_revision_id
                FOR SHARE;
                PERFORM model_call_id FROM p9b_model_calls
                WHERE model_call_id = NEW.model_call_id FOR UPDATE;
                SELECT coalesce(max(attempt_number), 0) + 1 INTO expected_attempt
                FROM p9b_model_call_attempts WHERE model_call_id = NEW.model_call_id;
                IF NEW.attempt_number IS DISTINCT FROM expected_attempt THEN
                    RAISE EXCEPTION 'P9B_MODEL_CALL_ATTEMPT_SEQUENCE_MISMATCH';
                END IF;
                SELECT * INTO decision_row FROM p9b_egress_decisions
                WHERE egress_decision_id = call_row.egress_decision_id;
                SELECT * INTO task_row FROM p9b_model_task_specs
                WHERE task_name = call_row.task_spec_name
                  AND task_version = call_row.task_spec_version;
                IF expected_attempt > coalesce(task_row.max_attempts, 0) THEN
                    RAISE EXCEPTION 'P9B_MODEL_CALL_ATTEMPT_LIMIT_EXCEEDED';
                END IF;

                authorized := revision_status = 'FROZEN'
                    AND decision_row.decision IN ('ALLOW', 'REDACT_AND_ALLOW')
                    AND decision_row.expires_at > authorization_time
                    AND decision_row.source_bundle_revision_id = call_row.source_bundle_revision_id
                    AND decision_row.opportunity_id = call_row.opportunity_id
                    AND decision_row.opportunity_version = call_row.opportunity_version
                    AND decision_row.task_spec_name = call_row.task_spec_name
                    AND decision_row.task_spec_version = call_row.task_spec_version
                    AND decision_row.provider = call_row.provider
                    AND decision_row.input_block_ids = call_row.input_block_ids
                    AND decision_row.input_block_hashes = call_row.input_block_hashes
                    AND EXISTS (
                        SELECT 1 FROM p9b_source_egress_policy_snapshots AS policy
                        WHERE policy.snapshot_id = decision_row.source_policy_snapshot_id
                          AND policy.snapshot_hash = decision_row.source_policy_snapshot_hash
                          AND policy.source_bundle_revision_id = call_row.source_bundle_revision_id
                          AND policy.allows_egress
                          AND policy.valid_from <= authorization_time
                          AND policy.valid_until > authorization_time
                          AND policy.valid_until >= decision_row.expires_at
                    )
                    AND EXISTS (
                        SELECT 1 FROM p9b_provider_egress_policy_snapshots AS policy
                        WHERE policy.snapshot_id = decision_row.provider_policy_snapshot_id
                          AND policy.snapshot_hash = decision_row.provider_policy_snapshot_hash
                          AND policy.provider = call_row.provider
                          AND policy.region = decision_row.provider_region
                          AND policy.active
                          AND NOT policy.training_use
                          AND policy.retention_class = call_row.retention_class
                          AND (
                              NOT ('ZERO_RETENTION' = ANY(task_row.provider_capabilities))
                              OR policy.zero_retention
                          )
                          AND policy.valid_from <= authorization_time
                          AND policy.valid_until > authorization_time
                          AND policy.valid_until >= decision_row.expires_at
                    );

                NEW.egress_decision_id := call_row.egress_decision_id;
                NEW.source_bundle_revision_id := call_row.source_bundle_revision_id;
                NEW.source_policy_snapshot_id := decision_row.source_policy_snapshot_id;
                NEW.source_policy_snapshot_hash := decision_row.source_policy_snapshot_hash;
                NEW.provider_policy_snapshot_id := decision_row.provider_policy_snapshot_id;
                NEW.provider_policy_snapshot_hash := decision_row.provider_policy_snapshot_hash;
                NEW.authorization_checked_at := authorization_time;
                NEW.created_at := authorization_time;
                NEW.provider_http_status := NULL;
                NEW.error_code := NULL;
                NEW.provider_response_id := NULL;
                NEW.raw_response_reference_kind := NULL;
                NEW.raw_response_storage_bucket := NULL;
                NEW.raw_response_object_key := NULL;
                NEW.raw_response_sha256 := NULL;
                NEW.response_hash := NULL;
                NEW.parsed_result_hash := NULL;
                NEW.input_tokens := NULL;
                NEW.output_tokens := NULL;
                NEW.cache_read_tokens := NULL;
                NEW.cache_write_tokens := NULL;
                NEW.cost_status := NULL;
                NEW.monetary_cost := NULL;
                NEW.latency_ms := NULL;
                IF authorized THEN
                    NEW.authorization_decision := 'AUTHORIZED';
                    NEW.authorization_reason_code := 'AUTHORIZED';
                    NEW.provider_invocation_allowed := true;
                    NEW.dispatch_deadline := authorization_time
                        + make_interval(secs => task_row.timeout_ms::double precision / 1000.0);
                    NEW.outcome := NULL;
                    NEW.completed_at := NULL;
                ELSE
                    NEW.authorization_decision := 'AUTHORITY_REJECTED';
                    NEW.authorization_reason_code := 'P9B_EGRESS_AUTHORITY_EXPIRED_OR_MISMATCH';
                    NEW.provider_invocation_allowed := false;
                    NEW.dispatch_deadline := NULL;
                    NEW.outcome := 'AUTHORITY_REJECTED';
                    NEW.completed_at := authorization_time;
                END IF;
                RETURN NEW;
            END IF;

            IF OLD.outcome IS NOT NULL THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_RESULT_ALREADY_TERMINAL';
            END IF;
            IF EXISTS (
                SELECT 1 FROM p9b_model_call_finalizations
                WHERE model_call_id = OLD.model_call_id
            ) THEN
                RAISE EXCEPTION 'P9B_MODEL_CALL_ALREADY_FINALIZED';
            END IF;
            IF OLD.authorization_decision <> 'AUTHORIZED' OR NOT OLD.provider_invocation_allowed THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_PROVIDER_INVOCATION_NOT_AUTHORIZED';
            END IF;
            IF ROW(
                NEW.model_call_id, NEW.attempt_number, NEW.attempt_id,
                NEW.egress_decision_id, NEW.source_bundle_revision_id,
                NEW.source_policy_snapshot_id, NEW.source_policy_snapshot_hash,
                NEW.provider_policy_snapshot_id, NEW.provider_policy_snapshot_hash,
                NEW.authorization_decision, NEW.authorization_reason_code,
                NEW.authorization_checked_at, NEW.dispatch_deadline,
                NEW.provider_invocation_allowed, NEW.created_at
            ) IS DISTINCT FROM ROW(
                OLD.model_call_id, OLD.attempt_number, OLD.attempt_id,
                OLD.egress_decision_id, OLD.source_bundle_revision_id,
                OLD.source_policy_snapshot_id, OLD.source_policy_snapshot_hash,
                OLD.provider_policy_snapshot_id, OLD.provider_policy_snapshot_hash,
                OLD.authorization_decision, OLD.authorization_reason_code,
                OLD.authorization_checked_at, OLD.dispatch_deadline,
                OLD.provider_invocation_allowed, OLD.created_at
            ) THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_AUTHORIZATION_IMMUTABLE';
            END IF;
            IF NEW.outcome IS NULL OR NEW.outcome = 'AUTHORITY_REJECTED' THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_RESULT_REQUIRED';
            END IF;

            NEW.completed_at := clock_timestamp();
            IF coalesce(p9b_gateway_contains_credential_material(NEW.provider_response_id), false)
               OR coalesce(p9b_gateway_contains_credential_material(NEW.raw_response_storage_bucket), false)
               OR coalesce(p9b_gateway_contains_credential_material(NEW.raw_response_object_key), false)
               OR coalesce(p9b_gateway_contains_credential_material(NEW.error_code), false)
            THEN
                NEW.outcome := 'RESPONSE_METADATA_REJECTED';
                NEW.error_code := 'CREDENTIAL_MATERIAL_REJECTED';
                NEW.provider_response_id := NULL;
                NEW.raw_response_reference_kind := NULL;
                NEW.raw_response_storage_bucket := NULL;
                NEW.raw_response_object_key := NULL;
                NEW.raw_response_sha256 := NULL;
                NEW.response_hash := NULL;
                NEW.parsed_result_hash := NULL;
            END IF;

            IF NEW.provider_http_status IS NOT NULL
               AND NEW.provider_http_status NOT BETWEEN 100 AND 599 THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_HTTP_STATUS_INVALID';
            END IF;
            IF NEW.raw_response_reference_kind IS NULL THEN
                IF NEW.provider_response_id IS NOT NULL
                   OR NEW.raw_response_storage_bucket IS NOT NULL
                   OR NEW.raw_response_object_key IS NOT NULL
                   OR NEW.raw_response_sha256 IS NOT NULL THEN
                    RAISE EXCEPTION 'P9B_ATTEMPT_RAW_RESPONSE_REFERENCE_INVALID';
                END IF;
            ELSIF NEW.raw_response_reference_kind = 'PROVIDER_RESPONSE_ID' THEN
                IF NEW.provider_response_id IS NULL
                   OR NEW.raw_response_storage_bucket IS NOT NULL
                   OR NEW.raw_response_object_key IS NOT NULL
                   OR NEW.raw_response_sha256 IS NOT NULL THEN
                    RAISE EXCEPTION 'P9B_ATTEMPT_RAW_RESPONSE_REFERENCE_INVALID';
                END IF;
            ELSIF NEW.raw_response_reference_kind = 'INTERNAL_OBJECT' THEN
                IF NEW.provider_response_id IS NOT NULL
                   OR NEW.raw_response_storage_bucket IS NULL
                   OR NEW.raw_response_object_key IS NULL
                   OR NEW.raw_response_sha256 IS NULL THEN
                    RAISE EXCEPTION 'P9B_ATTEMPT_RAW_RESPONSE_REFERENCE_INVALID';
                END IF;
            ELSE
                RAISE EXCEPTION 'P9B_ATTEMPT_RAW_RESPONSE_REFERENCE_INVALID';
            END IF;
            IF NEW.outcome = 'SUCCEEDED' THEN
                IF NEW.raw_response_reference_kind IS NULL
                   OR NEW.response_hash IS NULL
                   OR NEW.parsed_result_hash IS NULL
                   OR NEW.error_code IS NOT NULL THEN
                    RAISE EXCEPTION 'P9B_ATTEMPT_SUCCESS_SHAPE_INVALID';
                END IF;
            ELSIF NEW.parsed_result_hash IS NOT NULL THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_FAILURE_SHAPE_INVALID';
            END IF;
            IF NEW.input_tokens IS NULL OR NEW.input_tokens < 0
               OR NEW.output_tokens IS NULL OR NEW.output_tokens < 0
               OR NEW.cache_read_tokens IS NULL OR NEW.cache_read_tokens < 0
               OR NEW.cache_write_tokens IS NULL OR NEW.cache_write_tokens < 0
               OR NEW.latency_ms IS NULL OR NEW.latency_ms < 0 THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_USAGE_INVALID';
            END IF;
            IF (NEW.cost_status = 'REPORTED') IS DISTINCT FROM (NEW.monetary_cost IS NOT NULL)
               OR NEW.cost_status NOT IN ('REPORTED', 'COST_NOT_REPORTED')
               OR NEW.monetary_cost < 0 THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_COST_INVALID';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION p9b_derive_model_call_finalization()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            call_row p9b_model_calls%ROWTYPE;
            latest_attempt p9b_model_call_attempts%ROWTYPE;
            revision_status text;
            attempt_count integer;
            maximum_attempts integer;
        BEGIN
            SELECT * INTO call_row FROM p9b_model_calls
            WHERE model_call_id = NEW.model_call_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'P9B_MODEL_CALL_NOT_FOUND';
            END IF;
            SELECT status INTO revision_status FROM source_bundle_revisions
            WHERE source_bundle_revision_id = call_row.source_bundle_revision_id
            FOR SHARE;
            SELECT * INTO latest_attempt FROM p9b_model_call_attempts
            WHERE model_call_id = NEW.model_call_id
            ORDER BY attempt_number DESC LIMIT 1;
            IF NOT FOUND OR latest_attempt.outcome IS NULL THEN
                RAISE EXCEPTION 'P9B_MODEL_CALL_NOT_FINALIZABLE';
            END IF;
            SELECT count(*) INTO attempt_count FROM p9b_model_call_attempts
            WHERE model_call_id = NEW.model_call_id;
            SELECT max_attempts INTO maximum_attempts FROM p9b_model_task_specs
            WHERE task_name = call_row.task_spec_name
              AND task_version = call_row.task_spec_version;

            NEW.finalized_at := clock_timestamp();
            IF revision_status <> 'FROZEN'
               AND latest_attempt.authorization_decision = 'AUTHORIZED' THEN
                NEW.status := 'TERMINAL_FAILED';
                NEW.disposition := 'REVISION_INVALIDATED_AFTER_DISPATCH';
                NEW.reason_code := 'REVISION_INVALIDATED_AFTER_DISPATCH';
            ELSIF latest_attempt.outcome = 'SUCCEEDED' THEN
                NEW.status := 'SUCCEEDED';
                NEW.disposition := 'COMPLETED';
                NEW.reason_code := 'SUCCEEDED';
            ELSIF latest_attempt.outcome = 'AUTHORITY_REJECTED' THEN
                NEW.status := 'TERMINAL_FAILED';
                NEW.disposition := 'AUTHORITY_REJECTED';
                NEW.reason_code := latest_attempt.authorization_reason_code;
            ELSIF latest_attempt.outcome = 'PROVIDER_OUTCOME_UNKNOWN' THEN
                NEW.status := 'TERMINAL_FAILED';
                NEW.disposition := 'PROVIDER_OUTCOME_UNKNOWN';
                NEW.reason_code := coalesce(latest_attempt.error_code, 'PROVIDER_OUTCOME_UNKNOWN');
            ELSIF latest_attempt.outcome = 'RESPONSE_METADATA_REJECTED' THEN
                NEW.status := 'TERMINAL_FAILED';
                NEW.disposition := 'RESPONSE_METADATA_REJECTED';
                NEW.reason_code := coalesce(latest_attempt.error_code, 'RESPONSE_METADATA_REJECTED');
            ELSIF latest_attempt.outcome = 'RETRYABLE_PROVIDER_ERROR'
                  AND attempt_count < maximum_attempts THEN
                RAISE EXCEPTION 'P9B_MODEL_CALL_NOT_FINALIZABLE';
            ELSIF latest_attempt.outcome = 'RETRYABLE_PROVIDER_ERROR' THEN
                NEW.status := 'TERMINAL_FAILED';
                NEW.disposition := 'ATTEMPTS_EXHAUSTED';
                NEW.reason_code := coalesce(latest_attempt.error_code, 'ATTEMPTS_EXHAUSTED');
            ELSE
                NEW.status := 'TERMINAL_FAILED';
                NEW.disposition := 'PROVIDER_TERMINAL';
                NEW.reason_code := coalesce(latest_attempt.error_code, latest_attempt.outcome);
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )


def _create_gateway_state_triggers() -> None:
    for table_name in (
        "p9b_model_task_specs",
        "p9b_egress_block_classifications",
        "p9b_source_egress_policy_snapshots",
        "p9b_provider_egress_policy_snapshots",
        "p9b_egress_decisions",
        "p9b_model_calls",
    ):
        op.execute(
            f"CREATE TRIGGER {table_name}_immutable BEFORE UPDATE OR DELETE ON {table_name} "
            "FOR EACH ROW EXECUTE FUNCTION p9b_insert_only_guard()"
        )
    op.execute(
        "CREATE TRIGGER p9b_model_call_attempts_guard BEFORE INSERT OR UPDATE OR DELETE "
        "ON p9b_model_call_attempts FOR EACH ROW EXECUTE FUNCTION "
        "p9b_guard_model_call_attempt()"
    )
    op.execute(
        "CREATE TRIGGER p9b_model_call_finalizations_derive BEFORE INSERT "
        "ON p9b_model_call_finalizations FOR EACH ROW EXECUTE FUNCTION "
        "p9b_derive_model_call_finalization()"
    )
    op.execute(
        "CREATE TRIGGER p9b_model_call_finalizations_immutable BEFORE UPDATE OR DELETE "
        "ON p9b_model_call_finalizations FOR EACH ROW EXECUTE FUNCTION "
        "p9b_insert_only_guard()"
    )


def _create_ledger_view() -> None:
    op.execute(
        r"""
        CREATE VIEW p9b_model_call_ledger_view AS
        SELECT
            call.model_call_id,
            call.task_spec_name,
            call.task_spec_version,
            call.provider,
            call.model_id,
            call.model_snapshot,
            call.adapter_name,
            call.adapter_version,
            call.runtime_version,
            call.canonical_request_hash,
            call.canonical_message_hashes,
            call.input_block_ids,
            call.input_block_hashes,
            call.source_bundle_revision_id,
            call.target_scope,
            call.opportunity_id,
            call.opportunity_version,
            call.opportunity_unit_id,
            call.opportunity_unit_version_id,
            call.unit_segmentation_version,
            call.prompt_version,
            call.output_schema_version,
            call.parser_version,
            call.contract_version,
            call.temperature,
            call.top_p,
            call.seed,
            call.egress_decision_id,
            call.validation_pipeline_version,
            call.retention_class,
            call.registered_at,
            coalesce(finalization.status, 'IN_PROGRESS') AS status,
            finalization.disposition AS terminal_disposition,
            finalization.reason_code AS terminal_reason_code,
            finalization.finalized_at,
            coalesce(summary.attempt_count, 0)::integer AS attempt_count,
            greatest(coalesce(summary.attempt_count, 0) - 1, 0)::integer AS retry_count,
            0::integer AS fallback_count,
            coalesce(summary.attempts, '[]'::jsonb) AS attempts,
            latest.provider_response_id,
            latest.raw_response_reference_kind,
            latest.raw_response_storage_bucket,
            latest.raw_response_object_key,
            latest.raw_response_sha256,
            latest.response_hash,
            latest.parsed_result_hash,
            coalesce(summary.input_tokens, 0)::bigint AS input_tokens,
            coalesce(summary.output_tokens, 0)::bigint AS output_tokens,
            coalesce(summary.cache_read_tokens, 0)::bigint AS cache_read_tokens,
            coalesce(summary.cache_write_tokens, 0)::bigint AS cache_write_tokens,
            coalesce(summary.monetary_cost, 0)::numeric(18, 6) AS monetary_cost,
            coalesce(summary.latency_ms, 0)::bigint AS latency_ms
        FROM p9b_model_calls AS call
        LEFT JOIN p9b_model_call_finalizations AS finalization
          ON finalization.model_call_id = call.model_call_id
        LEFT JOIN LATERAL (
            SELECT
                count(*) AS attempt_count,
                jsonb_agg(
                    jsonb_build_object(
                        'attempt', attempt.attempt_number,
                        'attempt_id', attempt.attempt_id,
                        'authorization_decision', attempt.authorization_decision,
                        'authorization_reason_code', attempt.authorization_reason_code,
                        'authorization_checked_at', attempt.authorization_checked_at,
                        'dispatch_deadline', attempt.dispatch_deadline,
                        'provider_invocation_allowed', attempt.provider_invocation_allowed,
                        'outcome', attempt.outcome,
                        'error_code', attempt.error_code,
                        'provider_http_status', attempt.provider_http_status,
                        'completed_at', attempt.completed_at
                    ) ORDER BY attempt.attempt_number
                ) AS attempts,
                sum(coalesce(attempt.input_tokens, 0)) AS input_tokens,
                sum(coalesce(attempt.output_tokens, 0)) AS output_tokens,
                sum(coalesce(attempt.cache_read_tokens, 0)) AS cache_read_tokens,
                sum(coalesce(attempt.cache_write_tokens, 0)) AS cache_write_tokens,
                sum(coalesce(attempt.monetary_cost, 0)) AS monetary_cost,
                sum(coalesce(attempt.latency_ms, 0)) AS latency_ms
            FROM p9b_model_call_attempts AS attempt
            WHERE attempt.model_call_id = call.model_call_id
        ) AS summary ON true
        LEFT JOIN LATERAL (
            SELECT attempt.* FROM p9b_model_call_attempts AS attempt
            WHERE attempt.model_call_id = call.model_call_id
            ORDER BY attempt.attempt_number DESC LIMIT 1
        ) AS latest ON true
        """
    )
