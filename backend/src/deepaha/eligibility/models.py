from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class EligibilityResultModel(Base):
    __tablename__ = "eligibility_results"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(result_id) = 7", name="result_id_uuid7"),
        CheckConstraint(
            "status in ('ELIGIBLE', 'LIKELY_ELIGIBLE', 'UNCERTAIN', 'INELIGIBLE')",
            name="status_values",
        ),
        CheckConstraint(
            "jsonb_typeof(rule_results) = 'array' and jsonb_array_length(rule_results) >= 1",
            name="rule_results_nonempty_array",
        ),
        CheckConstraint(
            "jsonb_typeof(satisfied_rule_ids) = 'array'",
            name="satisfied_rule_ids_array",
        ),
        CheckConstraint(
            "jsonb_typeof(conflict_rule_ids) = 'array'",
            name="conflict_rule_ids_array",
        ),
        CheckConstraint(
            "jsonb_typeof(unknown_rule_ids) = 'array'",
            name="unknown_rule_ids_array",
        ),
        CheckConstraint("jsonb_typeof(missing_fields) = 'array'", name="missing_fields_array"),
        CheckConstraint("jsonb_typeof(review_reasons) = 'array'", name="review_reasons_array"),
        CheckConstraint(
            "status <> 'INELIGIBLE' or jsonb_array_length(conflict_rule_ids) >= 1",
            name="ineligible_has_conflict",
        ),
        CheckConstraint("length(btrim(engine_version)) >= 1", name="engine_version_nonempty"),
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
    )

    result_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column()
    rule_set_id: Mapped[UUID] = mapped_column(Uuid)
    rule_set_version: Mapped[int] = mapped_column()
    profile_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("profile_snapshots.profile_snapshot_id", ondelete="RESTRICT"),
    )
    status: Mapped[str] = mapped_column(String(24))
    rule_results: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    satisfied_rule_ids: Mapped[list[str]] = mapped_column(JSONB)
    conflict_rule_ids: Mapped[list[str]] = mapped_column(JSONB)
    unknown_rule_ids: Mapped[list[str]] = mapped_column(JSONB)
    missing_fields: Mapped[list[str]] = mapped_column(JSONB)
    review_reasons: Mapped[list[str]] = mapped_column(JSONB)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    engine_version: Mapped[str] = mapped_column(String(64))


__all__ = ["EligibilityResultModel"]
