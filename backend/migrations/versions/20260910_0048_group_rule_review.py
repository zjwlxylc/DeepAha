"""Independent group rule receipts and exact materialization guards."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260910_0048"
down_revision = "20260910_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_group_rule_preparations",
        sa.Column("preparation_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "fact_preparation_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_group_fact_preparations.preparation_id"),
            nullable=False,
        ),
        sa.Column(
            "fact_set_id",
            sa.Uuid(),
            sa.ForeignKey("versioned_verified_fact_sets.verified_fact_set_id"),
            nullable=False,
        ),
        sa.Column("compiler_version", sa.String(128), nullable=False),
        sa.Column("result", JSONB(), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column(
            "reviewer_id", sa.Uuid(), sa.ForeignKey("reviewer_accounts.reviewer_id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "fact_preparation_id",
            "fact_set_id",
            "compiler_version",
            name="uq_group_rule_preparation",
        ),
    )
    op.create_table(
        "investigation_group_rule_decisions",
        sa.Column("decision_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "preparation_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_group_rule_preparations.preparation_id"),
            nullable=False,
        ),
        sa.Column("rule_candidate_id", sa.Uuid(), nullable=False),
        sa.Column(
            "reviewer_id", sa.Uuid(), sa.ForeignKey("reviewer_accounts.reviewer_id"), nullable=False
        ),
        sa.Column("request_key_hash", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("request", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "preparation_id", "reviewer_id", "request_key_hash", name="uq_group_rule_request"
        ),
        sa.ForeignKeyConstraint(
            ["decision_id", "rule_candidate_id"],
            [
                "p9b_rule_approval_decisions.rule_approval_decision_id",
                "p9b_rule_approval_decisions.rule_candidate_id",
            ],
        ),
    )
    op.execute(r"""
    CREATE FUNCTION investigation_group_rule_payload(field_name text, norm jsonb, fact_id text)
    RETURNS jsonb LANGUAGE plpgsql IMMUTABLE AS $$
    DECLARE key text; fld text; operator text; typ text; reason text; val jsonb;
        whitespace constant text := U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020'
            || U&'\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009'
            || U&'\200A\2028\2029\202F\205F\3000';
    BEGIN
        IF jsonb_typeof(norm) IS DISTINCT FROM 'object' THEN RETURN NULL; END IF;
        CASE field_name
        WHEN 'education_requirements' THEN
            key:='minimum_level'; fld:='education_level'; operator:='GTE'; typ:='STRING';
            reason:='学历必须满足官方最低要求';
            IF norm->>key IS NULL OR norm->>key NOT IN
                ('SECONDARY','ASSOCIATE','BACHELOR','MASTER','DOCTORATE')
                THEN RETURN NULL; END IF;
        WHEN 'major_requirements' THEN
            key:='allowed_codes'; fld:='major_code'; operator:='IN'; typ:='STRING';
            reason:='专业代码必须属于官方允许范围';
        WHEN 'credential_requirements' THEN
            key:='required_certificates'; fld:='certificates'; operator:='CONTAINS_ALL';
            typ:='STRING_SET'; reason:='必须具备官方要求的证书';
        WHEN 'household_registration_requirements' THEN
            key:='allowed_regions'; fld:='hukou_region'; operator:='IN'; typ:='STRING';
            reason:='户籍必须属于官方允许范围';
        WHEN 'applicant_scope' THEN
            key:='student_statuses'; fld:='student_status'; operator:='IN'; typ:='STRING';
            reason:='在读或毕业状态必须属于官方允许范围';
        WHEN 'age_requirements' THEN
            key:='birth_date_between'; fld:='birth_date'; operator:='BETWEEN'; typ:='DATE';
            reason:='出生日期必须处于官方允许区间';
        ELSE RETURN NULL;
        END CASE;
        IF NOT norm ? key OR (SELECT count(*) FROM jsonb_object_keys(norm)) <> 1
            THEN RETURN NULL; END IF;
        val := norm->key;
        IF key <> 'minimum_level' THEN
            IF jsonb_typeof(val) IS DISTINCT FROM 'array' THEN RETURN NULL; END IF;
            IF jsonb_array_length(val)=0 OR EXISTS(SELECT 1 FROM jsonb_array_elements(val) x
                WHERE jsonb_typeof(x) <> 'string'
                    OR NULLIF(btrim(x#>>'{}',whitespace),'') IS NULL)
                THEN RETURN NULL; END IF;
            IF key='birth_date_between' THEN
                IF jsonb_array_length(val)<>2 THEN RETURN NULL; END IF;
            ELSE
                IF (SELECT count(DISTINCT x) FROM jsonb_array_elements(val) x)<>
                    jsonb_array_length(val) THEN RETURN NULL; END IF;
                SELECT jsonb_agg(x ORDER BY x#>>'{}' COLLATE "C") INTO val
                    FROM jsonb_array_elements(val) x;
            END IF;
        END IF;
        RETURN jsonb_build_object('code','group-preview-' || fact_id,
            'field',fld,'operator',operator,'value_type',typ,'value',val,'required',true,
            'reason_template',reason);
    END $$;

    CREATE FUNCTION investigation_group_rule_valid_record(
        p investigation_group_rule_preparations, as_of timestamptz
    ) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
    DECLARE fp investigation_group_fact_preparations; g investigation_group_bindings;
        b investigation_bindings; fs versioned_verified_fact_sets; row jsonb; raw jsonb;
        prev jsonb; fact verified_facts; candidate p9b_rule_candidates;
        expected jsonb; refs jsonb; reason text; n integer; exists_fact boolean;
    BEGIN
        SELECT * INTO fp FROM investigation_group_fact_preparations
            WHERE preparation_id=p.fact_preparation_id;
        IF NOT FOUND THEN RETURN false; END IF;
        SELECT * INTO STRICT g FROM investigation_group_bindings WHERE
                group_binding_id=fp.group_binding_id;
        SELECT * INTO STRICT b FROM investigation_bindings WHERE binding_id=g.binding_id;
        SELECT * INTO fs FROM versioned_verified_fact_sets WHERE
                verified_fact_set_id=p.fact_set_id;
        IF NOT FOUND OR fs.status<>'ACTIVE' OR fs.created_at > p.created_at
            OR p.created_at<fp.created_at OR p.created_at>as_of
            OR p.compiler_version<>'group-rule-review/1.0.0+deriver-1.0.1'
            OR p.result->>'contract_version' IS DISTINCT FROM p.compiler_version
            OR p.result->>'scope' IS DISTINCT FROM 'GROUP_RULE_REVIEW_ONLY'
            OR p.result_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(p.result),'UTF8')),'hex')
            OR NOT
                investigation_group_fact_materialization_valid(fp.preparation_id,p.fact_set_id,as_of)
            OR NOT EXISTS(SELECT 1 FROM investigation_group_fact_actions WHERE
                preparation_id=fp.preparation_id AND kind='PROMOTION' AND
                fact_set_id=p.fact_set_id)
            OR NOT EXISTS(SELECT 1 FROM investigation_tasks WHERE task_id=g.task_id AND
                status='APPROVED' AND delivery_hash=b.delivery_hash)
            OR g.binding_id IS DISTINCT FROM (SELECT binding_id FROM investigation_bindings WHERE
                task_id=g.task_id ORDER BY sequence DESC LIMIT 1)
            OR NOT EXISTS(SELECT 1 FROM opportunity_units WHERE opportunity_unit_id=g.unit_id AND
                unit_kind='GROUP' AND lifecycle_status='ACTIVE' AND
                current_version_id=g.unit_version_id)
            OR NOT EXISTS(SELECT 1 FROM opportunity_unit_versions WHERE
                opportunity_unit_version_id=g.unit_version_id AND status='ACTIVE')
            OR NOT EXISTS(SELECT 1 FROM opportunities WHERE opportunity_id=b.opportunity_id AND
                current_version=b.opportunity_version)
            THEN RETURN false; END IF;
        prev:=p.result->'preview'->'result';
        IF p.result->'preview'->>'result_hash' IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(prev),'UTF8')),'hex')
            OR prev->>'contract_version' IS DISTINCT FROM 'group-rule-preview/1.0.0'
            OR prev->>'derivation_version' IS DISTINCT FROM '1.0.1'
            OR prev->>'scope' IS DISTINCT FROM 'READ_ONLY_GROUP_RULE_PREVIEW'
            OR prev->'target' IS DISTINCT FROM fp.result->'group_source'->'group_identity'
            OR prev->'fact_review'->'result' IS DISTINCT FROM fp.result
            OR prev->'fact_review'->>'result_hash' IS DISTINCT FROM fp.result_hash
            OR prev->'fact_review'->>'preparation_id' IS DISTINCT FROM fp.preparation_id::text
            OR prev->'fact_review'->'fact_set'->>'fact_set_id' IS DISTINCT FROM
                fs.verified_fact_set_id::text
            OR jsonb_typeof(p.result->'rows') IS DISTINCT FROM 'array'
            OR jsonb_array_length(p.result->'rows')<>jsonb_array_length(fp.result->'rows')
            OR jsonb_array_length(prev->'rows')<>jsonb_array_length(fp.result->'rows')
            THEN RETURN false; END IF;
        FOR row,n IN SELECT value,ordinality::int-1 FROM jsonb_array_elements(p.result->'rows')
                WITH ORDINALITY LOOP
            raw:=fp.result->'rows'->n;
            IF (row-'rule_candidate_id') IS DISTINCT FROM prev->'rows'->n
                OR row->'source_index' IS DISTINCT FROM raw->'source_index'
                OR row->'candidate_id' IS DISTINCT FROM raw->'candidate_id'
                THEN RETURN false; END IF;
            SELECT * INTO fact FROM verified_facts WHERE verified_fact_set_id=p.fact_set_id AND
                candidate_id::text=raw->>'candidate_id';
            exists_fact:=FOUND; expected:=NULL; refs:='[]';
            IF exists_fact THEN
                SELECT COALESCE(jsonb_agg(evidence_ref_id::text ORDER BY evidence_ref_id),'[]')
                INTO refs
                    FROM verified_fact_evidence WHERE verified_fact_id=fact.verified_fact_id;
                IF row->>'verified_fact_id' IS DISTINCT FROM fact.verified_fact_id::text
                    OR row->>'fact_state' IS DISTINCT FROM fact.fact_state
                    OR row->'normalized_value' IS DISTINCT FROM
                COALESCE(fact.normalized_value,'null')
                    THEN RETURN false; END IF;
                IF fact.fact_state='KNOWN' THEN
                    expected:=investigation_group_rule_payload(
                        fact.field_name,fact.normalized_value,fact.verified_fact_id::text);
                    reason:=CASE WHEN expected IS NULL THEN 'FIELD_NOT_EXECUTABLE' ELSE
                'INDEPENDENT_RULE_REVIEW_REQUIRED' END;
                ELSE reason:='FACT_UNKNOWN'; END IF;
            ELSE
                IF row->>'verified_fact_id' IS NOT NULL OR row->>'fact_state' IS NOT NULL OR
                row->>'normalized_value' IS NOT NULL THEN RETURN false; END IF;
                reason:=CASE WHEN raw->>'candidate_id' IS NULL THEN 'GROUP_FIELD_UNPROCESSED' ELSE
                'FACT_REJECTED' END;
            END IF;
            IF row->'proposed_rule_payload' IS DISTINCT FROM COALESCE(expected,'null'::jsonb)
                OR row->'evidence_ref_ids' IS DISTINCT FROM refs OR row->>'reason_code' IS
                DISTINCT FROM reason
                OR (row->>'rule_candidate_id' IS NULL) IS DISTINCT FROM (expected IS NULL)
                THEN RETURN false; END IF;
            IF expected IS NULL THEN CONTINUE; END IF;
            SELECT * INTO candidate FROM p9b_rule_candidates WHERE
                rule_candidate_id::text=row->>'rule_candidate_id';
            IF NOT FOUND OR candidate.target_scope<>'UNIT' OR
                candidate.opportunity_unit_id<>g.unit_id
                OR candidate.opportunity_unit_version_id<>g.unit_version_id OR
                candidate.opportunity_id<>b.opportunity_id
                OR candidate.opportunity_version<>b.opportunity_version OR
                candidate.verified_fact_set_id<>p.fact_set_id
                OR candidate.compiler_version<>p.compiler_version OR
                candidate.producer_identity<>'component:' || p.compiler_version
                OR candidate.rule_type<>'ATOMIC_QUALIFICATION' OR candidate.status<>'PROPOSED'
                OR candidate.proposed_rule_payload IS DISTINCT FROM expected OR
                candidate.created_at<>p.created_at
                OR (SELECT count(*) FROM p9b_rule_candidate_facts WHERE
                rule_candidate_id=candidate.rule_candidate_id)<>1
                OR NOT EXISTS(SELECT 1 FROM p9b_rule_candidate_facts WHERE
                rule_candidate_id=candidate.rule_candidate_id AND
                verified_fact_id=fact.verified_fact_id AND verified_fact_set_id=p.fact_set_id)
                OR (SELECT jsonb_agg(evidence_ref_id::text ORDER BY evidence_ref_id) FROM
                p9b_rule_candidate_evidence WHERE rule_candidate_id=candidate.rule_candidate_id)
                IS DISTINCT FROM refs
                THEN RETURN false; END IF;
        END LOOP;
        RETURN NOT EXISTS(SELECT 1 FROM jsonb_array_elements(p.result->'rows') r WHERE
                r->>'rule_candidate_id' IS NOT NULL GROUP BY r->>'rule_candidate_id' HAVING
                count(*)>1);
    END $$;
    CREATE FUNCTION investigation_group_rule_materialization_valid(id uuid, as_of timestamptz)
    RETURNS boolean LANGUAGE sql STABLE AS $$
        SELECT COALESCE((SELECT investigation_group_rule_valid_record(p,as_of)
            FROM investigation_group_rule_preparations p WHERE preparation_id=id),false)
    $$;

    CREATE FUNCTION investigation_guard_group_rule() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE p investigation_group_rule_preparations; d p9b_rule_approval_decisions;
        row jsonb; ev jsonb; fp investigation_group_fact_preparations; g
                investigation_group_bindings;
    BEGIN
        IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'GROUP_RULE_IMMUTABLE'; END IF;
        IF TG_TABLE_NAME='investigation_group_rule_preparations' THEN p:=NEW;
        ELSE SELECT * INTO STRICT p FROM investigation_group_rule_preparations WHERE
                preparation_id=NEW.preparation_id; END IF;
        SELECT * INTO STRICT fp FROM investigation_group_fact_preparations WHERE
                preparation_id=p.fact_preparation_id;
        SELECT * INTO STRICT g FROM investigation_group_bindings WHERE
                group_binding_id=fp.group_binding_id;
        PERFORM 1 FROM investigation_tasks WHERE task_id=g.task_id FOR UPDATE;
        PERFORM 1 FROM opportunity_units WHERE opportunity_unit_id=g.unit_id FOR UPDATE;
        PERFORM 1 FROM versioned_verified_fact_sets WHERE verified_fact_set_id=p.fact_set_id FOR
                UPDATE;
        IF NOT EXISTS(SELECT 1 FROM reviewer_accounts WHERE reviewer_id=NEW.reviewer_id AND active
                AND NOT synthetic AND roles ? 'VALIDATION_REVIEWER' AND allowed_purposes ?
                'OPPORTUNITY_FACT_VALIDATION')
            OR NOT investigation_group_rule_valid_record(p,NEW.created_at)
            THEN RAISE EXCEPTION 'GROUP_RULE_MATERIALIZATION_INVALID'; END IF;
        IF TG_TABLE_NAME='investigation_group_rule_preparations' THEN RETURN NEW; END IF;
        SELECT * INTO STRICT d FROM p9b_rule_approval_decisions WHERE
                rule_approval_decision_id=NEW.decision_id;
        SELECT value INTO row FROM jsonb_array_elements(p.result->'rows') WHERE
                value->>'rule_candidate_id'=NEW.rule_candidate_id::text;
        IF row IS NULL OR d.rule_candidate_id<>NEW.rule_candidate_id OR d.approval_method<>'HUMAN'
            OR d.approver_identity<>'human:' || NEW.reviewer_id::text OR
                d.policy_version<>p.compiler_version
            OR d.decided_at<>NEW.created_at OR d.decided_at<p.created_at
            OR d.reason_code<>'HUMAN_' || d.decision
            OR NEW.request_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.request),'UTF8')),'hex')
            OR NEW.request->>'expected_preparation_hash' IS DISTINCT FROM p.result_hash
            OR NEW.request->>'rule_candidate_id' IS DISTINCT FROM NEW.rule_candidate_id::text
            OR NEW.request->>'decision' IS DISTINCT FROM d.decision
            OR NULLIF(btrim(NEW.request->>'reason'),'') IS NULL
            OR NEW.request_key_hash !~ '^[a-f0-9]{64}$'
            OR jsonb_typeof(NEW.request->'evidence') IS DISTINCT FROM 'array'
            OR EXISTS(SELECT 1 FROM p9b_rule_approval_decisions WHERE
                rule_candidate_id=NEW.rule_candidate_id AND
                rule_approval_decision_id<>NEW.decision_id AND decision<>'NEEDS_ADJUDICATION')
            THEN RAISE EXCEPTION 'GROUP_RULE_DECISION_INVALID'; END IF;
        IF EXISTS(SELECT 1 FROM jsonb_array_elements(NEW.request->'evidence') e GROUP BY
                e->>'evidence_ref_id' HAVING count(*)>1)
            OR (d.decision='APPROVE' AND
                jsonb_array_length(NEW.request->'evidence')<>jsonb_array_length(row->'evidence_ref_ids'))
            THEN RAISE EXCEPTION 'GROUP_RULE_EVIDENCE_INVALID'; END IF;
        FOR ev IN SELECT value FROM jsonb_array_elements(NEW.request->'evidence') LOOP
            IF ev->>'effective_at' IS NOT NULL THEN
                IF jsonb_typeof(ev->'effective_at') IS DISTINCT FROM 'string'
                    OR ev->>'effective_at' !~
                        '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$'
                    THEN RAISE EXCEPTION 'GROUP_RULE_EVIDENCE_INVALID'; END IF;
                IF NOT isfinite((ev->>'effective_at')::timestamptz)
                    OR (ev->>'effective_at')::timestamptz>NEW.created_at
                    THEN RAISE EXCEPTION 'GROUP_RULE_EVIDENCE_INVALID'; END IF;
            END IF;
            IF (row->'evidence_ref_ids' ? (ev->>'evidence_ref_id')) IS DISTINCT FROM true
                THEN RAISE EXCEPTION 'GROUP_RULE_EVIDENCE_INVALID'; END IF;
            IF d.decision='APPROVE' AND (
                ev->>'applicability' IS DISTINCT FROM 'APPLIES_TO_EXACT_TARGET'
                OR ev->>'authority' IS NULL OR ev->>'authority' NOT IN
                ('LATEST_OFFICIAL_CORRECTION','FORMAL_OFFICIAL_ATTACHMENT','ORIGINAL_OFFICIAL_NOTICE','OFFICIAL_FAQ_GUIDANCE','HUMAN_APPROVED_MAPPING','LLM_SEMANTIC_INFERENCE')
                OR ev->>'relation' IS NULL OR ev->>'relation' NOT IN ('SUPPORTS','CONTRADICTS')
                OR ev->>'effective_at' IS NULL OR NULLIF(btrim(ev->>'reason'),'') IS NULL)
                THEN RAISE EXCEPTION 'GROUP_RULE_EVIDENCE_INVALID'; END IF;
        END LOOP;
        RETURN NEW;
    END $$;
    CREATE TRIGGER group_rule_preparation_guard BEFORE INSERT OR UPDATE OR DELETE ON
                investigation_group_rule_preparations FOR EACH ROW EXECUTE FUNCTION
                investigation_guard_group_rule();
    CREATE TRIGGER group_rule_decision_guard BEFORE INSERT OR UPDATE OR DELETE ON
                investigation_group_rule_decisions FOR EACH ROW EXECUTE FUNCTION
                investigation_guard_group_rule();

    CREATE FUNCTION investigation_group_rule_pair_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE c p9b_rule_candidates; p investigation_group_rule_preparations;
    BEGIN
        SELECT * INTO c FROM p9b_rule_candidates WHERE rule_candidate_id=NEW.rule_candidate_id;
        IF c.compiler_version NOT LIKE 'group-rule-review/%%' THEN RETURN NEW; END IF;
        SELECT * INTO p FROM investigation_group_rule_preparations p1 WHERE EXISTS(
            SELECT 1 FROM jsonb_array_elements(p1.result->'rows') r WHERE
                r->>'rule_candidate_id'=c.rule_candidate_id::text);
        IF NOT FOUND OR NOT investigation_group_rule_valid_record(p,p.created_at)
            THEN RAISE EXCEPTION 'GROUP_RULE_RECEIPT_REQUIRED'; END IF;
        IF TG_TABLE_NAME='p9b_rule_approval_decisions' THEN
            IF NOT EXISTS(SELECT 1 FROM investigation_group_rule_decisions WHERE
                decision_id=NEW.rule_approval_decision_id AND
                rule_candidate_id=c.rule_candidate_id)
                THEN RAISE EXCEPTION 'GROUP_RULE_DECISION_RECEIPT_REQUIRED'; END IF;
        END IF;
        RETURN NEW;
    END $$;
    """)
    for table in (
        "p9b_rule_candidates",
        "p9b_rule_candidate_facts",
        "p9b_rule_candidate_evidence",
        "p9b_rule_approval_decisions",
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER group_rule_pair_guard AFTER INSERT ON {table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION investigation_group_rule_pair_guard()"
        )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM investigation_group_rule_preparations)")
    ):
        raise RuntimeError("GROUP_RULE_HISTORY_DOWNGRADE_REFUSED")
    for table in (
        "p9b_rule_candidates",
        "p9b_rule_candidate_facts",
        "p9b_rule_candidate_evidence",
        "p9b_rule_approval_decisions",
    ):
        op.execute(f"DROP TRIGGER group_rule_pair_guard ON {table}")
    op.execute("DROP FUNCTION investigation_group_rule_pair_guard()")
    op.drop_table("investigation_group_rule_decisions")
    op.execute("DROP TRIGGER group_rule_preparation_guard ON investigation_group_rule_preparations")
    op.execute("DROP FUNCTION investigation_guard_group_rule()")
    op.execute("DROP FUNCTION investigation_group_rule_materialization_valid(uuid,timestamptz)")
    op.execute(
        "DROP FUNCTION investigation_group_rule_valid_record("
        "investigation_group_rule_preparations,timestamptz)"
    )
    op.drop_table("investigation_group_rule_preparations")
    op.execute("DROP FUNCTION investigation_group_rule_payload(text,jsonb,text)")
