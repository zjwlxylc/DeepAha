"""Read-only replay of the pre-generic Delivery quote gate; not the active path."""

import re
from io import BytesIO
from typing import TYPE_CHECKING, Any

from openpyxl import load_workbook
from openpyxl.utils.cell import column_index_from_string
from pypdf import PdfReader

from deepaha.documents.html import _parse_html_tree
from deepaha.documents.parser import ExpectedParseError
from deepaha.documents.pdf import MAX_PDF_PAGES
from deepaha.documents.spreadsheet_reading import SpreadsheetText as _SpreadsheetText
from deepaha.documents.spreadsheet_reading import read_spreadsheet_text
from deepaha.evidence_verification.adapters.html_text import _html_quote_text
from deepaha.evidence_verification.adapters.projection import (
    canonical_html_text as _canonical_html_text,
)
from deepaha.investigations.delivery_errors import DeliveryValidationError
from deepaha.investigations.delivery_errors import fail as _fail

if TYPE_CHECKING:
    from deepaha.investigations.delivery import ValidatedArtifact


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _quote_support(
    artifact: ValidatedArtifact,
    quote: str,
    locator: dict[str, Any],
    issues: set[str],
    *,
    spreadsheet_cache: dict[str, _SpreadsheetText] | None = None,
) -> bool:
    media = artifact.media_type.partition(";")[0].strip().lower()
    supported_locator = False
    selected: str | None = None
    try:
        if media == "text/html":
            tree = _parse_html_tree(artifact.content, utf8_fallback=True)
            canonical_quote = _canonical_html_text(quote)
            if not canonical_quote:
                _fail("EVIDENCE_QUOTE_INVALID")
            selector = locator.get("selector")
            if isinstance(selector, str) and set(locator) == {"selector"}:
                nodes = tree.cssselect(selector)
                if not nodes:
                    _fail("EVIDENCE_LOCATOR_MISMATCH")
                # A selector may match several locations; never stitch them into a quote.
                texts = [_html_quote_text(node) for node in nodes]
                texts.extend(
                    _html_quote_text(node, join_cell_wraps=True)
                    for node in nodes
                    if node.tag in {"td", "th"}
                )
                supported_locator = True
            else:
                texts = [_html_quote_text(tree)]
                if set(locator) == {"url"}:
                    if locator["url"] != artifact.url:
                        _fail("EVIDENCE_LOCATOR_MISMATCH")
                    supported_locator = True
            if not any(canonical_quote in _canonical_html_text(text) for text in texts):
                _fail("EVIDENCE_QUOTE_MISMATCH")
        elif media == "application/pdf":
            reader = PdfReader(BytesIO(artifact.content), strict=True)
            if reader.is_encrypted:
                issues.add(f"EVIDENCE_FORMAT_REVIEW_REQUIRED:{artifact.artifact_id}")
                return False
            if len(reader.pages) > MAX_PDF_PAGES:
                _fail("EVIDENCE_RESOURCE_LIMIT_EXCEEDED")
            page = locator.get("page")
            if type(page) is int and set(locator) == {"page"}:
                if not 1 <= page <= len(reader.pages):
                    _fail("EVIDENCE_LOCATOR_MISMATCH")
                selected = reader.pages[page - 1].extract_text() or ""
                supported_locator = True
        elif media == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            selected, supported_locator = _spreadsheet_text(
                artifact.content, locator, cache=spreadsheet_cache, cache_key=artifact.artifact_id
            )
        else:
            issues.add(f"EVIDENCE_FORMAT_REVIEW_REQUIRED:{artifact.artifact_id}")
            return False
    except DeliveryValidationError:
        raise
    except ExpectedParseError as error:
        if error.code == "HTML_ENCODING_UNRESOLVED":
            issues.add(f"EVIDENCE_FORMAT_REVIEW_REQUIRED:{artifact.artifact_id}")
            return False
        raise DeliveryValidationError("EVIDENCE_MATERIAL_INVALID") from None
    except Exception:
        # Parser-specific errors must not expose material bytes or local paths.
        raise DeliveryValidationError("EVIDENCE_MATERIAL_INVALID") from None
    if selected is not None and _normalized(quote) not in _normalized(selected):
        _fail("EVIDENCE_QUOTE_MISMATCH")
    if not supported_locator:
        issues.add(f"EVIDENCE_LOCATOR_REVIEW_REQUIRED:{artifact.artifact_id}")
    return supported_locator


def _spreadsheet_text(
    content: bytes,
    locator: dict[str, Any],
    *,
    cache: dict[str, _SpreadsheetText] | None = None,
    cache_key: str = "",
) -> tuple[str | None, bool]:
    sheet = locator.get("sheet")
    row = locator.get("row")
    cell = locator.get("cell")
    column = locator.get("col")
    numeric_cell = set(locator) == {"sheet", "row", "col"}
    if numeric_cell and (
        type(row) is not int
        or not 1 <= row <= 1048576
        or type(column) is not int
        or not 1 <= column <= 16384
    ):
        _fail("EVIDENCE_LOCATOR_MISMATCH")
    if not (
        (set(locator) == {"sheet", "row"} and type(row) is int)
        or (set(locator) == {"sheet", "cell"} and isinstance(cell, str))
        or numeric_cell
    ):
        return None, False
    if "cell" in locator:
        match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", str(cell))
        if match is None:
            _fail("EVIDENCE_LOCATOR_MISMATCH")
        column, row = column_index_from_string(match[1]), int(match[2])
        if column > 16384 or row > 1048576:
            _fail("EVIDENCE_LOCATOR_MISMATCH")
    tables = cache.get(cache_key) if cache is not None else None
    if tables is None:
        tables = _read_spreadsheet_text(content)
        if cache is not None:
            cache[cache_key] = tables
    if not isinstance(sheet, str) or sheet not in tables.rows:
        _fail("EVIDENCE_LOCATOR_MISMATCH")
    if type(row) is not int or not 1 <= row <= tables.row_counts[sheet]:
        _fail("EVIDENCE_LOCATOR_MISMATCH")
    values = tables.rows[sheet].get(row, {})
    if column is not None:
        return values.get(column, ""), True
    return " ".join(values.values()), True


def _read_spreadsheet_text(content: bytes) -> _SpreadsheetText:
    """Read cells once per validation, retaining zeroes and exact worksheet names."""
    try:
        return _bounded_spreadsheet_text(content)
    except ExpectedParseError as error:
        if error.code in {
            "XLSX_ENTRY_LIMIT_EXCEEDED",
            "XLSX_UNCOMPRESSED_SIZE_EXCEEDED",
            "XLSX_EXPANSION_LIMIT_EXCEEDED",
            "XLSX_WORKSHEET_LIMIT_EXCEEDED",
        }:
            _fail("EVIDENCE_RESOURCE_LIMIT_EXCEEDED")
        raise


def _bounded_spreadsheet_text(content: bytes) -> _SpreadsheetText:
    return read_spreadsheet_text(
        content,
        open_workbook=lambda data: load_workbook(
            BytesIO(data), read_only=True, data_only=False, keep_links=False
        ),
    )
