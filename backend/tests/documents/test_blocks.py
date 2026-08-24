from hashlib import sha256
from pathlib import Path

import pytest

from deepaha.documents.blocks import (
    ParsedBlock,
    block_hash,
    build_pdf_blocks,
    evidence_binding_hash,
    replay_block_value,
    validate_parsed_blocks,
)
from deepaha.documents.html import P9BHtmlDocumentParser
from deepaha.documents.pdf import P9BPdfDocumentParser
from deepaha.documents.spreadsheet import P9BSpreadsheetDocumentParser

FIXTURES = Path(__file__).parents[1] / "fixtures" / "documents"


def _parse(parser: object, path: Path):  # type: ignore[no-untyped-def]
    content = path.read_bytes()
    return parser.parse(content, artifact_sha256=sha256(content).hexdigest())  # type: ignore[attr-defined]


def test_html_emits_ordered_field_level_element_spans() -> None:
    parsed = _parse(P9BHtmlDocumentParser(), FIXTURES / "minimal-official.html")

    assert [block.block_type for block in parsed.blocks] == ["HTML_ELEMENT"] * 3
    assert [block.canonical_text_or_value for block in parsed.blocks] == [
        "青年机会公告",
        "报名日期：2026-08-21",
        "申请材料 以原文为准。",
    ]
    assert all(block.structural_locator["kind"] == "html_element_span" for block in parsed.blocks)
    assert [block.structural_locator["text_start"] for block in parsed.blocks] == [0, 0, 0]
    assert [block.structural_locator["text_end"] for block in parsed.blocks] == [
        len(block.canonical_text_or_value) for block in parsed.blocks
    ]
    assert (
        replay_block_value(
            parsed.blocks,
            structural_locator=parsed.blocks[1].structural_locator,
            expected_value_sha256=sha256("报名日期：2026-08-21".encode()).hexdigest(),
        )
        == "报名日期：2026-08-21"
    )
    with pytest.raises(LookupError, match="hash"):
        replay_block_value(
            parsed.blocks,
            structural_locator=parsed.blocks[1].structural_locator,
            expected_value_sha256="0" * 64,
        )


def test_pdf_emits_page_bound_text_spans_not_whole_document_locators() -> None:
    parsed = _parse(P9BPdfDocumentParser(), FIXTURES / "minimal-text.pdf")

    assert [block.block_type for block in parsed.blocks] == ["PDF_TEXT_SPAN", "PDF_TEXT_SPAN"]
    assert [block.structural_locator["page_number"] for block in parsed.blocks] == [1, 2]
    assert all(block.structural_locator["text_start"] == 0 for block in parsed.blocks)
    assert [block.structural_locator["text_end"] for block in parsed.blocks] == [
        len("Synthetic PDF page one."),
        len("Synthetic PDF page two."),
    ]


def test_pdf_tabular_text_supports_cell_locators() -> None:
    blocks = build_pdf_blocks(("岗位\t人数\n综合岗\t2",))

    cells = [block for block in blocks if block.block_type == "PDF_TABLE_CELL"]
    assert [block.canonical_text_or_value for block in cells] == ["岗位", "人数", "综合岗", "2"]
    assert [
        (
            block.structural_locator["page_number"],
            block.structural_locator["row_index"],
            block.structural_locator["column_index"],
        )
        for block in cells
    ] == [(1, 1, 1), (1, 1, 2), (1, 2, 1), (1, 2, 2)]


def test_xlsx_emits_row_ranges_with_addressable_child_cells() -> None:
    parsed = _parse(P9BSpreadsheetDocumentParser(), FIXTURES / "minimal-table.xlsx")

    ranges = [block for block in parsed.blocks if block.block_type == "SPREADSHEET_RANGE"]
    cells = [block for block in parsed.blocks if block.block_type == "SPREADSHEET_CELL"]
    assert len(ranges) == 4
    assert len(cells) == 10
    assert all(block.parent_ordinal is not None for block in cells)
    first_cell = cells[0]
    assert first_cell.canonical_text_or_value == "名称"
    assert first_cell.structural_locator == {
        "kind": "spreadsheet_cell",
        "sheet_name": "岗位表",
        "row": 1,
        "column": 1,
    }


def test_block_validation_and_hashes_fail_closed() -> None:
    blocks = (
        ParsedBlock(
            block_type="HTML_ELEMENT",
            canonical_text_or_value="Official fact",
            structural_locator={
                "kind": "html_element_span",
                "selector": "main:nth-of-type(1) > p:nth-of-type(1)",
                "text_start": 0,
                "text_end": 13,
            },
            parent_ordinal=None,
        ),
    )
    validated = validate_parsed_blocks(blocks)
    first_hash = block_hash(
        document_parse_key="1" * 64,
        ordinal=1,
        block=validated[0],
    )
    assert first_hash == block_hash(
        document_parse_key="1" * 64,
        ordinal=1,
        block=validated[0],
    )
    assert first_hash == "ec029e6939f05bafa1fa1d9a5db6ff974e44272a22eb1df380df34157aa889cc"
    binding_hash = evidence_binding_hash(
        block_id="018f4f3d-7b1a-7e66-a9d7-6dfae4f9668b",
        document_parse_key="1" * 64,
        structural_locator=validated[0].structural_locator,
        block_hash_value=first_hash,
    )
    assert binding_hash == "e8d64f910efa05a3d246fb825888c9f86eb37774addcdc1fda5f28371ae46670"
    assert binding_hash != first_hash

    with pytest.raises(ValueError, match="locator kind"):
        validate_parsed_blocks(
            (
                ParsedBlock(
                    block_type="HTML_ELEMENT",
                    canonical_text_or_value="Official fact",
                    structural_locator={
                        "kind": "pdf_text_span",
                        "page_number": 1,
                        "text_start": 0,
                        "text_end": 13,
                    },
                    parent_ordinal=None,
                ),
            )
        )

    with pytest.raises(ValueError, match="earlier block"):
        validate_parsed_blocks(
            (
                ParsedBlock(
                    block_type="SPREADSHEET_CELL",
                    canonical_text_or_value="2",
                    structural_locator={
                        "kind": "spreadsheet_cell",
                        "sheet_name": "岗位表",
                        "row": 2,
                        "column": 2,
                    },
                    parent_ordinal=1,
                ),
            )
        )
