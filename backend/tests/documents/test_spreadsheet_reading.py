"""A quote located inside a merged range must read the anchor value.

openpyxl's read-only worksheet exposes no ``merged_cells``, so covered cells
used to read as empty and a correct locator was rejected as a quote mismatch.
"""

from collections.abc import Sequence
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook

from deepaha.documents.spreadsheet_limits import (
    MAX_MERGE_RANGES,
    MAX_MERGED_CELL_VALUES,
    WorksheetExpansionBudget,
    parse_merge_range,
    preflight_worksheet,
)
from deepaha.documents.spreadsheet_reading import _fill_merged_cells, read_spreadsheet_text

ANCHOR = "中共浙江省纪浙江省监委"
_NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'


def _saved(values: dict[str, str], *merges: str) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "S"
    for reference, value in values.items():
        sheet[reference] = value
    for merge in merges:
        sheet.merge_cells(merge)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _with_raw_merges(content: bytes, merges: str) -> bytes:
    """Insert an arbitrary ``mergeCells`` block; openpyxl never writes a bad one."""
    output = BytesIO()
    with (
        ZipFile(BytesIO(content), "r") as source,
        ZipFile(output, "w", ZIP_DEFLATED) as target,
    ):
        for entry in source.infolist():
            value = source.read(entry.filename)
            if entry.filename == "xl/worksheets/sheet1.xml":
                value = value.replace(
                    b"</sheetData>",
                    b"</sheetData><mergeCells>" + merges.encode() + b"</mergeCells>",
                )
            target.writestr(entry, value)
    return output.getvalue()


def _worksheet_xml(refs: Sequence[str]) -> bytes:
    merges = "".join(f'<mergeCell ref="{ref}"/>' for ref in refs)
    return (
        f"<worksheet {_NS}>"
        '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>x</t></is></c></row></sheetData>'
        f'<mergeCells count="{len(refs)}">{merges}</mergeCells>'
        "</worksheet>"
    ).encode()


def test_merged_cell_reads_the_value_excel_shows_for_it() -> None:
    table = read_spreadsheet_text(_saved({"H5": ANCHOR}, "H5:H6"))

    assert table.rows["S"][5][8] == ANCHOR
    assert table.rows["S"][6][8] == ANCHOR
    assert table.row_counts["S"] == 6


def test_reversed_merge_reference_fills_from_the_anchor() -> None:
    rows: dict[int, dict[int, str]] = {1: {1: ANCHOR}}

    assert _fill_merged_cells(rows, ("B2:A1",)) == 2

    assert rows == {1: {1: ANCHOR, 2: ANCHOR}, 2: {1: ANCHOR, 2: ANCHOR}}


def test_unusable_merge_references_are_ignored() -> None:
    # Reversed and ref-less merges are rejected by openpyxl before we read them,
    # so the end-to-end check stays with the refs openpyxl itself tolerates.
    merges = (
        '<mergeCell ref="A1:A1"/>'  # single cell: already the anchor
        '<mergeCell ref="XFE1:XFE2"/>'  # column outside the grid
        '<mergeCell ref="H5"/>'  # not a range
    )
    content = _with_raw_merges(_saved({"A1": ANCHOR}), merges)

    table = read_spreadsheet_text(content)

    assert table.rows == {"S": {1: {1: ANCHOR}}}
    assert table.row_counts == {"S": 1}


@pytest.mark.parametrize(
    "reference",
    [None, "", "H5", "A1", "1A:2B", "A0:B1", "A1:A1", "A1:A2000000", "XFE1:XFE2", "A1:B2:C3"],
)
def test_merge_references_outside_the_grid_are_not_parsed(reference: str | None) -> None:
    assert parse_merge_range(reference) is None


def test_merge_reference_is_normalized_to_sorted_bounds() -> None:
    assert parse_merge_range("H5:H6") == (5, 8, 6, 8)
    assert parse_merge_range("B2:A1") == (1, 1, 2, 2)


def test_merge_without_an_anchor_value_fills_nothing() -> None:
    table = read_spreadsheet_text(_saved({"B1": ANCHOR}, "A1:A2"))

    assert table.rows["S"] == {1: {2: ANCHOR}}
    assert table.row_counts["S"] == 2


def test_existing_cell_values_are_never_overwritten_by_a_merge() -> None:
    content = _with_raw_merges(_saved({"A1": ANCHOR, "B1": "kept"}), '<mergeCell ref="A1:B1"/>')

    table = read_spreadsheet_text(content)

    assert table.rows["S"] == {1: {1: ANCHOR, 2: "kept"}}


def test_merge_fill_stops_at_the_cell_budget_without_failing() -> None:
    content = _with_raw_merges(_saved({"A1": ANCHOR}), '<mergeCell ref="A1:CV2000"/>')

    table = read_spreadsheet_text(content)

    filled = sum(len(cells) for cells in table.rows["S"].values()) - 1
    assert filled == MAX_MERGED_CELL_VALUES
    assert table.row_counts["S"] == 2000


def test_merge_reference_collection_is_capped() -> None:
    refs = tuple(f"A{i}:B{i}" for i in range(1, MAX_MERGE_RANGES + 11))
    merges: list[str] = []

    preflight_worksheet(
        BytesIO(_worksheet_xml(refs)),
        WorksheetExpansionBudget(),
        required=True,
        merges=merges,
    )

    assert len(merges) == MAX_MERGE_RANGES
