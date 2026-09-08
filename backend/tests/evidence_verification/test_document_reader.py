from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from deepaha.contracts.evidence_anchor import ReaderAnchor
from deepaha.contracts.export import render_evidence_anchor_schemas
from deepaha.documents.blocks import ParsedBlock, validate_parsed_blocks
from deepaha.documents.parser import ExpectedParseError
from deepaha.documents.reader import ReaderDocumentParser, replay_reader_anchor
from deepaha.evidence_verification.adapters.defaults import default_registry
from deepaha.evidence_verification.adapters.html import HtmlAdapter
from deepaha.evidence_verification.contracts import ArtifactInput

CONTENT = "<table><tr><th><p>学历、学</p><p>位要求</p></th></tr></table>".encode()


def test_versioned_anchor_schema_matches_current_contract() -> None:
    root = Path(__file__).resolve().parents[3]
    for name, content in render_evidence_anchor_schemas().items():
        assert (root / "contracts" / "schemas" / "v0.9.0" / name).read_text(
            encoding="utf-8"
        ) == content.decode("utf-8")


def test_generic_blocks_preserve_literal_text_and_replay_exact_reader_projection() -> None:
    parser = ReaderDocumentParser(HtmlAdapter())
    parsed = parser.parse(CONTENT, artifact_sha256=sha256(CONTENT).hexdigest())
    block = next(b for b in parsed.blocks if b.canonical_text_or_value == "学历、学位要求")
    assert block.block_type == "READER_TEXT_SPAN"
    assert validate_parsed_blocks(parsed.blocks) == parsed.blocks
    artifact = ArtifactInput(
        "fixture", "text/html", "https://example.gov/", sha256(CONTENT).hexdigest(), CONTENT
    )
    projection = replay_reader_anchor(default_registry(), artifact, block.structural_locator)
    assert projection.text == block.canonical_text_or_value
    assert len(projection.source_spans(0, len(projection.text)) or ()) == 2


@pytest.mark.parametrize("field", ["representation_sha256", "projection_sha256", "artifact_sha256"])
def test_replay_rejects_forged_hashes(field: str) -> None:
    parser = ReaderDocumentParser(HtmlAdapter())
    block = parser.parse(CONTENT, artifact_sha256=sha256(CONTENT).hexdigest()).blocks[0]
    artifact = ArtifactInput(
        "fixture", "text/html", "https://example.gov/", sha256(CONTENT).hexdigest(), CONTENT
    )
    with pytest.raises(LookupError):
        replay_reader_anchor(
            default_registry(), artifact, block.structural_locator | {field: "0" * 64}
        )


def test_unregistered_reader_and_invented_projection_cannot_replay() -> None:
    parser = ReaderDocumentParser(HtmlAdapter())
    block = parser.parse(CONTENT, artifact_sha256=sha256(CONTENT).hexdigest()).blocks[0]
    artifact = ArtifactInput(
        "fixture", "text/html", "https://example.gov/", sha256(CONTENT).hexdigest(), CONTENT
    )
    for change in (
        {"reader": asdict(replace(HtmlAdapter.identity, version="unavailable"))},
        {"projection_id": "invented"},
        {"text_start": 1},
    ):
        with pytest.raises((LookupError, ValidationError)):
            replay_reader_anchor(default_registry(), artifact, block.structural_locator | change)


def test_generic_block_does_not_inherit_legacy_unicode_folding() -> None:
    content = "<p>Cafe\u0301</p>".encode()
    parsed = ReaderDocumentParser(HtmlAdapter()).parse(
        content, artifact_sha256=sha256(content).hexdigest()
    )
    assert all(b.canonical_text_or_value == "Cafe\u0301" for b in parsed.blocks)
    assert parsed.normalized_text == "Café"  # Separate human-readable derived document.
    assert validate_parsed_blocks(parsed.blocks) == parsed.blocks
    with pytest.raises(ValueError, match="normalized"):
        validate_parsed_blocks((ParsedBlock("HTML_ELEMENT", "Cafe\u0301", {}, None),))


def test_anchor_schema_rejects_extra_fields_and_non_integer_coordinates() -> None:
    block = (
        ReaderDocumentParser(HtmlAdapter())
        .parse(CONTENT, artifact_sha256=sha256(CONTENT).hexdigest())
        .blocks[0]
    )
    for change in ({"unexpected": True}, {"text_start": False}, {"text_end": "12"}):
        with pytest.raises(ValidationError):
            ReaderAnchor.model_validate(block.structural_locator | change)


def test_overlong_reader_path_is_a_recordable_expected_parse_failure() -> None:
    content = (("<" + "x" * 100 + ">") * 190 + "value" + ("</" + "x" * 100 + ">") * 190).encode()
    assert HtmlAdapter().read(content).projections
    with pytest.raises(ExpectedParseError, match="READER_ANCHOR_INVALID"):
        ReaderDocumentParser(HtmlAdapter()).parse(
            content, artifact_sha256=sha256(content).hexdigest()
        )
