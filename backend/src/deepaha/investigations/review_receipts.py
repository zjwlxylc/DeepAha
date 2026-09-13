"""Read committed action identity without replaying a write or re-approving evidence."""

from hashlib import sha256
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select

from deepaha.investigations.bindings import _authorize
from deepaha.investigations.models import (
    InvestigationFactAction,
    InvestigationFactPreparation,
    InvestigationRuleDecision,
    InvestigationRulePreparation,
)
from deepaha.investigations.store import InvestigationStore
from deepaha.review.auth import ReviewerPrincipal


def read_review_receipt(
    store: InvestigationStore,
    task_id: UUID,
    kind: Literal["FACT", "RULE"],
    preparation_id: UUID,
    request_key: str,
    principal: ReviewerPrincipal,
) -> dict[str, Any]:
    key_hash = sha256(request_key.encode()).hexdigest()
    with store.factory() as session:
        _authorize(session, principal)
        store._get(session, task_id)
        if kind == "FACT":
            receipt = session.scalar(
                select(InvestigationFactAction.action_id)
                .join(InvestigationFactPreparation)
                .where(
                    InvestigationFactPreparation.task_id == task_id,
                    InvestigationFactAction.preparation_id == preparation_id,
                    InvestigationFactAction.reviewer_id == principal.reviewer_id,
                    InvestigationFactAction.request_key_hash == key_hash,
                )
            )
        else:
            receipt = session.scalar(
                select(InvestigationRuleDecision.decision_id)
                .join(InvestigationRulePreparation)
                .join(InvestigationFactPreparation)
                .where(
                    InvestigationFactPreparation.task_id == task_id,
                    InvestigationRuleDecision.rule_preparation_id == preparation_id,
                    InvestigationRuleDecision.reviewer_id == principal.reviewer_id,
                    InvestigationRuleDecision.request_key_hash == key_hash,
                )
            )
    return {
        "task_id": str(task_id),
        "committed": receipt is not None,
        "receipt_id": str(receipt) if receipt else None,
    }
