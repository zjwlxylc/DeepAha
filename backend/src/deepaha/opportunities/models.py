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


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(opportunity_id) = 7",
            name="opportunity_id_uuid7",
        ),
        CheckConstraint(
            "public_id ~ '^opp_[0-9a-f]{32}$'",
            name="public_id_format",
        ),
        CheckConstraint(
            "type in ('PUBLIC_INSTITUTION_JOB', 'STATE_OWNED_ENTERPRISE_JOB', "
            "'CIVIL_SERVICE', 'GRASSROOTS_PROGRAM', 'YOUTH_POLICY_BENEFIT', "
            "'POSTGRAD_RECOMMENDATION', 'ADMISSION_CHANGE', 'COMPETITION', "
            "'RESEARCH_PROGRAM', 'SCHOLARSHIP', 'YOUTH_DEVELOPMENT_PROGRAM')",
            name="type_values",
        ),
        CheckConstraint(
            "status in ('DRAFT', 'OPEN', 'CLOSING_SOON', 'CLOSED', 'CANCELLED', "
            "'SUPERSEDED', 'UNKNOWN')",
            name="status_values",
        ),
        CheckConstraint(
            "publication_status in ('INTERNAL', 'READY', 'PUBLISHED', 'WITHDRAWN')",
            name="publication_status_values",
        ),
        CheckConstraint(
            "current_version is null or current_version >= 1",
            name="positive_current_version",
        ),
        CheckConstraint("updated_at >= created_at", name="timestamp_order"),
        ForeignKeyConstraint(
            ["opportunity_id", "current_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            name="fk_opportunities_current_version_opportunity_versions",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
    )

    opportunity_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    public_id: Mapped[str] = mapped_column(String(36), unique=True)
    type: Mapped[str] = mapped_column(String(64))
    canonical_title: Mapped[str] = mapped_column(Text)
    issuer_name: Mapped[str] = mapped_column(Text)
    jurisdiction: Mapped[str | None] = mapped_column(Text)
    current_version: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    publication_status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OpportunityVersion(Base):
    __tablename__ = "opportunity_versions"
    __table_args__ = (
        CheckConstraint("version >= 1", name="positive_version"),
        CheckConstraint("jsonb_typeof(snapshot) = 'object'", name="snapshot_object"),
        CheckConstraint("jsonb_typeof(field_evidence) = 'array'", name="field_evidence_array"),
        CheckConstraint(
            "jsonb_typeof(changes) = 'array' and jsonb_array_length(changes) >= 1",
            name="changes_nonempty_array",
        ),
        CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="content_sha256_format",
        ),
        CheckConstraint(
            "review_status in ('NOT_REQUIRED', 'PENDING', 'APPROVED', 'REJECTED')",
            name="review_status_values",
        ),
        CheckConstraint("created_at >= effective_from", name="timestamp_order"),
        ForeignKeyConstraint(
            ["source_evidence_ref_id", "source_document_id"],
            ["evidence_refs.evidence_ref_id", "evidence_refs.document_id"],
            ondelete="RESTRICT",
        ),
        PrimaryKeyConstraint("opportunity_id", "version"),
        UniqueConstraint("opportunity_id", "content_sha256"),
    )

    opportunity_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("opportunities.opportunity_id", ondelete="RESTRICT"),
    )
    version: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_document_id: Mapped[UUID] = mapped_column(Uuid)
    source_evidence_ref_id: Mapped[UUID] = mapped_column(Uuid)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB)
    field_evidence: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    changes: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    content_sha256: Mapped[str] = mapped_column(String(64))
    review_status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OpportunityIdentityAction(Base):
    __tablename__ = "opportunity_identity_actions"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(action_id) = 7",
            name="action_id_uuid7",
        ),
        CheckConstraint(
            "action_type in ('MERGE', 'SPLIT', 'MERGE_REVERSAL', 'SPLIT_REVERSAL')",
            name="action_type_values",
        ),
        CheckConstraint(
            "(action_type in ('MERGE', 'SPLIT') and reversal_of_action_id is null) or "
            "(action_type in ('MERGE_REVERSAL', 'SPLIT_REVERSAL') and "
            "reversal_of_action_id is not null)",
            name="reversal_shape",
        ),
        CheckConstraint("length(btrim(actor)) >= 1", name="actor_nonempty"),
        CheckConstraint("length(btrim(reason)) >= 1", name="reason_nonempty"),
        CheckConstraint(
            "(source_document_id is null) = (source_evidence_ref_id is null)",
            name="source_evidence_pair",
        ),
        ForeignKeyConstraint(
            ["source_evidence_ref_id", "source_document_id"],
            ["evidence_refs.evidence_ref_id", "evidence_refs.document_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("reversal_of_action_id"),
    )

    action_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    action_type: Mapped[str] = mapped_column(String(24))
    reversal_of_action_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("opportunity_identity_actions.action_id", ondelete="RESTRICT"),
    )
    actor: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    source_document_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_evidence_ref_id: Mapped[UUID | None] = mapped_column(Uuid)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OpportunityEvent(Base):
    __tablename__ = "opportunity_events"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(event_id) = 7", name="event_id_uuid7"),
        CheckConstraint(
            "event_type in ('CREATED', 'UPDATED', 'CORRECTED', 'DEADLINE_CHANGED', "
            "'ATTACHMENT_REPLACED', 'CANCELLED', 'REOPENED')",
            name="event_type_values",
        ),
        CheckConstraint(
            "(event_type = 'CREATED' and from_version is null and to_version = 1) or "
            "(event_type <> 'CREATED' and from_version is not null and "
            "to_version = from_version + 1)",
            name="version_transition",
        ),
        CheckConstraint(
            "jsonb_typeof(changed_fields) = 'array' and jsonb_array_length(changed_fields) >= 1",
            name="changed_fields_nonempty_array",
        ),
        CheckConstraint(
            "jsonb_typeof(changes) = 'array' and jsonb_array_length(changes) >= 1",
            name="changes_nonempty_array",
        ),
        ForeignKeyConstraint(
            ["opportunity_id", "to_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["opportunity_id", "from_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_evidence_ref_id", "source_document_id"],
            ["evidence_refs.evidence_ref_id", "evidence_refs.document_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("opportunity_id", "to_version"),
        UniqueConstraint(
            "event_id",
            "opportunity_id",
            "to_version",
            name="uq_opportunity_events_reminder_binding",
        ),
    )

    event_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    from_version: Mapped[int | None] = mapped_column(Integer)
    to_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(32))
    changed_fields: Mapped[list[str]] = mapped_column(JSONB)
    changes: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    source_document_id: Mapped[UUID] = mapped_column(Uuid)
    source_evidence_ref_id: Mapped[UUID] = mapped_column(Uuid)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DocumentOpportunityLink(Base):
    __tablename__ = "document_opportunity_links"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(link_id) = 7", name="link_id_uuid7"),
        CheckConstraint(
            "role in ('PRIMARY_NOTICE', 'ATTACHMENT', 'POSITION_TABLE', 'CORRECTION', "
            "'DEADLINE_EXTENSION', 'CANCELLATION', 'RESULT', 'OFFICIAL_GUIDANCE')",
            name="role_values",
        ),
        CheckConstraint("length(btrim(resolution_key)) >= 1", name="resolution_key_nonempty"),
        CheckConstraint("length(btrim(resolver_version)) >= 1", name="resolver_version_nonempty"),
        CheckConstraint(
            "(ended_at is null) = (ended_by_identity_action_id is null)",
            name="ended_pair",
        ),
        CheckConstraint(
            "ended_at is null or ended_at >= linked_at",
            name="timestamp_order",
        ),
        ForeignKeyConstraint(
            ["source_evidence_ref_id", "document_id"],
            ["evidence_refs.evidence_ref_id", "evidence_refs.document_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("document_id", "opportunity_id", "role"),
        Index(
            "uq_document_opportunity_links_active_document",
            "document_id",
            unique=True,
            postgresql_where=text("ended_at is null"),
        ),
    )

    link_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    document_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.document_id", ondelete="RESTRICT"),
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("opportunities.opportunity_id", ondelete="RESTRICT"),
    )
    role: Mapped[str] = mapped_column(String(32))
    resolution_key: Mapped[str] = mapped_column(Text)
    resolver_version: Mapped[str] = mapped_column(String(64))
    source_evidence_ref_id: Mapped[UUID] = mapped_column(Uuid)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_by_identity_action_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("opportunity_identity_actions.action_id", ondelete="RESTRICT"),
    )


class OpportunityResolutionCandidate(Base):
    __tablename__ = "opportunity_resolution_candidates"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(candidate_id) = 7", name="candidate_id_uuid7"),
        CheckConstraint(
            "proposed_role in ('PRIMARY_NOTICE', 'ATTACHMENT', 'POSITION_TABLE', 'CORRECTION', "
            "'DEADLINE_EXTENSION', 'CANCELLATION', 'RESULT', 'OFFICIAL_GUIDANCE')",
            name="proposed_role_values",
        ),
        CheckConstraint(
            "jsonb_typeof(candidate_opportunity_ids) = 'array'",
            name="candidate_ids_array",
        ),
        CheckConstraint(
            "proposed_snapshot is null or jsonb_typeof(proposed_snapshot) = 'object'",
            name="proposed_snapshot_object",
        ),
        CheckConstraint(
            "jsonb_typeof(reason_codes) = 'array' and jsonb_array_length(reason_codes) >= 1",
            name="reason_codes_array",
        ),
        CheckConstraint("length(btrim(resolver_version)) >= 1", name="resolver_version_nonempty"),
        CheckConstraint("review_status = 'PENDING'", name="review_status_pending"),
        ForeignKeyConstraint(
            ["source_evidence_ref_id", "document_id"],
            ["evidence_refs.evidence_ref_id", "evidence_refs.document_id"],
            ondelete="RESTRICT",
        ),
    )

    candidate_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    document_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.document_id", ondelete="RESTRICT"),
    )
    candidate_opportunity_ids: Mapped[list[str]] = mapped_column(JSONB)
    proposed_role: Mapped[str] = mapped_column(String(32))
    proposed_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True))
    reason_codes: Mapped[list[str]] = mapped_column(JSONB)
    resolver_version: Mapped[str] = mapped_column(String(64))
    source_evidence_ref_id: Mapped[UUID] = mapped_column(Uuid)
    review_status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OpportunityAlias(Base):
    __tablename__ = "opportunity_aliases"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(alias_id) = 7", name="alias_id_uuid7"),
        CheckConstraint("alias_type in ('TITLE', 'URL', 'EXTERNAL_ID')", name="alias_type_values"),
        CheckConstraint("length(btrim(alias_value)) >= 1", name="alias_value_nonempty"),
        CheckConstraint("length(btrim(normalized_value)) >= 1", name="normalized_value_nonempty"),
        CheckConstraint(
            "alias_type <> 'EXTERNAL_ID' or source_id is not null",
            name="external_id_source_required",
        ),
        ForeignKeyConstraint(
            ["source_evidence_ref_id", "source_document_id"],
            ["evidence_refs.evidence_ref_id", "evidence_refs.document_id"],
            ondelete="RESTRICT",
        ),
        Index(
            "uq_opportunity_aliases_url",
            "alias_type",
            "normalized_value",
            unique=True,
            postgresql_where=text("alias_type = 'URL'"),
        ),
        Index(
            "uq_opportunity_aliases_external_id",
            "alias_type",
            "source_id",
            "normalized_value",
            unique=True,
            postgresql_where=text("alias_type = 'EXTERNAL_ID'"),
        ),
    )

    alias_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("opportunities.opportunity_id", ondelete="RESTRICT"),
    )
    alias_type: Mapped[str] = mapped_column(String(16))
    alias_value: Mapped[str] = mapped_column(Text)
    normalized_value: Mapped[str] = mapped_column(Text)
    source_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("sources.source_id", ondelete="RESTRICT"),
    )
    source_document_id: Mapped[UUID] = mapped_column(Uuid)
    source_evidence_ref_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OpportunityIdentityActionMember(Base):
    __tablename__ = "opportunity_identity_action_members"
    __table_args__ = (
        CheckConstraint(
            "role in ('SOURCE', 'TARGET', 'PARENT', 'CHILD')",
            name="role_values",
        ),
    )

    action_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("opportunity_identity_actions.action_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("opportunities.opportunity_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(16), primary_key=True)
