"""Add one generic Reader block/anchor envelope without rewriting legacy records."""

import sqlalchemy as sa
from alembic import op

revision = "20260908_0038"
down_revision = "20260907_0037"
branch_labels = None
depends_on = None

LEGACY_SCHEMA_FORM = (
    "(locator_schema_version = '0.1.0' and "
    "locator_kind in ('page', 'paragraph', 'css_selector', 'text_span', 'full_document') "
    "and locator_value is not null and locator_payload is null) or "
    "(locator_schema_version = '0.2.0' and "
    "locator_kind in ('html_selector', 'pdf_page_text', 'spreadsheet_range') "
    "and locator_value is null and locator_payload is not null) or "
    "(locator_schema_version = '0.8.0' and "
    "locator_kind in ('html_element_span', 'pdf_text_span', 'pdf_table_cell', "
    "'spreadsheet_cell', 'spreadsheet_range', 'docx_paragraph', 'docx_table_cell') "
    "and locator_value is null and locator_payload is not null)"
)

# Frozen SQL envelopes, independent of future application code.
READER_EVIDENCE_SHAPE = """
locator_schema_version <> '0.9.0' OR coalesce((
    locator_kind = 'reader_anchor' AND locator_value IS NULL AND
    jsonb_typeof(locator_payload) = 'object' AND locator_payload ?&
    ARRAY['schema_version','kind','block_id','document_parse_key','block_type',
          'structural_locator','value_sha256'] AND
    locator_payload - ARRAY['schema_version','kind','block_id','document_parse_key',
          'block_type','structural_locator','value_sha256'] = '{}'::jsonb AND
    locator_payload->>'schema_version' = '0.9.0' AND
    locator_payload->>'kind' = 'reader_anchor' AND
    locator_payload->>'block_type' = 'READER_TEXT_SPAN' AND
    jsonb_typeof(locator_payload->'block_id') = 'string' AND
    locator_payload->>'block_id' ~
      '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' AND
    jsonb_typeof(locator_payload->'document_parse_key') = 'string' AND
    locator_payload->>'document_parse_key' ~ '^[0-9a-f]{64}$' AND
    jsonb_typeof(locator_payload->'value_sha256') = 'string' AND
    locator_payload->>'value_sha256' ~ '^[0-9a-f]{64}$' AND
    locator_payload->>'value_sha256' = quote_sha256 AND
    evidence_reader_anchor_valid(locator_payload->'structural_locator')
), false)
"""

READER_BLOCK_SHAPE = """
block_type <> 'READER_TEXT_SPAN' OR coalesce((
    evidence_reader_anchor_valid(structural_locator) AND
    parent_block_id IS NULL AND parser_name = 'deepaha-evidence-reader' AND
    parse_contract_version = 'reader-document-block-contract-v1' AND
    structural_locator->>'text_end' = char_length(canonical_text_or_value)::text AND
    structural_locator->>'projection_sha256' =
        encode(sha256(convert_to(canonical_text_or_value, 'UTF8')), 'hex')
), false)
"""


ANCHOR_VALID = """
CREATE FUNCTION evidence_reader_anchor_valid(payload jsonb)
RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
SELECT coalesce((
  jsonb_typeof(payload) = 'object' AND payload ?&
    ARRAY['kind','anchor_schema','reader','artifact_sha256','representation_sha256',
          'projection_id','projection_sha256','text_start','text_end'] AND
  payload - ARRAY['kind','anchor_schema','reader','artifact_sha256','representation_sha256',
          'projection_id','projection_sha256','text_start','text_end'] = '{}'::jsonb AND
  payload->>'kind' = 'reader_anchor' AND payload->>'anchor_schema' = 'reader-projection/1' AND
  jsonb_typeof(payload->'reader') = 'object' AND payload->'reader' ?&
    ARRAY['name','version','parse_contract','comparison_version'] AND
  (payload->'reader') - ARRAY['name','version','parse_contract','comparison_version']
    = '{}'::jsonb AND
  jsonb_typeof(payload->'reader'->'name') = 'string' AND
    length(payload->'reader'->>'name') BETWEEN 1 AND 1024 AND
  jsonb_typeof(payload->'reader'->'version') = 'string' AND
    length(payload->'reader'->>'version') BETWEEN 1 AND 1024 AND
  jsonb_typeof(payload->'reader'->'parse_contract') = 'string' AND
    length(payload->'reader'->>'parse_contract') BETWEEN 1 AND 1024 AND
  jsonb_typeof(payload->'reader'->'comparison_version') = 'string' AND
    length(payload->'reader'->>'comparison_version') BETWEEN 1 AND 1024 AND
  jsonb_typeof(payload->'artifact_sha256') = 'string' AND
    payload->>'artifact_sha256' ~ '^[0-9a-f]{64}$' AND
  jsonb_typeof(payload->'representation_sha256') = 'string' AND
    payload->>'representation_sha256' ~ '^[0-9a-f]{64}$' AND
  jsonb_typeof(payload->'projection_sha256') = 'string' AND
    payload->>'projection_sha256' ~ '^[0-9a-f]{64}$' AND
  jsonb_typeof(payload->'projection_id') = 'string' AND
    length(payload->>'projection_id') BETWEEN 1 AND 16384 AND
  jsonb_typeof(payload->'text_start') = 'number' AND payload->>'text_start' = '0' AND
  jsonb_typeof(payload->'text_end') = 'number' AND payload->>'text_end' ~ '^[1-9][0-9]*$'
), false)
$$
"""

GUARD = """
            /* READER_ANCHOR_START */
            IF NEW.block_type = 'READER_TEXT_SPAN' THEN
                IF evidence.artifact_id IS DISTINCT FROM NEW.artifact_id OR
                   evidence.locator_payload->>'value_sha256' IS DISTINCT FROM
                     NEW.structural_locator->>'projection_sha256' OR
                   NEW.structural_locator->>'artifact_sha256' IS DISTINCT FROM
                     (SELECT content_sha256 FROM raw_artifacts
                      WHERE artifact_id = NEW.artifact_id) OR
                   NEW.parser_version IS DISTINCT FROM encode(sha256(convert_to(
                     p9b_canonical_json(NEW.structural_locator->'reader'), 'UTF8')), 'hex') OR
                   NEW.block_hash IS DISTINCT FROM p9b_hash_json(
                     'document_block_hash', jsonb_build_object(
                     'block_type', NEW.block_type,
                     'canonical_text_or_value', NEW.canonical_text_or_value,
                     'document_parse_key', NEW.document_parse_key, 'ordinal', NEW.ordinal,
                     'parent_ordinal', NULL, 'structural_locator', NEW.structural_locator)) OR
                   NEW.evidence_binding_hash IS DISTINCT FROM p9b_hash_json(
                     'evidence_binding_hash', jsonb_build_object(
                     'block_hash', NEW.block_hash, 'block_id', NEW.block_id::text,
                     'document_parse_key', NEW.document_parse_key,
                     'structural_locator', NEW.structural_locator))
                THEN RAISE EXCEPTION 'Reader block provenance or hash mismatch'; END IF;
            END IF;
            /* READER_ANCHOR_END */
"""


def _kinds(*, upgrade: bool) -> None:
    blocks = [
        "HTML_SECTION",
        "HTML_ELEMENT",
        "PDF_TEXT_SPAN",
        "PDF_TABLE_CELL",
        "SPREADSHEET_CELL",
        "SPREADSHEET_RANGE",
        "DOCX_PARAGRAPH",
        "DOCX_TABLE_CELL",
        "OCR_TEXT_SPAN",
    ]
    locators = [
        "page",
        "paragraph",
        "css_selector",
        "text_span",
        "full_document",
        "html_selector",
        "pdf_page_text",
        "spreadsheet_range",
        "html_element_span",
        "pdf_text_span",
        "pdf_table_cell",
        "spreadsheet_cell",
        "docx_paragraph",
        "docx_table_cell",
    ]
    if upgrade:
        blocks.append("READER_TEXT_SPAN")
        locators.append("reader_anchor")
    for table, column, values, name in (
        ("document_blocks", "block_type", blocks, "ck_document_blocks_block_type_values"),
        ("evidence_refs", "locator_kind", locators, "ck_evidence_refs_locator_kind_values"),
    ):
        op.drop_constraint(op.f(name), table, type_="check")
        literals = ", ".join(repr(value) for value in values)
        op.create_check_constraint(op.f(name), table, f"{column} in ({literals})")


def _guard(*, upgrade: bool) -> None:
    definition = op.get_bind().scalar(
        sa.text("select pg_get_functiondef('p9b_document_blocks_guard()'::regprocedure)")
    )
    if not isinstance(definition, str):
        raise RuntimeError("DocumentBlock guard is missing")
    legacy = "evidence.locator_schema_version <> '0.8.0'"
    extended = (
        "evidence.locator_schema_version <> (CASE WHEN NEW.block_type = 'READER_TEXT_SPAN' "
        "THEN '0.9.0' ELSE '0.8.0' END)"
    )
    case = "WHEN 'READER_TEXT_SPAN' THEN 'reader_anchor'\n                "
    if upgrade:
        if legacy not in definition or "READER_ANCHOR_START" in definition:
            raise RuntimeError("Unsupported DocumentBlock guard definition")
        definition = definition.replace("WHEN 'HTML_SECTION'", case + "WHEN 'HTML_SECTION'")
        definition = definition.replace(legacy, extended).replace(
            "RETURN NEW;", GUARD + "RETURN NEW;"
        )
    else:
        definition = definition.replace(case, "").replace(extended, legacy)
        start = definition.index("\n            /* READER_ANCHOR_START */")
        end = definition.index("/* READER_ANCHOR_END */") + len("/* READER_ANCHOR_END */\n")
        definition = definition[:start] + definition[end:]
    op.get_bind().exec_driver_sql(definition.replace("%", "%%"))


def upgrade() -> None:
    op.execute(ANCHOR_VALID)
    op.execute("""
        CREATE FUNCTION evidence_reader_ref_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.locator_schema_version = '0.9.0' OR
               (TG_OP = 'UPDATE' AND NEW.locator_schema_version = '0.9.0') THEN
                RAISE EXCEPTION 'Reader EvidenceRefs are immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute(
        "CREATE TRIGGER evidence_reader_ref_immutable BEFORE UPDATE OR DELETE ON "
        "evidence_refs FOR EACH ROW EXECUTE FUNCTION evidence_reader_ref_immutable()"
    )
    _kinds(upgrade=True)
    op.drop_constraint(op.f("ck_evidence_refs_locator_schema_form"), "evidence_refs", type_="check")
    op.create_check_constraint(
        op.f("ck_evidence_refs_locator_schema_form"),
        "evidence_refs",
        f"({LEGACY_SCHEMA_FORM}) OR (locator_schema_version = '0.9.0' AND "
        "locator_kind = 'reader_anchor' AND locator_value IS NULL AND locator_payload IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_evidence_refs_reader_evidence_shape"), "evidence_refs", READER_EVIDENCE_SHAPE
    )
    op.create_check_constraint(
        op.f("ck_document_blocks_reader_block_shape"), "document_blocks", READER_BLOCK_SHAPE
    )
    _guard(upgrade=True)


def downgrade() -> None:
    count = op.get_bind().scalar(
        sa.text("select count(*) from evidence_refs where locator_schema_version = '0.9.0'")
    )
    if count:
        raise RuntimeError("Cannot remove Reader anchors with evidence history")
    op.execute("DROP TRIGGER evidence_reader_ref_immutable ON evidence_refs")
    op.execute("DROP FUNCTION evidence_reader_ref_immutable()")
    _guard(upgrade=False)
    op.drop_constraint(
        op.f("ck_document_blocks_reader_block_shape"), "document_blocks", type_="check"
    )
    op.drop_constraint(
        op.f("ck_evidence_refs_reader_evidence_shape"), "evidence_refs", type_="check"
    )
    _kinds(upgrade=False)
    op.drop_constraint(op.f("ck_evidence_refs_locator_schema_form"), "evidence_refs", type_="check")
    op.create_check_constraint(
        op.f("ck_evidence_refs_locator_schema_form"), "evidence_refs", LEGACY_SCHEMA_FORM
    )
    op.execute("DROP FUNCTION evidence_reader_anchor_valid(jsonb)")
