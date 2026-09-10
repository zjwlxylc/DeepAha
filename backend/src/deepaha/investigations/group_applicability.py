"""Read-only exact GROUP-to-POSITION review context; no rule inheritance."""

from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from deepaha.documents.models import DocumentBlock
from deepaha.investigations.applicability import _blocks, _command, _material_url
from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.group_applicability_contracts import GroupApplicabilityContext
from deepaha.investigations.group_rule_review import _checked, _view
from deepaha.investigations.models import (
    InvestigationGroupBinding,
    InvestigationGroupFactPreparation,
    InvestigationGroupRulePreparation,
    InvestigationUnitPlan,
)
from deepaha.investigations.store import InvestigationStore
from deepaha.investigations.unit_snapshots import _build, _checked_view
from deepaha.local_human_test.review import require_human_fact_reviewer
from deepaha.p9b.models import OpportunityUnit, SourceBundleMember, VersionedVerifiedFactSet
from deepaha.review.auth import ReviewerPrincipal


def _context(
    store: InvestigationStore,
    session: Session,
    task: UUID,
    plan_id: UUID,
    source_id: UUID,
    candidate_id: UUID,
) -> dict[str, Any]:
    store._get(session, task, lock=True)
    record = session.get(InvestigationUnitPlan, plan_id)
    if record is None:
        raise InvestigationError("UNIT_PLAN_NOT_FOUND")
    command = _command(session, task, record.rule_preparation_id)
    plan, plan_context = _build(store, session, task, command, plan_id)
    target_view = _checked_view(record, plan, plan_context)
    unit = session.get(OpportunityUnit, plan.target.unit_id)
    prep = _checked(store, session, task, source_id)
    review = _view(store, session, prep)
    facts = review["result"]["preview"]["result"]["fact_review"]["result"]
    group = facts["group_source"]
    source = group["source"]
    member = next((m for m in source["members"] if m["entity_id"] == command.entity_id), None)
    expected_binding = {
        "entity_id": command.entity_id,
        "opportunity_unit_id": str(plan.target.unit_id),
        "opportunity_unit_version_id": str(plan.target.unit_version_id),
    }
    if (
        unit is None
        or unit.unit_kind != "POSITION"
        or unit.current_version_id != plan.target.unit_version_id
        or source["task_id"] != str(task)
        or source["binding_id"] != str(command.binding_id)
        or source["delivery_hash"] != command.delivery_hash
        or facts["check_id"] != str(command.check_id)
        or source["source_bundle_revision_id"] != plan_context["source_bundle_revision_id"]
        or source["opportunity_id"] != str(plan.target.opportunity_id)
        or source["opportunity_version"] != plan.target.opportunity_version
        or member is None
        or member["state"] != "BOUND"
        or member["position_binding"] != expected_binding
    ):
        raise InvestigationError("GROUP_APPLICABILITY_SOURCE_CONFLICT")
    candidate = next(
        (r for r in review["result"]["rows"] if r["rule_candidate_id"] == str(candidate_id)), None
    )
    approval = review["decisions"].get(str(candidate_id))
    if candidate is None or approval is None or approval["decision"] != "APPROVE":
        raise InvestigationError("GROUP_APPLICABILITY_SOURCE_NOT_APPROVED")
    context = {
        "contract_version": "group-rule-applicability-context/1.0.0",
        "task_id": str(task),
        "target_plan_id": str(plan_id),
        "target_plan_hash": record.plan_hash,
        "target_plan_context_hash": record.context_hash,
        "target": plan.target.model_dump(mode="json"),
        "target_entity_id": command.entity_id,
        "source_group": group["group_identity"],
        "group_binding_id": group["group_binding_id"],
        "group_source_hash": group["source_hash"],
        "member": member,
        "binding_id": source["binding_id"],
        "check_id": facts["check_id"],
        "source_bundle_revision_id": source["source_bundle_revision_id"],
        "source_rule_preparation_id": str(source_id),
        "source_rule_preparation_hash": prep.result_hash,
        "source_rule_candidate_id": str(candidate_id),
        "source_rule_approval_id": approval["decision_id"],
        "source_rule_approval_hash": digest(approval),
        "source_review_hash": digest(review),
    }
    context = GroupApplicabilityContext.model_validate(context).model_dump(mode="json")
    return {
        "context": context,
        "context_hash": digest(context),
        "source_review": review,
        "target_plan": target_view,
        "candidate": candidate,
        "approval": approval,
    }


def read_group_rule_applicability(
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
        view = _context(store, session, task_id, plan_id, source_id, candidate_id)
        context = view["context"]
        query = _blocks(session, context)
        if after is not None:
            try:
                block_after, member_after = (UUID(part) for part in after.split(":"))
            except ValueError as error:
                raise InvestigationError("GROUP_APPLICABILITY_CURSOR_INVALID") from error
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
        options = [
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
        ]
        # Reconstruct again after the evidence reads: cached approvals cannot hide an append.
        session.expire_all()
        if _context(store, session, task_id, plan_id, source_id, candidate_id) != view:
            raise InvestigationError("GROUP_APPLICABILITY_CONTEXT_CHANGED")
        return view | {
            "scope": "GROUP_APPLICABILITY_CONTEXT_ONLY",
            "outcome": "UNDECIDED",
            "evidence_options": options,
            "next_cursor": f"{blocks[49][1].block_id}:{blocks[49][0].source_bundle_member_id}"
            if len(blocks) > 50
            else None,
        }


def list_group_rule_contexts(
    store: InvestigationStore,
    task_id: UUID,
    plan_id: UUID,
    principal: ReviewerPrincipal,
) -> list[dict[str, Any]]:
    """Discover saved approved sources, never infer that missing sources mean no conditions."""
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        task = store._get(session, task_id, lock=True)
        record = session.get(InvestigationUnitPlan, plan_id)
        if record is None:
            raise InvestigationError("UNIT_PLAN_NOT_FOUND")
        command = _command(session, task_id, record.rule_preparation_id)
        plan, context = _build(store, session, task_id, command, plan_id)
        _checked_view(record, plan, context)
        evidence = cast(dict[str, Any], (task.delivery or {}).get("evidence", {}))
        entities = cast(list[dict[str, Any]], evidence.get("entities", []))
        target_entity = next((e for e in entities if e["id"] == command.entity_id), None)
        if target_entity is None or target_entity["kind"] != "position":
            raise InvestigationError("GROUP_APPLICABILITY_SOURCE_CONFLICT")
        preparations = list(
            session.scalars(
                select(InvestigationGroupRulePreparation)
                .join(
                    InvestigationGroupFactPreparation,
                    InvestigationGroupFactPreparation.preparation_id
                    == InvestigationGroupRulePreparation.fact_preparation_id,
                )
                .join(
                    InvestigationGroupBinding,
                    InvestigationGroupBinding.group_binding_id
                    == InvestigationGroupFactPreparation.group_binding_id,
                )
                .join(
                    VersionedVerifiedFactSet,
                    VersionedVerifiedFactSet.verified_fact_set_id
                    == InvestigationGroupRulePreparation.fact_set_id,
                )
                .where(
                    InvestigationGroupBinding.task_id == task_id,
                    InvestigationGroupBinding.binding_id == command.binding_id,
                    InvestigationGroupBinding.source_entity_id == target_entity["parent_id"],
                    InvestigationGroupFactPreparation.check_id == command.check_id,
                    VersionedVerifiedFactSet.status == "ACTIVE",
                )
                .order_by(InvestigationGroupRulePreparation.preparation_id)
            )
        )
        contexts = []
        for prep in preparations:
            review = _view(store, session, _checked(store, session, task_id, prep.preparation_id))
            source = review["result"]["preview"]["result"]["fact_review"]["result"]["group_source"][
                "source"
            ]
            if not any(m["entity_id"] == command.entity_id for m in source["members"]):
                continue
            for row in review["result"]["rows"]:
                candidate = row["rule_candidate_id"]
                if (
                    candidate
                    and review["decisions"].get(candidate, {}).get("decision") == "APPROVE"
                ):
                    contexts.append(
                        _context(
                            store, session, task_id, plan_id, prep.preparation_id, UUID(candidate)
                        )["context"]
                    )
        return contexts
