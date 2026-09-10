"""Private API receipts for independent group applicability decisions."""

from typing import Any, Literal, Self

from pydantic import Field, model_validator

from deepaha.contracts.common import EntityId, Instant, Sha256
from deepaha.investigations.contracts import digest
from deepaha.investigations.group_applicability_contracts import (
    GroupApplicabilityContext,
    GroupApplicabilityPlan,
    GroupApplicabilityView,
)
from deepaha.investigations.group_applicability_decisions import DecideGroupApplicability
from deepaha.investigations.group_contracts import GroupContract
from deepaha.investigations.group_rule_review_contracts import (
    GroupRuleDecisionView,
    GroupRuleReviewRecord,
    GroupRuleReviewRow,
)


class GroupApplicabilityBoundEvidence(GroupContract):
    member_id: EntityId
    block_id: EntityId
    quote: str = Field(min_length=1, max_length=20000)
    document_id: EntityId
    material_id: str
    source_url: str
    evidence_ref_id: EntityId
    block_hash: Sha256
    binding_hash: Sha256
    locator: dict[str, Any]


class GroupApplicabilityReceipt(GroupContract):
    decision_id: EntityId
    sequence: int = Field(ge=1)
    request: DecideGroupApplicability
    request_hash: Sha256
    context: GroupApplicabilityContext
    context_hash: Sha256
    evidence_snapshot: tuple[GroupApplicabilityBoundEvidence, ...] = Field(max_length=20)
    evidence_hash: Sha256
    reviewer_id: EntityId
    created_at: Instant

    @model_validator(mode="after")
    def require_exact_receipt(self) -> Self:
        request, context = self.request, self.context
        if (
            digest(request.model_dump(mode="json")) != self.request_hash
            or digest(context.model_dump(mode="json")) != self.context_hash
            or digest([e.model_dump(mode="json") for e in self.evidence_snapshot])
            != self.evidence_hash
            or request.context_hash != self.context_hash
            or request.target_plan_id != context.target_plan_id
            or request.source_rule_preparation_id != context.source_rule_preparation_id
            or request.source_rule_candidate_id != context.source_rule_candidate_id
            or [e.model_dump(mode="json") for e in request.evidence]
            != [
                {k: e.model_dump(mode="json")[k] for k in ("member_id", "block_id", "quote")}
                for e in self.evidence_snapshot
            ]
        ):
            raise ValueError("group applicability receipt differs from request or evidence")
        return self


class GroupApplicabilityHistory(GroupContract):
    scope: Literal["GROUP_APPLICABILITY_REVIEW_ONLY"]
    context: GroupApplicabilityContext
    context_hash: Sha256
    source_review: GroupRuleReviewRecord
    target_plan: GroupApplicabilityPlan
    candidate: GroupRuleReviewRow
    approval: GroupRuleDecisionView
    history: tuple[GroupApplicabilityReceipt, ...]
    latest: GroupApplicabilityReceipt | None

    @model_validator(mode="after")
    def require_exact_history(self) -> Self:
        data = self.model_dump(mode="json", exclude={"history", "latest", "scope"})
        GroupApplicabilityView.model_validate(
            data
            | {
                "scope": "GROUP_APPLICABILITY_CONTEXT_ONLY",
                "outcome": "UNDECIDED",
                "evidence_options": [],
                "next_cursor": None,
            }
        )
        expected = self.context.model_dump(mode="json", exclude={"source_review_hash"})
        partial = self.source_review.model_dump(mode="json")
        partial["history"], partial["decisions"] = [], {}
        prefixes = {}
        for approval in self.source_review.history:
            item = approval.model_dump(mode="json")
            partial["history"].append(item)
            partial["decisions"][str(approval.rule_candidate_id)] = item
            selected = partial["decisions"].get(str(self.context.source_rule_candidate_id))
            if selected and selected["decision_id"] == str(self.context.source_rule_approval_id):
                prefixes[digest(partial)] = approval.created_at
        previous = None
        for sequence, row in enumerate(self.history, 1):
            if (
                row.sequence != sequence
                or row.request.previous_decision_id != (previous.decision_id if previous else None)
                or row.context.model_dump(mode="json", exclude={"source_review_hash"}) != expected
                or row.context.source_review_hash not in prefixes
                or prefixes[row.context.source_review_hash] > row.created_at
                or (previous is not None and row.created_at < previous.created_at)
            ):
                raise ValueError("group applicability history differs from current target")
            previous = row
        if self.latest != previous:
            raise ValueError("latest differs from final history record")
        return self
