"""phase7_feedback_review_validation

Revision ID: 20260822_0007
Revises: 20260822_0006
Create Date: 2026-08-22 17:53:16.959226
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260822_0007"
down_revision: str | None = "20260822_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PHASE7_TABLES = (
    "approved_feedback_labels",
    "feedback_adjudications",
    "feedback_confidence_assessments",
    "feedback_events",
    "feedback_evidence_links",
    "feedback_idempotency_records",
    "feedback_improvement_candidates",
    "feedback_review_case_snapshots",
    "offline_evaluation_candidates",
    "release_gate_decisions",
    "reviewer_accounts",
    "reviewer_auth_sessions",
    "reviewer_idempotency_records",
    "shadow_test_candidates",
    "validation_runs",
)
IMMUTABLE_PHASE7_TABLES = (
    "approved_feedback_labels",
    "feedback_adjudications",
    "feedback_confidence_assessments",
    "feedback_events",
    "feedback_evidence_links",
    "feedback_improvement_candidates",
    "feedback_review_case_snapshots",
    "offline_evaluation_candidates",
    "release_gate_decisions",
    "shadow_test_candidates",
    "validation_runs",
)


def upgrade() -> None:
    """Add immutable feedback, controlled review, and dual-track validation persistence."""
    op.create_unique_constraint(
        "uq_personal_ranking_items_feedback_binding",
        "personal_ranking_items",
        [
            "ranking_snapshot_id",
            "match_snapshot_id",
            "opportunity_id",
            "opportunity_version",
        ],
    )
    op.create_unique_constraint(
        "uq_user_state_snapshots_feedback_binding",
        "user_state_snapshots",
        ["user_state_snapshot_id", "version", "user_id"],
    )
    op.create_table(
        "reviewer_accounts",
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.Column("principal_label", sa.String(length=64), nullable=False),
        sa.Column("roles", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("allowed_purposes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(roles) = 'array' and jsonb_array_length(roles) >= 1",
            name=op.f("ck_reviewer_accounts_roles_nonempty_array"),
        ),
        sa.CheckConstraint(
            "allowed_purposes = '[\"FEEDBACK_REVIEW_AND_VALIDATION\"]'::jsonb",
            name=op.f("ck_reviewer_accounts_allowed_purposes_value"),
        ),
        sa.CheckConstraint(
            "length(btrim(principal_label)) >= 1",
            name=op.f("ck_reviewer_accounts_principal_label_nonempty"),
        ),
        sa.CheckConstraint(
            'roles <@ \'["FEEDBACK_REVIEWER", "FEEDBACK_ADJUDICATOR", '
            '"LABEL_CURATOR", "VALIDATION_REVIEWER"]\'::jsonb',
            name=op.f("ck_reviewer_accounts_roles_values"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(reviewer_id) = 7",
            name=op.f("ck_reviewer_accounts_reviewer_id_uuid7"),
        ),
        sa.PrimaryKeyConstraint("reviewer_id", name=op.f("pk_reviewer_accounts")),
        sa.UniqueConstraint("principal_label", name=op.f("uq_reviewer_accounts_principal_label")),
    )
    op.create_table(
        "feedback_idempotency_records",
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("key_sha256", sa.String(length=64), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("resource_kind", sa.String(length=24), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("response_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "key_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_feedback_idempotency_records_key_sha256_format"),
        ),
        sa.CheckConstraint(
            "request_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_feedback_idempotency_records_request_sha256_format"),
        ),
        sa.CheckConstraint(
            "resource_kind in ('FEEDBACK_EVENT', 'EVIDENCE_LINK')",
            name=op.f("ck_feedback_idempotency_records_resource_kind_values"),
        ),
        sa.CheckConstraint(
            "length(btrim(operation)) >= 1",
            name=op.f("ck_feedback_idempotency_records_operation_nonempty"),
        ),
        sa.CheckConstraint(
            "response_version >= 1",
            name=op.f("ck_feedback_idempotency_records_positive_response_version"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["personal_users.user_id"],
            name=op.f("fk_feedback_idempotency_records_owner_user_id_personal_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "owner_user_id", "operation", "key_sha256", name=op.f("pk_feedback_idempotency_records")
        ),
    )
    op.create_table(
        "feedback_improvement_candidates",
        sa.Column("improvement_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("validation_cycle_id", sa.Uuid(), nullable=False),
        sa.Column("approved_label_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("direction", sa.String(length=40), nullable=False),
        sa.Column("component", sa.String(length=128), nullable=False),
        sa.Column("input_manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("change_statement", sa.Text(), nullable=False),
        sa.Column("candidate_sha256", sa.String(length=64), nullable=False),
        sa.Column("evidence_class", sa.String(length=48), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("created_by_reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "candidate_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_feedback_improvement_candidates_candidate_sha256_format"),
        ),
        sa.CheckConstraint(
            "direction in ('EXPLANATION_CLARITY', 'OPPORTUNITY_FACT_QUALITY', "
            "'ELIGIBILITY_RULE_CANDIDATE', 'RANKING_POLICY_CANDIDATE')",
            name=op.f("ck_feedback_improvement_candidates_direction_values"),
        ),
        sa.CheckConstraint(
            "evidence_class in ('SYNTHETIC_FEEDBACK_WORKFLOW_ONLY', 'CONSENTED_HUMAN_PARTICIPANT')",
            name=op.f("ck_feedback_improvement_candidates_evidence_class_values"),
        ),
        sa.CheckConstraint(
            "input_manifest_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_feedback_improvement_candidates_input_manifest_sha256_format"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(approved_label_ids) = 'array' and "
            "jsonb_array_length(approved_label_ids) >= 1",
            name=op.f("ck_feedback_improvement_candidates_label_ids_nonempty"),
        ),
        sa.CheckConstraint(
            "length(btrim(change_statement)) between 1 and 500",
            name=op.f("ck_feedback_improvement_candidates_change_statement_bounds"),
        ),
        sa.CheckConstraint(
            "length(btrim(component)) >= 1",
            name=op.f("ck_feedback_improvement_candidates_component_nonempty"),
        ),
        sa.CheckConstraint(
            "selected is true", name=op.f("ck_feedback_improvement_candidates_selected_only")
        ),
        sa.CheckConstraint(
            "uuid_extract_version(improvement_candidate_id) = 7",
            name=op.f("ck_feedback_improvement_candidates_candidate_id_uuid7"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(validation_cycle_id) = 7",
            name=op.f("ck_feedback_improvement_candidates_validation_cycle_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_reviewer_id"],
            ["reviewer_accounts.reviewer_id"],
            name=op.f(
                "fk_feedback_improvement_candidates_created_by_reviewer_id_reviewer_accounts"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "improvement_candidate_id", name=op.f("pk_feedback_improvement_candidates")
        ),
        sa.UniqueConstraint(
            "candidate_sha256", name=op.f("uq_feedback_improvement_candidates_candidate_sha256")
        ),
        sa.UniqueConstraint("validation_cycle_id", name="uq_phase7_validation_cycle_candidate"),
    )
    op.create_table(
        "reviewer_auth_sessions",
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "token_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_reviewer_auth_sessions_token_sha256_format"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_reviewer_auth_sessions_expiry_after_creation")
        ),
        sa.CheckConstraint(
            "revoked_at is null or revoked_at >= created_at",
            name=op.f("ck_reviewer_auth_sessions_revocation_after_creation"),
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["reviewer_accounts.reviewer_id"],
            name=op.f("fk_reviewer_auth_sessions_reviewer_id_reviewer_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("token_sha256", name=op.f("pk_reviewer_auth_sessions")),
    )
    op.create_table(
        "reviewer_idempotency_records",
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("key_sha256", sa.String(length=64), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("resource_kind", sa.String(length=24), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "key_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_reviewer_idempotency_records_key_sha256_format"),
        ),
        sa.CheckConstraint(
            "request_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_reviewer_idempotency_records_request_sha256_format"),
        ),
        sa.CheckConstraint(
            "resource_kind in ('ASSESSMENT', 'ADJUDICATION', 'LABEL', "
            "'IMPROVEMENT', 'OFFLINE', 'SHADOW', 'VALIDATION_RUN', 'GATE_DECISION')",
            name=op.f("ck_reviewer_idempotency_records_resource_kind_values"),
        ),
        sa.CheckConstraint(
            "length(btrim(operation)) >= 1",
            name=op.f("ck_reviewer_idempotency_records_operation_nonempty"),
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["reviewer_accounts.reviewer_id"],
            name=op.f("fk_reviewer_idempotency_records_reviewer_id_reviewer_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "reviewer_id", "operation", "key_sha256", name=op.f("pk_reviewer_idempotency_records")
        ),
    )
    op.create_table(
        "offline_evaluation_candidates",
        sa.Column("offline_evaluation_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("improvement_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version", sa.Integer(), nullable=False),
        sa.Column("dataset_sha256", sa.String(length=64), nullable=False),
        sa.Column("baseline_component_version", sa.String(length=128), nullable=False),
        sa.Column("candidate_component_version", sa.String(length=128), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("result_sha256", sa.String(length=64), nullable=False),
        sa.Column("evidence_class", sa.String(length=48), nullable=False),
        sa.Column("created_by_reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "dataset_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_offline_evaluation_candidates_dataset_sha256_format"),
        ),
        sa.CheckConstraint(
            "evidence_class in ('SYNTHETIC_SIMULATION_ONLY', 'CONSENTED_HUMAN_PARTICIPANT')",
            name=op.f("ck_offline_evaluation_candidates_evidence_class_values"),
        ),
        sa.CheckConstraint(
            "outcome in ('PASSED', 'FAILED')",
            name=op.f("ck_offline_evaluation_candidates_outcome_values"),
        ),
        sa.CheckConstraint(
            "result_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_offline_evaluation_candidates_result_sha256_format"),
        ),
        sa.CheckConstraint(
            "dataset_version >= 1",
            name=op.f("ck_offline_evaluation_candidates_positive_dataset_version"),
        ),
        sa.CheckConstraint(
            "length(btrim(baseline_component_version)) >= 1",
            name=op.f("ck_offline_evaluation_candidates_baseline_version_nonempty"),
        ),
        sa.CheckConstraint(
            "length(btrim(candidate_component_version)) >= 1",
            name=op.f("ck_offline_evaluation_candidates_candidate_version_nonempty"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(offline_evaluation_candidate_id) = 7",
            name=op.f("ck_offline_evaluation_candidates_offline_candidate_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_reviewer_id"],
            ["reviewer_accounts.reviewer_id"],
            name=op.f("fk_offline_evaluation_candidates_created_by_reviewer_id_reviewer_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["improvement_candidate_id"],
            ["feedback_improvement_candidates.improvement_candidate_id"],
            name=op.f(
                "fk_offline_evaluation_candidates_improvement_candidate_id_feedback_improvement_candidates"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "offline_evaluation_candidate_id", name=op.f("pk_offline_evaluation_candidates")
        ),
        sa.UniqueConstraint(
            "improvement_candidate_id",
            "dataset_id",
            "dataset_version",
            name="uq_offline_candidate_dataset",
        ),
        sa.UniqueConstraint(
            "offline_evaluation_candidate_id",
            "improvement_candidate_id",
            name="uq_offline_candidate_improvement",
        ),
    )
    op.create_table(
        "validation_runs",
        sa.Column("validation_run_id", sa.Uuid(), nullable=False),
        sa.Column("validation_cycle_id", sa.Uuid(), nullable=False),
        sa.Column("improvement_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version", sa.Integer(), nullable=False),
        sa.Column("dataset_sha256", sa.String(length=64), nullable=False),
        sa.Column("track", sa.String(length=24), nullable=False),
        sa.Column("evidence_class", sa.String(length=48), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.Column("release_qualification_eligible", sa.Boolean(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by_reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(track = 'SIMULATION' and evidence_class = 'SYNTHETIC_SIMULATION_ONLY' "
            "and synthetic is true and release_qualification_eligible is false) or "
            "(track = 'HUMAN_PARTICIPANT' and "
            "evidence_class = 'CONSENTED_HUMAN_PARTICIPANT' and synthetic is false)",
            name=op.f("ck_validation_runs_track_evidence_separation"),
        ),
        sa.CheckConstraint(
            "dataset_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_validation_runs_dataset_sha256_format"),
        ),
        sa.CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_validation_runs_input_sha256_format")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metrics) = 'object'", name=op.f("ck_validation_runs_metrics_object")
        ),
        sa.CheckConstraint(
            "outcome in ('PASSED', 'FAILED')", name=op.f("ck_validation_runs_outcome_values")
        ),
        sa.CheckConstraint(
            "track in ('SIMULATION', 'HUMAN_PARTICIPANT')",
            name=op.f("ck_validation_runs_track_values"),
        ),
        sa.CheckConstraint(
            "completed_at >= started_at", name=op.f("ck_validation_runs_timestamp_order")
        ),
        sa.CheckConstraint(
            "dataset_version >= 1", name=op.f("ck_validation_runs_positive_dataset_version")
        ),
        sa.CheckConstraint(
            "uuid_extract_version(validation_run_id) = 7",
            name=op.f("ck_validation_runs_validation_run_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_reviewer_id"],
            ["reviewer_accounts.reviewer_id"],
            name=op.f("fk_validation_runs_created_by_reviewer_id_reviewer_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["improvement_candidate_id"],
            ["feedback_improvement_candidates.improvement_candidate_id"],
            name=op.f(
                "fk_validation_runs_improvement_candidate_id_feedback_improvement_candidates"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("validation_run_id", name=op.f("pk_validation_runs")),
        sa.UniqueConstraint("validation_cycle_id", "track", name="uq_validation_cycle_track"),
        sa.UniqueConstraint(
            "validation_run_id", "improvement_candidate_id", name="uq_validation_run_improvement"
        ),
    )
    op.create_table(
        "shadow_test_candidates",
        sa.Column("shadow_test_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("improvement_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("offline_evaluation_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_component_version", sa.String(length=128), nullable=False),
        sa.Column("candidate_component_version", sa.String(length=128), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("comparison_sha256", sa.String(length=64), nullable=False),
        sa.Column("evidence_class", sa.String(length=48), nullable=False),
        sa.Column("created_by_reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "comparison_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_shadow_test_candidates_comparison_sha256_format"),
        ),
        sa.CheckConstraint(
            "evidence_class in ('SYNTHETIC_SIMULATION_ONLY', 'CONSENTED_HUMAN_PARTICIPANT')",
            name=op.f("ck_shadow_test_candidates_evidence_class_values"),
        ),
        sa.CheckConstraint(
            "outcome in ('PASSED', 'FAILED')", name=op.f("ck_shadow_test_candidates_outcome_values")
        ),
        sa.CheckConstraint(
            "length(btrim(baseline_component_version)) >= 1",
            name=op.f("ck_shadow_test_candidates_baseline_version_nonempty"),
        ),
        sa.CheckConstraint(
            "length(btrim(candidate_component_version)) >= 1",
            name=op.f("ck_shadow_test_candidates_candidate_version_nonempty"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(shadow_test_candidate_id) = 7",
            name=op.f("ck_shadow_test_candidates_shadow_candidate_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_reviewer_id"],
            ["reviewer_accounts.reviewer_id"],
            name=op.f("fk_shadow_test_candidates_created_by_reviewer_id_reviewer_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["offline_evaluation_candidate_id", "improvement_candidate_id"],
            [
                "offline_evaluation_candidates.offline_evaluation_candidate_id",
                "offline_evaluation_candidates.improvement_candidate_id",
            ],
            name=op.f(
                "fk_shadow_test_candidates_offline_evaluation_candidate_id_offline_evaluation_candidates"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("shadow_test_candidate_id", name=op.f("pk_shadow_test_candidates")),
        sa.UniqueConstraint(
            "offline_evaluation_candidate_id",
            name=op.f("uq_shadow_test_candidates_offline_evaluation_candidate_id"),
        ),
        sa.UniqueConstraint(
            "shadow_test_candidate_id",
            "improvement_candidate_id",
            "offline_evaluation_candidate_id",
            name="uq_shadow_candidate_gate_binding",
        ),
    )
    op.create_table(
        "release_gate_decisions",
        sa.Column("release_gate_decision_id", sa.Uuid(), nullable=False),
        sa.Column("validation_cycle_id", sa.Uuid(), nullable=False),
        sa.Column("improvement_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("offline_evaluation_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("shadow_test_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("simulation_validation_run_id", sa.Uuid(), nullable=True),
        sa.Column("human_validation_run_id", sa.Uuid(), nullable=True),
        sa.Column("decision", sa.String(length=64), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("decided_by_reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision <> 'CANDIDATE_ACCEPTED_FOR_FUTURE_IMPLEMENTATION' or "
            "(simulation_validation_run_id is not null and "
            "human_validation_run_id is not null)",
            name=op.f("ck_release_gate_decisions_accepted_requires_both_tracks"),
        ),
        sa.CheckConstraint(
            "decision <> 'HOLD_MISSING_HUMAN_EVIDENCE' or "
            "(simulation_validation_run_id is not null and "
            "human_validation_run_id is null)",
            name=op.f("ck_release_gate_decisions_missing_human_hold_shape"),
        ),
        sa.CheckConstraint(
            "decision in ('HOLD_MISSING_HUMAN_EVIDENCE', "
            "'HOLD_ENGINEERING_FAILURE', 'REJECTED', "
            "'CANDIDATE_ACCEPTED_FOR_FUTURE_IMPLEMENTATION')",
            name=op.f("ck_release_gate_decisions_decision_values"),
        ),
        sa.CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_release_gate_decisions_input_sha256_format"),
        ),
        sa.CheckConstraint(
            "length(btrim(rationale)) between 1 and 500",
            name=op.f("ck_release_gate_decisions_rationale_bounds"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(release_gate_decision_id) = 7",
            name=op.f("ck_release_gate_decisions_release_gate_decision_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_reviewer_id"],
            ["reviewer_accounts.reviewer_id"],
            name=op.f("fk_release_gate_decisions_decided_by_reviewer_id_reviewer_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["human_validation_run_id", "improvement_candidate_id"],
            ["validation_runs.validation_run_id", "validation_runs.improvement_candidate_id"],
            name=op.f("fk_release_gate_decisions_human_validation_run_id_validation_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["improvement_candidate_id"],
            ["feedback_improvement_candidates.improvement_candidate_id"],
            name=op.f(
                "fk_release_gate_decisions_improvement_candidate_id_feedback_improvement_candidates"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["offline_evaluation_candidate_id", "improvement_candidate_id"],
            [
                "offline_evaluation_candidates.offline_evaluation_candidate_id",
                "offline_evaluation_candidates.improvement_candidate_id",
            ],
            name=op.f(
                "fk_release_gate_decisions_offline_evaluation_candidate_id_offline_evaluation_candidates"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "shadow_test_candidate_id",
                "improvement_candidate_id",
                "offline_evaluation_candidate_id",
            ],
            [
                "shadow_test_candidates.shadow_test_candidate_id",
                "shadow_test_candidates.improvement_candidate_id",
                "shadow_test_candidates.offline_evaluation_candidate_id",
            ],
            name=op.f("fk_release_gate_decisions_shadow_test_candidate_id_shadow_test_candidates"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["simulation_validation_run_id", "improvement_candidate_id"],
            ["validation_runs.validation_run_id", "validation_runs.improvement_candidate_id"],
            name=op.f("fk_release_gate_decisions_simulation_validation_run_id_validation_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("release_gate_decision_id", name=op.f("pk_release_gate_decisions")),
        sa.UniqueConstraint(
            "validation_cycle_id", name=op.f("uq_release_gate_decisions_validation_cycle_id")
        ),
    )
    op.create_table(
        "feedback_events",
        sa.Column("feedback_event_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("ranking_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("match_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("user_state_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("user_state_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("claim_kind", sa.String(length=40), nullable=False),
        sa.Column("user_statement", sa.Text(), nullable=True),
        sa.Column("structured_reason_code", sa.String(length=64), nullable=False),
        sa.Column("consent_version", sa.String(length=40), nullable=False),
        sa.Column("consent_scope", sa.String(length=48), nullable=False),
        sa.Column("contract_version", sa.String(length=16), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "claim_kind in ('ELIGIBILITY_CORRECTION', 'OPPORTUNITY_FACT_CORRECTION', "
            "'EXPLANATION_UNCLEAR', 'RANKING_IRRELEVANT')",
            name=op.f("ck_feedback_events_claim_kind_values"),
        ),
        sa.CheckConstraint(
            "consent_scope = 'FEEDBACK_REVIEW_AND_VALIDATION'",
            name=op.f("ck_feedback_events_consent_scope_value"),
        ),
        sa.CheckConstraint(
            "consent_version = 'phase7-feedback-consent-v1'",
            name=op.f("ck_feedback_events_consent_version_v1"),
        ),
        sa.CheckConstraint(
            "contract_version = '0.6.0'", name=op.f("ck_feedback_events_contract_version_v06")
        ),
        sa.CheckConstraint(
            "event_type in ('STRUCTURED_CORRECTION', 'EXPLICIT_EVALUATION')",
            name=op.f("ck_feedback_events_event_type_values"),
        ),
        sa.CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_feedback_events_input_sha256_format")
        ),
        sa.CheckConstraint(
            "length(btrim(structured_reason_code)) >= 1",
            name=op.f("ck_feedback_events_reason_code_nonempty"),
        ),
        sa.CheckConstraint(
            "opportunity_version >= 1", name=op.f("ck_feedback_events_positive_opportunity_version")
        ),
        sa.CheckConstraint(
            "user_state_version >= 1", name=op.f("ck_feedback_events_positive_user_state_version")
        ),
        sa.CheckConstraint(
            "user_statement is null or (length(btrim(user_statement)) between 1 and 500)",
            name=op.f("ck_feedback_events_user_statement_bounds"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(feedback_event_id) = 7",
            name=op.f("ck_feedback_events_feedback_event_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["personal_users.user_id"],
            name=op.f("fk_feedback_events_owner_user_id_personal_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ranking_snapshot_id", "match_snapshot_id", "opportunity_id", "opportunity_version"],
            [
                "personal_ranking_items.ranking_snapshot_id",
                "personal_ranking_items.match_snapshot_id",
                "personal_ranking_items.opportunity_id",
                "personal_ranking_items.opportunity_version",
            ],
            name=op.f("fk_feedback_events_ranking_snapshot_id_personal_ranking_items"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ranking_snapshot_id", "owner_user_id"],
            [
                "personal_ranking_snapshots.ranking_snapshot_id",
                "personal_ranking_snapshots.user_id",
            ],
            name=op.f("fk_feedback_events_ranking_snapshot_id_personal_ranking_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_state_snapshot_id", "user_state_version", "owner_user_id"],
            [
                "user_state_snapshots.user_state_snapshot_id",
                "user_state_snapshots.version",
                "user_state_snapshots.user_id",
            ],
            name=op.f("fk_feedback_events_user_state_snapshot_id_user_state_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("feedback_event_id", name=op.f("pk_feedback_events")),
        sa.UniqueConstraint(
            "feedback_event_id",
            "match_snapshot_id",
            "opportunity_id",
            "opportunity_version",
            name="uq_feedback_events_label_binding",
        ),
        sa.UniqueConstraint("owner_user_id", "input_sha256", name="uq_feedback_events_owner_input"),
    )
    op.create_table(
        "feedback_evidence_links",
        sa.Column("feedback_evidence_link_id", sa.Uuid(), nullable=False),
        sa.Column("feedback_event_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_ref_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("relation", sa.String(length=16), nullable=False),
        sa.Column("actor_kind", sa.String(length=16), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_reviewer_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(actor_kind = 'USER' and actor_user_id is not null and "
            "actor_reviewer_id is null) or (actor_kind = 'REVIEWER' and "
            "actor_user_id is null and actor_reviewer_id is not null)",
            name=op.f("ck_feedback_evidence_links_actor_identity_shape"),
        ),
        sa.CheckConstraint(
            "actor_kind in ('USER', 'REVIEWER')",
            name=op.f("ck_feedback_evidence_links_actor_kind_values"),
        ),
        sa.CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_feedback_evidence_links_input_sha256_format"),
        ),
        sa.CheckConstraint(
            "relation in ('SUPPORTS', 'CONTRADICTS')",
            name=op.f("ck_feedback_evidence_links_relation_values"),
        ),
        sa.CheckConstraint(
            "note is null or (length(btrim(note)) between 1 and 300)",
            name=op.f("ck_feedback_evidence_links_note_bounds"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(feedback_evidence_link_id) = 7",
            name=op.f("ck_feedback_evidence_links_feedback_evidence_link_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_reviewer_id"],
            ["reviewer_accounts.reviewer_id"],
            name=op.f("fk_feedback_evidence_links_actor_reviewer_id_reviewer_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["personal_users.user_id"],
            name=op.f("fk_feedback_evidence_links_actor_user_id_personal_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_ref_id", "document_id"],
            ["evidence_refs.evidence_ref_id", "evidence_refs.document_id"],
            name=op.f("fk_feedback_evidence_links_evidence_ref_id_evidence_refs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["feedback_event_id"],
            ["feedback_events.feedback_event_id"],
            name=op.f("fk_feedback_evidence_links_feedback_event_id_feedback_events"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "feedback_evidence_link_id", name=op.f("pk_feedback_evidence_links")
        ),
        sa.UniqueConstraint(
            "feedback_event_id", "input_sha256", name="uq_feedback_evidence_links_event_input"
        ),
    )
    op.create_table(
        "feedback_review_case_snapshots",
        sa.Column("review_case_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("review_case_id", sa.Uuid(), nullable=False),
        sa.Column("feedback_event_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_reviewer_id", sa.Uuid(), nullable=True),
        sa.Column("transition_reason", sa.String(length=300), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_feedback_review_case_snapshots_input_sha256_format"),
        ),
        sa.CheckConstraint(
            "status in ('RECEIVED', 'NEEDS_EVIDENCE', 'CONFLICT', 'CONFIRMED', 'REJECTED')",
            name=op.f("ck_feedback_review_case_snapshots_status_values"),
        ),
        sa.CheckConstraint(
            "length(btrim(transition_reason)) between 1 and 300",
            name=op.f("ck_feedback_review_case_snapshots_transition_reason_bounds"),
        ),
        sa.CheckConstraint(
            "priority between 1 and 3",
            name=op.f("ck_feedback_review_case_snapshots_priority_range"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(review_case_id) = 7",
            name=op.f("ck_feedback_review_case_snapshots_review_case_id_uuid7"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(review_case_snapshot_id) = 7",
            name=op.f("ck_feedback_review_case_snapshots_review_case_snapshot_id_uuid7"),
        ),
        sa.CheckConstraint(
            "version >= 1", name=op.f("ck_feedback_review_case_snapshots_positive_version")
        ),
        sa.ForeignKeyConstraint(
            ["assigned_reviewer_id"],
            ["reviewer_accounts.reviewer_id"],
            name=op.f("fk_feedback_review_case_snapshots_assigned_reviewer_id_reviewer_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["feedback_event_id"],
            ["feedback_events.feedback_event_id"],
            name=op.f("fk_feedback_review_case_snapshots_feedback_event_id_feedback_events"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "review_case_snapshot_id", name=op.f("pk_feedback_review_case_snapshots")
        ),
        sa.UniqueConstraint("review_case_id", "version", name="uq_review_case_stream_version"),
    )
    op.create_table(
        "feedback_confidence_assessments",
        sa.Column("confidence_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("review_case_id", sa.Uuid(), nullable=False),
        sa.Column("review_case_version", sa.Integer(), nullable=False),
        sa.Column("evidence_complete", sa.Boolean(), nullable=False),
        sa.Column("confidence_band", sa.String(length=16), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("conflict", sa.Boolean(), nullable=False),
        sa.Column("evidence_ref_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("review_purpose", sa.String(length=48), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence_band in ('LOW', 'MEDIUM', 'HIGH')",
            name=op.f("ck_feedback_confidence_assessments_confidence_values"),
        ),
        sa.CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_feedback_confidence_assessments_input_sha256_format"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence_ref_ids) = 'array'",
            name=op.f("ck_feedback_confidence_assessments_evidence_ref_ids_array"),
        ),
        sa.CheckConstraint(
            "review_purpose = 'FEEDBACK_REVIEW_AND_VALIDATION'",
            name=op.f("ck_feedback_confidence_assessments_review_purpose_value"),
        ),
        sa.CheckConstraint(
            "risk_level in ('NORMAL', 'HIGH_IMPACT')",
            name=op.f("ck_feedback_confidence_assessments_risk_values"),
        ),
        sa.CheckConstraint(
            "evidence_complete is false or jsonb_array_length(evidence_ref_ids) >= 1",
            name=op.f("ck_feedback_confidence_assessments_complete_evidence_nonempty"),
        ),
        sa.CheckConstraint(
            "length(btrim(rationale)) between 1 and 500",
            name=op.f("ck_feedback_confidence_assessments_rationale_bounds"),
        ),
        sa.CheckConstraint(
            "review_case_version >= 1",
            name=op.f("ck_feedback_confidence_assessments_positive_review_case_version"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(confidence_assessment_id) = 7",
            name=op.f("ck_feedback_confidence_assessments_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["review_case_id", "review_case_version"],
            [
                "feedback_review_case_snapshots.review_case_id",
                "feedback_review_case_snapshots.version",
            ],
            name=op.f(
                "fk_feedback_confidence_assessments_review_case_id_feedback_review_case_snapshots"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["reviewer_accounts.reviewer_id"],
            name=op.f("fk_feedback_confidence_assessments_reviewer_id_reviewer_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "confidence_assessment_id", name=op.f("pk_feedback_confidence_assessments")
        ),
        sa.UniqueConstraint(
            "confidence_assessment_id",
            "review_case_id",
            "review_case_version",
            name="uq_feedback_assessment_case_version",
        ),
    )
    op.create_table(
        "feedback_adjudications",
        sa.Column("feedback_adjudication_id", sa.Uuid(), nullable=False),
        sa.Column("review_case_id", sa.Uuid(), nullable=False),
        sa.Column("review_case_version", sa.Integer(), nullable=False),
        sa.Column("confidence_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("evidence_ref_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("adjudicator_id", sa.Uuid(), nullable=False),
        sa.Column("review_purpose", sa.String(length=48), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision <> 'CONFIRMED' or jsonb_array_length(evidence_ref_ids) >= 1",
            name=op.f("ck_feedback_adjudications_confirmed_evidence_nonempty"),
        ),
        sa.CheckConstraint(
            "decision in ('NEEDS_EVIDENCE', 'CONFLICT', 'CONFIRMED', 'REJECTED')",
            name=op.f("ck_feedback_adjudications_decision_values"),
        ),
        sa.CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_feedback_adjudications_input_sha256_format"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence_ref_ids) = 'array'",
            name=op.f("ck_feedback_adjudications_evidence_ref_ids_array"),
        ),
        sa.CheckConstraint(
            "review_purpose = 'FEEDBACK_REVIEW_AND_VALIDATION'",
            name=op.f("ck_feedback_adjudications_review_purpose_value"),
        ),
        sa.CheckConstraint(
            "length(btrim(reason)) between 1 and 500",
            name=op.f("ck_feedback_adjudications_reason_bounds"),
        ),
        sa.CheckConstraint(
            "review_case_version >= 1",
            name=op.f("ck_feedback_adjudications_positive_review_case_version"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(feedback_adjudication_id) = 7",
            name=op.f("ck_feedback_adjudications_feedback_adjudication_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["adjudicator_id"],
            ["reviewer_accounts.reviewer_id"],
            name=op.f("fk_feedback_adjudications_adjudicator_id_reviewer_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["confidence_assessment_id", "review_case_id", "review_case_version"],
            [
                "feedback_confidence_assessments.confidence_assessment_id",
                "feedback_confidence_assessments.review_case_id",
                "feedback_confidence_assessments.review_case_version",
            ],
            name=op.f(
                "fk_feedback_adjudications_confidence_assessment_id_feedback_confidence_assessments"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("feedback_adjudication_id", name=op.f("pk_feedback_adjudications")),
        sa.UniqueConstraint(
            "review_case_id", "review_case_version", name="uq_feedback_adjudication_case_version"
        ),
    )
    op.create_table(
        "approved_feedback_labels",
        sa.Column("approved_feedback_label_id", sa.Uuid(), nullable=False),
        sa.Column("feedback_event_id", sa.Uuid(), nullable=False),
        sa.Column("feedback_adjudication_id", sa.Uuid(), nullable=False),
        sa.Column("match_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("claim_kind", sa.String(length=40), nullable=False),
        sa.Column("approved_target_value", sa.Text(), nullable=False),
        sa.Column("evidence_ref_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_class", sa.String(length=48), nullable=False),
        sa.Column("curator_id", sa.Uuid(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "claim_kind in ('ELIGIBILITY_CORRECTION', 'OPPORTUNITY_FACT_CORRECTION', "
            "'EXPLANATION_UNCLEAR', 'RANKING_IRRELEVANT')",
            name=op.f("ck_approved_feedback_labels_claim_kind_values"),
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_approved_feedback_labels_content_sha256_format"),
        ),
        sa.CheckConstraint(
            "evidence_class in ('SYNTHETIC_FEEDBACK_WORKFLOW_ONLY', 'CONSENTED_HUMAN_PARTICIPANT')",
            name=op.f("ck_approved_feedback_labels_evidence_class_values"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence_ref_ids) = 'array' and "
            "jsonb_array_length(evidence_ref_ids) >= 1",
            name=op.f("ck_approved_feedback_labels_evidence_ref_ids_nonempty_array"),
        ),
        sa.CheckConstraint(
            "length(btrim(approved_target_value)) between 1 and 500",
            name=op.f("ck_approved_feedback_labels_approved_target_bounds"),
        ),
        sa.CheckConstraint(
            "opportunity_version >= 1",
            name=op.f("ck_approved_feedback_labels_positive_opportunity_version"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(approved_feedback_label_id) = 7",
            name=op.f("ck_approved_feedback_labels_approved_feedback_label_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["curator_id"],
            ["reviewer_accounts.reviewer_id"],
            name=op.f("fk_approved_feedback_labels_curator_id_reviewer_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["feedback_adjudication_id"],
            ["feedback_adjudications.feedback_adjudication_id"],
            name=op.f(
                "fk_approved_feedback_labels_feedback_adjudication_id_feedback_adjudications"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["feedback_event_id", "match_snapshot_id", "opportunity_id", "opportunity_version"],
            [
                "feedback_events.feedback_event_id",
                "feedback_events.match_snapshot_id",
                "feedback_events.opportunity_id",
                "feedback_events.opportunity_version",
            ],
            name=op.f("fk_approved_feedback_labels_feedback_event_id_feedback_events"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "approved_feedback_label_id", name=op.f("pk_approved_feedback_labels")
        ),
        sa.UniqueConstraint(
            "feedback_adjudication_id",
            name=op.f("uq_approved_feedback_labels_feedback_adjudication_id"),
        ),
    )
    op.execute(
        """
        CREATE FUNCTION phase7_reject_immutable_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'Phase 7 governed fact is immutable';
        END;
        $$
        """
    )
    for table_name in IMMUTABLE_PHASE7_TABLES:
        op.execute(
            sa.text(
                f"CREATE TRIGGER phase7_reject_mutation "
                f"BEFORE UPDATE OR DELETE ON {table_name} "
                "FOR EACH ROW EXECUTE FUNCTION phase7_reject_immutable_mutation()"
            )
        )


def downgrade() -> None:
    """Refuse destructive downgrade when any Phase 7 governance row exists."""
    connection = op.get_bind()
    for table_name in PHASE7_TABLES:
        populated = connection.execute(
            sa.text(f"SELECT EXISTS (SELECT 1 FROM {table_name} LIMIT 1)")
        ).scalar_one()
        if populated:
            raise RuntimeError("cannot downgrade Phase 7 while governed rows exist")

    for table_name in IMMUTABLE_PHASE7_TABLES:
        op.execute(sa.text(f"DROP TRIGGER phase7_reject_mutation ON {table_name}"))
    op.execute("DROP FUNCTION phase7_reject_immutable_mutation()")
    op.drop_table("approved_feedback_labels")
    op.drop_table("feedback_adjudications")
    op.drop_table("feedback_confidence_assessments")
    op.drop_table("feedback_review_case_snapshots")
    op.drop_table("feedback_evidence_links")
    op.drop_table("feedback_events")
    op.drop_table("release_gate_decisions")
    op.drop_table("shadow_test_candidates")
    op.drop_table("validation_runs")
    op.drop_table("offline_evaluation_candidates")
    op.drop_table("reviewer_idempotency_records")
    op.drop_table("reviewer_auth_sessions")
    op.drop_table("feedback_improvement_candidates")
    op.drop_table("feedback_idempotency_records")
    op.drop_table("reviewer_accounts")
    op.drop_constraint(
        "uq_user_state_snapshots_feedback_binding",
        "user_state_snapshots",
        type_="unique",
    )
    op.drop_constraint(
        "uq_personal_ranking_items_feedback_binding",
        "personal_ranking_items",
        type_="unique",
    )
