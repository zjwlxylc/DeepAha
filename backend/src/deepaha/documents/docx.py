from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from lxml import etree

from deepaha.documents.blocks import ParsedBlock, validate_parsed_blocks
from deepaha.documents.normalization import normalize_text
from deepaha.documents.parser import (
    P9B_BLOCK_PARSE_CONTRACT_VERSION,
    ExpectedParseError,
    ParsedDocument,
)

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_ARCHIVE_ENTRIES = 10_000
MAX_UNCOMPRESSED_BYTES = 100_000_000
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_NS = {"w": _WORD_NS, "r": _REL_NS}


class DeterministicDocxParser:
    name = "docx_ooxml"
    version = "0.8.0"
    parse_contract_version = P9B_BLOCK_PARSE_CONTRACT_VERSION

    def supports(self, media_type: str) -> bool:
        return media_type.partition(";")[0].strip().lower() == DOCX_MEDIA_TYPE

    def parse(self, content: bytes, *, artifact_sha256: str) -> ParsedDocument:
        if sha256(content).hexdigest() != artifact_sha256:
            raise ValueError("artifact SHA-256 does not match DOCX bytes")
        document_xml = _read_document_xml(content)
        root = _parse_xml(document_xml, "DOCX_PARSE_FAILED")
        body_nodes = _xpath_elements(root, "/w:document/w:body")
        if len(body_nodes) != 1:
            raise ExpectedParseError("DOCX_PARSE_FAILED")
        body = body_nodes[0]
        blocks: list[ParsedBlock] = []
        paragraph_index = 0
        table_index = 0
        for body_index, child in enumerate(body, start=1):
            if child.tag == f"{{{_WORD_NS}}}p":
                paragraph_index += 1
                value = _element_text(child)
                if value:
                    blocks.append(
                        ParsedBlock(
                            block_type="DOCX_PARAGRAPH",
                            canonical_text_or_value=value,
                            structural_locator={
                                "kind": "docx_paragraph",
                                "body_index": body_index,
                                "paragraph_index": paragraph_index,
                            },
                            parent_ordinal=None,
                        )
                    )
                continue
            if child.tag != f"{{{_WORD_NS}}}tbl":
                continue
            table_index += 1
            rows = _xpath_elements(child, "./w:tr")
            for row_index, row in enumerate(rows, start=1):
                cells = _xpath_elements(row, "./w:tc")
                for column_index, cell in enumerate(cells, start=1):
                    value = _element_text(cell)
                    if not value:
                        continue
                    blocks.append(
                        ParsedBlock(
                            block_type="DOCX_TABLE_CELL",
                            canonical_text_or_value=value,
                            structural_locator={
                                "kind": "docx_table_cell",
                                "body_index": body_index,
                                "table_index": table_index,
                                "row_index": row_index,
                                "column_index": column_index,
                            },
                            parent_ordinal=None,
                        )
                    )
        if not blocks:
            raise ExpectedParseError("DOCX_TEXT_EMPTY")
        validated = validate_parsed_blocks(tuple(blocks))
        return ParsedDocument(
            title=None,
            published_at=None,
            language="und",
            normalized_text=normalize_text(
                "\n\n".join(block.canonical_text_or_value for block in validated) + "\n"
            ),
            locators=(),
            needs_review_reasons=(),
            blocks=validated,
        )


def _read_document_xml(content: bytes) -> bytes:
    try:
        with ZipFile(BytesIO(content), "r") as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise ExpectedParseError("DOCX_ENTRY_LIMIT_EXCEEDED")
            if sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED_BYTES:
                raise ExpectedParseError("DOCX_UNCOMPRESSED_SIZE_EXCEEDED")
            names: dict[str, str] = {}
            for entry in entries:
                normalized_name = entry.filename.replace("\\", "/")
                path = PurePosixPath(normalized_name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or (path.parts and ":" in path.parts[0])
                ):
                    raise ExpectedParseError("DOCX_PATH_TRAVERSAL")
                names[normalized_name.lower()] = entry.filename
            if any(name.endswith("vbaproject.bin") for name in names):
                raise ExpectedParseError("DOCX_MACRO_NOT_ALLOWED")
            content_types_name = names.get("[content_types].xml")
            if content_types_name is None:
                raise ExpectedParseError("DOCX_PARSE_FAILED")
            content_types = archive.read(content_types_name).lower()
            if b"macroenabled" in content_types or b"vbaproject" in content_types:
                raise ExpectedParseError("DOCX_MACRO_NOT_ALLOWED")
            for lowered, actual in names.items():
                if not lowered.endswith(".rels"):
                    continue
                relationships = _parse_xml(
                    archive.read(actual),
                    "DOCX_RELATIONSHIP_PARSE_FAILED",
                )
                external = relationships.xpath(
                    "boolean(//r:Relationship[@TargetMode='External'])",
                    namespaces=_NS,
                )
                if external is True:
                    raise ExpectedParseError("DOCX_EXTERNAL_RELATIONSHIP_NOT_ALLOWED")
            document_name = names.get("word/document.xml")
            if document_name is None:
                raise ExpectedParseError("DOCX_PARSE_FAILED")
            return archive.read(document_name)
    except ExpectedParseError:
        raise
    except (BadZipFile, KeyError, OSError) as error:
        raise ExpectedParseError("DOCX_PARSE_FAILED") from error


def _parse_xml(content: bytes, code: str) -> etree._Element:
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        recover=False,
        huge_tree=False,
    )
    try:
        return etree.fromstring(content, parser=parser)
    except (etree.ParserError, etree.XMLSyntaxError) as error:
        raise ExpectedParseError(code) from error


def _element_text(element: etree._Element) -> str:
    fragments = [node.text or "" for node in element.iter(f"{{{_WORD_NS}}}t")]
    return normalize_text("".join(fragments)).strip()


def _xpath_elements(element: etree._Element, expression: str) -> list[etree._Element]:
    result = element.xpath(expression, namespaces=_NS)
    if not isinstance(result, list) or not all(
        isinstance(value, etree._Element) for value in result
    ):
        raise ExpectedParseError("DOCX_PARSE_FAILED")
    return [value for value in result if isinstance(value, etree._Element)]


__all__ = ["DOCX_MEDIA_TYPE", "DeterministicDocxParser"]
