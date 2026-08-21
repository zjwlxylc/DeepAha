from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, Text, Uuid, text
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
