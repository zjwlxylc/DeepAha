import re
from dataclasses import dataclass
from typing import IO

from lxml import etree
from openpyxl.utils import column_index_from_string

from deepaha.documents.parser import ExpectedParseError

MAX_ROWS = 1_048_576
MAX_COLUMNS = 16_384
MAX_EXPANSION_STEPS = 2_000_000
MAX_WORKSHEETS = 128
MAX_MERGE_RANGES = 20_000
MAX_MERGED_CELL_VALUES = 100_000
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_CELL = re.compile(r"([A-Za-z]{1,3})([1-9][0-9]{0,6})")
_MERGE_CELL = re.compile(r"([A-Za-z]{1,3})([1-9][0-9]{0,6}):([A-Za-z]{1,3})([1-9][0-9]{0,6})")


@dataclass
class WorksheetExpansionBudget:
    steps: int = 0

    def consume(self, steps: int) -> None:
        self.steps += steps
        if self.steps > MAX_EXPANSION_STEPS:
            raise ExpectedParseError("XLSX_EXPANSION_LIMIT_EXCEEDED")


def parse_merge_range(reference: str | None) -> tuple[int, int, int, int] | None:
    """Normalize a ``mergeCell`` ref to ``(first_row, first_column, last_row, last_column)``.

    Returns ``None`` for a missing, malformed, out-of-grid or single-cell ref.
    Those are no-ops, so they are skipped instead of failing a workbook that was
    readable before merges were inspected.
    """
    if reference is None:
        return None
    match = _MERGE_CELL.fullmatch(reference)
    if match is None:
        return None
    start_column = column_index_from_string(match[1])
    start_row = int(match[2])
    end_column = column_index_from_string(match[3])
    end_row = int(match[4])
    if max(start_row, end_row) > MAX_ROWS or max(start_column, end_column) > MAX_COLUMNS:
        return None
    first_row, last_row = sorted((start_row, end_row))
    first_column, last_column = sorted((start_column, end_column))
    if first_row == last_row and first_column == last_column:
        return None
    return first_row, first_column, last_row, last_column


def preflight_worksheet(
    source: IO[bytes],
    budget: WorksheetExpansionBudget,
    *,
    required: bool = False,
    merges: list[str] | None = None,
) -> None:
    """Bound actual row/cell expansion; declared dimensions are not trusted.

    Empty row gaps cost one iteration each. A populated row costs its padded
    column width, matching read-only openpyxl with reset dimensions. XML is
    streamed without entities or network access; originals are never modified.

    When ``merges`` is given, the ``mergeCell`` refs seen on this single pass are
    appended to it: a second read of the part would double-count the budget.
    """
    previous_row = 0
    root: etree._Element | None = None
    try:
        events = etree.iterparse(
            source,
            events=("start", "end"),
            resolve_entities=False,
            load_dtd=False,
            no_network=True,
            huge_tree=False,
        )
        for event, node in events:
            if root is None:
                root = node
                if root.tag != f"{_NS}worksheet":
                    if required:
                        raise ExpectedParseError("XLSX_PARSE_FAILED")
                    return
                if root.getroottree().docinfo.internalDTD is not None:
                    raise ExpectedParseError("XLSX_PARSE_FAILED")
            if event != "end":
                continue
            if node.tag == f"{_NS}mergeCell":
                _collect_merge_reference(node, merges)
                continue
            if node.tag != f"{_NS}row":
                continue
            raw_row = node.get("r", str(previous_row + 1))
            if re.fullmatch(r"[0-9]{1,7}", raw_row) is None:
                raise ExpectedParseError("XLSX_COORDINATE_INVALID")
            row = int(raw_row)
            if not previous_row < row <= MAX_ROWS:
                raise ExpectedParseError("XLSX_COORDINATE_INVALID")
            previous_column = 0
            for cell in node:
                if cell.tag != f"{_NS}c":
                    raise ExpectedParseError("XLSX_COORDINATE_INVALID")
                coordinate = cell.get("r")
                if coordinate is None:
                    column = previous_column + 1
                else:
                    match = _CELL.fullmatch(coordinate)
                    if match is None or int(match[2]) != row:
                        raise ExpectedParseError("XLSX_COORDINATE_INVALID")
                    column = column_index_from_string(match[1])
                if not previous_column < column <= MAX_COLUMNS:
                    raise ExpectedParseError("XLSX_COORDINATE_INVALID")
                previous_column = column
            budget.consume(row - previous_row - 1 + max(1, previous_column))
            previous_row = row
            node.clear()
            parent = node.getparent()
            if parent is not None:
                while node.getprevious() is not None:
                    del parent[0]
    except etree.XMLSyntaxError as error:
        raise ExpectedParseError("XLSX_PARSE_FAILED") from error


def _collect_merge_reference(node: etree._Element, merges: list[str] | None) -> None:
    """Record one merge ref in streaming order; the cap bounds a hostile part."""
    reference = node.get("ref")
    if merges is not None and reference is not None and len(merges) < MAX_MERGE_RANGES:
        merges.append(reference)
    node.clear()
