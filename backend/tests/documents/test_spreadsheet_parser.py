import json
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook

from deepaha.contracts.phase2 import SpreadsheetRangeLocator
from deepaha.documents.parser import ExpectedParseError
from deepaha.documents.spreadsheet import OpenpyxlSpreadsheetParser

FIXTURES = Path(__file__).parents[1] / "fixtures" / "documents"
XLSX = FIXTURES / "minimal-table.xlsx"
MANIFEST = FIXTURES / "xlsx-fixtures.manifest.json"


def parse(content: bytes):  # type: ignore[no-untyped-def]
    return OpenpyxlSpreadsheetParser().parse(
        content,
        artifact_sha256=sha256(content).hexdigest(),
    )


def test_xlsx_fixture_matches_manifest() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "1.0.0"
    assert manifest["generator"] == "tests/fixtures/documents/generate_fixtures.py"
    fixture = manifest["fixtures"][0]
    content = XLSX.read_bytes()
    assert len(content) == fixture["byte_size"]
    assert sha256(content).hexdigest() == fixture["content_sha256"]
    assert fixture["synthetic"] is True
    assert fixture["business_facts"] is False
    assert fixture["contains_macros"] is False
    assert fixture["external_links"] is False


def test_xlsx_parser_preserves_formula_and_one_based_rows() -> None:
    parsed = parse(XLSX.read_bytes())

    assert parsed.title is None
    assert parsed.published_at is None
    assert parsed.language == "und"
    assert parsed.needs_review_reasons == ()
    assert parsed.normalized_text == (
        "[岗位表]\n"
        "A1\t名称\nB1\t数量\nC1\t日期\nD1\t公式\n"
        "A2\t合成岗位\nB2\t2\nC2\t2026-08-21\nD2\t=B2*2\n"
        "A4\t合并说明\n\n"
        "[说明]\nA1\t仅用于格式边界测试\n"
    )
    assert len(parsed.locators) == 4
    assert all(isinstance(locator, SpreadsheetRangeLocator) for locator in parsed.locators)
    ranges = [
        (
            locator.sheet_name,
            locator.start_row,
            locator.end_row,
            locator.start_column,
            locator.end_column,
        )
        for locator in parsed.locators
    ]
    assert ranges == [
        ("岗位表", 1, 1, 1, 4),
        ("岗位表", 2, 2, 1, 4),
        ("岗位表", 4, 4, 1, 1),
        ("说明", 1, 1, 1, 1),
    ]
    assert "D2\t=B2*2" in parsed.normalized_text
    assert "D2\t4" not in parsed.normalized_text


def test_xlsx_parser_supports_only_xlsx_media_type() -> None:
    parser = OpenpyxlSpreadsheetParser()

    assert parser.name == "xlsx_openpyxl"
    assert parser.version == "0.2.0"
    assert parser.supports("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert not parser.supports("application/vnd.ms-excel.sheet.macroEnabled.12")
    assert not parser.supports("application/vnd.ms-excel")


def test_empty_workbook_is_a_stable_failure() -> None:
    workbook = Workbook()
    output = BytesIO()
    workbook.save(output)
    workbook.close()

    with pytest.raises(ExpectedParseError) as captured:
        parse(output.getvalue())

    assert captured.value.code == "XLSX_EMPTY"


def test_macro_entry_is_rejected() -> None:
    content = _append_zip_entry(XLSX.read_bytes(), "xl/vbaProject.bin", b"not executable")

    with pytest.raises(ExpectedParseError) as captured:
        parse(content)

    assert captured.value.code == "XLSX_MACRO_NOT_ALLOWED"


def test_archive_entry_limit_is_enforced() -> None:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for index in range(10_001):
            archive.writestr(f"entries/{index}.xml", b"")

    with pytest.raises(ExpectedParseError) as captured:
        parse(output.getvalue())

    assert captured.value.code == "XLSX_ENTRY_LIMIT_EXCEEDED"


def test_uncompressed_size_limit_uses_zip_metadata_before_decompression() -> None:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", b"")
    content = bytearray(output.getvalue())
    central = content.index(b"PK\x01\x02")
    content[central + 24 : central + 28] = (100_000_001).to_bytes(4, "little")

    with pytest.raises(ExpectedParseError) as captured:
        parse(bytes(content))

    assert captured.value.code == "XLSX_UNCOMPRESSED_SIZE_EXCEEDED"


@pytest.mark.parametrize("path", ["../escape.xml", "/absolute.xml", "xl\\..\\escape.xml"])
def test_archive_path_traversal_is_rejected(path: str) -> None:
    content = _append_zip_entry(XLSX.read_bytes(), path, b"unsafe")

    with pytest.raises(ExpectedParseError) as captured:
        parse(content)

    assert captured.value.code == "XLSX_PATH_TRAVERSAL"


def test_external_workbook_link_is_rejected() -> None:
    content = _append_zip_entry(
        XLSX.read_bytes(),
        "xl/externalLinks/externalLink1.xml",
        b"<externalLink/>",
    )

    with pytest.raises(ExpectedParseError) as captured:
        parse(content)

    assert captured.value.code == "XLSX_EXTERNAL_LINK_NOT_ALLOWED"


def test_damaged_zip_is_a_stable_failure() -> None:
    with pytest.raises(ExpectedParseError) as captured:
        parse(b"PK this is not a valid workbook")

    assert captured.value.code == "XLSX_PARSE_FAILED"


def test_artifact_digest_mismatch_is_a_programmer_error() -> None:
    with pytest.raises(ValueError, match="artifact SHA-256"):
        OpenpyxlSpreadsheetParser().parse(XLSX.read_bytes(), artifact_sha256="0" * 64)


def _append_zip_entry(content: bytes, name: str, value: bytes) -> bytes:
    output = BytesIO(content)
    with ZipFile(output, "a", compression=ZIP_DEFLATED) as archive:
        archive.writestr(name, value)
    return output.getvalue()
