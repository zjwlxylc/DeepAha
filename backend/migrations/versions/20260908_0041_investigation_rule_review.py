"""Append-only rule proposals and independent evidence assessments for investigations."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260908_0041"
down_revision = "20260908_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_rule_preparations",
        sa.Column("rule_preparation_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "fact_preparation_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_fact_preparations.preparation_id"),
            nullable=False,
        ),
        sa.Column("entity_id", sa.String(256), nullable=False),
        sa.Column(
            "fact_set_id",
            sa.Uuid(),
            sa.ForeignKey("versioned_verified_fact_sets.verified_fact_set_id"),
            nullable=False,
        ),
        sa.Column("compiler_version", sa.String(128), nullable=False),
        sa.Column(
            "reviewer_id", sa.Uuid(), sa.ForeignKey("reviewer_accounts.reviewer_id"), nullable=False
        ),
        sa.Column("result", JSONB(), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "fact_preparation_id",
            "entity_id",
            "fact_set_id",
            "compiler_version",
            name="uq_investigation_rule_preparation_version",
        ),
    )
    op.create_table(
        "investigation_rule_decisions",
        sa.Column("decision_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "rule_preparation_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_rule_preparations.rule_preparation_id"),
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
        sa.ForeignKeyConstraint(
            ["decision_id", "rule_candidate_id"],
            [
                "p9b_rule_approval_decisions.rule_approval_decision_id",
                "p9b_rule_approval_decisions.rule_candidate_id",
            ],
        ),
        sa.UniqueConstraint(
            "rule_preparation_id",
            "reviewer_id",
            "request_key_hash",
            name="uq_investigation_rule_decision_request",
        ),
    )
    op.execute("""
    CREATE FUNCTION investigation_guard_rule_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        prep investigation_rule_preparations; facts investigation_fact_preparations;
        binding investigation_bindings; fs versioned_verified_fact_sets;
        item jsonb; ev jsonb; fact verified_facts; candidate p9b_rule_candidates;
        decision p9b_rule_approval_decisions;
    BEGIN
        IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'INVESTIGATION_RULE_RECEIPT_IMMUTABLE'; END IF;
        IF TG_TABLE_NAME = 'investigation_rule_preparations' THEN prep := NEW;
        ELSE SELECT * INTO STRICT prep FROM investigation_rule_preparations
            WHERE rule_preparation_id = NEW.rule_preparation_id; END IF;
        SELECT * INTO STRICT facts FROM investigation_fact_preparations
            WHERE preparation_id = prep.fact_preparation_id;
        SELECT * INTO STRICT binding FROM investigation_bindings WHERE binding_id =
            facts.binding_id;
        PERFORM 1 FROM investigation_tasks WHERE task_id = binding.task_id FOR UPDATE;
        SELECT * INTO STRICT fs FROM versioned_verified_fact_sets WHERE verified_fact_set_id =
            prep.fact_set_id FOR UPDATE;
        IF binding.binding_id IS DISTINCT FROM (SELECT binding_id FROM investigation_bindings
            WHERE task_id = binding.task_id ORDER BY sequence DESC LIMIT 1)
            OR NOT EXISTS (SELECT 1 FROM investigation_tasks WHERE task_id = binding.task_id
                AND status = 'APPROVED' AND delivery_hash = binding.delivery_hash)
            OR NOT EXISTS (SELECT 1 FROM opportunities WHERE opportunity_id =
                binding.opportunity_id
                AND current_version = binding.opportunity_version)
            OR fs.status <> 'ACTIVE' OR fs.source_bundle_revision_id <>
                binding.source_bundle_revision_id
            OR NOT EXISTS (SELECT 1 FROM investigation_fact_actions WHERE preparation_id =
                facts.preparation_id
                AND entity_id = prep.entity_id AND fact_set_id = prep.fact_set_id AND kind =
                    'PROMOTION')
            OR NOT EXISTS (SELECT 1 FROM reviewer_accounts WHERE reviewer_id = NEW.reviewer_id
                AND active AND NOT synthetic AND roles ? 'VALIDATION_REVIEWER'
                AND allowed_purposes ? 'OPPORTUNITY_FACT_VALIDATION')
        THEN RAISE EXCEPTION 'INVESTIGATION_RULE_TARGET_INVALID'; END IF;
        IF TG_TABLE_NAME = 'investigation_rule_preparations' THEN
            IF NEW.result_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.result), 'UTF8')), 'hex')
                OR NEW.result->'source_rows' IS DISTINCT FROM facts.result->'rows'
                OR NEW.result->>'fact_preparation_hash' IS DISTINCT FROM facts.result_hash
                OR NEW.result->>'check_id' IS DISTINCT FROM facts.check_id::text
                OR NEW.result->>'binding_id' IS DISTINCT FROM binding.binding_id::text
                OR NEW.result->>'delivery_hash' IS DISTINCT FROM binding.delivery_hash
                OR NEW.result->>'source_bundle_revision_id' IS DISTINCT FROM
                    binding.source_bundle_revision_id::text
                OR (NEW.result->>'fact_set_version')::integer IS DISTINCT FROM fs.version
                OR NEW.result->'target' IS DISTINCT FROM (SELECT t FROM
                    jsonb_array_elements(facts.result->'targets') t
                    WHERE t->>'entity_id' = NEW.entity_id)
                OR jsonb_typeof(NEW.result->'rows') IS DISTINCT FROM 'array'
                OR jsonb_array_length(NEW.result->'rows') <> (SELECT count(*) FROM verified_facts
                    WHERE verified_fact_set_id = NEW.fact_set_id)
                OR EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.result->'rows') r GROUP BY
                    r->>'verified_fact_id' HAVING count(*) > 1)
            THEN RAISE EXCEPTION 'INVESTIGATION_RULE_PREPARATION_MISMATCH'; END IF;
            FOR item IN SELECT value FROM jsonb_array_elements(NEW.result->'rows') LOOP
                SELECT * INTO STRICT fact FROM verified_facts WHERE verified_fact_id =
                    (item->>'verified_fact_id')::uuid
                    AND verified_fact_set_id = NEW.fact_set_id;
                IF item->>'candidate_id' IS DISTINCT FROM fact.candidate_id::text
                    OR item->>'field_name' IS DISTINCT FROM fact.field_name
                    OR item->>'fact_state' IS DISTINCT FROM fact.fact_state
                    OR item->'normalized_value' IS DISTINCT FROM COALESCE(fact.normalized_value,
                        'null'::jsonb)
                    OR jsonb_array_length(item->'evidence') IS DISTINCT FROM (SELECT count(*) FROM
                        verified_fact_evidence WHERE verified_fact_id = fact.verified_fact_id)
                    OR EXISTS (SELECT 1 FROM jsonb_array_elements(item->'evidence') e
                        GROUP BY e->>'evidence_ref_id' HAVING count(*) > 1)
                    OR (SELECT jsonb_agg(v.evidence_ref_id::text ORDER BY v.evidence_ref_id) FROM
                        verified_fact_evidence v
                        WHERE v.verified_fact_id = fact.verified_fact_id) IS DISTINCT FROM
                            item->'evidence_ref_ids'
                THEN RAISE EXCEPTION 'INVESTIGATION_RULE_FACT_MISMATCH'; END IF;
                FOR ev IN SELECT value FROM jsonb_array_elements(item->'evidence') LOOP
                    IF NOT EXISTS (SELECT 1 FROM verified_fact_evidence v JOIN document_blocks b
                        ON b.block_id = v.block_id
                        WHERE v.verified_fact_id = fact.verified_fact_id AND
                            v.evidence_ref_id::text = ev->>'evidence_ref_id'
                        AND b.block_id::text = ev->>'block_id' AND b.document_id::text =
                            ev->>'document_id'
                        AND b.canonical_text_or_value = ev->>'text' AND b.structural_locator =
                            ev->'structural_locator')
                    THEN RAISE EXCEPTION 'INVESTIGATION_RULE_EVIDENCE_MISMATCH'; END IF;
                END LOOP;
                IF item->>'rule_candidate_id' IS NOT NULL THEN
                    SELECT * INTO STRICT candidate FROM p9b_rule_candidates WHERE
                        rule_candidate_id = (item->>'rule_candidate_id')::uuid;
                    IF fact.fact_state <> 'KNOWN' OR candidate.verified_fact_set_id <>
                        NEW.fact_set_id
                        OR candidate.proposed_rule_payload IS DISTINCT FROM item->'payload'
                        OR candidate.compiler_version <> NEW.compiler_version
                        OR candidate.producer_identity <> 'component:' || NEW.compiler_version
                        OR (SELECT count(*) FROM p9b_rule_candidate_facts WHERE rule_candidate_id
                            = candidate.rule_candidate_id) <> 1
                        OR NOT EXISTS (SELECT 1 FROM p9b_rule_candidate_facts WHERE
                            rule_candidate_id = candidate.rule_candidate_id
                            AND verified_fact_id = fact.verified_fact_id)
                        OR (SELECT jsonb_agg(evidence_ref_id::text ORDER BY evidence_ref_id) FROM
                            p9b_rule_candidate_evidence
                            WHERE rule_candidate_id = candidate.rule_candidate_id) IS DISTINCT
                                FROM item->'evidence_ref_ids'
                    THEN RAISE EXCEPTION 'INVESTIGATION_RULE_CANDIDATE_MISMATCH'; END IF;
                ELSIF item->'payload' IS DISTINCT FROM 'null'::jsonb THEN
                    RAISE EXCEPTION 'INVESTIGATION_RULE_CANDIDATE_MISMATCH';
                END IF;
            END LOOP;
        ELSE
            SELECT * INTO STRICT decision FROM p9b_rule_approval_decisions WHERE
                rule_approval_decision_id = NEW.decision_id;
            SELECT r INTO STRICT item FROM jsonb_array_elements(prep.result->'rows') r
                WHERE r->>'rule_candidate_id' = NEW.rule_candidate_id::text;
            IF NEW.request_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.request), 'UTF8')), 'hex')
                OR NEW.request->>'rule_preparation_id' IS DISTINCT FROM
                    prep.rule_preparation_id::text
                OR NEW.request->>'fact_preparation_id' IS DISTINCT FROM facts.preparation_id::text
                OR NEW.request->>'check_id' IS DISTINCT FROM facts.check_id::text
                OR NEW.request->>'binding_id' IS DISTINCT FROM binding.binding_id::text
                OR NEW.request->>'delivery_hash' IS DISTINCT FROM binding.delivery_hash
                OR NEW.request->>'fact_set_id' IS DISTINCT FROM prep.fact_set_id::text
                OR NEW.request->>'entity_id' IS DISTINCT FROM prep.entity_id
                OR NEW.request->>'rule_candidate_id' IS DISTINCT FROM NEW.rule_candidate_id::text
                OR NEW.request->>'decision' IS DISTINCT FROM decision.decision
                OR decision.approval_method <> 'HUMAN' OR decision.approver_identity <> 'human:'
                    || NEW.reviewer_id::text
                OR NULLIF(btrim(NEW.request->>'reason'), '') IS NULL
            THEN RAISE EXCEPTION 'INVESTIGATION_RULE_DECISION_MISMATCH'; END IF;
            IF EXISTS (SELECT 1 FROM p9b_rule_approval_decisions d
                WHERE d.rule_candidate_id = NEW.rule_candidate_id
                  AND d.rule_approval_decision_id <> NEW.decision_id
                  AND d.decision <> 'NEEDS_ADJUDICATION')
            THEN RAISE EXCEPTION 'INVESTIGATION_RULE_ALREADY_DECIDED'; END IF;
            IF jsonb_typeof(NEW.request->'evidence') IS DISTINCT FROM 'array'
                OR EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.request->'evidence') e
                    GROUP BY e->>'evidence_ref_id' HAVING count(*) > 1)
                OR EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.request->'evidence') e
                    WHERE (item->'evidence_ref_ids' ? (e->>'evidence_ref_id'))
                        IS DISTINCT FROM TRUE)
            THEN RAISE EXCEPTION 'INVESTIGATION_RULE_EVIDENCE_INCOMPLETE'; END IF;
            IF decision.decision = 'APPROVE' THEN
                IF jsonb_typeof(NEW.request->'evidence') IS DISTINCT FROM 'array'
                    OR jsonb_array_length(NEW.request->'evidence') <>
                        jsonb_array_length(item->'evidence_ref_ids')
                    OR EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.request->'evidence') e GROUP
                        BY e->>'evidence_ref_id' HAVING count(*) > 1)
                THEN RAISE EXCEPTION 'INVESTIGATION_RULE_EVIDENCE_INCOMPLETE'; END IF;
                FOR ev IN SELECT value FROM jsonb_array_elements(NEW.request->'evidence') LOOP
                    IF (item->'evidence_ref_ids' ? (ev->>'evidence_ref_id')) IS DISTINCT FROM TRUE
                        OR ev->>'applicability' IS DISTINCT FROM 'APPLIES_TO_EXACT_TARGET'
                        OR ev->>'authority' IS NULL OR ev->>'authority' NOT IN
                            ('LATEST_OFFICIAL_CORRECTION',
                            'FORMAL_OFFICIAL_ATTACHMENT', 'ORIGINAL_OFFICIAL_NOTICE',
                                'OFFICIAL_FAQ_GUIDANCE',
                            'HUMAN_APPROVED_MAPPING', 'LLM_SEMANTIC_INFERENCE')
                        OR ev->>'relation' IS NULL OR ev->>'relation' NOT IN ('SUPPORTS',
                            'CONTRADICTS')
                        OR NULLIF(btrim(ev->>'reason'), '') IS NULL OR ev->>'effective_at' IS NULL
                        OR NOT (ev->>'effective_at' ~ '(Z|[+-][0-9]{2}:[0-9]{2})$')
                    THEN RAISE EXCEPTION 'INVESTIGATION_RULE_EVIDENCE_INCOMPLETE'; END IF;
                    PERFORM (ev->>'effective_at')::timestamptz;
                END LOOP;
            END IF;
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER investigation_rule_preparation_guard BEFORE INSERT OR UPDATE OR DELETE
        ON investigation_rule_preparations FOR EACH ROW EXECUTE FUNCTION
            investigation_guard_rule_receipt();
    CREATE TRIGGER investigation_rule_decision_guard BEFORE INSERT OR UPDATE OR DELETE
        ON investigation_rule_decisions FOR EACH ROW EXECUTE FUNCTION
            investigation_guard_rule_receipt();
    CREATE FUNCTION investigation_require_rule_decision_receipt() RETURNS trigger LANGUAGE plpgsql
        AS $$
    BEGIN
        IF EXISTS (SELECT 1 FROM p9b_rule_candidates WHERE rule_candidate_id =
            NEW.rule_candidate_id
                AND compiler_version LIKE 'direct-wma-rule-bridge/%%')
            AND NOT EXISTS (SELECT 1 FROM investigation_rule_decisions
                WHERE decision_id = NEW.rule_approval_decision_id AND rule_candidate_id =
                    NEW.rule_candidate_id)
        THEN RAISE EXCEPTION 'INVESTIGATION_RULE_DECISION_RECEIPT_REQUIRED'; END IF;
        RETURN NEW;
    END $$;
    CREATE CONSTRAINT TRIGGER investigation_rule_decision_pair_guard AFTER INSERT ON
        p9b_rule_approval_decisions
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION
            investigation_require_rule_decision_receipt();
    """)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM investigation_rule_preparations)")
    ):
        raise RuntimeError("INVESTIGATION_RULE_HISTORY_DOWNGRADE_REFUSED")
    op.execute(
        "DROP TRIGGER IF EXISTS investigation_rule_decision_pair_guard "
        "ON p9b_rule_approval_decisions"
    )
    op.execute("DROP FUNCTION IF EXISTS investigation_require_rule_decision_receipt()")
    op.drop_table("investigation_rule_decisions")
    op.drop_table("investigation_rule_preparations")
    op.execute("DROP FUNCTION investigation_guard_rule_receipt()")
