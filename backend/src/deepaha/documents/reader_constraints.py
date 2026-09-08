"""Current SQL envelopes; migrations contain their own immutable snapshots."""

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
