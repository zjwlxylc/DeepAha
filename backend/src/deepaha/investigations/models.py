from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base

STATES = (
    "QUEUED",
    "CREATING",
    "PREPARING",
    "INVESTIGATING",
    "COLLECTING",
    "PENDING_REVIEW",
    "APPROVED",
    "REJECTED",
    "FAILED_PREPARATION",
    "EXECUTION_UNCERTAIN",
    "COLLECTION_RETRYABLE",
    "FAILED_VALIDATION",
    "EXPIRED",
)


class InvestigationTask(Base):
    __tablename__ = "investigation_tasks"
    __table_args__ = (
        UniqueConstraint("created_by", "request_key_hash"),
        ForeignKeyConstraint(
            ["endpoint_id", "source_id"],
            ["source_endpoints.endpoint_id", "source_endpoints.source_id"],
        ),
        CheckConstraint(
            "status in (" + ",".join(repr(x) for x in STATES) + ")", name="status_values"
        ),
        CheckConstraint(
            "status not in ('PENDING_REVIEW','APPROVED','REJECTED') or delivery_hash is not null",
            name="delivery_required",
        ),
        CheckConstraint(
            "status not in ('APPROVED','REJECTED') or reviewer_id is not null",
            name="reviewer_required",
        ),
    )
    task_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_id: Mapped[UUID] = mapped_column(Uuid)
    endpoint_id: Mapped[UUID] = mapped_column(Uuid)
    created_by: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    request_key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, object]] = mapped_column(JSONB)
    source_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB)
    contract: Mapped[dict[str, object]] = mapped_column(JSONB)
    contract_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    execution: Mapped[dict[str, object]] = mapped_column(JSONB)
    runtime_id: Mapped[str | None] = mapped_column(String(256))
    remote_session_id: Mapped[str | None] = mapped_column(String(256))
    lease_owner: Mapped[UUID | None] = mapped_column(Uuid)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))
    delivery_hash: Mapped[str | None] = mapped_column(String(64))
    delivery: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    result_objects: Mapped[dict[str, str]] = mapped_column(JSONB)
    review: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    reviewer_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("reviewer_accounts.reviewer_id")
    )
    review_key_hash: Mapped[str | None] = mapped_column(String(64))
    review_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationMaterial(Base):
    __tablename__ = "investigation_materials"
    task_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_tasks.task_id"), primary_key=True
    )
    material_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    raw_artifact_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("raw_artifacts.artifact_id"))
    metadata_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB)


class InvestigationEvent(Base):
    __tablename__ = "investigation_events"
    task_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_tasks.task_id"), primary_key=True
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationBinding(Base):
    """Append-only full association snapshots; absent positions stay unmapped."""

    __tablename__ = "investigation_bindings"
    __table_args__ = (
        UniqueConstraint("task_id", "sequence", name="uq_investigation_bindings_sequence"),
        UniqueConstraint(
            "task_id", "reviewer_id", "request_key_hash", name="uq_investigation_bindings_request"
        ),
        ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
        ),
        CheckConstraint("uuid_extract_version(binding_id) = 7", name="binding_id_uuid7"),
        CheckConstraint("sequence >= 1 and opportunity_version >= 1", name="positive_versions"),
        CheckConstraint("jsonb_typeof(request) = 'object'", name="request_object"),
        CheckConstraint(
            "delivery_hash ~ '^[0-9a-f]{64}$' and request_key_hash ~ '^[0-9a-f]{64}$' "
            "and request_hash ~ '^[0-9a-f]{64}$'",
            name="hash_formats",
        ),
    )
    binding_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    task_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("investigation_tasks.task_id"))
    sequence: Mapped[int] = mapped_column(Integer)
    delivery_hash: Mapped[str] = mapped_column(String(64))
    source_bundle_revision_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("source_bundle_revisions.source_bundle_revision_id")
    )
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    request_key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
