"""Opaque (no-text) binary parser for explicitly excluded source materials.

Some official attachments (for example legacy ``application/msword`` binaries) have no
parser in :func:`deepaha.investigations.documents.document_parsers`, so they are reported
as ``UNSUPPORTED`` and the whole downstream chain (binding -> field review -> rule review)
stays closed.

The agreed remedy is an *explicit reviewer exclusion*: the reviewer excludes the material
with a written reason, the material is still really parsed once, and the result is a single
**opaque block** that carries no quotable text plus a citation that points at the whole
original file. Because the block has no text, it can never be used as block-level evidence
for an adjudication -- "excluded" must not read as "verified".

Why ``supports()`` is opt-in only
---------------------------------
``DocumentService._select_parser`` picks a parser purely by media type, and
``InvestigationStore``/``describe_documents`` treat "no parser supports this media type" as
``UNSUPPORTED``. A default-constructed ``OpaqueBinaryParser`` therefore supports nothing,
so registering one in ``document_parsers()`` would change nothing and staying out of it
keeps every currently ``UNSUPPORTED`` material unsupported.

To actually use it, the exclusion flow builds a **dedicated** ``DocumentService`` whose
parser sequence is exactly ``(OpaqueBinaryParser(frozenset({raw.media_type})),)``. That
parser then matches that one media type and nothing else, so the exclusion never leaks
into the normal parser registry.

Persisted shape
---------------
The block is ``OPAQUE_BINARY`` with an empty ``canonical_text_or_value``; it cites the
whole file through ``structural_locator = {"kind": "opaque_whole_file", "value_sha256":
<artifact sha256>, "byte_size": n}``. ``DocumentService`` still writes
``evidence_refs.value_sha256`` as ``sha256(canonical_text_or_value)``, i.e. the digest of
the empty string, which is why the whole-file digest lives in the locator.
"""

from hashlib import sha256

from deepaha.artifacts.object_store import ObjectIntegrityError
from deepaha.documents.blocks import (
    OPAQUE_BLOCK_TYPE,
    OPAQUE_LOCATOR_KIND,
    ParsedBlock,
    StructuralLocator,
)
from deepaha.documents.normalization import normalize_text
from deepaha.documents.parser import P9B_BLOCK_PARSE_CONTRACT_VERSION, ParsedDocument


class OpaqueBinaryParser:
    """Deterministic parser that turns excluded binary material into one opaque block.

    The block carries no text and cites the whole original by digest. This is the landing
    point for "excluded != verified": there is nothing in the block that can be quoted as
    evidence.

    Attributes:
        name: Stable parser identifier recorded on ``documents.parser_name``.
        version: Parser version recorded on ``documents.parser_version``.
        parse_contract_version: Shared P9-B block contract used by the other parsers.
    """

    name = "opaque_no_text"
    version = "0.1.0"
    parse_contract_version = P9B_BLOCK_PARSE_CONTRACT_VERSION

    def __init__(self, media_types: frozenset[str] = frozenset()) -> None:
        """Create a parser that claims only the media types it is explicitly given.

        Args:
            media_types: Media types this instance may handle. The default empty set means
                the instance supports nothing at all, which is what keeps it out of the
                regular parser registry.
        """
        self._media_types = frozenset(_canonical(value) for value in media_types)

    def supports(self, media_type: str) -> bool:
        """Report whether this instance was explicitly granted ``media_type``.

        Args:
            media_type: Declared media type of the raw artifact; parameters such as
                ``; charset=...`` are ignored, matching the other parsers.

        Returns:
            ``True`` only when ``media_type`` was passed to the constructor.
        """
        return _canonical(media_type) in self._media_types

    def parse(self, content: bytes, *, artifact_sha256: str) -> ParsedDocument:
        """Parse ``content`` into a single opaque, text-free block.

        Args:
            content: Raw bytes of the excluded source material.
            artifact_sha256: Declared SHA-256 of ``content``.

        Returns:
            A ``ParsedDocument`` with exactly one opaque block whose text is empty and
            whose locator cites the whole file by digest.

        Raises:
            ObjectIntegrityError: If ``content`` does not hash to ``artifact_sha256``. This
                reuses the project-wide artifact integrity error (the same one
                ``DocumentService._verify_raw_content`` raises) instead of introducing a new
                error type. Note that ``DocumentService.parse`` does not translate it into a
                ``FAILED`` ``ParseAttempt`` row -- it propagates -- which is intentional for
                an integrity violation.
        """
        actual_sha256 = sha256(content).hexdigest()
        if actual_sha256 != artifact_sha256:
            raise ObjectIntegrityError("artifact SHA-256 does not match opaque binary bytes")
        locator: StructuralLocator = {
            "kind": OPAQUE_LOCATOR_KIND,
            "value_sha256": actual_sha256,
            "byte_size": len(content),
        }
        block = ParsedBlock(
            block_type=OPAQUE_BLOCK_TYPE,
            canonical_text_or_value="",
            structural_locator=locator,
            parent_ordinal=None,
        )
        return ParsedDocument(
            title=None,
            published_at=None,
            language="und",
            normalized_text=normalize_text(""),
            locators=(),
            needs_review_reasons=(),
            blocks=(block,),
        )


def _canonical(media_type: str) -> str:
    return media_type.partition(";")[0].strip().lower()


__all__ = [
    "OPAQUE_BLOCK_TYPE",
    "OPAQUE_LOCATOR_KIND",
    "OpaqueBinaryParser",
]
