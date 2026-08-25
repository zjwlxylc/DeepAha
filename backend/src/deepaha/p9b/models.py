from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class SourceBundle(Base):
    __tablename__ = "source_bundles"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(source_bundle_id) = 7",
            name="source_bundle_id_uuid7",
        ),
        CheckConstraint(
            "retired_at is null or retired_at >= created_at",
            name="timestamp_order",
        ),
        UniqueConstraint(
            "source_bundle_id",
            "opportunity_id",
            name="uq_source_bundles_bundle_opportunity",
        ),
    )

    source_bundle_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    opportunity_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("opportunities.opportunity_id", ondelete="RESTRICT"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceBundleRevision(Base):
    __tablename__ = "source_bundle_revisions"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(source_bundle_revision_id) = 7",
            name="revision_id_uuid7",
        ),
        CheckConstraint("revision_number >= 1", name="positive_revision"),
        CheckConstraint(
            "opportunity_version >= 1",
            name="positive_opportunity_version",
        ),
        CheckConstraint(
            "canonical_bundle_hash ~ '^[0-9a-f]{64}$'",
            name="hash_format",
        ),
        CheckConstraint(
            "status in ('DRAFT', 'FROZEN', 'INVALIDATED')",
            name="status_values",
        ),
        CheckConstraint(
            "(status = 'DRAFT' and frozen_at is null) or "
            "(status in ('FROZEN', 'INVALIDATED') and frozen_at is not null)",
            name="freeze_state",
        ),
        ForeignKeyConstraint(
            ["source_bundle_id", "opportunity_id"],
            ["source_bundles.source_bundle_id", "source_bundles.opportunity_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "source_bundle_id",
            "revision_number",
            name="uq_source_bundle_revisions_bundle_revision",
        ),
        UniqueConstraint(
            "source_bundle_revision_id",
            "source_bundle_id",
            "opportunity_id",
            "opportunity_version",
            name="uq_source_bundle_revisions_p9b_binding",
        ),
        UniqueConstraint(
            "source_bundle_revision_id",
            "source_bundle_id",
            "opportunity_id",
            "opportunity_version",
            "canonical_bundle_hash",
            name="uq_source_bundle_revisions_dataset_binding",
        ),
        UniqueConstraint(
            "source_bundle_revision_id",
            "opportunity_id",
            "opportunity_version",
            name="uq_source_bundle_revisions_fact_binding",
        ),
    )

    source_bundle_revision_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_bundle_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    revision_number: Mapped[int] = mapped_column(Integer)
    canonical_bundle_hash: Mapped[str] = mapped_column(String(64))
    relation_graph_version: Mapped[str] = mapped_column(String(64))
    precedence_graph_version: Mapped[str] = mapped_column(String(64))
    effective_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceBundleMember(Base):
    __tablename__ = "source_bundle_members"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(source_bundle_member_id) = 7",
            name="member_id_uuid7",
        ),
        CheckConstraint(
            "acquisition_validation_status = 'VALID'",
            name="valid_only",
        ),
        CheckConstraint(
            "raw_artifact_sha256 ~ '^[0-9a-f]{64}$' and "
            "document_parse_key ~ '^[0-9a-f]{64}$' and "
            "member_provenance_hash ~ '^[0-9a-f]{64}$'",
            name="hash_formats",
        ),
        CheckConstraint(
            "raw_artifact_size > 0 and precedence between 0 and 1000",
            name="numeric_ranges",
        ),
        CheckConstraint(
            "member_role in ('PRIMARY_NOTICE', 'ATTACHMENT', 'CORRECTION', "
            "'SUPPLEMENT', 'FAQ', 'CANCELLATION', 'RESULT_NOTICE')",
            name="role_values",
        ),
        CheckConstraint(
            "effective_to is null or "
            "(effective_from is not null and effective_to > effective_from)",
            name="effective_window",
        ),
        CheckConstraint(
            "object_key = 'raw/sha256/' || "
            "substring(raw_artifact_sha256 from 1 for 2) || '/' || raw_artifact_sha256",
            name="content_addressed_object_key",
        ),
        ForeignKeyConstraint(
            ["source_bundle_revision_id"],
            ["source_bundle_revisions.source_bundle_revision_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
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
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
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
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
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
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
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
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
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
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "source_bundle_revision_id",
            "source_bundle_member_id",
            name="uq_source_bundle_members_revision_member",
        ),
        UniqueConstraint(
            "source_bundle_revision_id",
            "document_id",
            "document_parse_key",
            "member_role",
            name="uq_source_bundle_members_revision_document_role",
        ),
    )

    source_bundle_member_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_bundle_revision_id: Mapped[UUID] = mapped_column(Uuid)
    source_id: Mapped[UUID] = mapped_column(Uuid)
    endpoint_id: Mapped[UUID] = mapped_column(Uuid)
    capture_observation_id: Mapped[UUID] = mapped_column(Uuid)
    acquisition_evaluation_id: Mapped[UUID] = mapped_column(Uuid)
    acquisition_validation_status: Mapped[str] = mapped_column(String(32))
    acquisition_run_id: Mapped[UUID] = mapped_column(Uuid)
    recipe_id: Mapped[UUID] = mapped_column(Uuid)
    recipe_version: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(64))
    fetch_strategy: Mapped[str] = mapped_column(String(32))
    fetcher_name: Mapped[str] = mapped_column(String(128))
    fetcher_version: Mapped[str] = mapped_column(String(64))
    validator_name: Mapped[str] = mapped_column(String(128))
    validator_version: Mapped[str] = mapped_column(String(64))
    raw_artifact_id: Mapped[UUID] = mapped_column(Uuid)
    raw_artifact_sha256: Mapped[str] = mapped_column(String(64))
    raw_artifact_size: Mapped[int] = mapped_column(Integer)
    storage_bucket: Mapped[str] = mapped_column(String(63))
    object_key: Mapped[str] = mapped_column(Text)
    document_id: Mapped[UUID] = mapped_column(Uuid)
    document_parse_key: Mapped[str] = mapped_column(String(64))
    parser_name: Mapped[str] = mapped_column(String(128))
    parser_version: Mapped[str] = mapped_column(String(64))
    parse_contract_version: Mapped[str] = mapped_column(String(64))
    member_role: Mapped[str] = mapped_column(String(32))
    precedence: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    member_provenance_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceBundleMemberRelation(Base):
    __tablename__ = "source_bundle_member_relations"
    __table_args__ = (
        CheckConstraint("source_member_id <> target_member_id", name="distinct_members"),
        CheckConstraint(
            "relation_type in ('ATTACHES_TO', 'AMENDS', 'SUPERSEDES', 'CANCELS', 'CLARIFIES')",
            name="type_values",
        ),
        ForeignKeyConstraint(
            ["source_bundle_revision_id", "source_member_id"],
            [
                "source_bundle_members.source_bundle_revision_id",
                "source_bundle_members.source_bundle_member_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_bundle_revision_id", "target_member_id"],
            [
                "source_bundle_members.source_bundle_revision_id",
                "source_bundle_members.source_bundle_member_id",
            ],
            ondelete="RESTRICT",
        ),
        PrimaryKeyConstraint(
            "source_bundle_revision_id",
            "source_member_id",
            "target_member_id",
            "relation_type",
        ),
    )

    source_bundle_revision_id: Mapped[UUID] = mapped_column(Uuid)
    source_member_id: Mapped[UUID] = mapped_column(Uuid)
    target_member_id: Mapped[UUID] = mapped_column(Uuid)
    relation_type: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OpportunityUnit(Base):
    __tablename__ = "opportunity_units"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(opportunity_unit_id) = 7",
            name="unit_id_uuid7",
        ),
        CheckConstraint("public_id ~ '^unit_[0-9a-f]{32}$'", name="public_id_format"),
        CheckConstraint(
            "opportunity_version >= 1",
            name="positive_opportunity_version",
        ),
        CheckConstraint(
            "unit_kind in ('POSITION', 'TRACK', 'PROGRAM_TIER', 'REGION_VARIANT', "
            "'DEFAULT_SINGLETON')",
            name="kind_values",
        ),
        CheckConstraint(
            "lifecycle_status in ('ACTIVE', 'RETIRED', 'IDENTITY_COLLISION')",
            name="lifecycle_values",
        ),
        CheckConstraint(
            "(lifecycle_status = 'RETIRED') = (retired_at is not null)",
            name="retired_state",
        ),
        CheckConstraint(
            "length(btrim(current_unit_key)) >= 1 and "
            "length(btrim(normalized_current_unit_key)) >= 1",
            name="key_nonempty",
        ),
        ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "opportunity_unit_id",
                "current_version_id",
                "opportunity_id",
                "opportunity_version",
            ],
            [
                "opportunity_unit_versions.opportunity_unit_id",
                "opportunity_unit_versions.opportunity_unit_version_id",
                "opportunity_unit_versions.opportunity_id",
                "opportunity_unit_versions.opportunity_version",
            ],
            name="fk_opportunity_units_current_version",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        UniqueConstraint("public_id"),
        UniqueConstraint(
            "opportunity_unit_id",
            "opportunity_id",
            name="uq_opportunity_units_unit_opportunity",
        ),
        UniqueConstraint(
            "current_version_id",
            name="uq_opportunity_units_current_version_id",
        ),
        Index(
            "uq_opportunity_units_active_key",
            "opportunity_id",
            "normalized_current_unit_key",
            unique=True,
            postgresql_where=text("retired_at is null"),
        ),
    )

    opportunity_unit_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(37))
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    current_unit_key: Mapped[str] = mapped_column(Text)
    normalized_current_unit_key: Mapped[str] = mapped_column(Text)
    unit_kind: Mapped[str] = mapped_column(String(32))
    lifecycle_status: Mapped[str] = mapped_column(String(24))
    current_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OpportunityUnitVersion(Base):
    __tablename__ = "opportunity_unit_versions"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(opportunity_unit_version_id) = 7",
            name="version_id_uuid7",
        ),
        CheckConstraint(
            "version >= 1 and opportunity_version >= 1",
            name="positive_versions",
        ),
        CheckConstraint(
            "status in ('ACTIVE', 'SUPERSEDED', 'SUPERSEDED_BY_SEGMENTATION', "
            "'MERGED', 'CANCELLED', 'WITHDRAWN')",
            name="status_values",
        ),
        CheckConstraint(
            "effective_to is null or effective_to > effective_from",
            name="effective_window",
        ),
        CheckConstraint(
            "identity_fingerprint ~ '^[0-9a-f]{64}$'",
            name="fingerprint_format",
        ),
        ForeignKeyConstraint(
            ["opportunity_unit_id", "opportunity_id"],
            ["opportunity_units.opportunity_unit_id", "opportunity_units.opportunity_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_bundle_revision_id"],
            ["source_bundle_revisions.source_bundle_revision_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["opportunity_unit_id", "supersedes_version_id"],
            [
                "opportunity_unit_versions.opportunity_unit_id",
                "opportunity_unit_versions.opportunity_unit_version_id",
            ],
            name="fk_opportunity_unit_versions_supersedes",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "opportunity_unit_id",
            "version",
            name="uq_opportunity_unit_versions_unit_version",
        ),
        UniqueConstraint(
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            name="uq_opportunity_unit_versions_unit_version_id",
        ),
        UniqueConstraint(
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            "opportunity_id",
            name="uq_opportunity_unit_versions_member_binding",
        ),
        UniqueConstraint(
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            "opportunity_id",
            "opportunity_version",
            name="uq_opportunity_unit_versions_dataset_binding",
        ),
        UniqueConstraint(
            "opportunity_unit_id",
            "identity_fingerprint",
            "source_bundle_revision_id",
            name="uq_opportunity_unit_versions_idempotency",
        ),
    )

    opportunity_unit_version_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    opportunity_unit_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)
    source_bundle_revision_id: Mapped[UUID] = mapped_column(Uuid)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32))
    canonical_label: Mapped[str] = mapped_column(Text)
    identity_fingerprint: Mapped[str] = mapped_column(String(64))
    supersedes_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OpportunityUnitAlias(Base):
    __tablename__ = "opportunity_unit_aliases"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(alias_id) = 7", name="alias_id_uuid7"),
        CheckConstraint(
            "alias_kind in ('CURRENT', 'HISTORICAL', 'OFFICIAL_CODE', 'CANONICAL_DERIVED')",
            name="kind_values",
        ),
        CheckConstraint(
            "valid_to is null or valid_to > valid_from",
            name="effective_window",
        ),
        CheckConstraint(
            "length(btrim(normalized_alias_key)) >= 1 and length(btrim(display_alias_key)) >= 1",
            name="key_nonempty",
        ),
        ForeignKeyConstraint(
            ["opportunity_unit_id", "opportunity_id"],
            ["opportunity_units.opportunity_unit_id", "opportunity_units.opportunity_id"],
            ondelete="RESTRICT",
        ),
        Index(
            "uq_opportunity_unit_aliases_current",
            "opportunity_unit_id",
            unique=True,
            postgresql_where=text("alias_kind = 'CURRENT' and valid_to is null"),
        ),
    )

    alias_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_unit_id: Mapped[UUID] = mapped_column(Uuid)
    normalized_alias_key: Mapped[str] = mapped_column(Text)
    display_alias_key: Mapped[str] = mapped_column(Text)
    alias_kind: Mapped[str] = mapped_column(String(24))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_ref_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("evidence_refs.evidence_ref_id", ondelete="RESTRICT"),
    )
    source_bundle_revision_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "source_bundle_revisions.source_bundle_revision_id",
            ondelete="RESTRICT",
        ),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OpportunityUnitLineageEvent(Base):
    __tablename__ = "opportunity_unit_lineage_events"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(lineage_event_id) = 7",
            name="event_id_uuid7",
        ),
        CheckConstraint(
            "event_type in ('REKEY', 'SPLIT', 'MERGE', 'REVERSAL', 'CANCEL', 'REACTIVATE')",
            name="type_values",
        ),
        CheckConstraint(
            "(event_type = 'REVERSAL') = (reverses_event_id is not null)",
            name="reversal_shape",
        ),
        CheckConstraint(
            "length(btrim(reason_code)) >= 1 and length(btrim(actor_identity)) >= 1",
            name="text_nonempty",
        ),
        UniqueConstraint(
            "lineage_event_id",
            "opportunity_id",
            name="uq_opportunity_unit_lineage_events_event_opportunity",
        ),
        UniqueConstraint(
            "reverses_event_id",
            name="uq_opportunity_unit_lineage_events_reversal",
        ),
    )

    lineage_event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    opportunity_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("opportunities.opportunity_id", ondelete="RESTRICT"),
    )
    event_type: Mapped[str] = mapped_column(String(16))
    reverses_event_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "opportunity_unit_lineage_events.lineage_event_id",
            ondelete="RESTRICT",
        ),
    )
    source_bundle_revision_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "source_bundle_revisions.source_bundle_revision_id",
            ondelete="RESTRICT",
        ),
    )
    reason_code: Mapped[str] = mapped_column(String(128))
    actor_identity: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OpportunityUnitLineageMember(Base):
    __tablename__ = "opportunity_unit_lineage_members"
    __table_args__ = (
        CheckConstraint("member_role in ('SOURCE', 'TARGET')", name="role_values"),
        ForeignKeyConstraint(
            ["lineage_event_id", "opportunity_id"],
            [
                "opportunity_unit_lineage_events.lineage_event_id",
                "opportunity_unit_lineage_events.opportunity_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["opportunity_unit_id", "opportunity_unit_version_id", "opportunity_id"],
            [
                "opportunity_unit_versions.opportunity_unit_id",
                "opportunity_unit_versions.opportunity_unit_version_id",
                "opportunity_unit_versions.opportunity_id",
            ],
            ondelete="RESTRICT",
        ),
        PrimaryKeyConstraint(
            "lineage_event_id",
            "member_role",
            "opportunity_unit_id",
            "opportunity_unit_version_id",
        ),
    )

    lineage_event_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    member_role: Mapped[str] = mapped_column(String(16))
    opportunity_unit_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_unit_version_id: Mapped[UUID] = mapped_column(Uuid)


class OpportunityUnitLineageEvidence(Base):
    __tablename__ = "opportunity_unit_lineage_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["lineage_event_id"],
            ["opportunity_unit_lineage_events.lineage_event_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["evidence_ref_id"],
            ["evidence_refs.evidence_ref_id"],
            ondelete="RESTRICT",
        ),
        PrimaryKeyConstraint("lineage_event_id", "evidence_ref_id"),
    )

    lineage_event_id: Mapped[UUID] = mapped_column(Uuid)
    evidence_ref_id: Mapped[UUID] = mapped_column(Uuid)


class DatasetManifest(Base):
    __tablename__ = "dataset_manifests"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(dataset_manifest_id) = 7",
            name="manifest_id_uuid7",
        ),
        CheckConstraint(
            "partition in ('CALIBRATION', 'DEVELOPMENT', 'VALIDATION', 'LOCKED_ACCEPTANCE')",
            name="partition_values",
        ),
        CheckConstraint(
            "(partition = 'CALIBRATION' and expected_entry_count = 30 and "
            "answer_access_class = 'ASSISTED_CALIBRATION') or "
            "(partition = 'DEVELOPMENT' and expected_entry_count = 70 and "
            "answer_access_class = 'DEVELOPMENT_VISIBLE') or "
            "(partition = 'VALIDATION' and expected_entry_count = 30 and "
            "answer_access_class = 'VALIDATION_BLIND') or "
            "(partition = 'LOCKED_ACCEPTANCE' and expected_entry_count = 200 and "
            "answer_access_class = 'LOCKED_BLIND')",
            name="partition_contract",
        ),
        CheckConstraint(
            "actual_entry_count >= 0 and atomic_group_count >= 0 and "
            "atomic_group_count <= actual_entry_count",
            name="count_ranges",
        ),
        CheckConstraint(
            "status in ('DRAFT', 'FROZEN', 'INVALIDATED')",
            name="status_values",
        ),
        CheckConstraint(
            "(status = 'DRAFT' and frozen_at is null) or "
            "(status in ('FROZEN', 'INVALIDATED') and frozen_at is not null)",
            name="freeze_state",
        ),
        CheckConstraint(
            "(invalidated_at is null and invalidation_reason is null) or "
            "(status = 'INVALIDATED' and invalidated_at is not null and "
            "length(btrim(invalidation_reason)) >= 1)",
            name="invalidation_state",
        ),
        CheckConstraint(
            "manifest_hash ~ '^[0-9a-f]{64}$' and "
            "(successor_manifest_hash is null or "
            "successor_manifest_hash ~ '^[0-9a-f]{64}$')",
            name="hash_formats",
        ),
        UniqueConstraint("manifest_hash"),
        UniqueConstraint(
            "dataset_manifest_id",
            "partition",
            "answer_access_class",
            name="uq_dataset_manifests_entry_binding",
        ),
    )

    dataset_manifest_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    split_manifest_version: Mapped[str] = mapped_column(String(64))
    partition: Mapped[str] = mapped_column(String(32))
    expected_entry_count: Mapped[int] = mapped_column(Integer)
    actual_entry_count: Mapped[int] = mapped_column(Integer)
    atomic_group_count: Mapped[int] = mapped_column(Integer)
    evaluation_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    answer_access_class: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    frozen_by: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str | None] = mapped_column(Text)
    successor_manifest_hash: Mapped[str | None] = mapped_column(String(64))
    manifest_hash: Mapped[str] = mapped_column(String(64))


class DatasetManifestEntry(Base):
    __tablename__ = "dataset_manifest_entries"
    __table_args__ = (
        CheckConstraint(
            "opportunity_version >= 1",
            name="positive_opportunity_version",
        ),
        CheckConstraint(
            "canonical_bundle_hash ~ '^[0-9a-f]{64}$'",
            name="hash_format",
        ),
        CheckConstraint(
            "length(btrim(entry_id)) >= 1 and length(btrim(atomic_group_id)) >= 1",
            name="text_nonempty",
        ),
        CheckConstraint(
            "jsonb_typeof(near_duplicate_cluster_ids) = 'array' and "
            "jsonb_typeof(unit_lineage_ids) = 'array'",
            name="lineage_arrays",
        ),
        ForeignKeyConstraint(
            ["dataset_manifest_id", "partition", "answer_access_class"],
            [
                "dataset_manifests.dataset_manifest_id",
                "dataset_manifests.partition",
                "dataset_manifests.answer_access_class",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
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
        ForeignKeyConstraint(
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
            ondelete="RESTRICT",
        ),
        PrimaryKeyConstraint("dataset_manifest_id", "entry_id"),
        Index("ix_dataset_manifest_entries_atomic_group_id", "atomic_group_id"),
    )

    dataset_manifest_id: Mapped[UUID] = mapped_column(Uuid)
    entry_id: Mapped[str] = mapped_column(String(128))
    partition: Mapped[str] = mapped_column(String(32))
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    opportunity_unit_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_unit_version_id: Mapped[UUID] = mapped_column(Uuid)
    source_bundle_id: Mapped[UUID] = mapped_column(Uuid)
    source_bundle_revision_id: Mapped[UUID] = mapped_column(Uuid)
    canonical_bundle_hash: Mapped[str] = mapped_column(String(64))
    atomic_group_id: Mapped[str] = mapped_column(String(128))
    near_duplicate_cluster_ids: Mapped[list[str]] = mapped_column(JSONB)
    unit_lineage_ids: Mapped[list[str]] = mapped_column(JSONB)
    evaluation_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    answer_access_class: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(extraction_run_id) = 7", name="run_id_uuid7"),
        CheckConstraint("opportunity_version >= 1", name="positive_opportunity_version"),
        CheckConstraint("target_scope in ('OPPORTUNITY', 'UNIT')", name="target_scope_values"),
        CheckConstraint(
            "(target_scope = 'OPPORTUNITY' and opportunity_unit_id is null and "
            "opportunity_unit_version_id is null and unit_segmentation_version is null) or "
            "(target_scope = 'UNIT' and opportunity_unit_id is not null and "
            "opportunity_unit_version_id is not null and "
            "length(btrim(unit_segmentation_version)) >= 1)",
            name="target_shape",
        ),
        CheckConstraint(
            "extractor_kind in ('DETERMINISTIC', 'MODEL', 'HYBRID')",
            name="extractor_kind_values",
        ),
        CheckConstraint(
            "status in ('SUCCEEDED', 'ABSTAINED', 'FAILED')",
            name="status_values",
        ),
        CheckConstraint("completed_at >= started_at", name="timestamp_order"),
        CheckConstraint(
            "jsonb_typeof(ordered_input_block_ids) = 'array' and "
            "jsonb_array_length(ordered_input_block_ids) >= 1",
            name="input_blocks_nonempty",
        ),
        CheckConstraint(
            "input_block_set_hash ~ '^[0-9a-f]{64}$' and evidence_binding_hash ~ '^[0-9a-f]{64}$'",
            name="hash_formats",
        ),
        CheckConstraint(
            "extractor_kind <> 'MODEL' or producer_response_id is not null",
            name="model_response_required",
        ),
        ForeignKeyConstraint(
            ["source_bundle_revision_id", "opportunity_id", "opportunity_version"],
            [
                "source_bundle_revisions.source_bundle_revision_id",
                "source_bundle_revisions.opportunity_id",
                "source_bundle_revisions.opportunity_version",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
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
        UniqueConstraint(
            "extraction_run_id",
            "target_scope",
            "opportunity_id",
            "opportunity_version",
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            name="uq_extraction_runs_candidate_binding",
        ),
    )

    extraction_run_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_bundle_revision_id: Mapped[UUID] = mapped_column(Uuid)
    target_scope: Mapped[str] = mapped_column(String(16))
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    opportunity_unit_id: Mapped[UUID | None] = mapped_column(Uuid)
    opportunity_unit_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    unit_segmentation_version: Mapped[str | None] = mapped_column(String(64))
    task_spec_version: Mapped[str] = mapped_column(String(64))
    extractor_kind: Mapped[str] = mapped_column(String(16))
    component_version: Mapped[str] = mapped_column(String(128))
    producer_identity: Mapped[str] = mapped_column(Text)
    producer_response_id: Mapped[str | None] = mapped_column(Text)
    ordered_input_block_ids: Mapped[list[str]] = mapped_column(JSONB)
    input_block_set_hash: Mapped[str] = mapped_column(String(64))
    evidence_binding_hash: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))


class ExtractionRunInputBlock(Base):
    __tablename__ = "extraction_run_input_blocks"
    __table_args__ = (
        CheckConstraint("input_ordinal >= 1", name="positive_ordinal"),
        ForeignKeyConstraint(
            ["extraction_run_id"],
            ["extraction_runs.extraction_run_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["block_id", "evidence_ref_id", "document_id"],
            [
                "document_blocks.block_id",
                "document_blocks.evidence_ref_id",
                "document_blocks.document_id",
            ],
            ondelete="RESTRICT",
        ),
        PrimaryKeyConstraint("extraction_run_id", "input_ordinal"),
        UniqueConstraint(
            "extraction_run_id",
            "block_id",
            name="uq_extraction_run_input_blocks_run_block",
        ),
    )

    extraction_run_id: Mapped[UUID] = mapped_column(Uuid)
    input_ordinal: Mapped[int] = mapped_column(Integer)
    block_id: Mapped[UUID] = mapped_column(Uuid)
    evidence_ref_id: Mapped[UUID] = mapped_column(Uuid)
    document_id: Mapped[UUID] = mapped_column(Uuid)


class ExtractionCandidate(Base):
    __tablename__ = "extraction_candidates"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(candidate_id) = 7", name="candidate_id_uuid7"),
        CheckConstraint("opportunity_version >= 1", name="positive_opportunity_version"),
        CheckConstraint("target_scope in ('OPPORTUNITY', 'UNIT')", name="target_scope_values"),
        CheckConstraint("length(btrim(field_name)) >= 1", name="field_name_nonempty"),
        CheckConstraint(
            "confidence is null or confidence between 0 and 1", name="confidence_range"
        ),
        CheckConstraint(
            "(abstained and normalized_value_candidate is null and "
            "candidate_reason_code like 'UNKNOWN_%') or "
            "(not abstained and normalized_value_candidate is not null)",
            name="abstention_shape",
        ),
        CheckConstraint("schema_version = '0.8.0'", name="schema_version_v08"),
        ForeignKeyConstraint(
            ["extraction_run_id"],
            ["extraction_runs.extraction_run_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "candidate_id",
            "extraction_run_id",
            name="uq_extraction_candidates_run_binding",
        ),
    )

    candidate_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    extraction_run_id: Mapped[UUID] = mapped_column(Uuid)
    target_scope: Mapped[str] = mapped_column(String(16))
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    opportunity_unit_id: Mapped[UUID | None] = mapped_column(Uuid)
    opportunity_unit_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    field_name: Mapped[str] = mapped_column(String(128))
    raw_value: Mapped[object | None] = mapped_column(JSONB(none_as_null=True))
    normalized_value_candidate: Mapped[object | None] = mapped_column(JSONB(none_as_null=True))
    confidence: Mapped[float | None] = mapped_column(Float)
    abstained: Mapped[bool] = mapped_column(Boolean)
    candidate_reason_code: Mapped[str] = mapped_column(String(128))
    schema_version: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExtractionCandidateEvidence(Base):
    __tablename__ = "extraction_candidate_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["candidate_id", "extraction_run_id"],
            ["extraction_candidates.candidate_id", "extraction_candidates.extraction_run_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["extraction_run_id", "block_id"],
            [
                "extraction_run_input_blocks.extraction_run_id",
                "extraction_run_input_blocks.block_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["block_id", "evidence_ref_id", "document_id"],
            [
                "document_blocks.block_id",
                "document_blocks.evidence_ref_id",
                "document_blocks.document_id",
            ],
            ondelete="RESTRICT",
        ),
        PrimaryKeyConstraint("candidate_id", "block_id"),
        UniqueConstraint(
            "candidate_id",
            "block_id",
            "evidence_ref_id",
            name="uq_extraction_candidate_evidence_fact_binding",
        ),
    )

    candidate_id: Mapped[UUID] = mapped_column(Uuid)
    extraction_run_id: Mapped[UUID] = mapped_column(Uuid)
    block_id: Mapped[UUID] = mapped_column(Uuid)
    evidence_ref_id: Mapped[UUID] = mapped_column(Uuid)
    document_id: Mapped[UUID] = mapped_column(Uuid)


class FactVerificationDecisionModel(Base):
    __tablename__ = "fact_verification_decisions"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(decision_id) = 7", name="decision_id_uuid7"),
        CheckConstraint(
            "decision in ('APPROVE', 'REJECT', 'UNKNOWN', 'NEEDS_ADJUDICATION')",
            name="decision_values",
        ),
        CheckConstraint(
            "verification_method in ('DETERMINISTIC', 'HUMAN', 'APPROVED_MAPPING')",
            name="method_values",
        ),
        CheckConstraint(
            "evidence_support_result in ('SUPPORTED', 'UNSUPPORTED', 'UNKNOWN')",
            name="evidence_support_values",
        ),
        CheckConstraint(
            "precedence_check_result in ('PASSED', 'FAILED', 'UNKNOWN')",
            name="precedence_values",
        ),
        CheckConstraint(
            "decision <> 'APPROVE' or (evidence_support_result = 'SUPPORTED' and "
            "precedence_check_result = 'PASSED')",
            name="approval_support",
        ),
        ForeignKeyConstraint(
            ["candidate_id"],
            ["extraction_candidates.candidate_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "decision_id",
            "candidate_id",
            name="uq_fact_verification_decisions_candidate_binding",
        ),
    )

    decision_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    candidate_id: Mapped[UUID] = mapped_column(Uuid)
    decision: Mapped[str] = mapped_column(String(24))
    verification_method: Mapped[str] = mapped_column(String(24))
    verifier_identity: Mapped[str] = mapped_column(Text)
    verifier_response_id: Mapped[str | None] = mapped_column(Text)
    reason_code: Mapped[str] = mapped_column(String(128))
    evidence_support_result: Mapped[str] = mapped_column(String(16))
    precedence_check_result: Mapped[str] = mapped_column(String(16))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VersionedVerifiedFactSet(Base):
    __tablename__ = "versioned_verified_fact_sets"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(verified_fact_set_id) = 7",
            name="fact_set_id_uuid7",
        ),
        CheckConstraint("version >= 1 and opportunity_version >= 1", name="positive_versions"),
        CheckConstraint("target_scope in ('OPPORTUNITY', 'UNIT')", name="target_scope_values"),
        CheckConstraint(
            "(target_scope = 'OPPORTUNITY' and opportunity_unit_id is null and "
            "opportunity_unit_version_id is null) or (target_scope = 'UNIT' and "
            "opportunity_unit_id is not null and opportunity_unit_version_id is not null)",
            name="target_shape",
        ),
        CheckConstraint(
            "status in ('ACTIVE', 'SUPERSEDED', 'STALE', 'WITHDRAWN')",
            name="status_values",
        ),
        CheckConstraint("fact_schema_version = '0.8.0'", name="schema_version_v08"),
        CheckConstraint(
            "jsonb_typeof(reference_dataset_versions) = 'object'",
            name="reference_versions_object",
        ),
        ForeignKeyConstraint(
            ["source_bundle_revision_id", "opportunity_id", "opportunity_version"],
            [
                "source_bundle_revisions.source_bundle_revision_id",
                "source_bundle_revisions.opportunity_id",
                "source_bundle_revisions.opportunity_version",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
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
        ForeignKeyConstraint(
            ["supersedes_id"],
            ["versioned_verified_fact_sets.verified_fact_set_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "verified_fact_set_id",
            "target_scope",
            "opportunity_id",
            "opportunity_version",
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            name="uq_versioned_verified_fact_sets_target_binding",
        ),
        Index(
            "uq_versioned_verified_fact_sets_opportunity_version",
            "opportunity_id",
            "opportunity_version",
            "version",
            unique=True,
            postgresql_where=text("target_scope = 'OPPORTUNITY'"),
        ),
        Index(
            "uq_versioned_verified_fact_sets_unit_version",
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            "version",
            unique=True,
            postgresql_where=text("target_scope = 'UNIT'"),
        ),
        Index(
            "uq_versioned_verified_fact_sets_active_opportunity",
            "opportunity_id",
            "opportunity_version",
            unique=True,
            postgresql_where=text("target_scope = 'OPPORTUNITY' and status = 'ACTIVE'"),
        ),
        Index(
            "uq_versioned_verified_fact_sets_active_unit",
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            unique=True,
            postgresql_where=text("target_scope = 'UNIT' and status = 'ACTIVE'"),
        ),
    )

    verified_fact_set_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    target_scope: Mapped[str] = mapped_column(String(16))
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    opportunity_unit_id: Mapped[UUID | None] = mapped_column(Uuid)
    opportunity_unit_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_bundle_revision_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    relation_graph_version: Mapped[str] = mapped_column(String(64))
    precedence_graph_version: Mapped[str] = mapped_column(String(64))
    reference_dataset_versions: Mapped[dict[str, str]] = mapped_column(JSONB)
    fact_schema_version: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    supersedes_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VerifiedFactSetTransition(Base):
    __tablename__ = "verified_fact_set_transitions"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(transition_id) = 7", name="transition_id_uuid7"),
        CheckConstraint("from_status = 'ACTIVE'", name="from_status_active"),
        CheckConstraint(
            "to_status in ('SUPERSEDED', 'STALE', 'WITHDRAWN')",
            name="to_status_values",
        ),
        CheckConstraint(
            "(to_status = 'SUPERSEDED' and successor_fact_set_id is not null) or "
            "(to_status <> 'SUPERSEDED' and successor_fact_set_id is null)",
            name="successor_shape",
        ),
        CheckConstraint(
            "(to_status = 'STALE' and dependency_id is not null and "
            "expected_dependency_fingerprint ~ '^[0-9a-f]{64}$' and "
            "observed_dependency_fingerprint ~ '^[0-9a-f]{64}$' and "
            "expected_dependency_fingerprint <> observed_dependency_fingerprint) or "
            "(to_status <> 'STALE' and dependency_id is null and "
            "expected_dependency_fingerprint is null and "
            "observed_dependency_fingerprint is null)",
            name="dependency_invalidation_shape",
        ),
        ForeignKeyConstraint(
            ["verified_fact_set_id"],
            ["versioned_verified_fact_sets.verified_fact_set_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["successor_fact_set_id"],
            ["versioned_verified_fact_sets.verified_fact_set_id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["dependency_id"],
            ["verified_fact_set_dependencies.dependency_id"],
            name="fk_p9b_fact_transition_dependency",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        UniqueConstraint("verified_fact_set_id", name="uq_verified_fact_set_transitions_terminal"),
    )

    transition_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    verified_fact_set_id: Mapped[UUID] = mapped_column(Uuid)
    from_status: Mapped[str] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    successor_fact_set_id: Mapped[UUID | None] = mapped_column(Uuid)
    dependency_id: Mapped[UUID | None] = mapped_column(Uuid)
    expected_dependency_fingerprint: Mapped[str | None] = mapped_column(String(64))
    observed_dependency_fingerprint: Mapped[str | None] = mapped_column(String(64))
    reason_code: Mapped[str] = mapped_column(String(128))
    actor_identity: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VerifiedFact(Base):
    __tablename__ = "verified_facts"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(verified_fact_id) = 7", name="fact_id_uuid7"),
        CheckConstraint("fact_state in ('KNOWN', 'UNKNOWN')", name="fact_state_values"),
        CheckConstraint(
            "(fact_state = 'UNKNOWN' and normalized_value is null) or "
            "(fact_state = 'KNOWN' and normalized_value is not null)",
            name="fact_state_shape",
        ),
        CheckConstraint(
            "dependency_fingerprint ~ '^[0-9a-f]{64}$'",
            name="dependency_fingerprint_format",
        ),
        ForeignKeyConstraint(
            ["verified_fact_set_id"],
            ["versioned_verified_fact_sets.verified_fact_set_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["verification_decision_id", "candidate_id"],
            ["fact_verification_decisions.decision_id", "fact_verification_decisions.candidate_id"],
            ondelete="RESTRICT",
        ),
        PrimaryKeyConstraint("verified_fact_id"),
        UniqueConstraint(
            "verified_fact_set_id",
            "field_name",
            name="uq_verified_facts_fact_set_field",
        ),
        UniqueConstraint(
            "verified_fact_set_id",
            "verified_fact_id",
            name="uq_verified_facts_fact_set_fact",
        ),
    )

    verified_fact_id: Mapped[UUID] = mapped_column(Uuid)
    verified_fact_set_id: Mapped[UUID] = mapped_column(Uuid)
    candidate_id: Mapped[UUID] = mapped_column(Uuid)
    field_name: Mapped[str] = mapped_column(String(128))
    fact_state: Mapped[str] = mapped_column(String(16))
    normalized_value: Mapped[object | None] = mapped_column(JSONB(none_as_null=True))
    raw_value: Mapped[object | None] = mapped_column(JSONB(none_as_null=True))
    verification_decision_id: Mapped[UUID] = mapped_column(Uuid)
    dependency_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VerifiedFactEvidence(Base):
    __tablename__ = "verified_fact_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["verified_fact_set_id", "verified_fact_id"],
            ["verified_facts.verified_fact_set_id", "verified_facts.verified_fact_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["candidate_id", "block_id", "evidence_ref_id"],
            [
                "extraction_candidate_evidence.candidate_id",
                "extraction_candidate_evidence.block_id",
                "extraction_candidate_evidence.evidence_ref_id",
            ],
            ondelete="RESTRICT",
        ),
        PrimaryKeyConstraint("verified_fact_id", "block_id"),
        UniqueConstraint(
            "verified_fact_id",
            "evidence_ref_id",
            name="uq_verified_fact_evidence_fact_ref",
        ),
    )

    verified_fact_id: Mapped[UUID] = mapped_column(Uuid)
    verified_fact_set_id: Mapped[UUID] = mapped_column(Uuid)
    candidate_id: Mapped[UUID] = mapped_column(Uuid)
    block_id: Mapped[UUID] = mapped_column(Uuid)
    evidence_ref_id: Mapped[UUID] = mapped_column(Uuid)


class VerifiedFactSetDependency(Base):
    __tablename__ = "verified_fact_set_dependencies"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(dependency_id) = 7", name="dependency_id_uuid7"),
        CheckConstraint(
            "dependency_type in ('SOURCE_BUNDLE_REVISION', 'DOCUMENT_BLOCK')",
            name="dependency_type_values",
        ),
        CheckConstraint(
            "(dependency_type = 'SOURCE_BUNDLE_REVISION' and "
            "source_bundle_revision_id is not null and block_id is null) or "
            "(dependency_type = 'DOCUMENT_BLOCK' and source_bundle_revision_id is null and "
            "block_id is not null)",
            name="dependency_shape",
        ),
        CheckConstraint(
            "dependency_fingerprint ~ '^[0-9a-f]{64}$'",
            name="dependency_fingerprint_format",
        ),
        ForeignKeyConstraint(
            ["verified_fact_set_id"],
            ["versioned_verified_fact_sets.verified_fact_set_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_bundle_revision_id"],
            ["source_bundle_revisions.source_bundle_revision_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["block_id"],
            ["document_blocks.block_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "verified_fact_set_id",
            "dependency_type",
            "source_bundle_revision_id",
            "block_id",
            name="uq_verified_fact_set_dependencies_identity",
        ),
    )

    dependency_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    verified_fact_set_id: Mapped[UUID] = mapped_column(Uuid)
    dependency_type: Mapped[str] = mapped_column(String(32))
    source_bundle_revision_id: Mapped[UUID | None] = mapped_column(Uuid)
    block_id: Mapped[UUID | None] = mapped_column(Uuid)
    dependency_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RuleCandidateModel(Base):
    __tablename__ = "p9b_rule_candidates"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(rule_candidate_id) = 7",
            name="rule_candidate_id_uuid7",
        ),
        CheckConstraint("target_scope in ('OPPORTUNITY', 'UNIT')", name="target_scope_values"),
        CheckConstraint(
            "(target_scope = 'OPPORTUNITY' and opportunity_unit_id is null and "
            "opportunity_unit_version_id is null) or (target_scope = 'UNIT' and "
            "opportunity_unit_id is not null and opportunity_unit_version_id is not null)",
            name="target_shape",
        ),
        CheckConstraint("rule_type = 'ATOMIC_QUALIFICATION'", name="rule_type_values"),
        CheckConstraint("status = 'PROPOSED'", name="initial_status_proposed"),
        CheckConstraint(
            "jsonb_typeof(proposed_rule_payload) = 'object'",
            name="payload_object",
        ),
        ForeignKeyConstraint(
            ["verified_fact_set_id"],
            ["versioned_verified_fact_sets.verified_fact_set_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "rule_candidate_id",
            "target_scope",
            "opportunity_id",
            "opportunity_version",
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            name="uq_p9b_rule_candidates_target_binding",
        ),
    )

    rule_candidate_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    target_scope: Mapped[str] = mapped_column(String(16))
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    opportunity_unit_id: Mapped[UUID | None] = mapped_column(Uuid)
    opportunity_unit_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    verified_fact_set_id: Mapped[UUID] = mapped_column(Uuid)
    rule_type: Mapped[str] = mapped_column(String(32))
    proposed_rule_payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    compiler_version: Mapped[str] = mapped_column(String(64))
    producer_identity: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RuleCandidateFact(Base):
    __tablename__ = "p9b_rule_candidate_facts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["rule_candidate_id"],
            ["p9b_rule_candidates.rule_candidate_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["verified_fact_set_id", "verified_fact_id"],
            ["verified_facts.verified_fact_set_id", "verified_facts.verified_fact_id"],
            ondelete="RESTRICT",
        ),
        PrimaryKeyConstraint("rule_candidate_id", "verified_fact_id"),
    )

    rule_candidate_id: Mapped[UUID] = mapped_column(Uuid)
    verified_fact_set_id: Mapped[UUID] = mapped_column(Uuid)
    verified_fact_id: Mapped[UUID] = mapped_column(Uuid)


class RuleCandidateEvidence(Base):
    __tablename__ = "p9b_rule_candidate_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["rule_candidate_id"],
            ["p9b_rule_candidates.rule_candidate_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["evidence_ref_id"],
            ["evidence_refs.evidence_ref_id"],
            ondelete="RESTRICT",
        ),
        PrimaryKeyConstraint("rule_candidate_id", "evidence_ref_id"),
    )

    rule_candidate_id: Mapped[UUID] = mapped_column(Uuid)
    evidence_ref_id: Mapped[UUID] = mapped_column(Uuid)


class RuleApprovalDecisionModel(Base):
    __tablename__ = "p9b_rule_approval_decisions"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(rule_approval_decision_id) = 7",
            name="decision_id_uuid7",
        ),
        CheckConstraint(
            "decision in ('APPROVE', 'REJECT', 'NEEDS_ADJUDICATION')",
            name="decision_values",
        ),
        CheckConstraint(
            "approval_method in ('HUMAN', 'DETERMINISTIC_POLICY')",
            name="approval_method_values",
        ),
        ForeignKeyConstraint(
            ["rule_candidate_id"],
            ["p9b_rule_candidates.rule_candidate_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "rule_approval_decision_id",
            "rule_candidate_id",
            name="uq_p9b_rule_approval_decisions_candidate_binding",
        ),
    )

    rule_approval_decision_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    rule_candidate_id: Mapped[UUID] = mapped_column(Uuid)
    decision: Mapped[str] = mapped_column(String(24))
    approver_identity: Mapped[str] = mapped_column(Text)
    approval_method: Mapped[str] = mapped_column(String(32))
    reason_code: Mapped[str] = mapped_column(String(128))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    policy_version: Mapped[str] = mapped_column(String(64))


class UnitRuleSet(Base):
    __tablename__ = "unit_rule_sets"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(unit_rule_set_id) = 7", name="rule_set_id_uuid7"),
        CheckConstraint("opportunity_version >= 1", name="positive_opportunity_version"),
        CheckConstraint("rule_schema_version = '0.8.0'", name="schema_version_v08"),
        CheckConstraint("review_status = 'APPROVED'", name="review_status_approved"),
        CheckConstraint("activation_status = 'DORMANT'", name="activation_status_dormant"),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="payload_object"),
        ForeignKeyConstraint(
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
        ForeignKeyConstraint(
            ["rule_candidate_id"],
            ["p9b_rule_candidates.rule_candidate_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["rule_approval_decision_id", "rule_candidate_id"],
            [
                "p9b_rule_approval_decisions.rule_approval_decision_id",
                "p9b_rule_approval_decisions.rule_candidate_id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("rule_approval_decision_id"),
        UniqueConstraint(
            "opportunity_unit_id",
            "opportunity_unit_version_id",
            "rule_candidate_id",
            name="uq_unit_rule_sets_candidate_target",
        ),
    )

    unit_rule_set_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    opportunity_unit_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_unit_version_id: Mapped[UUID] = mapped_column(Uuid)
    rule_candidate_id: Mapped[UUID] = mapped_column(Uuid)
    rule_schema_version: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    review_status: Mapped[str] = mapped_column(String(16))
    activation_status: Mapped[str] = mapped_column(String(16))
    rule_approval_decision_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GoldAnnotationTask(Base):
    __tablename__ = "gold_annotation_tasks"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(gold_annotation_task_id) = 7", name="task_id_uuid7"),
        CheckConstraint(
            "partition in ('CALIBRATION', 'DEVELOPMENT', 'VALIDATION', 'LOCKED_ACCEPTANCE')",
            name="partition_values",
        ),
        CheckConstraint(
            "status in ('BLIND_REVIEW', 'READY_FOR_ADJUDICATION', 'FROZEN', 'INVALIDATED')",
            name="status_values",
        ),
        CheckConstraint(
            "annotator_identity like 'human:%' and verifier_identity like 'human:%' and "
            "adjudicator_identity like 'human:%' and curator_identity like 'human:%'",
            name="human_responsibility_identities",
        ),
        CheckConstraint(
            "annotator_identity <> verifier_identity and "
            "annotator_identity <> adjudicator_identity and "
            "annotator_identity <> curator_identity and "
            "verifier_identity <> adjudicator_identity and "
            "verifier_identity <> curator_identity and "
            "adjudicator_identity <> curator_identity",
            name="role_identity_separation",
        ),
        CheckConstraint(
            "jsonb_typeof(role_attestation_references) = 'object' and "
            "role_attestation_references ?& array['ANNOTATOR', 'VERIFIER', "
            "'ADJUDICATOR', 'CURATOR']",
            name="role_attestations_complete",
        ),
        CheckConstraint(
            "(status = 'BLIND_REVIEW' and blind_ended_at is null) or "
            "(status <> 'BLIND_REVIEW' and blind_ended_at is not null)",
            name="blind_state",
        ),
        ForeignKeyConstraint(
            ["dataset_manifest_id", "entry_id"],
            ["dataset_manifest_entries.dataset_manifest_id", "dataset_manifest_entries.entry_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["dataset_manifest_id", "partition", "answer_access_class"],
            [
                "dataset_manifests.dataset_manifest_id",
                "dataset_manifests.partition",
                "dataset_manifests.answer_access_class",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("dataset_manifest_id", "entry_id"),
    )

    gold_annotation_task_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    dataset_manifest_id: Mapped[UUID] = mapped_column(Uuid)
    entry_id: Mapped[str] = mapped_column(String(128))
    partition: Mapped[str] = mapped_column(String(32))
    answer_access_class: Mapped[str] = mapped_column(String(32))
    annotator_identity: Mapped[str] = mapped_column(Text)
    verifier_identity: Mapped[str] = mapped_column(Text)
    adjudicator_identity: Mapped[str] = mapped_column(Text)
    curator_identity: Mapped[str] = mapped_column(Text)
    role_attestation_references: Mapped[dict[str, str]] = mapped_column(JSONB)
    blind_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    blind_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    split_seed_reference: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GoldRoleAttestation(Base):
    __tablename__ = "gold_role_attestations"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(gold_role_attestation_id) = 7",
            name="attestation_id_uuid7",
        ),
        CheckConstraint(
            "review_role in ('ANNOTATOR', 'VERIFIER', 'ADJUDICATOR', 'CURATOR')",
            name="review_role_values",
        ),
        CheckConstraint(
            "subject_identity like 'human:%' and "
            "attestation_authority_identity <> subject_identity",
            name="independent_human_subject",
        ),
        CheckConstraint(
            "verification_method in ('EXTERNAL_HUMAN_DIRECTORY', "
            "'SIGNED_ACCOUNT_ASSERTION', 'IN_PERSON_ACCOUNTABILITY_RECORD')",
            name="verification_method_values",
        ),
        CheckConstraint(
            "external_evidence_sha256 ~ '^[0-9a-f]{64}$'",
            name="evidence_hash_format",
        ),
        CheckConstraint(
            "external_evidence_reference not like 'synthetic:%' and "
            "external_evidence_reference not like 'synthetic-fixture:%' and "
            "external_evidence_reference not like 'claimed-human:%'",
            name="external_evidence_required",
        ),
        CheckConstraint(
            "expires_at is null or expires_at > verified_at",
            name="attestation_window",
        ),
        UniqueConstraint(
            "review_role",
            "subject_identity",
            "external_evidence_sha256",
        ),
    )

    gold_role_attestation_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    review_role: Mapped[str] = mapped_column(String(16))
    subject_identity: Mapped[str] = mapped_column(Text)
    attestation_authority_identity: Mapped[str] = mapped_column(Text)
    verification_method: Mapped[str] = mapped_column(String(40))
    external_evidence_reference: Mapped[str] = mapped_column(Text)
    external_evidence_sha256: Mapped[str] = mapped_column(String(64))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GoldAnnotationSubmission(Base):
    __tablename__ = "gold_annotation_submissions"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(gold_annotation_submission_id) = 7",
            name="submission_id_uuid7",
        ),
        CheckConstraint("review_role in ('ANNOTATOR', 'VERIFIER')", name="review_role_values"),
        CheckConstraint(
            "jsonb_typeof(judgments) = 'array' and jsonb_array_length(judgments) >= 1",
            name="judgments_nonempty",
        ),
        ForeignKeyConstraint(
            ["gold_annotation_task_id"],
            ["gold_annotation_tasks.gold_annotation_task_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("gold_annotation_task_id", "review_role"),
        UniqueConstraint(
            "gold_annotation_submission_id",
            "gold_annotation_task_id",
            name="uq_gold_submissions_task_binding",
        ),
    )

    gold_annotation_submission_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    gold_annotation_task_id: Mapped[UUID] = mapped_column(Uuid)
    review_role: Mapped[str] = mapped_column(String(16))
    actor_identity: Mapped[str] = mapped_column(Text)
    assisted_calibration: Mapped[bool] = mapped_column(Boolean)
    judgments: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GoldAdjudicationDecision(Base):
    __tablename__ = "gold_adjudication_decisions"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(gold_adjudication_decision_id) = 7",
            name="decision_id_uuid7",
        ),
        CheckConstraint(
            "annotation_submission_id <> verification_submission_id",
            name="distinct_submissions",
        ),
        CheckConstraint(
            "jsonb_typeof(judgments) = 'array' and jsonb_array_length(judgments) >= 1",
            name="judgments_nonempty",
        ),
        ForeignKeyConstraint(
            ["gold_annotation_task_id"],
            ["gold_annotation_tasks.gold_annotation_task_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["annotation_submission_id", "gold_annotation_task_id"],
            [
                "gold_annotation_submissions.gold_annotation_submission_id",
                "gold_annotation_submissions.gold_annotation_task_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["verification_submission_id", "gold_annotation_task_id"],
            [
                "gold_annotation_submissions.gold_annotation_submission_id",
                "gold_annotation_submissions.gold_annotation_task_id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("gold_annotation_task_id"),
        UniqueConstraint(
            "gold_adjudication_decision_id",
            "gold_annotation_task_id",
            name="uq_gold_adjudication_task_binding",
        ),
    )

    gold_adjudication_decision_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    gold_annotation_task_id: Mapped[UUID] = mapped_column(Uuid)
    annotation_submission_id: Mapped[UUID] = mapped_column(Uuid)
    verification_submission_id: Mapped[UUID] = mapped_column(Uuid)
    adjudicator_identity: Mapped[str] = mapped_column(Text)
    judgments: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    reason_code: Mapped[str] = mapped_column(String(128))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GoldTruthVersion(Base):
    __tablename__ = "gold_truth_versions"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(gold_truth_version_id) = 7", name="truth_version_id_uuid7"
        ),
        CheckConstraint("version >= 1", name="positive_version"),
        CheckConstraint(
            "(version = 1 and supersedes_truth_version_id is null) or "
            "(version > 1 and supersedes_truth_version_id is not null)",
            name="version_chain_shape",
        ),
        CheckConstraint(
            "annotation_submission_id <> verification_submission_id", name="distinct_submissions"
        ),
        CheckConstraint("truth_hash ~ '^[0-9a-f]{64}$'", name="truth_hash_format"),
        CheckConstraint(
            "jsonb_typeof(judgments) = 'array' and jsonb_array_length(judgments) >= 1",
            name="judgments_nonempty",
        ),
        ForeignKeyConstraint(
            ["gold_annotation_task_id"],
            ["gold_annotation_tasks.gold_annotation_task_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["annotation_submission_id", "gold_annotation_task_id"],
            [
                "gold_annotation_submissions.gold_annotation_submission_id",
                "gold_annotation_submissions.gold_annotation_task_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["verification_submission_id", "gold_annotation_task_id"],
            [
                "gold_annotation_submissions.gold_annotation_submission_id",
                "gold_annotation_submissions.gold_annotation_task_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["adjudication_decision_id", "gold_annotation_task_id"],
            [
                "gold_adjudication_decisions.gold_adjudication_decision_id",
                "gold_adjudication_decisions.gold_annotation_task_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["supersedes_truth_version_id"],
            ["gold_truth_versions.gold_truth_version_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("gold_annotation_task_id"),
        UniqueConstraint("truth_hash"),
    )

    gold_truth_version_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    gold_annotation_task_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    supersedes_truth_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    revision_reason_code: Mapped[str] = mapped_column(String(128))
    annotation_submission_id: Mapped[UUID] = mapped_column(Uuid)
    verification_submission_id: Mapped[UUID] = mapped_column(Uuid)
    adjudication_decision_id: Mapped[UUID | None] = mapped_column(Uuid)
    curator_identity: Mapped[str] = mapped_column(Text)
    judgments: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    truth_hash: Mapped[str] = mapped_column(String(64))
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GoldAnswerAccessEvent(Base):
    __tablename__ = "gold_answer_access_events"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(gold_answer_access_event_id) = 7",
            name="access_event_id_uuid7",
        ),
        CheckConstraint(
            "requester_role in ('ANNOTATOR', 'VERIFIER', 'ADJUDICATOR', 'CURATOR', "
            "'AI_ENGINEER', 'EVALUATOR')",
            name="requester_role_values",
        ),
        CheckConstraint(
            "access_kind in ('GOLD_ANSWER', 'ADJUDICATION_REASON', 'MODEL_COMPARISON')",
            name="access_kind_values",
        ),
        CheckConstraint("decision in ('GRANTED', 'DENIED')", name="decision_values"),
        ForeignKeyConstraint(
            ["gold_annotation_task_id"],
            ["gold_annotation_tasks.gold_annotation_task_id"],
            ondelete="RESTRICT",
        ),
    )

    gold_answer_access_event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    gold_annotation_task_id: Mapped[UUID] = mapped_column(Uuid)
    requester_identity: Mapped[str] = mapped_column(Text)
    requester_role: Mapped[str] = mapped_column(String(24))
    access_kind: Mapped[str] = mapped_column(String(32))
    decision: Mapped[str] = mapped_column(String(16))
    reason_code: Mapped[str] = mapped_column(String(128))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ModelTaskSpec(Base):
    __tablename__ = "p9b_model_task_specs"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(model_task_spec_id) = 7", name="id_uuid7"),
        CheckConstraint("route_class in ('R1_LOW_COST_EXTRACT', 'R2_BALANCED_REASON', "
                        "'R3_STRONG_CANDIDATE')", name="route_class_values"),
        CheckConstraint("max_input_tokens >= 1 and max_output_tokens >= 1", name="token_bounds"),
        CheckConstraint("timeout_ms between 100 and 120000", name="timeout_bounds"),
        CheckConstraint("max_attempts between 1 and 3", name="attempt_bounds"),
        CheckConstraint("initial_backoff_ms between 0 and 10000", name="initial_backoff_bounds"),
        CheckConstraint("backoff_multiplier between 1 and 4", name="backoff_multiplier_bounds"),
        CheckConstraint(
            "max_backoff_ms between initial_backoff_ms and 30000",
            name="max_backoff_bounds",
        ),
        CheckConstraint("max_concurrency between 1 and 8", name="concurrency_bounds"),
        CheckConstraint("max_batch_size between 1 and 16", name="batch_bounds"),
        CheckConstraint(
            "fallback_policy = 'DISABLED' and max_fallbacks = 0",
            name="fallback_disabled",
        ),
        UniqueConstraint("task_name", "task_version"),
    )

    model_task_spec_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    task_name: Mapped[str] = mapped_column(String(64))
    task_version: Mapped[str] = mapped_column(String(32))
    route_class: Mapped[str] = mapped_column(String(32))
    allowed_input_block_types: Mapped[list[str]] = mapped_column(ARRAY(Text))
    output_schema_version: Mapped[str] = mapped_column(String(64))
    max_input_tokens: Mapped[int] = mapped_column(Integer)
    max_output_tokens: Mapped[int] = mapped_column(Integer)
    evidence_required: Mapped[bool] = mapped_column(Boolean)
    abstention_allowed: Mapped[bool] = mapped_column(Boolean)
    risk_class: Mapped[str] = mapped_column(String(32))
    provider_capabilities: Mapped[list[str]] = mapped_column(ARRAY(Text))
    egress_policy_id: Mapped[str] = mapped_column(String(64))
    timeout_ms: Mapped[int] = mapped_column(Integer)
    max_attempts: Mapped[int] = mapped_column(Integer)
    initial_backoff_ms: Mapped[int] = mapped_column(Integer)
    backoff_multiplier: Mapped[float] = mapped_column(Float)
    max_backoff_ms: Mapped[int] = mapped_column(Integer)
    max_concurrency: Mapped[int] = mapped_column(Integer)
    max_batch_size: Mapped[int] = mapped_column(Integer)
    fallback_policy: Mapped[str] = mapped_column(String(32))
    max_fallbacks: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EgressBlockClassification(Base):
    __tablename__ = "p9b_egress_block_classifications"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(classification_id) = 7", name="id_uuid7"),
        CheckConstraint("block_hash ~ '^[0-9a-f]{64}$'", name="block_hash_format"),
        ForeignKeyConstraint(["block_id"], ["document_blocks.block_id"], ondelete="RESTRICT"),
        UniqueConstraint("block_id", "block_hash", "classification_version"),
    )

    classification_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    block_id: Mapped[UUID] = mapped_column(Uuid)
    block_hash: Mapped[str] = mapped_column(String(64))
    classification_version: Mapped[str] = mapped_column(String(64))
    classifications: Mapped[list[str]] = mapped_column(ARRAY(Text))
    contains_user_data: Mapped[bool] = mapped_column(Boolean)
    classifier_identity: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceEgressPolicySnapshot(Base):
    __tablename__ = "p9b_source_egress_policy_snapshots"
    __table_args__ = (
        CheckConstraint("snapshot_hash ~ '^[0-9a-f]{64}$'", name="snapshot_hash_format"),
        CheckConstraint("valid_until > valid_from", name="valid_window"),
        ForeignKeyConstraint(
            ["source_bundle_revision_id"],
            ["source_bundle_revisions.source_bundle_revision_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("snapshot_hash"),
    )

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    source_bundle_revision_id: Mapped[UUID] = mapped_column(Uuid)
    allows_egress: Mapped[bool] = mapped_column(Boolean)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProviderEgressPolicySnapshot(Base):
    __tablename__ = "p9b_provider_egress_policy_snapshots"
    __table_args__ = (
        CheckConstraint("snapshot_hash ~ '^[0-9a-f]{64}$'", name="snapshot_hash_format"),
        CheckConstraint("valid_until > valid_from", name="valid_window"),
        CheckConstraint(
            "retention_class in ('ZERO_RETENTION', 'PROVIDER_TRANSIENT_RETENTION', "
            "'INTERNAL_ENCRYPTED_AUDIT')",
            name="retention_class_values",
        ),
        UniqueConstraint("snapshot_hash"),
    )

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean)
    zero_retention: Mapped[bool] = mapped_column(Boolean)
    training_use: Mapped[bool] = mapped_column(Boolean)
    supports_idempotency: Mapped[bool] = mapped_column(Boolean)
    allowed_classifications: Mapped[list[str]] = mapped_column(ARRAY(Text))
    retention_class: Mapped[str] = mapped_column(String(40))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EgressDecision(Base):
    __tablename__ = "p9b_egress_decisions"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(egress_decision_id) = 7", name="id_uuid7"),
        CheckConstraint("target_scope in ('OPPORTUNITY', 'UNIT')", name="target_scope_values"),
        CheckConstraint(
            "(target_scope = 'UNIT') = (opportunity_unit_id is not null and "
            "opportunity_unit_version_id is not null)",
            name="unit_target_shape",
        ),
        CheckConstraint("decision in ('ALLOW', 'REDACT_AND_ALLOW', 'DENY', "
                        "'LOCAL_NO_EGRESS')", name="decision_values"),
        CheckConstraint(
            "original_input_hash ~ '^[0-9a-f]{64}$' and "
            "(actual_payload_hash is null or actual_payload_hash ~ '^[0-9a-f]{64}$')",
            name="hash_formats",
        ),
        CheckConstraint(
            "(decision in ('ALLOW', 'REDACT_AND_ALLOW')) = "
            "(actual_payload_hash is not null and expires_at is not null)",
            name="allowed_payload_shape",
        ),
        ForeignKeyConstraint(
            ["task_spec_name", "task_spec_version"],
            ["p9b_model_task_specs.task_name", "p9b_model_task_specs.task_version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_bundle_revision_id", "opportunity_id", "opportunity_version"],
            [
                "source_bundle_revisions.source_bundle_revision_id",
                "source_bundle_revisions.opportunity_id",
                "source_bundle_revisions.opportunity_version",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
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
    )

    egress_decision_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    task_spec_name: Mapped[str] = mapped_column(String(64))
    task_spec_version: Mapped[str] = mapped_column(String(32))
    source_bundle_revision_id: Mapped[UUID] = mapped_column(Uuid)
    target_scope: Mapped[str] = mapped_column(String(16))
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    opportunity_unit_id: Mapped[UUID | None] = mapped_column(Uuid)
    opportunity_unit_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    input_block_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid))
    input_block_hashes: Mapped[list[str]] = mapped_column(ARRAY(String(64)))
    data_classification_version: Mapped[str] = mapped_column(String(64))
    minimizer_version: Mapped[str] = mapped_column(String(64))
    redactor_version: Mapped[str] = mapped_column(String(64))
    source_policy_snapshot_id: Mapped[str] = mapped_column(String(64))
    source_policy_snapshot_hash: Mapped[str] = mapped_column(String(64))
    provider_policy_snapshot_id: Mapped[str] = mapped_column(String(64))
    provider_policy_snapshot_hash: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64))
    provider_region: Mapped[str] = mapped_column(String(64))
    original_input_hash: Mapped[str] = mapped_column(String(64))
    actual_payload_hash: Mapped[str | None] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(24))
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_identity: Mapped[str | None] = mapped_column(String(128))
    reason_codes: Mapped[list[str]] = mapped_column(ARRAY(String(64)))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModelCall(Base):
    __tablename__ = "p9b_model_calls"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(model_call_id) = 7", name="id_uuid7"),
        CheckConstraint("canonical_request_hash ~ '^[0-9a-f]{64}$'", name="request_hash_format"),
        CheckConstraint("target_scope in ('OPPORTUNITY', 'UNIT')", name="target_scope_values"),
        CheckConstraint("temperature between 0 and 2", name="temperature_bounds"),
        CheckConstraint("top_p between 0 and 1", name="top_p_bounds"),
        CheckConstraint(
            "retention_class in ('ZERO_RETENTION', 'PROVIDER_TRANSIENT_RETENTION', "
            "'INTERNAL_ENCRYPTED_AUDIT')",
            name="retention_class_values",
        ),
        ForeignKeyConstraint(
            ["egress_decision_id"],
            ["p9b_egress_decisions.egress_decision_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_bundle_revision_id", "opportunity_id", "opportunity_version"],
            [
                "source_bundle_revisions.source_bundle_revision_id",
                "source_bundle_revisions.opportunity_id",
                "source_bundle_revisions.opportunity_version",
            ],
            ondelete="RESTRICT",
        ),
    )

    model_call_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    task_spec_name: Mapped[str] = mapped_column(String(64))
    task_spec_version: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(64))
    model_id: Mapped[str] = mapped_column(String(128))
    model_snapshot: Mapped[str] = mapped_column(String(128))
    adapter_name: Mapped[str] = mapped_column(String(64))
    adapter_version: Mapped[str] = mapped_column(String(32))
    runtime_version: Mapped[str] = mapped_column(String(64))
    canonical_request_hash: Mapped[str] = mapped_column(String(64))
    canonical_message_hashes: Mapped[list[str]] = mapped_column(ARRAY(String(64)))
    input_block_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid))
    input_block_hashes: Mapped[list[str]] = mapped_column(ARRAY(String(64)))
    source_bundle_revision_id: Mapped[UUID] = mapped_column(Uuid)
    target_scope: Mapped[str] = mapped_column(String(16))
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    opportunity_unit_id: Mapped[UUID | None] = mapped_column(Uuid)
    opportunity_unit_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    unit_segmentation_version: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(64))
    output_schema_version: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str] = mapped_column(String(64))
    contract_version: Mapped[str] = mapped_column(String(64))
    temperature: Mapped[float] = mapped_column(Float)
    top_p: Mapped[float] = mapped_column(Float)
    seed: Mapped[int] = mapped_column(BigInteger)
    egress_decision_id: Mapped[UUID] = mapped_column(Uuid)
    validation_pipeline_version: Mapped[str] = mapped_column(String(64))
    retention_class: Mapped[str] = mapped_column(String(40))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ModelCallAttempt(Base):
    __tablename__ = "p9b_model_call_attempts"
    __table_args__ = (
        PrimaryKeyConstraint("model_call_id", "attempt_number"),
        CheckConstraint("uuid_extract_version(attempt_id) = 7", name="attempt_id_uuid7"),
        CheckConstraint("attempt_number between 1 and 3", name="attempt_number_bounds"),
        CheckConstraint(
            "authorization_decision in ('AUTHORIZED', 'AUTHORITY_REJECTED')",
            name="authorization_values",
        ),
        CheckConstraint(
            "outcome is null or outcome in ('AUTHORITY_REJECTED', 'SUCCEEDED', "
            "'RETRYABLE_PROVIDER_ERROR', 'TERMINAL_PROVIDER_ERROR', "
            "'PROVIDER_OUTCOME_UNKNOWN', 'RESPONSE_METADATA_REJECTED', "
            "'OUTPUT_LIMIT_EXCEEDED', 'INVALID_JSON_RESPONSE', "
            "'INVALID_CANDIDATE_SHAPE', 'OUTPUT_SCHEMA_VALIDATION_FAILED')",
            name="outcome_values",
        ),
        CheckConstraint(
            "(authorization_decision = 'AUTHORIZED') = provider_invocation_allowed",
            name="authorization_dispatch_shape",
        ),
        CheckConstraint(
            "(outcome is null) = (completed_at is null)",
            name="completion_shape",
        ),
        CheckConstraint(
            "response_hash is null or response_hash ~ '^[0-9a-f]{64}$'",
            name="response_hash_format",
        ),
        CheckConstraint(
            "parsed_result_hash is null or parsed_result_hash ~ '^[0-9a-f]{64}$'",
            name="parsed_hash_format",
        ),
        ForeignKeyConstraint(
            ["model_call_id"],
            ["p9b_model_calls.model_call_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["egress_decision_id"],
            ["p9b_egress_decisions.egress_decision_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("attempt_id"),
    )

    model_call_id: Mapped[UUID] = mapped_column(Uuid)
    attempt_number: Mapped[int] = mapped_column(Integer)
    attempt_id: Mapped[UUID] = mapped_column(Uuid)
    egress_decision_id: Mapped[UUID] = mapped_column(Uuid)
    source_bundle_revision_id: Mapped[UUID] = mapped_column(Uuid)
    source_policy_snapshot_id: Mapped[str] = mapped_column(String(64))
    source_policy_snapshot_hash: Mapped[str] = mapped_column(String(64))
    provider_policy_snapshot_id: Mapped[str] = mapped_column(String(64))
    provider_policy_snapshot_hash: Mapped[str] = mapped_column(String(64))
    authorization_decision: Mapped[str] = mapped_column(String(24))
    authorization_reason_code: Mapped[str] = mapped_column(String(64))
    authorization_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dispatch_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_invocation_allowed: Mapped[bool] = mapped_column(Boolean)
    outcome: Mapped[str | None] = mapped_column(String(40))
    provider_http_status: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    provider_response_id: Mapped[str | None] = mapped_column(String(256))
    raw_response_reference_kind: Mapped[str | None] = mapped_column(String(32))
    raw_response_storage_bucket: Mapped[str | None] = mapped_column(String(128))
    raw_response_object_key: Mapped[str | None] = mapped_column(String(512))
    raw_response_sha256: Mapped[str | None] = mapped_column(String(64))
    response_hash: Mapped[str | None] = mapped_column(String(64))
    parsed_result_hash: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_status: Mapped[str | None] = mapped_column(String(24))
    monetary_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ModelCallFinalization(Base):
    __tablename__ = "p9b_model_call_finalizations"
    __table_args__ = (
        CheckConstraint("status in ('SUCCEEDED', 'TERMINAL_FAILED')", name="status_values"),
        CheckConstraint(
            "disposition in ('COMPLETED', 'AUTHORITY_REJECTED', 'PROVIDER_TERMINAL', "
            "'PROVIDER_OUTCOME_UNKNOWN', 'RESPONSE_METADATA_REJECTED', "
            "'ATTEMPTS_EXHAUSTED', 'REVISION_INVALIDATED_AFTER_DISPATCH')",
            name="disposition_values",
        ),
        ForeignKeyConstraint(
            ["model_call_id"],
            ["p9b_model_calls.model_call_id"],
            ondelete="RESTRICT",
        ),
    )

    model_call_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    status: Mapped[str] = mapped_column(String(24))
    disposition: Mapped[str] = mapped_column(String(48))
    reason_code: Mapped[str] = mapped_column(String(64))
    finalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = [
    "DatasetManifest",
    "DatasetManifestEntry",
    "ExtractionCandidate",
    "ExtractionCandidateEvidence",
    "ExtractionRun",
    "ExtractionRunInputBlock",
    "FactVerificationDecisionModel",
    "GoldAdjudicationDecision",
    "GoldAnnotationSubmission",
    "GoldAnnotationTask",
    "GoldAnswerAccessEvent",
    "GoldRoleAttestation",
    "GoldTruthVersion",
    "EgressBlockClassification",
    "EgressDecision",
    "ModelCall",
    "ModelCallAttempt",
    "ModelCallFinalization",
    "ModelTaskSpec",
    "OpportunityUnit",
    "OpportunityUnitAlias",
    "OpportunityUnitLineageEvent",
    "OpportunityUnitLineageEvidence",
    "OpportunityUnitLineageMember",
    "OpportunityUnitVersion",
    "SourceBundle",
    "SourceBundleMember",
    "SourceBundleMemberRelation",
    "SourceBundleRevision",
    "SourceEgressPolicySnapshot",
    "ProviderEgressPolicySnapshot",
    "RuleApprovalDecisionModel",
    "RuleCandidateEvidence",
    "RuleCandidateFact",
    "RuleCandidateModel",
    "UnitRuleSet",
    "VerifiedFact",
    "VerifiedFactEvidence",
    "VerifiedFactSetDependency",
    "VerifiedFactSetTransition",
    "VersionedVerifiedFactSet",
]
