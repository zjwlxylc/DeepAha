"""Strict private response boundary for scope projection, never qualification."""

from typing import Annotated, Any, Literal, Self

from pydantic import AfterValidator, TypeAdapter, model_validator

from deepaha.contracts.common import EntityId, Instant, Sha256
from deepaha.investigations.contracts import digest
from deepaha.investigations.group_applicability_contracts import GroupApplicabilityContext
from deepaha.investigations.group_applicability_decision_contracts import (
    GroupApplicabilityBoundEvidence,
    GroupApplicabilityHistory,
    GroupApplicabilityReceipt,
)
from deepaha.investigations.group_applicability_decisions import DecideGroupApplicability
from deepaha.investigations.group_contracts import (
    GroupContract,
    GroupSourceContext,
    GroupSourceRecord,
)
from deepaha.investigations.group_inheritance import _condition
from deepaha.investigations.group_rule_contracts import GroupRulePreview
from deepaha.investigations.group_rule_review_contracts import (
    GroupRuleDecisionView,
    GroupRuleReviewRecord,
    GroupRuleReviewRow,
)
from deepaha.unit_qualification.contracts import CoverageCondition, UnitQualificationPlan

Version = Literal["group-inheritance-preview/1.0.0"]


def _original_instant(value: str) -> str:
    TypeAdapter(Instant).validate_python(value)
    return value


OriginalInstant = Annotated[str, AfterValidator(_original_instant)]


class OriginalPlan(GroupContract):
    plan_id: EntityId
    plan: UnitQualificationPlan
    plan_hash: Sha256
    context: dict[str, Any]
    context_hash: Sha256
    reviewer_id: EntityId
    created_at: OriginalInstant


class OriginalReceipt(GroupContract):
    decision_id: EntityId
    sequence: int
    request: DecideGroupApplicability
    request_hash: Sha256
    context: GroupApplicabilityContext
    context_hash: Sha256
    evidence_snapshot: tuple[GroupApplicabilityBoundEvidence, ...]
    evidence_hash: Sha256
    reviewer_id: EntityId
    created_at: OriginalInstant

    @model_validator(mode="after")
    def require_receipt(self) -> Self:
        GroupApplicabilityReceipt.model_validate(self.model_dump(mode="json"))
        return self


class GroupInheritanceSource(GroupContract):
    entity_id: str
    source: GroupSourceContext
    registration: GroupSourceRecord | None
    rule_preview: GroupRulePreview | None
    rule_review: GroupRuleReviewRecord | None
    applicability_histories: dict[str, tuple[OriginalReceipt, ...]]


class GroupInheritanceDependencies(GroupContract):
    contract_version: Version
    base_v2: OriginalPlan
    group_source: GroupInheritanceSource


class GroupInheritedCondition(GroupContract):
    condition: CoverageCondition
    disposition: Literal["INHERIT", "EXCLUDE", "UNRESOLVED"]
    reason: str
    source_rule: GroupRuleReviewRow | None
    approval: GroupRuleDecisionView | None
    applicability: OriginalReceipt | None


class GroupInheritanceSnapshot(GroupContract):
    contract_version: Version
    scope: Literal["GROUP_INHERITANCE_PREVIEW_ONLY"]
    base_v2: OriginalPlan
    group_conditions: tuple[GroupInheritedCondition, ...]
    overall_qualification: Literal["UNCERTAIN"]


class GroupInheritancePreview(GroupContract):
    dependencies: GroupInheritanceDependencies
    dependencies_hash: Sha256
    snapshot: GroupInheritanceSnapshot
    snapshot_hash: Sha256

    @model_validator(mode="after")
    def require_exact_projection(self) -> Self:
        dep, snap = self.dependencies, self.snapshot
        base, group = dep.base_v2, dep.group_source
        source, registration, preview, review = (
            group.source,
            group.registration,
            group.rule_preview,
            group.rule_review,
        )
        context = base.context
        conditions = [c for c in base.plan.manifest.conditions if c.scope == "EMPLOYER_GROUP"]
        originals = source.source_group.get("unit_level", [])
        if len(conditions) != len(originals):
            raise ValueError("group condition denominator differs from frozen source")
        member = next(
            (
                m
                for m in source.members
                if m.position_binding
                and m.position_binding.opportunity_unit_id == base.plan.target.unit_id
            ),
            None,
        )
        if (
            digest(dep.model_dump(mode="json")) != self.dependencies_hash
            or digest(snap.model_dump(mode="json")) != self.snapshot_hash
            or snap.base_v2 != base
            or base.plan_id != base.plan.qualification_plan_id
            or digest(base.plan.model_dump(mode="json")) != base.plan_hash
            or digest(context) != base.context_hash
            or str(source.binding_id) != context["binding_id"]
            or source.delivery_hash != context["delivery_hash"]
            or str(source.source_bundle_revision_id) != context["source_bundle_revision_id"]
            or source.opportunity_id != base.plan.target.opportunity_id
            or source.opportunity_version != base.plan.target.opportunity_version
            or group.entity_id != source.source_entity["id"]
            or any(c.source_entity_id != group.entity_id for c in conditions)
            or member is None
            or member.position_binding is None
            or member.position_binding.opportunity_unit_id != base.plan.target.unit_id
            or member.position_binding.opportunity_unit_version_id
            != base.plan.target.unit_version_id
        ):
            raise ValueError("group projection identity or digest differs")
        if registration is not None and (
            registration.source != source
            or registration.source_hash != digest(source.model_dump(mode="json"))
        ):
            raise ValueError("group registration differs")
        if preview is not None:
            facts = preview.result.fact_review
            if (
                registration is None
                or facts.result.group_source != registration
                or str(facts.result.check_id) != context["check_id"]
                or digest(facts.result.model_dump(mode="json")) != facts.result_hash
                or digest(preview.result.model_dump(mode="json")) != preview.result_hash
                or [r.source_index for r in facts.result.rows]
                != [c.source_index for c in conditions]
            ):
                raise ValueError("group facts differ from full source denominator")
            if [r.source_index for r in preview.result.rows] != [
                c.source_index for c in conditions
            ]:
                raise ValueError("group rule denominator differs")
            for row, raw, rule in zip(
                facts.result.rows, originals, preview.result.rows, strict=True
            ):
                original = row.original
                if (
                    row.entity_id != group.entity_id
                    or original.get("entity_id") != group.entity_id
                    or any(original.get(k) != raw.get(k) for k in ("field", "value", "status"))
                    or ("note" in original and original["note"] != raw.get("note"))
                    or row.original_field != original.get("field")
                    or row.original_status != original.get("status")
                    or row.raw_value != original.get("value")
                    or [e.reference for e in row.evidence] != original.get("evidence")
                    or [
                        {
                            "artifact_id": e.get("artifact_id"),
                            "quote": e.get("quote"),
                            "locator": e.get("locator", {}),
                        }
                        for e in original.get("evidence", [])
                    ]
                    != [
                        {
                            "artifact_id": e.get("artifact_id"),
                            "quote": e.get("quote"),
                            "locator": e.get("locator", {}),
                        }
                        for e in raw.get("evidence", [])
                    ]
                    or rule.candidate_id != row.candidate_id
                ):
                    raise ValueError("group displayed fact differs from frozen original")
        if review is not None and (
            preview is None
            or review.result.preview != preview
            or digest(review.result.model_dump(mode="json")) != review.result_hash
        ):
            raise ValueError("group review differs from current preview")
        if (
            review is not None
            and preview is not None
            and (
                [
                    r.model_dump(mode="json", exclude={"rule_candidate_id"})
                    for r in review.result.rows
                ]
                != [r.model_dump(mode="json") for r in preview.result.rows]
            )
        ):
            raise ValueError("review rows differ from full rule preview")
        approved = (
            {
                str(row.rule_candidate_id): row
                for row in review.result.rows
                if row.rule_candidate_id
                and review.decisions.get(str(row.rule_candidate_id))
                and review.decisions[str(row.rule_candidate_id)].decision == "APPROVE"
            }
            if review
            else {}
        )
        if set(group.applicability_histories) != set(approved):
            raise ValueError("group applicability denominator differs")
        for candidate_id, history in group.applicability_histories.items():
            if not history:
                continue
            assert review is not None
            ctx = history[-1].context.model_dump(mode="json")
            ctx["source_review_hash"] = digest(review.model_dump(mode="json"))
            if (
                ctx["task_id"] != str(source.task_id)
                or ctx["binding_id"] != context["binding_id"]
                or ctx["check_id"] != context["check_id"]
                or ctx["target_entity_id"] != member.entity_id
                or ctx["source_bundle_revision_id"] != context["source_bundle_revision_id"]
            ):
                raise ValueError("group history differs from target context")
            GroupApplicabilityHistory.model_validate(
                {
                    "scope": "GROUP_APPLICABILITY_REVIEW_ONLY",
                    "context": ctx,
                    "context_hash": digest(ctx),
                    "source_review": review,
                    "target_plan": base.model_dump(mode="json"),
                    "candidate": approved[candidate_id],
                    "approval": review.decisions[candidate_id],
                    "history": [r.model_dump(mode="json") for r in history],
                    "latest": history[-1].model_dump(mode="json"),
                }
            )
        data = group.model_dump(mode="json")
        try:
            expected = [_condition(c.model_dump(mode="json"), data) for c in conditions]
        except (KeyError, StopIteration, TypeError) as error:
            raise ValueError("incomplete group projection dependencies") from error
        if expected != [r.model_dump(mode="json") for r in snap.group_conditions]:
            raise ValueError("group conditions differ from exact decisions")
        return self
