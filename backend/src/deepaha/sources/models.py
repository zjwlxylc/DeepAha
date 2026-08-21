from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(source_id) = 7", name="source_id_uuid7"),
        CheckConstraint(
            "public_id ~ '^src_[0-9a-f]{32}$'",
            name="public_id_format",
        ),
        CheckConstraint(
            "tier in ('OFFICIAL_PRIMARY', 'OFFICIAL_AGGREGATOR', "
            "'TRUSTED_SECONDARY', 'COMMUNITY_SIGNAL')",
            name="tier_values",
        ),
        CheckConstraint("updated_at >= created_at", name="timestamp_order"),
    )

    source_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    public_id: Mapped[str] = mapped_column(String(36), unique=True)
    canonical_url: Mapped[str] = mapped_column(Text, unique=True)
    authority_name: Mapped[str] = mapped_column(Text)
    tier: Mapped[str] = mapped_column(String(32))
    jurisdiction: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceEndpoint(Base):
    __tablename__ = "source_endpoints"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(endpoint_id) = 7", name="endpoint_id_uuid7"),
        CheckConstraint("jsonb_array_length(allowed_hosts) >= 1", name="allowed_hosts_nonempty"),
        CheckConstraint(
            "jsonb_array_length(expected_media_types) >= 1",
            name="expected_media_types_nonempty",
        ),
        CheckConstraint("browser_policy in ('NEVER', 'FALLBACK')", name="browser_policy_values"),
        CheckConstraint("minimum_interval_seconds >= 1", name="minimum_interval_positive"),
        CheckConstraint("timeout_seconds between 1 and 120", name="timeout_seconds_range"),
        CheckConstraint("max_attempts between 1 and 3", name="max_attempts_range"),
        CheckConstraint(
            "robots_decision in ('ALLOWED', 'NOT_APPLICABLE', 'DISALLOWED', 'UNKNOWN')",
            name="robots_decision_values",
        ),
        CheckConstraint(
            "content_use_basis in "
            "('OPEN_LICENSE', 'OFFICIAL_PUBLIC_ACCESS', 'LINK_ONLY', 'UNKNOWN')",
            name="content_use_basis_values",
        ),
        CheckConstraint(
            "not active or (robots_decision in ('ALLOWED', 'NOT_APPLICABLE') "
            "and content_use_basis <> 'UNKNOWN')",
            name="active_policy_approved",
        ),
        CheckConstraint(
            "content_use_basis <> 'OPEN_LICENSE' or "
            "(license_name is not null and license_url is not null)",
            name="open_license_metadata",
        ),
        CheckConstraint(
            "not fixture_storage_allowed or content_use_basis = 'OPEN_LICENSE'",
            name="fixture_storage_permission",
        ),
        CheckConstraint("updated_at >= created_at", name="timestamp_order"),
        UniqueConstraint("source_id", "url", "policy_version"),
        UniqueConstraint("endpoint_id", "source_id"),
    )

    endpoint_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("sources.source_id", ondelete="RESTRICT"),
    )
    url: Mapped[str] = mapped_column(Text)
    allowed_hosts: Mapped[list[str]] = mapped_column(JSONB)
    expected_media_types: Mapped[list[str]] = mapped_column(JSONB)
    browser_policy: Mapped[str] = mapped_column(String(16))
    minimum_interval_seconds: Mapped[int] = mapped_column(Integer)
    timeout_seconds: Mapped[int] = mapped_column(Integer)
    max_attempts: Mapped[int] = mapped_column(Integer)
    robots_url: Mapped[str | None] = mapped_column(Text)
    robots_decision: Mapped[str] = mapped_column(String(16))
    robots_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_use_basis: Mapped[str] = mapped_column(String(32))
    license_name: Mapped[str | None] = mapped_column(Text)
    license_url: Mapped[str | None] = mapped_column(Text)
    attribution: Mapped[str | None] = mapped_column(Text)
    fixture_storage_allowed: Mapped[bool] = mapped_column(Boolean)
    usage_note: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CaptureObservation(Base):
    __tablename__ = "capture_observations"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(observation_id) = 7",
            name="observation_id_uuid7",
        ),
        CheckConstraint(
            "uuid_extract_version(collection_run_id) = 7",
            name="collection_run_id_uuid7",
        ),
        CheckConstraint("attempt_number >= 1", name="attempt_number_positive"),
        CheckConstraint("completed_at >= started_at", name="timestamp_order"),
        CheckConstraint(
            "outcome in ('SUCCEEDED', 'NOT_MODIFIED', 'FAILED')",
            name="outcome_values",
        ),
        CheckConstraint(
            "http_status is null or http_status between 100 and 599",
            name="http_status_range",
        ),
        CheckConstraint(
            "(outcome = 'SUCCEEDED' and artifact_id is not null and error_code is null) or "
            "(outcome = 'NOT_MODIFIED' and http_status = 304 and artifact_id is not null "
            "and error_code is null) or "
            "(outcome = 'FAILED' and artifact_id is null and error_code is not null)",
            name="outcome_state",
        ),
        ForeignKeyConstraint(
            ["endpoint_id", "source_id"],
            ["source_endpoints.endpoint_id", "source_endpoints.source_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["artifact_id", "source_id"],
            ["raw_artifacts.artifact_id", "raw_artifacts.source_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("collection_run_id", "attempt_number"),
    )

    observation_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    collection_run_id: Mapped[UUID] = mapped_column(Uuid)
    attempt_number: Mapped[int] = mapped_column(Integer)
    endpoint_id: Mapped[UUID] = mapped_column(Uuid)
    source_id: Mapped[UUID] = mapped_column(Uuid)
    requested_url: Mapped[str] = mapped_column(Text)
    resolved_url: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(16))
    http_status: Mapped[int | None] = mapped_column(Integer)
    response_etag: Mapped[str | None] = mapped_column(Text)
    response_last_modified: Mapped[str | None] = mapped_column(Text)
    artifact_id: Mapped[UUID | None] = mapped_column(Uuid)
    error_code: Mapped[str | None] = mapped_column(String(128))
    collector_name: Mapped[str] = mapped_column(String(128))
    collector_version: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(64))
