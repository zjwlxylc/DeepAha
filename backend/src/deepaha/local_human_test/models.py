from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
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


class LocalHumanTestRun(Base):
    __tablename__ = "local_human_test_runs"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(run_id) = 7", name="run_id_uuid7"),
        CheckConstraint("mode in ('LIVE_OFFICIAL', 'OFFICIAL_REPLAY')", name="mode_values"),
        CheckConstraint(
            "status in ('CREATED', 'RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED', 'CANCELLED')",
            name="status_values",
        ),
        CheckConstraint(
            "jsonb_typeof(recipe_ids) = 'array' and jsonb_array_length(recipe_ids) >= 1",
            name="recipe_ids_nonempty_array",
        ),
        CheckConstraint(
            "jsonb_typeof(provider_config_snapshot) = 'object'",
            name="provider_config_snapshot_object",
        ),
        CheckConstraint("jsonb_typeof(budget) = 'object'", name="budget_object"),
        CheckConstraint(
            "length(btrim(idempotency_key)) >= 1",
            name="idempotency_key_nonempty",
        ),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="request_hash_format"),
        CheckConstraint(
            "official_request_count between 0 and 9 and llm_call_count between 0 and 8",
            name="counter_ranges",
        ),
        CheckConstraint(
            "(lease_owner is null and lease_expires_at is null) or "
            "(lease_owner is not null and lease_expires_at is not null)",
            name="lease_state",
        ),
        CheckConstraint(
            "terminal_reason_code is null or terminal_reason_code ~ '^[A-Z][A-Z0-9_]{0,127}$'",
            name="terminal_reason_code_format",
        ),
        CheckConstraint("updated_at >= created_at", name="timestamp_order"),
        CheckConstraint(
            "completed_at is null or completed_at >= created_at",
            name="completion_timestamp_order",
        ),
        UniqueConstraint(
            "created_by_reviewer_id",
            "idempotency_key",
            name="uq_local_human_test_runs_creator_idempotency",
        ),
    )

    run_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    mode: Mapped[str] = mapped_column(String(24))
    recipe_ids: Mapped[list[str]] = mapped_column(JSONB)
    provider_config_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB)
    budget: Mapped[dict[str, object]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32))
    official_request_count: Mapped[int] = mapped_column(Integer, default=0)
    llm_call_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by_reviewer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("reviewer_accounts.reviewer_id", ondelete="RESTRICT"),
    )
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminal_reason_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LocalHumanTestItem(Base):
    __tablename__ = "local_human_test_items"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(item_id) = 7", name="item_id_uuid7"),
        CheckConstraint("length(btrim(recipe_id)) >= 1", name="recipe_id_nonempty"),
        CheckConstraint(
            "status in ('CREATED', 'ACQUIRING', 'BOOTSTRAP_REVIEW', 'EXTRACTING', "
            "'FACT_REVIEW', 'RULE_REVIEW', 'READY_TO_PUBLISH', 'COMPLETED', "
            "'ACQUISITION_REJECTED', 'FAILED_CONFIG', 'PARTIAL_BUDGET_EXHAUSTED', "
            "'UNKNOWN_OUTCOME', 'MODEL_OUTPUT_INVALID', 'EVIDENCE_BINDING_INVALID', "
            "'FAILED', 'CANCELLED')",
            name="status_values",
        ),
        CheckConstraint(
            "error_code is null or error_code ~ '^[A-Z][A-Z0-9_]{0,127}$'",
            name="error_code_format",
        ),
        CheckConstraint("updated_at >= created_at", name="timestamp_order"),
        UniqueConstraint("run_id", "recipe_id", name="uq_local_human_test_items_run_recipe"),
    )

    item_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("local_human_test_runs.run_id", ondelete="CASCADE"),
    )
    recipe_id: Mapped[str] = mapped_column(String(128))
    source_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("sources.source_id", ondelete="RESTRICT"),
    )
    endpoint_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("source_endpoints.endpoint_id", ondelete="RESTRICT"),
    )
    acquisition_evaluation_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("acquisition_evaluations.acquisition_evaluation_id", ondelete="RESTRICT"),
    )
    document_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("documents.document_id", ondelete="RESTRICT"),
    )
    opportunity_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("opportunities.opportunity_id", ondelete="RESTRICT"),
    )
    source_bundle_revision_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("source_bundle_revisions.source_bundle_revision_id", ondelete="RESTRICT"),
    )
    extraction_run_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("extraction_runs.extraction_run_id", ondelete="RESTRICT"),
    )
    model_call_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("p9b_model_calls.model_call_id", ondelete="RESTRICT"),
    )
    verified_fact_set_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("versioned_verified_fact_sets.verified_fact_set_id", ondelete="RESTRICT"),
    )
    status: Mapped[str] = mapped_column(String(40))
    error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LocalHumanTestReviewDecision(Base):
    __tablename__ = "local_human_test_review_decisions"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(decision_id) = 7", name="decision_id_uuid7"),
        CheckConstraint(
            "decision_kind in ('BOOTSTRAP', 'FACT', 'RULE', 'PUBLISH')",
            name="decision_kind_values",
        ),
        CheckConstraint("length(btrim(idempotency_key)) >= 1", name="idempotency_key_nonempty"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="request_hash_format"),
        CheckConstraint("length(btrim(reason)) >= 1", name="reason_nonempty"),
        UniqueConstraint(
            "item_id",
            "decision_kind",
            "idempotency_key",
            name="uq_local_human_test_review_decisions_idempotency",
        ),
    )

    decision_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    item_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("local_human_test_items.item_id", ondelete="CASCADE"),
    )
    decision_kind: Mapped[str] = mapped_column(String(24))
    reviewer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("reviewer_accounts.reviewer_id", ondelete="RESTRICT"),
    )
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = [
    "LocalHumanTestItem",
    "LocalHumanTestReviewDecision",
    "LocalHumanTestRun",
]
