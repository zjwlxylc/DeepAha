"""Exact identities for read-only GROUP applicability preparation."""

from typing import Any, Literal, Self

from pydantic import Field, model_validator

from deepaha.contracts.common import EntityId, Instant, NonEmptyString, Sha256
from deepaha.investigations.contracts import digest
from deepaha.investigations.group_contracts import GroupContract, GroupIdentity, GroupMember
from deepaha.investigations.group_rule_review_contracts import (
    GroupRuleDecisionView,
    GroupRuleReviewRecord,
    GroupRuleReviewRow,
)
from deepaha.unit_qualification.contracts import UnitIdentity, UnitQualificationPlan


class GroupApplicabilityContext(GroupContract):
    contract_version: Literal["group-rule-applicability-context/1.0.0"]
    task_id: EntityId
    target_plan_id: EntityId
    target_plan_hash: Sha256
    target_plan_context_hash: Sha256
    target: UnitIdentity
    target_entity_id: NonEmptyString
    source_group: GroupIdentity
    group_binding_id: EntityId
    group_source_hash: Sha256
    member: GroupMember
    binding_id: EntityId
    check_id: EntityId
    source_bundle_revision_id: EntityId
    source_rule_preparation_id: EntityId
    source_rule_preparation_hash: Sha256
    source_rule_candidate_id: EntityId
    source_rule_approval_id: EntityId
    source_rule_approval_hash: Sha256
    source_review_hash: Sha256


class GroupApplicabilityPlan(GroupContract):
    plan_id: EntityId
    plan: UnitQualificationPlan
    plan_hash: Sha256
    context: dict[str, Any]
    context_hash: Sha256
    reviewer_id: EntityId
    created_at: Instant


class GroupApplicabilityEvidenceOption(GroupContract):
    member_id: EntityId
    block_id: EntityId
    material_id: NonEmptyString
    source_url: NonEmptyString
    document_id: EntityId
    evidence_ref_id: EntityId
    text: str
    locator: dict[str, Any]


class GroupApplicabilityView(GroupContract):
    scope: Literal["GROUP_APPLICABILITY_CONTEXT_ONLY"]
    outcome: Literal["UNDECIDED"]
    context: GroupApplicabilityContext
    context_hash: Sha256
    source_review: GroupRuleReviewRecord
    target_plan: GroupApplicabilityPlan
    candidate: GroupRuleReviewRow
    approval: GroupRuleDecisionView
    evidence_options: tuple[GroupApplicabilityEvidenceOption, ...] = Field(max_length=50)
    next_cursor: str | None

    @model_validator(mode="after")
    def require_exact_context(self) -> Self:
        ctx, review, plan = self.context, self.source_review, self.target_plan
        source = review.result.preview.result.fact_review.result.group_source
        if (
            digest(ctx.model_dump(mode="json")) != self.context_hash
            or digest(review.model_dump(mode="json")) != ctx.source_review_hash
            or digest(self.approval.model_dump(mode="json")) != ctx.source_rule_approval_hash
            or digest(plan.plan.model_dump(mode="json")) != plan.plan_hash
            or digest(plan.context) != plan.context_hash
            or plan.plan_id != ctx.target_plan_id
            or plan.plan_hash != ctx.target_plan_hash
            or plan.context_hash != ctx.target_plan_context_hash
            or plan.plan.target != ctx.target
            or plan.plan.qualification_plan_id != plan.plan_id
            or review.preparation_id != ctx.source_rule_preparation_id
            or review.result_hash != ctx.source_rule_preparation_hash
            or self.candidate not in review.result.rows
            or self.candidate.rule_candidate_id != ctx.source_rule_candidate_id
            or review.decisions.get(str(ctx.source_rule_candidate_id)) != self.approval
            or self.approval.decision != "APPROVE"
            or self.approval.decision_id != ctx.source_rule_approval_id
            or source.group_identity != ctx.source_group
            or source.group_binding_id != ctx.group_binding_id
            or source.source_hash != ctx.group_source_hash
            or ctx.member not in source.source.members
            or ctx.member.state != "BOUND"
            or ctx.member.entity_id != ctx.target_entity_id
            or ctx.member.position_binding is None
            or ctx.member.position_binding.opportunity_unit_id != ctx.target.unit_id
            or ctx.member.position_binding.opportunity_unit_version_id != ctx.target.unit_version_id
        ):
            raise ValueError("group applicability response differs from exact context")
        if len({(e.block_id, e.member_id) for e in self.evidence_options}) != len(
            self.evidence_options
        ):
            raise ValueError("duplicate evidence option")
        if self.next_cursor is not None:
            if len(self.evidence_options) != 50:
                raise ValueError("next cursor requires a full evidence page")
            last = self.evidence_options[-1]
            if self.next_cursor != f"{last.block_id}:{last.member_id}":
                raise ValueError("next cursor differs from last evidence option")
        return self
