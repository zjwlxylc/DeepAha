"""Append-only GROUP scope adjudication, separate from inherited qualification."""

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID, uuid7

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.investigations.applicability import DecideRuleApplicability, _bound_evidence
from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.group_applicability import _context
from deepaha.investigations.models import InvestigationGroupApplicability
from deepaha.investigations.store import InvestigationStore
from deepaha.local_human_test.review import require_human_fact_reviewer, validate_idempotency_key
from deepaha.review.auth import ReviewerPrincipal


class DecideGroupApplicability(DecideRuleApplicability):
    contract_version: Literal["group-applicability-decision/1.0.0"] = (
        "group-applicability-decision/1.0.0"
    )


def _describe(
    store: InvestigationStore,
    session: Session,
    row: InvestigationGroupApplicability,
    context: dict[str, Any],
    review_prefixes: dict[str, datetime] | None = None,
) -> dict[str, Any]:
    try:
        command = DecideGroupApplicability.model_validate(row.request)
    except ValidationError as error:
        raise InvestigationError("GROUP_APPLICABILITY_INTEGRITY_FAILED") from error
    evidence = _bound_evidence(session, context, command.evidence)
    expected = deepcopy(context)
    if review_prefixes is not None:
        historical_hash = str(row.context.get("source_review_hash", ""))
        observed_at = review_prefixes.get(historical_hash)
        if observed_at is None or observed_at > row.created_at:
            raise InvestigationError("GROUP_APPLICABILITY_HISTORY_CONFLICT")
        expected["source_review_hash"] = historical_hash
    if (
        row.context != expected
        or row.context_hash != digest(row.context)
        or row.request_hash != digest(row.request)
        or command.context_hash != row.context_hash
        or row.request != command.model_dump(mode="json")
        or row.target_plan_id != command.target_plan_id
        or row.source_rule_preparation_id != command.source_rule_preparation_id
        or row.source_rule_candidate_id != command.source_rule_candidate_id
        or row.previous_decision_id != command.previous_decision_id
        or str(row.source_rule_approval_id) != context["source_rule_approval_id"]
        or row.evidence_snapshot != evidence
        or row.evidence_hash != digest(evidence)
        or row.created_at > store.clock()
    ):
        raise InvestigationError("GROUP_APPLICABILITY_INTEGRITY_FAILED")
    return {
        "decision_id": str(row.decision_id),
        "sequence": row.sequence,
        "request": deepcopy(row.request),
        "request_hash": row.request_hash,
        "context": deepcopy(row.context),
        "context_hash": row.context_hash,
        "evidence_snapshot": evidence,
        "evidence_hash": row.evidence_hash,
        "reviewer_id": str(row.reviewer_id),
        "created_at": row.created_at.isoformat(),
    }


def _history(
    store: InvestigationStore, session: Session, context: dict[str, Any], review: dict[str, Any]
) -> list[dict[str, Any]]:
    # A sibling rule approval appends to the review without changing this selected rule.
    # Accept only hashes of actual immutable prefixes, retaining the exact old context.
    prefixes: dict[str, datetime] = {}
    partial = deepcopy(review)
    partial["history"], partial["decisions"] = [], {}
    for approval in review["history"]:
        partial["history"].append(approval)
        partial["decisions"][approval["rule_candidate_id"]] = approval
        selected = partial["decisions"].get(context["source_rule_candidate_id"])
        if selected is not None and selected["decision_id"] == context["source_rule_approval_id"]:
            prefixes[digest(partial)] = datetime.fromisoformat(approval["created_at"])
    rows = list(
        session.scalars(
            select(InvestigationGroupApplicability)
            .where(
                InvestigationGroupApplicability.target_plan_id == UUID(context["target_plan_id"]),
                InvestigationGroupApplicability.source_rule_candidate_id
                == UUID(context["source_rule_candidate_id"]),
            )
            .order_by(InvestigationGroupApplicability.sequence)
        )
    )
    previous = None
    result = []
    for sequence, row in enumerate(rows, 1):
        if (
            row.sequence != sequence
            or row.previous_decision_id != (previous.decision_id if previous else None)
            or (previous is not None and row.created_at < previous.created_at)
        ):
            raise InvestigationError("GROUP_APPLICABILITY_HISTORY_CONFLICT")
        result.append(_describe(store, session, row, context, prefixes))
        previous = row
    return result


def _recheck(
    store: InvestigationStore,
    session: Session,
    task: UUID,
    context: dict[str, Any],
    principal: ReviewerPrincipal,
) -> None:
    session.expire_all()
    _authorize(session, principal)
    current = _context(
        store,
        session,
        task,
        UUID(context["target_plan_id"]),
        UUID(context["source_rule_preparation_id"]),
        UUID(context["source_rule_candidate_id"]),
    )
    if current["context"] != context:
        raise InvestigationError("GROUP_APPLICABILITY_CONTEXT_CHANGED")


def load_group_applicability_decisions(
    store: InvestigationStore,
    task_id: UUID,
    plan_id: UUID,
    source_id: UUID,
    candidate_id: UUID,
    principal: ReviewerPrincipal,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        view = _context(store, session, task_id, plan_id, source_id, candidate_id)
        history = _history(store, session, view["context"], view["source_review"])
        _recheck(store, session, task_id, view["context"], principal)
        return view | {
            "scope": "GROUP_APPLICABILITY_REVIEW_ONLY",
            "history": history,
            "latest": history[-1] if history else None,
        }


def save_group_applicability(
    store: InvestigationStore,
    task_id: UUID,
    command: DecideGroupApplicability,
    principal: ReviewerPrincipal,
    key: str,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    key_hash = sha256(validate_idempotency_key(key).encode()).hexdigest()
    request = command.model_dump(mode="json")
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        view = _context(
            store,
            session,
            task_id,
            command.target_plan_id,
            command.source_rule_preparation_id,
            command.source_rule_candidate_id,
        )
        context = view["context"]
        if digest(context) != command.context_hash:
            raise InvestigationError("GROUP_APPLICABILITY_CONTEXT_CHANGED")
        history = _history(store, session, context, view["source_review"])
        existing = session.scalar(
            select(InvestigationGroupApplicability).where(
                InvestigationGroupApplicability.target_plan_id == command.target_plan_id,
                InvestigationGroupApplicability.reviewer_id == principal.reviewer_id,
                InvestigationGroupApplicability.request_key_hash == key_hash,
            )
        )
        if existing is not None:
            if existing.request_hash != digest(request):
                raise InvestigationError("GROUP_APPLICABILITY_IDEMPOTENCY_CONFLICT")
            result = _describe(store, session, existing, context)
            _recheck(store, session, task_id, context, principal)
            return result
        previous = history[-1] if history else None
        if command.previous_decision_id != (UUID(previous["decision_id"]) if previous else None):
            raise InvestigationError("GROUP_APPLICABILITY_PREDECESSOR_CHANGED")
        evidence = _bound_evidence(session, context, command.evidence)
        _recheck(store, session, task_id, context, principal)
        record = InvestigationGroupApplicability(
            decision_id=uuid7(),
            target_plan_id=command.target_plan_id,
            source_rule_preparation_id=command.source_rule_preparation_id,
            source_rule_candidate_id=command.source_rule_candidate_id,
            source_rule_approval_id=UUID(context["source_rule_approval_id"]),
            previous_decision_id=command.previous_decision_id,
            sequence=len(history) + 1,
            reviewer_id=principal.reviewer_id,
            request_key_hash=key_hash,
            request=request,
            request_hash=digest(request),
            context=deepcopy(context),
            context_hash=digest(context),
            evidence_snapshot=evidence,
            evidence_hash=digest(evidence),
            created_at=store.clock(),
        )
        session.add(record)
        session.flush()
        result = _describe(store, session, record, context)
        _recheck(store, session, task_id, context, principal)
        return result
