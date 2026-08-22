from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class ProfileSnapshotModel(Base):
    __tablename__ = "profile_snapshots"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(profile_snapshot_id) = 7",
            name="profile_snapshot_id_uuid7",
        ),
        CheckConstraint("uuid_extract_version(profile_id) = 7", name="profile_id_uuid7"),
        CheckConstraint(
            "persona_family_id is null or uuid_extract_version(persona_family_id) = 7",
            name="persona_family_id_uuid7",
        ),
        CheckConstraint("version >= 1", name="positive_version"),
        CheckConstraint("jsonb_typeof(attributes) = 'object'", name="attributes_object"),
        CheckConstraint(
            "(synthetic is true and profile_schema_version = '0.4.0') or "
            "(synthetic is false and profile_schema_version = '0.5.0')",
            name="provenance_schema_version",
        ),
        CheckConstraint("length(btrim(created_by)) >= 1", name="created_by_nonempty"),
        CheckConstraint("length(btrim(reviewed_by)) >= 1", name="reviewed_by_nonempty"),
        CheckConstraint("length(btrim(change_note)) >= 1", name="change_note_nonempty"),
        UniqueConstraint(
            "profile_id",
            "version",
            name="uq_profile_snapshots_profile_version",
        ),
    )

    profile_snapshot_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    profile_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    synthetic: Mapped[bool] = mapped_column(Boolean)
    persona_family_id: Mapped[UUID | None] = mapped_column(Uuid)
    attributes: Mapped[dict[str, object]] = mapped_column(JSONB)
    scenario_clock: Mapped[date] = mapped_column(Date)
    profile_schema_version: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(Text)
    reviewed_by: Mapped[str] = mapped_column(Text)
    change_note: Mapped[str] = mapped_column(Text)


__all__ = ["ProfileSnapshotModel"]
