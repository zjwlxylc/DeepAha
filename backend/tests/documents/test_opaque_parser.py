"""Unit tests for the opaque (no-text) binary parser used by the exclusion flow."""

from hashlib import sha256

import pytest

from deepaha.artifacts.object_store import ObjectIntegrityError
from deepaha.documents.blocks import (
    OPAQUE_BLOCK_TYPE,
    OPAQUE_LOCATOR_KIND,
    ParsedBlock,
    validate_parsed_blocks,
)
from deepaha.documents.opaque import OpaqueBinaryParser
from deepaha.documents.parser import ParsedDocument
from deepaha.investigations.documents import document_parsers

_DOC_BYTES = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy-word-binary-payload"


def _parse(content: bytes, *, artifact_sha256: str | None = None) -> ParsedDocument:
    digest = sha256(content).hexdigest() if artifact_sha256 is None else artifact_sha256
    return OpaqueBinaryParser().parse(content, artifact_sha256=digest)


def _service_outcome(parsed: ParsedDocument) -> str:
    """Mirror the outcome derivation in ``DocumentService.parse``.

    ``DocumentService`` writes ``outcome = "NEEDS_REVIEW" if needs_review_reasons else
    "SUCCEEDED"`` and, whenever parsing returns, builds a ``Document`` row and stores its
    ``document_id`` on the ``ParseAttempt``. The database round-trip is covered by
    ``tests/integration/test_document_service.py``.
    """
    return "NEEDS_REVIEW" if parsed.needs_review_reasons else "SUCCEEDED"


@pytest.mark.parametrize(
    "media_type",
    [
        "application/msword",
        "application/pdf",
        "text/html",
        "text/plain",
        "application/octet-stream",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "",
    ],
)
def test_default_opaque_parser_supports_no_media_type(media_type: str) -> None:
    assert OpaqueBinaryParser().supports(media_type) is False


def test_opaque_parser_supports_only_the_media_types_it_is_given() -> None:
    parser = OpaqueBinaryParser(frozenset({"application/msword"}))

    assert parser.supports("application/msword")
    assert parser.supports("Application/MSWord; charset=binary")
    assert not parser.supports("application/pdf")
    assert not parser.supports("text/html")


def test_opaque_parser_identity_uses_the_shared_p9b_contract() -> None:
    parser = OpaqueBinaryParser()

    assert parser.name == "opaque_no_text"
    assert parser.version == "0.1.0"
    assert parser.parse_contract_version == "p9b-document-block-contract-v0.8.0"


def test_opaque_parse_emits_one_block_with_no_quotable_text() -> None:
    parsed = _parse(_DOC_BYTES)

    assert len(parsed.blocks) == 1
    block = parsed.blocks[0]
    assert block.block_type == OPAQUE_BLOCK_TYPE == "OPAQUE_BINARY"
    assert block.canonical_text_or_value == ""
    assert block.parent_ordinal is None
    assert parsed.normalized_text == ""
    assert parsed.language == "und"
    assert parsed.locators == ()


def test_opaque_block_cites_the_whole_original_by_digest() -> None:
    parsed = _parse(_DOC_BYTES)

    assert parsed.blocks[0].structural_locator == {
        "kind": OPAQUE_LOCATOR_KIND,
        "value_sha256": sha256(_DOC_BYTES).hexdigest(),
        "byte_size": len(_DOC_BYTES),
    }


def test_opaque_parse_derives_a_succeeded_attempt_with_a_document() -> None:
    parsed = _parse(_DOC_BYTES)

    # No review reasons -> DocumentService records outcome="SUCCEEDED"; a non-empty block
    # set -> a Document row is created, so ParseAttempt.document_id is not null.
    assert _service_outcome(parsed) == "SUCCEEDED"
    assert parsed.blocks


def test_opaque_parse_rejects_a_digest_mismatch() -> None:
    with pytest.raises(ObjectIntegrityError, match="artifact SHA-256"):
        OpaqueBinaryParser().parse(_DOC_BYTES, artifact_sha256="0" * 64)

    with pytest.raises(ObjectIntegrityError, match="artifact SHA-256"):
        OpaqueBinaryParser().parse(b"tampered", artifact_sha256=sha256(_DOC_BYTES).hexdigest())


def test_opaque_block_passes_the_current_block_rules() -> None:
    validated = validate_parsed_blocks(_parse(_DOC_BYTES).blocks)

    assert [block.block_type for block in validated] == ["OPAQUE_BINARY"]
    assert validated[0].canonical_text_or_value == ""
    assert validated[0].structural_locator["kind"] == "opaque_whole_file"


def test_opaque_block_rejects_carrying_text() -> None:
    block = ParsedBlock(
        block_type=OPAQUE_BLOCK_TYPE,
        canonical_text_or_value="看起来像证据",
        structural_locator={"kind": OPAQUE_LOCATOR_KIND, "value_sha256": "0" * 64, "byte_size": 1},
        parent_ordinal=None,
    )

    with pytest.raises(ValueError, match="opaque DocumentBlock must not carry text"):
        validate_parsed_blocks((block,))


def test_document_parsers_never_register_the_opaque_parser() -> None:
    """Registering it would turn every UNSUPPORTED material into a parsed one."""
    assert not any(isinstance(parser, OpaqueBinaryParser) for parser in document_parsers())
