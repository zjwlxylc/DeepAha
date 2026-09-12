"""Prepare existing document evidence without creating facts or acquisition history."""

from datetime import UTC
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.object_store import ObjectIntegrityError
from deepaha.documents.docx import DeterministicDocxParser
from deepaha.documents.models import DocumentBlock, EvidenceRef, ParseAttempt
from deepaha.documents.opaque import OpaqueBinaryParser
from deepaha.documents.parser import DocumentParser
from deepaha.documents.reader import ReaderDocumentParser
from deepaha.documents.service import DocumentService, ParseDocumentCommand
from deepaha.evidence_verification.adapters.defaults import default_registry
from deepaha.investigations.contracts import CreateInvestigation, InvestigationError, digest
from deepaha.investigations.models import (
    InvestigationDocumentExclusion,
    InvestigationMaterial,
    InvestigationTask,
)
from deepaha.review.auth import (
    OPPORTUNITY_FACT_VALIDATION_PURPOSE,
    ReviewerPrincipal,
    ReviewerRole,
    require_reviewer_authority,
)
from deepaha.review.models import ReviewerAccountModel

if TYPE_CHECKING:
    from deepaha.investigations.store import InvestigationStore


def document_parsers() -> tuple[DocumentParser, ...]:
    return (
        *(ReaderDocumentParser(adapter) for adapter in default_registry().active_adapters),
        DeterministicDocxParser(),
    )


def _parser_for(media_type: str, parsers: tuple[DocumentParser, ...]) -> DocumentParser | None:
    matched = [parser for parser in parsers if parser.supports(media_type)]
    if len(matched) > 1:
        raise InvestigationError("DOCUMENT_PARSER_AMBIGUOUS")
    return matched[0] if matched else None


# Task statuses in which a reviewer may still decide about material preparation. Every
# other status is terminal for the collection itself, so touching evidence then would
# silently rewrite an already adjudicated delivery.
EXCLUSION_ALLOWED_STATUSES = ("PENDING_REVIEW", "APPROVED")
# Mirrors the ``reason_length`` / ``revoked_reason`` CHECK constraints on
# ``investigation_document_exclusions``. The business layer rejects first so the caller
# gets a named code instead of a database error.
EXCLUSION_REASON_MIN_LENGTH = 8
EXCLUSION_REASON_MAX_LENGTH = 2000

# ``evidence_mode`` describes evidence that really exists, not the intent: ``null`` means
# "there is nothing here yet" (unsupported, unparsed, failed, or parsed without blocks),
# ``TEXT`` means quotable blocks, ``OPAQUE_NO_TEXT`` means one text-free opaque block.
EVIDENCE_MODE_TEXT = "TEXT"
EVIDENCE_MODE_OPAQUE = "OPAQUE_NO_TEXT"


def exclusion_reason_or_raise(value: str) -> str:
    """Validate and normalize a free-text reviewer reason.

    Args:
        value: Raw reason as submitted by the caller.

    Returns:
        The reason with surrounding whitespace removed, which is what gets persisted and
        what the database CHECK measures.

    Raises:
        InvestigationError: ``DOCUMENT_EXCLUSION_REASON_REQUIRED`` when the trimmed reason
            is shorter than :data:`EXCLUSION_REASON_MIN_LENGTH` or longer than
            :data:`EXCLUSION_REASON_MAX_LENGTH`.
    """
    reason = value.strip()
    if not EXCLUSION_REASON_MIN_LENGTH <= len(reason) <= EXCLUSION_REASON_MAX_LENGTH:
        raise InvestigationError("DOCUMENT_EXCLUSION_REASON_REQUIRED")
    return reason


def active_exclusions(
    session: Session, task_id: UUID, delivery_hash: str
) -> dict[str, InvestigationDocumentExclusion]:
    """Return the effective exclusions of one delivery keyed by ``material_id``.

    Args:
        session: Open ORM session.
        task_id: Owning investigation task.
        delivery_hash: Delivery digest the rows are bound to. Rows of earlier deliveries
            are never returned, so re-collected material starts with no exclusion.

    Returns:
        A mapping for every material with a non-revoked exclusion. Revoked rows stay in the
        table as history and are deliberately skipped.
    """
    return {
        row.material_id: row
        for row in session.scalars(
            select(InvestigationDocumentExclusion).where(
                InvestigationDocumentExclusion.task_id == task_id,
                InvestigationDocumentExclusion.delivery_hash == delivery_hash,
                InvestigationDocumentExclusion.revoked_at.is_(None),
            )
        )
    }


def _current_exclusions(
    session: Session, materials: list[InvestigationMaterial]
) -> dict[str, InvestigationDocumentExclusion]:
    """Resolve the exclusions that apply to the materials' own task and delivery."""
    if not materials:
        return {}
    task = session.get(InvestigationTask, materials[0].task_id)
    if task is None or not task.delivery_hash:
        return {}
    return active_exclusions(session, task.task_id, task.delivery_hash)


def describe_documents(session: Session, materials: list[InvestigationMaterial]) -> dict[str, Any]:
    parsers = document_parsers()
    exclusions = _current_exclusions(session, materials)
    rows: list[dict[str, Any]] = []
    for material in materials:
        media_type = str(material.metadata_snapshot["media_type"])
        exclusion = exclusions.get(material.material_id)
        parser = _parser_for(media_type, parsers)
        if parser is None and exclusion is not None:
            # Excluded material: it has an opaque block (or will get one from
            # ``prepare_documents``), so describe it with the parser that produced it
            # instead of leaving it UNSUPPORTED forever. Adding the parser only when no
            # registry parser matches keeps ``_parser_for`` unambiguous.
            parser = OpaqueBinaryParser(frozenset({media_type}))
        row: dict[str, Any] = {
            "material_id": material.material_id,
            "outcome": "UNSUPPORTED" if parser is None else "NOT_PREPARED",
            "error_code": "DOCUMENT_FORMAT_UNSUPPORTED" if parser is None else None,
            "document_id": None,
            "parse_attempt_id": None,
            "document_parse_key": None,
            "parser_name": None if parser is None else parser.name,
            "parser_version": None if parser is None else parser.version,
            "parse_contract_version": None if parser is None else parser.parse_contract_version,
            "block_count": 0,
            "evidence_ref_count": 0,
            "excluded": exclusion is not None,
            "evidence_mode": None,
            "exclusion": None,
        }
        if parser is not None:
            attempt = session.scalar(
                select(ParseAttempt).where(
                    ParseAttempt.artifact_id == material.raw_artifact_id,
                    ParseAttempt.parser_name == parser.name,
                    ParseAttempt.parser_version == parser.version,
                    ParseAttempt.parse_contract_version == parser.parse_contract_version,
                )
            )
            if attempt is not None:
                row.update(
                    outcome=attempt.outcome,
                    error_code=attempt.error_code,
                    document_id=str(attempt.document_id) if attempt.document_id else None,
                    parse_attempt_id=str(attempt.parse_attempt_id),
                    document_parse_key=attempt.document_parse_key,
                )
                if attempt.document_id is not None:
                    row["block_count"] = (
                        session.scalar(
                            select(func.count())
                            .select_from(DocumentBlock)
                            .where(DocumentBlock.document_id == attempt.document_id)
                        )
                        or 0
                    )
                    row["evidence_ref_count"] = (
                        session.scalar(
                            select(func.count())
                            .select_from(EvidenceRef)
                            .where(EvidenceRef.document_id == attempt.document_id)
                        )
                        or 0
                    )
                if row["outcome"] == "SUCCEEDED" and not row["block_count"]:
                    row.update(outcome="NEEDS_REVIEW", error_code="DOCUMENT_BLOCKS_MISSING")
        if exclusion is not None:
            row["exclusion"] = {
                "reason": exclusion.reason,
                "excluded_by": str(exclusion.excluded_by),
                "excluded_at": exclusion.excluded_at.astimezone(UTC).isoformat(),
            }
        # Computed after the NEEDS_REVIEW downgrade above: a material stays ``null`` unless
        # a real parse produced blocks, so UNSUPPORTED / NOT_PREPARED / FAILED / NEEDS_REVIEW
        # never claim to hold text. Whether the text came from an exclusion is decided by the
        # parser that produced it, not by the exclusion row, because a later deployment may
        # well parse an excluded file with a real parser.
        if row["outcome"] == "SUCCEEDED":
            row["evidence_mode"] = (
                EVIDENCE_MODE_OPAQUE
                if isinstance(parser, OpaqueBinaryParser)
                else EVIDENCE_MODE_TEXT
            )
        rows.append(row)
    prepared = sum(row["outcome"] == "SUCCEEDED" for row in rows)
    if not rows or all(row["outcome"] == "NOT_PREPARED" for row in rows):
        status = "NOT_PREPARED"
    elif prepared == len(rows):
        status = "PREPARED"
    else:
        status = "NEEDS_ATTENTION"
    return {
        "scope": "DOCUMENT_EVIDENCE_ONLY",
        "status": status,
        "material_count": len(rows),
        "prepared_count": prepared,
        "excluded_count": sum(row["excluded"] for row in rows),
        "unsupported_count": sum(row["outcome"] == "UNSUPPORTED" for row in rows),
        "materials": rows,
    }


def prepare_documents(
    store: InvestigationStore,
    task_id: UUID,
    delivery_hash: str,
    principal: ReviewerPrincipal,
) -> None:
    require_reviewer_authority(
        principal, ReviewerRole.LOCAL_TEST_OPERATOR, OPPORTUNITY_FACT_VALIDATION_PURPOSE
    )
    with store.factory() as session, session.begin():
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
        if (
            task.status not in ("PENDING_REVIEW", "APPROVED")
            or not task.delivery_hash
            or task.delivery_hash != delivery_hash
        ):
            raise InvestigationError("DOCUMENT_DELIVERY_CONFLICT")
        command = CreateInvestigation.model_validate(task.request)
        if digest(store._source(session, command)) != digest(task.source_snapshot):
            raise InvestigationError("SOURCE_POLICY_CHANGED")
        materials = list(
            session.scalars(
                select(InvestigationMaterial)
                .where(InvestigationMaterial.task_id == task_id)
                .order_by(InvestigationMaterial.raw_artifact_id, InvestigationMaterial.material_id)
            )
        )
        if not materials or len(materials) != (task.delivery or {}).get("material_count"):
            raise InvestigationError("STORED_MATERIAL_INTEGRITY_FAILED")
        try:
            store._verify_stored_bytes(session, task)
        except (OSError, ObjectIntegrityError) as error:
            raise InvestigationError("STORED_MATERIAL_INTEGRITY_FAILED") from error
        parsers = document_parsers()
        service = DocumentService(
            session_factory=sessionmaker(session.get_bind(), expire_on_commit=False),
            object_store=store.objects,
            parsers=parsers,
        )
        exclusions = active_exclusions(session, task_id, task.delivery_hash)
        for material in materials:
            raw = session.get(RawArtifact, material.raw_artifact_id)
            if (
                raw is None
                or raw.media_type is None
                or raw.media_type != material.metadata_snapshot["media_type"]
            ):
                raise InvestigationError("STORED_MATERIAL_INTEGRITY_FAILED")
            target = service
            if _parser_for(raw.media_type, parsers) is None:
                exclusion = exclusions.get(material.material_id)
                if exclusion is None:
                    continue
                # Excluded material: no registered parser can read it, so it is parsed once
                # by a service whose single parser claims exactly this media type. The
                # result is one opaque text-free block, which lets the denominator reach
                # PREPARED without ever offering quotable text for an adjudication.
                target = DocumentService(
                    session_factory=sessionmaker(session.get_bind(), expire_on_commit=False),
                    object_store=store.objects,
                    parsers=(OpaqueBinaryParser(frozenset({raw.media_type})),),
                )
            # All tasks lock shared originals in the same order. DocumentService
            # commits each parse separately, so interrupted preparation can resume.
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": int(digest(["investigation-document", str(raw.artifact_id)])[:15], 16)},
            )
            target.parse(ParseDocumentCommand(artifact_id=raw.artifact_id))
        from deepaha.investigations.evidence_checks import append_check

        append_check(session, store.objects, task, materials, principal.reviewer_id, store.clock())
