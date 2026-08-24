from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(document_id) = 7", name="document_id_uuid7"),
        CheckConstraint(
            "parse_confidence is null or parse_confidence between 0 and 1",
            name="parse_confidence_range",
        ),
        CheckConstraint(
            "document_parse_key ~ '^[0-9a-f]{64}$'",
            name="document_parse_key_format",
        ),
        UniqueConstraint(
            "artifact_id",
            "parser_name",
            "parser_version",
            "parse_contract_version",
            name="uq_documents_parse_identity",
        ),
        UniqueConstraint("document_id", "artifact_id"),
        UniqueConstraint(
            "document_id",
            "artifact_id",
            "document_parse_key",
            "parser_name",
            "parser_version",
            "parse_contract_version",
            name="uq_documents_p9b_parse_binding",
        ),
    )

    document_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    artifact_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("raw_artifacts.artifact_id", ondelete="RESTRICT"),
    )
    title: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    language: Mapped[str] = mapped_column(String(35))
    extracted_text_uri: Mapped[str | None] = mapped_column(Text)
    parser_name: Mapped[str] = mapped_column(String(128))
    parser_version: Mapped[str] = mapped_column(String(64))
    parse_contract_version: Mapped[str] = mapped_column(String(64))
    document_parse_key: Mapped[str] = mapped_column(String(64))
    parse_confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvidenceRef(Base):
    __tablename__ = "evidence_refs"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(evidence_ref_id) = 7",
            name="evidence_ref_id_uuid7",
        ),
        CheckConstraint(
            "locator_kind in ('page', 'paragraph', 'css_selector', 'text_span', 'full_document', "
            "'html_selector', 'pdf_page_text', 'spreadsheet_range', "
            "'html_element_span', 'pdf_text_span', 'pdf_table_cell', "
            "'spreadsheet_cell', 'docx_paragraph', 'docx_table_cell')",
            name="locator_kind_values",
        ),
        CheckConstraint(
            "(locator_schema_version = '0.1.0' and "
            "locator_kind in ('page', 'paragraph', 'css_selector', 'text_span', 'full_document') "
            "and locator_value is not null and locator_payload is null) or "
            "(locator_schema_version = '0.2.0' and "
            "locator_kind in ('html_selector', 'pdf_page_text', 'spreadsheet_range') "
            "and locator_value is null and locator_payload is not null)"
            " or (locator_schema_version = '0.8.0' and "
            "locator_kind in ('html_element_span', 'pdf_text_span', 'pdf_table_cell', "
            "'spreadsheet_cell', 'spreadsheet_range', 'docx_paragraph', "
            "'docx_table_cell') and locator_value is null and locator_payload is not null)",
            name="locator_schema_form",
        ),
        CheckConstraint(
            "locator_schema_version <> '0.1.0' or locator_kind <> 'full_document' "
            "or locator_value = '*'",
            name="full_document_locator_value",
        ),
        CheckConstraint(
            "((locator_schema_version not in ('0.2.0', '0.8.0')) or "
            "(locator_schema_version = '0.2.0' and ("
            "jsonb_typeof(locator_payload) = 'object' and "
            "locator_payload->>'schema_version' = '0.2.0' and "
            "locator_payload->>'kind' = locator_kind and ("
            "(locator_kind = 'html_selector' and locator_payload ?& "
            "array['schema_version', 'kind', 'selector', 'text_sha256'] and "
            "locator_payload - array['schema_version', 'kind', 'selector', 'text_sha256'] "
            "= '{}'::jsonb and "
            'locator_payload @@ \'$.selector.type() == "string" && $.selector != ""\' and '
            "locator_payload->>'text_sha256' ~ '^[0-9a-f]{64}$') or "
            "(locator_kind = 'pdf_page_text' and locator_payload ?& "
            "array['schema_version', 'kind', 'page_number', 'text_start', 'text_end', "
            "'text_sha256'] and locator_payload - array['schema_version', 'kind', "
            "'page_number', 'text_start', 'text_end', 'text_sha256'] = '{}'::jsonb and "
            'locator_payload @@ \'$.page_number.type() == "number" && $.page_number >= 1 '
            '&& $.text_start.type() == "number" && $.text_start >= 0 '
            '&& $.text_end.type() == "number" && $.text_end > $.text_start\' and '
            "locator_payload->>'text_sha256' ~ '^[0-9a-f]{64}$') or "
            "(locator_kind = 'spreadsheet_range' and locator_payload ?& "
            "array['schema_version', 'kind', 'sheet_name', 'start_row', 'end_row', "
            "'start_column', 'end_column', 'cells_sha256'] and locator_payload - "
            "array['schema_version', 'kind', 'sheet_name', 'start_row', 'end_row', "
            "'start_column', 'end_column', 'cells_sha256'] = '{}'::jsonb and "
            'locator_payload @@ \'$.sheet_name.type() == "string" && $.sheet_name != "" '
            '&& $.start_row.type() == "number" && $.start_row >= 1 '
            '&& $.end_row.type() == "number" && $.end_row >= $.start_row '
            '&& $.start_column.type() == "number" && $.start_column >= 1 '
            '&& $.end_column.type() == "number" && $.end_column >= $.start_column\' and '
            "locator_payload->>'cells_sha256' ~ '^[0-9a-f]{64}$')"
            "))) or (locator_schema_version = '0.8.0' and "
            "jsonb_typeof(locator_payload) = 'object' and locator_payload ?& "
            "array['schema_version', 'kind', 'block_id', 'document_parse_key', "
            "'block_type', 'structural_locator', 'value_sha256'] and "
            "locator_payload - array['schema_version', 'kind', 'block_id', "
            "'document_parse_key', 'block_type', 'structural_locator', 'value_sha256'] "
            "= '{}'::jsonb and locator_payload->>'schema_version' = '0.8.0' and "
            "locator_payload->>'kind' = locator_kind and "
            "locator_payload->>'document_parse_key' ~ '^[0-9a-f]{64}$' and "
            "locator_payload->>'value_sha256' ~ '^[0-9a-f]{64}$' and "
            "jsonb_typeof(locator_payload->'structural_locator') = 'object'))",
            name="locator_payload_shape",
        ),
        CheckConstraint(
            "quote_sha256 is null or quote_sha256 ~ '^[0-9a-f]{64}$'",
            name="quote_sha256_format",
        ),
        ForeignKeyConstraint(
            ["document_id", "artifact_id"],
            ["documents.document_id", "documents.artifact_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("evidence_ref_id", "document_id"),
    )

    evidence_ref_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    document_id: Mapped[UUID] = mapped_column(Uuid)
    artifact_id: Mapped[UUID] = mapped_column(Uuid)
    locator_kind: Mapped[str] = mapped_column(String(32))
    locator_value: Mapped[str | None] = mapped_column(Text)
    locator_schema_version: Mapped[str] = mapped_column(
        String(16),
        server_default=text("'0.1.0'"),
    )
    locator_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True))
    quote_sha256: Mapped[str | None] = mapped_column(String(64))


class ParseAttempt(Base):
    __tablename__ = "parse_attempts"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(parse_attempt_id) = 7",
            name="parse_attempt_id_uuid7",
        ),
        CheckConstraint("completed_at >= started_at", name="timestamp_order"),
        CheckConstraint(
            "outcome in ('SUCCEEDED', 'NEEDS_REVIEW', 'FAILED')",
            name="outcome_values",
        ),
        CheckConstraint(
            "(outcome = 'SUCCEEDED' and document_id is not null and error_code is null) or "
            "(outcome = 'NEEDS_REVIEW' and document_id is not null) or "
            "(outcome = 'FAILED' and document_id is null and error_code is not null)",
            name="outcome_state",
        ),
        CheckConstraint(
            "document_parse_key ~ '^[0-9a-f]{64}$'",
            name="document_parse_key_format",
        ),
        ForeignKeyConstraint(
            ["document_id", "artifact_id"],
            ["documents.document_id", "documents.artifact_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "artifact_id",
            "parser_name",
            "parser_version",
            "parse_contract_version",
            name="uq_parse_attempts_parse_identity",
        ),
    )

    parse_attempt_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    artifact_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("raw_artifacts.artifact_id", ondelete="RESTRICT"),
    )
    parser_name: Mapped[str] = mapped_column(String(128))
    parser_version: Mapped[str] = mapped_column(String(64))
    parse_contract_version: Mapped[str] = mapped_column(String(64))
    document_parse_key: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(16))
    document_id: Mapped[UUID | None] = mapped_column(Uuid)
    error_code: Mapped[str | None] = mapped_column(String(128))
    input_media_type: Mapped[str] = mapped_column(Text)


class DocumentBlock(Base):
    __tablename__ = "document_blocks"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(block_id) = 7", name="block_id_uuid7"),
        CheckConstraint("ordinal >= 1", name="ordinal_positive"),
        CheckConstraint(
            "block_type in ('HTML_SECTION', 'HTML_ELEMENT', 'PDF_TEXT_SPAN', "
            "'PDF_TABLE_CELL', 'SPREADSHEET_CELL', 'SPREADSHEET_RANGE', "
            "'DOCX_PARAGRAPH', 'DOCX_TABLE_CELL', 'OCR_TEXT_SPAN')",
            name="block_type_values",
        ),
        CheckConstraint(
            "length(btrim(canonical_text_or_value)) >= 1",
            name="canonical_value_nonempty",
        ),
        CheckConstraint(
            "jsonb_typeof(structural_locator) = 'object'",
            name="structural_locator_object",
        ),
        CheckConstraint(
            "document_parse_key ~ '^[0-9a-f]{64}$' and "
            "block_hash ~ '^[0-9a-f]{64}$' and "
            "evidence_binding_hash ~ '^[0-9a-f]{64}$'",
            name="hash_formats",
        ),
        ForeignKeyConstraint(
            [
                "document_id",
                "artifact_id",
                "document_parse_key",
                "parser_name",
                "parser_version",
                "parse_contract_version",
            ],
            [
                "documents.document_id",
                "documents.artifact_id",
                "documents.document_parse_key",
                "documents.parser_name",
                "documents.parser_version",
                "documents.parse_contract_version",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["evidence_ref_id", "document_id"],
            ["evidence_refs.evidence_ref_id", "evidence_refs.document_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["document_id", "parent_block_id"],
            ["document_blocks.document_id", "document_blocks.block_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("document_id", "ordinal", name="uq_document_blocks_document_ordinal"),
        UniqueConstraint("document_id", "block_id", name="uq_document_blocks_document_block"),
        UniqueConstraint(
            "block_id",
            "evidence_ref_id",
            "document_id",
            name="uq_document_blocks_candidate_evidence_binding",
        ),
        UniqueConstraint("evidence_ref_id", name="uq_document_blocks_evidence_ref"),
    )

    block_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    document_id: Mapped[UUID] = mapped_column(Uuid)
    artifact_id: Mapped[UUID] = mapped_column(Uuid)
    document_parse_key: Mapped[str] = mapped_column(String(64))
    ordinal: Mapped[int] = mapped_column(Integer)
    block_type: Mapped[str] = mapped_column(String(32))
    canonical_text_or_value: Mapped[str] = mapped_column(Text)
    structural_locator: Mapped[dict[str, object]] = mapped_column(JSONB)
    block_hash: Mapped[str] = mapped_column(String(64))
    evidence_binding_hash: Mapped[str] = mapped_column(String(64))
    evidence_ref_id: Mapped[UUID] = mapped_column(Uuid)
    parent_block_id: Mapped[UUID | None] = mapped_column(Uuid)
    parser_name: Mapped[str] = mapped_column(String(128))
    parser_version: Mapped[str] = mapped_column(String(64))
    parse_contract_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
