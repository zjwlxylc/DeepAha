from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Computed,
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

STATES = (
    "QUEUED",
    "CREATING",
    "PREPARING",
    "INVESTIGATING",
    "COLLECTING",
    "PENDING_REVIEW",
    "APPROVED",
    "REJECTED",
    "FAILED_PREPARATION",
    "EXECUTION_UNCERTAIN",
    "COLLECTION_RETRYABLE",
    "FAILED_VALIDATION",
    "EXPIRED",
)


class InvestigationTask(Base):
    __tablename__ = "investigation_tasks"
    __table_args__ = (
        UniqueConstraint("created_by", "request_key_hash"),
        ForeignKeyConstraint(
            ["endpoint_id", "source_id"],
            ["source_endpoints.endpoint_id", "source_endpoints.source_id"],
        ),
        CheckConstraint(
            "status in (" + ",".join(repr(x) for x in STATES) + ")", name="status_values"
        ),
        CheckConstraint(
            "status not in ('PENDING_REVIEW','APPROVED','REJECTED') or delivery_hash is not null",
            name="delivery_required",
        ),
        CheckConstraint(
            "status not in ('APPROVED','REJECTED') or reviewer_id is not null",
            name="reviewer_required",
        ),
    )
    task_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_id: Mapped[UUID] = mapped_column(Uuid)
    endpoint_id: Mapped[UUID] = mapped_column(Uuid)
    created_by: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    request_key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, object]] = mapped_column(JSONB)
    source_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB)
    contract: Mapped[dict[str, object]] = mapped_column(JSONB)
    contract_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    execution: Mapped[dict[str, object]] = mapped_column(JSONB)
    runtime_id: Mapped[str | None] = mapped_column(String(256))
    remote_session_id: Mapped[str | None] = mapped_column(String(256))
    lease_owner: Mapped[UUID | None] = mapped_column(Uuid)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))
    delivery_hash: Mapped[str | None] = mapped_column(String(64))
    delivery: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    result_objects: Mapped[dict[str, str]] = mapped_column(JSONB)
    review: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    reviewer_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("reviewer_accounts.reviewer_id")
    )
    review_key_hash: Mapped[str | None] = mapped_column(String(64))
    review_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationMaterial(Base):
    __tablename__ = "investigation_materials"
    task_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_tasks.task_id"), primary_key=True
    )
    material_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    raw_artifact_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("raw_artifacts.artifact_id"))
    metadata_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB)


class InvestigationEvent(Base):
    __tablename__ = "investigation_events"
    task_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_tasks.task_id"), primary_key=True
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationEvidenceCheck(Base):
    """Versioned mechanical receipt; never replaces delivery or human decisions."""

    __tablename__ = "investigation_evidence_checks"
    __table_args__ = (
        UniqueConstraint("task_id", "input_hash", name="uq_investigation_evidence_check_input"),
        CheckConstraint("uuid_extract_version(check_id) = 7", name="check_id_uuid7"),
        CheckConstraint(
            "delivery_hash ~ '^[0-9a-f]{64}$' and input_hash ~ '^[0-9a-f]{64}$' "
            "and result_hash ~ '^[0-9a-f]{64}$'",
            name="hash_formats",
        ),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="payload_object"),
    )
    check_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    task_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("investigation_tasks.task_id"))
    delivery_hash: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))
    result_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    checked_by: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationBinding(Base):
    """Append-only full association snapshots; absent positions stay unmapped."""

    __tablename__ = "investigation_bindings"
    __table_args__ = (
        UniqueConstraint("task_id", "sequence", name="uq_investigation_bindings_sequence"),
        UniqueConstraint(
            "task_id", "reviewer_id", "request_key_hash", name="uq_investigation_bindings_request"
        ),
        ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
        ),
        CheckConstraint("uuid_extract_version(binding_id) = 7", name="binding_id_uuid7"),
        CheckConstraint("sequence >= 1 and opportunity_version >= 1", name="positive_versions"),
        CheckConstraint("jsonb_typeof(request) = 'object'", name="request_object"),
        CheckConstraint(
            "delivery_hash ~ '^[0-9a-f]{64}$' and request_key_hash ~ '^[0-9a-f]{64}$' "
            "and request_hash ~ '^[0-9a-f]{64}$'",
            name="hash_formats",
        ),
    )
    binding_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    task_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("investigation_tasks.task_id"))
    sequence: Mapped[int] = mapped_column(Integer)
    delivery_hash: Mapped[str] = mapped_column(String(64))
    source_bundle_revision_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("source_bundle_revisions.source_bundle_revision_id")
    )
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    request_key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationGroupBinding(Base):
    """Complete source membership attached to a separate, stable GROUP identity."""

    __tablename__ = "investigation_group_bindings"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "source_entity_id", "sequence", name="uq_investigation_group_sequence"
        ),
        UniqueConstraint(
            "binding_id", "source_entity_id", name="uq_investigation_group_binding_entity"
        ),
        CheckConstraint("uuid_extract_version(group_binding_id) = 7", name="id_uuid7"),
        CheckConstraint("sequence >= 1", name="positive_sequence"),
        CheckConstraint("source_hash ~ '^[0-9a-f]{64}$'", name="hash_format"),
        CheckConstraint("jsonb_typeof(source) = 'object'", name="source_object"),
    )
    group_binding_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    task_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("investigation_tasks.task_id"))
    binding_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("investigation_bindings.binding_id"))
    source_entity_id: Mapped[str] = mapped_column(String(256))
    sequence: Mapped[int] = mapped_column(Integer)
    unit_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("opportunity_units.opportunity_unit_id"))
    unit_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("opportunity_unit_versions.opportunity_unit_version_id")
    )
    source: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source_hash: Mapped[str] = mapped_column(String(64))
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationFactPreparation(Base):
    """Immutable bridge receipt; candidate/fact lifecycle remains in P9-B."""

    __tablename__ = "investigation_fact_preparations"
    __table_args__ = (
        UniqueConstraint(
            "binding_id",
            "check_id",
            "mapping_version",
            name="uq_investigation_fact_preparation_version",
        ),
    )
    preparation_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    task_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("investigation_tasks.task_id"))
    binding_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("investigation_bindings.binding_id"))
    check_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_evidence_checks.check_id")
    )
    mapping_version: Mapped[str] = mapped_column(String(128))
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    result: Mapped[dict[str, object]] = mapped_column(JSONB)
    result_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationGroupFactPreparation(Base):
    __tablename__ = "investigation_group_fact_preparations"
    __table_args__ = (
        UniqueConstraint(
            "group_binding_id", "check_id", "mapping_version", name="uq_group_fact_preparation"
        ),
    )
    preparation_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    group_binding_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_group_bindings.group_binding_id")
    )
    check_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_evidence_checks.check_id")
    )
    mapping_version: Mapped[str] = mapped_column(String(128))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result_hash: Mapped[str] = mapped_column(String(64))
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationGroupFactAction(Base):
    __tablename__ = "investigation_group_fact_actions"
    __table_args__ = (
        UniqueConstraint(
            "preparation_id", "reviewer_id", "request_key_hash", name="uq_group_fact_request"
        ),
        UniqueConstraint("decision_id", name="uq_group_fact_decision"),
        CheckConstraint(
            "(kind = 'DECISION' and candidate_id is not null "
            "and decision_id is not null and fact_set_id is null) or "
            "(kind = 'PROMOTION' and candidate_id is null "
            "and decision_id is null and fact_set_id is not null)",
            name="action_shape",
        ),
    )
    action_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    preparation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_group_fact_preparations.preparation_id")
    )
    kind: Mapped[str] = mapped_column(String(16))
    candidate_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("extraction_candidates.candidate_id")
    )
    decision_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("fact_verification_decisions.decision_id")
    )
    fact_set_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("versioned_verified_fact_sets.verified_fact_set_id")
    )
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    request_key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationFactAction(Base):
    __tablename__ = "investigation_fact_actions"
    __table_args__ = (
        UniqueConstraint("decision_id", name="uq_investigation_fact_action_decision"),
        UniqueConstraint(
            "preparation_id",
            "reviewer_id",
            "request_key_hash",
            name="uq_investigation_fact_action_request",
        ),
        CheckConstraint(
            "(kind = 'DECISION' and candidate_id is not null "
            "and decision_id is not null and fact_set_id is null) or "
            "(kind = 'PROMOTION' and candidate_id is null "
            "and decision_id is null and fact_set_id is not null)",
            name="action_shape",
        ),
    )
    action_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    preparation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_fact_preparations.preparation_id")
    )
    kind: Mapped[str] = mapped_column(String(16))
    entity_id: Mapped[str] = mapped_column(String(256))
    candidate_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("extraction_candidates.candidate_id")
    )
    decision_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("fact_verification_decisions.decision_id")
    )
    fact_set_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("versioned_verified_fact_sets.verified_fact_set_id")
    )
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    request_key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationRulePreparation(Base):
    __tablename__ = "investigation_rule_preparations"
    __table_args__ = (
        UniqueConstraint(
            "fact_preparation_id",
            "entity_id",
            "fact_set_id",
            "compiler_version",
            name="uq_investigation_rule_preparation_version",
        ),
    )
    rule_preparation_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    fact_preparation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_fact_preparations.preparation_id")
    )
    entity_id: Mapped[str] = mapped_column(String(256))
    fact_set_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("versioned_verified_fact_sets.verified_fact_set_id")
    )
    compiler_version: Mapped[str] = mapped_column(String(128))
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    result: Mapped[dict[str, object]] = mapped_column(JSONB)
    result_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationRuleDecision(Base):
    __tablename__ = "investigation_rule_decisions"
    __table_args__ = (
        UniqueConstraint(
            "rule_preparation_id",
            "reviewer_id",
            "request_key_hash",
            name="uq_investigation_rule_decision_request",
        ),
        ForeignKeyConstraint(
            ["decision_id", "rule_candidate_id"],
            [
                "p9b_rule_approval_decisions.rule_approval_decision_id",
                "p9b_rule_approval_decisions.rule_candidate_id",
            ],
        ),
    )
    decision_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    rule_preparation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_rule_preparations.rule_preparation_id")
    )
    rule_candidate_id: Mapped[UUID] = mapped_column(Uuid)
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    request_key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationGroupRulePreparation(Base):
    __tablename__ = "investigation_group_rule_preparations"
    __table_args__ = (
        UniqueConstraint(
            "fact_preparation_id",
            "fact_set_id",
            "compiler_version",
            name="uq_group_rule_preparation",
        ),
    )
    preparation_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    fact_preparation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_group_fact_preparations.preparation_id")
    )
    fact_set_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("versioned_verified_fact_sets.verified_fact_set_id")
    )
    compiler_version: Mapped[str] = mapped_column(String(128))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result_hash: Mapped[str] = mapped_column(String(64))
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationGroupRuleDecision(Base):
    __tablename__ = "investigation_group_rule_decisions"
    __table_args__ = (
        UniqueConstraint(
            "preparation_id", "reviewer_id", "request_key_hash", name="uq_group_rule_request"
        ),
        ForeignKeyConstraint(
            ["decision_id", "rule_candidate_id"],
            [
                "p9b_rule_approval_decisions.rule_approval_decision_id",
                "p9b_rule_approval_decisions.rule_candidate_id",
            ],
        ),
    )
    decision_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    preparation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_group_rule_preparations.preparation_id")
    )
    rule_candidate_id: Mapped[UUID] = mapped_column(Uuid)
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    request_key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationUnitPlan(Base):
    __tablename__ = "investigation_unit_plans"
    __table_args__ = (
        UniqueConstraint(
            "rule_preparation_id",
            "contract_version",
            "adapter_version",
            name="uq_investigation_unit_plan_version",
        ),
    )
    plan_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    rule_preparation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_rule_preparations.rule_preparation_id")
    )
    unit_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("opportunity_unit_versions.opportunity_unit_version_id")
    )
    contract_version: Mapped[str] = mapped_column(String(64))
    adapter_version: Mapped[str] = mapped_column(String(128))
    plan: Mapped[dict[str, object]] = mapped_column(JSONB)
    plan_hash: Mapped[str] = mapped_column(String(64))
    context: Mapped[dict[str, object]] = mapped_column(JSONB)
    context_hash: Mapped[str] = mapped_column(String(64))
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationRuleApplicability(Base):
    __tablename__ = "investigation_rule_applicability"
    __table_args__ = (
        UniqueConstraint(
            "target_plan_id",
            "source_rule_candidate_id",
            "sequence",
            name="uq_investigation_applicability_sequence",
        ),
        UniqueConstraint(
            "target_plan_id",
            "reviewer_id",
            "request_key_hash",
            name="uq_investigation_applicability_request",
        ),
    )
    decision_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    target_plan_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_unit_plans.plan_id")
    )
    source_rule_preparation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_rule_preparations.rule_preparation_id")
    )
    source_rule_candidate_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("p9b_rule_candidates.rule_candidate_id")
    )
    source_rule_approval_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_rule_decisions.decision_id")
    )
    previous_decision_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("investigation_rule_applicability.decision_id")
    )
    sequence: Mapped[int] = mapped_column(Integer)
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    request_key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, object]] = mapped_column(JSONB)
    context: Mapped[dict[str, object]] = mapped_column(JSONB)
    context_hash: Mapped[str] = mapped_column(String(64))
    evidence_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    evidence_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationGroupApplicability(Base):
    __tablename__ = "investigation_group_applicability"
    __table_args__ = (
        UniqueConstraint(
            "target_plan_id",
            "source_rule_candidate_id",
            "sequence",
            name="uq_group_applicability_sequence",
        ),
        UniqueConstraint(
            "target_plan_id",
            "reviewer_id",
            "request_key_hash",
            name="uq_group_applicability_request",
        ),
    )
    decision_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    target_plan_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_unit_plans.plan_id")
    )
    source_rule_preparation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_group_rule_preparations.preparation_id")
    )
    source_rule_candidate_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("p9b_rule_candidates.rule_candidate_id")
    )
    source_rule_approval_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_group_rule_decisions.decision_id")
    )
    previous_decision_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("investigation_group_applicability.decision_id")
    )
    sequence: Mapped[int] = mapped_column(Integer)
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    request_key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, object]] = mapped_column(JSONB)
    context: Mapped[dict[str, object]] = mapped_column(JSONB)
    context_hash: Mapped[str] = mapped_column(String(64))
    evidence_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    evidence_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationAnnouncementSnapshot(Base):
    __tablename__ = "investigation_announcement_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "base_plan_id",
            "contract_version",
            "adapter_version",
            "dependencies_hash",
            name="uq_investigation_announcement_snapshot_inputs",
        ),
    )
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    base_plan_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("investigation_unit_plans.plan_id"))
    unit_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("opportunity_unit_versions.opportunity_unit_version_id")
    )
    contract_version: Mapped[str] = mapped_column(String(64))
    adapter_version: Mapped[str] = mapped_column(String(128))
    dependencies: Mapped[dict[str, object]] = mapped_column(JSONB)
    dependencies_hash: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationRelationDecision(Base):
    __tablename__ = "investigation_relation_decisions"
    __table_args__ = (
        UniqueConstraint("proposal_id", "sequence", name="uq_relation_decision_sequence"),
        UniqueConstraint(
            "proposal_id", "reviewer_id", "request_key_hash", name="uq_relation_decision_request"
        ),
        CheckConstraint(
            "payload_sha256 = encode(sha256(convert_to(payload_text,'UTF8')),'hex')",
            name="payload_bytes",
        ),
    )
    decision_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    proposal_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_relation_proposals.proposal_id")
    )
    previous_decision_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("investigation_relation_decisions.decision_id")
    )
    sequence: Mapped[int] = mapped_column(Integer)
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    request_key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, Any]] = mapped_column(JSONB)
    payload_text: Mapped[str] = mapped_column(Text)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    projection: Mapped[dict[str, Any]] = mapped_column(
        JSONB, Computed("payload_text::jsonb", persisted=True)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationRelationProposal(Base):
    __tablename__ = "investigation_relation_proposals"
    __table_args__ = (
        UniqueConstraint(
            "target_plan_id", "producer_id", "request_key_hash", name="uq_relation_proposal_request"
        ),
        CheckConstraint(
            "storage_version = 'adjudication-frozen-json/1.0.0'",
            name="storage_version",
        ),
        CheckConstraint(
            "payload_sha256 = encode(sha256(convert_to(payload_text,'UTF8')),'hex')",
            name="payload_bytes",
        ),
    )
    proposal_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    task_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("investigation_tasks.task_id"))
    target_plan_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("investigation_unit_plans.plan_id")
    )
    producer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("reviewer_accounts.reviewer_id"))
    request_key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, Any]] = mapped_column(JSONB)
    storage_version: Mapped[str] = mapped_column(String(64))
    payload_text: Mapped[str] = mapped_column(Text)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    projection: Mapped[dict[str, Any]] = mapped_column(
        JSONB, Computed("payload_text::jsonb", persisted=True)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
