"""Bounded, authenticated current-state navigation; never an executable plan."""

from typing import Any
from uuid import UUID

from sqlalchemy import select

from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import digest
from deepaha.investigations.cross_level_preview import _build
from deepaha.investigations.models import InvestigationRelationProposal
from deepaha.investigations.relation_decisions import _history
from deepaha.investigations.relation_proposals import _recheck
from deepaha.investigations.store import InvestigationStore
from deepaha.local_human_test.review import require_human_fact_reviewer
from deepaha.review.auth import ReviewerPrincipal


def read_relation_queue(
    store: InvestigationStore,
    task: UUID,
    plan: UUID,
    principal: ReviewerPrincipal,
    after: UUID | None = None,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        # Serialize with proposal/decision writers so one page is a coherent read.
        store._get(session, task, lock=True)
        current = _build(store, session, task, plan)
        query = select(InvestigationRelationProposal).where(
            InvestigationRelationProposal.task_id == task,
            InvestigationRelationProposal.target_plan_id == plan,
        )
        if after is not None:
            query = query.where(InvestigationRelationProposal.proposal_id > after)
        rows = list(
            session.scalars(query.order_by(InvestigationRelationProposal.proposal_id).limit(51))
        )
        proposals = []
        for row in rows[:50]:
            view = _history(store, session, row, current)
            proposal = view["package"]["proposal"]
            proposals.append(
                {
                    "proposal_id": str(row.proposal_id),
                    "created_at": row.created_at.isoformat(),
                    "relation": proposal["relation"],
                    "reason": proposal["reason"],
                    "condition_ids": proposal["condition_ids"],
                    "status": view["review"]["status"],
                    "is_own_proposal": row.producer_id == principal.reviewer_id,
                }
            )
        _recheck(store, session, task, plan, principal, current)
        return {
            "task_id": str(task),
            "target_plan_id": str(plan),
            "source_review_hash": digest(current),
            "read_at": store.clock().isoformat(),
            "executable": False,
            "overall_qualification": "UNCERTAIN",
            "proposals": proposals,
            "next_after": str(rows[49].proposal_id) if len(rows) > 50 else None,
        }
