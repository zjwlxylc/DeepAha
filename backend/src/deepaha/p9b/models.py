from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
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
            ["opportunity_unit_id", "current_version_id"],
            [
                "opportunity_unit_versions.opportunity_unit_id",
                "opportunity_unit_versions.opportunity_unit_version_id",
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


__all__ = [
    "DatasetManifest",
    "DatasetManifestEntry",
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
]
