"""Persist existing Reader projections through DocumentService, without a new store."""

from dataclasses import asdict
from hashlib import sha256

from pydantic import ValidationError

from deepaha.contracts.evidence_anchor import (
    READER_BLOCK_CONTRACT,
    READER_BLOCK_PARSER,
    ReaderAnchor,
)
from deepaha.documents.blocks import ParsedBlock, validate_parsed_blocks
from deepaha.documents.normalization import normalize_text
from deepaha.documents.parser import ExpectedParseError, ParsedDocument
from deepaha.evidence_verification.contracts import (
    ArtifactInput,
    EvidenceAdapter,
    Projection,
    ReaderIdentity,
    Representation,
)
from deepaha.evidence_verification.registry import AdapterRegistry
from deepaha.p9b.hashing import canonical_json_bytes


def reader_parser_version(identity: ReaderIdentity) -> str:
    return sha256(canonical_json_bytes(asdict(identity))).hexdigest()


def representation_blocks(representation: Representation) -> tuple[ParsedBlock, ...]:
    digest = representation.sha256
    return validate_parsed_blocks(
        tuple(
            ParsedBlock(
                "READER_TEXT_SPAN",
                projection.text,
                ReaderAnchor.model_validate(
                    {
                        "reader": asdict(representation.reader),
                        "artifact_sha256": representation.artifact_sha256,
                        "representation_sha256": digest,
                        "projection_id": projection.projection_id,
                        "projection_sha256": projection.sha256,
                        "text_start": 0,
                        "text_end": len(projection.text),
                    }
                ).model_dump(mode="json"),
                None,
            )
            for projection in representation.projections
        )
    )


class ReaderDocumentParser:
    name = READER_BLOCK_PARSER
    parse_contract_version = READER_BLOCK_CONTRACT

    def __init__(self, adapter: EvidenceAdapter) -> None:
        self.adapter = adapter
        self.version = reader_parser_version(adapter.identity)

    def supports(self, media_type: str) -> bool:
        return AdapterRegistry.media_type(media_type) in tuple(
            AdapterRegistry.media_type(media) for media in self.adapter.media_types
        )

    def parse(self, content: bytes, *, artifact_sha256: str) -> ParsedDocument:
        if sha256(content).hexdigest() != artifact_sha256:
            raise ExpectedParseError("ARTIFACT_HASH_MISMATCH")
        representation = self.adapter.read(content)
        if (
            representation.reader != self.adapter.identity
            or representation.artifact_sha256 != artifact_sha256
        ):
            raise ExpectedParseError("REPRESENTATION_IDENTITY_MISMATCH")
        if not representation.projections:
            raise ExpectedParseError("READER_NO_TEXT")
        # The display document follows the existing normalization contract; the
        # separately hashed blocks retain the literal Reader text and traces.
        display = normalize_text(
            "\n".join(dict.fromkeys(p.text for p in representation.projections))
        )
        reasons = tuple(
            code
            for condition, code in (
                (not representation.complete, "READER_INCOMPLETE"),
                (not representation.reliable, "READER_UNRELIABLE"),
            )
            if condition
        )
        try:
            blocks = representation_blocks(representation)
        except ValidationError as error:
            raise ExpectedParseError("READER_ANCHOR_INVALID") from error
        return ParsedDocument(None, None, "und", display, (), reasons, blocks)


def replay_reader_anchor(
    registry: AdapterRegistry, artifact: ArtifactInput, payload: dict[str, object]
) -> Projection:
    anchor = ReaderAnchor.model_validate(payload)
    identity = ReaderIdentity(**anchor.reader.model_dump())
    adapter = registry.select(artifact.media_type, identity)
    if adapter is None:
        raise LookupError("READER_VERSION_UNAVAILABLE")
    if (
        sha256(artifact.content).hexdigest() != artifact.sha256
        or anchor.artifact_sha256 != artifact.sha256
    ):
        raise LookupError("ARTIFACT_HASH_MISMATCH")
    representation = adapter.read(artifact.content)
    if (
        representation.reader != identity
        or representation.artifact_sha256 != artifact.sha256
        or representation.sha256 != anchor.representation_sha256
    ):
        raise LookupError("REPRESENTATION_IDENTITY_MISMATCH")
    projection = next(
        (p for p in representation.projections if p.projection_id == anchor.projection_id), None
    )
    if (
        projection is None
        or projection.sha256 != anchor.projection_sha256
        or len(projection.text) != anchor.text_end
    ):
        raise LookupError("READER_ANCHOR_MISMATCH")
    return projection
