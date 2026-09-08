"""Append-only announcement rule applicability, without qualification inheritance."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260908_0043"
down_revision = "20260908_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_rule_applicability",
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
            sa.ForeignKey("investigation_rule_preparations.rule_preparation_id"),
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
            sa.ForeignKey("investigation_rule_decisions.decision_id"),
            nullable=False,
        ),
        sa.Column(
            "previous_decision_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_rule_applicability.decision_id"),
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
            name="uq_investigation_applicability_sequence",
        ),
        sa.UniqueConstraint(
            "target_plan_id",
            "reviewer_id",
            "request_key_hash",
            name="uq_investigation_applicability_request",
        ),
    )
    op.execute("""
    CREATE FUNCTION investigation_guard_rule_applicability() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        target investigation_unit_plans; source investigation_rule_preparations;
        facts investigation_fact_preparations; target_prep investigation_rule_preparations;
        binding investigation_bindings; approval investigation_rule_decisions;
        previous investigation_rule_applicability; e jsonb; b document_blocks;
        member source_bundle_members; evidence_count integer;
    BEGIN
        IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'RULE_APPLICABILITY_IMMUTABLE'; END IF;
        SELECT * INTO STRICT target FROM investigation_unit_plans WHERE plan_id=NEW.target_plan_id;
        SELECT * INTO STRICT target_prep FROM investigation_rule_preparations
            WHERE rule_preparation_id=target.rule_preparation_id;
        SELECT * INTO STRICT source FROM investigation_rule_preparations
            WHERE rule_preparation_id=NEW.source_rule_preparation_id;
        SELECT * INTO STRICT facts FROM investigation_fact_preparations
            WHERE preparation_id=source.fact_preparation_id;
        SELECT * INTO STRICT binding FROM investigation_bindings WHERE binding_id=facts.binding_id;
        PERFORM 1 FROM investigation_tasks WHERE task_id=binding.task_id FOR UPDATE;
        SELECT * INTO STRICT approval FROM investigation_rule_decisions
            WHERE decision_id=NEW.source_rule_approval_id;
        IF uuid_extract_version(NEW.decision_id) IS DISTINCT FROM 7
            OR NEW.sequence < 1 OR NEW.request_key_hash !~ '^[0-9a-f]{64}$'
            OR NOT EXISTS(SELECT 1 FROM reviewer_accounts WHERE reviewer_id=NEW.reviewer_id
                AND active AND NOT synthetic AND roles ? 'VALIDATION_REVIEWER'
                AND allowed_purposes ? 'OPPORTUNITY_FACT_VALIDATION')
            OR source.result->'target'->>'target_scope' IS DISTINCT FROM 'OPPORTUNITY'
            OR source.result->'target'->>'entity_kind' IS DISTINCT FROM 'announcement'
            OR source.fact_preparation_id IS DISTINCT FROM target_prep.fact_preparation_id
            OR approval.rule_preparation_id IS DISTINCT FROM source.rule_preparation_id
            OR approval.rule_candidate_id IS DISTINCT FROM NEW.source_rule_candidate_id
            OR approval.request->>'decision' IS DISTINCT FROM 'APPROVE'
            OR NOT EXISTS(SELECT 1 FROM p9b_rule_candidates WHERE
                rule_candidate_id=NEW.source_rule_candidate_id
                    AND verified_fact_set_id=source.fact_set_id)
            OR NOT EXISTS(SELECT 1 FROM versioned_verified_fact_sets WHERE
                verified_fact_set_id=source.fact_set_id AND status='ACTIVE')
            OR NOT EXISTS(SELECT 1 FROM versioned_verified_fact_sets WHERE
                verified_fact_set_id=target_prep.fact_set_id AND status='ACTIVE')
            OR NOT EXISTS(SELECT 1 FROM investigation_tasks WHERE task_id=binding.task_id
                AND status='APPROVED' AND delivery_hash=binding.delivery_hash)
            OR binding.binding_id IS DISTINCT FROM (SELECT binding_id FROM investigation_bindings
                WHERE task_id=binding.task_id ORDER BY sequence DESC LIMIT 1)
            OR NOT EXISTS(SELECT 1 FROM opportunities WHERE opportunity_id=binding.opportunity_id
                AND current_version=binding.opportunity_version)
            OR NOT EXISTS(SELECT 1 FROM opportunity_units WHERE
                current_version_id=target.unit_version_id AND opportunity_id=binding.opportunity_id)
            OR NOT EXISTS(SELECT 1 FROM source_bundle_revisions WHERE
                source_bundle_revision_id=binding.source_bundle_revision_id AND status='FROZEN')
        THEN RAISE EXCEPTION 'RULE_APPLICABILITY_TARGET_INVALID'; END IF;
        IF NEW.request_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.request),'UTF8')),'hex')
            OR NEW.context_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.context),'UTF8')),'hex')
            OR NEW.evidence_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.evidence_snapshot),'UTF8')),'hex')
            OR NEW.request->>'context_hash' IS DISTINCT FROM NEW.context_hash
            OR NEW.request->>'target_plan_id' IS DISTINCT FROM NEW.target_plan_id::text
            OR NEW.request->>'source_rule_preparation_id'
                    IS DISTINCT FROM NEW.source_rule_preparation_id::text
            OR NEW.request->>'source_rule_candidate_id'
                    IS DISTINCT FROM NEW.source_rule_candidate_id::text
            OR NEW.request->>'previous_decision_id' IS DISTINCT FROM NEW.previous_decision_id::text
            OR (NEW.request->>'outcome' IN ('APPLIES','DOES_NOT_APPLY','NEEDS_ADJUDICATION'))
                    IS DISTINCT FROM TRUE
            OR (length(btrim(NEW.request->>'reason')) BETWEEN 1 AND 2000) IS DISTINCT FROM TRUE
            OR NEW.context->>'contract_version'
                    IS DISTINCT FROM 'announcement-rule-applicability/1.0.0'
            OR NEW.context->>'target_plan_id' IS DISTINCT FROM NEW.target_plan_id::text
            OR NEW.context->>'target_plan_hash' IS DISTINCT FROM target.plan_hash
            OR NEW.context->>'target_plan_context_hash' IS DISTINCT FROM target.context_hash
            OR NEW.context->'target' IS DISTINCT FROM target.plan->'target'
            OR NEW.context->>'source_rule_preparation_id'
                    IS DISTINCT FROM NEW.source_rule_preparation_id::text
            OR NEW.context->>'source_rule_preparation_hash' IS DISTINCT FROM source.result_hash
            OR NEW.context->>'source_rule_candidate_id'
                    IS DISTINCT FROM NEW.source_rule_candidate_id::text
            OR NEW.context->>'source_rule_approval_id'
                    IS DISTINCT FROM NEW.source_rule_approval_id::text
            OR NEW.context->>'source_rule_approval_hash' IS DISTINCT FROM approval.request_hash
            OR NEW.context->>'source_fact_preparation_id'
                    IS DISTINCT FROM facts.preparation_id::text
            OR NEW.context->>'source_fact_preparation_hash' IS DISTINCT FROM facts.result_hash
            OR NEW.context->>'source_fact_set_id' IS DISTINCT FROM source.fact_set_id::text
            OR NEW.context->>'task_id' IS DISTINCT FROM binding.task_id::text
            OR NEW.context->>'binding_id' IS DISTINCT FROM binding.binding_id::text
            OR NEW.context->>'check_id' IS DISTINCT FROM facts.check_id::text
            OR NEW.context->>'source_bundle_revision_id'
                    IS DISTINCT FROM binding.source_bundle_revision_id::text
        THEN RAISE EXCEPTION 'RULE_APPLICABILITY_CONTEXT_INVALID'; END IF;
        SELECT * INTO previous FROM investigation_rule_applicability WHERE
            target_plan_id=NEW.target_plan_id
                    AND source_rule_candidate_id=NEW.source_rule_candidate_id
            ORDER BY sequence DESC LIMIT 1;
        IF NEW.previous_decision_id IS DISTINCT FROM previous.decision_id
            OR NEW.sequence IS DISTINCT FROM COALESCE(previous.sequence,0)+1
        THEN RAISE EXCEPTION 'RULE_APPLICABILITY_PREDECESSOR_CHANGED'; END IF;
        IF jsonb_typeof(NEW.request->'evidence') IS DISTINCT FROM 'array'
            OR jsonb_typeof(NEW.evidence_snapshot) IS DISTINCT FROM 'array'
        THEN RAISE EXCEPTION 'RULE_APPLICABILITY_EVIDENCE_INVALID'; END IF;
        evidence_count := jsonb_array_length(NEW.request->'evidence');
        IF evidence_count > 20 OR evidence_count <> jsonb_array_length(NEW.evidence_snapshot)
            OR (NEW.request->>'outcome' <> 'NEEDS_ADJUDICATION' AND evidence_count=0)
        THEN RAISE EXCEPTION 'RULE_APPLICABILITY_EVIDENCE_INVALID'; END IF;
        FOR e IN SELECT value FROM jsonb_array_elements(NEW.evidence_snapshot) LOOP
            SELECT * INTO STRICT b FROM document_blocks WHERE block_id=(e->>'block_id')::uuid;
            SELECT * INTO STRICT member FROM source_bundle_members
                WHERE source_bundle_member_id=(e->>'member_id')::uuid;
            IF b.document_id IS DISTINCT FROM member.document_id
                OR member.source_bundle_revision_id
                    IS DISTINCT FROM binding.source_bundle_revision_id
                OR member.wma_task_id IS DISTINCT FROM binding.task_id
                OR member.provenance_kind IS DISTINCT FROM 'DIRECT_WMA'
                OR e->>'document_id' IS DISTINCT FROM b.document_id::text
                OR e->>'evidence_ref_id' IS DISTINCT FROM b.evidence_ref_id::text
                OR e->>'block_hash' IS DISTINCT FROM b.block_hash
                OR e->>'binding_hash' IS DISTINCT FROM b.evidence_binding_hash
                OR e->'locator' IS DISTINCT FROM b.structural_locator
                OR (length(e->>'quote') BETWEEN 1 AND 20000) IS DISTINCT FROM TRUE
                OR length(btrim(e->>'quote'))=0
                OR (strpos(b.canonical_text_or_value,e->>'quote') > 0) IS DISTINCT FROM TRUE
                OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(NEW.request->'evidence') q
                    WHERE q->>'member_id'=e->>'member_id' AND q->>'block_id'=e->>'block_id'
                    AND q->>'quote'=e->>'quote')
            THEN RAISE EXCEPTION 'RULE_APPLICABILITY_EVIDENCE_INVALID'; END IF;
        END LOOP;
        RETURN NEW;
    END $$;
    CREATE TRIGGER investigation_rule_applicability_guard BEFORE INSERT OR UPDATE OR DELETE
        ON investigation_rule_applicability FOR EACH ROW
        EXECUTE FUNCTION investigation_guard_rule_applicability();
    """)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM investigation_rule_applicability)")
    ):
        raise RuntimeError("RULE_APPLICABILITY_HISTORY_DOWNGRADE_REFUSED")
    op.drop_table("investigation_rule_applicability")
    op.execute("DROP FUNCTION investigation_guard_rule_applicability()")
