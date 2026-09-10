"""Independent group fact receipts; preserve the old announcement/position bridge."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260910_0047"
down_revision = "20260910_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_group_fact_preparations",
        sa.Column("preparation_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "group_binding_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_group_bindings.group_binding_id"),
            nullable=False,
        ),
        sa.Column(
            "check_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_evidence_checks.check_id"),
            nullable=False,
        ),
        sa.Column("mapping_version", sa.String(128), nullable=False),
        sa.Column("result", JSONB(), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column(
            "reviewer_id", sa.Uuid(), sa.ForeignKey("reviewer_accounts.reviewer_id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "group_binding_id", "check_id", "mapping_version", name="uq_group_fact_preparation"
        ),
    )
    op.create_table(
        "investigation_group_fact_actions",
        sa.Column("action_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "preparation_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_group_fact_preparations.preparation_id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
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
        sa.Column("request", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "preparation_id", "reviewer_id", "request_key_hash", name="uq_group_fact_request"
        ),
        sa.UniqueConstraint("decision_id", name="uq_group_fact_decision"),
        sa.CheckConstraint(
            "(kind = 'DECISION' and candidate_id is not null "
            "and decision_id is not null and fact_set_id is null) or "
            "(kind = 'PROMOTION' and candidate_id is null "
            "and decision_id is null and fact_set_id is not null)",
            name="action_shape",
        ),
    )
    op.execute("""
    CREATE FUNCTION investigation_group_fact_materialization_valid(
        prep_id uuid, set_id uuid, as_of timestamptz
    ) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
    DECLARE p investigation_group_fact_preparations; g investigation_group_bindings;
        b investigation_bindings; row jsonb; candidate extraction_candidates;
        run extraction_runs; f verified_facts; fs versioned_verified_fact_sets;
        d fact_verification_decisions; refs jsonb; actual jsonb; fingerprint text;
    BEGIN
        SELECT * INTO p FROM investigation_group_fact_preparations WHERE preparation_id=prep_id;
        IF NOT FOUND OR p.created_at > as_of THEN RETURN false; END IF;
        SELECT * INTO STRICT g FROM investigation_group_bindings
            WHERE group_binding_id=p.group_binding_id;
        SELECT * INTO STRICT b FROM investigation_bindings WHERE binding_id=g.binding_id;
        IF (p.result->>'extraction_run_id' IS NULL) IS DISTINCT FROM
            (NOT EXISTS (SELECT 1 FROM jsonb_array_elements(p.result->'rows') x
                WHERE x->>'candidate_id' IS NOT NULL)) THEN RETURN false; END IF;
        FOR row IN SELECT value FROM jsonb_array_elements(p.result->'rows') LOOP
            IF row->>'candidate_id' IS NULL THEN CONTINUE; END IF;
            SELECT * INTO candidate FROM extraction_candidates
                WHERE candidate_id::text=row->>'candidate_id';
            IF NOT FOUND THEN RETURN false; END IF;
            SELECT * INTO run FROM extraction_runs
                WHERE extraction_run_id=candidate.extraction_run_id;
            IF NOT FOUND OR run.extraction_run_id::text IS DISTINCT FROM
                p.result->>'extraction_run_id' OR candidate.target_scope <> 'UNIT'
                OR candidate.opportunity_unit_id IS DISTINCT FROM g.unit_id
                OR candidate.opportunity_unit_version_id IS DISTINCT FROM g.unit_version_id
                OR candidate.opportunity_id <> b.opportunity_id
                OR candidate.opportunity_version <> b.opportunity_version
                OR run.source_bundle_revision_id <> b.source_bundle_revision_id
                OR run.component_version <> p.mapping_version
                OR run.task_spec_version <> p.mapping_version
                OR run.unit_segmentation_version <> 'group-binding:' || g.group_binding_id::text
                OR run.producer_identity <> 'component:' || p.mapping_version || ':wma:' ||
                    g.task_id::text
                OR run.started_at > run.completed_at OR run.completed_at > p.created_at
                OR candidate.created_at < run.completed_at OR candidate.created_at > p.created_at
                OR candidate.field_name IS DISTINCT FROM row->>'field_name'
                OR COALESCE(candidate.raw_value,'null'::jsonb) IS DISTINCT FROM row->'raw_value'
                OR COALESCE(candidate.normalized_value_candidate,'null'::jsonb) IS DISTINCT FROM
                    row->'normalized_value_candidate'
                OR candidate.abstained IS DISTINCT FROM (row->>'abstained')::boolean
                OR candidate.candidate_reason_code IS DISTINCT FROM row->>'candidate_reason_code'
                OR candidate.confidence IS NOT NULL THEN RETURN false; END IF;
            SELECT COALESCE(jsonb_agg(x ORDER BY x->>'block_id'),'[]') INTO refs FROM (
                SELECT DISTINCT jsonb_build_object('block_id',value->'binding'->>'block_id',
                    'evidence_ref_id',value->'binding'->>'evidence_ref_id') x
                FROM jsonb_array_elements(row->'evidence')) a;
            SELECT COALESCE(jsonb_agg(jsonb_build_object('block_id',block_id::text,
                'evidence_ref_id',evidence_ref_id::text) ORDER BY block_id::text),'[]') INTO actual
                FROM extraction_candidate_evidence WHERE candidate_id=candidate.candidate_id;
            IF refs IS DISTINCT FROM actual THEN RETURN false; END IF;
        END LOOP;
        IF set_id IS NULL THEN RETURN true; END IF;
        SELECT * INTO fs FROM versioned_verified_fact_sets WHERE verified_fact_set_id=set_id;
        IF NOT FOUND OR fs.target_scope <> 'UNIT'
            OR fs.opportunity_unit_id IS DISTINCT FROM g.unit_id
            OR fs.opportunity_unit_version_id IS DISTINCT FROM g.unit_version_id
            OR fs.opportunity_id <> b.opportunity_id
            OR fs.opportunity_version <> b.opportunity_version
            OR fs.source_bundle_revision_id <> b.source_bundle_revision_id
            OR fs.created_at < p.created_at OR fs.created_at > as_of OR fs.updated_at > as_of
            OR fs.reference_dataset_versions <>
                jsonb_build_object('group_fact_bridge',p.mapping_version)
            THEN RETURN false; END IF;
        IF EXISTS (SELECT 1 FROM jsonb_array_elements(p.result->'rows') r
            WHERE r->>'candidate_id' IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM investigation_group_fact_actions a
                JOIN fact_verification_decisions dec
                ON dec.decision_id=a.decision_id WHERE a.preparation_id=prep_id
                    AND a.candidate_id::text=r->>'candidate_id'
                    AND dec.decision <> 'NEEDS_ADJUDICATION'
                    AND a.created_at <= fs.created_at AND dec.decided_at <= fs.created_at))
            OR EXISTS (SELECT 1 FROM investigation_group_fact_actions a
                JOIN fact_verification_decisions dec ON dec.decision_id=a.decision_id
                WHERE a.preparation_id=prep_id AND dec.decision IN ('APPROVE','UNKNOWN')
                AND NOT EXISTS (SELECT 1 FROM verified_facts saved
                    WHERE saved.verified_fact_set_id=set_id
                    AND saved.candidate_id=a.candidate_id
                    AND saved.verification_decision_id=dec.decision_id))
            THEN RETURN false; END IF;
        FOR f IN SELECT * FROM verified_facts WHERE verified_fact_set_id=set_id LOOP
            SELECT * INTO STRICT candidate FROM extraction_candidates
                WHERE candidate_id=f.candidate_id;
            SELECT * INTO STRICT d FROM fact_verification_decisions
                WHERE decision_id=f.verification_decision_id;
            IF NOT EXISTS (SELECT 1 FROM investigation_group_fact_actions a
                WHERE a.preparation_id=prep_id AND a.candidate_id=f.candidate_id
                    AND a.decision_id=d.decision_id AND a.created_at <= fs.created_at)
                OR f.field_name <> candidate.field_name
                OR f.raw_value IS DISTINCT FROM candidate.raw_value
                OR f.normalized_value IS DISTINCT FROM candidate.normalized_value_candidate
                OR f.fact_state <> (CASE WHEN candidate.abstained THEN 'UNKNOWN' ELSE 'KNOWN' END)
                OR d.decision <> (CASE WHEN candidate.abstained THEN 'UNKNOWN' ELSE 'APPROVE' END)
                OR f.created_at <> fs.created_at OR d.decided_at > fs.created_at
                THEN RETURN false; END IF;
            SELECT COALESCE(jsonb_agg(jsonb_build_object('block_id',block_id::text,
                'evidence_ref_id',evidence_ref_id::text) ORDER BY block_id::text),'[]') INTO refs
                FROM extraction_candidate_evidence WHERE candidate_id=f.candidate_id;
            SELECT COALESCE(jsonb_agg(jsonb_build_object('block_id',block_id::text,
                'evidence_ref_id',evidence_ref_id::text) ORDER BY block_id::text),'[]') INTO actual
                FROM verified_fact_evidence WHERE verified_fact_id=f.verified_fact_id;
            fingerprint := encode(sha256(convert_to(
                'deepaha:p9b:fact_dependency_fingerprint:p9b-canonical-json-sha256-v1','UTF8') ||
                decode('00','hex') || convert_to(p9b_canonical_json(jsonb_build_object(
                    'candidate_id',candidate.candidate_id::text,'decision_id',d.decision_id::text,
                    'evidence',refs)),'UTF8')),'hex');
            IF actual IS DISTINCT FROM refs OR f.dependency_fingerprint <> fingerprint
                THEN RETURN false; END IF;
        END LOOP;
        RETURN EXISTS (SELECT 1 FROM verified_facts WHERE verified_fact_set_id=set_id);
    END $$;
    CREATE FUNCTION investigation_guard_group_fact() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE p investigation_group_fact_preparations; g investigation_group_bindings;
        b investigation_bindings; t investigation_tasks; c investigation_evidence_checks;
        u opportunity_units; v opportunity_unit_versions; r jsonb; e jsonb; checked jsonb;
        candidate extraction_candidates; run extraction_runs; expected jsonb;
    BEGIN
        IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'GROUP_FACT_IMMUTABLE'; END IF;
        IF TG_TABLE_NAME='investigation_group_fact_preparations' THEN p:=NEW;
        ELSE SELECT * INTO STRICT p FROM investigation_group_fact_preparations
            WHERE preparation_id=NEW.preparation_id; END IF;
        SELECT * INTO STRICT g FROM investigation_group_bindings WHERE
            group_binding_id=p.group_binding_id;
        SELECT * INTO STRICT t FROM investigation_tasks WHERE task_id=g.task_id FOR UPDATE;
        SELECT * INTO STRICT b FROM investigation_bindings WHERE binding_id=g.binding_id;
        SELECT * INTO STRICT c FROM investigation_evidence_checks WHERE check_id=p.check_id;
        SELECT * INTO STRICT u FROM opportunity_units WHERE opportunity_unit_id=g.unit_id FOR
            UPDATE;
        SELECT * INTO STRICT v FROM opportunity_unit_versions WHERE
            opportunity_unit_version_id=g.unit_version_id;
        IF t.status <> 'APPROVED' OR t.delivery_hash <> b.delivery_hash
            OR b.binding_id IS DISTINCT FROM (SELECT binding_id FROM investigation_bindings
                WHERE task_id=t.task_id ORDER BY sequence DESC LIMIT 1)
            OR c.task_id <> t.task_id OR c.delivery_hash <> t.delivery_hash
            OR c.result_hash <> encode(sha256(convert_to(p9b_canonical_json(c.payload),'UTF8')),
            'hex')
            OR p.mapping_version <> 'group-fact-bridge/1.0.0'
            OR u.unit_kind <> 'GROUP' OR u.lifecycle_status <> 'ACTIVE'
            OR u.current_version_id IS DISTINCT FROM g.unit_version_id OR v.status <> 'ACTIVE'
            OR v.opportunity_unit_id <> g.unit_id OR v.opportunity_id <> b.opportunity_id
            OR v.opportunity_version <> b.opportunity_version
            OR v.source_bundle_revision_id <> b.source_bundle_revision_id
            OR NOT EXISTS (SELECT 1 FROM opportunities WHERE opportunity_id=b.opportunity_id AND
            current_version=b.opportunity_version)
            OR NOT EXISTS (SELECT 1 FROM source_bundle_revisions WHERE
            source_bundle_revision_id=b.source_bundle_revision_id AND status='FROZEN')
            OR NOT EXISTS (SELECT 1 FROM reviewer_accounts WHERE reviewer_id=NEW.reviewer_id
                AND active AND NOT synthetic AND roles ? 'VALIDATION_REVIEWER'
                AND allowed_purposes ? 'OPPORTUNITY_FACT_VALIDATION')
        THEN RAISE EXCEPTION 'GROUP_FACT_TARGET_INVALID'; END IF;
        IF TG_TABLE_NAME='investigation_group_fact_preparations' THEN
            IF p.result_hash IS DISTINCT FROM
            encode(sha256(convert_to(p9b_canonical_json(p.result),'UTF8')),'hex')
                OR p.result->>'contract_version' IS DISTINCT FROM p.mapping_version
                OR p.result->>'scope' IS DISTINCT FROM 'GROUP_FACT_REVIEW_ONLY'
                OR p.result->>'check_id' IS DISTINCT FROM p.check_id::text
                OR p.result->>'check_hash' IS DISTINCT FROM c.result_hash
                OR p.result->'group_source'->>'group_binding_id' IS DISTINCT FROM
            g.group_binding_id::text
                OR p.result->'group_source'->'source' IS DISTINCT FROM g.source
                OR p.result->'group_source'->>'source_hash' IS DISTINCT FROM g.source_hash
                OR p.result->'group_source'->'group_identity'->>'unit_kind' IS DISTINCT FROM 'GROUP'
                OR p.result->'group_source'->'group_identity'->>'unit_id' IS DISTINCT FROM
            g.unit_id::text
                OR p.result->'group_source'->'group_identity'->>'unit_version_id' IS DISTINCT
            FROM g.unit_version_id::text
                OR p.result->'source_row_count' IS DISTINCT FROM
            to_jsonb(jsonb_array_length(t.delivery->'facts'))
            THEN RAISE EXCEPTION 'GROUP_FACT_SOURCE_INVALID'; END IF;
            SELECT COALESCE(jsonb_agg(ordinality-1 ORDER BY ordinality),'[]') INTO expected
                FROM jsonb_array_elements(t.delivery->'facts') WITH ORDINALITY
                WHERE value->>'entity_id'=g.source_entity_id;
            IF (SELECT COALESCE(jsonb_agg(value->'source_index' ORDER BY ordinality),'[]')
                FROM jsonb_array_elements(p.result->'rows') WITH ORDINALITY) IS DISTINCT FROM
            expected
            THEN RAISE EXCEPTION 'GROUP_FACT_DENOMINATOR_INVALID'; END IF;
            SELECT COALESCE(jsonb_agg(jsonb_build_object('source_index',ordinality-1,
                'entity_id',value->>'entity_id','source_hash',
            encode(sha256(convert_to(p9b_canonical_json(value),'UTF8')),'hex'),
                'reason','DIFFERENT_ENTITY_SCOPE') ORDER BY ordinality),'[]') INTO expected
                FROM jsonb_array_elements(t.delivery->'facts') WITH ORDINALITY
                WHERE value->>'entity_id' <> g.source_entity_id;
            IF p.result->'excluded_rows' IS DISTINCT FROM expected
            THEN RAISE EXCEPTION 'GROUP_FACT_DENOMINATOR_INVALID'; END IF;
            IF EXISTS (SELECT 1 FROM jsonb_array_elements(p.result->'rows') row
                WHERE row->>'candidate_id' IS NOT NULL GROUP BY row->>'candidate_id' HAVING
            count(*)>1)
            THEN RAISE EXCEPTION 'GROUP_FACT_CANDIDATE_INVALID'; END IF;
            FOR r IN SELECT value FROM jsonb_array_elements(p.result->'rows') LOOP
                IF r->'original' IS DISTINCT FROM t.delivery->'facts'->((r->>'source_index')::int)
                    OR r->>'entity_id' IS DISTINCT FROM g.source_entity_id
                    OR r->>'original_field' IS DISTINCT FROM r->'original'->>'field'
                    OR r->>'original_status' IS DISTINCT FROM r->'original'->>'status'
                    OR r->'raw_value' IS DISTINCT FROM r->'original'->'value'
                    OR r->>'mapping_version' IS DISTINCT FROM p.mapping_version
                    OR r->>'target_scope' IS DISTINCT FROM 'UNIT'
                    OR jsonb_array_length(r->'evidence') IS DISTINCT FROM
            jsonb_array_length(r->'original'->'evidence')
                THEN RAISE EXCEPTION 'GROUP_FACT_ORIGINAL_INVALID'; END IF;
                FOR e IN SELECT value || jsonb_build_object('_index',ordinality-1)
                    FROM jsonb_array_elements(r->'evidence') WITH ORDINALITY LOOP
                    SELECT value INTO checked FROM jsonb_array_elements(c.payload->'references')
                        WHERE value->'fact_index'=r->'source_index' AND
            value->'reference_index'=e->'_index';
                    IF checked IS NULL OR e->'check_reference' IS DISTINCT FROM checked
                        OR e->'reference' IS DISTINCT FROM
            r->'original'->'evidence'->((e->>'_index')::int)
                        OR (checked->>'verdict' <> 'PASS' AND e->'binding' IS DISTINCT FROM
            'null'::jsonb)
                        OR (checked->>'verdict'='PASS' AND ((e->'binding') - ARRAY['material_id',
            'structural_locator','block_text']) IS DISTINCT FROM checked->'persistent_binding')
                    THEN RAISE EXCEPTION 'GROUP_FACT_EVIDENCE_INVALID'; END IF;
                    IF e->'binding' <> 'null'::jsonb AND NOT EXISTS (
                        SELECT 1 FROM document_blocks block JOIN investigation_materials m ON
            m.raw_artifact_id=block.artifact_id
                        WHERE block.block_id::text=e->'binding'->>'block_id' AND m.task_id=t.task_id
                        AND m.material_id=e->'reference'->>'artifact_id' AND
            m.material_id=e->'binding'->>'material_id'
                        AND block.structural_locator=e->'binding'->'structural_locator' AND
            block.canonical_text_or_value=e->'binding'->>'block_text')
                    THEN RAISE EXCEPTION 'GROUP_FACT_EVIDENCE_INVALID'; END IF;
                END LOOP;
                IF (r->>'ready_for_persistence')::boolean IS DISTINCT FROM (r->>'candidate_id'
            IS NOT NULL)
                THEN RAISE EXCEPTION 'GROUP_FACT_CANDIDATE_INVALID'; END IF;
                IF r->>'candidate_id' IS NULL THEN CONTINUE; END IF;
                SELECT * INTO STRICT candidate FROM extraction_candidates WHERE
            candidate_id::text=r->>'candidate_id';
                SELECT * INTO STRICT run FROM extraction_runs WHERE
            extraction_run_id=candidate.extraction_run_id;
                IF candidate.target_scope <> 'UNIT' OR candidate.opportunity_unit_id <> g.unit_id
                    OR candidate.opportunity_unit_version_id <> g.unit_version_id
                    OR candidate.opportunity_id <> b.opportunity_id OR
            candidate.opportunity_version <> b.opportunity_version
                    OR run.extraction_run_id::text IS DISTINCT FROM p.result->>'extraction_run_id'
                    OR run.source_bundle_revision_id <> b.source_bundle_revision_id
                    OR run.component_version <> p.mapping_version OR run.task_spec_version <>
            p.mapping_version
                    OR run.unit_segmentation_version <> 'group-binding:' || g.group_binding_id::text
                    OR candidate.field_name IS DISTINCT FROM r->>'field_name'
                    OR COALESCE(candidate.raw_value,'null'::jsonb) IS DISTINCT FROM r->'raw_value'
                    OR COALESCE(candidate.normalized_value_candidate,'null'::jsonb) IS DISTINCT
            FROM r->'normalized_value_candidate'
                    OR candidate.abstained IS DISTINCT FROM (r->>'abstained')::boolean
                    OR candidate.created_at > p.created_at OR run.completed_at > p.created_at
                    OR r->>'original_status'='UNPROCESSED' OR jsonb_array_length(r->'evidence')=0
                    OR EXISTS (SELECT 1 FROM jsonb_array_elements(r->'evidence') x WHERE
                        x->'check_reference'->>'verdict' <> 'PASS' OR NOT EXISTS (
                            SELECT 1 FROM extraction_candidate_evidence ce WHERE
            ce.candidate_id=candidate.candidate_id
                            AND ce.block_id::text=x->'binding'->>'block_id' AND
            ce.evidence_ref_id::text=x->'binding'->>'evidence_ref_id'))
                    OR (SELECT count(DISTINCT x->'binding'->>'block_id') FROM
            jsonb_array_elements(r->'evidence') x)
                       <> (SELECT count(*) FROM extraction_candidate_evidence ce WHERE
            ce.candidate_id=candidate.candidate_id)
                THEN RAISE EXCEPTION 'GROUP_FACT_CANDIDATE_INVALID'; END IF;
            END LOOP;
        ELSE
            IF NOT investigation_group_fact_materialization_valid(
                p.preparation_id, NEW.fact_set_id, NEW.created_at)
            THEN RAISE EXCEPTION 'GROUP_FACT_MATERIALIZATION_INVALID'; END IF;
            IF NEW.request_hash IS DISTINCT FROM
            encode(sha256(convert_to(p9b_canonical_json(NEW.request),'UTF8')),'hex')
                OR NEW.request->>'expected_preparation_hash' IS DISTINCT FROM p.result_hash
                OR NEW.request->>'kind' IS DISTINCT FROM NEW.kind
                OR length(btrim(COALESCE(NEW.request->>'reason',''))) NOT BETWEEN 1 AND 2000
                OR NEW.created_at < p.created_at
            THEN RAISE EXCEPTION 'GROUP_FACT_REQUEST_INVALID'; END IF;
            IF NEW.kind='DECISION' THEN
                IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(p.result->'rows') row WHERE
            row->>'candidate_id'=NEW.candidate_id::text)
                    OR NOT EXISTS (SELECT 1 FROM fact_verification_decisions d WHERE
            d.decision_id=NEW.decision_id
                        AND d.candidate_id=NEW.candidate_id AND d.verification_method='HUMAN'
                        AND d.verifier_identity='human:' || NEW.reviewer_id::text
                        AND d.decided_at <= NEW.created_at AND d.decided_at >= p.created_at
                        AND NEW.request->>'candidate_id'=d.candidate_id::text
                        AND NEW.request->>'decision'=d.decision AND
            NEW.request->>'evidence_support'=d.evidence_support_result
                        AND NEW.request->>'precedence_check'=d.precedence_check_result)
                    OR EXISTS (SELECT 1 FROM fact_verification_decisions d WHERE
            d.candidate_id=NEW.candidate_id
                        AND d.decision_id <> NEW.decision_id AND d.decision <> 'NEEDS_ADJUDICATION')
                THEN RAISE EXCEPTION 'GROUP_FACT_DECISION_INVALID'; END IF;
            ELSE
                IF NOT EXISTS (SELECT 1 FROM versioned_verified_fact_sets f WHERE
            f.verified_fact_set_id=NEW.fact_set_id
                    AND f.target_scope='UNIT' AND f.opportunity_unit_id=g.unit_id AND
            f.opportunity_unit_version_id=g.unit_version_id
                    AND f.opportunity_id=b.opportunity_id AND
            f.opportunity_version=b.opportunity_version
                    AND f.source_bundle_revision_id=b.source_bundle_revision_id AND
            f.status='ACTIVE' AND f.supersedes_id IS NOT DISTINCT FROM
                (NEW.request->>'supersedes_id')::uuid)
                THEN RAISE EXCEPTION 'GROUP_FACT_PROMOTION_INVALID'; END IF;
                IF EXISTS (SELECT 1 FROM investigation_group_fact_actions WHERE
            preparation_id=p.preparation_id AND kind='PROMOTION')
                    OR EXISTS (SELECT 1 FROM jsonb_array_elements(p.result->'rows') row WHERE
            row->>'candidate_id' IS NOT NULL
                        AND NOT EXISTS (SELECT 1 FROM investigation_group_fact_actions a JOIN
            fact_verification_decisions d ON d.decision_id=a.decision_id
                            WHERE a.preparation_id=p.preparation_id AND
            a.candidate_id::text=row->>'candidate_id'
                            AND d.decision <> 'NEEDS_ADJUDICATION' AND d.decided_at <=
            NEW.created_at AND a.created_at <= NEW.created_at))
                    OR EXISTS (SELECT 1 FROM verified_facts f WHERE
            f.verified_fact_set_id=NEW.fact_set_id AND NOT EXISTS (
                        SELECT 1 FROM investigation_group_fact_actions a WHERE
            a.preparation_id=p.preparation_id
                            AND a.candidate_id=f.candidate_id AND
            a.decision_id=f.verification_decision_id))
                    OR EXISTS (SELECT 1 FROM investigation_group_fact_actions a JOIN
            fact_verification_decisions d ON d.decision_id=a.decision_id
                        WHERE a.preparation_id=p.preparation_id AND d.decision IN ('APPROVE',
            'UNKNOWN') AND NOT EXISTS (
                            SELECT 1 FROM verified_facts f WHERE
            f.verified_fact_set_id=NEW.fact_set_id
                                AND f.candidate_id=a.candidate_id AND
            f.verification_decision_id=d.decision_id))
                THEN RAISE EXCEPTION 'GROUP_FACT_PROMOTION_INCOMPLETE'; END IF;
            END IF;
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER investigation_group_fact_preparation_guard BEFORE INSERT OR UPDATE OR DELETE
        ON investigation_group_fact_preparations FOR EACH ROW EXECUTE FUNCTION
            investigation_guard_group_fact();
    CREATE TRIGGER investigation_group_fact_action_guard BEFORE INSERT OR UPDATE OR DELETE
        ON investigation_group_fact_actions FOR EACH ROW EXECUTE FUNCTION
            investigation_guard_group_fact();
    """)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM investigation_group_fact_preparations)")
    ):
        raise RuntimeError("GROUP_FACT_HISTORY_DOWNGRADE_REFUSED")
    op.drop_table("investigation_group_fact_actions")
    op.drop_table("investigation_group_fact_preparations")
    op.execute("DROP FUNCTION investigation_guard_group_fact()")
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "investigation_group_fact_materialization_valid(uuid,uuid,timestamptz)"
    )
