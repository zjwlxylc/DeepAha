"""Explicit evidence assessments, separate from extraction and fact approval."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from deepaha.contracts.phase4 import EvidenceRelation, RuleEvidenceAuthority
from deepaha.investigations.contracts import PrepareInvestigationFacts


class PrepareInvestigationRules(PrepareInvestigationFacts):
    fact_preparation_id: UUID
    entity_id: str = Field(min_length=1, max_length=256)
    fact_set_id: UUID


class MaterializeInvestigationUnitPlan(PrepareInvestigationRules):
    rule_preparation_id: UUID


class InvestigationRuleEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    evidence_ref_id: UUID
    authority: RuleEvidenceAuthority | None
    relation: EvidenceRelation | None
    effective_at: AwareDatetime | None
    applicability: Literal["APPLIES_TO_EXACT_TARGET", "UNRESOLVED"]
    reason: str = Field(min_length=1, max_length=2000)


class DecideInvestigationRule(PrepareInvestigationRules):
    rule_preparation_id: UUID
    rule_candidate_id: UUID
    decision: Literal["APPROVE", "REJECT", "NEEDS_ADJUDICATION"]
    evidence: tuple[InvestigationRuleEvidence, ...] = Field(default=(), max_length=2000)
    reason: str = Field(min_length=1, max_length=2000)
