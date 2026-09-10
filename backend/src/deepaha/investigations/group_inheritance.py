"""Current GROUP scope projection, never an executable qualification plan."""

from copy import deepcopy
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.investigations.applicability import _command
from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.group_applicability import _context as applicability_context
from deepaha.investigations.group_applicability_decisions import _history
from deepaha.investigations.group_bindings import _latest_group
from deepaha.investigations.group_bindings import _view as group_view
from deepaha.investigations.group_fact_contracts import GROUP_FACT_VERSION
from deepaha.investigations.group_rule_review import _checked
from deepaha.investigations.group_rule_review import _view as rule_view
from deepaha.investigations.group_rule_review_contracts import GROUP_RULE_REVIEW_VERSION
from deepaha.investigations.group_rules import build_group_rule_preview
from deepaha.investigations.group_sources import build_group_source
from deepaha.investigations.models import (
    InvestigationGroupApplicability,
    InvestigationGroupFactPreparation,
    InvestigationGroupRulePreparation,
    InvestigationUnitPlan,
)
from deepaha.investigations.store import InvestigationStore
from deepaha.investigations.unit_snapshots import _build, _checked_view
from deepaha.local_human_test.review import require_human_fact_reviewer
from deepaha.review.auth import ReviewerPrincipal

GROUP_INHERITANCE_VERSION = "group-inheritance-preview/1.0.0"


def _source(
    store: InvestigationStore,
    session: Session,
    task: UUID,
    plan: UUID,
    entity: str,
    check: UUID,
) -> dict[str, Any]:
    source = build_group_source(store, session, task, entity)
    result: dict[str, Any] = {
        "entity_id": entity,
        "source": source,
        "registration": None,
        "rule_preview": None,
        "rule_review": None,
        "applicability_histories": {},
    }
    group = _latest_group(session, task, entity)
    if group is None:
        return result
    result["registration"] = group_view(session, group, source)
    facts = session.scalar(
        select(InvestigationGroupFactPreparation).where(
            InvestigationGroupFactPreparation.group_binding_id == group.group_binding_id,
            InvestigationGroupFactPreparation.check_id == check,
            InvestigationGroupFactPreparation.mapping_version == GROUP_FACT_VERSION,
        )
    )
    if facts is None:
        return result
    preview = build_group_rule_preview(store, session, task, facts.preparation_id)
    result["rule_preview"] = preview
    saved = preview["result"]["fact_review"]["fact_set"]
    if saved is None:
        return result
    preparation = session.scalar(
        select(InvestigationGroupRulePreparation).where(
            InvestigationGroupRulePreparation.fact_preparation_id == facts.preparation_id,
            InvestigationGroupRulePreparation.fact_set_id == UUID(saved["fact_set_id"]),
            InvestigationGroupRulePreparation.compiler_version == GROUP_RULE_REVIEW_VERSION,
        )
    )
    if preparation is None:
        return result
    review = rule_view(store, session, _checked(store, session, task, preparation.preparation_id))
    result["rule_review"] = review
    for row in review["result"]["rows"]:
        candidate = row["rule_candidate_id"]
        if candidate and review["decisions"].get(candidate, {}).get("decision") == "APPROVE":
            context = applicability_context(
                store, session, task, plan, preparation.preparation_id, UUID(candidate)
            )
            result["applicability_histories"][candidate] = _history(
                store, session, context["context"], context["source_review"]
            )
    return result


def _condition(condition: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    result = {
        "condition": deepcopy(condition),
        "disposition": "UNRESOLVED",
        "reason": "GROUP_SOURCE_NOT_REGISTERED",
        "source_rule": None,
        "approval": None,
        "applicability": None,
    }
    if source["registration"] is None:
        return result
    result["reason"] = "GROUP_FACTS_NOT_PREPARED"
    preview = source["rule_preview"]
    if preview is None:
        return result
    row = next(
        r for r in preview["result"]["rows"] if r["source_index"] == condition["source_index"]
    )
    result["reason"] = row["reason_code"]
    if row["proposed_rule_payload"] is None:
        return result
    review = source["rule_review"]
    result["reason"] = "GROUP_RULE_REVIEW_NOT_PREPARED"
    if review is None:
        return result
    rule = next(
        r for r in review["result"]["rows"] if r["source_index"] == condition["source_index"]
    )
    result["source_rule"] = deepcopy(rule)
    approval = review["decisions"].get(rule["rule_candidate_id"])
    result["approval"] = deepcopy(approval)
    result["reason"] = "GROUP_RULE_NOT_REVIEWED"
    if approval is None:
        return result
    if approval["decision"] != "APPROVE":
        result["reason"] = "GROUP_RULE_" + approval["decision"]
        return result
    history = source["applicability_histories"][rule["rule_candidate_id"]]
    result["reason"] = "GROUP_APPLICABILITY_NOT_REVIEWED"
    if not history:
        return result
    latest = history[-1]
    result["applicability"] = deepcopy(latest)
    outcome = latest["request"]["outcome"]
    result["reason"] = "GROUP_APPLICABILITY_" + outcome
    result["disposition"] = {
        "APPLIES": "INHERIT",
        "DOES_NOT_APPLY": "EXCLUDE",
        "NEEDS_ADJUDICATION": "UNRESOLVED",
    }[outcome]
    return result


def _assemble(
    store: InvestigationStore, session: Session, task_id: UUID, plan_id: UUID
) -> dict[str, Any]:
    task = store._get(session, task_id, lock=True)
    record = session.get(InvestigationUnitPlan, plan_id)
    if record is None:
        raise InvestigationError("UNIT_PLAN_NOT_FOUND")
    command = _command(session, task_id, record.rule_preparation_id)
    plan, context = _build(store, session, task_id, command, plan_id)
    base = _checked_view(record, plan, context)
    delivery = cast(dict[str, Any], task.delivery or {})
    entities = delivery.get("evidence", {}).get("entities", [])
    target = next((e for e in entities if e["id"] == command.entity_id), None)
    if target is None or target["kind"] != "position":
        raise InvestigationError("GROUP_INHERITANCE_TARGET_INVALID")
    parent = target["parent_id"]
    conditions = [
        c for c in base["plan"]["manifest"]["conditions"] if c["scope"] == "EMPLOYER_GROUP"
    ]
    originals = [
        (i, f) for i, f in enumerate(delivery.get("facts", [])) if f["entity_id"] == parent
    ]
    if [(c["source_index"], c["source_entity_id"]) for c in conditions] != [
        (i, parent) for i, _ in originals
    ]:
        raise InvestigationError("GROUP_INHERITANCE_DENOMINATOR_INVALID")
    source = _source(store, session, task_id, plan_id, parent, command.check_id)
    member = next(
        (m for m in source["source"]["members"] if m["entity_id"] == command.entity_id), None
    )
    if member is None or member["position_binding"] != {
        "entity_id": command.entity_id,
        "opportunity_unit_id": str(plan.target.unit_id),
        "opportunity_unit_version_id": str(plan.target.unit_version_id),
    }:
        raise InvestigationError("GROUP_INHERITANCE_MEMBER_INVALID")
    preview = source["rule_preview"]
    if preview is not None:
        source_rows = preview["result"]["fact_review"]["result"]["rows"]
        if [(r["source_index"], r["original"]) for r in source_rows] != originals:
            raise InvestigationError("GROUP_INHERITANCE_DENOMINATOR_INVALID")
    represented = {
        r["decision_id"] for history in source["applicability_histories"].values() for r in history
    }
    actual = {
        str(key)
        for key in session.scalars(
            select(InvestigationGroupApplicability.decision_id).where(
                InvestigationGroupApplicability.target_plan_id == plan_id
            )
        )
    }
    if represented != actual:
        raise InvestigationError("GROUP_INHERITANCE_APPLICABILITY_CONFLICT")
    dependencies = {
        "contract_version": GROUP_INHERITANCE_VERSION,
        "base_v2": base,
        "group_source": source,
    }
    snapshot = {
        "contract_version": GROUP_INHERITANCE_VERSION,
        "scope": "GROUP_INHERITANCE_PREVIEW_ONLY",
        "base_v2": deepcopy(base),
        "group_conditions": [_condition(c, source) for c in conditions],
        "overall_qualification": "UNCERTAIN",
    }
    return {
        "dependencies": dependencies,
        "dependencies_hash": digest(dependencies),
        "snapshot": snapshot,
        "snapshot_hash": digest(snapshot),
    }


def preview_group_inheritance(
    store: InvestigationStore, task_id: UUID, plan_id: UUID, principal: ReviewerPrincipal
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        result = _assemble(store, session, task_id, plan_id)
        session.expire_all()
        _authorize(session, principal)
        current = _assemble(store, session, task_id, plan_id)
        if current != result:
            raise InvestigationError("GROUP_INHERITANCE_INPUT_CHANGED")
        return current
