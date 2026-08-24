"""p9b_identity_provenance

Revision ID: 20260824_0011
Revises: 20260823_0010
Create Date: 2026-08-24 18:00:00.000000
"""

import json
from collections.abc import Sequence
from hashlib import sha256

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260824_0011"
down_revision: str | None = "20260823_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_PARSE_CONTRACT_VERSION = "phase2-locator-contract-v0.2.0"
HASH_CONTRACT_VERSION = "p9b-canonical-json-sha256-v1"
P9B_TABLES = (
    "dataset_manifest_entries",
    "dataset_manifests",
    "opportunity_unit_lineage_evidence",
    "opportunity_unit_lineage_members",
    "opportunity_unit_lineage_events",
    "opportunity_unit_aliases",
    "opportunity_unit_versions",
    "opportunity_units",
    "source_bundle_member_relations",
    "source_bundle_members",
    "source_bundle_revisions",
    "source_bundles",
)


def _document_parse_key(
    *,
    artifact_id: object,
    artifact_sha256: str,
    parser_name: str,
    parser_version: str,
    parse_contract_version: str,
) -> str:
    payload = {
        "artifact_id": str(artifact_id),
        "artifact_sha256": artifact_sha256,
        "parse_contract_version": parse_contract_version,
        "parser_name": parser_name,
        "parser_version": parser_version,
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    domain = f"deepaha:p9b:document_parse_key:{HASH_CONTRACT_VERSION}\0".encode()
    return sha256(domain + serialized).hexdigest()


def _add_parse_identity() -> None:
    op.add_column(
        "documents",
        sa.Column("parse_contract_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("document_parse_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "parse_attempts",
        sa.Column("parse_contract_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "parse_attempts",
        sa.Column("document_parse_key", sa.String(length=64), nullable=True),
    )

    connection = op.get_bind()
    document_rows = connection.execute(
        sa.text(
            "select d.document_id, d.artifact_id, a.content_sha256, d.parser_name, "
            "d.parser_version from documents d join raw_artifacts a "
            "on a.artifact_id = d.artifact_id"
        )
    ).mappings()
    for row in document_rows:
        parse_key = _document_parse_key(
            artifact_id=row["artifact_id"],
            artifact_sha256=row["content_sha256"],
            parser_name=row["parser_name"],
            parser_version=row["parser_version"],
            parse_contract_version=LEGACY_PARSE_CONTRACT_VERSION,
        )
        connection.execute(
            sa.text(
                "update documents set parse_contract_version=:contract, "
                "document_parse_key=:parse_key where document_id=:document_id"
            ),
            {
                "contract": LEGACY_PARSE_CONTRACT_VERSION,
                "parse_key": parse_key,
                "document_id": row["document_id"],
            },
        )

    attempt_rows = connection.execute(
        sa.text(
            "select p.parse_attempt_id, p.artifact_id, a.content_sha256, p.parser_name, "
            "p.parser_version from parse_attempts p join raw_artifacts a "
            "on a.artifact_id = p.artifact_id"
        )
    ).mappings()
    for row in attempt_rows:
        parse_key = _document_parse_key(
            artifact_id=row["artifact_id"],
            artifact_sha256=row["content_sha256"],
            parser_name=row["parser_name"],
            parser_version=row["parser_version"],
            parse_contract_version=LEGACY_PARSE_CONTRACT_VERSION,
        )
        connection.execute(
            sa.text(
                "update parse_attempts set parse_contract_version=:contract, "
                "document_parse_key=:parse_key where parse_attempt_id=:attempt_id"
            ),
            {
                "contract": LEGACY_PARSE_CONTRACT_VERSION,
                "parse_key": parse_key,
                "attempt_id": row["parse_attempt_id"],
            },
        )

    op.alter_column("documents", "parse_contract_version", nullable=False)
    op.alter_column("documents", "document_parse_key", nullable=False)
    op.alter_column("parse_attempts", "parse_contract_version", nullable=False)
    op.alter_column("parse_attempts", "document_parse_key", nullable=False)
    op.create_check_constraint(
        "document_parse_key_format",
        "documents",
        "document_parse_key ~ '^[0-9a-f]{64}$'",
    )
    op.create_check_constraint(
        "document_parse_key_format",
        "parse_attempts",
        "document_parse_key ~ '^[0-9a-f]{64}$'",
    )
    op.drop_constraint("uq_documents_artifact_id", "documents", type_="unique")
    op.create_unique_constraint(
        "uq_documents_parse_identity",
        "documents",
        ["artifact_id", "parser_name", "parser_version", "parse_contract_version"],
    )
    op.drop_constraint("uq_parse_attempts_artifact_id", "parse_attempts", type_="unique")
    op.create_unique_constraint(
        "uq_parse_attempts_parse_identity",
        "parse_attempts",
        ["artifact_id", "parser_name", "parser_version", "parse_contract_version"],
    )
    op.create_unique_constraint(
        "uq_documents_p9b_parse_binding",
        "documents",
        [
            "document_id",
            "artifact_id",
            "document_parse_key",
            "parser_name",
            "parser_version",
            "parse_contract_version",
        ],
    )


def _add_provenance_supporting_constraints() -> None:
    op.create_unique_constraint(
        "uq_raw_artifacts_p9b_provenance_binding",
        "raw_artifacts",
        [
            "artifact_id",
            "source_id",
            "content_sha256",
            "byte_size",
            "storage_bucket",
            "object_key",
        ],
    )
    op.create_unique_constraint(
        "uq_capture_observations_p9b_provenance_binding",
        "capture_observations",
        [
            "observation_id",
            "endpoint_id",
            "source_id",
            "artifact_id",
            "policy_version",
            "collector_name",
            "collector_version",
        ],
    )
    op.create_unique_constraint(
        "uq_acquisition_evaluations_p9b_provenance_binding",
        "acquisition_evaluations",
        [
            "acquisition_evaluation_id",
            "observation_id",
            "endpoint_id",
            "source_id",
            "artifact_id",
            "strategy_used",
            "validation_status",
            "validator_name",
            "validator_version",
        ],
    )
    op.create_unique_constraint(
        "uq_acquisition_runs_p9b_provenance_binding",
        "acquisition_runs",
        [
            "acquisition_run_id",
            "recipe_id",
            "source_id",
            "endpoint_id",
            "endpoint_policy_version",
            "recipe_version",
        ],
    )


def _create_bundle_tables() -> None:
    op.create_table(
        "source_bundles",
        sa.Column("source_bundle_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "uuid_extract_version(source_bundle_id) = 7",
            name=op.f("ck_source_bundles_source_bundle_id_uuid7"),
        ),
        sa.CheckConstraint(
            "retired_at is null or retired_at >= created_at",
            name=op.f("ck_source_bundles_timestamp_order"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.opportunity_id"],
            name=op.f("fk_source_bundles_opportunity_id_opportunities"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("source_bundle_id", name=op.f("pk_source_bundles")),
        sa.UniqueConstraint(
            "source_bundle_id",
            "opportunity_id",
            name="uq_source_bundles_bundle_opportunity",
        ),
    )
    op.create_table(
        "source_bundle_revisions",
        sa.Column("source_bundle_revision_id", sa.Uuid(), nullable=False),
        sa.Column("source_bundle_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("canonical_bundle_hash", sa.String(length=64), nullable=False),
        sa.Column("relation_graph_version", sa.String(length=64), nullable=False),
        sa.Column("precedence_graph_version", sa.String(length=64), nullable=False),
        sa.Column("effective_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "uuid_extract_version(source_bundle_revision_id) = 7",
            name=op.f("ck_source_bundle_revisions_revision_id_uuid7"),
        ),
        sa.CheckConstraint(
            "revision_number >= 1",
            name=op.f("ck_source_bundle_revisions_positive_revision"),
        ),
        sa.CheckConstraint(
            "opportunity_version >= 1",
            name=op.f("ck_source_bundle_revisions_positive_opportunity_version"),
        ),
        sa.CheckConstraint(
            "canonical_bundle_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_source_bundle_revisions_hash_format"),
        ),
        sa.CheckConstraint(
            "status in ('DRAFT', 'FROZEN', 'INVALIDATED')",
            name=op.f("ck_source_bundle_revisions_status_values"),
        ),
        sa.CheckConstraint(
            "(status = 'DRAFT' and frozen_at is null) or "
            "(status in ('FROZEN', 'INVALIDATED') and frozen_at is not null)",
            name=op.f("ck_source_bundle_revisions_freeze_state"),
        ),
        sa.ForeignKeyConstraint(
            ["source_bundle_id", "opportunity_id"],
            ["source_bundles.source_bundle_id", "source_bundles.opportunity_id"],
            name=op.f("fk_source_bundle_revisions_source_bundle_id_source_bundles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            name=op.f("fk_source_bundle_revisions_opportunity_id_opportunity_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "source_bundle_revision_id",
            name=op.f("pk_source_bundle_revisions"),
        ),
        sa.UniqueConstraint(
            "source_bundle_id",
            "revision_number",
            name="uq_source_bundle_revisions_bundle_revision",
        ),
        sa.UniqueConstraint(
            "source_bundle_revision_id",
            "source_bundle_id",
            "opportunity_id",
            "opportunity_version",
            name="uq_source_bundle_revisions_p9b_binding",
        ),
        sa.UniqueConstraint(
            "source_bundle_revision_id",
            "source_bundle_id",
            "opportunity_id",
            "opportunity_version",
            "canonical_bundle_hash",
            name="uq_source_bundle_revisions_dataset_binding",
        ),
    )
    op.create_table(
        "source_bundle_members",
        sa.Column("source_bundle_member_id", sa.Uuid(), nullable=False),
        sa.Column("source_bundle_revision_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), nullable=False),
        sa.Column("capture_observation_id", sa.Uuid(), nullable=False),
        sa.Column("acquisition_evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("acquisition_validation_status", sa.String(length=32), nullable=False),
        sa.Column("acquisition_run_id", sa.Uuid(), nullable=False),
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("recipe_version", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("fetch_strategy", sa.String(length=32), nullable=False),
        sa.Column("fetcher_name", sa.String(length=128), nullable=False),
        sa.Column("fetcher_version", sa.String(length=64), nullable=False),
        sa.Column("validator_name", sa.String(length=128), nullable=False),
        sa.Column("validator_version", sa.String(length=64), nullable=False),
        sa.Column("raw_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("raw_artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("raw_artifact_size", sa.Integer(), nullable=False),
        sa.Column("storage_bucket", sa.String(length=63), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_parse_key", sa.String(length=64), nullable=False),
        sa.Column("parser_name", sa.String(length=128), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("parse_contract_version", sa.String(length=64), nullable=False),
        sa.Column("member_role", sa.String(length=32), nullable=False),
        sa.Column("precedence", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("member_provenance_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(source_bundle_member_id) = 7",
            name=op.f("ck_source_bundle_members_member_id_uuid7"),
        ),
        sa.CheckConstraint(
            "acquisition_validation_status = 'VALID'",
            name=op.f("ck_source_bundle_members_valid_only"),
        ),
        sa.CheckConstraint(
            "raw_artifact_sha256 ~ '^[0-9a-f]{64}$' and "
            "document_parse_key ~ '^[0-9a-f]{64}$' and "
            "member_provenance_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_source_bundle_members_hash_formats"),
        ),
        sa.CheckConstraint(
            "raw_artifact_size > 0 and precedence between 0 and 1000",
            name=op.f("ck_source_bundle_members_numeric_ranges"),
        ),
        sa.CheckConstraint(
            "member_role in ('PRIMARY_NOTICE', 'ATTACHMENT', 'CORRECTION', 'SUPPLEMENT', "
            "'FAQ', 'CANCELLATION', 'RESULT_NOTICE')",
            name=op.f("ck_source_bundle_members_role_values"),
        ),
        sa.CheckConstraint(
            "effective_to is null or "
            "(effective_from is not null and effective_to > effective_from)",
            name=op.f("ck_source_bundle_members_effective_window"),
        ),
        sa.CheckConstraint(
            "object_key = 'raw/sha256/' || substring(raw_artifact_sha256 from 1 for 2) || "
            "'/' || raw_artifact_sha256",
            name=op.f("ck_source_bundle_members_content_addressed_object_key"),
        ),
        sa.ForeignKeyConstraint(
            ["source_bundle_revision_id"],
            ["source_bundle_revisions.source_bundle_revision_id"],
            name=op.f("fk_source_bundle_members_source_bundle_revision_id_source_bundle_revisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "capture_observation_id",
                "endpoint_id",
                "source_id",
                "raw_artifact_id",
                "policy_version",
                "fetcher_name",
                "fetcher_version",
            ],
            [
                "capture_observations.observation_id",
                "capture_observations.endpoint_id",
                "capture_observations.source_id",
                "capture_observations.artifact_id",
                "capture_observations.policy_version",
                "capture_observations.collector_name",
                "capture_observations.collector_version",
            ],
            name=op.f("fk_source_bundle_members_capture_observation_id_capture_observations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "acquisition_evaluation_id",
                "capture_observation_id",
                "endpoint_id",
                "source_id",
                "raw_artifact_id",
                "fetch_strategy",
                "acquisition_validation_status",
                "validator_name",
                "validator_version",
            ],
            [
                "acquisition_evaluations.acquisition_evaluation_id",
                "acquisition_evaluations.observation_id",
                "acquisition_evaluations.endpoint_id",
                "acquisition_evaluations.source_id",
                "acquisition_evaluations.artifact_id",
                "acquisition_evaluations.strategy_used",
                "acquisition_evaluations.validation_status",
                "acquisition_evaluations.validator_name",
                "acquisition_evaluations.validator_version",
            ],
            name=op.f("fk_source_bundle_members_acquisition_evaluation_id_acquisition_evaluations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "acquisition_run_id",
                "recipe_id",
                "source_id",
                "endpoint_id",
                "policy_version",
                "recipe_version",
            ],
            [
                "acquisition_runs.acquisition_run_id",
                "acquisition_runs.recipe_id",
                "acquisition_runs.source_id",
                "acquisition_runs.endpoint_id",
                "acquisition_runs.endpoint_policy_version",
                "acquisition_runs.recipe_version",
            ],
            name=op.f("fk_source_bundle_members_acquisition_run_id_acquisition_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "raw_artifact_id",
                "source_id",
                "raw_artifact_sha256",
                "raw_artifact_size",
                "storage_bucket",
                "object_key",
            ],
            [
                "raw_artifacts.artifact_id",
                "raw_artifacts.source_id",
                "raw_artifacts.content_sha256",
                "raw_artifacts.byte_size",
                "raw_artifacts.storage_bucket",
                "raw_artifacts.object_key",
            ],
            name=op.f("fk_source_bundle_members_raw_artifact_id_raw_artifacts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "document_id",
                "raw_artifact_id",
                "document_parse_key",
                "parser_name",
                "parser_version",
                "parse_contract_version",
            ],
            [
                "documents.document_id",
                "documents.artifact_id",
                "documents.document_parse_key",
                "documents.parser_name",
                "documents.parser_version",
                "documents.parse_contract_version",
            ],
            name=op.f("fk_source_bundle_members_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("source_bundle_member_id", name=op.f("pk_source_bundle_members")),
        sa.UniqueConstraint(
            "source_bundle_revision_id",
            "source_bundle_member_id",
            name="uq_source_bundle_members_revision_member",
        ),
        sa.UniqueConstraint(
            "source_bundle_revision_id",
            "document_id",
            "document_parse_key",
            "member_role",
            name="uq_source_bundle_members_revision_document_role",
        ),
    )
    op.create_table(
        "source_bundle_member_relations",
        sa.Column("source_bundle_revision_id", sa.Uuid(), nullable=False),
        sa.Column("source_member_id", sa.Uuid(), nullable=False),
        sa.Column("target_member_id", sa.Uuid(), nullable=False),
        sa.Column("relation_type", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_member_id <> target_member_id",
            name=op.f("ck_source_bundle_member_relations_distinct_members"),
        ),
        sa.CheckConstraint(
            "relation_type in ('ATTACHES_TO', 'AMENDS', 'SUPERSEDES', 'CANCELS', 'CLARIFIES')",
            name=op.f("ck_source_bundle_member_relations_type_values"),
        ),
        sa.ForeignKeyConstraint(
            ["source_bundle_revision_id", "source_member_id"],
            [
                "source_bundle_members.source_bundle_revision_id",
                "source_bundle_members.source_bundle_member_id",
            ],
            name=op.f("fk_source_bundle_member_relations_source_member_id_source_bundle_members"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_bundle_revision_id", "target_member_id"],
            [
                "source_bundle_members.source_bundle_revision_id",
                "source_bundle_members.source_bundle_member_id",
            ],
            name=op.f("fk_source_bundle_member_relations_target_member_id_source_bundle_members"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "source_bundle_revision_id",
            "source_member_id",
            "target_member_id",
            "relation_type",
            name=op.f("pk_source_bundle_member_relations"),
        ),
    )


def _create_unit_tables() -> None:
    op.create_table(
        "opportunity_units",
        sa.Column("opportunity_unit_id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.String(length=37), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("current_unit_key", sa.Text(), nullable=False),
        sa.Column("normalized_current_unit_key", sa.Text(), nullable=False),
        sa.Column("unit_kind", sa.String(length=32), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=24), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "uuid_extract_version(opportunity_unit_id) = 7",
            name=op.f("ck_opportunity_units_unit_id_uuid7"),
        ),
        sa.CheckConstraint(
            "public_id ~ '^unit_[0-9a-f]{32}$'",
            name=op.f("ck_opportunity_units_public_id_format"),
        ),
        sa.CheckConstraint(
            "opportunity_version >= 1",
            name=op.f("ck_opportunity_units_positive_opportunity_version"),
        ),
        sa.CheckConstraint(
            "unit_kind in ('POSITION', 'TRACK', 'PROGRAM_TIER', 'REGION_VARIANT', "
            "'DEFAULT_SINGLETON')",
            name=op.f("ck_opportunity_units_kind_values"),
        ),
        sa.CheckConstraint(
            "lifecycle_status in ('ACTIVE', 'RETIRED', 'IDENTITY_COLLISION')",
            name=op.f("ck_opportunity_units_lifecycle_values"),
        ),
        sa.CheckConstraint(
            "(lifecycle_status = 'RETIRED') = (retired_at is not null)",
            name=op.f("ck_opportunity_units_retired_state"),
        ),
        sa.CheckConstraint(
            "length(btrim(current_unit_key)) >= 1 and "
            "length(btrim(normalized_current_unit_key)) >= 1",
            name=op.f("ck_opportunity_units_key_nonempty"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            name=op.f("fk_opportunity_units_opportunity_id_opportunity_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("opportunity_unit_id", name=op.f("pk_opportunity_units")),
        sa.UniqueConstraint("public_id", name=op.f("uq_opportunity_units_public_id")),
        sa.UniqueConstraint(
            "opportunity_unit_id",
            "opportunity_id",
            name="uq_opportunity_units_unit_opportunity",
        ),
        sa.UniqueConstraint(
            "current_version_id",
            name="uq_opportunity_units_current_version_id",
        ),
    )
    op.create_index(
        "uq_opportunity_units_active_key",
        "opportunity_units",
        ["opportunity_id", "normalized_current_unit_key"],
        unique=True,
        postgresql_where=sa.text("retired_at is null"),
    )
    op.create_table(
        "opportunity_unit_versions",
        sa.Column("opportunity_unit_version_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_unit_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_bundle_revision_id", sa.Uuid(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("canonical_label", sa.Text(), nullable=False),
        sa.Column("identity_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("supersedes_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(opportunity_unit_version_id) = 7",
            name=op.f("ck_opportunity_unit_versions_version_id_uuid7"),
        ),
        sa.CheckConstraint(
            "version >= 1 and opportunity_version >= 1",
            name=op.f("ck_opportunity_unit_versions_positive_versions"),
        ),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'SUPERSEDED', 'SUPERSEDED_BY_SEGMENTATION', 'MERGED', "
            "'CANCELLED', 'WITHDRAWN')",
            name=op.f("ck_opportunity_unit_versions_status_values"),
        ),
        sa.CheckConstraint(
            "effective_to is null or effective_to > effective_from",
            name=op.f("ck_opportunity_unit_versions_effective_window"),
        ),
        sa.CheckConstraint(
            "identity_fingerprint ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_opportunity_unit_versions_fingerprint_format"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_unit_id", "opportunity_id"],
            ["opportunity_units.opportunity_unit_id", "opportunity_units.opportunity_id"],
            name=op.f("fk_opportunity_unit_versions_opportunity_unit_id_opportunity_units"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            name=op.f("fk_opportunity_unit_versions_opportunity_id_opportunity_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_bundle_revision_id"],
            ["source_bundle_revisions.source_bundle_revision_id"],
            name=op.f(
                "fk_opportunity_unit_versions_source_bundle_revision_id_source_bundle_revisions"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "opportunity_unit_version_id",
            name=op.f("pk_opportunity_unit_versions"),
        ),
        sa.UniqueConstraint(
            "opportunity_unit_id",
            "version",
            name="uq_opportunity_unit_versions_unit_version",
        ),
        sa.UniqueConstraint(
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            name="uq_opportunity_unit_versions_unit_version_id",
        ),
        sa.UniqueConstraint(
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            "opportunity_id",
            name="uq_opportunity_unit_versions_member_binding",
        ),
        sa.UniqueConstraint(
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            "opportunity_id",
            "opportunity_version",
            name="uq_opportunity_unit_versions_dataset_binding",
        ),
        sa.UniqueConstraint(
            "opportunity_unit_id",
            "identity_fingerprint",
            "source_bundle_revision_id",
            name="uq_opportunity_unit_versions_idempotency",
        ),
    )
    op.create_foreign_key(
        "fk_opportunity_unit_versions_supersedes",
        "opportunity_unit_versions",
        "opportunity_unit_versions",
        ["opportunity_unit_id", "supersedes_version_id"],
        ["opportunity_unit_id", "opportunity_unit_version_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_opportunity_units_current_version",
        "opportunity_units",
        "opportunity_unit_versions",
        ["opportunity_unit_id", "current_version_id"],
        ["opportunity_unit_id", "opportunity_unit_version_id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_table(
        "opportunity_unit_aliases",
        sa.Column("alias_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_unit_id", sa.Uuid(), nullable=False),
        sa.Column("normalized_alias_key", sa.Text(), nullable=False),
        sa.Column("display_alias_key", sa.Text(), nullable=False),
        sa.Column("alias_kind", sa.String(length=24), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_ref_id", sa.Uuid(), nullable=False),
        sa.Column("source_bundle_revision_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(alias_id) = 7",
            name=op.f("ck_opportunity_unit_aliases_alias_id_uuid7"),
        ),
        sa.CheckConstraint(
            "alias_kind in ('CURRENT', 'HISTORICAL', 'OFFICIAL_CODE', 'CANONICAL_DERIVED')",
            name=op.f("ck_opportunity_unit_aliases_kind_values"),
        ),
        sa.CheckConstraint(
            "valid_to is null or valid_to > valid_from",
            name=op.f("ck_opportunity_unit_aliases_effective_window"),
        ),
        sa.CheckConstraint(
            "length(btrim(normalized_alias_key)) >= 1 and length(btrim(display_alias_key)) >= 1",
            name=op.f("ck_opportunity_unit_aliases_key_nonempty"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_unit_id", "opportunity_id"],
            ["opportunity_units.opportunity_unit_id", "opportunity_units.opportunity_id"],
            name=op.f("fk_opportunity_unit_aliases_opportunity_unit_id_opportunity_units"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_ref_id"],
            ["evidence_refs.evidence_ref_id"],
            name=op.f("fk_opportunity_unit_aliases_evidence_ref_id_evidence_refs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_bundle_revision_id"],
            ["source_bundle_revisions.source_bundle_revision_id"],
            name=op.f(
                "fk_opportunity_unit_aliases_source_bundle_revision_id_source_bundle_revisions"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("alias_id", name=op.f("pk_opportunity_unit_aliases")),
    )
    op.create_table(
        "opportunity_unit_lineage_events",
        sa.Column("lineage_event_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("reverses_event_id", sa.Uuid(), nullable=True),
        sa.Column("source_bundle_revision_id", sa.Uuid(), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("actor_identity", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(lineage_event_id) = 7",
            name=op.f("ck_opportunity_unit_lineage_events_event_id_uuid7"),
        ),
        sa.CheckConstraint(
            "event_type in ('REKEY', 'SPLIT', 'MERGE', 'REVERSAL', 'CANCEL', 'REACTIVATE')",
            name=op.f("ck_opportunity_unit_lineage_events_type_values"),
        ),
        sa.CheckConstraint(
            "(event_type = 'REVERSAL') = (reverses_event_id is not null)",
            name=op.f("ck_opportunity_unit_lineage_events_reversal_shape"),
        ),
        sa.CheckConstraint(
            "length(btrim(reason_code)) >= 1 and length(btrim(actor_identity)) >= 1",
            name=op.f("ck_opportunity_unit_lineage_events_text_nonempty"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.opportunity_id"],
            name=op.f("fk_opportunity_unit_lineage_events_opportunity_id_opportunities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reverses_event_id"],
            ["opportunity_unit_lineage_events.lineage_event_id"],
            name=op.f(
                "fk_opportunity_unit_lineage_events_reverses_event_id_opportunity_unit_lineage_events"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_bundle_revision_id"],
            ["source_bundle_revisions.source_bundle_revision_id"],
            name=op.f(
                "fk_opportunity_unit_lineage_events_source_bundle_revision_id_source_bundle_revisions"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "lineage_event_id", name=op.f("pk_opportunity_unit_lineage_events")
        ),
        sa.UniqueConstraint(
            "lineage_event_id",
            "opportunity_id",
            name="uq_opportunity_unit_lineage_events_event_opportunity",
        ),
        sa.UniqueConstraint(
            "reverses_event_id",
            name="uq_opportunity_unit_lineage_events_reversal",
        ),
    )
    op.create_table(
        "opportunity_unit_lineage_members",
        sa.Column("lineage_event_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("member_role", sa.String(length=16), nullable=False),
        sa.Column("opportunity_unit_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_unit_version_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "member_role in ('SOURCE', 'TARGET')",
            name=op.f("ck_opportunity_unit_lineage_members_role_values"),
        ),
        sa.ForeignKeyConstraint(
            ["lineage_event_id", "opportunity_id"],
            [
                "opportunity_unit_lineage_events.lineage_event_id",
                "opportunity_unit_lineage_events.opportunity_id",
            ],
            name=op.f(
                "fk_opportunity_unit_lineage_members_lineage_event_id_opportunity_unit_lineage_events"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_unit_id", "opportunity_unit_version_id", "opportunity_id"],
            [
                "opportunity_unit_versions.opportunity_unit_id",
                "opportunity_unit_versions.opportunity_unit_version_id",
                "opportunity_unit_versions.opportunity_id",
            ],
            name=op.f(
                "fk_opportunity_unit_lineage_members_opportunity_unit_id_opportunity_unit_versions"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "lineage_event_id",
            "member_role",
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            name=op.f("pk_opportunity_unit_lineage_members"),
        ),
    )
    op.create_table(
        "opportunity_unit_lineage_evidence",
        sa.Column("lineage_event_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_ref_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["lineage_event_id"],
            ["opportunity_unit_lineage_events.lineage_event_id"],
            name=op.f(
                "fk_opportunity_unit_lineage_evidence_lineage_event_id_opportunity_unit_lineage_events"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_ref_id"],
            ["evidence_refs.evidence_ref_id"],
            name=op.f("fk_opportunity_unit_lineage_evidence_evidence_ref_id_evidence_refs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "lineage_event_id",
            "evidence_ref_id",
            name=op.f("pk_opportunity_unit_lineage_evidence"),
        ),
    )


def _create_dataset_tables() -> None:
    op.create_table(
        "dataset_manifests",
        sa.Column("dataset_manifest_id", sa.Uuid(), nullable=False),
        sa.Column("split_manifest_version", sa.String(length=64), nullable=False),
        sa.Column("partition", sa.String(length=32), nullable=False),
        sa.Column("expected_entry_count", sa.Integer(), nullable=False),
        sa.Column("actual_entry_count", sa.Integer(), nullable=False),
        sa.Column("atomic_group_count", sa.Integer(), nullable=False),
        sa.Column("evaluation_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answer_access_class", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("frozen_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidation_reason", sa.Text(), nullable=True),
        sa.Column("successor_manifest_hash", sa.String(length=64), nullable=True),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(dataset_manifest_id) = 7",
            name=op.f("ck_dataset_manifests_manifest_id_uuid7"),
        ),
        sa.CheckConstraint(
            "partition in ('CALIBRATION', 'DEVELOPMENT', 'VALIDATION', 'LOCKED_ACCEPTANCE')",
            name=op.f("ck_dataset_manifests_partition_values"),
        ),
        sa.CheckConstraint(
            "(partition = 'CALIBRATION' and expected_entry_count = 30 and "
            "answer_access_class = 'ASSISTED_CALIBRATION') or "
            "(partition = 'DEVELOPMENT' and expected_entry_count = 70 and "
            "answer_access_class = 'DEVELOPMENT_VISIBLE') or "
            "(partition = 'VALIDATION' and expected_entry_count = 30 and "
            "answer_access_class = 'VALIDATION_BLIND') or "
            "(partition = 'LOCKED_ACCEPTANCE' and expected_entry_count = 200 and "
            "answer_access_class = 'LOCKED_BLIND')",
            name=op.f("ck_dataset_manifests_partition_contract"),
        ),
        sa.CheckConstraint(
            "actual_entry_count >= 0 and atomic_group_count >= 0 and "
            "atomic_group_count <= actual_entry_count",
            name=op.f("ck_dataset_manifests_count_ranges"),
        ),
        sa.CheckConstraint(
            "status in ('DRAFT', 'FROZEN', 'INVALIDATED')",
            name=op.f("ck_dataset_manifests_status_values"),
        ),
        sa.CheckConstraint(
            "(status = 'DRAFT' and frozen_at is null) or "
            "(status in ('FROZEN', 'INVALIDATED') and frozen_at is not null)",
            name=op.f("ck_dataset_manifests_freeze_state"),
        ),
        sa.CheckConstraint(
            "(invalidated_at is null and invalidation_reason is null) or "
            "(status = 'INVALIDATED' and invalidated_at is not null and "
            "length(btrim(invalidation_reason)) >= 1)",
            name=op.f("ck_dataset_manifests_invalidation_state"),
        ),
        sa.CheckConstraint(
            "manifest_hash ~ '^[0-9a-f]{64}$' and "
            "(successor_manifest_hash is null or "
            "successor_manifest_hash ~ '^[0-9a-f]{64}$')",
            name=op.f("ck_dataset_manifests_hash_formats"),
        ),
        sa.PrimaryKeyConstraint("dataset_manifest_id", name=op.f("pk_dataset_manifests")),
        sa.UniqueConstraint("manifest_hash", name=op.f("uq_dataset_manifests_manifest_hash")),
        sa.UniqueConstraint(
            "dataset_manifest_id",
            "partition",
            "answer_access_class",
            name="uq_dataset_manifests_entry_binding",
        ),
    )
    op.create_table(
        "dataset_manifest_entries",
        sa.Column("dataset_manifest_id", sa.Uuid(), nullable=False),
        sa.Column("entry_id", sa.String(length=128), nullable=False),
        sa.Column("partition", sa.String(length=32), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("opportunity_unit_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_unit_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_bundle_id", sa.Uuid(), nullable=False),
        sa.Column("source_bundle_revision_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_bundle_hash", sa.String(length=64), nullable=False),
        sa.Column("atomic_group_id", sa.String(length=128), nullable=False),
        sa.Column("near_duplicate_cluster_ids", postgresql.JSONB(), nullable=False),
        sa.Column("unit_lineage_ids", postgresql.JSONB(), nullable=False),
        sa.Column("evaluation_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answer_access_class", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "opportunity_version >= 1",
            name=op.f("ck_dataset_manifest_entries_positive_opportunity_version"),
        ),
        sa.CheckConstraint(
            "canonical_bundle_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_dataset_manifest_entries_hash_format"),
        ),
        sa.CheckConstraint(
            "length(btrim(entry_id)) >= 1 and length(btrim(atomic_group_id)) >= 1",
            name=op.f("ck_dataset_manifest_entries_text_nonempty"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(near_duplicate_cluster_ids) = 'array' and "
            "jsonb_typeof(unit_lineage_ids) = 'array'",
            name=op.f("ck_dataset_manifest_entries_lineage_arrays"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_manifest_id", "partition", "answer_access_class"],
            [
                "dataset_manifests.dataset_manifest_id",
                "dataset_manifests.partition",
                "dataset_manifests.answer_access_class",
            ],
            name=op.f("fk_dataset_manifest_entries_dataset_manifest_id_dataset_manifests"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            name=op.f("fk_dataset_manifest_entries_opportunity_id_opportunity_versions"),
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
            name=op.f("fk_dataset_manifest_entries_opportunity_unit_id_opportunity_unit_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "source_bundle_revision_id",
                "source_bundle_id",
                "opportunity_id",
                "opportunity_version",
                "canonical_bundle_hash",
            ],
            [
                "source_bundle_revisions.source_bundle_revision_id",
                "source_bundle_revisions.source_bundle_id",
                "source_bundle_revisions.opportunity_id",
                "source_bundle_revisions.opportunity_version",
                "source_bundle_revisions.canonical_bundle_hash",
            ],
            name=op.f(
                "fk_dataset_manifest_entries_source_bundle_revision_id_source_bundle_revisions"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "dataset_manifest_id",
            "entry_id",
            name=op.f("pk_dataset_manifest_entries"),
        ),
    )
    op.create_index(
        "ix_dataset_manifest_entries_atomic_group_id",
        "dataset_manifest_entries",
        ["atomic_group_id"],
    )


def _create_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION p9b_reject_immutable_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'P9-B immutable history cannot be changed';
        END;
        $$
        """
    )
    for table_name in (
        "source_bundle_members",
        "source_bundle_member_relations",
        "opportunity_unit_versions",
        "opportunity_unit_aliases",
        "opportunity_unit_lineage_events",
        "opportunity_unit_lineage_members",
        "opportunity_unit_lineage_evidence",
        "dataset_manifest_entries",
    ):
        op.execute(
            f"CREATE TRIGGER {table_name}_reject_mutation BEFORE UPDATE OR DELETE ON "
            f"{table_name} FOR EACH ROW EXECUTE FUNCTION p9b_reject_immutable_mutation()"
        )
    op.execute(
        """
        CREATE FUNCTION p9b_require_draft_bundle_revision()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM source_bundle_revisions
                WHERE source_bundle_revision_id = NEW.source_bundle_revision_id
                  AND status = 'DRAFT'
            ) THEN
                RAISE EXCEPTION 'SourceBundle member graph can only be added to a DRAFT revision';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for table_name in ("source_bundle_members", "source_bundle_member_relations"):
        op.execute(
            f"CREATE TRIGGER {table_name}_require_draft BEFORE INSERT ON {table_name} "
            "FOR EACH ROW EXECUTE FUNCTION p9b_require_draft_bundle_revision()"
        )
    op.execute(
        """
        CREATE FUNCTION p9b_guard_bundle_revision_update()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'SourceBundleRevision history cannot be deleted';
            END IF;
            IF OLD.source_bundle_revision_id <> NEW.source_bundle_revision_id
               OR OLD.source_bundle_id <> NEW.source_bundle_id
               OR OLD.opportunity_id <> NEW.opportunity_id
               OR OLD.opportunity_version <> NEW.opportunity_version
               OR OLD.revision_number <> NEW.revision_number
               OR (
                    OLD.canonical_bundle_hash <> NEW.canonical_bundle_hash
                    AND NOT (OLD.status = 'DRAFT' AND NEW.status = 'FROZEN')
               )
               OR OLD.relation_graph_version <> NEW.relation_graph_version
               OR OLD.precedence_graph_version <> NEW.precedence_graph_version
               OR OLD.effective_as_of <> NEW.effective_as_of
               OR OLD.created_at <> NEW.created_at
               OR NOT (
                    (OLD.status = 'DRAFT' AND NEW.status = 'FROZEN' AND NEW.frozen_at IS NOT NULL)
                    OR (OLD.status = 'FROZEN' AND NEW.status = 'INVALIDATED'
                        AND NEW.frozen_at = OLD.frozen_at)
               )
            THEN
                RAISE EXCEPTION 'SourceBundleRevision immutable fields or transition rejected';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER source_bundle_revisions_guard_update BEFORE UPDATE OR DELETE ON "
        "source_bundle_revisions FOR EACH ROW EXECUTE FUNCTION "
        "p9b_guard_bundle_revision_update()"
    )
    op.execute(
        """
        CREATE FUNCTION p9b_reject_alias_overlap()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM opportunity_unit_aliases existing
                WHERE existing.opportunity_id = NEW.opportunity_id
                  AND existing.normalized_alias_key = NEW.normalized_alias_key
                  AND existing.opportunity_unit_id <> NEW.opportunity_unit_id
                  AND tstzrange(existing.valid_from, existing.valid_to, '[)')
                      && tstzrange(NEW.valid_from, NEW.valid_to, '[)')
            ) THEN
                RAISE EXCEPTION 'IDENTITY_COLLISION';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER opportunity_unit_aliases_reject_overlap BEFORE INSERT ON "
        "opportunity_unit_aliases FOR EACH ROW EXECUTE FUNCTION p9b_reject_alias_overlap()"
    )
    op.execute(
        """
        CREATE FUNCTION p9b_guard_dataset_entry_insert()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM dataset_manifests
                WHERE dataset_manifest_id = NEW.dataset_manifest_id AND status = 'DRAFT'
            ) THEN
                RAISE EXCEPTION 'Dataset entries can only be added to a DRAFT manifest';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM source_bundle_revisions
                WHERE source_bundle_revision_id = NEW.source_bundle_revision_id
                  AND status = 'FROZEN'
                  AND canonical_bundle_hash = NEW.canonical_bundle_hash
            ) THEN
                RAISE EXCEPTION 'Dataset entry requires a matching FROZEN SourceBundleRevision';
            END IF;
            IF EXISTS (
                SELECT 1 FROM dataset_manifest_entries existing
                WHERE existing.partition <> NEW.partition AND (
                    existing.source_bundle_id = NEW.source_bundle_id OR
                    existing.source_bundle_revision_id = NEW.source_bundle_revision_id OR
                    existing.atomic_group_id = NEW.atomic_group_id OR
                    (
                        existing.opportunity_id = NEW.opportunity_id AND
                        existing.opportunity_version = NEW.opportunity_version AND
                        existing.opportunity_unit_id = NEW.opportunity_unit_id AND
                        existing.opportunity_unit_version_id = NEW.opportunity_unit_version_id
                    ) OR
                    existing.near_duplicate_cluster_ids ?| ARRAY(
                        SELECT jsonb_array_elements_text(NEW.near_duplicate_cluster_ids)
                    ) OR
                    existing.unit_lineage_ids ?| ARRAY(
                        SELECT jsonb_array_elements_text(NEW.unit_lineage_ids)
                    )
                )
            ) THEN
                RAISE EXCEPTION 'DATASET_PARTITION_LEAKAGE';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER dataset_manifest_entries_guard_insert BEFORE INSERT ON "
        "dataset_manifest_entries FOR EACH ROW EXECUTE FUNCTION "
        "p9b_guard_dataset_entry_insert()"
    )
    op.execute(
        """
        CREATE FUNCTION p9b_guard_dataset_manifest_update()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            persisted_count integer;
            persisted_groups integer;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'DatasetManifest history cannot be deleted';
            END IF;
            IF OLD.dataset_manifest_id <> NEW.dataset_manifest_id
               OR OLD.split_manifest_version <> NEW.split_manifest_version
               OR OLD.partition <> NEW.partition
               OR OLD.expected_entry_count <> NEW.expected_entry_count
               OR OLD.evaluation_cutoff <> NEW.evaluation_cutoff
               OR OLD.answer_access_class <> NEW.answer_access_class
               OR OLD.frozen_by <> NEW.frozen_by
               OR OLD.created_at <> NEW.created_at
               OR (
                    OLD.manifest_hash <> NEW.manifest_hash
                    AND NOT (OLD.status = 'DRAFT' AND NEW.status = 'FROZEN')
               )
            THEN
                RAISE EXCEPTION 'DatasetManifest immutable fields rejected';
            END IF;
            IF OLD.status = 'DRAFT' AND NEW.status = 'FROZEN' THEN
                SELECT count(*), count(DISTINCT atomic_group_id)
                  INTO persisted_count, persisted_groups
                  FROM dataset_manifest_entries
                 WHERE dataset_manifest_id = OLD.dataset_manifest_id;
                IF persisted_count <> NEW.expected_entry_count
                   OR NEW.actual_entry_count <> persisted_count
                   OR NEW.atomic_group_count <> persisted_groups
                   OR NEW.frozen_at IS NULL
                   OR NEW.invalidated_at IS NOT NULL
                   OR NEW.invalidation_reason IS NOT NULL
                THEN
                    RAISE EXCEPTION 'DatasetManifest exact freeze gate rejected';
                END IF;
            ELSIF OLD.status = 'FROZEN' AND NEW.status = 'INVALIDATED' THEN
                IF NEW.frozen_at <> OLD.frozen_at
                   OR NEW.actual_entry_count <> OLD.actual_entry_count
                   OR NEW.atomic_group_count <> OLD.atomic_group_count
                   OR NEW.invalidated_at IS NULL
                   OR length(btrim(NEW.invalidation_reason)) < 1
                THEN
                    RAISE EXCEPTION 'DatasetManifest invalidation transition rejected';
                END IF;
            ELSE
                RAISE EXCEPTION 'DatasetManifest transition rejected';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER dataset_manifests_guard_update BEFORE UPDATE OR DELETE ON "
        "dataset_manifests FOR EACH ROW EXECUTE FUNCTION "
        "p9b_guard_dataset_manifest_update()"
    )


def upgrade() -> None:
    """Add P9-B identity and member-level provenance without changing legacy reads."""
    _add_parse_identity()
    _add_provenance_supporting_constraints()
    _create_bundle_tables()
    _create_unit_tables()
    _create_dataset_tables()
    _create_guards()


def downgrade() -> None:
    """Refuse to discard P9-B identity/provenance or new parse-contract history."""
    connection = op.get_bind()
    populated = [
        table_name
        for table_name in P9B_TABLES
        if connection.execute(
            sa.text(f'SELECT EXISTS (SELECT 1 FROM "{table_name}" LIMIT 1)')
        ).scalar_one()
    ]
    nonlegacy_parse = connection.execute(
        sa.text(
            "select exists(select 1 from documents where parse_contract_version <> :legacy) "
            "or exists(select 1 from parse_attempts where parse_contract_version <> :legacy)"
        ),
        {"legacy": LEGACY_PARSE_CONTRACT_VERSION},
    ).scalar_one()
    if populated or nonlegacy_parse:
        details = ", ".join(populated) or "non-legacy parse identity"
        raise RuntimeError(f"cannot downgrade P9-B0 while history exists: {details}")

    op.execute("DROP TRIGGER dataset_manifests_guard_update ON dataset_manifests")
    op.execute("DROP FUNCTION p9b_guard_dataset_manifest_update()")
    op.execute("DROP TRIGGER dataset_manifest_entries_guard_insert ON dataset_manifest_entries")
    op.execute("DROP FUNCTION p9b_guard_dataset_entry_insert()")
    op.execute("DROP TRIGGER opportunity_unit_aliases_reject_overlap ON opportunity_unit_aliases")
    op.execute("DROP FUNCTION p9b_reject_alias_overlap()")
    op.execute("DROP TRIGGER source_bundle_revisions_guard_update ON source_bundle_revisions")
    op.execute("DROP FUNCTION p9b_guard_bundle_revision_update()")
    for table_name in ("source_bundle_member_relations", "source_bundle_members"):
        op.execute(f"DROP TRIGGER {table_name}_require_draft ON {table_name}")
    op.execute("DROP FUNCTION p9b_require_draft_bundle_revision()")
    for table_name in (
        "opportunity_unit_lineage_evidence",
        "opportunity_unit_lineage_members",
        "opportunity_unit_lineage_events",
        "opportunity_unit_aliases",
        "opportunity_unit_versions",
        "source_bundle_member_relations",
        "source_bundle_members",
        "dataset_manifest_entries",
    ):
        op.execute(f"DROP TRIGGER {table_name}_reject_mutation ON {table_name}")
    op.execute("DROP FUNCTION p9b_reject_immutable_mutation()")

    op.drop_index(
        "ix_dataset_manifest_entries_atomic_group_id",
        table_name="dataset_manifest_entries",
    )
    op.drop_table("dataset_manifest_entries")
    op.drop_table("dataset_manifests")
    op.drop_table("opportunity_unit_lineage_evidence")
    op.drop_table("opportunity_unit_lineage_members")
    op.drop_table("opportunity_unit_lineage_events")
    op.drop_table("opportunity_unit_aliases")
    op.drop_constraint(
        "fk_opportunity_units_current_version", "opportunity_units", type_="foreignkey"
    )
    op.drop_table("opportunity_unit_versions")
    op.drop_index("uq_opportunity_units_active_key", table_name="opportunity_units")
    op.drop_table("opportunity_units")
    op.drop_table("source_bundle_member_relations")
    op.drop_table("source_bundle_members")
    op.drop_table("source_bundle_revisions")
    op.drop_table("source_bundles")

    op.drop_constraint(
        "uq_acquisition_runs_p9b_provenance_binding",
        "acquisition_runs",
        type_="unique",
    )
    op.drop_constraint(
        "uq_acquisition_evaluations_p9b_provenance_binding",
        "acquisition_evaluations",
        type_="unique",
    )
    op.drop_constraint(
        "uq_capture_observations_p9b_provenance_binding",
        "capture_observations",
        type_="unique",
    )
    op.drop_constraint("uq_raw_artifacts_p9b_provenance_binding", "raw_artifacts", type_="unique")
    op.drop_constraint("uq_documents_p9b_parse_binding", "documents", type_="unique")
    op.drop_constraint("uq_documents_parse_identity", "documents", type_="unique")
    op.create_unique_constraint(
        "uq_documents_artifact_id",
        "documents",
        ["artifact_id", "parser_name", "parser_version"],
    )
    op.drop_constraint("uq_parse_attempts_parse_identity", "parse_attempts", type_="unique")
    op.create_unique_constraint(
        "uq_parse_attempts_artifact_id",
        "parse_attempts",
        ["artifact_id", "parser_name", "parser_version"],
    )
    op.drop_constraint("document_parse_key_format", "documents", type_="check")
    op.drop_constraint("document_parse_key_format", "parse_attempts", type_="check")
    op.drop_column("parse_attempts", "document_parse_key")
    op.drop_column("parse_attempts", "parse_contract_version")
    op.drop_column("documents", "document_parse_key")
    op.drop_column("documents", "parse_contract_version")
