from dataclasses import dataclass
from hashlib import sha256

import pypdf
from pypdf._page import PageObject
from pypdf.errors import PyPdfError
from pypdf.generic import ContentStream, DictionaryObject, StreamObject

from deepaha.documents.parser import ExpectedParseError
from deepaha.documents.pdf import _read_pdf
from deepaha.evidence_verification.adapters.projection import TextPart, text_projection
from deepaha.evidence_verification.contracts import (
    Projection,
    ReaderIdentity,
    Representation,
    ScopeResolution,
    SourceSpan,
)

MAX_PDF_BYTES = 20_000_000
MAX_PDF_TEXT_CHARACTERS = 10_000_000
_VISUAL_OPERATORS = frozenset(
    {b"INLINE IMAGE", b"S", b"s", b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*", b"sh"}
)


@dataclass(frozen=True, slots=True, kw_only=True)
class PdfRepresentation(Representation):
    page_count: int
    incomplete_pages: tuple[int, ...]


def _has_unread_visuals(page: PageObject) -> bool:
    # Do not decode images or run OCR. Presence of content outside the text
    # Reader means the broad page locator cannot prove a negative (or a PASS).
    stream = page.get_contents()
    if stream is not None and any(
        operation in _VISUAL_OPERATORS for _, operation in stream.operations
    ):
        return True
    if page.get("/Annots"):
        return True  # Annotation appearances/content are outside extract_text.
    pending: list[DictionaryObject] = [page]
    seen: set[int] = set()
    while pending:
        container = pending.pop()
        if id(container) in seen:
            continue
        seen.add(id(container))
        if len(seen) > 10_000:
            raise ExpectedParseError("PDF_RESOURCE_LIMIT_EXCEEDED")
        if isinstance(container, StreamObject):
            operations = ContentStream(container, page.pdf).operations
            if any(operation in _VISUAL_OPERATORS for _, operation in operations):
                return True
        resources_ref = container.get("/Resources")
        if resources_ref is None:
            continue
        resources = resources_ref.get_object()
        if not isinstance(resources, DictionaryObject):
            raise ExpectedParseError("PDF_RESOURCES_INVALID")
        objects_ref = resources.get("/XObject")
        if objects_ref is None:
            continue
        objects = objects_ref.get_object()
        if not isinstance(objects, DictionaryObject):
            raise ExpectedParseError("PDF_RESOURCES_INVALID")
        for reference in objects.values():
            obj = reference.get_object()
            if not isinstance(obj, DictionaryObject):
                raise ExpectedParseError("PDF_RESOURCES_INVALID")
            if obj.get("/Subtype") != "/Form":
                return True
            pending.append(obj)
    return False


class PdfAdapter:
    identity = ReaderIdentity(
        "pdf_pypdf_literal",
        "1",
        f"pdf-text-layer/1;pypdf={pypdf.__version__}",
        "whitespace-collapse/1",
    )
    media_types = ("application/pdf",)

    def normalize_quote(self, quote: str) -> str:
        return " ".join(quote.split())

    def read(self, content: bytes) -> Representation:
        if len(content) > MAX_PDF_BYTES:
            raise ExpectedParseError("PDF_SIZE_LIMIT_EXCEEDED")
        reader = _read_pdf(content)
        projections: list[Projection] = []
        incomplete_pages: list[int] = []
        total = 0
        try:
            for number, page in enumerate(reader.pages, 1):
                if _has_unread_visuals(page):
                    incomplete_pages.append(number)
                # Use the original extractor text, not Phase 2's NFC view, for offsets.
                text = page.extract_text() or ""
                total += len(text)
                if total > MAX_PDF_TEXT_CHARACTERS:
                    raise ExpectedParseError("PDF_TEXT_LIMIT_EXCEEDED")
                if text:
                    identity = f"page:{number}"
                    projection = text_projection(
                        identity, (TextPart(text, SourceSpan(identity, 0, len(text))),)
                    )
                    if projection:
                        projections.append(projection)
        except PyPdfError as error:
            raise ExpectedParseError("PDF_PARSE_FAILED") from error
        return PdfRepresentation(
            self.identity,
            sha256(content).hexdigest(),
            tuple(projections),
            page_count=len(reader.pages),
            incomplete_pages=tuple(incomplete_pages),
        )

    def resolve_scope(
        self, representation: Representation, locator: dict[str, object], *, source_url: str
    ) -> ScopeResolution:
        if not isinstance(representation, PdfRepresentation):
            raise ExpectedParseError("PDF_REPRESENTATION_INVALID")
        keys = set(locator) - {"human_verify"}
        ids = tuple(p.projection_id for p in representation.projections)
        page = locator.get("page")
        if keys == {"page"}:
            if type(page) is not int:
                return ScopeResolution("INVALID", (), "NONE")
            if not 1 <= page <= representation.page_count:
                return ScopeResolution("MISMATCH", (), "NONE")
            identity = f"page:{page}"
            found = identity in ids
            complete = found and page not in representation.incomplete_pages
            return ScopeResolution(
                "VERIFIED",
                (identity,) if found else (),
                "SCOPE",
                complete=complete,
                reason_codes=("PDF_TEXT_LAYER_MISSING",)
                if not found
                else (() if complete else ("PDF_VISUAL_CONTENT_UNREAD",)),
            )
        return ScopeResolution(
            "UNSUPPORTED" if keys else "UNBOUND",
            ids,
            "ARTIFACT",
            complete=len(ids) == representation.page_count and not representation.incomplete_pages,
        )
