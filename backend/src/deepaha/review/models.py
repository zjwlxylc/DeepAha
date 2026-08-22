from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class ReviewerAccountModel(Base):
    __tablename__ = "reviewer_accounts"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(reviewer_id) = 7", name="reviewer_id_uuid7"),
        CheckConstraint("length(btrim(principal_label)) >= 1", name="principal_label_nonempty"),
        CheckConstraint(
            "jsonb_typeof(roles) = 'array' and jsonb_array_length(roles) >= 1",
            name="roles_nonempty_array",
        ),
        CheckConstraint(
            'roles <@ \'["FEEDBACK_REVIEWER", "FEEDBACK_ADJUDICATOR", '
            '"LABEL_CURATOR", "VALIDATION_REVIEWER"]\'::jsonb',
            name="roles_values",
        ),
        CheckConstraint(
            "allowed_purposes = '[\"FEEDBACK_REVIEW_AND_VALIDATION\"]'::jsonb",
            name="allowed_purposes_value",
        ),
    )

    reviewer_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean)
    synthetic: Mapped[bool] = mapped_column(Boolean)
    principal_label: Mapped[str] = mapped_column(String(64), unique=True)
    roles: Mapped[list[str]] = mapped_column(JSONB)
    allowed_purposes: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReviewerAuthSessionModel(Base):
    __tablename__ = "reviewer_auth_sessions"
    __table_args__ = (
        CheckConstraint("token_sha256 ~ '^[0-9a-f]{64}$'", name="token_sha256_format"),
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        CheckConstraint(
            "revoked_at is null or revoked_at >= created_at",
            name="revocation_after_creation",
        ),
    )

    token_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    reviewer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("reviewer_accounts.reviewer_id", ondelete="RESTRICT"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReviewerIdempotencyRecordModel(Base):
    __tablename__ = "reviewer_idempotency_records"
    __table_args__ = (
        CheckConstraint("length(btrim(operation)) >= 1", name="operation_nonempty"),
        CheckConstraint("key_sha256 ~ '^[0-9a-f]{64}$'", name="key_sha256_format"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_sha256_format"),
        CheckConstraint(
            "resource_kind in ('ASSESSMENT', 'ADJUDICATION', 'LABEL', "
            "'IMPROVEMENT', 'OFFLINE', 'SHADOW', 'VALIDATION_RUN', 'GATE_DECISION')",
            name="resource_kind_values",
        ),
        PrimaryKeyConstraint("reviewer_id", "operation", "key_sha256"),
    )

    reviewer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("reviewer_accounts.reviewer_id", ondelete="RESTRICT"),
    )
    operation: Mapped[str] = mapped_column(String(64))
    key_sha256: Mapped[str] = mapped_column(String(64))
    request_sha256: Mapped[str] = mapped_column(String(64))
    resource_kind: Mapped[str] = mapped_column(String(24))
    resource_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FeedbackReviewCaseSnapshotModel(Base):
    __tablename__ = "feedback_review_case_snapshots"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(review_case_snapshot_id) = 7",
            name="review_case_snapshot_id_uuid7",
        ),
        CheckConstraint("uuid_extract_version(review_case_id) = 7", name="review_case_id_uuid7"),
        CheckConstraint("version >= 1", name="positive_version"),
        CheckConstraint(
            "status in ('RECEIVED', 'NEEDS_EVIDENCE', 'CONFLICT', 'CONFIRMED', 'REJECTED')",
            name="status_values",
        ),
        CheckConstraint("priority between 1 and 3", name="priority_range"),
        CheckConstraint(
            "length(btrim(transition_reason)) between 1 and 300",
            name="transition_reason_bounds",
        ),
        CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="input_sha256_format"),
        UniqueConstraint("review_case_id", "version", name="uq_review_case_stream_version"),
    )

    review_case_snapshot_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    review_case_id: Mapped[UUID] = mapped_column(Uuid)
    feedback_event_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("feedback_events.feedback_event_id", ondelete="RESTRICT"),
    )
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    priority: Mapped[int] = mapped_column(Integer)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    assigned_reviewer_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("reviewer_accounts.reviewer_id", ondelete="RESTRICT"),
    )
    transition_reason: Mapped[str] = mapped_column(String(300))
    input_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FeedbackConfidenceAssessmentModel(Base):
    __tablename__ = "feedback_confidence_assessments"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(confidence_assessment_id) = 7",
            name="id_uuid7",
        ),
        CheckConstraint("review_case_version >= 1", name="positive_review_case_version"),
        CheckConstraint("confidence_band in ('LOW', 'MEDIUM', 'HIGH')", name="confidence_values"),
        CheckConstraint("risk_level in ('NORMAL', 'HIGH_IMPACT')", name="risk_values"),
        CheckConstraint(
            "jsonb_typeof(evidence_ref_ids) = 'array'",
            name="evidence_ref_ids_array",
        ),
        CheckConstraint(
            "evidence_complete is false or jsonb_array_length(evidence_ref_ids) >= 1",
            name="complete_evidence_nonempty",
        ),
        CheckConstraint("length(btrim(rationale)) between 1 and 500", name="rationale_bounds"),
        CheckConstraint(
            "review_purpose = 'FEEDBACK_REVIEW_AND_VALIDATION'",
            name="review_purpose_value",
        ),
        CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="input_sha256_format"),
        ForeignKeyConstraint(
            ["review_case_id", "review_case_version"],
            [
                "feedback_review_case_snapshots.review_case_id",
                "feedback_review_case_snapshots.version",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "confidence_assessment_id",
            "review_case_id",
            "review_case_version",
            name="uq_feedback_assessment_case_version",
        ),
    )

    confidence_assessment_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    review_case_id: Mapped[UUID] = mapped_column(Uuid)
    review_case_version: Mapped[int] = mapped_column(Integer)
    evidence_complete: Mapped[bool] = mapped_column(Boolean)
    confidence_band: Mapped[str] = mapped_column(String(16))
    risk_level: Mapped[str] = mapped_column(String(16))
    conflict: Mapped[bool] = mapped_column(Boolean)
    evidence_ref_ids: Mapped[list[str]] = mapped_column(JSONB)
    rationale: Mapped[str] = mapped_column(Text)
    reviewer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("reviewer_accounts.reviewer_id", ondelete="RESTRICT"),
    )
    review_purpose: Mapped[str] = mapped_column(String(48))
    input_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FeedbackAdjudicationModel(Base):
    __tablename__ = "feedback_adjudications"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(feedback_adjudication_id) = 7",
            name="feedback_adjudication_id_uuid7",
        ),
        CheckConstraint("review_case_version >= 1", name="positive_review_case_version"),
        CheckConstraint(
            "decision in ('NEEDS_EVIDENCE', 'CONFLICT', 'CONFIRMED', 'REJECTED')",
            name="decision_values",
        ),
        CheckConstraint(
            "jsonb_typeof(evidence_ref_ids) = 'array'",
            name="evidence_ref_ids_array",
        ),
        CheckConstraint(
            "decision <> 'CONFIRMED' or jsonb_array_length(evidence_ref_ids) >= 1",
            name="confirmed_evidence_nonempty",
        ),
        CheckConstraint("length(btrim(reason)) between 1 and 500", name="reason_bounds"),
        CheckConstraint(
            "review_purpose = 'FEEDBACK_REVIEW_AND_VALIDATION'",
            name="review_purpose_value",
        ),
        CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="input_sha256_format"),
        ForeignKeyConstraint(
            ["confidence_assessment_id", "review_case_id", "review_case_version"],
            [
                "feedback_confidence_assessments.confidence_assessment_id",
                "feedback_confidence_assessments.review_case_id",
                "feedback_confidence_assessments.review_case_version",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "review_case_id",
            "review_case_version",
            name="uq_feedback_adjudication_case_version",
        ),
    )

    feedback_adjudication_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    review_case_id: Mapped[UUID] = mapped_column(Uuid)
    review_case_version: Mapped[int] = mapped_column(Integer)
    confidence_assessment_id: Mapped[UUID] = mapped_column(Uuid)
    decision: Mapped[str] = mapped_column(String(24))
    evidence_ref_ids: Mapped[list[str]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text)
    adjudicator_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("reviewer_accounts.reviewer_id", ondelete="RESTRICT"),
    )
    review_purpose: Mapped[str] = mapped_column(String(48))
    input_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ApprovedFeedbackLabelModel(Base):
    __tablename__ = "approved_feedback_labels"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(approved_feedback_label_id) = 7",
            name="approved_feedback_label_id_uuid7",
        ),
        CheckConstraint("opportunity_version >= 1", name="positive_opportunity_version"),
        CheckConstraint(
            "claim_kind in ('ELIGIBILITY_CORRECTION', 'OPPORTUNITY_FACT_CORRECTION', "
            "'EXPLANATION_UNCLEAR', 'RANKING_IRRELEVANT')",
            name="claim_kind_values",
        ),
        CheckConstraint(
            "length(btrim(approved_target_value)) between 1 and 500",
            name="approved_target_bounds",
        ),
        CheckConstraint(
            "jsonb_typeof(evidence_ref_ids) = 'array' and "
            "jsonb_array_length(evidence_ref_ids) >= 1",
            name="evidence_ref_ids_nonempty_array",
        ),
        CheckConstraint(
            "evidence_class in ('SYNTHETIC_FEEDBACK_WORKFLOW_ONLY', 'CONSENTED_HUMAN_PARTICIPANT')",
            name="evidence_class_values",
        ),
        CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="content_sha256_format"),
        ForeignKeyConstraint(
            [
                "feedback_event_id",
                "match_snapshot_id",
                "opportunity_id",
                "opportunity_version",
            ],
            [
                "feedback_events.feedback_event_id",
                "feedback_events.match_snapshot_id",
                "feedback_events.opportunity_id",
                "feedback_events.opportunity_version",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("feedback_adjudication_id"),
    )

    approved_feedback_label_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    feedback_event_id: Mapped[UUID] = mapped_column(Uuid)
    feedback_adjudication_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("feedback_adjudications.feedback_adjudication_id", ondelete="RESTRICT"),
    )
    match_snapshot_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    claim_kind: Mapped[str] = mapped_column(String(40))
    approved_target_value: Mapped[str] = mapped_column(Text)
    evidence_ref_ids: Mapped[list[str]] = mapped_column(JSONB)
    evidence_class: Mapped[str] = mapped_column(String(48))
    curator_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("reviewer_accounts.reviewer_id", ondelete="RESTRICT"),
    )
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = [
    "ApprovedFeedbackLabelModel",
    "FeedbackAdjudicationModel",
    "FeedbackConfidenceAssessmentModel",
    "FeedbackReviewCaseSnapshotModel",
    "ReviewerAccountModel",
    "ReviewerAuthSessionModel",
    "ReviewerIdempotencyRecordModel",
]
