from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, Uuid, text
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
            "'POSTGRAD_RECOMMENDATION', 'ADMISSION_CHANGE')",
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
