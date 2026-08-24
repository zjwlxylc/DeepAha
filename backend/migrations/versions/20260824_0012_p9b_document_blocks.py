"""p9b_document_blocks

Revision ID: 20260824_0012
Revises: 20260824_0011
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260824_0012"
down_revision: str | None = "20260824_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LOCATOR_KIND = (
    "locator_kind in ('page', 'paragraph', 'css_selector', 'text_span', 'full_document', "
    "'html_selector', 'pdf_page_text', 'spreadsheet_range', 'html_element_span', "
    "'pdf_text_span', 'pdf_table_cell', 'spreadsheet_cell', 'docx_paragraph', "
    "'docx_table_cell')"
)
_LOCATOR_FORM = (
    "(locator_schema_version = '0.1.0' and locator_kind in ('page', 'paragraph', "
    "'css_selector', 'text_span', 'full_document') and locator_value is not null and "
    "locator_payload is null) or (locator_schema_version = '0.2.0' and locator_kind in "
    "('html_selector', 'pdf_page_text', 'spreadsheet_range') and locator_value is null and "
    "locator_payload is not null) or (locator_schema_version = '0.8.0' and locator_kind in "
    "('html_element_span', 'pdf_text_span', 'pdf_table_cell', 'spreadsheet_cell', "
    "'spreadsheet_range', 'docx_paragraph', 'docx_table_cell') and locator_value is null and "
    "locator_payload is not null)"
)
_LOCATOR_PAYLOAD_V02 = (
    "locator_schema_version = '0.2.0' and jsonb_typeof(locator_payload) = 'object' and "
    "locator_payload->>'schema_version' = '0.2.0' and locator_payload->>'kind' = locator_kind "
    "and ((locator_kind = 'html_selector' and locator_payload ?& "
    "array['schema_version', 'kind', 'selector', 'text_sha256'] and locator_payload - "
    "array['schema_version', 'kind', 'selector', 'text_sha256'] = '{}'::jsonb and "
    'locator_payload @@ \'$.selector.type() == "string" && $.selector != ""\' and '
    "locator_payload->>'text_sha256' ~ '^[0-9a-f]{64}$') or (locator_kind = "
    "'pdf_page_text' and locator_payload ?& array['schema_version', 'kind', 'page_number', "
    "'text_start', 'text_end', 'text_sha256'] and locator_payload - array['schema_version', "
    "'kind', 'page_number', 'text_start', 'text_end', 'text_sha256'] = '{}'::jsonb and "
    'locator_payload @@ \'$.page_number.type() == "number" && $.page_number >= 1 && '
    '$.text_start.type() == "number" && $.text_start >= 0 && $.text_end.type() == '
    "\"number\" && $.text_end > $.text_start' and locator_payload->>'text_sha256' ~ "
    "'^[0-9a-f]{64}$') or (locator_kind = 'spreadsheet_range' and locator_payload ?& "
    "array['schema_version', 'kind', 'sheet_name', 'start_row', 'end_row', 'start_column', "
    "'end_column', 'cells_sha256'] and locator_payload - array['schema_version', 'kind', "
    "'sheet_name', 'start_row', 'end_row', 'start_column', 'end_column', 'cells_sha256'] = "
    "'{}'::jsonb and locator_payload @@ '$.sheet_name.type() == \"string\" && "
    '$.sheet_name != "" && $.start_row.type() == "number" && $.start_row >= 1 && '
    '$.end_row.type() == "number" && $.end_row >= $.start_row && '
    '$.start_column.type() == "number" && $.start_column >= 1 && '
    '$.end_column.type() == "number" && $.end_column >= $.start_column\' and '
    "locator_payload->>'cells_sha256' ~ '^[0-9a-f]{64}$'))"
)
_LOCATOR_PAYLOAD_V08 = (
    "locator_schema_version = '0.8.0' and jsonb_typeof(locator_payload) = 'object' and "
    "locator_payload ?& array['schema_version', 'kind', 'block_id', 'document_parse_key', "
    "'block_type', 'structural_locator', 'value_sha256'] and locator_payload - "
    "array['schema_version', 'kind', 'block_id', 'document_parse_key', 'block_type', "
    "'structural_locator', 'value_sha256'] = '{}'::jsonb and "
    "locator_payload->>'schema_version' = '0.8.0' and locator_payload->>'kind' = locator_kind "
    "and locator_payload->>'document_parse_key' ~ '^[0-9a-f]{64}$' and "
    "locator_payload->>'value_sha256' ~ '^[0-9a-f]{64}$' and "
    "jsonb_typeof(locator_payload->'structural_locator') = 'object'"
)
_LOCATOR_PAYLOAD = (
    f"(locator_schema_version not in ('0.2.0', '0.8.0')) or ({_LOCATOR_PAYLOAD_V02}) or "
    f"({_LOCATOR_PAYLOAD_V08})"
)


def upgrade() -> None:
    _replace_evidence_constraints(p9b=True)
    op.create_table(
        "document_blocks",
        sa.Column("block_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("document_parse_key", sa.String(length=64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(length=32), nullable=False),
        sa.Column("canonical_text_or_value", sa.Text(), nullable=False),
        sa.Column("structural_locator", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("block_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_binding_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_ref_id", sa.Uuid(), nullable=False),
        sa.Column("parent_block_id", sa.Uuid(), nullable=True),
        sa.Column("parser_name", sa.String(length=128), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("parse_contract_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(block_id) = 7",
            name=op.f("ck_document_blocks_block_id_uuid7"),
        ),
        sa.CheckConstraint("ordinal >= 1", name=op.f("ck_document_blocks_ordinal_positive")),
        sa.CheckConstraint(
            "block_type in ('HTML_SECTION', 'HTML_ELEMENT', 'PDF_TEXT_SPAN', "
            "'PDF_TABLE_CELL', 'SPREADSHEET_CELL', 'SPREADSHEET_RANGE', 'DOCX_PARAGRAPH', "
            "'DOCX_TABLE_CELL', 'OCR_TEXT_SPAN')",
            name=op.f("ck_document_blocks_block_type_values"),
        ),
        sa.CheckConstraint(
            "length(btrim(canonical_text_or_value)) >= 1",
            name=op.f("ck_document_blocks_canonical_value_nonempty"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(structural_locator) = 'object'",
            name=op.f("ck_document_blocks_structural_locator_object"),
        ),
        sa.CheckConstraint(
            "document_parse_key ~ '^[0-9a-f]{64}$' and block_hash ~ '^[0-9a-f]{64}$' and "
            "evidence_binding_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_document_blocks_hash_formats"),
        ),
        sa.ForeignKeyConstraint(
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
            name=op.f("fk_document_blocks_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_ref_id", "document_id"],
            ["evidence_refs.evidence_ref_id", "evidence_refs.document_id"],
            name=op.f("fk_document_blocks_evidence_ref_id_evidence_refs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "parent_block_id"],
            ["document_blocks.document_id", "document_blocks.block_id"],
            name=op.f("fk_document_blocks_parent_block_id_document_blocks"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("block_id", name=op.f("pk_document_blocks")),
        sa.UniqueConstraint(
            "document_id",
            "ordinal",
            name="uq_document_blocks_document_ordinal",
        ),
        sa.UniqueConstraint(
            "document_id",
            "block_id",
            name="uq_document_blocks_document_block",
        ),
        sa.UniqueConstraint("evidence_ref_id", name="uq_document_blocks_evidence_ref"),
    )
    op.execute(
        """
        CREATE FUNCTION p9b_document_blocks_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            evidence evidence_refs%ROWTYPE;
            expected_kind text;
            parent_ordinal integer;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'document_blocks are immutable';
            END IF;
            SELECT * INTO evidence FROM evidence_refs
            WHERE evidence_ref_id = NEW.evidence_ref_id AND document_id = NEW.document_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'DocumentBlock EvidenceRef binding does not exist';
            END IF;
            expected_kind := CASE NEW.block_type
                WHEN 'HTML_SECTION' THEN 'html_element_span'
                WHEN 'HTML_ELEMENT' THEN 'html_element_span'
                WHEN 'PDF_TEXT_SPAN' THEN 'pdf_text_span'
                WHEN 'PDF_TABLE_CELL' THEN 'pdf_table_cell'
                WHEN 'SPREADSHEET_CELL' THEN 'spreadsheet_cell'
                WHEN 'SPREADSHEET_RANGE' THEN 'spreadsheet_range'
                WHEN 'DOCX_PARAGRAPH' THEN 'docx_paragraph'
                WHEN 'DOCX_TABLE_CELL' THEN 'docx_table_cell'
                ELSE NULL
            END;
            IF expected_kind IS NULL OR evidence.locator_kind <> expected_kind OR
               evidence.locator_schema_version <> '0.8.0' OR
               evidence.locator_payload->>'block_id' <> NEW.block_id::text OR
               evidence.locator_payload->>'document_parse_key' <> NEW.document_parse_key OR
               evidence.locator_payload->>'block_type' <> NEW.block_type OR
               evidence.locator_payload->'structural_locator' <> NEW.structural_locator OR
               evidence.locator_payload->>'value_sha256' <> evidence.quote_sha256 THEN
                RAISE EXCEPTION 'DocumentBlock locator binding mismatch';
            END IF;
            IF NEW.parent_block_id IS NOT NULL THEN
                SELECT ordinal INTO parent_ordinal FROM document_blocks
                WHERE document_id = NEW.document_id AND block_id = NEW.parent_block_id;
                IF NOT FOUND OR parent_ordinal >= NEW.ordinal THEN
                    RAISE EXCEPTION 'DocumentBlock parent order mismatch';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER document_blocks_guard BEFORE INSERT OR UPDATE OR DELETE ON "
        "document_blocks FOR EACH ROW EXECUTE FUNCTION p9b_document_blocks_guard()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    block_count = connection.execute(sa.text("select count(*) from document_blocks")).scalar_one()
    locator_count = connection.execute(
        sa.text("select count(*) from evidence_refs where locator_schema_version = '0.8.0'")
    ).scalar_one()
    if block_count or locator_count:
        raise RuntimeError("cannot downgrade P9-B DocumentBlock migration with block history")
    op.execute("DROP TRIGGER document_blocks_guard ON document_blocks")
    op.execute("DROP FUNCTION p9b_document_blocks_guard()")
    op.drop_table("document_blocks")
    _replace_evidence_constraints(p9b=False)


def _replace_evidence_constraints(*, p9b: bool) -> None:
    for name in (
        "ck_evidence_refs_locator_payload_shape",
        "ck_evidence_refs_locator_schema_form",
        "ck_evidence_refs_locator_kind_values",
    ):
        op.drop_constraint(op.f(name), "evidence_refs", type_="check")
    if p9b:
        op.create_check_constraint(
            op.f("ck_evidence_refs_locator_kind_values"),
            "evidence_refs",
            _LOCATOR_KIND,
        )
        op.create_check_constraint(
            op.f("ck_evidence_refs_locator_schema_form"),
            "evidence_refs",
            _LOCATOR_FORM,
        )
        op.create_check_constraint(
            op.f("ck_evidence_refs_locator_payload_shape"),
            "evidence_refs",
            _LOCATOR_PAYLOAD,
        )
        return
    legacy_payload = _LOCATOR_PAYLOAD_V02.replace(
        "locator_schema_version = '0.2.0' and ",
        "",
        1,
    )
    op.create_check_constraint(
        op.f("ck_evidence_refs_locator_kind_values"),
        "evidence_refs",
        "locator_kind in ('page', 'paragraph', 'css_selector', 'text_span', 'full_document', "
        "'html_selector', 'pdf_page_text', 'spreadsheet_range')",
    )
    op.create_check_constraint(
        op.f("ck_evidence_refs_locator_schema_form"),
        "evidence_refs",
        "(locator_schema_version = '0.1.0' and locator_kind in ('page', 'paragraph', "
        "'css_selector', 'text_span', 'full_document') and locator_value is not null and "
        "locator_payload is null) or (locator_schema_version = '0.2.0' and locator_kind in "
        "('html_selector', 'pdf_page_text', 'spreadsheet_range') and locator_value is null and "
        "locator_payload is not null)",
    )
    op.create_check_constraint(
        op.f("ck_evidence_refs_locator_payload_shape"),
        "evidence_refs",
        f"locator_schema_version <> '0.2.0' or ({legacy_payload})",
    )
