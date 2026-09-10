"""Persist exact GROUP rule candidates and independent evidence assessments."""

from hashlib import sha256
from typing import Any
from uuid import UUID, uuid7

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from deepaha.contracts.phase9b import RuleApprovalDecisionSchemaV08, RuleCandidateSchemaV08
from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.group_rule_review_contracts import (
    GROUP_RULE_REVIEW_VERSION,
    DecideGroupRule,
    GroupRuleReviewRecord,
    PrepareGroupRules,
)
from deepaha.investigations.group_rules import build_group_rule_preview
from deepaha.investigations.models import (
    InvestigationGroupRuleDecision,
    InvestigationGroupRulePreparation,
)
from deepaha.investigations.rules import reviewed_rule
from deepaha.investigations.store import InvestigationStore
from deepaha.local_human_test.review import require_human_fact_reviewer, validate_idempotency_key
from deepaha.p9b.models import RuleApprovalDecisionModel
from deepaha.p9b.rules import RulePromotionService
from deepaha.review.auth import ReviewerPrincipal
from deepaha.rules.compiler import compile_rule_graph
from deepaha.rules.types import RuleCompileError


def _target(preview: dict[str, Any]) -> dict[str, Any]:
    data = preview["result"]
    source = data["fact_review"]["result"]["group_source"]["source"]
    return {
        "target_scope": "UNIT",
        "opportunity_id": source["opportunity_id"],
        "opportunity_version": source["opportunity_version"],
        "opportunity_unit_id": data["target"]["unit_id"],
        "opportunity_unit_version_id": data["target"]["unit_version_id"],
    }


def _validate(
    store: InvestigationStore, session: Session, prep: InvestigationGroupRulePreparation
) -> None:
    if not session.scalar(
        text("SELECT investigation_group_rule_materialization_valid(:id,:now)"),
        {"id": prep.preparation_id, "now": store.clock()},
    ):
        raise InvestigationError("GROUP_RULE_MATERIALIZATION_INTEGRITY_FAILED")


def _checked(
    store: InvestigationStore, session: Session, task: UUID, prep_id: UUID
) -> InvestigationGroupRulePreparation:
    prep = session.get(InvestigationGroupRulePreparation, prep_id)
    if prep is None:
        raise InvestigationError("GROUP_RULE_PREPARATION_NOT_FOUND")
    current = build_group_rule_preview(store, session, task, prep.fact_preparation_id)
    if (
        prep.result["preview"] != current
        or prep.compiler_version != GROUP_RULE_REVIEW_VERSION
        or digest(prep.result) != prep.result_hash
        or prep.created_at > store.clock()
    ):
        raise InvestigationError("GROUP_RULE_PREPARATION_CONFLICT")
    _validate(store, session, prep)
    return prep


def _view(
    store: InvestigationStore, session: Session, prep: InvestigationGroupRulePreparation
) -> dict[str, Any]:
    decisions, history = {}, []
    rows = list(
        session.scalars(
            select(InvestigationGroupRuleDecision)
            .where(InvestigationGroupRuleDecision.preparation_id == prep.preparation_id)
            .order_by(
                InvestigationGroupRuleDecision.created_at,
                InvestigationGroupRuleDecision.decision_id,
            )
        )
    )
    candidate_ids = [
        UUID(r["rule_candidate_id"]) for r in prep.result["rows"] if r["rule_candidate_id"]
    ]
    actual = list(
        session.scalars(
            select(RuleApprovalDecisionModel).where(
                RuleApprovalDecisionModel.rule_candidate_id.in_(candidate_ids)
            )
        )
    )
    if {r.decision_id for r in rows} != {r.rule_approval_decision_id for r in actual}:
        raise InvestigationError("GROUP_RULE_DECISION_INTEGRITY_FAILED")
    for row in rows:
        try:
            request = DecideGroupRule.model_validate(row.request)
        except ValidationError as error:
            raise InvestigationError("GROUP_RULE_DECISION_INTEGRITY_FAILED") from error
        approval = next(a for a in actual if a.rule_approval_decision_id == row.decision_id)
        if (
            row.request_hash != digest(row.request)
            or row.created_at > store.clock()
            or approval.decided_at != row.created_at
            or approval.decision != row.request["decision"]
            or approval.approver_identity != f"human:{row.reviewer_id}"
            or approval.policy_version != GROUP_RULE_REVIEW_VERSION
            or approval.approval_method != "HUMAN"
            or approval.reason_code != f"HUMAN_{request.decision}"
            or request.expected_preparation_hash != prep.result_hash
            or request.rule_candidate_id != row.rule_candidate_id
        ):
            raise InvestigationError("GROUP_RULE_DECISION_INTEGRITY_FAILED")
        if request.decision == "APPROVE":
            _compile_approved(prep, request.model_dump(mode="json"))
        item = {
            "decision_id": str(row.decision_id),
            "rule_candidate_id": str(row.rule_candidate_id),
            "decision": approval.decision,
            "reason": row.request["reason"],
            "evidence": row.request["evidence"],
            "reviewer_id": str(row.reviewer_id),
            "created_at": row.created_at.isoformat(),
        }
        history.append(item)
        decisions[str(row.rule_candidate_id)] = item
    _validate(store, session, prep)
    return GroupRuleReviewRecord.model_validate(
        {
            "preparation_id": prep.preparation_id,
            "fact_preparation_id": prep.fact_preparation_id,
            "fact_set_id": prep.fact_set_id,
            "result": prep.result,
            "result_hash": prep.result_hash,
            "reviewer_id": prep.reviewer_id,
            "created_at": prep.created_at,
            "decisions": decisions,
            "history": history,
        }
    ).model_dump(mode="json")


def _compile_approved(prep: InvestigationGroupRulePreparation, request: dict[str, Any]) -> None:
    row = next(
        r for r in prep.result["rows"] if r["rule_candidate_id"] == request["rule_candidate_id"]
    )
    source = next(
        r
        for r in prep.result["preview"]["result"]["fact_review"]["result"]["rows"]
        if r["source_index"] == row["source_index"]
    )
    evidence = [
        {
            "evidence_ref_id": e["binding"]["evidence_ref_id"],
            "document_id": e["binding"]["document_id"],
        }
        for e in source["evidence"]
    ]
    try:
        rule = reviewed_rule(
            row | {"payload": row["proposed_rule_payload"], "evidence": evidence},
            request,
            _target(prep.result["preview"]),
        )
        compile_rule_graph((rule,), (rule.rule_id,))
    except (RuleCompileError, ValidationError) as error:
        raise InvestigationError("GROUP_RULE_NOT_EXECUTABLE") from error


def prepare_group_rule_review(
    store: InvestigationStore,
    task: UUID,
    fact_id: UUID,
    command: PrepareGroupRules,
    principal: ReviewerPrincipal,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        preview = build_group_rule_preview(store, session, task, fact_id)
        saved = preview["result"]["fact_review"]["fact_set"]
        if preview["result_hash"] != command.expected_preview_hash:
            raise InvestigationError("GROUP_RULE_PREVIEW_CHANGED")
        if not saved:
            raise InvestigationError("GROUP_RULE_FACT_SET_REQUIRED")
        set_id = UUID(saved["fact_set_id"])
        existing = session.scalar(
            select(InvestigationGroupRulePreparation).where(
                InvestigationGroupRulePreparation.fact_preparation_id == fact_id,
                InvestigationGroupRulePreparation.fact_set_id == set_id,
                InvestigationGroupRulePreparation.compiler_version == GROUP_RULE_REVIEW_VERSION,
            )
        )
        if existing:
            return _view(store, session, _checked(store, session, task, existing.preparation_id))
        result: dict[str, Any] = {
            "contract_version": GROUP_RULE_REVIEW_VERSION,
            "scope": "GROUP_RULE_REVIEW_ONLY",
            "preview": preview,
            "rows": [],
        }
        now = store.clock()
        for row in preview["result"]["rows"]:
            candidate_id = None
            if row["proposed_rule_payload"] is not None:
                candidate_id = uuid7()
                RulePromotionService(session).propose(
                    RuleCandidateSchemaV08.model_validate(
                        _target(preview)
                        | {
                            "rule_candidate_id": candidate_id,
                            "verified_fact_ids": [row["verified_fact_id"]],
                            "rule_type": "ATOMIC_QUALIFICATION",
                            "proposed_rule_payload": row["proposed_rule_payload"],
                            "evidence_ref_ids": row["evidence_ref_ids"],
                            "compiler_version": GROUP_RULE_REVIEW_VERSION,
                            "producer_identity": f"component:{GROUP_RULE_REVIEW_VERSION}",
                            "status": "PROPOSED",
                            "created_at": now,
                        }
                    ),
                    verified_fact_set_id=set_id,
                )
            result["rows"].append(
                row | {"rule_candidate_id": str(candidate_id) if candidate_id else None}
            )
        prep = InvestigationGroupRulePreparation(
            preparation_id=uuid7(),
            fact_preparation_id=fact_id,
            fact_set_id=set_id,
            compiler_version=GROUP_RULE_REVIEW_VERSION,
            result=result,
            result_hash=digest(result),
            reviewer_id=principal.reviewer_id,
            created_at=now,
        )
        session.add(prep)
        session.flush()
        return _view(store, session, _checked(store, session, task, prep.preparation_id))


def load_group_rule_review(
    store: InvestigationStore, task: UUID, prep_id: UUID, principal: ReviewerPrincipal
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        return _view(store, session, _checked(store, session, task, prep_id))


def decide_group_rule(
    store: InvestigationStore,
    task: UUID,
    prep_id: UUID,
    command: DecideGroupRule,
    principal: ReviewerPrincipal,
    key: str,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    key_hash = sha256(validate_idempotency_key(key).encode()).hexdigest()
    request = command.model_dump(mode="json")
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        prep = _checked(store, session, task, prep_id)
        current = _view(store, session, prep)
        if command.expected_preparation_hash != prep.result_hash or not command.reason.strip():
            raise InvestigationError("GROUP_RULE_PREPARATION_CONFLICT")
        existing = session.scalar(
            select(InvestigationGroupRuleDecision).where(
                InvestigationGroupRuleDecision.preparation_id == prep_id,
                InvestigationGroupRuleDecision.reviewer_id == principal.reviewer_id,
                InvestigationGroupRuleDecision.request_key_hash == key_hash,
            )
        )
        if existing:
            if existing.request_hash != digest(request):
                raise InvestigationError("GROUP_RULE_IDEMPOTENCY_CONFLICT")
            return current
        row = next(
            (
                r
                for r in prep.result["rows"]
                if r["rule_candidate_id"] == str(command.rule_candidate_id)
            ),
            None,
        )
        if row is None:
            raise InvestigationError("GROUP_RULE_CANDIDATE_INVALID")
        prior = current["decisions"].get(str(command.rule_candidate_id))
        if prior and prior["decision"] != "NEEDS_ADJUDICATION":
            raise InvestigationError("GROUP_RULE_ALREADY_DECIDED")
        submitted = [str(e.evidence_ref_id) for e in command.evidence]
        if (
            len(submitted) != len(set(submitted))
            or not set(submitted).issubset(row["evidence_ref_ids"])
            or any(e.effective_at and e.effective_at > store.clock() for e in command.evidence)
        ):
            raise InvestigationError("GROUP_RULE_EVIDENCE_INVALID")
        if command.decision == "APPROVE":
            _compile_approved(prep, request)
        decision_id, now = uuid7(), store.clock()
        RulePromotionService(session).decide(
            RuleApprovalDecisionSchemaV08.model_validate(
                {
                    "rule_approval_decision_id": decision_id,
                    "rule_candidate_id": command.rule_candidate_id,
                    "decision": command.decision,
                    "approver_identity": f"human:{principal.reviewer_id}",
                    "approval_method": "HUMAN",
                    "reason_code": f"HUMAN_{command.decision}",
                    "decided_at": now,
                    "policy_version": GROUP_RULE_REVIEW_VERSION,
                }
            )
        )
        session.add(
            InvestigationGroupRuleDecision(
                decision_id=decision_id,
                preparation_id=prep_id,
                rule_candidate_id=command.rule_candidate_id,
                reviewer_id=principal.reviewer_id,
                request_key_hash=key_hash,
                request_hash=digest(request),
                request=request,
                created_at=now,
            )
        )
        session.flush()
        return _view(store, session, _checked(store, session, task, prep_id))
