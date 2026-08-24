from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol
from uuid import UUID, uuid7

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.models import AcquisitionEvaluation
from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.object_store import ObjectIntegrityError, ObjectStore
from deepaha.contracts.phase2 import (
    EvidenceLocatorV02,
    LegacyEvidenceLocator,
)
from deepaha.documents.blocks import (
    ParsedBlock,
    validate_parsed_blocks,
)
from deepaha.documents.blocks import (
    block_hash as calculate_block_hash,
)
from deepaha.documents.blocks import (
    evidence_binding_hash as calculate_evidence_binding_hash,
)
from deepaha.documents.models import Document, DocumentBlock, EvidenceRef, ParseAttempt
from deepaha.documents.normalization import build_derived_text_key, normalize_text
from deepaha.documents.parser import (
    P9B_BLOCK_PARSE_CONTRACT_VERSION,
    DocumentParser,
    ExpectedParseError,
    ParsedDocument,
    validate_review_reason,
)
from deepaha.p9b.hashing import document_parse_key

_LOCATOR_ADAPTER: TypeAdapter[EvidenceLocatorV02] = TypeAdapter(EvidenceLocatorV02)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ParseDocumentCommand:
    artifact_id: UUID


@dataclass(frozen=True, slots=True)
class ParseDocumentResult:
    parse_attempt_id: UUID
    artifact_id: UUID
    parser_name: str
    parser_version: str
    parse_contract_version: str
    document_parse_key: str
    outcome: str
    document_id: UUID | None
    error_code: str | None
    extracted_text_uri: str | None
    evidence_ref_ids: tuple[UUID, ...]
    document_block_ids: tuple[UUID, ...]
    created: bool


class ParserSelectionError(RuntimeError):
    pass


class DerivedObjectConflict(RuntimeError):
    def __init__(self) -> None:
        self.code = "DERIVED_OBJECT_CONFLICT"
        super().__init__(self.code)


class DocumentService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        object_store: ObjectStore,
        parsers: Sequence[DocumentParser],
        clock: Clock | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._object_store = object_store
        self._parsers = tuple(parsers)
        self._clock = clock or SystemClock()

    def parse(self, command: ParseDocumentCommand) -> ParseDocumentResult:
        with self._session_factory.begin() as session:
            artifact = session.get(RawArtifact, command.artifact_id)
            if artifact is None:
                raise LookupError(f"RawArtifact not found: {command.artifact_id}")
            acquisition_statuses = tuple(
                session.scalars(
                    select(AcquisitionEvaluation.validation_status).where(
                        AcquisitionEvaluation.artifact_id == artifact.artifact_id
                    )
                )
            )
            if acquisition_statuses and set(acquisition_statuses) != {"VALID"}:
                raise RuntimeError("ACQUISITION_DOCUMENT_BLOCKED")

            parser = self._select_parser(artifact.media_type)
            parse_key = document_parse_key(
                artifact_id=artifact.artifact_id,
                artifact_sha256=artifact.content_sha256,
                parser_name=parser.name,
                parser_version=parser.version,
                parse_contract_version=parser.parse_contract_version,
            )
            build_derived_text_key(
                artifact.content_sha256,
                parser.name,
                parser.version,
                parser.parse_contract_version,
            )
            existing = session.scalar(
                select(ParseAttempt).where(
                    ParseAttempt.artifact_id == artifact.artifact_id,
                    ParseAttempt.parser_name == parser.name,
                    ParseAttempt.parser_version == parser.version,
                    ParseAttempt.parse_contract_version == parser.parse_contract_version,
                )
            )
            if existing is not None:
                return self._existing_result(session, existing)

            started_at = self._clock.now()
            content = self._object_store.get_bytes(key=artifact.object_key)
            self._verify_raw_content(artifact, content)
            try:
                parsed = parser.parse(content, artifact_sha256=artifact.content_sha256)
            except ExpectedParseError as error:
                attempt = ParseAttempt(
                    parse_attempt_id=uuid7(),
                    artifact_id=artifact.artifact_id,
                    parser_name=parser.name,
                    parser_version=parser.version,
                    parse_contract_version=parser.parse_contract_version,
                    document_parse_key=parse_key,
                    started_at=started_at,
                    completed_at=self._clock.now(),
                    outcome="FAILED",
                    document_id=None,
                    error_code=error.code,
                    input_media_type=self._required_media_type(artifact.media_type),
                )
                session.add(attempt)
                session.flush()
                return self._result(
                    attempt=attempt,
                    document=None,
                    evidence_ref_ids=(),
                    created=True,
                )

            locators = self._validate_parsed(parsed)
            blocks = validate_parsed_blocks(parsed.blocks) if parsed.blocks else ()
            if blocks and parser.parse_contract_version != P9B_BLOCK_PARSE_CONTRACT_VERSION:
                raise ValueError("DocumentBlock output requires the P9-B parse contract")
            if parser.parse_contract_version == P9B_BLOCK_PARSE_CONTRACT_VERSION and not blocks:
                raise ValueError("P9-B parse contract requires DocumentBlock output")
            text_bytes = parsed.normalized_text.encode("utf-8")
            derived_key = build_derived_text_key(
                artifact.content_sha256,
                parser.name,
                parser.version,
                parser.parse_contract_version,
            )
            digest = sha256(text_bytes).hexdigest()
            try:
                stored = self._object_store.put_bytes_if_absent(
                    key=derived_key,
                    content=text_bytes,
                    media_type="text/plain; charset=utf-8",
                    sha256=digest,
                )
            except ObjectIntegrityError as error:
                raise DerivedObjectConflict from error
            if (
                stored.key != derived_key
                or stored.byte_size != len(text_bytes)
                or stored.sha256 != digest
            ):
                raise DerivedObjectConflict

            created_at = self._clock.now()
            document = Document(
                document_id=uuid7(),
                artifact_id=artifact.artifact_id,
                title=parsed.title,
                published_at=parsed.published_at,
                language=parsed.language,
                extracted_text_uri=f"s3://{stored.bucket}/{stored.key}",
                parser_name=parser.name,
                parser_version=parser.version,
                parse_contract_version=parser.parse_contract_version,
                document_parse_key=parse_key,
                parse_confidence=None,
                created_at=created_at,
            )
            session.add(document)
            session.flush()

            evidence_refs = [
                self._build_evidence_ref(document=document, artifact=artifact, locator=locator)
                for locator in locators
            ]
            session.add_all(evidence_refs)
            block_evidence_refs, document_blocks = self._build_document_blocks(
                document=document,
                artifact=artifact,
                blocks=blocks,
                created_at=created_at,
            )
            session.add_all(block_evidence_refs)
            session.flush()
            session.add_all(document_blocks)
            outcome = "NEEDS_REVIEW" if parsed.needs_review_reasons else "SUCCEEDED"
            error_code = "|".join(parsed.needs_review_reasons) or None
            attempt = ParseAttempt(
                parse_attempt_id=uuid7(),
                artifact_id=artifact.artifact_id,
                parser_name=parser.name,
                parser_version=parser.version,
                parse_contract_version=parser.parse_contract_version,
                document_parse_key=parse_key,
                started_at=started_at,
                completed_at=self._clock.now(),
                outcome=outcome,
                document_id=document.document_id,
                error_code=error_code,
                input_media_type=self._required_media_type(artifact.media_type),
            )
            session.add(attempt)
            session.flush()
            return self._result(
                attempt=attempt,
                document=document,
                evidence_ref_ids=tuple(
                    sorted(
                        value.evidence_ref_id for value in (*evidence_refs, *block_evidence_refs)
                    )
                ),
                document_block_ids=tuple(value.block_id for value in document_blocks),
                created=True,
            )

    def _select_parser(self, media_type: str | None) -> DocumentParser:
        if media_type is None:
            matched: list[DocumentParser] = []
        else:
            matched = [parser for parser in self._parsers if parser.supports(media_type)]
        if len(matched) != 1:
            raise ParserSelectionError(
                f"expected exactly one parser for media type {media_type!r}; found {len(matched)}"
            )
        return matched[0]

    @staticmethod
    def _verify_raw_content(artifact: RawArtifact, content: bytes) -> None:
        if len(content) != artifact.byte_size or sha256(content).hexdigest() != (
            artifact.content_sha256
        ):
            raise ObjectIntegrityError("raw object bytes do not match RawArtifact")

    @staticmethod
    def _validate_parsed(parsed: ParsedDocument) -> tuple[EvidenceLocatorV02, ...]:
        if not parsed.normalized_text:
            raise ValueError("parser returned empty normalized text")
        if normalize_text(parsed.normalized_text) != parsed.normalized_text:
            raise ValueError("parser returned text that is not normalized")
        if not parsed.language.strip():
            raise ValueError("parser returned empty language")
        if parsed.published_at is not None and (
            parsed.published_at.tzinfo is None or parsed.published_at.utcoffset() is None
        ):
            raise ValueError("parser returned published_at without timezone")
        for reason in parsed.needs_review_reasons:
            validate_review_reason(reason)
        if not parsed.locators and not parsed.blocks:
            raise ValueError("parser returned no evidence locator or DocumentBlock")

        result: list[EvidenceLocatorV02] = []
        for locator in parsed.locators:
            validated = _LOCATOR_ADAPTER.validate_python(locator)
            if isinstance(validated, LegacyEvidenceLocator):
                raise ValueError("parser returned a legacy locator")
            result.append(validated)
        return tuple(result)

    @staticmethod
    def _build_evidence_ref(
        *,
        document: Document,
        artifact: RawArtifact,
        locator: EvidenceLocatorV02,
    ) -> EvidenceRef:
        payload = locator.model_dump(mode="json")
        quote_sha256 = payload.get("text_sha256", payload.get("cells_sha256"))
        if not isinstance(quote_sha256, str):
            raise ValueError("v0.2 locator is missing its evidence hash")
        return EvidenceRef(
            evidence_ref_id=uuid7(),
            document_id=document.document_id,
            artifact_id=artifact.artifact_id,
            locator_kind=locator.kind,
            locator_value=None,
            locator_schema_version="0.2.0",
            locator_payload=payload,
            quote_sha256=quote_sha256,
        )

    @staticmethod
    def _build_document_blocks(
        *,
        document: Document,
        artifact: RawArtifact,
        blocks: tuple[ParsedBlock, ...],
        created_at: datetime,
    ) -> tuple[list[EvidenceRef], list[DocumentBlock]]:
        block_ids = [uuid7() for _ in blocks]
        evidence_refs: list[EvidenceRef] = []
        rows: list[DocumentBlock] = []
        for ordinal, (block_id, block) in enumerate(zip(block_ids, blocks, strict=True), start=1):
            block_hash_value = calculate_block_hash(
                document_parse_key=document.document_parse_key,
                ordinal=ordinal,
                block=block,
            )
            binding_hash = calculate_evidence_binding_hash(
                block_id=str(block_id),
                document_parse_key=document.document_parse_key,
                structural_locator=block.structural_locator,
                block_hash_value=block_hash_value,
            )
            value_hash = sha256(block.canonical_text_or_value.encode("utf-8")).hexdigest()
            kind = block.structural_locator.get("kind")
            if not isinstance(kind, str):
                raise ValueError("DocumentBlock locator kind is missing")
            evidence_ref = EvidenceRef(
                evidence_ref_id=uuid7(),
                document_id=document.document_id,
                artifact_id=artifact.artifact_id,
                locator_kind=kind,
                locator_value=None,
                locator_schema_version="0.8.0",
                locator_payload={
                    "schema_version": "0.8.0",
                    "kind": kind,
                    "block_id": str(block_id),
                    "document_parse_key": document.document_parse_key,
                    "block_type": block.block_type,
                    "structural_locator": block.structural_locator,
                    "value_sha256": value_hash,
                },
                quote_sha256=value_hash,
            )
            evidence_refs.append(evidence_ref)
            rows.append(
                DocumentBlock(
                    block_id=block_id,
                    document_id=document.document_id,
                    artifact_id=artifact.artifact_id,
                    document_parse_key=document.document_parse_key,
                    ordinal=ordinal,
                    block_type=block.block_type,
                    canonical_text_or_value=block.canonical_text_or_value,
                    structural_locator=block.structural_locator,
                    block_hash=block_hash_value,
                    evidence_binding_hash=binding_hash,
                    evidence_ref_id=evidence_ref.evidence_ref_id,
                    parent_block_id=(
                        block_ids[block.parent_ordinal - 1]
                        if block.parent_ordinal is not None
                        else None
                    ),
                    parser_name=document.parser_name,
                    parser_version=document.parser_version,
                    parse_contract_version=document.parse_contract_version,
                    created_at=created_at,
                )
            )
        return evidence_refs, rows

    def _existing_result(self, session: Session, attempt: ParseAttempt) -> ParseDocumentResult:
        document = (
            session.get(Document, attempt.document_id) if attempt.document_id is not None else None
        )
        evidence_ref_ids = (
            tuple(
                session.scalars(
                    select(EvidenceRef.evidence_ref_id)
                    .where(EvidenceRef.document_id == attempt.document_id)
                    .order_by(EvidenceRef.evidence_ref_id)
                )
            )
            if attempt.document_id is not None
            else ()
        )
        document_block_ids = (
            tuple(
                session.scalars(
                    select(DocumentBlock.block_id)
                    .where(DocumentBlock.document_id == attempt.document_id)
                    .order_by(DocumentBlock.ordinal)
                )
            )
            if attempt.document_id is not None
            else ()
        )
        return self._result(
            attempt=attempt,
            document=document,
            evidence_ref_ids=evidence_ref_ids,
            document_block_ids=document_block_ids,
            created=False,
        )

    @staticmethod
    def _result(
        *,
        attempt: ParseAttempt,
        document: Document | None,
        evidence_ref_ids: tuple[UUID, ...],
        document_block_ids: tuple[UUID, ...] = (),
        created: bool,
    ) -> ParseDocumentResult:
        return ParseDocumentResult(
            parse_attempt_id=attempt.parse_attempt_id,
            artifact_id=attempt.artifact_id,
            parser_name=attempt.parser_name,
            parser_version=attempt.parser_version,
            parse_contract_version=attempt.parse_contract_version,
            document_parse_key=attempt.document_parse_key,
            outcome=attempt.outcome,
            document_id=attempt.document_id,
            error_code=attempt.error_code,
            extracted_text_uri=document.extracted_text_uri if document is not None else None,
            evidence_ref_ids=evidence_ref_ids,
            document_block_ids=document_block_ids,
            created=created,
        )

    @staticmethod
    def _required_media_type(media_type: str | None) -> str:
        if media_type is None or not media_type.strip():
            raise ValueError("RawArtifact media_type is required for parsing")
        return media_type
