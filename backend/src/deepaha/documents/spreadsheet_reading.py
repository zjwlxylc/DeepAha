"""Bounded, literal cell reading shared by Delivery and its versioned Adapter."""

from collections.abc import Callable
from dataclasses import dataclass, field

from openpyxl.workbook.workbook import Workbook

from deepaha.documents.parser import ExpectedParseError
from deepaha.documents.spreadsheet import (
    _ignore_declared_dimensions,
    _load_workbook,
    _preflight_archive,
    _preflight_loaded_worksheet,
)
from deepaha.documents.spreadsheet_limits import MAX_WORKSHEETS, WorksheetExpansionBudget


@dataclass(frozen=True, slots=True)
class SpreadsheetText:
    rows: dict[str, dict[int, dict[int, str]]]
    row_counts: dict[str, int]
    display_ambiguities: dict[str, dict[int, dict[int, tuple[str, str]]]] = field(
        default_factory=dict
    )


def read_spreadsheet_text(
    content: bytes, *, open_workbook: Callable[[bytes], Workbook] = _load_workbook
) -> SpreadsheetText:
    _preflight_archive(content)
    book = open_workbook(content)
    try:
        if len(book.sheetnames) > MAX_WORKSHEETS:
            raise ExpectedParseError("XLSX_WORKSHEET_LIMIT_EXCEEDED")
        sheets: dict[str, dict[int, dict[int, str]]] = {}
        row_counts: dict[str, int] = {}
        display_ambiguities: dict[str, dict[int, dict[int, tuple[str, str]]]] = {}
        expansion = WorksheetExpansionBudget()
        for worksheet in book.worksheets:
            _preflight_loaded_worksheet(worksheet, expansion)
            _ignore_declared_dimensions(worksheet)
            rows = sheets[worksheet.title] = {}
            ambiguous_rows = display_ambiguities[worksheet.title] = {}
            row_counts[worksheet.title] = 0
            for number, cells in enumerate(worksheet.iter_rows(), 1):
                populated = {
                    i: str(cell.value) for i, cell in enumerate(cells, 1) if cell.value is not None
                }
                ambiguous = {
                    i: (cell.data_type, cell.number_format)
                    for i, cell in enumerate(cells, 1)
                    if cell.value is not None
                    and (
                        cell.data_type in {"f", "b", "e"}
                        or cell.number_format not in {"General", "@"}
                    )
                }
                if populated:
                    rows[number] = populated
                if ambiguous:
                    ambiguous_rows[number] = ambiguous
                row_counts[worksheet.title] = number
        return SpreadsheetText(sheets, row_counts, display_ambiguities)
    finally:
        book.close()
