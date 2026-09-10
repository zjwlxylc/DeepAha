"""Append-only independent interpretations; never activate eligibility rules."""

import json
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID, uuid7

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.contracts.common import EntityId, Sha256
from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.cross_level_adjudication import (
    AdjudicationPackage,
    RelationDecision,
    RelationProposal,
    replay_adjudication,
)
from deepaha.investigations.cross_level_preview import _build
from deepaha.investigations.group_contracts import GroupContract
from deepaha.investigations.models import (
    InvestigationRelationDecision,
    InvestigationRelationProposal,
)
from deepaha.investigations.relation_proposals import _describe, _recheck
from deepaha.investigations.store import InvestigationStore
from deepaha.local_human_test.review import require_human_fact_reviewer, validate_idempotency_key
from deepaha.review.auth import ReviewerPrincipal


class DecideRelation(GroupContract):
    proposal_id: EntityId
    expected_proposal_payload_hash: Sha256
    previous_decision_id: EntityId | None
    decision: Literal["APPROVE", "REJECT", "NEEDS_ADJUDICATION"]
    reason: str = Field(min_length=1, max_length=2000)


def _history(
    store: InvestigationStore,
    session: Session,
    proposal: InvestigationRelationProposal,
    current: dict[str, Any],
) -> dict[str, Any]:
    result = _describe(store, session, proposal, current)
    package = result["package"]
    try:
        for row in session.scalars(
            select(InvestigationRelationDecision)
            .where(InvestigationRelationDecision.proposal_id == proposal.proposal_id)
            .order_by(InvestigationRelationDecision.sequence)
        ):
            raw = json.loads(row.payload_text)
            decision = RelationDecision.model_validate(raw)
            command = DecideRelation.model_validate(row.request)
            if (
                sha256(row.payload_text.encode()).hexdigest() != row.payload_sha256
                or digest(raw) != row.payload_sha256
                or digest(row.request) != row.request_hash
                or decision.decision_id != row.decision_id
                or decision.proposal_id != row.proposal_id
                or decision.reviewer_id != row.reviewer_id
                or decision.previous_decision_id != row.previous_decision_id
                or decision.sequence != row.sequence
                or decision.created_at != row.created_at
                or command.proposal_id != proposal.proposal_id
                or command.expected_proposal_payload_hash != proposal.payload_sha256
                or command.previous_decision_id != decision.previous_decision_id
                or command.decision != decision.decision
                or command.reason != decision.reason
            ):
                raise ValueError("decision binding differs")
            package["decisions"].append(raw)
        AdjudicationPackage.model_validate(package)
        package_hash = digest(package)
        result.update(
            payload_sha256=package_hash,
            review=replay_adjudication(
                package,
                expected_package_hash=package_hash,
                current_source_review=current,
                as_of=store.clock(),
            ),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise InvestigationError("RELATION_DECISION_INTEGRITY_FAILED") from exc
    return result


def save_relation_decision(
    store: InvestigationStore,
    task: UUID,
    command: DecideRelation,
    principal: ReviewerPrincipal,
    key: str,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    key_hash = sha256(validate_idempotency_key(key).encode()).hexdigest()
    request = command.model_dump(mode="json")
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        store._get(session, task, lock=True)
        proposal = session.get(InvestigationRelationProposal, command.proposal_id)
        if proposal is None or proposal.task_id != task:
            raise InvestigationError("RELATION_PROPOSAL_NOT_FOUND")
        if principal.reviewer_id == proposal.producer_id:
            raise InvestigationError("RELATION_INDEPENDENT_REVIEW_REQUIRED")
        if command.expected_proposal_payload_hash != proposal.payload_sha256:
            raise InvestigationError("RELATION_PROPOSAL_HASH_MISMATCH")
        current = _build(store, session, task, proposal.target_plan_id)
        view = _history(store, session, proposal, current)
        existing = session.scalar(
            select(InvestigationRelationDecision).where(
                InvestigationRelationDecision.proposal_id == proposal.proposal_id,
                InvestigationRelationDecision.reviewer_id == principal.reviewer_id,
                InvestigationRelationDecision.request_key_hash == key_hash,
            )
        )
        if existing is not None:
            if existing.request_hash != digest(request):
                raise InvestigationError("RELATION_DECISION_IDEMPOTENCY_CONFLICT")
            _recheck(store, session, task, proposal.target_plan_id, principal, current)
            return dict(view, decision=json.loads(existing.payload_text))
        if view["review"]["status"] == "STALE":
            raise InvestigationError("RELATION_PROPOSAL_CONTEXT_CHANGED")
        decisions = view["package"]["decisions"]
        previous = decisions[-1]["decision_id"] if decisions else None
        if (
            str(command.previous_decision_id) if command.previous_decision_id else None
        ) != previous:
            raise InvestigationError("RELATION_DECISION_PREVIOUS_CHANGED")
        try:
            decision = RelationDecision.model_validate(
                dict(
                    decision_id=uuid7(),
                    proposal_id=proposal.proposal_id,
                    proposal_hash=digest(
                        RelationProposal.model_validate(view["package"]["proposal"]).model_dump(
                            mode="json"
                        )
                    ),
                    sequence=len(decisions) + 1,
                    previous_decision_id=command.previous_decision_id,
                    reviewer_id=principal.reviewer_id,
                    created_at=store.clock(),
                    decision=command.decision,
                    reason=command.reason,
                )
            )
            raw = decision.model_dump(mode="json")
            AdjudicationPackage.model_validate(
                dict(proposal=view["package"]["proposal"], decisions=[*decisions, raw])
            )
        except ValueError as exc:
            raise InvestigationError("RELATION_DECISION_INVALID") from exc
        _recheck(store, session, task, proposal.target_plan_id, principal, current)
        session.add(
            InvestigationRelationDecision(
                decision_id=decision.decision_id,
                proposal_id=proposal.proposal_id,
                previous_decision_id=decision.previous_decision_id,
                sequence=decision.sequence,
                reviewer_id=principal.reviewer_id,
                request_key_hash=key_hash,
                request_hash=digest(request),
                request=request,
                payload_text=json.dumps(
                    raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
                ),
                payload_sha256=digest(raw),
                created_at=decision.created_at,
            )
        )
        session.flush()
        result = dict(_history(store, session, proposal, current), decision=raw)
        _recheck(store, session, task, proposal.target_plan_id, principal, current)
        return result
