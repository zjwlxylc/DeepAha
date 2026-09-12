"""Let an excluded binary persist as an opaque, text-free DocumentBlock.

An ``OPAQUE_BINARY`` block deliberately carries no text: it only cites the whole original
file by digest through the ``opaque_whole_file`` locator. Four CHECK constraints and the
``p9b_document_blocks_guard()`` trigger currently refuse such a row, so this revision opens
exactly that one shape and nothing else.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260911_0054"
down_revision = "20260911_0053"
branch_labels = None
depends_on = None

# Frozen SQL envelopes, independent of future application code. The "before" text is the
# state left by 20260908_0038 and must be restored verbatim by downgrade().
BLOCK_TYPES_BEFORE = (
    "block_type in ('HTML_SECTION', 'HTML_ELEMENT', 'PDF_TEXT_SPAN', 'PDF_TABLE_CELL', "
    "'SPREADSHEET_CELL', 'SPREADSHEET_RANGE', 'DOCX_PARAGRAPH', 'DOCX_TABLE_CELL', "
    "'OCR_TEXT_SPAN', 'READER_TEXT_SPAN')"
)
BLOCK_TYPES_AFTER = (
    "block_type in ('HTML_SECTION', 'HTML_ELEMENT', 'PDF_TEXT_SPAN', 'PDF_TABLE_CELL', "
    "'SPREADSHEET_CELL', 'SPREADSHEET_RANGE', 'DOCX_PARAGRAPH', 'DOCX_TABLE_CELL', "
    "'OCR_TEXT_SPAN', 'READER_TEXT_SPAN', 'OPAQUE_BINARY')"
)
VALUE_NONEMPTY_BEFORE = "length(btrim(canonical_text_or_value)) >= 1"
VALUE_NONEMPTY_AFTER = "block_type = 'OPAQUE_BINARY' OR length(btrim(canonical_text_or_value)) >= 1"
LOCATOR_KINDS_BEFORE = (
    "locator_kind in ('page', 'paragraph', 'css_selector', 'text_span', 'full_document', "
    "'html_selector', 'pdf_page_text', 'spreadsheet_range', 'html_element_span', "
    "'pdf_text_span', 'pdf_table_cell', 'spreadsheet_cell', 'docx_paragraph', "
    "'docx_table_cell', 'reader_anchor')"
)
LOCATOR_KINDS_AFTER = (
    "locator_kind in ('page', 'paragraph', 'css_selector', 'text_span', 'full_document', "
    "'html_selector', 'pdf_page_text', 'spreadsheet_range', 'html_element_span', "
    "'pdf_text_span', 'pdf_table_cell', 'spreadsheet_cell', 'docx_paragraph', "
    "'docx_table_cell', 'reader_anchor', 'opaque_whole_file')"
)
SCHEMA_FORM_BEFORE = (
    "(locator_schema_version = '0.1.0' and "
    "locator_kind in ('page', 'paragraph', 'css_selector', 'text_span', 'full_document') "
    "and locator_value is not null and locator_payload is null) or "
    "(locator_schema_version = '0.2.0' and "
    "locator_kind in ('html_selector', 'pdf_page_text', 'spreadsheet_range') and "
    "locator_value is null and locator_payload is not null) or "
    "(locator_schema_version = '0.8.0' and "
    "locator_kind in ('html_element_span', 'pdf_text_span', 'pdf_table_cell', "
    "'spreadsheet_cell', 'spreadsheet_range', 'docx_paragraph', 'docx_table_cell') and "
    "locator_value is null and locator_payload is not null) or "
    "(locator_schema_version = '0.9.0' and locator_kind = 'reader_anchor' and "
    "locator_value is null and locator_payload is not null)"
)
SCHEMA_FORM_AFTER = (
    "(locator_schema_version = '0.1.0' and "
    "locator_kind in ('page', 'paragraph', 'css_selector', 'text_span', 'full_document') "
    "and locator_value is not null and locator_payload is null) or "
    "(locator_schema_version = '0.2.0' and "
    "locator_kind in ('html_selector', 'pdf_page_text', 'spreadsheet_range') and "
    "locator_value is null and locator_payload is not null) or "
    "(locator_schema_version = '0.8.0' and "
    "locator_kind in ('html_element_span', 'pdf_text_span', 'pdf_table_cell', "
    "'spreadsheet_cell', 'spreadsheet_range', 'docx_paragraph', 'docx_table_cell', "
    "'opaque_whole_file') and locator_value is null and locator_payload is not null) or "
    "(locator_schema_version = '0.9.0' and locator_kind = 'reader_anchor' and "
    "locator_value is null and locator_payload is not null)"
)

# The guard maps block_type -> expected locator kind; OPAQUE_BINARY would resolve to NULL
# and raise "DocumentBlock locator binding mismatch" without this arm.
_OPAQUE_CASE = "WHEN 'OPAQUE_BINARY' THEN 'opaque_whole_file'\n                "


def _replace_check(table: str, name: str, definition: str) -> None:
    op.drop_constraint(op.f(name), table, type_="check")
    op.create_check_constraint(op.f(name), table, definition)


def _guard(*, upgrade: bool) -> None:
    definition = op.get_bind().scalar(
        sa.text("select pg_get_functiondef('p9b_document_blocks_guard()'::regprocedure)")
    )
    if not isinstance(definition, str):
        raise RuntimeError("DocumentBlock guard is missing")
    if upgrade:
        if _OPAQUE_CASE in definition or "WHEN 'HTML_SECTION'" not in definition:
            raise RuntimeError("Unsupported DocumentBlock guard definition")
        definition = definition.replace("WHEN 'HTML_SECTION'", _OPAQUE_CASE + "WHEN 'HTML_SECTION'")
    else:
        if _OPAQUE_CASE not in definition:
            raise RuntimeError("Unsupported DocumentBlock guard definition")
        definition = definition.replace(_OPAQUE_CASE, "")
    op.get_bind().exec_driver_sql(definition.replace("%", "%%"))


def upgrade() -> None:
    _replace_check(
        "document_blocks",
        "ck_document_blocks_block_type_values",
        BLOCK_TYPES_AFTER,
    )
    _replace_check(
        "document_blocks",
        "ck_document_blocks_canonical_value_nonempty",
        VALUE_NONEMPTY_AFTER,
    )
    _replace_check(
        "evidence_refs",
        "ck_evidence_refs_locator_kind_values",
        LOCATOR_KINDS_AFTER,
    )
    _replace_check(
        "evidence_refs",
        "ck_evidence_refs_locator_schema_form",
        SCHEMA_FORM_AFTER,
    )
    _guard(upgrade=True)


def downgrade() -> None:
    counts = (
        op.get_bind()
        .execute(
            sa.text(
                "select (select count(*) from document_blocks where block_type = 'OPAQUE_BINARY'), "
                "(select count(*) from evidence_refs where locator_kind = 'opaque_whole_file')"
            )
        )
        .one()
    )
    if any(counts):
        raise RuntimeError("Cannot discard opaque DocumentBlock history")
    _guard(upgrade=False)
    _replace_check(
        "evidence_refs",
        "ck_evidence_refs_locator_schema_form",
        SCHEMA_FORM_BEFORE,
    )
    _replace_check(
        "evidence_refs",
        "ck_evidence_refs_locator_kind_values",
        LOCATOR_KINDS_BEFORE,
    )
    _replace_check(
        "document_blocks",
        "ck_document_blocks_canonical_value_nonempty",
        VALUE_NONEMPTY_BEFORE,
    )
    _replace_check(
        "document_blocks",
        "ck_document_blocks_block_type_values",
        BLOCK_TYPES_BEFORE,
    )
