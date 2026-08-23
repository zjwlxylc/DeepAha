import json
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from deepaha.contracts.phase2 import PdfPageTextLocator
from deepaha.documents.parser import ExpectedParseError
from deepaha.documents.pdf import PypdfDocumentParser

FIXTURES = Path(__file__).parents[1] / "fixtures" / "documents"
TEXT_PDF = FIXTURES / "minimal-text.pdf"
EMPTY_PDF = FIXTURES / "empty-text.pdf"
MANIFEST = FIXTURES / "pdf-fixtures.manifest.json"


def parse(content: bytes):  # type: ignore[no-untyped-def]
    return PypdfDocumentParser().parse(content, artifact_sha256=sha256(content).hexdigest())


def test_pdf_fixtures_match_manifest() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "1.0.0"
    assert manifest["generator"] == "tests/fixtures/documents/generate_fixtures.py"
    for fixture in manifest["fixtures"]:
        content = (FIXTURES / fixture["path"]).read_bytes()
        assert len(content) == fixture["byte_size"]
        assert sha256(content).hexdigest() == fixture["content_sha256"]
        assert fixture["synthetic"] is True
        assert fixture["business_facts"] is False


def test_pdf_parser_extracts_two_pages_without_metadata_inference() -> None:
    parsed = parse(TEXT_PDF.read_bytes())

    assert parsed.title is None
    assert parsed.published_at is None
    assert parsed.language == "und"
    assert parsed.normalized_text == ("Synthetic PDF page one.\n\f\nSynthetic PDF page two.")
    assert parsed.needs_review_reasons == ()
    assert len(parsed.locators) == 2
    assert all(isinstance(locator, PdfPageTextLocator) for locator in parsed.locators)
    assert {locator.page_number for locator in parsed.locators} == {1, 2}
    assert [(locator.text_start, locator.text_end) for locator in parsed.locators] == [
        (0, len("Synthetic PDF page one.")),
        (0, len("Synthetic PDF page two.")),
    ]


def test_pdf_parser_supports_only_pdf_media_type() -> None:
    parser = PypdfDocumentParser()

    assert parser.name == "pdf_pypdf"
    assert parser.version == "0.2.0"
    assert parser.supports("application/pdf") is True
    assert parser.supports("application/pdf; version=1.4") is True
    assert parser.supports("text/html") is False


def test_encrypted_pdf_is_rejected() -> None:
    reader = PdfReader(BytesIO(TEXT_PDF.read_bytes()), strict=True)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.encrypt("fixture-password")
    output = BytesIO()
    writer.write(output)

    with pytest.raises(ExpectedParseError) as captured:
        parse(output.getvalue())

    assert captured.value.code == "PDF_ENCRYPTED"


def test_damaged_pdf_is_a_stable_failure() -> None:
    with pytest.raises(ExpectedParseError) as captured:
        parse(b"%PDF-1.4\nthis is not a valid PDF")

    assert captured.value.code == "PDF_PARSE_FAILED"


def test_page_limit_is_enforced_before_text_extraction() -> None:
    writer = PdfWriter()
    for _ in range(501):
        writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)

    with pytest.raises(ExpectedParseError) as captured:
        parse(output.getvalue())

    assert captured.value.code == "PDF_PAGE_LIMIT_EXCEEDED"


def test_all_empty_pages_are_a_stable_failure() -> None:
    with pytest.raises(ExpectedParseError) as captured:
        parse(EMPTY_PDF.read_bytes())

    assert captured.value.code == "PDF_TEXT_EMPTY"


def test_partially_empty_pdf_is_kept_for_review() -> None:
    reader = PdfReader(BytesIO(TEXT_PDF.read_bytes()), strict=True)
    writer = PdfWriter()
    writer.add_page(reader.pages[0])
    writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)

    parsed = parse(output.getvalue())

    assert parsed.normalized_text == "Synthetic PDF page one.\n\f\n"
    assert parsed.needs_review_reasons == ("PDF_PAGE_TEXT_MISSING",)
    assert len(parsed.locators) == 1
    locator = parsed.locators[0]
    assert isinstance(locator, PdfPageTextLocator)
    assert locator.page_number == 1


def test_artifact_digest_mismatch_is_a_programmer_error() -> None:
    with pytest.raises(ValueError, match="artifact SHA-256"):
        PypdfDocumentParser().parse(TEXT_PDF.read_bytes(), artifact_sha256="0" * 64)
