from hashlib import sha256

from deepaha.contracts.phase2 import (
    HtmlSelectorLocator,
    PdfPageTextLocator,
    SpreadsheetRangeLocator,
)
from deepaha.documents.html import _normalized_visible_text, _parse_html_tree
from deepaha.documents.parser import ExpectedParseError
from deepaha.documents.pdf import _extract_page_text, _read_pdf
from deepaha.documents.spreadsheet import (
    NormalizedCell,
    _cells_for_range,
    _load_workbook,
    _preflight_archive,
    hash_normalized_cells,
)


class LocatorReplayError(RuntimeError):
    pass


def replay_html_locator(content: bytes, locator: HtmlSelectorLocator) -> str:
    tree = _parse_html_tree(content)
    nodes = tree.cssselect(locator.selector)
    if len(nodes) != 1:
        raise LocatorReplayError(
            f"HTML locator must resolve to exactly one node; found {len(nodes)}"
        )
    text = _normalized_visible_text(nodes[0])
    if sha256(text.encode()).hexdigest() != locator.text_sha256:
        raise LocatorReplayError("HTML locator text hash mismatch")
    return text


def replay_pdf_locator(content: bytes, locator: PdfPageTextLocator) -> str:
    if not isinstance(locator.page_number, int) or locator.page_number < 1:
        raise LocatorReplayError("PDF locator page number must be 1-based")
    try:
        reader = _read_pdf(content)
        if locator.page_number > len(reader.pages):
            raise LocatorReplayError("PDF locator page does not exist")
        page_text = _extract_page_text(reader, locator.page_number - 1)
    except ExpectedParseError as error:
        raise LocatorReplayError(f"PDF locator input cannot be parsed: {error.code}") from error

    if (
        not isinstance(locator.text_start, int)
        or not isinstance(locator.text_end, int)
        or locator.text_start < 0
        or locator.text_end <= locator.text_start
        or locator.text_end > len(page_text)
    ):
        raise LocatorReplayError("PDF locator text offsets are outside the page text")
    text = page_text[locator.text_start : locator.text_end]
    if sha256(text.encode()).hexdigest() != locator.text_sha256:
        raise LocatorReplayError("PDF locator text hash mismatch")
    return text


def replay_spreadsheet_locator(
    content: bytes,
    locator: SpreadsheetRangeLocator,
) -> tuple[NormalizedCell, ...]:
    if (
        not all(
            isinstance(value, int)
            for value in (
                locator.start_row,
                locator.end_row,
                locator.start_column,
                locator.end_column,
            )
        )
        or locator.start_row < 1
        or locator.end_row < locator.start_row
        or locator.start_column < 1
        or locator.end_column < locator.start_column
    ):
        raise LocatorReplayError("spreadsheet locator range must use ordered 1-based coordinates")
    try:
        _preflight_archive(content)
        workbook = _load_workbook(content)
        try:
            cells = _cells_for_range(workbook, locator)
        finally:
            workbook.close()
    except LookupError as error:
        raise LocatorReplayError(str(error)) from error
    except ExpectedParseError as error:
        raise LocatorReplayError(
            f"spreadsheet locator input cannot be parsed: {error.code}"
        ) from error
    if hash_normalized_cells(cells) != locator.cells_sha256:
        raise LocatorReplayError("spreadsheet locator cell hash mismatch")
    return cells
