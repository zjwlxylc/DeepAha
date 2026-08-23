from hashlib import sha256
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from deepaha.contracts.phase2 import EvidenceLocatorV02, PdfPageTextLocator
from deepaha.documents.normalization import normalize_text
from deepaha.documents.parser import ExpectedParseError, ParsedDocument

MAX_PDF_PAGES = 500


class PypdfDocumentParser:
    name = "pdf_pypdf"
    version = "0.2.0"

    def supports(self, media_type: str) -> bool:
        return media_type.partition(";")[0].strip().lower() == "application/pdf"

    def parse(self, content: bytes, *, artifact_sha256: str) -> ParsedDocument:
        if sha256(content).hexdigest() != artifact_sha256:
            raise ValueError("artifact SHA-256 does not match PDF bytes")

        reader = _read_pdf(content)
        page_texts = tuple(_extract_page_text(reader, index) for index in range(len(reader.pages)))
        nonempty_pages = [(index, text) for index, text in enumerate(page_texts) if text]
        if not nonempty_pages:
            raise ExpectedParseError("PDF_TEXT_EMPTY")

        locators: list[EvidenceLocatorV02] = []
        for index, text in nonempty_pages:
            locators.append(
                PdfPageTextLocator(
                    schema_version="0.2.0",
                    kind="pdf_page_text",
                    page_number=index + 1,
                    text_start=0,
                    text_end=len(text),
                    text_sha256=sha256(text.encode()).hexdigest(),
                )
            )
        needs_review = ("PDF_PAGE_TEXT_MISSING",) if len(nonempty_pages) != len(page_texts) else ()
        return ParsedDocument(
            title=None,
            published_at=None,
            language="und",
            normalized_text=normalize_text("\n\f\n".join(page_texts)),
            locators=tuple(locators),
            needs_review_reasons=needs_review,
        )


def _read_pdf(content: bytes) -> PdfReader:
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ExpectedParseError("PDF_ENCRYPTED")
        page_count = len(reader.pages)
    except ExpectedParseError:
        raise
    except PyPdfError as error:
        raise ExpectedParseError("PDF_PARSE_FAILED") from error

    if page_count > MAX_PDF_PAGES:
        raise ExpectedParseError("PDF_PAGE_LIMIT_EXCEEDED")
    if page_count == 0:
        raise ExpectedParseError("PDF_TEXT_EMPTY")
    return reader


def _extract_page_text(reader: PdfReader, page_index: int) -> str:
    try:
        value = reader.pages[page_index].extract_text()
    except PyPdfError as error:
        raise ExpectedParseError("PDF_PARSE_FAILED") from error
    return normalize_text(value or "")
