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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class FeedbackImprovementCandidateModel(Base):
    __tablename__ = "feedback_improvement_candidates"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(improvement_candidate_id) = 7",
            name="candidate_id_uuid7",
        ),
        CheckConstraint(
            "uuid_extract_version(validation_cycle_id) = 7",
            name="validation_cycle_id_uuid7",
        ),
        CheckConstraint(
            "jsonb_typeof(approved_label_ids) = 'array' and "
            "jsonb_array_length(approved_label_ids) >= 1",
            name="label_ids_nonempty",
        ),
        CheckConstraint(
            "direction in ('EXPLANATION_CLARITY', 'OPPORTUNITY_FACT_QUALITY', "
            "'ELIGIBILITY_RULE_CANDIDATE', 'RANKING_POLICY_CANDIDATE')",
            name="direction_values",
        ),
        CheckConstraint("length(btrim(component)) >= 1", name="component_nonempty"),
        CheckConstraint(
            "input_manifest_sha256 ~ '^[0-9a-f]{64}$'",
            name="input_manifest_sha256_format",
        ),
        CheckConstraint(
            "length(btrim(change_statement)) between 1 and 500",
            name="change_statement_bounds",
        ),
        CheckConstraint("candidate_sha256 ~ '^[0-9a-f]{64}$'", name="candidate_sha256_format"),
        CheckConstraint(
            "evidence_class in ('SYNTHETIC_FEEDBACK_WORKFLOW_ONLY', 'CONSENTED_HUMAN_PARTICIPANT')",
            name="evidence_class_values",
        ),
        CheckConstraint("selected is true", name="selected_only"),
        UniqueConstraint("validation_cycle_id", name="uq_phase7_validation_cycle_candidate"),
    )

    improvement_candidate_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    validation_cycle_id: Mapped[UUID] = mapped_column(Uuid)
    approved_label_ids: Mapped[list[str]] = mapped_column(JSONB)
    direction: Mapped[str] = mapped_column(String(40))
    component: Mapped[str] = mapped_column(String(128))
    input_manifest_sha256: Mapped[str] = mapped_column(String(64))
    change_statement: Mapped[str] = mapped_column(Text)
    candidate_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    evidence_class: Mapped[str] = mapped_column(String(48))
    selected: Mapped[bool] = mapped_column(Boolean)
    created_by_reviewer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("reviewer_accounts.reviewer_id", ondelete="RESTRICT"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OfflineEvaluationCandidateModel(Base):
    __tablename__ = "offline_evaluation_candidates"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(offline_evaluation_candidate_id) = 7",
            name="offline_candidate_id_uuid7",
        ),
        CheckConstraint("dataset_version >= 1", name="positive_dataset_version"),
        CheckConstraint("dataset_sha256 ~ '^[0-9a-f]{64}$'", name="dataset_sha256_format"),
        CheckConstraint(
            "length(btrim(baseline_component_version)) >= 1",
            name="baseline_version_nonempty",
        ),
        CheckConstraint(
            "length(btrim(candidate_component_version)) >= 1",
            name="candidate_version_nonempty",
        ),
        CheckConstraint("outcome in ('PASSED', 'FAILED')", name="outcome_values"),
        CheckConstraint("result_sha256 ~ '^[0-9a-f]{64}$'", name="result_sha256_format"),
        CheckConstraint(
            "evidence_class in ('SYNTHETIC_SIMULATION_ONLY', 'CONSENTED_HUMAN_PARTICIPANT')",
            name="evidence_class_values",
        ),
        UniqueConstraint(
            "offline_evaluation_candidate_id",
            "improvement_candidate_id",
            name="uq_offline_candidate_improvement",
        ),
        UniqueConstraint(
            "improvement_candidate_id",
            "dataset_id",
            "dataset_version",
            name="uq_offline_candidate_dataset",
        ),
    )

    offline_evaluation_candidate_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    improvement_candidate_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "feedback_improvement_candidates.improvement_candidate_id",
            ondelete="RESTRICT",
        ),
    )
    dataset_id: Mapped[UUID] = mapped_column(Uuid)
    dataset_version: Mapped[int] = mapped_column(Integer)
    dataset_sha256: Mapped[str] = mapped_column(String(64))
    baseline_component_version: Mapped[str] = mapped_column(String(128))
    candidate_component_version: Mapped[str] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(16))
    result_sha256: Mapped[str] = mapped_column(String(64))
    evidence_class: Mapped[str] = mapped_column(String(48))
    created_by_reviewer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("reviewer_accounts.reviewer_id", ondelete="RESTRICT"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ShadowTestCandidateModel(Base):
    __tablename__ = "shadow_test_candidates"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(shadow_test_candidate_id) = 7",
            name="shadow_candidate_id_uuid7",
        ),
        CheckConstraint(
            "length(btrim(baseline_component_version)) >= 1",
            name="baseline_version_nonempty",
        ),
        CheckConstraint(
            "length(btrim(candidate_component_version)) >= 1",
            name="candidate_version_nonempty",
        ),
        CheckConstraint("outcome in ('PASSED', 'FAILED')", name="outcome_values"),
        CheckConstraint(
            "comparison_sha256 ~ '^[0-9a-f]{64}$'",
            name="comparison_sha256_format",
        ),
        CheckConstraint(
            "evidence_class in ('SYNTHETIC_SIMULATION_ONLY', 'CONSENTED_HUMAN_PARTICIPANT')",
            name="evidence_class_values",
        ),
        ForeignKeyConstraint(
            ["offline_evaluation_candidate_id", "improvement_candidate_id"],
            [
                "offline_evaluation_candidates.offline_evaluation_candidate_id",
                "offline_evaluation_candidates.improvement_candidate_id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("offline_evaluation_candidate_id"),
        UniqueConstraint(
            "shadow_test_candidate_id",
            "improvement_candidate_id",
            "offline_evaluation_candidate_id",
            name="uq_shadow_candidate_gate_binding",
        ),
    )

    shadow_test_candidate_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    improvement_candidate_id: Mapped[UUID] = mapped_column(Uuid)
    offline_evaluation_candidate_id: Mapped[UUID] = mapped_column(Uuid)
    baseline_component_version: Mapped[str] = mapped_column(String(128))
    candidate_component_version: Mapped[str] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(16))
    comparison_sha256: Mapped[str] = mapped_column(String(64))
    evidence_class: Mapped[str] = mapped_column(String(48))
    created_by_reviewer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("reviewer_accounts.reviewer_id", ondelete="RESTRICT"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ValidationRunModel(Base):
    __tablename__ = "validation_runs"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(validation_run_id) = 7",
            name="validation_run_id_uuid7",
        ),
        CheckConstraint("dataset_version >= 1", name="positive_dataset_version"),
        CheckConstraint("dataset_sha256 ~ '^[0-9a-f]{64}$'", name="dataset_sha256_format"),
        CheckConstraint("track in ('SIMULATION', 'HUMAN_PARTICIPANT')", name="track_values"),
        CheckConstraint(
            "(track = 'SIMULATION' and evidence_class = 'SYNTHETIC_SIMULATION_ONLY' "
            "and synthetic is true and release_qualification_eligible is false) or "
            "(track = 'HUMAN_PARTICIPANT' and "
            "evidence_class = 'CONSENTED_HUMAN_PARTICIPANT' and synthetic is false)",
            name="track_evidence_separation",
        ),
        CheckConstraint("outcome in ('PASSED', 'FAILED')", name="outcome_values"),
        CheckConstraint("jsonb_typeof(metrics) = 'object'", name="metrics_object"),
        CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="input_sha256_format"),
        CheckConstraint("completed_at >= started_at", name="timestamp_order"),
        UniqueConstraint("validation_cycle_id", "track", name="uq_validation_cycle_track"),
        UniqueConstraint(
            "validation_run_id",
            "improvement_candidate_id",
            name="uq_validation_run_improvement",
        ),
    )

    validation_run_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    validation_cycle_id: Mapped[UUID] = mapped_column(Uuid)
    improvement_candidate_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "feedback_improvement_candidates.improvement_candidate_id",
            ondelete="RESTRICT",
        ),
    )
    dataset_id: Mapped[UUID] = mapped_column(Uuid)
    dataset_version: Mapped[int] = mapped_column(Integer)
    dataset_sha256: Mapped[str] = mapped_column(String(64))
    track: Mapped[str] = mapped_column(String(24))
    evidence_class: Mapped[str] = mapped_column(String(48))
    synthetic: Mapped[bool] = mapped_column(Boolean)
    release_qualification_eligible: Mapped[bool] = mapped_column(Boolean)
    outcome: Mapped[str] = mapped_column(String(16))
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB)
    input_sha256: Mapped[str] = mapped_column(String(64))
    created_by_reviewer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("reviewer_accounts.reviewer_id", ondelete="RESTRICT"),
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReleaseGateDecisionModel(Base):
    __tablename__ = "release_gate_decisions"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(release_gate_decision_id) = 7",
            name="release_gate_decision_id_uuid7",
        ),
        CheckConstraint(
            "decision in ('HOLD_MISSING_HUMAN_EVIDENCE', 'HOLD_ENGINEERING_FAILURE', "
            "'REJECTED', 'CANDIDATE_ACCEPTED_FOR_FUTURE_IMPLEMENTATION')",
            name="decision_values",
        ),
        CheckConstraint(
            "decision <> 'CANDIDATE_ACCEPTED_FOR_FUTURE_IMPLEMENTATION' or "
            "(simulation_validation_run_id is not null and human_validation_run_id is not null)",
            name="accepted_requires_both_tracks",
        ),
        CheckConstraint(
            "decision <> 'HOLD_MISSING_HUMAN_EVIDENCE' or "
            "(simulation_validation_run_id is not null and human_validation_run_id is null)",
            name="missing_human_hold_shape",
        ),
        CheckConstraint("length(btrim(rationale)) between 1 and 500", name="rationale_bounds"),
        CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="input_sha256_format"),
        ForeignKeyConstraint(
            ["offline_evaluation_candidate_id", "improvement_candidate_id"],
            [
                "offline_evaluation_candidates.offline_evaluation_candidate_id",
                "offline_evaluation_candidates.improvement_candidate_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "shadow_test_candidate_id",
                "improvement_candidate_id",
                "offline_evaluation_candidate_id",
            ],
            [
                "shadow_test_candidates.shadow_test_candidate_id",
                "shadow_test_candidates.improvement_candidate_id",
                "shadow_test_candidates.offline_evaluation_candidate_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["simulation_validation_run_id", "improvement_candidate_id"],
            ["validation_runs.validation_run_id", "validation_runs.improvement_candidate_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["human_validation_run_id", "improvement_candidate_id"],
            ["validation_runs.validation_run_id", "validation_runs.improvement_candidate_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("validation_cycle_id"),
    )

    release_gate_decision_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    validation_cycle_id: Mapped[UUID] = mapped_column(Uuid)
    improvement_candidate_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "feedback_improvement_candidates.improvement_candidate_id",
            ondelete="RESTRICT",
        ),
    )
    offline_evaluation_candidate_id: Mapped[UUID] = mapped_column(Uuid)
    shadow_test_candidate_id: Mapped[UUID] = mapped_column(Uuid)
    simulation_validation_run_id: Mapped[UUID | None] = mapped_column(Uuid)
    human_validation_run_id: Mapped[UUID | None] = mapped_column(Uuid)
    decision: Mapped[str] = mapped_column(String(64))
    rationale: Mapped[str] = mapped_column(Text)
    input_sha256: Mapped[str] = mapped_column(String(64))
    decided_by_reviewer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("reviewer_accounts.reviewer_id", ondelete="RESTRICT"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = [
    "FeedbackImprovementCandidateModel",
    "OfflineEvaluationCandidateModel",
    "ReleaseGateDecisionModel",
    "ShadowTestCandidateModel",
    "ValidationRunModel",
]
