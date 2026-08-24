"""p9b_fact_lifecycle

Revision ID: 20260824_0013
Revises: 20260824_0012
Create Date: 2026-08-24 18:42:46.472500
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260824_0013"
down_revision: str | None = "20260824_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
        "uq_document_blocks_candidate_evidence_binding",
        "document_blocks",
        ["block_id", "evidence_ref_id", "document_id"],
    )
    op.create_unique_constraint(
        "uq_source_bundle_revisions_fact_binding",
        "source_bundle_revisions",
        ["source_bundle_revision_id", "opportunity_id", "opportunity_version"],
    )
    op.create_table(
        "extraction_runs",
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("source_bundle_revision_id", sa.Uuid(), nullable=False),
        sa.Column("target_scope", sa.String(length=16), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("opportunity_unit_id", sa.Uuid(), nullable=True),
        sa.Column("opportunity_unit_version_id", sa.Uuid(), nullable=True),
        sa.Column("unit_segmentation_version", sa.String(length=64), nullable=True),
        sa.Column("task_spec_version", sa.String(length=64), nullable=False),
        sa.Column("extractor_kind", sa.String(length=16), nullable=False),
        sa.Column("component_version", sa.String(length=128), nullable=False),
        sa.Column("producer_identity", sa.Text(), nullable=False),
        sa.Column("producer_response_id", sa.Text(), nullable=True),
        sa.Column(
            "ordered_input_block_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("input_block_set_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_binding_hash", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "(target_scope = 'OPPORTUNITY' and opportunity_unit_id is null and opportunity_unit_version_id is null and unit_segmentation_version is null) or (target_scope = 'UNIT' and opportunity_unit_id is not null and opportunity_unit_version_id is not null and length(btrim(unit_segmentation_version)) >= 1)",
            name=op.f("ck_extraction_runs_target_shape"),
        ),
        sa.CheckConstraint(
            "extractor_kind <> 'MODEL' or producer_response_id is not null",
            name=op.f("ck_extraction_runs_model_response_required"),
        ),
        sa.CheckConstraint(
            "extractor_kind in ('DETERMINISTIC', 'MODEL', 'HYBRID')",
            name=op.f("ck_extraction_runs_extractor_kind_values"),
        ),
        sa.CheckConstraint(
            "input_block_set_hash ~ '^[0-9a-f]{64}$' and evidence_binding_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_extraction_runs_hash_formats"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(ordered_input_block_ids) = 'array' and jsonb_array_length(ordered_input_block_ids) >= 1",
            name=op.f("ck_extraction_runs_input_blocks_nonempty"),
        ),
        sa.CheckConstraint(
            "status in ('SUCCEEDED', 'ABSTAINED', 'FAILED')",
            name=op.f("ck_extraction_runs_status_values"),
        ),
        sa.CheckConstraint(
            "target_scope in ('OPPORTUNITY', 'UNIT')",
            name=op.f("ck_extraction_runs_target_scope_values"),
        ),
        sa.CheckConstraint(
            "completed_at >= started_at", name=op.f("ck_extraction_runs_timestamp_order")
        ),
        sa.CheckConstraint(
            "opportunity_version >= 1", name=op.f("ck_extraction_runs_positive_opportunity_version")
        ),
        sa.CheckConstraint(
            "uuid_extract_version(extraction_run_id) = 7",
            name=op.f("ck_extraction_runs_run_id_uuid7"),
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
            name=op.f("fk_extraction_runs_opportunity_unit_id_opportunity_unit_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_bundle_revision_id", "opportunity_id", "opportunity_version"],
            [
                "source_bundle_revisions.source_bundle_revision_id",
                "source_bundle_revisions.opportunity_id",
                "source_bundle_revisions.opportunity_version",
            ],
            name=op.f("fk_extraction_runs_source_bundle_revision_id_source_bundle_revisions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("extraction_run_id", name=op.f("pk_extraction_runs")),
        sa.UniqueConstraint(
            "extraction_run_id",
            "target_scope",
            "opportunity_id",
            "opportunity_version",
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            name="uq_extraction_runs_candidate_binding",
        ),
    )
    op.create_table(
        "versioned_verified_fact_sets",
        sa.Column("verified_fact_set_id", sa.Uuid(), nullable=False),
        sa.Column("target_scope", sa.String(length=16), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("opportunity_unit_id", sa.Uuid(), nullable=True),
        sa.Column("opportunity_unit_version_id", sa.Uuid(), nullable=True),
        sa.Column("source_bundle_revision_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("relation_graph_version", sa.String(length=64), nullable=False),
        sa.Column("precedence_graph_version", sa.String(length=64), nullable=False),
        sa.Column(
            "reference_dataset_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("fact_schema_version", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(target_scope = 'OPPORTUNITY' and opportunity_unit_id is null and opportunity_unit_version_id is null) or (target_scope = 'UNIT' and opportunity_unit_id is not null and opportunity_unit_version_id is not null)",
            name=op.f("ck_versioned_verified_fact_sets_target_shape"),
        ),
        sa.CheckConstraint(
            "fact_schema_version = '0.8.0'",
            name=op.f("ck_versioned_verified_fact_sets_schema_version_v08"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reference_dataset_versions) = 'object'",
            name=op.f("ck_versioned_verified_fact_sets_reference_versions_object"),
        ),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'SUPERSEDED', 'STALE', 'WITHDRAWN')",
            name=op.f("ck_versioned_verified_fact_sets_status_values"),
        ),
        sa.CheckConstraint(
            "target_scope in ('OPPORTUNITY', 'UNIT')",
            name=op.f("ck_versioned_verified_fact_sets_target_scope_values"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(verified_fact_set_id) = 7",
            name=op.f("ck_versioned_verified_fact_sets_fact_set_id_uuid7"),
        ),
        sa.CheckConstraint(
            "version >= 1 and opportunity_version >= 1",
            name=op.f("ck_versioned_verified_fact_sets_positive_versions"),
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
            name=op.f(
                "fk_versioned_verified_fact_sets_opportunity_unit_id_opportunity_unit_versions"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_bundle_revision_id", "opportunity_id", "opportunity_version"],
            [
                "source_bundle_revisions.source_bundle_revision_id",
                "source_bundle_revisions.opportunity_id",
                "source_bundle_revisions.opportunity_version",
            ],
            name=op.f(
                "fk_versioned_verified_fact_sets_source_bundle_revision_id_source_bundle_revisions"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["versioned_verified_fact_sets.verified_fact_set_id"],
            name=op.f("fk_versioned_verified_fact_sets_supersedes_id_versioned_verified_fact_sets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "verified_fact_set_id", name=op.f("pk_versioned_verified_fact_sets")
        ),
        sa.UniqueConstraint(
            "verified_fact_set_id",
            "target_scope",
            "opportunity_id",
            "opportunity_version",
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            name="uq_versioned_verified_fact_sets_target_binding",
        ),
    )
    op.create_index(
        "uq_versioned_verified_fact_sets_active_opportunity",
        "versioned_verified_fact_sets",
        ["opportunity_id", "opportunity_version"],
        unique=True,
        postgresql_where=sa.text("target_scope = 'OPPORTUNITY' and status = 'ACTIVE'"),
    )
    op.create_index(
        "uq_versioned_verified_fact_sets_active_unit",
        "versioned_verified_fact_sets",
        ["opportunity_unit_id", "opportunity_unit_version_id"],
        unique=True,
        postgresql_where=sa.text("target_scope = 'UNIT' and status = 'ACTIVE'"),
    )
    op.create_index(
        "uq_versioned_verified_fact_sets_opportunity_version",
        "versioned_verified_fact_sets",
        ["opportunity_id", "opportunity_version", "version"],
        unique=True,
        postgresql_where=sa.text("target_scope = 'OPPORTUNITY'"),
    )
    op.create_index(
        "uq_versioned_verified_fact_sets_unit_version",
        "versioned_verified_fact_sets",
        ["opportunity_unit_id", "opportunity_unit_version_id", "version"],
        unique=True,
        postgresql_where=sa.text("target_scope = 'UNIT'"),
    )
    op.create_table(
        "extraction_candidates",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("target_scope", sa.String(length=16), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("opportunity_unit_id", sa.Uuid(), nullable=True),
        sa.Column("opportunity_unit_version_id", sa.Uuid(), nullable=True),
        sa.Column("field_name", sa.String(length=128), nullable=False),
        sa.Column(
            "raw_value", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "normalized_value_candidate",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("abstained", sa.Boolean(), nullable=False),
        sa.Column("candidate_reason_code", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(abstained and normalized_value_candidate is null and candidate_reason_code like 'UNKNOWN_%%') or (not abstained and normalized_value_candidate is not null)",
            name=op.f("ck_extraction_candidates_abstention_shape"),
        ),
        sa.CheckConstraint(
            "schema_version = '0.8.0'", name=op.f("ck_extraction_candidates_schema_version_v08")
        ),
        sa.CheckConstraint(
            "target_scope in ('OPPORTUNITY', 'UNIT')",
            name=op.f("ck_extraction_candidates_target_scope_values"),
        ),
        sa.CheckConstraint(
            "confidence is null or confidence between 0 and 1",
            name=op.f("ck_extraction_candidates_confidence_range"),
        ),
        sa.CheckConstraint(
            "length(btrim(field_name)) >= 1",
            name=op.f("ck_extraction_candidates_field_name_nonempty"),
        ),
        sa.CheckConstraint(
            "opportunity_version >= 1",
            name=op.f("ck_extraction_candidates_positive_opportunity_version"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(candidate_id) = 7",
            name=op.f("ck_extraction_candidates_candidate_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["extraction_run_id"],
            ["extraction_runs.extraction_run_id"],
            name=op.f("fk_extraction_candidates_extraction_run_id_extraction_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("candidate_id", name=op.f("pk_extraction_candidates")),
        sa.UniqueConstraint(
            "candidate_id", "extraction_run_id", name="uq_extraction_candidates_run_binding"
        ),
    )
    op.create_table(
        "extraction_run_input_blocks",
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("input_ordinal", sa.Integer(), nullable=False),
        sa.Column("block_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_ref_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "input_ordinal >= 1", name=op.f("ck_extraction_run_input_blocks_positive_ordinal")
        ),
        sa.ForeignKeyConstraint(
            ["block_id", "evidence_ref_id", "document_id"],
            [
                "document_blocks.block_id",
                "document_blocks.evidence_ref_id",
                "document_blocks.document_id",
            ],
            name=op.f("fk_extraction_run_input_blocks_block_id_document_blocks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_run_id"],
            ["extraction_runs.extraction_run_id"],
            name=op.f("fk_extraction_run_input_blocks_extraction_run_id_extraction_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "extraction_run_id", "input_ordinal", name=op.f("pk_extraction_run_input_blocks")
        ),
        sa.UniqueConstraint(
            "extraction_run_id", "block_id", name="uq_extraction_run_input_blocks_run_block"
        ),
    )
    op.create_table(
        "p9b_rule_candidates",
        sa.Column("rule_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("target_scope", sa.String(length=16), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("opportunity_unit_id", sa.Uuid(), nullable=True),
        sa.Column("opportunity_unit_version_id", sa.Uuid(), nullable=True),
        sa.Column("verified_fact_set_id", sa.Uuid(), nullable=False),
        sa.Column("rule_type", sa.String(length=32), nullable=False),
        sa.Column("proposed_rule_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("compiler_version", sa.String(length=64), nullable=False),
        sa.Column("producer_identity", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(target_scope = 'OPPORTUNITY' and opportunity_unit_id is null and opportunity_unit_version_id is null) or (target_scope = 'UNIT' and opportunity_unit_id is not null and opportunity_unit_version_id is not null)",
            name=op.f("ck_p9b_rule_candidates_target_shape"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(proposed_rule_payload) = 'object'",
            name=op.f("ck_p9b_rule_candidates_payload_object"),
        ),
        sa.CheckConstraint(
            "rule_type = 'ATOMIC_QUALIFICATION'",
            name=op.f("ck_p9b_rule_candidates_rule_type_values"),
        ),
        sa.CheckConstraint(
            "status = 'PROPOSED'", name=op.f("ck_p9b_rule_candidates_initial_status_proposed")
        ),
        sa.CheckConstraint(
            "target_scope in ('OPPORTUNITY', 'UNIT')",
            name=op.f("ck_p9b_rule_candidates_target_scope_values"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(rule_candidate_id) = 7",
            name=op.f("ck_p9b_rule_candidates_rule_candidate_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["verified_fact_set_id"],
            ["versioned_verified_fact_sets.verified_fact_set_id"],
            name=op.f("fk_p9b_rule_candidates_verified_fact_set_id_versioned_verified_fact_sets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("rule_candidate_id", name=op.f("pk_p9b_rule_candidates")),
        sa.UniqueConstraint(
            "rule_candidate_id",
            "target_scope",
            "opportunity_id",
            "opportunity_version",
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            name="uq_p9b_rule_candidates_target_binding",
        ),
    )
    op.create_table(
        "verified_fact_set_dependencies",
        sa.Column("dependency_id", sa.Uuid(), nullable=False),
        sa.Column("verified_fact_set_id", sa.Uuid(), nullable=False),
        sa.Column("dependency_type", sa.String(length=32), nullable=False),
        sa.Column("source_bundle_revision_id", sa.Uuid(), nullable=True),
        sa.Column("block_id", sa.Uuid(), nullable=True),
        sa.Column("dependency_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(dependency_type = 'SOURCE_BUNDLE_REVISION' and source_bundle_revision_id is not null and block_id is null) or (dependency_type = 'DOCUMENT_BLOCK' and source_bundle_revision_id is null and block_id is not null)",
            name=op.f("ck_verified_fact_set_dependencies_dependency_shape"),
        ),
        sa.CheckConstraint(
            "dependency_fingerprint ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_verified_fact_set_dependencies_dependency_fingerprint_format"),
        ),
        sa.CheckConstraint(
            "dependency_type in ('SOURCE_BUNDLE_REVISION', 'DOCUMENT_BLOCK')",
            name=op.f("ck_verified_fact_set_dependencies_dependency_type_values"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(dependency_id) = 7",
            name=op.f("ck_verified_fact_set_dependencies_dependency_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["block_id"],
            ["document_blocks.block_id"],
            name=op.f("fk_verified_fact_set_dependencies_block_id_document_blocks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_bundle_revision_id"],
            ["source_bundle_revisions.source_bundle_revision_id"],
            name=op.f(
                "fk_verified_fact_set_dependencies_source_bundle_revision_id_source_bundle_revisions"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["verified_fact_set_id"],
            ["versioned_verified_fact_sets.verified_fact_set_id"],
            name=op.f(
                "fk_verified_fact_set_dependencies_verified_fact_set_id_versioned_verified_fact_sets"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("dependency_id", name=op.f("pk_verified_fact_set_dependencies")),
        sa.UniqueConstraint(
            "verified_fact_set_id",
            "dependency_type",
            "source_bundle_revision_id",
            "block_id",
            name="uq_verified_fact_set_dependencies_identity",
        ),
    )
    op.create_table(
        "verified_fact_set_transitions",
        sa.Column("transition_id", sa.Uuid(), nullable=False),
        sa.Column("verified_fact_set_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=False),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("successor_fact_set_id", sa.Uuid(), nullable=True),
        sa.Column("dependency_id", sa.Uuid(), nullable=True),
        sa.Column("expected_dependency_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("observed_dependency_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("actor_identity", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(to_status = 'STALE' and dependency_id is not null and expected_dependency_fingerprint ~ '^[0-9a-f]{64}$' and observed_dependency_fingerprint ~ '^[0-9a-f]{64}$' and expected_dependency_fingerprint <> observed_dependency_fingerprint) or (to_status <> 'STALE' and dependency_id is null and expected_dependency_fingerprint is null and observed_dependency_fingerprint is null)",
            name=op.f("ck_verified_fact_set_transitions_dependency_invalidation_shape"),
        ),
        sa.CheckConstraint(
            "(to_status = 'SUPERSEDED' and successor_fact_set_id is not null) or (to_status <> 'SUPERSEDED' and successor_fact_set_id is null)",
            name=op.f("ck_verified_fact_set_transitions_successor_shape"),
        ),
        sa.CheckConstraint(
            "from_status = 'ACTIVE'",
            name=op.f("ck_verified_fact_set_transitions_from_status_active"),
        ),
        sa.CheckConstraint(
            "to_status in ('SUPERSEDED', 'STALE', 'WITHDRAWN')",
            name=op.f("ck_verified_fact_set_transitions_to_status_values"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(transition_id) = 7",
            name=op.f("ck_verified_fact_set_transitions_transition_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["dependency_id"],
            ["verified_fact_set_dependencies.dependency_id"],
            name="fk_p9b_fact_transition_dependency",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        sa.ForeignKeyConstraint(
            ["successor_fact_set_id"],
            ["versioned_verified_fact_sets.verified_fact_set_id"],
            name=op.f(
                "fk_verified_fact_set_transitions_successor_fact_set_id_versioned_verified_fact_sets"
            ),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["verified_fact_set_id"],
            ["versioned_verified_fact_sets.verified_fact_set_id"],
            name=op.f(
                "fk_verified_fact_set_transitions_verified_fact_set_id_versioned_verified_fact_sets"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("transition_id", name=op.f("pk_verified_fact_set_transitions")),
        sa.UniqueConstraint(
            "verified_fact_set_id", name="uq_verified_fact_set_transitions_terminal"
        ),
    )
    op.create_table(
        "extraction_candidate_evidence",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("block_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_ref_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["block_id", "evidence_ref_id", "document_id"],
            [
                "document_blocks.block_id",
                "document_blocks.evidence_ref_id",
                "document_blocks.document_id",
            ],
            name=op.f("fk_extraction_candidate_evidence_block_id_document_blocks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id", "extraction_run_id"],
            ["extraction_candidates.candidate_id", "extraction_candidates.extraction_run_id"],
            name=op.f("fk_extraction_candidate_evidence_candidate_id_extraction_candidates"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_run_id", "block_id"],
            [
                "extraction_run_input_blocks.extraction_run_id",
                "extraction_run_input_blocks.block_id",
            ],
            name=op.f(
                "fk_extraction_candidate_evidence_extraction_run_id_extraction_run_input_blocks"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "candidate_id", "block_id", name=op.f("pk_extraction_candidate_evidence")
        ),
        sa.UniqueConstraint(
            "candidate_id",
            "block_id",
            "evidence_ref_id",
            name="uq_extraction_candidate_evidence_fact_binding",
        ),
    )
    op.create_table(
        "fact_verification_decisions",
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("verification_method", sa.String(length=24), nullable=False),
        sa.Column("verifier_identity", sa.Text(), nullable=False),
        sa.Column("verifier_response_id", sa.Text(), nullable=True),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("evidence_support_result", sa.String(length=16), nullable=False),
        sa.Column("precedence_check_result", sa.String(length=16), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision <> 'APPROVE' or (evidence_support_result = 'SUPPORTED' and precedence_check_result = 'PASSED')",
            name=op.f("ck_fact_verification_decisions_approval_support"),
        ),
        sa.CheckConstraint(
            "decision in ('APPROVE', 'REJECT', 'UNKNOWN', 'NEEDS_ADJUDICATION')",
            name=op.f("ck_fact_verification_decisions_decision_values"),
        ),
        sa.CheckConstraint(
            "evidence_support_result in ('SUPPORTED', 'UNSUPPORTED', 'UNKNOWN')",
            name=op.f("ck_fact_verification_decisions_evidence_support_values"),
        ),
        sa.CheckConstraint(
            "precedence_check_result in ('PASSED', 'FAILED', 'UNKNOWN')",
            name=op.f("ck_fact_verification_decisions_precedence_values"),
        ),
        sa.CheckConstraint(
            "verification_method in ('DETERMINISTIC', 'HUMAN', 'APPROVED_MAPPING')",
            name=op.f("ck_fact_verification_decisions_method_values"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(decision_id) = 7",
            name=op.f("ck_fact_verification_decisions_decision_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["extraction_candidates.candidate_id"],
            name=op.f("fk_fact_verification_decisions_candidate_id_extraction_candidates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("decision_id", name=op.f("pk_fact_verification_decisions")),
        sa.UniqueConstraint(
            "decision_id", "candidate_id", name="uq_fact_verification_decisions_candidate_binding"
        ),
    )
    op.create_table(
        "p9b_rule_approval_decisions",
        sa.Column("rule_approval_decision_id", sa.Uuid(), nullable=False),
        sa.Column("rule_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("approver_identity", sa.Text(), nullable=False),
        sa.Column("approval_method", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "approval_method in ('HUMAN', 'DETERMINISTIC_POLICY')",
            name=op.f("ck_p9b_rule_approval_decisions_approval_method_values"),
        ),
        sa.CheckConstraint(
            "decision in ('APPROVE', 'REJECT', 'NEEDS_ADJUDICATION')",
            name=op.f("ck_p9b_rule_approval_decisions_decision_values"),
        ),
        sa.CheckConstraint(
            "uuid_extract_version(rule_approval_decision_id) = 7",
            name=op.f("ck_p9b_rule_approval_decisions_decision_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["rule_candidate_id"],
            ["p9b_rule_candidates.rule_candidate_id"],
            name=op.f("fk_p9b_rule_approval_decisions_rule_candidate_id_p9b_rule_candidates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "rule_approval_decision_id", name=op.f("pk_p9b_rule_approval_decisions")
        ),
        sa.UniqueConstraint(
            "rule_approval_decision_id",
            "rule_candidate_id",
            name="uq_p9b_rule_approval_decisions_candidate_binding",
        ),
    )
    op.create_table(
        "p9b_rule_candidate_evidence",
        sa.Column("rule_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_ref_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["evidence_ref_id"],
            ["evidence_refs.evidence_ref_id"],
            name=op.f("fk_p9b_rule_candidate_evidence_evidence_ref_id_evidence_refs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_candidate_id"],
            ["p9b_rule_candidates.rule_candidate_id"],
            name=op.f("fk_p9b_rule_candidate_evidence_rule_candidate_id_p9b_rule_candidates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "rule_candidate_id", "evidence_ref_id", name=op.f("pk_p9b_rule_candidate_evidence")
        ),
    )
    op.create_table(
        "unit_rule_sets",
        sa.Column("unit_rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("opportunity_unit_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_unit_version_id", sa.Uuid(), nullable=False),
        sa.Column("rule_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("rule_schema_version", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("activation_status", sa.String(length=16), nullable=False),
        sa.Column("rule_approval_decision_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "activation_status = 'DORMANT'",
            name=op.f("ck_unit_rule_sets_activation_status_dormant"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'", name=op.f("ck_unit_rule_sets_payload_object")
        ),
        sa.CheckConstraint(
            "review_status = 'APPROVED'", name=op.f("ck_unit_rule_sets_review_status_approved")
        ),
        sa.CheckConstraint(
            "rule_schema_version = '0.8.0'", name=op.f("ck_unit_rule_sets_schema_version_v08")
        ),
        sa.CheckConstraint(
            "opportunity_version >= 1", name=op.f("ck_unit_rule_sets_positive_opportunity_version")
        ),
        sa.CheckConstraint(
            "uuid_extract_version(unit_rule_set_id) = 7",
            name=op.f("ck_unit_rule_sets_rule_set_id_uuid7"),
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
            name=op.f("fk_unit_rule_sets_opportunity_unit_id_opportunity_unit_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_approval_decision_id", "rule_candidate_id"],
            [
                "p9b_rule_approval_decisions.rule_approval_decision_id",
                "p9b_rule_approval_decisions.rule_candidate_id",
            ],
            name=op.f("fk_unit_rule_sets_rule_approval_decision_id_p9b_rule_approval_decisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_candidate_id"],
            ["p9b_rule_candidates.rule_candidate_id"],
            name=op.f("fk_unit_rule_sets_rule_candidate_id_p9b_rule_candidates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("unit_rule_set_id", name=op.f("pk_unit_rule_sets")),
        sa.UniqueConstraint(
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            "rule_candidate_id",
            name="uq_unit_rule_sets_candidate_target",
        ),
        sa.UniqueConstraint(
            "rule_approval_decision_id", name=op.f("uq_unit_rule_sets_rule_approval_decision_id")
        ),
    )
    op.create_table(
        "verified_facts",
        sa.Column("verified_fact_id", sa.Uuid(), nullable=False),
        sa.Column("verified_fact_set_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("field_name", sa.String(length=128), nullable=False),
        sa.Column("fact_state", sa.String(length=16), nullable=False),
        sa.Column(
            "normalized_value",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "raw_value", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
        sa.Column("verification_decision_id", sa.Uuid(), nullable=False),
        sa.Column("dependency_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(fact_state = 'UNKNOWN' and normalized_value is null) or (fact_state = 'KNOWN' and normalized_value is not null)",
            name=op.f("ck_verified_facts_fact_state_shape"),
        ),
        sa.CheckConstraint(
            "dependency_fingerprint ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_verified_facts_dependency_fingerprint_format"),
        ),
        sa.CheckConstraint(
            "fact_state in ('KNOWN', 'UNKNOWN')", name=op.f("ck_verified_facts_fact_state_values")
        ),
        sa.CheckConstraint(
            "uuid_extract_version(verified_fact_id) = 7",
            name=op.f("ck_verified_facts_fact_id_uuid7"),
        ),
        sa.ForeignKeyConstraint(
            ["verification_decision_id", "candidate_id"],
            ["fact_verification_decisions.decision_id", "fact_verification_decisions.candidate_id"],
            name=op.f("fk_verified_facts_verification_decision_id_fact_verification_decisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["verified_fact_set_id"],
            ["versioned_verified_fact_sets.verified_fact_set_id"],
            name=op.f("fk_verified_facts_verified_fact_set_id_versioned_verified_fact_sets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("verified_fact_id", name=op.f("pk_verified_facts")),
        sa.UniqueConstraint(
            "verified_fact_set_id", "field_name", name="uq_verified_facts_fact_set_field"
        ),
        sa.UniqueConstraint(
            "verified_fact_set_id", "verified_fact_id", name="uq_verified_facts_fact_set_fact"
        ),
    )
    op.create_table(
        "p9b_rule_candidate_facts",
        sa.Column("rule_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("verified_fact_set_id", sa.Uuid(), nullable=False),
        sa.Column("verified_fact_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["rule_candidate_id"],
            ["p9b_rule_candidates.rule_candidate_id"],
            name=op.f("fk_p9b_rule_candidate_facts_rule_candidate_id_p9b_rule_candidates"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["verified_fact_set_id", "verified_fact_id"],
            ["verified_facts.verified_fact_set_id", "verified_facts.verified_fact_id"],
            name=op.f("fk_p9b_rule_candidate_facts_verified_fact_set_id_verified_facts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "rule_candidate_id", "verified_fact_id", name=op.f("pk_p9b_rule_candidate_facts")
        ),
    )
    op.create_table(
        "verified_fact_evidence",
        sa.Column("verified_fact_id", sa.Uuid(), nullable=False),
        sa.Column("verified_fact_set_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("block_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_ref_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id", "block_id", "evidence_ref_id"],
            [
                "extraction_candidate_evidence.candidate_id",
                "extraction_candidate_evidence.block_id",
                "extraction_candidate_evidence.evidence_ref_id",
            ],
            name=op.f("fk_verified_fact_evidence_candidate_id_extraction_candidate_evidence"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["verified_fact_set_id", "verified_fact_id"],
            ["verified_facts.verified_fact_set_id", "verified_facts.verified_fact_id"],
            name=op.f("fk_verified_fact_evidence_verified_fact_set_id_verified_facts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "verified_fact_id", "block_id", name=op.f("pk_verified_fact_evidence")
        ),
        sa.UniqueConstraint(
            "verified_fact_id", "evidence_ref_id", name="uq_verified_fact_evidence_fact_ref"
        ),
    )
    op.create_foreign_key(
        "fk_p9b_fact_transition_dependency",
        "verified_fact_set_transitions",
        "verified_fact_set_dependencies",
        ["dependency_id"],
        ["dependency_id"],
        ondelete="RESTRICT",
    )
    _create_guards()


def downgrade() -> None:
    """Downgrade schema."""
    connection = op.get_bind()
    history_count = connection.execute(
        sa.text(
            "select (select count(*) from extraction_runs) + "
            "(select count(*) from versioned_verified_fact_sets) + "
            "(select count(*) from p9b_rule_candidates) + "
            "(select count(*) from unit_rule_sets)"
        )
    ).scalar_one()
    if history_count:
        raise RuntimeError("cannot downgrade P9-B fact lifecycle migration with history")
    _drop_guards()
    op.drop_constraint(
        "fk_p9b_fact_transition_dependency",
        "verified_fact_set_transitions",
        type_="foreignkey",
    )
    op.drop_table("verified_fact_evidence")
    op.drop_table("p9b_rule_candidate_facts")
    op.drop_table("verified_facts")
    op.drop_table("unit_rule_sets")
    op.drop_table("p9b_rule_candidate_evidence")
    op.drop_table("p9b_rule_approval_decisions")
    op.drop_table("fact_verification_decisions")
    op.drop_table("extraction_candidate_evidence")
    op.drop_table("verified_fact_set_transitions")
    op.drop_table("verified_fact_set_dependencies")
    op.drop_table("p9b_rule_candidates")
    op.drop_table("extraction_run_input_blocks")
    op.drop_table("extraction_candidates")
    op.drop_index(
        "uq_versioned_verified_fact_sets_unit_version",
        table_name="versioned_verified_fact_sets",
        postgresql_where=sa.text("target_scope = 'UNIT'"),
    )
    op.drop_index(
        "uq_versioned_verified_fact_sets_opportunity_version",
        table_name="versioned_verified_fact_sets",
        postgresql_where=sa.text("target_scope = 'OPPORTUNITY'"),
    )
    op.drop_index(
        "uq_versioned_verified_fact_sets_active_unit",
        table_name="versioned_verified_fact_sets",
        postgresql_where=sa.text("target_scope = 'UNIT' and status = 'ACTIVE'"),
    )
    op.drop_index(
        "uq_versioned_verified_fact_sets_active_opportunity",
        table_name="versioned_verified_fact_sets",
        postgresql_where=sa.text("target_scope = 'OPPORTUNITY' and status = 'ACTIVE'"),
    )
    op.drop_table("versioned_verified_fact_sets")
    op.drop_table("extraction_runs")
    op.drop_constraint(
        "uq_source_bundle_revisions_fact_binding", "source_bundle_revisions", type_="unique"
    )
    op.drop_constraint(
        "uq_document_blocks_candidate_evidence_binding", "document_blocks", type_="unique"
    )


def _create_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION p9b_insert_only_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION '% is immutable P9-B history', TG_TABLE_NAME;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    immutable_tables = (
        "extraction_runs",
        "extraction_candidates",
        "extraction_candidate_evidence",
        "fact_verification_decisions",
        "verified_facts",
        "verified_fact_evidence",
        "verified_fact_set_dependencies",
        "p9b_rule_candidates",
        "p9b_rule_candidate_facts",
        "p9b_rule_candidate_evidence",
        "p9b_rule_approval_decisions",
        "unit_rule_sets",
    )
    for table in immutable_tables:
        op.execute(
            f"CREATE TRIGGER {table}_immutable_guard BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION p9b_insert_only_guard()"
        )

    op.execute(
        """
        CREATE FUNCTION p9b_extraction_run_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            revision source_bundle_revisions%ROWTYPE;
        BEGIN
            SELECT * INTO revision FROM source_bundle_revisions
            WHERE source_bundle_revision_id = NEW.source_bundle_revision_id;
            IF NOT FOUND OR revision.status <> 'FROZEN' OR
               revision.opportunity_id <> NEW.opportunity_id OR
               revision.opportunity_version <> NEW.opportunity_version THEN
                RAISE EXCEPTION 'EXTRACTION_REQUIRES_EXACT_FROZEN_BUNDLE';
            END IF;
            IF jsonb_array_length(NEW.ordered_input_block_ids) <>
               (SELECT count(DISTINCT value) FROM
                jsonb_array_elements_text(NEW.ordered_input_block_ids)) THEN
                RAISE EXCEPTION 'EXTRACTION_INPUT_BLOCK_IDS_NOT_UNIQUE';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER extraction_runs_insert_guard BEFORE INSERT ON extraction_runs "
        "FOR EACH ROW EXECUTE FUNCTION p9b_extraction_run_insert_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION p9b_extraction_input_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            run extraction_runs%ROWTYPE;
            block document_blocks%ROWTYPE;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'extraction_run_input_blocks are immutable P9-B history';
            END IF;
            SELECT * INTO run FROM extraction_runs
            WHERE extraction_run_id = NEW.extraction_run_id;
            SELECT * INTO block FROM document_blocks WHERE block_id = NEW.block_id;
            IF NOT FOUND OR run.ordered_input_block_ids->>(NEW.input_ordinal - 1) <>
               NEW.block_id::text OR block.evidence_ref_id <> NEW.evidence_ref_id OR
               block.document_id <> NEW.document_id THEN
                RAISE EXCEPTION 'EXTRACTION_INPUT_BINDING_MISMATCH';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM source_bundle_members
                WHERE source_bundle_revision_id = run.source_bundle_revision_id
                  AND document_id = block.document_id
            ) THEN
                RAISE EXCEPTION 'EXTRACTION_INPUT_OUTSIDE_BUNDLE';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER extraction_run_input_blocks_guard BEFORE INSERT OR UPDATE OR DELETE ON "
        "extraction_run_input_blocks FOR EACH ROW EXECUTE FUNCTION p9b_extraction_input_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION p9b_extraction_run_complete_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (SELECT count(*) FROM extraction_run_input_blocks
                WHERE extraction_run_id = NEW.extraction_run_id) <>
               jsonb_array_length(NEW.ordered_input_block_ids) THEN
                RAISE EXCEPTION 'EXTRACTION_INPUT_SET_INCOMPLETE';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER extraction_runs_complete_guard AFTER INSERT ON extraction_runs "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
        "p9b_extraction_run_complete_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION p9b_candidate_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            run extraction_runs%ROWTYPE;
        BEGIN
            SELECT * INTO run FROM extraction_runs
            WHERE extraction_run_id = NEW.extraction_run_id;
            IF NOT FOUND OR run.target_scope <> NEW.target_scope OR
               run.opportunity_id <> NEW.opportunity_id OR
               run.opportunity_version <> NEW.opportunity_version OR
               run.opportunity_unit_id IS DISTINCT FROM NEW.opportunity_unit_id OR
               run.opportunity_unit_version_id IS DISTINCT FROM NEW.opportunity_unit_version_id THEN
                RAISE EXCEPTION 'CANDIDATE_TARGET_BINDING_MISMATCH';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER extraction_candidates_insert_guard BEFORE INSERT ON "
        "extraction_candidates FOR EACH ROW EXECUTE FUNCTION p9b_candidate_insert_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION p9b_candidate_complete_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM extraction_candidate_evidence
                           WHERE candidate_id = NEW.candidate_id) THEN
                RAISE EXCEPTION 'CANDIDATE_EVIDENCE_REQUIRED';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER extraction_candidates_complete_guard AFTER INSERT ON "
        "extraction_candidates DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
        "p9b_candidate_complete_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION p9b_fact_decision_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            candidate extraction_candidates%ROWTYPE;
            run extraction_runs%ROWTYPE;
        BEGIN
            SELECT * INTO candidate FROM extraction_candidates
            WHERE candidate_id = NEW.candidate_id;
            SELECT * INTO run FROM extraction_runs
            WHERE extraction_run_id = candidate.extraction_run_id;
            IF NOT FOUND OR run.producer_identity = NEW.verifier_identity OR
               (run.producer_response_id IS NOT NULL AND NEW.verifier_response_id IS NOT NULL AND
                run.producer_response_id = NEW.verifier_response_id) THEN
                RAISE EXCEPTION 'FACT_VERIFIER_NOT_INDEPENDENT';
            END IF;
            IF (NEW.decision = 'APPROVE' AND candidate.abstained) OR
               (NEW.decision = 'UNKNOWN' AND NOT candidate.abstained) THEN
                RAISE EXCEPTION 'FACT_DECISION_CANDIDATE_STATE_MISMATCH';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER fact_verification_decisions_insert_guard BEFORE INSERT ON "
        "fact_verification_decisions FOR EACH ROW EXECUTE FUNCTION "
        "p9b_fact_decision_insert_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION p9b_fact_set_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            predecessor versioned_verified_fact_sets%ROWTYPE;
            revision source_bundle_revisions%ROWTYPE;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'versioned_verified_fact_sets cannot be deleted';
            END IF;
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'ACTIVE' THEN
                    RAISE EXCEPTION 'NEW_FACT_SET_MUST_BE_ACTIVE';
                END IF;
                SELECT * INTO revision FROM source_bundle_revisions
                WHERE source_bundle_revision_id = NEW.source_bundle_revision_id;
                IF NOT FOUND OR revision.status <> 'FROZEN' OR
                   revision.relation_graph_version <> NEW.relation_graph_version OR
                   revision.precedence_graph_version <> NEW.precedence_graph_version THEN
                    RAISE EXCEPTION 'FACT_SET_BUNDLE_SNAPSHOT_MISMATCH';
                END IF;
                IF NEW.supersedes_id IS NULL AND NEW.version <> 1 THEN
                    RAISE EXCEPTION 'FIRST_FACT_SET_VERSION_MUST_BE_ONE';
                ELSIF NEW.supersedes_id IS NOT NULL THEN
                    SELECT * INTO predecessor FROM versioned_verified_fact_sets
                    WHERE verified_fact_set_id = NEW.supersedes_id;
                    IF NOT FOUND OR predecessor.status <> 'SUPERSEDED' OR
                       predecessor.version + 1 <> NEW.version OR
                       predecessor.target_scope <> NEW.target_scope OR
                       predecessor.opportunity_id <> NEW.opportunity_id OR
                       predecessor.opportunity_version <> NEW.opportunity_version OR
                       predecessor.opportunity_unit_id IS DISTINCT FROM NEW.opportunity_unit_id OR
                       predecessor.opportunity_unit_version_id IS DISTINCT FROM
                           NEW.opportunity_unit_version_id THEN
                        RAISE EXCEPTION 'FACT_SET_SUPERSESSION_BINDING_MISMATCH';
                    END IF;
                END IF;
                RETURN NEW;
            END IF;
            IF (to_jsonb(OLD) - ARRAY['status', 'updated_at']) <>
               (to_jsonb(NEW) - ARRAY['status', 'updated_at']) OR
               OLD.status <> 'ACTIVE' OR NEW.status NOT IN ('SUPERSEDED', 'STALE', 'WITHDRAWN') OR
               NOT EXISTS (
                   SELECT 1 FROM verified_fact_set_transitions
                   WHERE verified_fact_set_id = OLD.verified_fact_set_id
                     AND from_status = OLD.status AND to_status = NEW.status
                     AND created_at = NEW.updated_at
               ) THEN
                RAISE EXCEPTION 'FACT_SET_STATUS_TRANSITION_NOT_AUDITED';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER versioned_verified_fact_sets_guard BEFORE INSERT OR UPDATE OR DELETE ON "
        "versioned_verified_fact_sets FOR EACH ROW EXECUTE FUNCTION p9b_fact_set_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION p9b_fact_transition_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            fact_set versioned_verified_fact_sets%ROWTYPE;
            dependency verified_fact_set_dependencies%ROWTYPE;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'verified_fact_set_transitions are immutable P9-B history';
            END IF;
            SELECT * INTO fact_set FROM versioned_verified_fact_sets
            WHERE verified_fact_set_id = NEW.verified_fact_set_id;
            IF NOT FOUND OR fact_set.status <> 'ACTIVE' THEN
                RAISE EXCEPTION 'FACT_SET_TRANSITION_REQUIRES_ACTIVE_SOURCE';
            END IF;
            IF NEW.to_status = 'STALE' THEN
                SELECT * INTO dependency FROM verified_fact_set_dependencies
                WHERE dependency_id = NEW.dependency_id;
                IF NOT FOUND OR dependency.verified_fact_set_id <> NEW.verified_fact_set_id OR
                   dependency.dependency_fingerprint <> NEW.expected_dependency_fingerprint THEN
                    RAISE EXCEPTION 'FACT_SET_INVALIDATION_DEPENDENCY_MISMATCH';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER verified_fact_set_transitions_guard BEFORE INSERT OR UPDATE OR DELETE ON "
        "verified_fact_set_transitions FOR EACH ROW EXECUTE FUNCTION "
        "p9b_fact_transition_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION p9b_verified_fact_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            fact_set versioned_verified_fact_sets%ROWTYPE;
            candidate extraction_candidates%ROWTYPE;
            decision fact_verification_decisions%ROWTYPE;
            run extraction_runs%ROWTYPE;
        BEGIN
            SELECT * INTO fact_set FROM versioned_verified_fact_sets
            WHERE verified_fact_set_id = NEW.verified_fact_set_id;
            SELECT * INTO candidate FROM extraction_candidates WHERE candidate_id = NEW.candidate_id;
            SELECT * INTO decision FROM fact_verification_decisions
            WHERE decision_id = NEW.verification_decision_id AND candidate_id = NEW.candidate_id;
            SELECT * INTO run FROM extraction_runs
            WHERE extraction_run_id = candidate.extraction_run_id;
            IF NOT FOUND OR fact_set.status <> 'ACTIVE' OR
               fact_set.source_bundle_revision_id <> run.source_bundle_revision_id OR
               fact_set.target_scope <> run.target_scope OR fact_set.opportunity_id <> run.opportunity_id OR
               fact_set.opportunity_version <> run.opportunity_version OR
               fact_set.opportunity_unit_id IS DISTINCT FROM run.opportunity_unit_id OR
               fact_set.opportunity_unit_version_id IS DISTINCT FROM run.opportunity_unit_version_id OR
               NEW.field_name <> candidate.field_name OR
               (NEW.fact_state = 'KNOWN' AND (candidate.abstained OR decision.decision <> 'APPROVE')) OR
               (NEW.fact_state = 'UNKNOWN' AND (NOT candidate.abstained OR decision.decision <> 'UNKNOWN')) THEN
                RAISE EXCEPTION 'VERIFIED_FACT_PROMOTION_BINDING_MISMATCH';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER verified_facts_insert_guard BEFORE INSERT ON verified_facts "
        "FOR EACH ROW EXECUTE FUNCTION p9b_verified_fact_insert_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION p9b_fact_dependency_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            expected_hash text;
            expected_revision uuid;
        BEGIN
            SELECT source_bundle_revision_id INTO expected_revision
            FROM versioned_verified_fact_sets
            WHERE verified_fact_set_id = NEW.verified_fact_set_id;
            IF NEW.dependency_type = 'SOURCE_BUNDLE_REVISION' THEN
                SELECT canonical_bundle_hash INTO expected_hash FROM source_bundle_revisions
                WHERE source_bundle_revision_id = NEW.source_bundle_revision_id;
                IF NEW.source_bundle_revision_id <> expected_revision THEN
                    RAISE EXCEPTION 'FACT_DEPENDENCY_BUNDLE_MISMATCH';
                END IF;
            ELSE
                SELECT evidence_binding_hash INTO expected_hash FROM document_blocks
                WHERE block_id = NEW.block_id;
            END IF;
            IF expected_hash IS NULL OR expected_hash <> NEW.dependency_fingerprint THEN
                RAISE EXCEPTION 'FACT_DEPENDENCY_FINGERPRINT_MISMATCH';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER verified_fact_set_dependencies_insert_guard BEFORE INSERT ON "
        "verified_fact_set_dependencies FOR EACH ROW EXECUTE FUNCTION "
        "p9b_fact_dependency_insert_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION p9b_fact_set_complete_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM verified_facts
                           WHERE verified_fact_set_id = NEW.verified_fact_set_id) OR
               NOT EXISTS (SELECT 1 FROM verified_fact_set_dependencies
                           WHERE verified_fact_set_id = NEW.verified_fact_set_id
                             AND dependency_type = 'SOURCE_BUNDLE_REVISION') OR
               EXISTS (
                   SELECT 1 FROM verified_fact_evidence evidence
                   WHERE evidence.verified_fact_set_id = NEW.verified_fact_set_id
                     AND NOT EXISTS (
                         SELECT 1 FROM verified_fact_set_dependencies dependency
                         WHERE dependency.verified_fact_set_id = NEW.verified_fact_set_id
                           AND dependency.dependency_type = 'DOCUMENT_BLOCK'
                           AND dependency.block_id = evidence.block_id
                     )
               ) THEN
                RAISE EXCEPTION 'VERIFIED_FACT_SET_INCOMPLETE';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER versioned_verified_fact_sets_complete_guard AFTER INSERT ON "
        "versioned_verified_fact_sets DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
        "p9b_fact_set_complete_guard()"
    )

    op.execute(
        """
        CREATE FUNCTION p9b_rule_candidate_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            fact_set versioned_verified_fact_sets%ROWTYPE;
        BEGIN
            SELECT * INTO fact_set FROM versioned_verified_fact_sets
            WHERE verified_fact_set_id = NEW.verified_fact_set_id;
            IF NOT FOUND OR fact_set.status <> 'ACTIVE' OR fact_set.target_scope <> NEW.target_scope OR
               fact_set.opportunity_id <> NEW.opportunity_id OR
               fact_set.opportunity_version <> NEW.opportunity_version OR
               fact_set.opportunity_unit_id IS DISTINCT FROM NEW.opportunity_unit_id OR
               fact_set.opportunity_unit_version_id IS DISTINCT FROM
                   NEW.opportunity_unit_version_id THEN
                RAISE EXCEPTION 'RULE_CANDIDATE_FACT_SET_BINDING_MISMATCH';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER p9b_rule_candidates_insert_guard BEFORE INSERT ON p9b_rule_candidates "
        "FOR EACH ROW EXECUTE FUNCTION p9b_rule_candidate_insert_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION p9b_rule_candidate_complete_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM p9b_rule_candidate_facts
                           WHERE rule_candidate_id = NEW.rule_candidate_id) OR
               NOT EXISTS (SELECT 1 FROM p9b_rule_candidate_evidence
                           WHERE rule_candidate_id = NEW.rule_candidate_id) OR
               EXISTS (
                   SELECT 1 FROM p9b_rule_candidate_facts linked
                   WHERE linked.rule_candidate_id = NEW.rule_candidate_id
                     AND linked.verified_fact_set_id <> NEW.verified_fact_set_id
               ) OR EXISTS (
                   SELECT 1 FROM p9b_rule_candidate_evidence candidate_evidence
                   WHERE candidate_evidence.rule_candidate_id = NEW.rule_candidate_id
                     AND NOT EXISTS (
                         SELECT 1 FROM p9b_rule_candidate_facts candidate_fact
                         JOIN verified_fact_evidence fact_evidence
                           ON fact_evidence.verified_fact_set_id =
                              candidate_fact.verified_fact_set_id
                          AND fact_evidence.verified_fact_id = candidate_fact.verified_fact_id
                         WHERE candidate_fact.rule_candidate_id = NEW.rule_candidate_id
                           AND fact_evidence.evidence_ref_id =
                               candidate_evidence.evidence_ref_id
                     )
               ) THEN
                RAISE EXCEPTION 'RULE_CANDIDATE_BINDINGS_INCOMPLETE';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER p9b_rule_candidates_complete_guard AFTER INSERT ON "
        "p9b_rule_candidates DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "
        "p9b_rule_candidate_complete_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION p9b_rule_approval_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            candidate p9b_rule_candidates%ROWTYPE;
        BEGIN
            SELECT * INTO candidate FROM p9b_rule_candidates
            WHERE rule_candidate_id = NEW.rule_candidate_id;
            IF NOT FOUND OR candidate.producer_identity = NEW.approver_identity THEN
                RAISE EXCEPTION 'RULE_APPROVER_NOT_INDEPENDENT';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER p9b_rule_approval_decisions_insert_guard BEFORE INSERT ON "
        "p9b_rule_approval_decisions FOR EACH ROW EXECUTE FUNCTION "
        "p9b_rule_approval_insert_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION p9b_unit_rule_set_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            candidate p9b_rule_candidates%ROWTYPE;
            decision p9b_rule_approval_decisions%ROWTYPE;
        BEGIN
            SELECT * INTO candidate FROM p9b_rule_candidates
            WHERE rule_candidate_id = NEW.rule_candidate_id;
            SELECT * INTO decision FROM p9b_rule_approval_decisions
            WHERE rule_approval_decision_id = NEW.rule_approval_decision_id
              AND rule_candidate_id = NEW.rule_candidate_id;
            IF NOT FOUND OR candidate.target_scope <> 'UNIT' OR decision.decision <> 'APPROVE' OR
               candidate.opportunity_id <> NEW.opportunity_id OR
               candidate.opportunity_version <> NEW.opportunity_version OR
               candidate.opportunity_unit_id <> NEW.opportunity_unit_id OR
               candidate.opportunity_unit_version_id <> NEW.opportunity_unit_version_id OR
               candidate.proposed_rule_payload <> NEW.payload THEN
                RAISE EXCEPTION 'UNIT_RULE_SET_APPROVAL_BINDING_MISMATCH';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER unit_rule_sets_insert_guard BEFORE INSERT ON unit_rule_sets "
        "FOR EACH ROW EXECUTE FUNCTION p9b_unit_rule_set_insert_guard()"
    )


def _drop_guards() -> None:
    for table in (
        "extraction_runs",
        "extraction_candidates",
        "extraction_candidate_evidence",
        "fact_verification_decisions",
        "verified_facts",
        "verified_fact_evidence",
        "verified_fact_set_dependencies",
        "p9b_rule_candidates",
        "p9b_rule_candidate_facts",
        "p9b_rule_candidate_evidence",
        "p9b_rule_approval_decisions",
        "unit_rule_sets",
    ):
        op.execute(f"DROP TRIGGER {table}_immutable_guard ON {table}")
    for trigger, table in (
        ("extraction_runs_insert_guard", "extraction_runs"),
        ("extraction_run_input_blocks_guard", "extraction_run_input_blocks"),
        ("extraction_runs_complete_guard", "extraction_runs"),
        ("extraction_candidates_insert_guard", "extraction_candidates"),
        ("extraction_candidates_complete_guard", "extraction_candidates"),
        ("fact_verification_decisions_insert_guard", "fact_verification_decisions"),
        ("versioned_verified_fact_sets_guard", "versioned_verified_fact_sets"),
        ("verified_fact_set_transitions_guard", "verified_fact_set_transitions"),
        ("verified_facts_insert_guard", "verified_facts"),
        ("verified_fact_set_dependencies_insert_guard", "verified_fact_set_dependencies"),
        ("versioned_verified_fact_sets_complete_guard", "versioned_verified_fact_sets"),
        ("p9b_rule_candidates_insert_guard", "p9b_rule_candidates"),
        ("p9b_rule_candidates_complete_guard", "p9b_rule_candidates"),
        ("p9b_rule_approval_decisions_insert_guard", "p9b_rule_approval_decisions"),
        ("unit_rule_sets_insert_guard", "unit_rule_sets"),
    ):
        op.execute(f"DROP TRIGGER {trigger} ON {table}")
    for function in (
        "p9b_unit_rule_set_insert_guard",
        "p9b_rule_approval_insert_guard",
        "p9b_rule_candidate_complete_guard",
        "p9b_rule_candidate_insert_guard",
        "p9b_fact_set_complete_guard",
        "p9b_fact_dependency_insert_guard",
        "p9b_verified_fact_insert_guard",
        "p9b_fact_transition_guard",
        "p9b_fact_set_guard",
        "p9b_fact_decision_insert_guard",
        "p9b_candidate_complete_guard",
        "p9b_candidate_insert_guard",
        "p9b_extraction_run_complete_guard",
        "p9b_extraction_input_guard",
        "p9b_extraction_run_insert_guard",
        "p9b_insert_only_guard",
    ):
        op.execute(f"DROP FUNCTION {function}()")
