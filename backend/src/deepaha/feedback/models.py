from datetime import datetime
from uuid import UUID

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class FeedbackIdempotencyRecordModel(Base):
    __tablename__ = "feedback_idempotency_records"
    __table_args__ = (
        CheckConstraint("length(btrim(operation)) >= 1", name="operation_nonempty"),
        CheckConstraint("key_sha256 ~ '^[0-9a-f]{64}$'", name="key_sha256_format"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_sha256_format"),
        CheckConstraint(
            "resource_kind in ('FEEDBACK_EVENT', 'EVIDENCE_LINK')",
            name="resource_kind_values",
        ),
        CheckConstraint("response_version >= 1", name="positive_response_version"),
        PrimaryKeyConstraint("owner_user_id", "operation", "key_sha256"),
    )

    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("personal_users.user_id", ondelete="RESTRICT"),
    )
    operation: Mapped[str] = mapped_column(String(64))
    key_sha256: Mapped[str] = mapped_column(String(64))
    request_sha256: Mapped[str] = mapped_column(String(64))
    resource_kind: Mapped[str] = mapped_column(String(24))
    resource_id: Mapped[UUID] = mapped_column(Uuid)
    response_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FeedbackEventModel(Base):
    __tablename__ = "feedback_events"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(feedback_event_id) = 7",
            name="feedback_event_id_uuid7",
        ),
        CheckConstraint("opportunity_version >= 1", name="positive_opportunity_version"),
        CheckConstraint("user_state_version >= 1", name="positive_user_state_version"),
        CheckConstraint(
            "event_type in ('STRUCTURED_CORRECTION', 'EXPLICIT_EVALUATION')",
            name="event_type_values",
        ),
        CheckConstraint(
            "claim_kind in ('ELIGIBILITY_CORRECTION', 'OPPORTUNITY_FACT_CORRECTION', "
            "'EXPLANATION_UNCLEAR', 'RANKING_IRRELEVANT')",
            name="claim_kind_values",
        ),
        CheckConstraint(
            "user_statement is null or (length(btrim(user_statement)) between 1 and 500)",
            name="user_statement_bounds",
        ),
        CheckConstraint(
            "length(btrim(structured_reason_code)) >= 1",
            name="reason_code_nonempty",
        ),
        CheckConstraint(
            "consent_version = 'phase7-feedback-consent-v1'",
            name="consent_version_v1",
        ),
        CheckConstraint(
            "consent_scope = 'FEEDBACK_REVIEW_AND_VALIDATION'",
            name="consent_scope_value",
        ),
        CheckConstraint("contract_version = '0.6.0'", name="contract_version_v06"),
        CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="input_sha256_format"),
        ForeignKeyConstraint(
            ["ranking_snapshot_id", "owner_user_id"],
            [
                "personal_ranking_snapshots.ranking_snapshot_id",
                "personal_ranking_snapshots.user_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "ranking_snapshot_id",
                "match_snapshot_id",
                "opportunity_id",
                "opportunity_version",
            ],
            [
                "personal_ranking_items.ranking_snapshot_id",
                "personal_ranking_items.match_snapshot_id",
                "personal_ranking_items.opportunity_id",
                "personal_ranking_items.opportunity_version",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["user_state_snapshot_id", "user_state_version", "owner_user_id"],
            [
                "user_state_snapshots.user_state_snapshot_id",
                "user_state_snapshots.version",
                "user_state_snapshots.user_id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "owner_user_id",
            "input_sha256",
            name="uq_feedback_events_owner_input",
        ),
        UniqueConstraint(
            "feedback_event_id",
            "match_snapshot_id",
            "opportunity_id",
            "opportunity_version",
            name="uq_feedback_events_label_binding",
        ),
    )

    feedback_event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("personal_users.user_id", ondelete="RESTRICT"),
    )
    ranking_snapshot_id: Mapped[UUID] = mapped_column(Uuid)
    match_snapshot_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    user_state_snapshot_id: Mapped[UUID] = mapped_column(Uuid)
    user_state_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(32))
    claim_kind: Mapped[str] = mapped_column(String(40))
    user_statement: Mapped[str | None] = mapped_column(Text)
    structured_reason_code: Mapped[str] = mapped_column(String(64))
    consent_version: Mapped[str] = mapped_column(String(40))
    consent_scope: Mapped[str] = mapped_column(String(48))
    contract_version: Mapped[str] = mapped_column(String(16))
    input_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FeedbackEvidenceLinkModel(Base):
    __tablename__ = "feedback_evidence_links"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(feedback_evidence_link_id) = 7",
            name="feedback_evidence_link_id_uuid7",
        ),
        CheckConstraint("relation in ('SUPPORTS', 'CONTRADICTS')", name="relation_values"),
        CheckConstraint("actor_kind in ('USER', 'REVIEWER')", name="actor_kind_values"),
        CheckConstraint(
            "(actor_kind = 'USER' and actor_user_id is not null and "
            "actor_reviewer_id is null) or (actor_kind = 'REVIEWER' and "
            "actor_user_id is null and actor_reviewer_id is not null)",
            name="actor_identity_shape",
        ),
        CheckConstraint(
            "note is null or (length(btrim(note)) between 1 and 300)",
            name="note_bounds",
        ),
        CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="input_sha256_format"),
        ForeignKeyConstraint(
            ["evidence_ref_id", "document_id"],
            ["evidence_refs.evidence_ref_id", "evidence_refs.document_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "feedback_event_id",
            "input_sha256",
            name="uq_feedback_evidence_links_event_input",
        ),
    )

    feedback_evidence_link_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    feedback_event_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("feedback_events.feedback_event_id", ondelete="RESTRICT"),
    )
    evidence_ref_id: Mapped[UUID] = mapped_column(Uuid)
    document_id: Mapped[UUID] = mapped_column(Uuid)
    relation: Mapped[str] = mapped_column(String(16))
    actor_kind: Mapped[str] = mapped_column(String(16))
    actor_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("personal_users.user_id", ondelete="RESTRICT"),
    )
    actor_reviewer_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("reviewer_accounts.reviewer_id", ondelete="RESTRICT"),
    )
    note: Mapped[str | None] = mapped_column(Text)
    input_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = [
    "FeedbackEventModel",
    "FeedbackEvidenceLinkModel",
    "FeedbackIdempotencyRecordModel",
]
