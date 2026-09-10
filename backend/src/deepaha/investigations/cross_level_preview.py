"""Current, authorized cross-level review; no writes and no qualification execution."""

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from deepaha.investigations.announcement_sources import build_announcement_snapshot
from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import InvestigationError
from deepaha.investigations.cross_level_review import _compose_cross_level, replay_cross_level
from deepaha.investigations.group_inheritance import _assemble as build_group_snapshot
from deepaha.investigations.store import InvestigationStore
from deepaha.local_human_test.review import require_human_fact_reviewer
from deepaha.review.auth import ReviewerPrincipal


def _build(store: InvestigationStore, session: Session, task: UUID, plan: UUID) -> dict[str, Any]:
    announcement = build_announcement_snapshot(store, session, task, plan)
    group = build_group_snapshot(store, session, task, plan)
    # These are actual, authorized DB reconstructions, never a request payload.
    result = _compose_cross_level(announcement, group)
    return replay_cross_level(result, expected_dependencies_hash=result["dependencies_hash"])


def preview_cross_level(
    store: InvestigationStore, task: UUID, plan: UUID, principal: ReviewerPrincipal
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        initial = _build(store, session, task, plan)
        session.expire_all()
        _authorize(session, principal)
        current = _build(store, session, task, plan)
        if current != initial:
            raise InvestigationError("CROSS_LEVEL_INPUT_CHANGED")
        return current
