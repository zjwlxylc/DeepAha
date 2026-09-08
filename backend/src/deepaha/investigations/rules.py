"""Propose from verified facts; require separate human rule and evidence approval."""

from hashlib import sha256
from typing import Any, cast
from uuid import UUID, uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.contracts.phase4 import RuleEvidenceSchemaV04, RuleSchemaV04
from deepaha.contracts.phase9b import RuleApprovalDecisionSchemaV08, RuleCandidateSchemaV08
from deepaha.documents.models import DocumentBlock
from deepaha.investigations.bindings import _authorize, _validated_members
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.facts import _current, _current_check, _target_contract
from deepaha.investigations.field_mapping import FIELD_MAPPING_VERSION
from deepaha.investigations.models import (
    InvestigationBinding,
    InvestigationFactAction,
    InvestigationFactPreparation,
    InvestigationRuleDecision,
    InvestigationRulePreparation,
    InvestigationTask,
)
from deepaha.investigations.rule_contracts import DecideInvestigationRule, PrepareInvestigationRules
from deepaha.investigations.store import InvestigationStore
from deepaha.local_human_test.review import (
    RULE_DERIVATION_VERSION,
    build_rule_payload,
    require_human_fact_reviewer,
    validate_idempotency_key,
)
from deepaha.p9b.models import (
    RuleApprovalDecisionModel,
    VerifiedFact,
    VerifiedFactEvidence,
    VersionedVerifiedFactSet,
)
from deepaha.p9b.rules import P9BRuleCompileError, RulePromotionService
from deepaha.review.auth import ReviewerPrincipal
from deepaha.rules.compiler import compile_rule_graph
from deepaha.rules.types import RuleCompileError

RULE_BRIDGE_VERSION = f"direct-wma-rule-bridge/2.0.0+deriver-{RULE_DERIVATION_VERSION}"


def _context(
    store: InvestigationStore,
    session: Session,
    task_id: UUID,
    command: PrepareInvestigationRules,
) -> tuple[
    InvestigationTask,
    InvestigationBinding,
    InvestigationFactPreparation,
    VersionedVerifiedFactSet,
    dict[str, Any],
]:
    task, binding = _current(store, session, task_id, command)
    prep = session.get(InvestigationFactPreparation, command.fact_preparation_id)
    if (
        prep is None
        or prep.binding_id != binding.binding_id
        or prep.mapping_version != FIELD_MAPPING_VERSION
        or prep.check_id != command.check_id
        or digest(prep.result) != prep.result_hash
    ):
        raise InvestigationError("RULE_FACT_PREPARATION_CONFLICT")
    _current_check(store, session, task, binding, command.check_id)
    promoted = session.scalar(
        select(InvestigationFactAction).where(
            InvestigationFactAction.preparation_id == prep.preparation_id,
            InvestigationFactAction.entity_id == command.entity_id,
            InvestigationFactAction.fact_set_id == command.fact_set_id,
            InvestigationFactAction.kind == "PROMOTION",
        )
    )
    fact_set = session.scalar(
        select(VersionedVerifiedFactSet)
        .where(VersionedVerifiedFactSet.verified_fact_set_id == command.fact_set_id)
        .with_for_update()
    )
    target = next(
        (
            t
            for t in cast(list[dict[str, Any]], prep.result["targets"])
            if t["entity_id"] == command.entity_id
        ),
        None,
    )
    if (
        promoted is None
        or fact_set is None
        or fact_set.status != "ACTIVE"
        or target is None
        or fact_set.source_bundle_revision_id != binding.source_bundle_revision_id
        or any(str(getattr(fact_set, k)) != str(v) for k, v in _target_contract(target).items())
    ):
        raise InvestigationError("RULE_FACT_SET_CONFLICT")
    return task, binding, prep, fact_set, target


def prepare_rules(
    store: InvestigationStore,
    task_id: UUID,
    command: PrepareInvestigationRules,
    principal: ReviewerPrincipal,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        task, binding, prep, fact_set, target = _context(store, session, task_id, command)
        existing = session.scalar(
            select(InvestigationRulePreparation).where(
                InvestigationRulePreparation.fact_preparation_id == prep.preparation_id,
                InvestigationRulePreparation.entity_id == command.entity_id,
                InvestigationRulePreparation.fact_set_id == fact_set.verified_fact_set_id,
                InvestigationRulePreparation.compiler_version == RULE_BRIDGE_VERSION,
            )
        )
        if existing is not None:
            return describe_rule_preparation(session, existing)
        _validated_members(store, session, task)
        rows = []
        for fact in session.scalars(
            select(VerifiedFact)
            .where(VerifiedFact.verified_fact_set_id == fact_set.verified_fact_set_id)
            .order_by(VerifiedFact.verified_fact_id)
        ):
            payload = build_rule_payload(
                field_name=fact.field_name, normalized_value=fact.normalized_value
            )
            evidence = list(
                session.execute(
                    select(VerifiedFactEvidence, DocumentBlock)
                    .join(DocumentBlock, VerifiedFactEvidence.block_id == DocumentBlock.block_id)
                    .where(VerifiedFactEvidence.verified_fact_id == fact.verified_fact_id)
                    .order_by(VerifiedFactEvidence.evidence_ref_id)
                )
            )
            candidate_id = None
            reason = "FACT_UNKNOWN" if fact.fact_state != "KNOWN" else "FIELD_NOT_EXECUTABLE"
            if fact.fact_state == "KNOWN" and payload is not None:
                candidate_id = uuid7()
                payload = payload.model_copy(
                    update={"code": f"investigation-{fact.verified_fact_id}"}
                )
                contract = RuleCandidateSchemaV08.model_validate(
                    _target_contract(target)
                    | {
                        "rule_candidate_id": candidate_id,
                        "verified_fact_ids": [fact.verified_fact_id],
                        "rule_type": "ATOMIC_QUALIFICATION",
                        "proposed_rule_payload": payload,
                        "evidence_ref_ids": [e.evidence_ref_id for e, _ in evidence],
                        "compiler_version": RULE_BRIDGE_VERSION,
                        "producer_identity": f"component:{RULE_BRIDGE_VERSION}",
                        "status": "PROPOSED",
                        "created_at": store.clock(),
                    }
                )
                RulePromotionService(session).propose(
                    contract, verified_fact_set_id=fact_set.verified_fact_set_id
                )
                reason = "INDEPENDENT_RULE_REVIEW_REQUIRED"
            rows.append(
                {
                    "verified_fact_id": str(fact.verified_fact_id),
                    "candidate_id": str(fact.candidate_id),
                    "field_name": fact.field_name,
                    "fact_state": fact.fact_state,
                    "normalized_value": fact.normalized_value,
                    "rule_candidate_id": str(candidate_id) if candidate_id else None,
                    "payload": payload.model_dump(mode="json")
                    if candidate_id and payload
                    else None,
                    "reason_code": reason,
                    "evidence_ref_ids": [str(e.evidence_ref_id) for e, _ in evidence],
                    "evidence": [
                        {
                            "evidence_ref_id": str(e.evidence_ref_id),
                            "block_id": str(b.block_id),
                            "document_id": str(b.document_id),
                            "text": b.canonical_text_or_value,
                            "structural_locator": b.structural_locator,
                        }
                        for e, b in evidence
                    ],
                }
            )
        result = {
            "target": target,
            "source_rows": prep.result["rows"],
            "rows": rows,
            "binding_id": str(binding.binding_id),
            "delivery_hash": binding.delivery_hash,
            "fact_preparation_hash": prep.result_hash,
            "check_id": str(prep.check_id),
            "fact_set_version": fact_set.version,
            "source_bundle_revision_id": str(binding.source_bundle_revision_id),
            "scope_status": "COMPLETE_CONDITION_REVIEW_REQUIRED",
        }
        record = InvestigationRulePreparation(
            rule_preparation_id=uuid7(),
            fact_preparation_id=prep.preparation_id,
            entity_id=command.entity_id,
            fact_set_id=fact_set.verified_fact_set_id,
            compiler_version=RULE_BRIDGE_VERSION,
            reviewer_id=principal.reviewer_id,
            result=result,
            result_hash=digest(result),
            created_at=store.clock(),
        )
        session.add(record)
        session.flush()
        return describe_rule_preparation(session, record)


def describe_rule_preparation(
    session: Session, prep: InvestigationRulePreparation
) -> dict[str, Any]:
    if digest(prep.result) != prep.result_hash:
        raise InvestigationError("RULE_PREPARATION_CONFLICT")
    decisions: dict[str, Any] = {}
    history = []
    for row in session.scalars(
        select(InvestigationRuleDecision)
        .where(InvestigationRuleDecision.rule_preparation_id == prep.rule_preparation_id)
        .order_by(InvestigationRuleDecision.created_at, InvestigationRuleDecision.decision_id)
    ):
        key = str(row.rule_candidate_id)
        view = {
            "decision_id": str(row.decision_id),
            "rule_candidate_id": key,
            "decision": row.request["decision"],
            "reason": row.request["reason"],
            "evidence": row.request["evidence"],
            "reviewer_id": str(row.reviewer_id),
            "created_at": row.created_at.isoformat(),
        }
        history.append(view)
        if key not in decisions or decisions[key]["decision"] == "NEEDS_ADJUDICATION":
            decisions[key] = view
    return {
        **prep.result,
        "rule_preparation_id": str(prep.rule_preparation_id),
        "fact_preparation_id": str(prep.fact_preparation_id),
        "entity_id": prep.entity_id,
        "fact_set_id": str(prep.fact_set_id),
        "compiler_version": prep.compiler_version,
        "result_hash": prep.result_hash,
        "decisions": decisions,
        "decision_history": history,
    }


def describe_rules(session: Session, task_id: UUID, binding_id: UUID) -> dict[str, Any]:
    current, history = [], []
    records = session.execute(
        select(InvestigationRulePreparation, InvestigationFactPreparation, VersionedVerifiedFactSet)
        .join(
            InvestigationFactPreparation,
            InvestigationFactPreparation.preparation_id
            == InvestigationRulePreparation.fact_preparation_id,
        )
        .join(
            VersionedVerifiedFactSet,
            VersionedVerifiedFactSet.verified_fact_set_id
            == InvestigationRulePreparation.fact_set_id,
        )
        .where(InvestigationFactPreparation.task_id == task_id)
        .order_by(
            InvestigationRulePreparation.created_at,
            InvestigationRulePreparation.rule_preparation_id,
        )
    )
    for prep, facts, fact_set in records:
        view = describe_rule_preparation(session, prep)
        if (
            facts.binding_id == binding_id
            and facts.mapping_version == FIELD_MAPPING_VERSION
            and fact_set.status == "ACTIVE"
            and prep.compiler_version == RULE_BRIDGE_VERSION
        ):
            current.append(view)
        history.append(
            {
                "rule_preparation_id": str(prep.rule_preparation_id),
                "entity_id": prep.entity_id,
                "fact_set_id": str(prep.fact_set_id),
                "compiler_version": prep.compiler_version,
                "created_at": prep.created_at.isoformat(),
            }
        )
    return {"current": current, "history": history}


def reviewed_rule(
    row: dict[str, Any], request: dict[str, Any], target: dict[str, Any]
) -> RuleSchemaV04:
    command_evidence = request["evidence"]
    expected = {e["evidence_ref_id"]: e for e in row["evidence"]}
    if (
        request["decision"] != "APPROVE"
        or len(command_evidence) != len(expected)
        or {e["evidence_ref_id"] for e in command_evidence} != set(expected)
        or any(
            e["authority"] is None
            or e["relation"] is None
            or e["effective_at"] is None
            or e["applicability"] != "APPLIES_TO_EXACT_TARGET"
            or not e["reason"].strip()
            for e in command_evidence
        )
    ):
        raise InvestigationError("RULE_EVIDENCE_REVIEW_INCOMPLETE")
    from deepaha.contracts.phase4 import RuleEvidenceAuthority

    evidence = [
        RuleEvidenceSchemaV04.model_validate(
            {
                "evidence_ref_id": e["evidence_ref_id"],
                "document_id": expected[e["evidence_ref_id"]]["document_id"],
                "authority": e["authority"],
                "precedence": RuleEvidenceAuthority(e["authority"]).precedence,
                "relation": e["relation"],
                "effective_at": e["effective_at"],
                "assertion_sha256": digest(
                    {"target": _target_contract(target), "payload": row["payload"], "assessment": e}
                ),
            }
        )
        for e in command_evidence
    ]
    return RuleSchemaV04.model_validate(
        row["payload"]
        | {"rule_id": row["rule_candidate_id"], "operand_rule_ids": [], "evidence": evidence}
    )


def decide_rule(
    store: InvestigationStore,
    task_id: UUID,
    command: DecideInvestigationRule,
    principal: ReviewerPrincipal,
    key: str,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    request = command.model_dump(mode="json")
    key_hash = sha256(validate_idempotency_key(key).encode()).hexdigest()
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        task, _, _, _, _ = _context(store, session, task_id, command)
        prep = session.get(InvestigationRulePreparation, command.rule_preparation_id)
        if (
            prep is None
            or prep.fact_preparation_id != command.fact_preparation_id
            or prep.fact_set_id != command.fact_set_id
            or prep.entity_id != command.entity_id
            or prep.compiler_version != RULE_BRIDGE_VERSION
            or digest(prep.result) != prep.result_hash
        ):
            raise InvestigationError("RULE_PREPARATION_CONFLICT")
        existing = session.scalar(
            select(InvestigationRuleDecision).where(
                InvestigationRuleDecision.rule_preparation_id == prep.rule_preparation_id,
                InvestigationRuleDecision.reviewer_id == principal.reviewer_id,
                InvestigationRuleDecision.request_key_hash == key_hash,
            )
        )
        if existing:
            if existing.request_hash != digest(request):
                raise InvestigationError("RULE_IDEMPOTENCY_CONFLICT")
            return describe_rule_preparation(session, prep)
        row = next(
            (
                r
                for r in cast(list[dict[str, Any]], prep.result["rows"])
                if r["rule_candidate_id"] == str(command.rule_candidate_id)
            ),
            None,
        )
        if row is None or not command.reason.strip():
            raise InvestigationError("RULE_CANDIDATE_INVALID")
        if session.scalar(
            select(RuleApprovalDecisionModel).where(
                RuleApprovalDecisionModel.rule_candidate_id == command.rule_candidate_id,
                RuleApprovalDecisionModel.decision != "NEEDS_ADJUDICATION",
            )
        ):
            raise InvestigationError("RULE_CANDIDATE_ALREADY_DECIDED")
        _validated_members(store, session, task)
        submitted = [item.evidence_ref_id for item in command.evidence]
        expected = {UUID(value) for value in row["evidence_ref_ids"]}
        if len(submitted) != len(set(submitted)) or not set(submitted).issubset(expected):
            raise InvestigationError("RULE_EVIDENCE_REVIEW_INCOMPLETE")
        if command.decision == "APPROVE":
            rule = reviewed_rule(row, request, cast(dict[str, Any], prep.result["target"]))
            try:
                compile_rule_graph((rule,), (rule.rule_id,))
            except RuleCompileError as error:
                raise InvestigationError("RULE_NOT_EXECUTABLE") from error
        decision_id = uuid7()
        try:
            RulePromotionService(session).decide(
                RuleApprovalDecisionSchemaV08.model_validate(
                    {
                        "rule_approval_decision_id": decision_id,
                        "rule_candidate_id": command.rule_candidate_id,
                        "decision": command.decision,
                        "approver_identity": f"human:{principal.reviewer_id}",
                        "approval_method": "HUMAN",
                        "reason_code": f"HUMAN_{command.decision}",
                        "decided_at": store.clock(),
                        "policy_version": RULE_BRIDGE_VERSION,
                    }
                )
            )
        except P9BRuleCompileError as error:
            raise InvestigationError("RULE_APPROVAL_INVALID") from error
        session.add(
            InvestigationRuleDecision(
                decision_id=decision_id,
                rule_preparation_id=prep.rule_preparation_id,
                rule_candidate_id=command.rule_candidate_id,
                reviewer_id=principal.reviewer_id,
                request_key_hash=key_hash,
                request_hash=digest(request),
                request=request,
                created_at=store.clock(),
            )
        )
        session.flush()
        return describe_rule_preparation(session, prep)
