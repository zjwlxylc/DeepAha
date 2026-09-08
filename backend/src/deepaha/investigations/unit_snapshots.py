"""Trusted, current-state reconstruction of immutable derived unit plans.

The persisted JSON is a cache, not an approval or an executable trusted input.
Every return rebuilds it from current receipts and actual independent decisions.
"""

from copy import deepcopy
from typing import Any, cast
from uuid import UUID, uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.facts import _target_contract
from deepaha.investigations.models import (
    InvestigationFactAction,
    InvestigationFactPreparation,
    InvestigationRuleDecision,
    InvestigationRulePreparation,
    InvestigationUnitPlan,
)
from deepaha.investigations.rule_contracts import MaterializeInvestigationUnitPlan
from deepaha.investigations.rules import RULE_BRIDGE_VERSION, _context, reviewed_rule
from deepaha.investigations.store import InvestigationStore
from deepaha.investigations.unit_manifest import source_conditions
from deepaha.local_human_test.review import require_human_fact_reviewer
from deepaha.p9b.models import (
    OpportunityUnitVersion,
    RuleApprovalDecisionModel,
    RuleCandidateModel,
    VerifiedFact,
)
from deepaha.review.auth import ReviewerPrincipal
from deepaha.unit_qualification.contracts import (
    CONTRACT_VERSION,
    ConditionDisposition,
    CoverageManifest,
    EvidenceValidity,
    UnitIdentity,
    UnitQualificationPlan,
    UnitRuleAdmission,
    coverage_manifest_sha256,
    rule_sha256,
)

ADAPTER_VERSION = "investigation-unit-snapshot/1.0.0"


def materialize_unit_plan(
    store: InvestigationStore,
    task_id: UUID,
    command: MaterializeInvestigationUnitPlan,
    principal: ReviewerPrincipal,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        # Build before cache lookup so stale evidence cannot bypass current-state checks.
        plan, context = _build(store, session, task_id, command, uuid7())
        existing = session.scalar(
            select(InvestigationUnitPlan).where(
                InvestigationUnitPlan.rule_preparation_id == command.rule_preparation_id,
                InvestigationUnitPlan.contract_version == CONTRACT_VERSION,
                InvestigationUnitPlan.adapter_version == ADAPTER_VERSION,
            )
        )
        if existing is not None:
            plan = plan.model_copy(update={"qualification_plan_id": existing.plan_id})
            return _checked_view(existing, plan, context)
        record = InvestigationUnitPlan(
            plan_id=plan.qualification_plan_id,
            rule_preparation_id=command.rule_preparation_id,
            unit_version_id=plan.target.unit_version_id,
            contract_version=CONTRACT_VERSION,
            adapter_version=ADAPTER_VERSION,
            plan=plan.model_dump(mode="json"),
            plan_hash=digest(plan.model_dump(mode="json")),
            context=deepcopy(context),
            context_hash=digest(context),
            reviewer_id=principal.reviewer_id,
            created_at=store.clock(),
        )
        session.add(record)
        session.flush()
        session.refresh(record)
        return _checked_view(record, plan, context)


def load_unit_plan(
    store: InvestigationStore,
    task_id: UUID,
    plan_id: UUID,
    principal: ReviewerPrincipal,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        record = session.get(InvestigationUnitPlan, plan_id)
        prep = (
            session.get(InvestigationRulePreparation, record.rule_preparation_id)
            if record
            else None
        )
        facts = (
            session.get(InvestigationFactPreparation, prep.fact_preparation_id) if prep else None
        )
        if record is None or prep is None or facts is None or facts.task_id != task_id:
            raise InvestigationError("UNIT_PLAN_NOT_FOUND")
        command = MaterializeInvestigationUnitPlan(
            delivery_hash=str(prep.result["delivery_hash"]),
            binding_id=facts.binding_id,
            check_id=facts.check_id,
            fact_preparation_id=facts.preparation_id,
            entity_id=prep.entity_id,
            fact_set_id=prep.fact_set_id,
            rule_preparation_id=prep.rule_preparation_id,
        )
        plan, context = _build(store, session, task_id, command, plan_id)
        return _checked_view(record, plan, context)


def _checked_view(
    record: InvestigationUnitPlan, plan: UnitQualificationPlan, context: dict[str, Any]
) -> dict[str, Any]:
    expected = plan.model_dump(mode="json")
    if (
        record.contract_version != CONTRACT_VERSION
        or record.adapter_version != ADAPTER_VERSION
        or record.rule_preparation_id != UUID(context["rule_preparation_id"])
        or record.unit_version_id != plan.target.unit_version_id
        or record.plan != expected
        or record.plan_hash != digest(expected)
        or record.context != context
        or record.context_hash != digest(context)
    ):
        raise InvestigationError("UNIT_PLAN_INTEGRITY_FAILED")
    return {
        "plan_id": str(record.plan_id),
        "plan": expected,
        "plan_hash": record.plan_hash,
        "context": deepcopy(context),
        "context_hash": record.context_hash,
        "reviewer_id": str(record.reviewer_id),
        "created_at": record.created_at.isoformat(),
    }


def _build(
    store: InvestigationStore,
    session: Session,
    task_id: UUID,
    command: MaterializeInvestigationUnitPlan,
    plan_id: UUID,
) -> tuple[UnitQualificationPlan, dict[str, Any]]:
    task, binding, facts, fact_set, target = _context(store, session, task_id, command)
    prep = session.get(InvestigationRulePreparation, command.rule_preparation_id)
    if (
        prep is None
        or prep.fact_preparation_id != facts.preparation_id
        or prep.fact_set_id != fact_set.verified_fact_set_id
        or prep.entity_id != command.entity_id
        or prep.compiler_version != RULE_BRIDGE_VERSION
        or digest(prep.result) != prep.result_hash
        or prep.result["target"] != target
        or prep.result["source_rows"] != facts.result["rows"]
        or prep.result["fact_preparation_hash"] != facts.result_hash
        or prep.result["check_id"] != str(command.check_id)
    ):
        raise InvestigationError("RULE_PREPARATION_CONFLICT")
    if target["target_scope"] != "UNIT":
        raise InvestigationError("UNIT_TARGET_REQUIRED")
    unit = session.get(OpportunityUnitVersion, UUID(target["opportunity_unit_version_id"]))
    if unit is None:
        raise InvestigationError("UNIT_TARGET_REQUIRED")
    identity = UnitIdentity(
        opportunity_id=unit.opportunity_id,
        opportunity_version=unit.opportunity_version,
        unit_id=unit.opportunity_unit_id,
        unit_version=unit.version,
        unit_version_id=unit.opportunity_unit_version_id,
    )
    rows = cast(list[dict[str, Any]], prep.result["rows"])
    _check_facts(session, rows, prep.fact_set_id)
    decisions = _final_decisions(session, prep, rows, command, target)
    field_decisions = {
        str(action.candidate_id): str(action.request["decision"])
        for action in session.scalars(
            select(InvestigationFactAction).where(
                InvestigationFactAction.preparation_id == facts.preparation_id,
                InvestigationFactAction.entity_id == command.entity_id,
                InvestigationFactAction.kind == "DECISION",
            )
        )
        if action.request["decision"] != "NEEDS_ADJUDICATION"
    }
    conditions, excluded, notes = source_conditions(
        identity,
        command.entity_id,
        cast(dict[str, Any], task.delivery),
        cast(list[dict[str, Any]], facts.result["rows"]),
        {row["candidate_id"]: row for row in rows},
        field_decisions,
        {key: str(value.request["decision"]) for key, value in decisions.items()},
    )
    # Byte matching and individual approvals cannot establish exhaustive source coverage.
    blockers = ["SOURCE_COMPLETENESS_UNVERIFIED"]
    if notes:
        blockers.append("SOURCE_NOTES_UNREVIEWED")
    manifest = CoverageManifest(
        target=identity,
        preparation_id=facts.preparation_id,
        preparation_sha256=facts.result_hash,
        conditions=tuple(conditions),
        upstream_blockers=tuple(blockers),
    )
    rules, admissions, dispositions = [], [], []
    by_fact = {row["verified_fact_id"]: row for row in rows}
    for condition in conditions:
        row = by_fact.get(str(condition.fact_id))
        decision = decisions.get(row["rule_candidate_id"]) if row else None
        if row and decision and decision.request["decision"] == "APPROVE":
            rule = reviewed_rule(row, cast(dict[str, Any], decision.request), target)
            candidate = session.get(RuleCandidateModel, decision.rule_candidate_id)
            approval = session.get(RuleApprovalDecisionModel, decision.decision_id)
            assert candidate is not None  # checked against the persisted candidate below
            assert approval is not None
            rules.append(rule)
            admissions.append(
                UnitRuleAdmission(
                    rule_id=rule.rule_id,
                    target=identity,
                    rule_sha256=rule_sha256(rule),
                    condition_ids=(condition.condition_id,),
                    candidate_id=candidate.rule_candidate_id,
                    approval_decision_id=decision.decision_id,
                    producer_principal_id=candidate.producer_identity,
                    reviewer_principal_id=f"human:{decision.reviewer_id}",
                    reviewed_at=approval.decided_at,
                    evidence_validity=tuple(
                        EvidenceValidity(
                            evidence_ref_id=e.evidence_ref_id,
                            valid_from=e.effective_at,
                            valid_until=None,
                        )
                        for e in rule.evidence
                    ),
                )
            )
            dispositions.append(
                ConditionDisposition(
                    condition_id=condition.condition_id,
                    kind="RULE",
                    rule_ids=(rule.rule_id,),
                    decision_id=decision.decision_id,
                    reviewer_principal_id=f"human:{decision.reviewer_id}",
                    reason=str(decision.request["reason"]),
                )
            )
        else:
            dispositions.append(
                ConditionDisposition(
                    condition_id=condition.condition_id,
                    kind="UNRESOLVED",
                    rule_ids=(),
                    decision_id=decision.decision_id if decision else None,
                    reviewer_principal_id=f"human:{decision.reviewer_id}" if decision else None,
                    reason="RULE_REJECTED" if decision else "CONDITION_REVIEW_REQUIRED",
                )
            )
    plan = UnitQualificationPlan(
        qualification_plan_id=plan_id,
        version=1,
        target=identity,
        manifest=manifest,
        manifest_sha256=coverage_manifest_sha256(manifest),
        dispositions=tuple(dispositions),
        rules=tuple(rules),
        root_rule_ids=tuple(rule.rule_id for rule in rules),
        admissions=tuple(admissions),
    )
    references = [
        e["check_reference"]
        for source in cast(list[dict[str, Any]], facts.result["rows"])
        for e in source["evidence"]
    ]
    return plan, {
        "adapter_version": ADAPTER_VERSION,
        "rule_preparation_id": str(prep.rule_preparation_id),
        "rule_preparation_hash": prep.result_hash,
        "fact_preparation_hash": facts.result_hash,
        "check_id": str(facts.check_id),
        "binding_id": str(binding.binding_id),
        "delivery_hash": binding.delivery_hash,
        "fact_set_id": str(fact_set.verified_fact_set_id),
        "fact_set_version": fact_set.version,
        "source_bundle_revision_id": str(binding.source_bundle_revision_id),
        "source_row_count": len(cast(list[Any], facts.result["rows"])),
        "excluded_source_rows": excluded,
        "source_notes": notes,
        "evidence_reference_counts": {
            verdict: sum(r["verdict"] == verdict for r in references)
            for verdict in ("PASS", "FAIL", "UNVERIFIED")
        },
        "unresolved_source_references": [r for r in references if r["verdict"] != "PASS"],
        "rule_decisions": {
            key: {
                "decision_id": str(value.decision_id),
                "request_hash": value.request_hash,
                "receipt_created_at": value.created_at.isoformat(),
            }
            for key, value in sorted(decisions.items())
        },
        "evidence_valid_until_policy": "NOT_ESTABLISHED",
    }


def _check_facts(session: Session, rows: list[dict[str, Any]], fact_set_id: UUID) -> None:
    actual = {
        str(f.verified_fact_id): f
        for f in session.scalars(
            select(VerifiedFact).where(VerifiedFact.verified_fact_set_id == fact_set_id)
        )
    }
    if len(rows) != len(actual) or {row["verified_fact_id"] for row in rows} != actual.keys():
        raise InvestigationError("UNIT_RULE_FACTS_CONFLICT")
    for row in rows:
        fact = actual[row["verified_fact_id"]]
        if (
            str(fact.candidate_id) != row["candidate_id"]
            or fact.field_name != row["field_name"]
            or fact.fact_state != row["fact_state"]
            or fact.normalized_value != row["normalized_value"]
        ):
            raise InvestigationError("UNIT_RULE_FACTS_CONFLICT")


def _final_decisions(
    session: Session,
    prep: InvestigationRulePreparation,
    rows: list[dict[str, Any]],
    command: MaterializeInvestigationUnitPlan,
    target: dict[str, Any],
) -> dict[str, InvestigationRuleDecision]:
    final: dict[str, InvestigationRuleDecision] = {}
    for decision in session.scalars(
        select(InvestigationRuleDecision).where(
            InvestigationRuleDecision.rule_preparation_id == prep.rule_preparation_id
        )
    ):
        if decision.request["decision"] == "NEEDS_ADJUDICATION":
            continue
        key = str(decision.rule_candidate_id)
        if key in final:
            raise InvestigationError("UNIT_RULE_APPROVAL_CONFLICT")
        final[key] = decision
    expected = {row["rule_candidate_id"]: row for row in rows if row["rule_candidate_id"]}
    if final.keys() != expected.keys():
        raise InvestigationError("UNIT_ALL_RULES_REQUIRE_FINAL_DECISION")
    for key, decision in final.items():
        candidate = session.get(RuleCandidateModel, decision.rule_candidate_id)
        approval = session.get(RuleApprovalDecisionModel, decision.decision_id)
        if (
            digest(decision.request) != decision.request_hash
            or any(str(decision.request[k]) != str(v) for k, v in command.model_dump().items())
            or candidate is None
            or candidate.proposed_rule_payload != expected[key]["payload"]
            or candidate.verified_fact_set_id != prep.fact_set_id
            or candidate.compiler_version != RULE_BRIDGE_VERSION
            or any(
                str(getattr(candidate, k)) != str(v) for k, v in _target_contract(target).items()
            )
            or approval is None
            or approval.rule_candidate_id != candidate.rule_candidate_id
            or approval.decision != decision.request["decision"]
            or approval.approval_method != "HUMAN"
            or approval.approver_identity != f"human:{decision.reviewer_id}"
            or approval.policy_version != RULE_BRIDGE_VERSION
            or candidate.producer_identity == approval.approver_identity
        ):
            raise InvestigationError("UNIT_RULE_APPROVAL_CONFLICT")
    return final
