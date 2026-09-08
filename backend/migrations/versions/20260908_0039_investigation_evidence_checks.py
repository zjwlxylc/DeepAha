"""Append versioned mechanical receipts without rewriting investigation delivery."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260908_0039"
down_revision = "20260908_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_evidence_checks",
        sa.Column("check_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("investigation_tasks.task_id"), nullable=False
        ),
        sa.Column("delivery_hash", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "checked_by", sa.Uuid(), sa.ForeignKey("reviewer_accounts.reviewer_id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "input_hash", name="uq_investigation_evidence_check_input"),
        sa.CheckConstraint("uuid_extract_version(check_id) = 7", name="check_id_uuid7"),
        sa.CheckConstraint(
            "delivery_hash ~ '^[0-9a-f]{64}$' and input_hash ~ '^[0-9a-f]{64}$' "
            "and result_hash ~ '^[0-9a-f]{64}$'",
            name="hash_formats",
        ),
        sa.CheckConstraint("jsonb_typeof(payload) = 'object'", name="payload_object"),
    )
    op.execute("""
        CREATE FUNCTION investigation_evidence_check_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            frozen jsonb; f jsonb; ref jsonb; item jsonb; v jsonb; b jsonb;
            fi bigint; ri bigint; ordinal integer := 0;
            pass_count integer := 0; fail_count integer := 0; pending_count integer := 0;
            expected_verdict text;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'Investigation evidence checks are immutable';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM investigation_tasks t
                WHERE t.task_id = NEW.task_id AND t.delivery_hash = NEW.delivery_hash
                AND t.status IN ('PENDING_REVIEW','APPROVED'))
               OR NOT EXISTS (SELECT 1 FROM reviewer_accounts r WHERE r.reviewer_id = NEW.checked_by
                   AND r.active AND r.roles @> '["LOCAL_TEST_OPERATOR"]'::jsonb
                   AND r.allowed_purposes @> '["OPPORTUNITY_FACT_VALIDATION"]'::jsonb)
               OR (NEW.payload->'inputs'->>'delivery_hash') IS DISTINCT FROM NEW.delivery_hash
               OR (NEW.payload->>'scope') IS DISTINCT FROM 'MECHANICAL_EVIDENCE_ONLY'
               OR NEW.input_hash IS DISTINCT FROM encode(sha256(convert_to(
                   p9b_canonical_json(NEW.payload->'inputs'), 'UTF8')), 'hex')
               OR NEW.result_hash IS DISTINCT FROM encode(sha256(convert_to(
                   p9b_canonical_json(NEW.payload), 'UTF8')), 'hex') THEN
                RAISE EXCEPTION 'Invalid investigation evidence check';
            END IF;
            SELECT delivery INTO frozen FROM investigation_tasks WHERE task_id = NEW.task_id;
            IF jsonb_typeof(NEW.payload->'references') IS DISTINCT FROM 'array'
               OR jsonb_typeof(NEW.payload->'inputs'->'readers') IS DISTINCT FROM 'array'
               OR jsonb_typeof(NEW.payload->'inputs'->'materials') IS DISTINCT FROM 'array'
               OR jsonb_typeof(NEW.payload->'inputs'->'documents') IS DISTINCT FROM 'array'
               OR nullif(NEW.payload->'inputs'->>'check_version', '') IS NULL
               OR nullif(NEW.payload->'inputs'->>'verifier_version', '') IS NULL THEN
                RAISE EXCEPTION 'Invalid investigation evidence check shape';
            END IF;
            IF (NEW.payload->'inputs'->'materials') IS DISTINCT FROM (
                SELECT jsonb_agg(jsonb_build_object('material_id', m.material_id,
                    'raw_artifact_id', m.raw_artifact_id::text,
                    'sha256', m.metadata_snapshot->>'sha256')
                    ORDER BY m.raw_artifact_id, m.material_id)
                FROM investigation_materials m WHERE m.task_id = NEW.task_id
            ) THEN RAISE EXCEPTION 'Invalid investigation evidence check materials';
            END IF;
            FOR f, fi IN SELECT value, ordinality-1 FROM
                jsonb_array_elements(frozen->'facts') WITH ORDINALITY LOOP
                FOR ref, ri IN SELECT value, ordinality-1 FROM
                    jsonb_array_elements(f->'evidence') WITH ORDINALITY LOOP
                    item := NEW.payload->'references'->ordinal;
                    v := item->'verification'; b := item->'persistent_binding';
                    IF (item->'fact_index') IS DISTINCT FROM to_jsonb(fi)
                       OR (item->'reference_index') IS DISTINCT FROM to_jsonb(ri)
                       OR (item->'entity_id') IS DISTINCT FROM (f->'entity_id')
                       OR (item->'field') IS DISTINCT FROM (f->'field')
                       OR (item->'artifact_id') IS DISTINCT FROM (ref->'artifact_id')
                       OR (v->'artifact_id') IS DISTINCT FROM (ref->'artifact_id')
                       OR (v->'artifact_sha256') IS DISTINCT FROM (ref->'sha256')
                       OR (v->'quote') IS DISTINCT FROM (ref->'quote')
                       OR (v->'original_locator') IS DISTINCT FROM (ref->'locator') THEN
                        RAISE EXCEPTION 'Invalid investigation evidence check reference';
                    END IF;
                    IF (v->'verifier_version') IS DISTINCT FROM
                        (NEW.payload->'inputs'->'verifier_version') THEN
                        RAISE EXCEPTION 'Invalid investigation evidence check version';
                    END IF;
                    IF item->>'verdict' = 'PASS' THEN
                        IF v->>'verdict' IS DISTINCT FROM 'PASS'
                           OR v->>'content_support' IS DISTINCT FROM 'FOUND'
                           OR v->>'declared_locator' IS DISTINCT FROM 'VERIFIED'
                           OR v->>'binding' IS DISTINCT FROM 'BOUND'
                           OR jsonb_array_length(v->'matches') IS DISTINCT FROM 1
                           OR NOT EXISTS (
                               SELECT 1 FROM document_blocks db
                               JOIN evidence_refs er ON er.evidence_ref_id = db.evidence_ref_id
                               JOIN documents d ON d.document_id = db.document_id
                               JOIN parse_attempts pa ON pa.document_id = d.document_id
                               JOIN investigation_materials m ON m.raw_artifact_id = d.artifact_id
                               WHERE m.task_id = NEW.task_id AND m.material_id = ref->>'artifact_id'
                               AND db.block_id::text = b->>'block_id'
                               AND db.evidence_ref_id::text = b->>'evidence_ref_id'
                               AND db.evidence_binding_hash = b->>'evidence_binding_hash'
                               AND d.document_id::text = b->>'document_id'
                               AND d.document_parse_key = b->>'document_parse_key'
                               AND pa.parse_attempt_id::text = b->>'parse_attempt_id'
                               AND pa.document_parse_key = d.document_parse_key
                               AND pa.outcome = 'SUCCEEDED' AND er.locator_schema_version = '0.9.0'
                               AND db.structural_locator->'reader' = v->'reader'
                               AND db.structural_locator->'representation_sha256'
                                   = v->'representation_sha256'
                               AND db.structural_locator->'projection_id'
                                   = v->'matches'->0->'projection_id'
                               AND db.structural_locator->'projection_sha256'
                                   = v->'matches'->0->'projection_sha256'
                           ) THEN
                            RAISE EXCEPTION 'Invalid investigation evidence check binding';
                        END IF;
                        pass_count := pass_count + 1;
                    ELSIF item->>'verdict' = 'FAIL' AND v->>'verdict' = 'FAIL'
                        AND b = 'null'::jsonb THEN fail_count := fail_count + 1;
                    ELSIF item->>'verdict' = 'UNVERIFIED'
                        AND v->>'verdict' IN ('PASS','UNVERIFIED') AND b = 'null'::jsonb
                        THEN pending_count := pending_count + 1;
                    ELSE RAISE EXCEPTION 'Invalid investigation evidence check verdict';
                    END IF;
                    ordinal := ordinal + 1;
                END LOOP;
            END LOOP;
            expected_verdict := CASE WHEN fail_count > 0 THEN 'FAIL'
                WHEN pending_count > 0 OR ordinal = 0 THEN 'UNVERIFIED' ELSE 'PASS' END;
            IF ordinal <> jsonb_array_length(NEW.payload->'references')
               OR (NEW.payload->>'verdict') IS DISTINCT FROM expected_verdict
               OR (NEW.payload->'counts') IS DISTINCT FROM jsonb_build_object(
                   'PASS', pass_count, 'FAIL', fail_count, 'UNVERIFIED', pending_count) THEN
                RAISE EXCEPTION 'Invalid investigation evidence check counts';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER investigation_evidence_check_guard BEFORE INSERT OR UPDATE OR DELETE
        ON investigation_evidence_checks FOR EACH ROW
        EXECUTE FUNCTION investigation_evidence_check_guard();
    """)


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM investigation_evidence_checks)")):
        raise RuntimeError("Cannot discard investigation evidence check history")
    op.drop_table("investigation_evidence_checks")
    op.execute("DROP FUNCTION investigation_evidence_check_guard()")
