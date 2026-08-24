from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.contracts.phase9b import (
    RuleApprovalDecisionSchemaV08,
    RuleCandidateSchemaV08,
)
from deepaha.p9b.models import (
    RuleApprovalDecisionModel,
    RuleCandidateEvidence,
    RuleCandidateFact,
    RuleCandidateModel,
    UnitRuleSet,
    VerifiedFact,
    VerifiedFactEvidence,
    VersionedVerifiedFactSet,
)


class P9BRuleCompileError(ValueError):
    """A P9-B rule promotion boundary was violated."""


def compile_legacy_opportunity_rule(
    candidate: RuleCandidateSchemaV08,
    *,
    approval_decision: str | None = None,
) -> dict[str, object]:
    if candidate.target_scope == "UNIT":
        raise P9BRuleCompileError("Unit RuleCandidate cannot compile to legacy Opportunity RuleSet")
    if approval_decision != "APPROVE":
        raise P9BRuleCompileError("independent approval is required before legacy rule compilation")
    return {
        "opportunity_id": candidate.opportunity_id,
        "opportunity_version": candidate.opportunity_version,
        "rule_candidate_id": candidate.rule_candidate_id,
        "payload": candidate.proposed_rule_payload.model_dump(mode="python"),
    }


def compile_dormant_unit_rule_set(
    candidate: RuleCandidateSchemaV08,
    *,
    rule_approval_decision_id: UUID,
    approval_decision: str,
    unit_rule_set_id: UUID,
    created_at: datetime,
) -> dict[str, object]:
    if candidate.target_scope != "UNIT":
        raise P9BRuleCompileError("UnitRuleSet requires a UNIT RuleCandidate")
    if approval_decision != "APPROVE":
        raise P9BRuleCompileError("UnitRuleSet requires an independently approved candidate")
    assert candidate.opportunity_unit_id is not None
    assert candidate.opportunity_unit_version_id is not None
    return {
        "unit_rule_set_id": unit_rule_set_id,
        "opportunity_id": candidate.opportunity_id,
        "opportunity_version": candidate.opportunity_version,
        "opportunity_unit_id": candidate.opportunity_unit_id,
        "opportunity_unit_version_id": candidate.opportunity_unit_version_id,
        "rule_candidate_id": candidate.rule_candidate_id,
        "rule_schema_version": "0.8.0",
        "payload": candidate.proposed_rule_payload.model_dump(mode="python"),
        "review_status": "APPROVED",
        "activation_status": "DORMANT",
        "rule_approval_decision_id": rule_approval_decision_id,
        "created_at": created_at,
    }


class RulePromotionService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def propose(
        self,
        contract: RuleCandidateSchemaV08,
        *,
        verified_fact_set_id: UUID,
    ) -> RuleCandidateModel:
        fact_set = self._session.get(VersionedVerifiedFactSet, verified_fact_set_id)
        if fact_set is None or fact_set.status != "ACTIVE":
            raise P9BRuleCompileError("RuleCandidate requires an ACTIVE VerifiedFactSet")
        target = (
            contract.target_scope.value,
            contract.opportunity_id,
            contract.opportunity_version,
            contract.opportunity_unit_id,
            contract.opportunity_unit_version_id,
        )
        if target != (
            fact_set.target_scope,
            fact_set.opportunity_id,
            fact_set.opportunity_version,
            fact_set.opportunity_unit_id,
            fact_set.opportunity_unit_version_id,
        ):
            raise P9BRuleCompileError("RuleCandidate target does not match VerifiedFactSet")
        facts = {
            fact.verified_fact_id: fact
            for fact in self._session.scalars(
                select(VerifiedFact).where(
                    VerifiedFact.verified_fact_set_id == verified_fact_set_id,
                    VerifiedFact.verified_fact_id.in_(contract.verified_fact_ids),
                )
            )
        }
        if len(facts) != len(contract.verified_fact_ids):
            raise P9BRuleCompileError("RuleCandidate fact does not belong to VerifiedFactSet")
        supported_evidence = set(
            self._session.scalars(
                select(VerifiedFactEvidence.evidence_ref_id).where(
                    VerifiedFactEvidence.verified_fact_set_id == verified_fact_set_id,
                    VerifiedFactEvidence.verified_fact_id.in_(contract.verified_fact_ids),
                )
            )
        )
        if not set(contract.evidence_ref_ids).issubset(supported_evidence):
            raise P9BRuleCompileError("RuleCandidate evidence is not supported by its facts")

        row = RuleCandidateModel(
            rule_candidate_id=contract.rule_candidate_id,
            target_scope=contract.target_scope.value,
            opportunity_id=contract.opportunity_id,
            opportunity_version=contract.opportunity_version,
            opportunity_unit_id=contract.opportunity_unit_id,
            opportunity_unit_version_id=contract.opportunity_unit_version_id,
            verified_fact_set_id=verified_fact_set_id,
            rule_type=contract.rule_type,
            proposed_rule_payload=contract.proposed_rule_payload.model_dump(mode="json"),
            compiler_version=contract.compiler_version,
            producer_identity=contract.producer_identity,
            status="PROPOSED",
            created_at=contract.created_at,
        )
        self._session.add(row)
        self._session.flush()
        self._session.add_all(
            [
                RuleCandidateFact(
                    rule_candidate_id=row.rule_candidate_id,
                    verified_fact_set_id=verified_fact_set_id,
                    verified_fact_id=fact_id,
                )
                for fact_id in contract.verified_fact_ids
            ]
        )
        self._session.add_all(
            [
                RuleCandidateEvidence(
                    rule_candidate_id=row.rule_candidate_id,
                    evidence_ref_id=evidence_ref_id,
                )
                for evidence_ref_id in contract.evidence_ref_ids
            ]
        )
        self._session.flush()
        return row

    def decide(self, contract: RuleApprovalDecisionSchemaV08) -> RuleApprovalDecisionModel:
        candidate = self._session.get(RuleCandidateModel, contract.rule_candidate_id)
        if candidate is None:
            raise P9BRuleCompileError("RuleCandidate does not exist")
        if candidate.producer_identity == contract.approver_identity:
            raise P9BRuleCompileError("RuleCandidate approval must be independent of its producer")
        row = RuleApprovalDecisionModel(
            rule_approval_decision_id=contract.rule_approval_decision_id,
            rule_candidate_id=contract.rule_candidate_id,
            decision=contract.decision.value,
            approver_identity=contract.approver_identity,
            approval_method=contract.approval_method.value,
            reason_code=contract.reason_code,
            decided_at=contract.decided_at,
            policy_version=contract.policy_version,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def materialize_dormant_unit_rule_set(
        self,
        *,
        rule_candidate_id: UUID,
        rule_approval_decision_id: UUID,
        unit_rule_set_id: UUID,
        created_at: datetime,
    ) -> UnitRuleSet:
        candidate = self._candidate_contract(rule_candidate_id)
        decision = self._session.get(RuleApprovalDecisionModel, rule_approval_decision_id)
        if decision is None or decision.rule_candidate_id != rule_candidate_id:
            raise P9BRuleCompileError("RuleApprovalDecision does not bind the RuleCandidate")
        values = compile_dormant_unit_rule_set(
            candidate,
            rule_approval_decision_id=rule_approval_decision_id,
            approval_decision=decision.decision,
            unit_rule_set_id=unit_rule_set_id,
            created_at=created_at,
        )
        row = UnitRuleSet(**values)
        self._session.add(row)
        self._session.flush()
        return row

    def _candidate_contract(self, rule_candidate_id: UUID) -> RuleCandidateSchemaV08:
        candidate = self._session.get(RuleCandidateModel, rule_candidate_id)
        if candidate is None:
            raise P9BRuleCompileError("RuleCandidate does not exist")
        fact_ids = list(
            self._session.scalars(
                select(RuleCandidateFact.verified_fact_id)
                .where(RuleCandidateFact.rule_candidate_id == rule_candidate_id)
                .order_by(RuleCandidateFact.verified_fact_id)
            )
        )
        evidence_ids = list(
            self._session.scalars(
                select(RuleCandidateEvidence.evidence_ref_id)
                .where(RuleCandidateEvidence.rule_candidate_id == rule_candidate_id)
                .order_by(RuleCandidateEvidence.evidence_ref_id)
            )
        )
        return RuleCandidateSchemaV08.model_validate(
            {
                "rule_candidate_id": candidate.rule_candidate_id,
                "target_scope": candidate.target_scope,
                "opportunity_id": candidate.opportunity_id,
                "opportunity_version": candidate.opportunity_version,
                "opportunity_unit_id": candidate.opportunity_unit_id,
                "opportunity_unit_version_id": candidate.opportunity_unit_version_id,
                "verified_fact_ids": fact_ids,
                "rule_type": candidate.rule_type,
                "proposed_rule_payload": candidate.proposed_rule_payload,
                "evidence_ref_ids": evidence_ids,
                "compiler_version": candidate.compiler_version,
                "producer_identity": candidate.producer_identity,
                "status": candidate.status,
                "created_at": candidate.created_at,
            }
        )


__all__ = [
    "P9BRuleCompileError",
    "RulePromotionService",
    "compile_dormant_unit_rule_set",
    "compile_legacy_opportunity_rule",
]
