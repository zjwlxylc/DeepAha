from hashlib import sha256
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from deepaha.documents.docx import DOCX_MEDIA_TYPE, DeterministicDocxParser
from deepaha.documents.parser import ExpectedParseError


def _docx(document_xml: str, *, relationships_xml: str | None = None) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        archive.writestr("word/document.xml", document_xml)
        if relationships_xml is not None:
            archive.writestr("word/_rels/document.xml.rels", relationships_xml)
    return output.getvalue()


def _parse(content: bytes):  # type: ignore[no-untyped-def]
    return DeterministicDocxParser().parse(content, artifact_sha256=sha256(content).hexdigest())


def test_docx_emits_paragraph_and_table_cell_blocks() -> None:
    content = _docx(
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        "<w:p><w:r><w:t>报名说明</w:t></w:r></w:p>"
        "<w:tbl><w:tr>"
        "<w:tc><w:p><w:r><w:t>岗位 A</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>2</w:t></w:r></w:p></w:tc>"
        "</w:tr></w:tbl>"
        "</w:body></w:document>"
    )

    parsed = _parse(content)

    assert parsed.normalized_text == "报名说明\n\n岗位 A\n\n2\n"
    assert [block.block_type for block in parsed.blocks] == [
        "DOCX_PARAGRAPH",
        "DOCX_TABLE_CELL",
        "DOCX_TABLE_CELL",
    ]
    assert parsed.blocks[0].structural_locator == {
        "kind": "docx_paragraph",
        "body_index": 1,
        "paragraph_index": 1,
    }
    assert parsed.blocks[1].structural_locator == {
        "kind": "docx_table_cell",
        "body_index": 2,
        "table_index": 1,
        "row_index": 1,
        "column_index": 1,
    }


def test_docx_parser_supports_only_docx_and_uses_new_contract() -> None:
    parser = DeterministicDocxParser()

    assert parser.name == "docx_ooxml"
    assert parser.version == "0.8.0"
    assert parser.parse_contract_version == "p9b-document-block-contract-v0.8.0"
    assert parser.supports(DOCX_MEDIA_TYPE)
    assert not parser.supports("application/msword")


def test_empty_docx_is_a_stable_failure() -> None:
    content = _docx(
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p/></w:body></w:document>"
    )

    with pytest.raises(ExpectedParseError) as captured:
        _parse(content)

    assert captured.value.code == "DOCX_TEXT_EMPTY"


def test_docx_macro_and_external_relationship_are_rejected() -> None:
    content = _docx(
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>safe</w:t></w:r></w:p></w:body></w:document>",
        relationships_xml=(
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" TargetMode="External" Target="https://example.com/x"/>'
            "</Relationships>"
        ),
    )
    with pytest.raises(ExpectedParseError) as captured:
        _parse(content)
    assert captured.value.code == "DOCX_EXTERNAL_RELATIONSHIP_NOT_ALLOWED"

    output = BytesIO(content)
    with ZipFile(output, "a", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/vbaProject.bin", b"not executable")
    with pytest.raises(ExpectedParseError) as captured:
        _parse(output.getvalue())
    assert captured.value.code == "DOCX_MACRO_NOT_ALLOWED"


def test_docx_path_traversal_and_digest_mismatch_are_rejected() -> None:
    content = _docx(
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>safe</w:t></w:r></w:p></w:body></w:document>"
    )
    output = BytesIO(content)
    with ZipFile(output, "a", compression=ZIP_DEFLATED) as archive:
        archive.writestr("../escape.xml", b"unsafe")
    with pytest.raises(ExpectedParseError) as captured:
        _parse(output.getvalue())
    assert captured.value.code == "DOCX_PATH_TRAVERSAL"

    with pytest.raises(ValueError, match="artifact SHA-256"):
        DeterministicDocxParser().parse(content, artifact_sha256="0" * 64)
