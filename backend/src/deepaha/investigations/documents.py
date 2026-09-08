"""Prepare existing document evidence without creating facts or acquisition history."""

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.object_store import ObjectIntegrityError
from deepaha.documents.docx import DeterministicDocxParser
from deepaha.documents.models import DocumentBlock, EvidenceRef, ParseAttempt
from deepaha.documents.parser import DocumentParser
from deepaha.documents.reader import ReaderDocumentParser
from deepaha.documents.service import DocumentService, ParseDocumentCommand
from deepaha.evidence_verification.adapters.defaults import default_registry
from deepaha.investigations.contracts import CreateInvestigation, InvestigationError, digest
from deepaha.investigations.models import InvestigationMaterial
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


def describe_documents(session: Session, materials: list[InvestigationMaterial]) -> dict[str, Any]:
    parsers = document_parsers()
    rows: list[dict[str, Any]] = []
    for material in materials:
        parser = _parser_for(str(material.metadata_snapshot["media_type"]), parsers)
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
        for material in materials:
            raw = session.get(RawArtifact, material.raw_artifact_id)
            if (
                raw is None
                or raw.media_type is None
                or raw.media_type != material.metadata_snapshot["media_type"]
            ):
                raise InvestigationError("STORED_MATERIAL_INTEGRITY_FAILED")
            if _parser_for(raw.media_type, parsers) is None:
                continue
            # All tasks lock shared originals in the same order. DocumentService
            # commits each parse separately, so interrupted preparation can resume.
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": int(digest(["investigation-document", str(raw.artifact_id)])[:15], 16)},
            )
            service.parse(ParseDocumentCommand(artifact_id=raw.artifact_id))
        from deepaha.investigations.evidence_checks import append_check

        append_check(session, store.objects, task, materials, principal.reviewer_id, store.clock())
