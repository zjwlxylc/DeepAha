"""Immutable derived unit snapshots; trusted reads must reconstruct their contents."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260908_0042"
down_revision = "20260908_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_unit_plans",
        sa.Column("plan_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "rule_preparation_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_rule_preparations.rule_preparation_id"),
            nullable=False,
        ),
        sa.Column(
            "unit_version_id",
            sa.Uuid(),
            sa.ForeignKey("opportunity_unit_versions.opportunity_unit_version_id"),
            nullable=False,
        ),
        sa.Column("contract_version", sa.String(64), nullable=False),
        sa.Column("adapter_version", sa.String(128), nullable=False),
        sa.Column("plan", JSONB(), nullable=False),
        sa.Column("plan_hash", sa.String(64), nullable=False),
        sa.Column("context", JSONB(), nullable=False),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column(
            "reviewer_id", sa.Uuid(), sa.ForeignKey("reviewer_accounts.reviewer_id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "rule_preparation_id",
            "contract_version",
            "adapter_version",
            name="uq_investigation_unit_plan_version",
        ),
    )
    op.execute("""
    CREATE FUNCTION investigation_guard_unit_plan() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        prep investigation_rule_preparations; facts investigation_fact_preparations;
        binding investigation_bindings; uv opportunity_unit_versions;
    BEGIN
        IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'INVESTIGATION_UNIT_PLAN_IMMUTABLE'; END IF;
        SELECT * INTO STRICT prep FROM investigation_rule_preparations
            WHERE rule_preparation_id = NEW.rule_preparation_id;
        SELECT * INTO STRICT facts FROM investigation_fact_preparations
            WHERE preparation_id = prep.fact_preparation_id;
        SELECT * INTO STRICT binding FROM investigation_bindings
            WHERE binding_id = facts.binding_id;
        PERFORM 1 FROM investigation_tasks WHERE task_id = binding.task_id FOR UPDATE;
        SELECT * INTO STRICT uv FROM opportunity_unit_versions
            WHERE opportunity_unit_version_id = NEW.unit_version_id;
        IF uuid_extract_version(NEW.plan_id) IS DISTINCT FROM 7
            OR NOT EXISTS (SELECT 1 FROM reviewer_accounts WHERE reviewer_id = NEW.reviewer_id
                AND active AND NOT synthetic AND roles ? 'VALIDATION_REVIEWER'
                AND allowed_purposes ? 'OPPORTUNITY_FACT_VALIDATION')
            OR binding.binding_id IS DISTINCT FROM (SELECT binding_id FROM investigation_bindings
                WHERE task_id = binding.task_id ORDER BY sequence DESC LIMIT 1)
            OR NOT EXISTS (SELECT 1 FROM investigation_tasks WHERE task_id = binding.task_id
                AND status = 'APPROVED' AND delivery_hash = binding.delivery_hash)
            OR NOT EXISTS (SELECT 1 FROM opportunities WHERE opportunity_id = uv.opportunity_id
                AND current_version = uv.opportunity_version)
            OR NOT EXISTS (SELECT 1 FROM opportunity_units
                WHERE opportunity_unit_id = uv.opportunity_unit_id
                AND current_version_id = uv.opportunity_unit_version_id)
            OR NOT EXISTS (SELECT 1 FROM versioned_verified_fact_sets
                WHERE verified_fact_set_id = prep.fact_set_id AND status = 'ACTIVE')
            OR NOT EXISTS (SELECT 1 FROM source_bundle_revisions WHERE
                source_bundle_revision_id = binding.source_bundle_revision_id AND status = 'FROZEN')
            OR prep.result->'target'->>'target_scope' IS DISTINCT FROM 'UNIT'
            OR prep.result->'target'->>'opportunity_unit_version_id'
                IS DISTINCT FROM NEW.unit_version_id::text
        THEN RAISE EXCEPTION 'INVESTIGATION_UNIT_PLAN_TARGET_INVALID'; END IF;
        IF NEW.plan_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.plan), 'UTF8')), 'hex')
            OR NEW.context_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.context), 'UTF8')), 'hex')
            OR NEW.plan->>'qualification_plan_id' IS DISTINCT FROM NEW.plan_id::text
            OR NEW.plan->>'contract_version' IS DISTINCT FROM NEW.contract_version
            OR NEW.context->>'adapter_version' IS DISTINCT FROM NEW.adapter_version
            OR NEW.context->>'rule_preparation_hash' IS DISTINCT FROM prep.result_hash
            OR NEW.context->>'fact_preparation_hash' IS DISTINCT FROM facts.result_hash
            OR NEW.context->>'check_id' IS DISTINCT FROM facts.check_id::text
            OR NEW.plan->'manifest'->>'preparation_id' IS DISTINCT FROM facts.preparation_id::text
            OR NEW.plan->'manifest'->>'preparation_sha256' IS DISTINCT FROM facts.result_hash
            OR NEW.plan->'target' IS DISTINCT FROM jsonb_build_object(
                'opportunity_id', uv.opportunity_id, 'opportunity_version', uv.opportunity_version,
                'unit_id', uv.opportunity_unit_id, 'unit_version', uv.version,
                'unit_version_id', uv.opportunity_unit_version_id)
            OR NEW.plan->'manifest'->'target' IS DISTINCT FROM NEW.plan->'target'
        THEN RAISE EXCEPTION 'INVESTIGATION_UNIT_PLAN_CONTEXT_MISMATCH'; END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER investigation_unit_plan_guard BEFORE INSERT OR UPDATE OR DELETE
        ON investigation_unit_plans FOR EACH ROW EXECUTE FUNCTION investigation_guard_unit_plan();
    """)


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM investigation_unit_plans)")):
        raise RuntimeError("INVESTIGATION_UNIT_PLAN_HISTORY_DOWNGRADE_REFUSED")
    op.drop_table("investigation_unit_plans")
    op.execute("DROP FUNCTION investigation_guard_unit_plan()")
