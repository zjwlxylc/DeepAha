"""Append-only group rule applicability, without qualification inheritance."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260910_0049"
down_revision = "20260910_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_group_applicability",
        sa.Column("decision_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "target_plan_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_unit_plans.plan_id"),
            nullable=False,
        ),
        sa.Column(
            "source_rule_preparation_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_group_rule_preparations.preparation_id"),
            nullable=False,
        ),
        sa.Column(
            "source_rule_candidate_id",
            sa.Uuid(),
            sa.ForeignKey("p9b_rule_candidates.rule_candidate_id"),
            nullable=False,
        ),
        sa.Column(
            "source_rule_approval_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_group_rule_decisions.decision_id"),
            nullable=False,
        ),
        sa.Column(
            "previous_decision_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_group_applicability.decision_id"),
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "reviewer_id", sa.Uuid(), sa.ForeignKey("reviewer_accounts.reviewer_id"), nullable=False
        ),
        sa.Column("request_key_hash", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("request", JSONB(), nullable=False),
        sa.Column("context", JSONB(), nullable=False),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column("evidence_snapshot", JSONB(), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "target_plan_id",
            "source_rule_candidate_id",
            "sequence",
            name="uq_group_applicability_sequence",
        ),
        sa.UniqueConstraint(
            "target_plan_id",
            "reviewer_id",
            "request_key_hash",
            name="uq_group_applicability_request",
        ),
    )
    op.execute("""
    CREATE FUNCTION group_applicability_iso(ts timestamptz) RETURNS text LANGUAGE sql STABLE AS $$
        SELECT to_char(ts AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS') ||
            CASE WHEN mod(extract(microseconds FROM ts)::bigint,1000000)=0 THEN ''
                ELSE '.' || to_char(ts AT TIME ZONE 'UTC','US') END || 'Z'
    $$;
    CREATE FUNCTION group_applicability_review_order() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE latest investigation_group_rule_decisions;
    BEGIN
        PERFORM 1 FROM investigation_tasks WHERE task_id=(
            SELECT g.task_id FROM investigation_group_rule_preparations p
            JOIN investigation_group_fact_preparations f ON f.preparation_id=p.fact_preparation_id
            JOIN investigation_group_bindings g ON g.group_binding_id=f.group_binding_id
            WHERE p.preparation_id=NEW.preparation_id) FOR UPDATE;
        SELECT * INTO latest FROM investigation_group_rule_decisions
            WHERE preparation_id=NEW.preparation_id
            ORDER BY created_at DESC,decision_id DESC LIMIT 1;
        IF latest.decision_id IS NOT NULL AND
            (NEW.created_at,NEW.decision_id)<=(latest.created_at,latest.decision_id)
            THEN RAISE EXCEPTION 'GROUP_APPLICABILITY_REVIEW_ORDER_INVALID'; END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER group_applicability_review_order BEFORE INSERT
        ON investigation_group_rule_decisions FOR EACH ROW
        EXECUTE FUNCTION group_applicability_review_order();
    CREATE FUNCTION group_applicability_review(id uuid) RETURNS jsonb LANGUAGE plpgsql STABLE AS $$
    DECLARE p investigation_group_rule_preparations; d investigation_group_rule_decisions;
        item jsonb; history jsonb:='[]'; decisions jsonb:='{}';
    BEGIN
        SELECT * INTO STRICT p FROM investigation_group_rule_preparations WHERE preparation_id=id;
        FOR d IN SELECT * FROM investigation_group_rule_decisions WHERE preparation_id=id
                ORDER BY created_at,decision_id LOOP
            item:=jsonb_build_object('decision_id',d.decision_id::text,
                'rule_candidate_id',d.rule_candidate_id::text,'decision',d.request->>'decision',
                'reason',d.request->>'reason','evidence',d.request->'evidence',
                'reviewer_id',d.reviewer_id::text,'created_at',group_applicability_iso(d.created_at));
            history:=history || jsonb_build_array(item);
            decisions:=decisions || jsonb_build_object(d.rule_candidate_id::text,item);
        END LOOP;
        RETURN jsonb_build_object('preparation_id',p.preparation_id::text,
            'fact_preparation_id',p.fact_preparation_id::text,'fact_set_id',p.fact_set_id::text,
            'result',p.result,'result_hash',p.result_hash,'reviewer_id',p.reviewer_id::text,
            'created_at',group_applicability_iso(p.created_at),'decisions',decisions,'history',history);
    END $$;
    CREATE FUNCTION investigation_guard_group_applicability() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        target investigation_unit_plans; tp investigation_rule_preparations;
        tf investigation_fact_preparations; p investigation_group_rule_preparations;
        fp investigation_group_fact_preparations; g investigation_group_bindings;
        a investigation_group_rule_decisions; b investigation_bindings;
        previous investigation_group_applicability; e jsonb; q jsonb; expected jsonb;
        block document_blocks; member source_bundle_members; material investigation_materials;
        n integer; i integer; source_member jsonb; review jsonb; expected_context jsonb;
        whitespace constant text := U&'\\0009\\000A\\000B\\000C\\000D\\001C\\001D\\001E\\001F\\0020'
            || U&'\\0085\\00A0\\1680\\2000\\2001\\2002\\2003\\2004\\2005\\2006\\2007\\2008\\2009'
            || U&'\\200A\\2028\\2029\\202F\\205F\\3000';
    BEGIN
        IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'GROUP_APPLICABILITY_IMMUTABLE'; END IF;
        SELECT * INTO STRICT p FROM investigation_group_rule_preparations
            WHERE preparation_id=NEW.source_rule_preparation_id;
        SELECT * INTO STRICT fp FROM investigation_group_fact_preparations
            WHERE preparation_id=p.fact_preparation_id;
        SELECT * INTO STRICT g FROM investigation_group_bindings
            WHERE group_binding_id=fp.group_binding_id;
        PERFORM 1 FROM investigation_tasks WHERE task_id=g.task_id FOR UPDATE;
        SELECT * INTO STRICT b FROM investigation_bindings WHERE binding_id=g.binding_id;
        SELECT * INTO STRICT target FROM investigation_unit_plans WHERE plan_id=NEW.target_plan_id;
        SELECT * INTO STRICT tp FROM investigation_rule_preparations
            WHERE rule_preparation_id=target.rule_preparation_id;
        SELECT * INTO STRICT tf FROM investigation_fact_preparations
            WHERE preparation_id=tp.fact_preparation_id;
        SELECT * INTO STRICT a FROM investigation_group_rule_decisions
            WHERE decision_id=NEW.source_rule_approval_id;
        PERFORM 1 FROM reviewer_accounts WHERE reviewer_id=NEW.reviewer_id FOR SHARE;
        PERFORM 1 FROM versioned_verified_fact_sets WHERE
            verified_fact_set_id IN (p.fact_set_id,tp.fact_set_id) ORDER BY verified_fact_set_id
            FOR SHARE;
        IF uuid_extract_version(NEW.decision_id) IS DISTINCT FROM 7 OR NEW.sequence<1
            OR NEW.request_key_hash !~ '^[0-9a-f]{64}$' OR NOT isfinite(NEW.created_at)
            OR NEW.created_at < GREATEST(a.created_at,target.created_at)
            OR NOT EXISTS(SELECT 1 FROM reviewer_accounts WHERE reviewer_id=NEW.reviewer_id
                AND active AND NOT synthetic AND roles ? 'VALIDATION_REVIEWER'
                AND allowed_purposes ? 'OPPORTUNITY_FACT_VALIDATION')
            OR NOT investigation_group_rule_materialization_valid(p.preparation_id,NEW.created_at)
            OR tf.task_id IS DISTINCT FROM g.task_id
            OR tf.binding_id IS DISTINCT FROM g.binding_id
            OR tf.check_id IS DISTINCT FROM fp.check_id
            OR a.preparation_id IS DISTINCT FROM p.preparation_id
            OR a.rule_candidate_id IS DISTINCT FROM NEW.source_rule_candidate_id
            OR a.request->>'decision' IS DISTINCT FROM 'APPROVE'
            OR NOT EXISTS(SELECT 1 FROM p9b_rule_approval_decisions WHERE
                rule_approval_decision_id=a.decision_id AND rule_candidate_id=a.rule_candidate_id
                AND decision='APPROVE' AND approval_method='HUMAN'
                AND approver_identity='human:' || a.reviewer_id::text
                AND decided_at=a.created_at AND policy_version=p.compiler_version)
            OR NOT EXISTS(SELECT 1 FROM versioned_verified_fact_sets WHERE
                verified_fact_set_id=tp.fact_set_id AND status='ACTIVE')
            OR tp.result->'target'->>'entity_kind' IS DISTINCT FROM 'position'
            OR NOT EXISTS(SELECT 1 FROM opportunity_units WHERE
                current_version_id=target.unit_version_id AND unit_kind='POSITION'
                AND lifecycle_status='ACTIVE' AND opportunity_id=b.opportunity_id
                AND opportunity_version=b.opportunity_version)
            THEN RAISE EXCEPTION 'GROUP_APPLICABILITY_TARGET_INVALID'; END IF;
        SELECT value INTO source_member FROM jsonb_array_elements(g.source->'members')
            WHERE value->>'entity_id'=tp.entity_id;
        IF source_member IS NULL OR source_member->>'state' IS DISTINCT FROM 'BOUND'
            OR source_member->'position_binding' IS DISTINCT FROM jsonb_build_object(
                'entity_id',tp.entity_id,
                'opportunity_unit_id',target.plan->'target'->>'unit_id',
                'opportunity_unit_version_id',target.unit_version_id::text)
            THEN RAISE EXCEPTION 'GROUP_APPLICABILITY_MEMBER_INVALID'; END IF;
        review:=group_applicability_review(p.preparation_id);
        expected_context:=jsonb_build_object(
            'contract_version','group-rule-applicability-context/1.0.0',
            'task_id',g.task_id::text,'target_plan_id',target.plan_id::text,
            'target_plan_hash',target.plan_hash,'target_plan_context_hash',target.context_hash,
            'target',target.plan->'target','target_entity_id',tp.entity_id,
            'source_group',fp.result->'group_source'->'group_identity',
            'group_binding_id',g.group_binding_id::text,'group_source_hash',g.source_hash,
            'member',source_member,'binding_id',b.binding_id::text,'check_id',fp.check_id::text,
            'source_bundle_revision_id',b.source_bundle_revision_id::text,
            'source_rule_preparation_id',p.preparation_id::text,
            'source_rule_preparation_hash',p.result_hash,
            'source_rule_candidate_id',a.rule_candidate_id::text,
            'source_rule_approval_id',a.decision_id::text,
            'source_rule_approval_hash',encode(sha256(convert_to(p9b_canonical_json(
                review->'decisions'->a.rule_candidate_id::text),'UTF8')),'hex'),
            'source_review_hash',encode(sha256(convert_to(p9b_canonical_json(review),'UTF8')),'hex'));
        IF NEW.request_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.request),'UTF8')),'hex')
            OR NEW.context_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.context),'UTF8')),'hex')
            OR NEW.evidence_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.evidence_snapshot),'UTF8')),'hex')
            OR NEW.request->>'contract_version' IS DISTINCT FROM
                'group-applicability-decision/1.0.0'
            OR NOT (NEW.request ?& ARRAY['contract_version','target_plan_id',
                'source_rule_preparation_id','source_rule_candidate_id','context_hash',
                'previous_decision_id','outcome','evidence','reason'])
            OR NEW.request - ARRAY['contract_version','target_plan_id','source_rule_preparation_id',
                'source_rule_candidate_id','context_hash','previous_decision_id','outcome',
                'evidence','reason'] <> '{}'::jsonb
            OR NEW.request->>'context_hash' IS DISTINCT FROM NEW.context_hash
            OR NEW.request->>'target_plan_id' IS DISTINCT FROM NEW.target_plan_id::text
            OR NEW.request->>'source_rule_preparation_id' IS DISTINCT FROM p.preparation_id::text
            OR NEW.request->>'source_rule_candidate_id' IS DISTINCT FROM a.rule_candidate_id::text
            OR NEW.request->>'previous_decision_id' IS DISTINCT FROM NEW.previous_decision_id::text
            OR (NEW.request->>'outcome' IN ('APPLIES','DOES_NOT_APPLY','NEEDS_ADJUDICATION'))
                IS DISTINCT FROM TRUE
            OR jsonb_typeof(NEW.request->'reason') IS DISTINCT FROM 'string'
            OR (length(btrim(NEW.request->>'reason',whitespace)) BETWEEN 1 AND 2000)
                IS DISTINCT FROM TRUE
            OR length(NEW.request->>'reason')>2000
            OR NEW.context IS DISTINCT FROM expected_context
            OR NEW.context->>'contract_version' IS DISTINCT FROM
                'group-rule-applicability-context/1.0.0'
            OR NEW.context->>'task_id' IS DISTINCT FROM g.task_id::text
            OR NEW.context->>'binding_id' IS DISTINCT FROM b.binding_id::text
            OR NEW.context->>'check_id' IS DISTINCT FROM fp.check_id::text
            OR NEW.context->>'source_bundle_revision_id' IS DISTINCT FROM
                b.source_bundle_revision_id::text
            OR NEW.context->>'target_plan_id' IS DISTINCT FROM target.plan_id::text
            OR NEW.context->>'target_plan_hash' IS DISTINCT FROM target.plan_hash
            OR NEW.context->>'target_plan_context_hash' IS DISTINCT FROM target.context_hash
            OR NEW.context->'target' IS DISTINCT FROM target.plan->'target'
            OR NEW.context->>'target_entity_id' IS DISTINCT FROM tp.entity_id
            OR NEW.context->'source_group' IS DISTINCT FROM
                fp.result->'group_source'->'group_identity'
            OR NEW.context->>'group_binding_id' IS DISTINCT FROM g.group_binding_id::text
            OR NEW.context->>'group_source_hash' IS DISTINCT FROM g.source_hash
            OR NEW.context->'member' IS DISTINCT FROM source_member
            OR NEW.context->>'source_rule_preparation_id' IS DISTINCT FROM p.preparation_id::text
            OR NEW.context->>'source_rule_preparation_hash' IS DISTINCT FROM p.result_hash
            OR NEW.context->>'source_rule_candidate_id' IS DISTINCT FROM a.rule_candidate_id::text
            OR NEW.context->>'source_rule_approval_id' IS DISTINCT FROM a.decision_id::text
            THEN RAISE EXCEPTION 'GROUP_APPLICABILITY_CONTEXT_INVALID'; END IF;
        SELECT * INTO previous FROM investigation_group_applicability
            WHERE target_plan_id=NEW.target_plan_id AND source_rule_candidate_id=a.rule_candidate_id
            ORDER BY sequence DESC LIMIT 1;
        IF NEW.previous_decision_id IS DISTINCT FROM previous.decision_id
            OR NEW.sequence IS DISTINCT FROM COALESCE(previous.sequence,0)+1
            OR (previous.decision_id IS NOT NULL AND NEW.created_at<previous.created_at)
            THEN RAISE EXCEPTION 'GROUP_APPLICABILITY_PREDECESSOR_CHANGED'; END IF;
        IF jsonb_typeof(NEW.request->'evidence') IS DISTINCT FROM 'array'
            OR jsonb_typeof(NEW.evidence_snapshot) IS DISTINCT FROM 'array'
            THEN RAISE EXCEPTION 'GROUP_APPLICABILITY_EVIDENCE_INVALID'; END IF;
        n:=jsonb_array_length(NEW.request->'evidence');
        IF n>20 OR n<>jsonb_array_length(NEW.evidence_snapshot)
            OR (NEW.request->>'outcome'<>'NEEDS_ADJUDICATION' AND n=0)
            OR EXISTS(SELECT 1 FROM jsonb_array_elements(NEW.request->'evidence') v
                GROUP BY v->>'member_id',v->>'block_id',v->>'quote' HAVING count(*)>1)
            THEN RAISE EXCEPTION 'GROUP_APPLICABILITY_EVIDENCE_INVALID'; END IF;
        FOR i IN 0..n-1 LOOP
            q:=NEW.request->'evidence'->i; e:=NEW.evidence_snapshot->i;
            SELECT * INTO STRICT block FROM document_blocks WHERE block_id=(q->>'block_id')::uuid;
            SELECT * INTO STRICT member FROM source_bundle_members
                WHERE source_bundle_member_id=(q->>'member_id')::uuid;
            SELECT * INTO STRICT material FROM investigation_materials
                WHERE task_id=g.task_id AND material_id=member.wma_material_id;
            expected:=jsonb_build_object('member_id',member.source_bundle_member_id::text,
                'block_id',block.block_id::text,'quote',q->>'quote',
                'document_id',block.document_id::text,'material_id',member.wma_material_id,
                'source_url',material.metadata_snapshot->>'url','evidence_ref_id',block.evidence_ref_id::text,
                'block_hash',block.block_hash,'binding_hash',block.evidence_binding_hash,
                'locator',block.structural_locator);
            IF q - ARRAY['member_id','block_id','quote'] <> '{}'::jsonb
                OR jsonb_typeof(q->'quote') IS DISTINCT FROM 'string'
                OR e IS DISTINCT FROM expected
                OR member.source_bundle_revision_id IS DISTINCT FROM b.source_bundle_revision_id
                OR member.wma_task_id IS DISTINCT FROM g.task_id
                OR member.provenance_kind IS DISTINCT FROM 'DIRECT_WMA'
                OR block.document_id IS DISTINCT FROM member.document_id
                OR block.parse_contract_version IS DISTINCT FROM 'reader-document-block-contract-v1'
                OR (length(q->>'quote') BETWEEN 1 AND 20000) IS DISTINCT FROM TRUE
                OR NULLIF(btrim(q->>'quote',whitespace),'') IS NULL
                OR (strpos(block.canonical_text_or_value,q->>'quote')>0) IS DISTINCT FROM TRUE
                THEN RAISE EXCEPTION 'GROUP_APPLICABILITY_EVIDENCE_INVALID'; END IF;
        END LOOP;
        RETURN NEW;
    END $$;
    CREATE TRIGGER group_applicability_guard BEFORE INSERT OR UPDATE OR DELETE
        ON investigation_group_applicability FOR EACH ROW
        EXECUTE FUNCTION investigation_guard_group_applicability();
    """)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM investigation_group_applicability)")
    ):
        raise RuntimeError("GROUP_APPLICABILITY_HISTORY_DOWNGRADE_REFUSED")
    op.drop_table("investigation_group_applicability")
    op.execute(
        "DROP TRIGGER IF EXISTS group_applicability_review_order "
        "ON investigation_group_rule_decisions"
    )
    op.execute("DROP FUNCTION IF EXISTS group_applicability_review_order()")
    op.execute("DROP FUNCTION investigation_guard_group_applicability()")
    op.execute("DROP FUNCTION IF EXISTS group_applicability_review(uuid)")
    op.execute("DROP FUNCTION IF EXISTS group_applicability_iso(timestamptz)")
