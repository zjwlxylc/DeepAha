"""Immutable investigation receipts for existing P9-B candidates and human facts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260908_0040"
down_revision = "20260908_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_fact_preparations",
        sa.Column("preparation_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("investigation_tasks.task_id"), nullable=False
        ),
        sa.Column(
            "binding_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_bindings.binding_id"),
            nullable=False,
        ),
        sa.Column(
            "check_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_evidence_checks.check_id"),
            nullable=False,
        ),
        sa.Column("mapping_version", sa.String(128), nullable=False),
        sa.Column(
            "reviewer_id", sa.Uuid(), sa.ForeignKey("reviewer_accounts.reviewer_id"), nullable=False
        ),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "binding_id",
            "check_id",
            "mapping_version",
            name="uq_investigation_fact_preparation_version",
        ),
    )
    op.create_table(
        "investigation_fact_actions",
        sa.Column("action_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "preparation_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_fact_preparations.preparation_id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("entity_id", sa.String(256), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("extraction_candidates.candidate_id")),
        sa.Column(
            "decision_id", sa.Uuid(), sa.ForeignKey("fact_verification_decisions.decision_id")
        ),
        sa.Column(
            "fact_set_id",
            sa.Uuid(),
            sa.ForeignKey("versioned_verified_fact_sets.verified_fact_set_id"),
        ),
        sa.Column(
            "reviewer_id", sa.Uuid(), sa.ForeignKey("reviewer_accounts.reviewer_id"), nullable=False
        ),
        sa.Column("request_key_hash", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("request", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("decision_id", name="uq_investigation_fact_action_decision"),
        sa.UniqueConstraint(
            "preparation_id",
            "reviewer_id",
            "request_key_hash",
            name="uq_investigation_fact_action_request",
        ),
        sa.CheckConstraint(
            "(kind = 'DECISION' and candidate_id is not null "
            "and decision_id is not null and fact_set_id is null) or "
            "(kind = 'PROMOTION' and candidate_id is null "
            "and decision_id is null and fact_set_id is not null)",
            name="action_shape",
        ),
    )
    op.execute("""
    CREATE FUNCTION investigation_guard_fact_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE prep investigation_fact_preparations; binding investigation_bindings;
        item jsonb; candidate extraction_candidates; run extraction_runs; evidence jsonb;
        checked investigation_evidence_checks; check_reference jsonb;
    BEGIN
        IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'INVESTIGATION_FACT_RECEIPT_IMMUTABLE'; END IF;
        IF TG_TABLE_NAME = 'investigation_fact_preparations' THEN
            prep := NEW;
        ELSE
            SELECT * INTO STRICT prep FROM investigation_fact_preparations
            WHERE preparation_id = NEW.preparation_id;
        END IF;
        SELECT * INTO STRICT binding FROM investigation_bindings WHERE binding_id =
            prep.binding_id;
        PERFORM 1 FROM investigation_tasks WHERE task_id = binding.task_id FOR UPDATE;
        SELECT * INTO STRICT checked FROM investigation_evidence_checks
        WHERE check_id = prep.check_id;
        IF checked.task_id <> binding.task_id OR checked.delivery_hash <> binding.delivery_hash
        THEN RAISE EXCEPTION 'INVESTIGATION_FACT_CHECK_MISMATCH'; END IF;
        IF prep.task_id <> binding.task_id OR binding.binding_id IS DISTINCT FROM
            (SELECT binding_id FROM investigation_bindings WHERE task_id = binding.task_id ORDER
                BY sequence DESC LIMIT 1)
            OR NOT EXISTS (SELECT 1 FROM investigation_tasks WHERE task_id = binding.task_id
                AND status = 'APPROVED' AND delivery_hash = binding.delivery_hash)
            OR NOT EXISTS (SELECT 1 FROM opportunities WHERE opportunity_id =
                binding.opportunity_id
                AND current_version = binding.opportunity_version)
            OR NOT EXISTS (SELECT 1 FROM source_bundle_revisions WHERE source_bundle_revision_id =
                binding.source_bundle_revision_id AND status = 'FROZEN')
            OR NOT EXISTS (SELECT 1 FROM reviewer_accounts WHERE reviewer_id = NEW.reviewer_id
                AND active AND NOT synthetic AND roles ? 'VALIDATION_REVIEWER'
                AND allowed_purposes ? 'OPPORTUNITY_FACT_VALIDATION')
        THEN RAISE EXCEPTION 'INVESTIGATION_FACT_RECEIPT_TARGET_INVALID'; END IF;
        IF TG_TABLE_NAME = 'investigation_fact_preparations' THEN
            IF NEW.result_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.result), 'UTF8')), 'hex')
                OR jsonb_typeof(NEW.result->'rows') IS DISTINCT FROM 'array'
                OR jsonb_array_length(NEW.result->'rows') IS DISTINCT FROM
                    (SELECT jsonb_array_length(delivery->'facts') FROM investigation_tasks WHERE
                        task_id = binding.task_id)
                OR EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.result->'rows') r GROUP BY
                    r->>'source_index' HAVING count(*) > 1)
                OR EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.result->'rows') r WHERE
                    r->>'candidate_id' IS NOT NULL GROUP BY r->>'candidate_id' HAVING count(*) >
                    1)
            THEN RAISE EXCEPTION 'INVESTIGATION_FACT_PREPARATION_MISMATCH'; END IF;
            IF jsonb_typeof(NEW.result->'targets') IS DISTINCT FROM 'array'
                OR jsonb_array_length(NEW.result->'targets') <> 1 +
                    jsonb_array_length(binding.request->'positions')
                OR EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.result->'targets') t
                    GROUP BY t->>'entity_id' HAVING count(*) > 1)
            THEN RAISE EXCEPTION 'INVESTIGATION_FACT_TARGET_MISMATCH'; END IF;
            FOR item IN SELECT value FROM jsonb_array_elements(NEW.result->'targets') LOOP
                IF item->>'opportunity_id' IS DISTINCT FROM binding.opportunity_id::text
                    OR (item->>'opportunity_version')::integer IS DISTINCT FROM
                        binding.opportunity_version
                    OR NOT EXISTS (SELECT 1 FROM investigation_tasks t,
                        jsonb_array_elements(t.delivery->'evidence'->'entities') e
                        WHERE t.task_id = binding.task_id AND e->>'id' = item->>'entity_id'
                        AND e->>'name' = item->>'name' AND e->>'kind' = item->>'entity_kind'
                        AND ((e->>'kind' = 'announcement' AND item->>'target_scope' =
                            'OPPORTUNITY'
                            AND item->>'opportunity_unit_id' IS NULL
                            AND item->>'opportunity_unit_version_id' IS NULL)
                        OR (e->>'kind' = 'position' AND item->>'target_scope' = 'UNIT' AND EXISTS
                            (
                            SELECT 1 FROM jsonb_array_elements(binding.request->'positions') p
                            WHERE p->>'entity_id' = item->>'entity_id'
                            AND p->>'opportunity_unit_id' = item->>'opportunity_unit_id'
                            AND p->>'opportunity_unit_version_id' =
                                item->>'opportunity_unit_version_id'))))
                THEN RAISE EXCEPTION 'INVESTIGATION_FACT_TARGET_MISMATCH'; END IF;
            END LOOP;
            FOR item IN SELECT value || jsonb_build_object('_expected_index', ordinality - 1)
                FROM jsonb_array_elements(NEW.result->'rows') WITH ORDINALITY LOOP
                IF item->'source_index' IS DISTINCT FROM item->'_expected_index'
                    OR item->'original' IS DISTINCT FROM (SELECT
                        delivery->'facts'->((item->>'source_index')::integer)
                    FROM investigation_tasks WHERE task_id = binding.task_id)
                    OR item->>'entity_id' IS DISTINCT FROM item->'original'->>'entity_id'
                    OR item->>'original_field' IS DISTINCT FROM item->'original'->>'field'
                    OR item->>'original_status' IS DISTINCT FROM item->'original'->>'status'
                    OR item->'raw_value' IS DISTINCT FROM item->'original'->'value'
                THEN RAISE EXCEPTION 'INVESTIGATION_FACT_ORIGINAL_MISMATCH'; END IF;
                IF jsonb_array_length(item->'evidence') IS DISTINCT FROM
                    jsonb_array_length(item->'original'->'evidence')
                THEN RAISE EXCEPTION 'INVESTIGATION_FACT_QUOTE_MISMATCH'; END IF;
                FOR evidence IN SELECT value || jsonb_build_object('_index', ordinality - 1)
                    FROM jsonb_array_elements(item->'evidence') WITH ORDINALITY LOOP
                    IF evidence->'reference' IS DISTINCT FROM
                        item->'original'->'evidence'->((evidence->>'_index')::integer)
                    THEN RAISE EXCEPTION 'INVESTIGATION_FACT_QUOTE_MISMATCH'; END IF;
                    SELECT value INTO check_reference
                    FROM jsonb_array_elements(checked.payload->'references')
                    WHERE (value->>'fact_index')::integer = (item->>'source_index')::integer
                      AND (value->>'reference_index')::integer = (evidence->>'_index')::integer;
                    IF check_reference IS NULL
                       OR evidence->'check_reference' IS DISTINCT FROM check_reference
                       OR (check_reference->>'verdict' = 'PASS' AND (
                           jsonb_typeof(evidence->'binding') IS DISTINCT FROM 'object'
                           OR ((evidence->'binding') -
                               ARRAY['material_id','structural_locator','block_text'])
                               IS DISTINCT FROM check_reference->'persistent_binding'))
                       OR (check_reference->>'verdict' <> 'PASS'
                           AND evidence->'binding' IS DISTINCT FROM 'null'::jsonb)
                    THEN RAISE EXCEPTION 'INVESTIGATION_FACT_CHECK_MISMATCH'; END IF;
                    IF evidence->'binding' <> 'null'::jsonb AND NOT EXISTS (
                        SELECT 1 FROM document_blocks b JOIN investigation_materials m
                            ON m.raw_artifact_id = b.artifact_id
                        WHERE b.block_id::text = evidence->'binding'->>'block_id'
                          AND m.task_id = binding.task_id
                          AND m.material_id = evidence->'reference'->>'artifact_id'
                          AND m.material_id = evidence->'binding'->>'material_id'
                          AND b.structural_locator = evidence->'binding'->'structural_locator'
                          AND b.canonical_text_or_value = evidence->'binding'->>'block_text')
                    THEN RAISE EXCEPTION 'INVESTIGATION_FACT_CHECK_MISMATCH'; END IF;
                END LOOP;
                IF item->>'candidate_id' IS NULL THEN CONTINUE; END IF;
                SELECT * INTO STRICT candidate FROM extraction_candidates WHERE candidate_id::text
                    = item->>'candidate_id';
                SELECT * INTO STRICT run FROM extraction_runs WHERE extraction_run_id =
                    candidate.extraction_run_id;
                IF run.source_bundle_revision_id <> binding.source_bundle_revision_id
                    OR NOT EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.result->'targets') t
                        WHERE t->>'entity_id' = item->>'entity_id'
                        AND t->>'extraction_run_id' = candidate.extraction_run_id::text)
                    OR run.extractor_kind <> 'HYBRID' OR run.component_version <>
                        NEW.mapping_version
                    OR item->>'extraction_run_id' IS DISTINCT FROM
                        candidate.extraction_run_id::text
                    OR item->>'field_name' IS DISTINCT FROM candidate.field_name
                    OR item->>'target_scope' IS DISTINCT FROM candidate.target_scope
                    OR COALESCE(item->'raw_value', 'null'::jsonb) IS DISTINCT FROM
                        COALESCE(candidate.raw_value, 'null'::jsonb)
                    OR COALESCE(item->'normalized_value_candidate', 'null'::jsonb) IS DISTINCT
                        FROM COALESCE(candidate.normalized_value_candidate, 'null'::jsonb)
                    OR (item->>'abstained')::boolean IS DISTINCT FROM candidate.abstained
                    OR (item->>'ready_for_persistence')::boolean IS DISTINCT FROM true
                    OR EXISTS (SELECT 1 FROM jsonb_array_elements(item->'evidence') e
                        WHERE NOT EXISTS (SELECT 1 FROM extraction_candidate_evidence ce JOIN
                            document_blocks b ON b.block_id = ce.block_id
                            WHERE ce.candidate_id = candidate.candidate_id AND ce.block_id::text =
                                e->'binding'->>'block_id'
                            AND ce.evidence_ref_id::text = e->'binding'->>'evidence_ref_id'
                            AND b.document_id::text = e->'binding'->>'document_id'
                            AND b.evidence_binding_hash = e->'binding'->>'evidence_binding_hash'
                            ))
                    OR (SELECT count(DISTINCT e->'binding'->>'block_id') FROM
                        jsonb_array_elements(item->'evidence') e)
                       <> (SELECT count(*) FROM extraction_candidate_evidence WHERE candidate_id =
                           candidate.candidate_id)
                    OR candidate.opportunity_id <> binding.opportunity_id OR
                        candidate.opportunity_version <> binding.opportunity_version
                    OR (candidate.target_scope = 'OPPORTUNITY' AND NOT EXISTS
                        (SELECT 1 FROM investigation_tasks t,
                            jsonb_array_elements(t.delivery->'evidence'->'entities') e
                         WHERE t.task_id = binding.task_id AND e->>'id' = item->>'entity_id' AND
                             e->>'kind' = 'announcement'))
                    OR (candidate.target_scope = 'UNIT' AND NOT EXISTS
                        (SELECT 1 FROM jsonb_array_elements(binding.request->'positions') p
                         WHERE p->>'entity_id' = item->>'entity_id' AND p->>'opportunity_unit_id'
                             = candidate.opportunity_unit_id::text
                         AND p->>'opportunity_unit_version_id' =
                             candidate.opportunity_unit_version_id::text))
                THEN RAISE EXCEPTION 'INVESTIGATION_FACT_CANDIDATE_MISMATCH'; END IF;
            END LOOP;
        ELSE
            IF NEW.request_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.request), 'UTF8')), 'hex')
                OR NEW.request->>'preparation_id' IS DISTINCT FROM prep.preparation_id::text
                OR NEW.request->>'check_id' IS DISTINCT FROM prep.check_id::text
                OR NEW.request->>'binding_id' IS DISTINCT FROM binding.binding_id::text
                OR NEW.request->>'delivery_hash' IS DISTINCT FROM binding.delivery_hash
                OR NEW.request->>'kind' IS DISTINCT FROM NEW.kind
                OR length(btrim(COALESCE(NEW.request->>'reason', ''))) NOT BETWEEN 1 AND 2000
            THEN RAISE EXCEPTION 'INVESTIGATION_FACT_REQUEST_MISMATCH'; END IF;
            IF NEW.kind = 'DECISION' AND (NOT EXISTS
                (SELECT 1 FROM jsonb_array_elements(prep.result->'rows') r
                 WHERE r->>'candidate_id' = NEW.candidate_id::text AND r->>'entity_id' =
                     NEW.entity_id)
                OR NOT EXISTS (SELECT 1 FROM fact_verification_decisions WHERE decision_id =
                    NEW.decision_id
                    AND candidate_id = NEW.candidate_id AND verification_method = 'HUMAN'
                    AND NEW.request->>'candidate_id' = candidate_id::text
                    AND NEW.request->>'decision' = decision AND NEW.request->>'evidence_support' =
                        evidence_support_result
                    AND NEW.request->>'precedence_check' = precedence_check_result
                    AND verifier_identity = 'human:' || NEW.reviewer_id::text))
            THEN RAISE EXCEPTION 'INVESTIGATION_FACT_DECISION_MISMATCH'; END IF;
            IF NEW.kind = 'DECISION' AND EXISTS (SELECT 1 FROM fact_verification_decisions
                WHERE candidate_id = NEW.candidate_id AND decision_id <> NEW.decision_id
                    AND decision <> 'NEEDS_ADJUDICATION')
            THEN RAISE EXCEPTION 'INVESTIGATION_FACT_ALREADY_DECIDED'; END IF;
            IF NEW.kind = 'PROMOTION' AND NOT EXISTS
                (SELECT 1 FROM versioned_verified_fact_sets f,
                    jsonb_array_elements(prep.result->'targets') t
                 WHERE f.verified_fact_set_id = NEW.fact_set_id AND f.source_bundle_revision_id =
                     binding.source_bundle_revision_id
                 AND t->>'entity_id' = NEW.entity_id AND f.target_scope = t->>'target_scope'
                 AND f.opportunity_id = binding.opportunity_id AND f.opportunity_version =
                     binding.opportunity_version
                 AND f.opportunity_unit_version_id::text IS NOT DISTINCT FROM
                     t->>'opportunity_unit_version_id')
            THEN RAISE EXCEPTION 'INVESTIGATION_FACT_PROMOTION_MISMATCH'; END IF;
            IF NEW.kind = 'PROMOTION' AND (NEW.request->>'entity_id' IS DISTINCT FROM
                NEW.entity_id
                OR EXISTS (SELECT 1 FROM verified_facts f WHERE f.verified_fact_set_id =
                    NEW.fact_set_id
                    AND NOT EXISTS (SELECT 1 FROM investigation_fact_actions a
                        WHERE a.preparation_id = prep.preparation_id AND a.kind = 'DECISION'
                        AND a.entity_id = NEW.entity_id AND a.candidate_id = f.candidate_id
                        AND a.decision_id = f.verification_decision_id)))
            THEN RAISE EXCEPTION 'INVESTIGATION_FACT_PROMOTION_DECISIONS_MISMATCH'; END IF;
            IF NEW.kind = 'PROMOTION' AND (
                EXISTS (SELECT 1 FROM investigation_fact_actions WHERE preparation_id =
                    prep.preparation_id
                    AND entity_id = NEW.entity_id AND kind = 'PROMOTION')
                OR EXISTS (SELECT 1 FROM jsonb_array_elements(prep.result->'rows') r
                    WHERE r->>'entity_id' = NEW.entity_id AND r->>'candidate_id' IS NOT NULL
                    AND NOT EXISTS (SELECT 1 FROM investigation_fact_actions a
                        JOIN fact_verification_decisions d ON d.decision_id = a.decision_id
                        WHERE a.preparation_id = prep.preparation_id AND a.candidate_id::text =
                            r->>'candidate_id'
                            AND d.decision <> 'NEEDS_ADJUDICATION'))
                OR EXISTS (SELECT 1 FROM investigation_fact_actions a JOIN
                    fact_verification_decisions d
                    ON a.decision_id = d.decision_id WHERE a.preparation_id = prep.preparation_id
                    AND a.entity_id = NEW.entity_id AND d.decision IN ('APPROVE', 'UNKNOWN')
                    AND NOT EXISTS (SELECT 1 FROM verified_facts f WHERE f.verified_fact_set_id =
                        NEW.fact_set_id
                        AND f.candidate_id = a.candidate_id AND f.verification_decision_id =
                            d.decision_id)))
            THEN RAISE EXCEPTION 'INVESTIGATION_FACT_PROMOTION_INCOMPLETE'; END IF;
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER investigation_fact_preparation_guard BEFORE INSERT OR UPDATE OR DELETE
    ON investigation_fact_preparations FOR EACH ROW EXECUTE FUNCTION
        investigation_guard_fact_receipt();
    CREATE TRIGGER investigation_fact_action_guard BEFORE INSERT OR UPDATE OR DELETE
    ON investigation_fact_actions FOR EACH ROW EXECUTE FUNCTION
        investigation_guard_fact_receipt();
    """)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM investigation_fact_preparations)")
    ):
        raise RuntimeError("INVESTIGATION_FACT_HISTORY_DOWNGRADE_REFUSED")
    op.drop_table("investigation_fact_actions")
    op.drop_table("investigation_fact_preparations")
    op.execute("DROP FUNCTION investigation_guard_fact_receipt()")
