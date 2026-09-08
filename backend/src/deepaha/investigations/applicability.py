"""Independent announcement-to-unit scope records, never an eligibility approval."""

from copy import deepcopy
from hashlib import sha256
from typing import Any, Literal, Self, cast
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from deepaha.contracts.evidence_anchor import READER_BLOCK_CONTRACT
from deepaha.documents.models import DocumentBlock
from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.models import (
    InvestigationFactPreparation,
    InvestigationMaterial,
    InvestigationRuleApplicability,
    InvestigationRulePreparation,
    InvestigationUnitPlan,
)
from deepaha.investigations.rule_contracts import MaterializeInvestigationUnitPlan
from deepaha.investigations.rules import RULE_BRIDGE_VERSION, _context, reviewed_rule
from deepaha.investigations.store import InvestigationStore
from deepaha.investigations.unit_snapshots import (
    _build,
    _check_facts,
    _checked_view,
    _final_decisions,
)
from deepaha.local_human_test.review import require_human_fact_reviewer, validate_idempotency_key
from deepaha.p9b.models import RuleApprovalDecisionModel, SourceBundleMember
from deepaha.review.auth import ReviewerPrincipal

APPLICABILITY_VERSION = "announcement-rule-applicability/1.0.0"


class ApplicabilityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    member_id: UUID
    block_id: UUID
    quote: str = Field(min_length=1, max_length=20000)


class DecideRuleApplicability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    target_plan_id: UUID
    source_rule_preparation_id: UUID
    source_rule_candidate_id: UUID
    context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    previous_decision_id: UUID | None
    outcome: Literal["APPLIES", "DOES_NOT_APPLY", "NEEDS_ADJUDICATION"]
    evidence: tuple[ApplicabilityEvidence, ...] = Field(default=(), max_length=20)
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def require_evidence(self) -> Self:
        if not self.reason.strip() or any(not e.quote.strip() for e in self.evidence):
            raise ValueError("review reason and supplied quotes must not be blank")
        if self.outcome != "NEEDS_ADJUDICATION" and not self.evidence:
            raise ValueError("resolved applicability requires official evidence")
        keys = [(e.member_id, e.block_id, e.quote) for e in self.evidence]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate applicability evidence")
        return self


def _command(session: Session, task_id: UUID, prep_id: UUID) -> MaterializeInvestigationUnitPlan:
    prep = session.get(InvestigationRulePreparation, prep_id)
    facts = session.get(InvestigationFactPreparation, prep.fact_preparation_id) if prep else None
    if prep is None or facts is None or facts.task_id != task_id:
        raise InvestigationError("RULE_APPLICABILITY_SOURCE_NOT_FOUND")
    return MaterializeInvestigationUnitPlan(
        delivery_hash=str(prep.result["delivery_hash"]),
        binding_id=facts.binding_id,
        check_id=facts.check_id,
        fact_preparation_id=facts.preparation_id,
        entity_id=prep.entity_id,
        fact_set_id=prep.fact_set_id,
        rule_preparation_id=prep_id,
    )


def _review_context(
    store: InvestigationStore,
    session: Session,
    task_id: UUID,
    plan_id: UUID,
    source_id: UUID,
    candidate_id: UUID,
) -> tuple[dict[str, Any], dict[str, Any]]:
    store._get(session, task_id, lock=True)
    record = session.get(InvestigationUnitPlan, plan_id)
    if record is None:
        raise InvestigationError("UNIT_PLAN_NOT_FOUND")
    target_command = _command(session, task_id, record.rule_preparation_id)
    plan, context = _build(store, session, task_id, target_command, plan_id)
    _checked_view(record, plan, context)
    source_command = _command(session, task_id, source_id)
    _, binding, facts, fact_set, target = _context(store, session, task_id, source_command)
    prep = session.get(InvestigationRulePreparation, source_id)
    assert prep is not None
    if (
        prep.compiler_version != RULE_BRIDGE_VERSION
        or digest(prep.result) != prep.result_hash
        or prep.result["target"] != target
        or prep.result["source_rows"] != facts.result["rows"]
        or prep.result["fact_preparation_hash"] != facts.result_hash
        or prep.result["check_id"] != str(source_command.check_id)
        or target["target_scope"] != "OPPORTUNITY"
        or target["entity_kind"] != "announcement"
        or source_command.fact_preparation_id != target_command.fact_preparation_id
        or str(binding.binding_id) != context["binding_id"]
        or str(binding.opportunity_id) != str(plan.target.opportunity_id)
        or binding.opportunity_version != plan.target.opportunity_version
    ):
        raise InvestigationError("RULE_APPLICABILITY_SOURCE_CONFLICT")
    rows = cast(list[dict[str, Any]], prep.result["rows"])
    _check_facts(session, rows, fact_set.verified_fact_set_id)
    decisions = _final_decisions(session, prep, rows, source_command, target)
    decision = decisions.get(str(candidate_id))
    row = next((r for r in rows if r["rule_candidate_id"] == str(candidate_id)), None)
    if decision is None or row is None or decision.request["decision"] != "APPROVE":
        raise InvestigationError("RULE_APPLICABILITY_SOURCE_NOT_APPROVED")
    approval = session.get(RuleApprovalDecisionModel, decision.decision_id)
    assert approval is not None
    if approval.decided_at > store.clock():
        raise InvestigationError("RULE_APPLICABILITY_APPROVAL_NOT_CURRENT")
    rule = reviewed_rule(row, cast(dict[str, Any], decision.request), target)
    target_prep = session.get(InvestigationRulePreparation, record.rule_preparation_id)
    assert target_prep is not None
    review_context = {
        "contract_version": APPLICABILITY_VERSION,
        "task_id": str(task_id),
        "target_plan_id": str(plan_id),
        "target_plan_hash": record.plan_hash,
        "target_plan_context_hash": record.context_hash,
        "target": plan.target.model_dump(mode="json"),
        "binding_id": str(binding.binding_id),
        "check_id": str(facts.check_id),
        "source_bundle_revision_id": str(binding.source_bundle_revision_id),
        "source_rule_preparation_id": str(source_id),
        "source_rule_preparation_hash": prep.result_hash,
        "source_rule_candidate_id": str(candidate_id),
        "source_rule_approval_id": str(decision.decision_id),
        "source_rule_approval_hash": decision.request_hash,
        "source_rule_sha256": digest(rule.model_dump(mode="json")),
        "source_fact_preparation_id": str(facts.preparation_id),
        "source_fact_preparation_hash": facts.result_hash,
        "source_fact_set_id": str(fact_set.verified_fact_set_id),
        "source_fact_set_version": fact_set.version,
    }
    return review_context, {
        "target_label": cast(dict[str, Any], target_prep.result["target"])["name"],
        "source_label": target["name"],
        "source_rule": rule.model_dump(mode="json"),
    }


def _blocks(session: Session, context: dict[str, Any]) -> Any:
    return (
        select(SourceBundleMember, DocumentBlock)
        .join(DocumentBlock, DocumentBlock.document_id == SourceBundleMember.document_id)
        .where(
            SourceBundleMember.source_bundle_revision_id
            == UUID(context["source_bundle_revision_id"]),
            SourceBundleMember.wma_task_id == UUID(context["task_id"]),
            SourceBundleMember.provenance_kind == "DIRECT_WMA",
            DocumentBlock.parse_contract_version == READER_BLOCK_CONTRACT,
        )
    )


def _bound_evidence(
    session: Session, context: dict[str, Any], evidence: tuple[ApplicabilityEvidence, ...]
) -> list[dict[str, Any]]:
    result = []
    for item in evidence:
        pair = session.execute(
            _blocks(session, context).where(
                SourceBundleMember.source_bundle_member_id == item.member_id,
                DocumentBlock.block_id == item.block_id,
            )
        ).one_or_none()
        if pair is None or item.quote not in pair[1].canonical_text_or_value:
            raise InvestigationError("RULE_APPLICABILITY_EVIDENCE_MISMATCH")
        member, block = pair
        result.append(
            {
                "member_id": str(member.source_bundle_member_id),
                "block_id": str(block.block_id),
                "quote": item.quote,
                "document_id": str(block.document_id),
                "material_id": member.wma_material_id,
                "source_url": _material_url(session, context, member),
                "evidence_ref_id": str(block.evidence_ref_id),
                "block_hash": block.block_hash,
                "binding_hash": block.evidence_binding_hash,
                "locator": block.structural_locator,
            }
        )
    return result


def _material_url(session: Session, context: dict[str, Any], member: SourceBundleMember) -> str:
    material = session.get(
        InvestigationMaterial, (UUID(context["task_id"]), member.wma_material_id)
    )
    if material is None:
        raise InvestigationError("RULE_APPLICABILITY_EVIDENCE_MISMATCH")
    return str(material.metadata_snapshot["url"])


def _describe(
    session: Session, record: InvestigationRuleApplicability, context: dict[str, Any]
) -> dict[str, Any]:
    try:
        request = DecideRuleApplicability.model_validate(record.request)
    except ValidationError as error:
        raise InvestigationError("RULE_APPLICABILITY_INTEGRITY_FAILED") from error
    evidence = _bound_evidence(session, context, request.evidence)
    if (
        record.context != context
        or record.context_hash != digest(context)
        or record.request_hash != digest(record.request)
        or request.context_hash != record.context_hash
        or record.target_plan_id != request.target_plan_id
        or record.source_rule_preparation_id != request.source_rule_preparation_id
        or record.source_rule_candidate_id != request.source_rule_candidate_id
        or record.previous_decision_id != request.previous_decision_id
        or str(record.source_rule_approval_id) != context["source_rule_approval_id"]
        or record.evidence_snapshot != evidence
        or record.evidence_hash != digest(evidence)
    ):
        raise InvestigationError("RULE_APPLICABILITY_INTEGRITY_FAILED")
    return {
        "decision_id": str(record.decision_id),
        "sequence": record.sequence,
        "request": deepcopy(record.request),
        "request_hash": record.request_hash,
        "context": deepcopy(record.context),
        "context_hash": record.context_hash,
        "evidence_snapshot": deepcopy(record.evidence_snapshot),
        "evidence_hash": record.evidence_hash,
        "reviewer_id": str(record.reviewer_id),
        "created_at": record.created_at.isoformat(),
    }


def _history(session: Session, context: dict[str, Any]) -> list[InvestigationRuleApplicability]:
    records = list(
        session.scalars(
            select(InvestigationRuleApplicability)
            .where(
                InvestigationRuleApplicability.target_plan_id == UUID(context["target_plan_id"]),
                InvestigationRuleApplicability.source_rule_candidate_id
                == UUID(context["source_rule_candidate_id"]),
            )
            .order_by(InvestigationRuleApplicability.sequence)
        )
    )
    previous = None
    for sequence, record in enumerate(records, 1):
        if record.sequence != sequence or record.previous_decision_id != previous:
            raise InvestigationError("RULE_APPLICABILITY_HISTORY_CONFLICT")
        _describe(session, record, context)
        previous = record.decision_id
    return records


def read_rule_applicability(
    store: InvestigationStore,
    task_id: UUID,
    plan_id: UUID,
    source_id: UUID,
    candidate_id: UUID,
    principal: ReviewerPrincipal,
    *,
    after: str | None = None,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        context, view = _review_context(store, session, task_id, plan_id, source_id, candidate_id)
        history = [_describe(session, r, context) for r in _history(session, context)]
        query = _blocks(session, context)
        if after is not None:
            try:
                block_after, member_after = (UUID(part) for part in after.split(":"))
            except ValueError as error:
                raise InvestigationError("RULE_APPLICABILITY_CURSOR_INVALID") from error
            query = query.where(
                tuple_(DocumentBlock.block_id, SourceBundleMember.source_bundle_member_id)
                > (block_after, member_after)
            )
        blocks = list(
            session.execute(
                query.order_by(
                    DocumentBlock.block_id, SourceBundleMember.source_bundle_member_id
                ).limit(51)
            )
        )
        return view | {
            "scope": "RULE_APPLICABILITY_REVIEW_ONLY",
            "context": context,
            "context_hash": digest(context),
            "latest": history[-1] if history else None,
            "history": history,
            "evidence_options": [
                {
                    "member_id": str(m.source_bundle_member_id),
                    "block_id": str(b.block_id),
                    "material_id": m.wma_material_id,
                    "source_url": _material_url(session, context, m),
                    "document_id": str(b.document_id),
                    "evidence_ref_id": str(b.evidence_ref_id),
                    "text": b.canonical_text_or_value,
                    "locator": b.structural_locator,
                }
                for m, b in blocks[:50]
            ],
            "next_cursor": (
                f"{blocks[49][1].block_id}:{blocks[49][0].source_bundle_member_id}"
                if len(blocks) > 50
                else None
            ),
        }


def save_rule_applicability(
    store: InvestigationStore,
    task_id: UUID,
    command: DecideRuleApplicability,
    principal: ReviewerPrincipal,
    key: str,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    key_hash = sha256(validate_idempotency_key(key).encode()).hexdigest()
    request = command.model_dump(mode="json")
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        context, _ = _review_context(
            store,
            session,
            task_id,
            command.target_plan_id,
            command.source_rule_preparation_id,
            command.source_rule_candidate_id,
        )
        if command.context_hash != digest(context):
            raise InvestigationError("RULE_APPLICABILITY_CONTEXT_CHANGED")
        existing = session.scalar(
            select(InvestigationRuleApplicability).where(
                InvestigationRuleApplicability.target_plan_id == command.target_plan_id,
                InvestigationRuleApplicability.reviewer_id == principal.reviewer_id,
                InvestigationRuleApplicability.request_key_hash == key_hash,
            )
        )
        records = _history(session, context)
        if existing is not None:
            if existing.request_hash != digest(request):
                raise InvestigationError("RULE_APPLICABILITY_IDEMPOTENCY_CONFLICT")
            return _describe(session, existing, context)
        previous = records[-1] if records else None
        if command.previous_decision_id != (previous.decision_id if previous else None):
            raise InvestigationError("RULE_APPLICABILITY_PREDECESSOR_CHANGED")
        evidence = _bound_evidence(session, context, command.evidence)
        record = InvestigationRuleApplicability(
            decision_id=uuid7(),
            target_plan_id=command.target_plan_id,
            source_rule_preparation_id=command.source_rule_preparation_id,
            source_rule_candidate_id=command.source_rule_candidate_id,
            source_rule_approval_id=UUID(context["source_rule_approval_id"]),
            previous_decision_id=command.previous_decision_id,
            sequence=len(records) + 1,
            reviewer_id=principal.reviewer_id,
            request_key_hash=key_hash,
            request=request,
            request_hash=digest(request),
            context=deepcopy(context),
            context_hash=digest(context),
            evidence_snapshot=evidence,
            evidence_hash=digest(evidence),
            created_at=store.clock(),
        )
        session.add(record)
        session.flush()
        session.refresh(record)
        return _describe(session, record, context)
