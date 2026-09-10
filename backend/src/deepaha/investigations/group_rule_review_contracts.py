"""Independent GROUP rule review; no target inheritance or activation contract."""

from typing import Literal

from pydantic import Field

from deepaha.contracts.common import EntityId, Instant, Sha256
from deepaha.investigations.group_contracts import GroupContract
from deepaha.investigations.group_rule_contracts import GroupRulePreview, GroupRulePreviewRow
from deepaha.investigations.rule_contracts import InvestigationRuleEvidence

GROUP_RULE_REVIEW_VERSION = "group-rule-review/1.0.0+deriver-1.0.1"


class PrepareGroupRules(GroupContract):
    expected_preview_hash: Sha256


class DecideGroupRule(GroupContract):
    expected_preparation_hash: Sha256
    rule_candidate_id: EntityId
    decision: Literal["APPROVE", "REJECT", "NEEDS_ADJUDICATION"]
    evidence: tuple[InvestigationRuleEvidence, ...] = Field(default=(), max_length=2000)
    reason: str = Field(min_length=1, max_length=2000)


class GroupRuleReviewRow(GroupRulePreviewRow):
    rule_candidate_id: EntityId | None


class GroupRuleReviewResult(GroupContract):
    contract_version: Literal["group-rule-review/1.0.0+deriver-1.0.1"]
    scope: Literal["GROUP_RULE_REVIEW_ONLY"]
    preview: GroupRulePreview
    rows: tuple[GroupRuleReviewRow, ...]


class GroupRuleDecisionView(GroupContract):
    decision_id: EntityId
    rule_candidate_id: EntityId
    decision: Literal["APPROVE", "REJECT", "NEEDS_ADJUDICATION"]
    reason: str = Field(min_length=1, max_length=2000)
    evidence: tuple[InvestigationRuleEvidence, ...]
    reviewer_id: EntityId
    created_at: Instant


class GroupRuleReviewRecord(GroupContract):
    preparation_id: EntityId
    fact_preparation_id: EntityId
    fact_set_id: EntityId
    result: GroupRuleReviewResult
    result_hash: Sha256
    reviewer_id: EntityId
    created_at: Instant
    decisions: dict[str, GroupRuleDecisionView]
    history: tuple[GroupRuleDecisionView, ...]
