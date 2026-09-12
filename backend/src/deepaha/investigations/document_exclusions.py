"""Explicit, revocable exclusion of a source material no parser can consume.

Why this exists
---------------
``document_parsers()`` only understands html / pdf / xlsx / docx. A legacy ``application/msword``
attachment therefore stays ``UNSUPPORTED`` forever, ``document_preparation.status`` never
reaches ``PREPARED``, and every downstream step (binding, field review, rule review,
cross-level conditions, scope preflight) stays closed.

The remedy is a *reviewer decision*, not a parser hack: the reviewer records why this one
material must not be required to yield machine-citable text, and ``prepare_documents`` then
runs it through :class:`~deepaha.documents.opaque.OpaqueBinaryParser` so it contributes an
opaque, text-free block instead of blocking the chain.

Exclusion is not verification
-----------------------------
``InvestigationDocumentExclusion`` deliberately says nothing about the *content* of the
material. The opaque block carries no text, so it can never be selected as block-level
evidence for an adjudication. Existence of an exclusion row is a statement about process
("no parser exists"), not about truth.

The row is bound to a single ``delivery_hash``: when the task is collected again the previous
decision stops applying and the reviewer has to decide afresh.
"""

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid7

from sqlalchemy import select

from deepaha.artifacts.models import RawArtifact
from deepaha.investigations.contracts import InvestigationError
from deepaha.investigations.documents import (
    EXCLUSION_ALLOWED_STATUSES,
    active_exclusions,
    describe_documents,
    exclusion_reason_or_raise,
)
from deepaha.investigations.models import InvestigationDocumentExclusion, InvestigationMaterial
from deepaha.review.auth import (
    OPPORTUNITY_FACT_VALIDATION_PURPOSE,
    ReviewerPrincipal,
    ReviewerRole,
    require_reviewer_authority,
)
from deepaha.review.models import ReviewerAccountModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from deepaha.investigations.models import InvestigationTask
    from deepaha.investigations.store import InvestigationStore


def _authorized_task(
    store: InvestigationStore,
    session: Session,
    task_id: UUID,
    delivery_hash: str,
    principal: ReviewerPrincipal,
) -> tuple[InvestigationTask, str]:
    """Lock the task and prove the caller may decide for exactly this delivery.

    Args:
        store: Investigation store owning the session factory.
        session: Session inside the caller's transaction.
        task_id: Task being decided on.
        delivery_hash: Delivery digest the caller believes is current.
        principal: Reviewer performing the action.

    Returns:
        The locked task row together with its current delivery digest.

    Raises:
        InvestigationError: ``DOCUMENT_OPERATOR_REQUIRED`` when the account is gone or
            deactivated, ``DOCUMENT_EXCLUSION_NOT_ALLOWED`` when the task status admits no
            such decision, ``DOCUMENT_EXCLUSION_DELIVERY_CONFLICT`` when the caller is
            reasoning about a superseded delivery.
    """
    account = session.get(ReviewerAccountModel, principal.reviewer_id)
    if account is None or not account.active:
        raise InvestigationError("DOCUMENT_OPERATOR_REQUIRED")
    require_reviewer_authority(
        ReviewerPrincipal(
            account.reviewer_id,
            frozenset(ReviewerRole(role) for role in account.roles),
            frozenset(account.allowed_purposes),
            account.synthetic,
        ),
        ReviewerRole.LOCAL_TEST_OPERATOR,
        OPPORTUNITY_FACT_VALIDATION_PURPOSE,
    )
    task = store._get(session, task_id, lock=True)
    current_hash = task.delivery_hash
    if task.status not in EXCLUSION_ALLOWED_STATUSES or not current_hash:
        raise InvestigationError("DOCUMENT_EXCLUSION_NOT_ALLOWED")
    if current_hash != delivery_hash:
        raise InvestigationError("DOCUMENT_EXCLUSION_DELIVERY_CONFLICT")
    return task, current_hash


def _declared_materials(session: Session, task_id: UUID) -> list[InvestigationMaterial]:
    materials = list(
        session.scalars(
            select(InvestigationMaterial)
            .where(InvestigationMaterial.task_id == task_id)
            .order_by(InvestigationMaterial.raw_artifact_id, InvestigationMaterial.material_id)
        )
    )
    if not materials:
        raise InvestigationError("STORED_MATERIAL_INTEGRITY_FAILED")
    return materials


def exclude_document(
    store: InvestigationStore,
    task_id: UUID,
    delivery_hash: str,
    material_id: str,
    reason: str,
    principal: ReviewerPrincipal,
) -> dict[str, Any]:
    """Exclude one material whose media type no registered parser can read.

    Args:
        store: Investigation store.
        task_id: Task owning the material.
        delivery_hash: Delivery digest the decision is bound to.
        material_id: Identifier of the material within the task.
        reason: Written justification, 8..2000 characters after trimming.
        principal: Reviewer performing the exclusion.

    Returns:
        The refreshed task view, whose ``document_preparation`` now marks the material
        ``excluded``.

    Raises:
        InvestigationError: ``DOCUMENT_EXCLUSION_REASON_REQUIRED`` for an unusable reason,
            ``DOCUMENT_EXCLUSION_MATERIAL_NOT_FOUND`` for an unknown material,
            ``DOCUMENT_EXCLUSION_ALREADY_PRESENT`` when an effective exclusion already
            exists for this delivery, ``DOCUMENT_EXCLUSION_NOT_UNSUPPORTED`` when the
            material is anything other than ``UNSUPPORTED`` (otherwise this would become a
            back door for hiding parse failures), plus the codes raised by
            :func:`_authorized_task`.
    """
    require_reviewer_authority(
        principal, ReviewerRole.LOCAL_TEST_OPERATOR, OPPORTUNITY_FACT_VALIDATION_PURPOSE
    )
    checked_reason = exclusion_reason_or_raise(reason)
    with store.factory() as session, session.begin():
        task, current_hash = _authorized_task(store, session, task_id, delivery_hash, principal)
        materials = _declared_materials(session, task_id)
        material = next((row for row in materials if row.material_id == material_id), None)
        if material is None:
            raise InvestigationError("DOCUMENT_EXCLUSION_MATERIAL_NOT_FOUND")
        if material_id in active_exclusions(session, task_id, current_hash):
            raise InvestigationError("DOCUMENT_EXCLUSION_ALREADY_PRESENT")
        rows = {
            row["material_id"]: row for row in describe_documents(session, materials)["materials"]
        }
        if rows[material_id]["outcome"] != "UNSUPPORTED":
            raise InvestigationError("DOCUMENT_EXCLUSION_NOT_UNSUPPORTED")
        raw = session.get(RawArtifact, material.raw_artifact_id)
        if (
            raw is None
            or raw.media_type is None
            or raw.media_type != material.metadata_snapshot["media_type"]
        ):
            raise InvestigationError("STORED_MATERIAL_INTEGRITY_FAILED")
        session.add(
            InvestigationDocumentExclusion(
                exclusion_id=uuid7(),
                task_id=task_id,
                material_id=material_id,
                raw_artifact_id=raw.artifact_id,
                media_type=raw.media_type,
                delivery_hash=current_hash,
                reason=checked_reason,
                excluded_by=principal.reviewer_id,
                excluded_at=store.clock(),
            )
        )
        return store._view(session, task)


def revoke_exclusion(
    store: InvestigationStore,
    task_id: UUID,
    delivery_hash: str,
    material_id: str,
    reason: str,
    principal: ReviewerPrincipal,
) -> dict[str, Any]:
    """Withdraw an exclusion, restoring the "must yield text blocks" requirement.

    Revocation is an append-only mutation: the original row keeps ``excluded_by`` and
    ``excluded_at`` and gains ``revoked_at`` / ``revoked_by`` / ``revoked_reason``, so who
    excluded what and who undid it both survive.

    Note that any document already parsed while the exclusion was active stays in the
    evidence tables; only the *future* interpretation changes, and this decision is itself
    recorded.

    Args:
        store: Investigation store.
        task_id: Task owning the material.
        delivery_hash: Delivery digest the decision is bound to.
        material_id: Identifier of the material within the task.
        reason: Written justification, 8..2000 characters after trimming.
        principal: Reviewer withdrawing the exclusion.

    Returns:
        The refreshed task view.

    Raises:
        InvestigationError: ``DOCUMENT_EXCLUSION_NOT_FOUND`` when there is no effective
            exclusion for this delivery (including one that was already revoked), plus the
            codes raised by :func:`_authorized_task` and :func:`exclusion_reason_or_raise`.
    """
    require_reviewer_authority(
        principal, ReviewerRole.LOCAL_TEST_OPERATOR, OPPORTUNITY_FACT_VALIDATION_PURPOSE
    )
    checked_reason = exclusion_reason_or_raise(reason)
    with store.factory() as session, session.begin():
        task, current_hash = _authorized_task(store, session, task_id, delivery_hash, principal)
        row = active_exclusions(session, task_id, current_hash).get(material_id)
        if row is None:
            raise InvestigationError("DOCUMENT_EXCLUSION_NOT_FOUND")
        row.revoked_at = store.clock()
        row.revoked_by = principal.reviewer_id
        row.revoked_reason = checked_reason
        return store._view(session, task)
