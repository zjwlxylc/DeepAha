"""Read-only binding to replayed DocumentBlock/EvidenceRef, never fact approval."""

from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.object_store import ObjectStore
from deepaha.contracts.evidence_anchor import (
    READER_BLOCK_CONTRACT,
    READER_BLOCK_PARSER,
    READER_EVIDENCE_VERSION,
    ReaderAnchor,
)
from deepaha.documents.blocks import block_hash, evidence_binding_hash
from deepaha.documents.models import Document, DocumentBlock, EvidenceRef, ParseAttempt
from deepaha.documents.normalization import build_derived_text_key, normalize_text
from deepaha.documents.reader import reader_parser_version, representation_blocks
from deepaha.evidence_verification.contracts import (
    ArtifactInput,
    ReaderIdentity,
    VerificationResult,
)
from deepaha.evidence_verification.registry import AdapterRegistry
from deepaha.evidence_verification.verifier import EvidenceVerifier
from deepaha.p9b.hashing import document_parse_key

MAX_BINDING_ARTIFACT_BYTES = 20_000_000


@dataclass(frozen=True, slots=True)
class PersistentEvidenceBinding:
    verification: VerificationResult
    document_id: UUID
    document_parse_key: str
    parse_attempt_id: UUID
    block_id: UUID | None
    evidence_ref_id: UUID | None
    evidence_binding_hash: str | None


class PreparedDocumentEvidence:
    """One immutable document replay per verification run; all rows are checked.

    Construction rejects incomplete or altered persistence. A literal match can
    bind only to the exact replayed projection and keeps its original locator.
    No database writes, semantic approval, or source authority inference occur.
    """

    def __init__(
        self,
        session: Session,
        objects: ObjectStore,
        registry: AdapterRegistry,
        *,
        document_id: UUID,
        source_url: str,
    ) -> None:
        document = session.get(Document, document_id)
        if document is None or document.parse_contract_version != READER_BLOCK_CONTRACT:
            raise LookupError("READER_DOCUMENT_REQUIRED")
        raw = session.get(RawArtifact, document.artifact_id)
        if raw is None or raw.media_type is None or raw.byte_size > MAX_BINDING_ARTIFACT_BYTES:
            raise LookupError("RAW_ARTIFACT_UNAVAILABLE")
        content = objects.get_bytes(key=raw.object_key)
        if len(content) != raw.byte_size or sha256(content).hexdigest() != raw.content_sha256:
            raise LookupError("RAW_ARTIFACT_INTEGRITY_FAILED")
        rows = tuple(
            session.scalars(
                select(DocumentBlock)
                .where(DocumentBlock.document_id == document_id)
                .order_by(DocumentBlock.ordinal)
            )
        )
        if not rows:
            raise LookupError("DOCUMENT_BLOCKS_MISSING")
        anchor = ReaderAnchor.model_validate(rows[0].structural_locator)
        identity = ReaderIdentity(**anchor.reader.model_dump())
        key = document_parse_key(
            artifact_id=raw.artifact_id,
            artifact_sha256=raw.content_sha256,
            parser_name=READER_BLOCK_PARSER,
            parser_version=reader_parser_version(identity),
            parse_contract_version=READER_BLOCK_CONTRACT,
        )
        if (
            document.parser_name != READER_BLOCK_PARSER
            or document.parser_version != reader_parser_version(identity)
            or document.document_parse_key != key
        ):
            raise LookupError("DOCUMENT_PARSE_IDENTITY_MISMATCH")
        attempt = session.scalar(
            select(ParseAttempt).where(
                ParseAttempt.document_id == document_id, ParseAttempt.document_parse_key == key
            )
        )
        if (
            attempt is None
            or attempt.outcome != "SUCCEEDED"
            or attempt.artifact_id != raw.artifact_id
            or attempt.parser_name != document.parser_name
            or attempt.parser_version != document.parser_version
            or attempt.parse_contract_version != document.parse_contract_version
        ):
            raise LookupError("DOCUMENT_PARSE_ATTEMPT_UNVERIFIED")
        artifact = ArtifactInput(
            str(raw.artifact_id), raw.media_type, source_url, raw.content_sha256, content
        )
        verifier = EvidenceVerifier(registry)
        representation = verifier.read(artifact, identity)
        expected = representation_blocks(representation)
        if len(rows) != len(expected):
            raise LookupError("DOCUMENT_BLOCK_SET_MISMATCH")
        refs = {
            r.evidence_ref_id: r
            for r in session.scalars(
                select(EvidenceRef).where(EvidenceRef.document_id == document_id)
            )
        }
        by_projection: dict[str, tuple[UUID, UUID, str]] = {}
        for ordinal, (row, block) in enumerate(zip(rows, expected, strict=True), start=1):
            digest = block_hash(document_parse_key=key, ordinal=ordinal, block=block)
            binding_digest = evidence_binding_hash(
                block_id=str(row.block_id),
                document_parse_key=key,
                structural_locator=block.structural_locator,
                block_hash_value=digest,
            )
            ref = refs.get(row.evidence_ref_id)
            value_hash = sha256(block.canonical_text_or_value.encode()).hexdigest()
            payload = {
                "schema_version": READER_EVIDENCE_VERSION,
                "kind": "reader_anchor",
                "block_id": str(row.block_id),
                "document_parse_key": key,
                "block_type": "READER_TEXT_SPAN",
                "structural_locator": block.structural_locator,
                "value_sha256": value_hash,
            }
            if (
                row.ordinal != ordinal
                or row.artifact_id != raw.artifact_id
                or row.document_parse_key != key
                or row.block_type != block.block_type
                or row.canonical_text_or_value != block.canonical_text_or_value
                or row.structural_locator != block.structural_locator
                or row.block_hash != digest
                or row.evidence_binding_hash != binding_digest
                or row.parent_block_id is not None
                or row.parser_name != document.parser_name
                or row.parser_version != document.parser_version
                or row.parse_contract_version != document.parse_contract_version
                or ref is None
                or ref.artifact_id != raw.artifact_id
                or ref.document_id != document_id
                or ref.locator_schema_version != READER_EVIDENCE_VERSION
                or ref.locator_kind != "reader_anchor"
                or ref.locator_value is not None
                or ref.locator_payload != payload
                or ref.quote_sha256 != value_hash
            ):
                raise LookupError("DOCUMENT_EVIDENCE_REPLAY_MISMATCH")
            projection_id = str(block.structural_locator["projection_id"])
            by_projection[projection_id] = row.block_id, row.evidence_ref_id, binding_digest
        derived_key = build_derived_text_key(
            raw.content_sha256,
            document.parser_name,
            document.parser_version,
            document.parse_contract_version,
        )
        uri = urlsplit(document.extracted_text_uri or "")
        if (
            uri.scheme != "s3"
            or uri.netloc != raw.storage_bucket
            or uri.path != f"/{derived_key}"
            or uri.query
            or uri.fragment
        ):
            raise LookupError("DERIVED_DOCUMENT_IDENTITY_MISMATCH")
        derived = objects.get_bytes(key=derived_key)
        expected_text = normalize_text(
            "\n".join(dict.fromkeys(p.text for p in representation.projections))
        ).encode()
        metadata = objects.stat(key=derived_key)
        if (
            derived != expected_text
            or metadata.sha256 != sha256(derived).hexdigest()
            or metadata.byte_size != len(derived)
            or metadata.key != derived_key
            or metadata.bucket != raw.storage_bucket
        ):
            raise LookupError("DERIVED_DOCUMENT_INTEGRITY_FAILED")
        self._verifier, self._artifact, self._identity = verifier, artifact, identity
        self._by_projection = by_projection
        self.document_id, self.document_parse_key = document_id, key
        self.parse_attempt_id = attempt.parse_attempt_id

    def verify(self, quote: str, locator: dict[str, object]) -> PersistentEvidenceBinding:
        result = self._verifier.verify(
            self._artifact, quote, locator, reader_identity=self._identity
        )
        block_id = ref_id = None
        binding_hash = None
        if result.verdict == "PASS":
            block_id, ref_id, binding_hash = self._by_projection[result.matches[0].projection_id]
        return PersistentEvidenceBinding(
            result,
            self.document_id,
            self.document_parse_key,
            self.parse_attempt_id,
            block_id,
            ref_id,
            binding_hash,
        )
