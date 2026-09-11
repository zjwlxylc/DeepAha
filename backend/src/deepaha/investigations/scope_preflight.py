"""Current scope gaps for reviewers, not a completeness receipt or executable plan."""

from copy import deepcopy
from datetime import datetime
from itertools import combinations
from typing import Any
from uuid import UUID

from sqlalchemy import select

from deepaha.contracts.common import normalize_instant
from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.cross_level_preview import _build
from deepaha.investigations.models import InvestigationRelationProposal
from deepaha.investigations.relation_decisions import _history
from deepaha.investigations.relation_proposals import _recheck
from deepaha.investigations.store import InvestigationStore
from deepaha.local_human_test.review import require_human_fact_reviewer
from deepaha.review.auth import ReviewerPrincipal
from deepaha.unit_qualification.compiler import compile_unit_qualification
from deepaha.unit_qualification.contracts import UnitQualificationPlan

MAX_RELATIONS = 200


def project_scope_preflight(
    current: dict[str, Any], relations: list[dict[str, Any]], *, as_of: datetime
) -> dict[str, Any]:
    """Internal projection of authorized, rechecked DB inputs; never a client API."""
    now = normalize_instant(as_of)
    base = current["dependencies"]["group"]["snapshot"]["base_v2"]
    context = base["context"]
    plan = UnitQualificationPlan.model_validate(base["plan"])
    represented = [c.source_index for c in plan.manifest.conditions] + [
        row["source_index"] for row in context["excluded_source_rows"]
    ]
    if [row["condition"] for row in current["snapshot"]["conditions"]] != [
        c.model_dump(mode="json") for c in plan.manifest.conditions
    ] or sorted(represented) != list(range(context["source_row_count"])):
        raise ValueError("scope preflight requires the complete source denominator")
    compiled = compile_unit_qualification(plan, evidence_as_of=now)
    blockers = set(current["snapshot"]["blockers"]) | {
        "HUMAN_SCOPE_REVIEW_UNVERIFIED",
        "SCOPE_PREFLIGHT_REVIEW_ONLY",
    }
    conditions = []
    for row in current["snapshot"]["conditions"]:
        condition = row["condition"]
        issues = []
        if row["disposition"] == "UNRESOLVED":
            issues.append("APPLICABILITY_UNRESOLVED")
        if row["disposition"] == "LOCAL" and condition["state"] != "KNOWN":
            issues.append(f"CONDITION_{condition['state']}")
        conditions.append(
            {
                "condition_id": condition["condition_id"],
                "scope": condition["scope"],
                "field_name": condition["field_name"],
                "state": condition["state"],
                "disposition": row["disposition"],
                "source_pointer": row["source_pointer"],
                "issues": issues,
            }
        )
        blockers.update(issues)
    active = [r for r in conditions if r["disposition"] in {"LOCAL", "INHERITED"}]
    approved = [r for r in relations if r["status"] == "APPROVED"]
    uncovered = [
        [a["condition_id"], b["condition_id"]]
        for a, b in combinations(active, 2)
        if a["scope"] != b["scope"]
        and a["field_name"] == b["field_name"]
        and not any(
            {a["condition_id"], b["condition_id"]} <= set(r["condition_ids"])
            and r["relation"] in {"CUMULATIVE", "EXCEPTION"}
            for r in approved
        )
    ]
    overlapping = [
        [a["proposal_id"], b["proposal_id"]]
        for a, b in combinations(approved, 2)
        if set(a["condition_ids"]) & set(b["condition_ids"])
    ]
    if uncovered:
        blockers.add("CROSS_LEVEL_RELATION_COVERAGE_INCOMPLETE")
    if overlapping:
        blockers.add("OVERLAPPING_RELATIONS_REQUIRE_REVIEW")
    if any(r["relation"] == "CONFLICT" for r in approved):
        blockers.add("CROSS_LEVEL_CONFLICT_RECORDED")
    if any(r["relation"] == "EXCEPTION" for r in approved):
        blockers.add("EXCEPTION_EXECUTION_NOT_IMPLEMENTED")
    validity = []
    for admission in plan.admissions:
        for evidence in admission.evidence_validity:
            status = (
                "NOT_YET_VALID"
                if now < evidence.valid_from
                else "EXPIRED"
                if evidence.valid_until is not None and now >= evidence.valid_until
                else "END_NOT_ESTABLISHED"
                if evidence.valid_until is None
                else "WITHIN_RECORDED_INTERVAL"
            )
            validity.append(
                {
                    "rule_id": str(admission.rule_id),
                    **evidence.model_dump(mode="json"),
                    "status": status,
                }
            )
    # Null expiry is not evidence of indefinite validity. Inherited rules have
    # no approved time-boundary contract in the current review-only adapter.
    if context["evidence_valid_until_policy"] == "NOT_ESTABLISHED" or any(
        row["status"] == "END_NOT_ESTABLISHED" for row in validity
    ):
        blockers.add("EVIDENCE_TIME_BOUNDARIES_NOT_ESTABLISHED")
    if any(row["disposition"] == "INHERITED" for row in conditions):
        blockers.add("INHERITED_TIME_BOUNDARIES_NOT_REVIEWED")
    local_blockers = [
        {
            "code": b.code,
            "condition_id": b.condition_id,
            "rule_id": str(b.rule_id) if b.rule_id else None,
        }
        for b in compiled.coverage_blockers
    ]
    return {
        "contract_version": "unit-scope-preflight/1.0.0",
        "source_review_hash": digest(current),
        "as_of": now.isoformat(),
        "target": deepcopy(current["snapshot"]["target"]),
        "source_row_count": context["source_row_count"],
        "conditions": conditions,
        "excluded_source_rows": deepcopy(context["excluded_source_rows"]),
        "source_notes": deepcopy(context["source_notes"]),
        "unresolved_source_references": deepcopy(context["unresolved_source_references"]),
        "relations": deepcopy(relations),
        "uncovered_condition_pairs": uncovered,
        "overlapping_relation_pairs": overlapping,
        "local_evidence_validity": validity,
        "local_kernel_blockers": local_blockers,
        "blockers": sorted(blockers),
        "executable": False,
        "overall_qualification": "UNCERTAIN",
    }


def read_scope_preflight(
    store: InvestigationStore, task: UUID, plan: UUID, principal: ReviewerPrincipal
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        store._get(session, task, lock=True)
        current = _build(store, session, task, plan)
        rows = list(
            session.scalars(
                select(InvestigationRelationProposal)
                .where(
                    InvestigationRelationProposal.task_id == task,
                    InvestigationRelationProposal.target_plan_id == plan,
                )
                .order_by(InvestigationRelationProposal.proposal_id)
                .limit(MAX_RELATIONS + 1)
            )
        )
        if len(rows) > MAX_RELATIONS:
            raise InvestigationError("SCOPE_PREFLIGHT_RELATION_LIMIT")
        relations = []
        for row in rows:
            view = _history(store, session, row, current)
            proposal = view["package"]["proposal"]
            relations.append(
                {
                    "proposal_id": str(row.proposal_id),
                    "status": view["review"]["status"],
                    "relation": proposal["relation"],
                    "condition_ids": proposal["condition_ids"],
                    "payload_sha256": view["payload_sha256"],
                }
            )
        result = project_scope_preflight(current, relations, as_of=store.clock())
        _recheck(store, session, task, plan, principal, current)
        return {"task_id": str(task), "target_plan_id": str(plan), **result}
