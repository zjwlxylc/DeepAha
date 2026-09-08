from dataclasses import dataclass
from hashlib import sha256

from pydantic import TypeAdapter

from deepaha.contracts.evidence_anchor import ReaderAnchor
from deepaha.contracts.phase9b import DocumentBlockLocatorSchemaV08
from deepaha.documents.normalization import normalize_text
from deepaha.p9b.hashing import (
    document_block_hash,
)
from deepaha.p9b.hashing import (
    evidence_binding_hash as calculate_evidence_binding_hash,
)

type StructuralLocator = dict[str, object]
_LOCATOR_ADAPTER: TypeAdapter[DocumentBlockLocatorSchemaV08] = TypeAdapter(
    DocumentBlockLocatorSchemaV08
)
_LOCATOR_FOR_BLOCK_TYPE = {
    "HTML_SECTION": "html_element_span",
    "HTML_ELEMENT": "html_element_span",
    "PDF_TEXT_SPAN": "pdf_text_span",
    "PDF_TABLE_CELL": "pdf_table_cell",
    "SPREADSHEET_CELL": "spreadsheet_cell",
    "SPREADSHEET_RANGE": "spreadsheet_range",
    "DOCX_PARAGRAPH": "docx_paragraph",
    "DOCX_TABLE_CELL": "docx_table_cell",
}


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    block_type: str
    canonical_text_or_value: str
    structural_locator: StructuralLocator
    parent_ordinal: int | None


def validate_parsed_blocks(blocks: tuple[ParsedBlock, ...]) -> tuple[ParsedBlock, ...]:
    if not blocks:
        raise ValueError("parser returned no DocumentBlock")
    result: list[ParsedBlock] = []
    for ordinal, block in enumerate(blocks, start=1):
        if block.block_type == "READER_TEXT_SPAN":
            anchor = ReaderAnchor.model_validate(block.structural_locator)
            if (
                not block.canonical_text_or_value.strip()
                or anchor.text_end != len(block.canonical_text_or_value)
                or anchor.projection_sha256
                != sha256(block.canonical_text_or_value.encode()).hexdigest()
                or block.parent_ordinal is not None
            ):
                raise ValueError("Reader block text or anchor mismatch")
            result.append(
                ParsedBlock(
                    block.block_type,
                    block.canonical_text_or_value,
                    anchor.model_dump(mode="json"),
                    None,
                )
            )
            continue
        expected_kind = _LOCATOR_FOR_BLOCK_TYPE.get(block.block_type)
        if expected_kind is None:
            raise ValueError("unsupported DocumentBlock type")
        if not block.canonical_text_or_value.strip():
            raise ValueError("DocumentBlock value must not be empty")
        if normalize_text(block.canonical_text_or_value) != block.canonical_text_or_value:
            raise ValueError("DocumentBlock value must be normalized")
        locator = _LOCATOR_ADAPTER.validate_python(block.structural_locator)
        if locator.kind != expected_kind:
            raise ValueError("DocumentBlock locator kind does not match block type")
        if block.parent_ordinal is not None and not 1 <= block.parent_ordinal < ordinal:
            raise ValueError("DocumentBlock parent must reference an earlier block")
        result.append(
            ParsedBlock(
                block_type=block.block_type,
                canonical_text_or_value=block.canonical_text_or_value,
                structural_locator=locator.model_dump(mode="json"),
                parent_ordinal=block.parent_ordinal,
            )
        )
    return tuple(result)


def block_hash(*, document_parse_key: str, ordinal: int, block: ParsedBlock) -> str:
    return document_block_hash(
        {
            "block_type": block.block_type,
            "canonical_text_or_value": block.canonical_text_or_value,
            "document_parse_key": document_parse_key,
            "ordinal": ordinal,
            "parent_ordinal": block.parent_ordinal,
            "structural_locator": block.structural_locator,
        },
    )


def evidence_binding_hash(
    *,
    block_id: str,
    document_parse_key: str,
    structural_locator: StructuralLocator,
    block_hash_value: str,
) -> str:
    return calculate_evidence_binding_hash(
        {
            "block_hash": block_hash_value,
            "block_id": block_id,
            "document_parse_key": document_parse_key,
            "structural_locator": structural_locator,
        },
    )


def build_pdf_blocks(page_texts: tuple[str, ...]) -> tuple[ParsedBlock, ...]:
    blocks: list[ParsedBlock] = []
    for page_number, page_text in enumerate(page_texts, start=1):
        cursor = 0
        for raw_line in page_text.splitlines():
            line = normalize_text(raw_line).strip()
            if not line:
                cursor += len(raw_line) + 1
                continue
            start = page_text.find(raw_line, cursor)
            if start < 0:
                start = cursor
            cursor = start + len(raw_line) + 1
            if "\t" in raw_line:
                for column_index, raw_cell in enumerate(raw_line.split("\t"), start=1):
                    cell = normalize_text(raw_cell).strip()
                    if not cell:
                        continue
                    blocks.append(
                        ParsedBlock(
                            block_type="PDF_TABLE_CELL",
                            canonical_text_or_value=cell,
                            structural_locator={
                                "kind": "pdf_table_cell",
                                "page_number": page_number,
                                "row_index": len(
                                    [
                                        value
                                        for value in page_text[:start].splitlines()
                                        if value.strip()
                                    ]
                                )
                                + 1,
                                "column_index": column_index,
                            },
                            parent_ordinal=None,
                        )
                    )
                continue
            blocks.append(
                ParsedBlock(
                    block_type="PDF_TEXT_SPAN",
                    canonical_text_or_value=line,
                    structural_locator={
                        "kind": "pdf_text_span",
                        "page_number": page_number,
                        "text_start": start,
                        "text_end": start + len(raw_line),
                    },
                    parent_ordinal=None,
                )
            )
    return validate_parsed_blocks(tuple(blocks))


def replay_block_value(
    blocks: tuple[ParsedBlock, ...],
    *,
    structural_locator: StructuralLocator,
    expected_value_sha256: str,
) -> str:
    locator = (
        ReaderAnchor.model_validate(structural_locator).model_dump(mode="json")
        if structural_locator.get("kind") == "reader_anchor"
        else _LOCATOR_ADAPTER.validate_python(structural_locator).model_dump(mode="json")
    )
    matches = [
        block for block in validate_parsed_blocks(blocks) if block.structural_locator == locator
    ]
    if len(matches) != 1:
        raise LookupError("DocumentBlock locator must resolve exactly one block")
    value = matches[0].canonical_text_or_value
    if sha256(value.encode("utf-8")).hexdigest() != expected_value_sha256:
        raise LookupError("DocumentBlock locator value hash mismatch")
    return value


__all__ = [
    "ParsedBlock",
    "StructuralLocator",
    "block_hash",
    "build_pdf_blocks",
    "evidence_binding_hash",
    "replay_block_value",
    "validate_parsed_blocks",
]
