"""Authenticated immutable proposals. No decision writing or qualification activation."""

from hashlib import sha256
from typing import Any, Literal
from uuid import UUID, uuid7

from pydantic import Field, ValidationError
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from deepaha.contracts.common import EntityId, Sha256
from deepaha.documents.models import DocumentBlock
from deepaha.investigations.adjudication_storage import freeze_adjudication, thaw_adjudication
from deepaha.investigations.applicability import (
    ApplicabilityEvidence,
    _blocks,
    _bound_evidence,
    _material_url,
)
from deepaha.investigations.bindings import _authorize
from deepaha.investigations.contracts import InvestigationError, digest
from deepaha.investigations.cross_level_adjudication import RelationProposal, replay_adjudication
from deepaha.investigations.cross_level_preview import _build
from deepaha.investigations.group_contracts import GroupContract
from deepaha.investigations.models import InvestigationRelationProposal
from deepaha.investigations.store import InvestigationStore
from deepaha.local_human_test.review import require_human_fact_reviewer, validate_idempotency_key
from deepaha.p9b.models import SourceBundleMember
from deepaha.review.auth import ReviewerPrincipal


class RelationEvidenceRequest(ApplicabilityEvidence):
    purpose: Literal["CONDITION", "RELATION"]
    condition_ids: tuple[str, ...] = Field(min_length=1)


class ProposeRelation(GroupContract):
    target_plan_id: EntityId
    expected_review_hash: Sha256
    condition_ids: tuple[str, ...] = Field(min_length=2)
    relation: Literal["CUMULATIVE", "EXCEPTION", "CONFLICT", "UNRESOLVED"]
    displaced_condition_ids: tuple[str, ...]
    reason: str = Field(min_length=1, max_length=2000)
    evidence: tuple[RelationEvidenceRequest, ...] = Field(max_length=200)


def read_proposal_context(
    store: InvestigationStore,
    task: UUID,
    plan: UUID,
    principal: ReviewerPrincipal,
    after: str | None = None,
) -> dict[str, Any]:
    """Return a server digest and paginated literal blocks from the current binding."""
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        current = _build(store, session, task, plan)
        source = current["dependencies"]["group"]["dependencies"]["group_source"]["source"]
        query = _blocks(session, source)
        if after is not None:
            try:
                block_after, member_after = (UUID(part) for part in after.split(":"))
            except ValueError as error:
                raise InvestigationError("RELATION_PROPOSAL_CURSOR_INVALID") from error
            query = query.where(
                tuple_(DocumentBlock.block_id, SourceBundleMember.source_bundle_member_id)
                > (block_after, member_after)
            )
        rows = list(
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
                "source_url": _material_url(session, source, m),
                "text": b.canonical_text_or_value,
                "locator": b.structural_locator,
            }
            for m, b in rows[:50]
        ]
        _recheck(store, session, task, plan, principal, current)
        return {
            "task_id": str(task),
            "target_plan_id": str(plan),
            "review": current,
            "review_hash": digest(current),
            "evidence_options": options,
            "next_cursor": f"{rows[49][1].block_id}:{rows[49][0].source_bundle_member_id}"
            if len(rows) > 50
            else None,
        }


def _evidence(
    session: Session, review: dict[str, Any], command: ProposeRelation
) -> list[dict[str, Any]]:
    source = review["dependencies"]["group"]["dependencies"]["group_source"]["source"]
    bound = _bound_evidence(
        session,
        source,
        tuple(
            ApplicabilityEvidence(member_id=e.member_id, block_id=e.block_id, quote=e.quote)
            for e in command.evidence
        ),
    )
    return [
        row | {"purpose": e.purpose, "condition_ids": list(e.condition_ids)}
        for row, e in zip(bound, command.evidence, strict=True)
    ]


def _describe(
    store: InvestigationStore,
    session: Session,
    row: InvestigationRelationProposal,
    current: dict[str, Any],
) -> dict[str, Any]:
    try:
        package = thaw_adjudication(
            {
                "storage_version": row.storage_version,
                "payload_text": row.payload_text,
                "payload_sha256": row.payload_sha256,
            },
            expected_payload_sha256=row.payload_sha256,
        )
        request = ProposeRelation.model_validate(row.request)
        p = package["proposal"]
        base = p["source_review"]["dependencies"]["group"]["snapshot"]["base_v2"]
        if (
            package["decisions"]
            or p["proposal_id"] != str(row.proposal_id)
            or p["producer_id"] != str(row.producer_id)
            or p["source_review"]["dependencies"]["group"]["dependencies"]["group_source"][
                "source"
            ]["task_id"]
            != str(row.task_id)
            or base["plan_id"] != str(row.target_plan_id)
            or request.target_plan_id != row.target_plan_id
            or digest(row.request) != row.request_hash
            or request.expected_review_hash != p["source_review_hash"]
            or any(
                row.request[k] != p[k]
                for k in ("condition_ids", "relation", "displaced_condition_ids", "reason")
            )
            or RelationProposal.model_validate(p).created_at != row.created_at
            or p["evidence"] != _evidence(session, p["source_review"], request)
        ):
            raise ValueError("stored proposal differs from original command or bindings")
        result = replay_adjudication(
            package,
            expected_package_hash=row.payload_sha256,
            current_source_review=current,
            as_of=store.clock(),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise InvestigationError("RELATION_PROPOSAL_INTEGRITY_FAILED") from exc
    return {
        "proposal_id": str(row.proposal_id),
        "proposal_payload_sha256": row.payload_sha256,
        "payload_sha256": row.payload_sha256,
        "package": package,
        "review": result,
    }


def _recheck(
    store: InvestigationStore,
    session: Session,
    task: UUID,
    plan: UUID,
    principal: ReviewerPrincipal,
    expected: dict[str, Any],
) -> None:
    session.expire_all()
    _authorize(session, principal)
    if _build(store, session, task, plan) != expected:
        raise InvestigationError("RELATION_PROPOSAL_CONTEXT_CHANGED")


def save_relation_proposal(
    store: InvestigationStore,
    task: UUID,
    command: ProposeRelation,
    principal: ReviewerPrincipal,
    key: str,
) -> dict[str, Any]:
    require_human_fact_reviewer(principal)
    key_hash = sha256(validate_idempotency_key(key).encode()).hexdigest()
    request = command.model_dump(mode="json")
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        current = _build(store, session, task, command.target_plan_id)
        if digest(current) != command.expected_review_hash:
            raise InvestigationError("RELATION_PROPOSAL_CONTEXT_CHANGED")
        existing = session.scalar(
            select(InvestigationRelationProposal).where(
                InvestigationRelationProposal.target_plan_id == command.target_plan_id,
                InvestigationRelationProposal.producer_id == principal.reviewer_id,
                InvestigationRelationProposal.request_key_hash == key_hash,
            )
        )
        if existing is not None:
            if existing.request_hash != digest(request):
                raise InvestigationError("RELATION_PROPOSAL_IDEMPOTENCY_CONFLICT")
            result = _describe(store, session, existing, current)
            _recheck(store, session, task, command.target_plan_id, principal, current)
            return result
        try:
            proposal = RelationProposal.model_validate(
                {
                    "contract_version": "cross-level-adjudication/1.0.0",
                    "scope": "CROSS_LEVEL_ADJUDICATION_REVIEW_ONLY",
                    "proposal_id": uuid7(),
                    "producer_id": principal.reviewer_id,
                    "created_at": store.clock(),
                    "source_review": current,
                    "source_review_hash": digest(current),
                    **{
                        k: request[k]
                        for k in ("condition_ids", "relation", "displaced_condition_ids", "reason")
                    },
                    "evidence": _evidence(session, current, command),
                }
            )
        except ValidationError as exc:
            raise InvestigationError("RELATION_PROPOSAL_INVALID") from exc
        frozen = freeze_adjudication(
            {"proposal": proposal.model_dump(mode="json"), "decisions": []}
        )
        _recheck(store, session, task, command.target_plan_id, principal, current)
        row = InvestigationRelationProposal(
            proposal_id=proposal.proposal_id,
            task_id=task,
            target_plan_id=command.target_plan_id,
            producer_id=principal.reviewer_id,
            request_key_hash=key_hash,
            request_hash=digest(request),
            request=request,
            storage_version=frozen.storage_version,
            payload_text=frozen.payload_text,
            payload_sha256=frozen.payload_sha256,
            created_at=proposal.created_at,
        )
        session.add(row)
        session.flush()
        result = _describe(store, session, row, current)
        _recheck(store, session, task, command.target_plan_id, principal, current)
        return result


def load_relation_proposal(
    store: InvestigationStore, task: UUID, proposal_id: UUID, principal: ReviewerPrincipal
) -> dict[str, Any]:
    from deepaha.investigations.relation_decisions import _history

    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        store._get(session, task, lock=True)
        row = session.get(InvestigationRelationProposal, proposal_id)
        if row is None or row.task_id != task:
            raise InvestigationError("RELATION_PROPOSAL_NOT_FOUND")
        current = _build(store, session, task, row.target_plan_id)
        result = _history(store, session, row, current)
        _recheck(store, session, task, row.target_plan_id, principal, current)
        return result


def list_relation_proposals(
    store: InvestigationStore, task: UUID, plan: UUID, principal: ReviewerPrincipal
) -> dict[str, Any]:
    """Return navigation identities only; current verdict comes from the detail read."""
    require_human_fact_reviewer(principal)
    with store.factory() as session, session.begin():
        _authorize(session, principal)
        current = _build(store, session, task, plan)
        rows = session.scalars(
            select(InvestigationRelationProposal)
            .where(
                InvestigationRelationProposal.task_id == task,
                InvestigationRelationProposal.target_plan_id == plan,
            )
            .order_by(
                InvestigationRelationProposal.created_at, InvestigationRelationProposal.proposal_id
            )
        )
        proposals = [
            {
                "proposal_id": str(row.proposal_id),
                "producer_id": str(row.producer_id),
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
        _recheck(store, session, task, plan, principal, current)
        return {"task_id": str(task), "target_plan_id": str(plan), "proposals": proposals}
