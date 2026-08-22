from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class EvaluationRunModel(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(run_id) = 7", name="run_id_uuid7"),
        CheckConstraint("length(btrim(dataset_id)) >= 1", name="dataset_id_nonempty"),
        CheckConstraint(
            "length(btrim(dataset_version)) >= 1",
            name="dataset_version_nonempty",
        ),
        CheckConstraint("dataset_sha256 ~ '^[0-9a-f]{64}$'", name="dataset_sha256_format"),
        CheckConstraint(
            "evidence_label = 'SYNTHETIC_EVALUATION_ONLY'",
            name="synthetic_evidence_label",
        ),
        CheckConstraint("report_sha256 ~ '^[0-9a-f]{64}$'", name="report_sha256_format"),
        CheckConstraint(
            "component in ('RULE_ENGINE', 'ELIGIBILITY', 'MATCH_REPLAY')",
            name="component_values",
        ),
        CheckConstraint(
            "jsonb_typeof(component_versions) = 'object'",
            name="component_versions_object",
        ),
        CheckConstraint("synthetic is true", name="synthetic_only"),
        CheckConstraint("status in ('RUNNING', 'COMPLETED', 'FAILED')", name="status_values"),
        CheckConstraint(
            "metrics is null or jsonb_typeof(metrics) = 'object'",
            name="metrics_object",
        ),
        CheckConstraint(
            "(status = 'RUNNING' and completed_at is null and metrics is null and "
            "error_summary is null) or "
            "(status = 'COMPLETED' and completed_at is not null and metrics is not null and "
            "error_summary is null) or "
            "(status = 'FAILED' and completed_at is not null and error_summary is not null)",
            name="status_shape",
        ),
        CheckConstraint(
            "completed_at is null or completed_at >= started_at",
            name="timestamp_order",
        ),
    )

    run_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(128))
    dataset_version: Mapped[str] = mapped_column(String(64))
    dataset_sha256: Mapped[str] = mapped_column(String(64))
    evidence_label: Mapped[str] = mapped_column(String(32))
    scenario_clock: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_sha256: Mapped[str] = mapped_column(String(64))
    component: Mapped[str] = mapped_column(String(24))
    component_versions: Mapped[dict[str, object]] = mapped_column(JSONB)
    synthetic: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(16))
    metrics: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(Text)


class EvaluationCaseResultModel(Base):
    __tablename__ = "evaluation_case_results"
    __table_args__ = (
        CheckConstraint("length(btrim(case_id)) >= 1", name="case_id_nonempty"),
        CheckConstraint(
            "expected_status in ('ELIGIBLE', 'LIKELY_ELIGIBLE', 'UNCERTAIN', 'INELIGIBLE')",
            name="expected_status_values",
        ),
        CheckConstraint(
            "actual_status in ('ELIGIBLE', 'LIKELY_ELIGIBLE', 'UNCERTAIN', 'INELIGIBLE')",
            name="actual_status_values",
        ),
        CheckConstraint(
            "passed = (expected_status = actual_status)",
            name="passed_matches_status",
        ),
        CheckConstraint(
            "unexpected_ineligible = (actual_status = 'INELIGIBLE' and "
            "expected_status <> 'INELIGIBLE')",
            name="unexpected_ineligible_matches_status",
        ),
        CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="input_sha256_format"),
        CheckConstraint("jsonb_typeof(reason_codes) = 'array'", name="reason_codes_array"),
    )

    run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("evaluation_runs.run_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    case_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    expected_status: Mapped[str] = mapped_column(String(24))
    actual_status: Mapped[str] = mapped_column(String(24))
    passed: Mapped[bool] = mapped_column(Boolean)
    match_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("match_snapshots.snapshot_id", ondelete="RESTRICT"),
    )
    input_sha256: Mapped[str] = mapped_column(String(64))
    unexpected_ineligible: Mapped[bool] = mapped_column(Boolean)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB)


__all__ = ["EvaluationCaseResultModel", "EvaluationRunModel"]
