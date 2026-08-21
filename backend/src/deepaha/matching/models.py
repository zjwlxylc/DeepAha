from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class MatchSnapshotModel(Base):
    __tablename__ = "match_snapshots"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(snapshot_id) = 7", name="snapshot_id_uuid7"),
        CheckConstraint("opportunity_version >= 1", name="positive_opportunity_version"),
        CheckConstraint("rule_set_version >= 1", name="positive_rule_set_version"),
        CheckConstraint("length(btrim(compiler_version)) >= 1", name="compiler_nonempty"),
        CheckConstraint("length(btrim(engine_version)) >= 1", name="engine_nonempty"),
        CheckConstraint("length(btrim(major_catalog_version)) >= 1", name="catalog_nonempty"),
        CheckConstraint("length(btrim(major_mapping_version)) >= 1", name="mapping_nonempty"),
        CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="input_sha256_format"),
        ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["rule_set_id", "rule_set_version"],
            ["rule_sets.rule_set_id", "rule_sets.version"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("eligibility_result_id"),
        UniqueConstraint("input_sha256"),
    )

    snapshot_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    eligibility_result_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("eligibility_results.result_id", ondelete="RESTRICT"),
    )
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    rule_set_id: Mapped[UUID] = mapped_column(Uuid)
    rule_set_version: Mapped[int] = mapped_column(Integer)
    profile_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("profile_snapshots.profile_snapshot_id", ondelete="RESTRICT"),
    )
    compiler_version: Mapped[str] = mapped_column(String(64))
    engine_version: Mapped[str] = mapped_column(String(64))
    major_catalog_version: Mapped[str] = mapped_column(String(128))
    major_mapping_version: Mapped[str] = mapped_column(String(128))
    scenario_clock: Mapped[date] = mapped_column(Date)
    input_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["MatchSnapshotModel"]
