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
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_CELL = re.compile(r"([A-Za-z]{1,3})([1-9][0-9]{0,6})")


@dataclass
class WorksheetExpansionBudget:
    steps: int = 0

    def consume(self, steps: int) -> None:
        self.steps += steps
        if self.steps > MAX_EXPANSION_STEPS:
            raise ExpectedParseError("XLSX_EXPANSION_LIMIT_EXCEEDED")


def preflight_worksheet(
    source: IO[bytes], budget: WorksheetExpansionBudget, *, required: bool = False
) -> None:
    """Bound actual row/cell expansion; declared dimensions are not trusted.

    Empty row gaps cost one iteration each. A populated row costs its padded
    column width, matching read-only openpyxl with reset dimensions. XML is
    streamed without entities or network access; originals are never modified.
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
            if event != "end" or node.tag != f"{_NS}row":
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
