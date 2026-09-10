"""Immutable announcement scope snapshots with complete dependency revisions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260909_0044"
down_revision = "20260908_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_announcement_snapshots",
        sa.Column("snapshot_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "base_plan_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_unit_plans.plan_id"),
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
        sa.Column("dependencies", JSONB(), nullable=False),
        sa.Column("dependencies_hash", sa.String(64), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column(
            "reviewer_id", sa.Uuid(), sa.ForeignKey("reviewer_accounts.reviewer_id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "base_plan_id",
            "contract_version",
            "adapter_version",
            "dependencies_hash",
            name="uq_investigation_announcement_snapshot_inputs",
        ),
    )
    op.execute("""
    CREATE FUNCTION investigation_guard_announcement_snapshot() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE
        base investigation_unit_plans; prep investigation_rule_preparations;
        facts investigation_fact_preparations; binding investigation_bindings;
        uv opportunity_unit_versions; row_data jsonb; app jsonb;
        decision investigation_rule_applicability; expected_count int;
    BEGIN
        IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'ANNOUNCEMENT_SNAPSHOT_IMMUTABLE'; END IF;
        SELECT * INTO STRICT base FROM investigation_unit_plans WHERE plan_id=NEW.base_plan_id;
        SELECT * INTO STRICT prep FROM investigation_rule_preparations
            WHERE rule_preparation_id=base.rule_preparation_id;
        SELECT * INTO STRICT facts FROM investigation_fact_preparations
            WHERE preparation_id=prep.fact_preparation_id;
        SELECT * INTO STRICT binding FROM investigation_bindings WHERE binding_id=facts.binding_id;
        PERFORM 1 FROM investigation_tasks WHERE task_id=binding.task_id FOR UPDATE;
        SELECT * INTO STRICT uv FROM opportunity_unit_versions
            WHERE opportunity_unit_version_id=NEW.unit_version_id;
        IF uuid_extract_version(NEW.snapshot_id) IS DISTINCT FROM 7
            OR NEW.unit_version_id IS DISTINCT FROM base.unit_version_id
            OR base.contract_version IS DISTINCT FROM 'unit-qualification/2.0.0'
            OR base.adapter_version IS DISTINCT FROM 'investigation-unit-snapshot/1.0.0'
            OR NOT EXISTS (SELECT 1 FROM reviewer_accounts WHERE reviewer_id=NEW.reviewer_id
                AND active AND NOT synthetic AND roles ? 'VALIDATION_REVIEWER'
                AND allowed_purposes ? 'OPPORTUNITY_FACT_VALIDATION')
            OR binding.binding_id IS DISTINCT FROM (SELECT binding_id FROM investigation_bindings
                WHERE task_id=binding.task_id ORDER BY sequence DESC LIMIT 1)
            OR NOT EXISTS (SELECT 1 FROM investigation_tasks WHERE task_id=binding.task_id
                AND status='APPROVED' AND delivery_hash=binding.delivery_hash)
            OR NOT EXISTS (SELECT 1 FROM opportunities WHERE opportunity_id=uv.opportunity_id
                AND current_version=uv.opportunity_version)
            OR NOT EXISTS (SELECT 1 FROM opportunity_units
                WHERE opportunity_unit_id=uv.opportunity_unit_id
                AND current_version_id=uv.opportunity_unit_version_id)
            OR NOT EXISTS (SELECT 1 FROM versioned_verified_fact_sets
                WHERE verified_fact_set_id=prep.fact_set_id AND status='ACTIVE')
            OR NOT EXISTS (SELECT 1 FROM source_bundle_revisions WHERE
                source_bundle_revision_id=binding.source_bundle_revision_id AND status='FROZEN')
        THEN RAISE EXCEPTION 'ANNOUNCEMENT_SNAPSHOT_TARGET_INVALID'; END IF;
        IF NEW.contract_version IS DISTINCT FROM 'investigation-announcement-snapshot/1.0.0'
            OR NEW.adapter_version IS DISTINCT FROM 'investigation-announcement-adapter/1.0.0'
            OR NEW.dependencies_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.dependencies), 'UTF8')), 'hex')
            OR NEW.snapshot_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.snapshot), 'UTF8')), 'hex')
            OR NEW.dependencies->>'base_plan_id' IS DISTINCT FROM base.plan_id::text
            OR NEW.dependencies->>'base_plan_hash' IS DISTINCT FROM base.plan_hash
            OR NEW.dependencies->>'base_context_hash' IS DISTINCT FROM base.context_hash
            OR NEW.snapshot->>'contract_version' IS DISTINCT FROM NEW.contract_version
            OR NEW.snapshot->>'adapter_version' IS DISTINCT FROM NEW.adapter_version
            OR NEW.snapshot->>'scope' IS DISTINCT FROM 'DERIVED_SCOPE_SNAPSHOT_ONLY'
            OR NEW.snapshot->>'overall_qualification' IS DISTINCT FROM 'UNCERTAIN'
            OR NEW.snapshot->'base_v2'->>'plan_id' IS DISTINCT FROM base.plan_id::text
            OR NEW.snapshot->'base_v2'->'plan' IS DISTINCT FROM base.plan
            OR NEW.snapshot->'base_v2'->>'plan_hash' IS DISTINCT FROM base.plan_hash
            OR NEW.snapshot->'base_v2'->'context' IS DISTINCT FROM base.context
            OR NEW.snapshot->'base_v2'->>'context_hash' IS DISTINCT FROM base.context_hash
            OR jsonb_typeof(NEW.snapshot->'announcement_conditions') IS DISTINCT FROM 'array'
        THEN RAISE EXCEPTION 'ANNOUNCEMENT_SNAPSHOT_CONTENT_INVALID'; END IF;
        SELECT count(*) INTO expected_count
            FROM jsonb_array_elements(base.plan->'manifest'->'conditions') c
            WHERE c->>'scope'='ANNOUNCEMENT';
        IF jsonb_array_length(NEW.snapshot->'announcement_conditions') <> expected_count
            OR (SELECT count(DISTINCT c->'condition'->>'condition_id') FROM
                jsonb_array_elements(NEW.snapshot->'announcement_conditions') c) <> expected_count
        THEN RAISE EXCEPTION 'ANNOUNCEMENT_SNAPSHOT_DENOMINATOR_INVALID'; END IF;
        FOR row_data IN SELECT value
            FROM jsonb_array_elements(NEW.snapshot->'announcement_conditions') LOOP
            IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(base.plan->'manifest'->'conditions') c
                WHERE c->>'scope'='ANNOUNCEMENT' AND c=row_data->'condition')
                OR (row_data->>'disposition' IN ('INHERITED','EXCLUDED','UNRESOLVED'))
                    IS DISTINCT FROM TRUE
            THEN RAISE EXCEPTION 'ANNOUNCEMENT_SNAPSHOT_DENOMINATOR_INVALID'; END IF;
            app := row_data->'applicability';
            IF app IS NULL OR app='null'::jsonb THEN
                IF row_data->>'disposition' <> 'UNRESOLVED'
                THEN RAISE EXCEPTION 'ANNOUNCEMENT_SNAPSHOT_APPLICABILITY_INVALID'; END IF;
                CONTINUE;
            END IF;
            SELECT * INTO STRICT decision FROM investigation_rule_applicability
                WHERE decision_id=(app->>'decision_id')::uuid;
            IF decision.target_plan_id IS DISTINCT FROM base.plan_id
                OR decision.decision_id IS DISTINCT FROM (SELECT decision_id
                    FROM investigation_rule_applicability WHERE target_plan_id=base.plan_id
                    AND source_rule_candidate_id=decision.source_rule_candidate_id
                    ORDER BY sequence DESC LIMIT 1)
                OR app->'request' IS DISTINCT FROM decision.request
                OR app->'context' IS DISTINCT FROM decision.context
                OR app->'evidence_snapshot' IS DISTINCT FROM decision.evidence_snapshot
                OR (row_data->>'disposition'='INHERITED'
                    AND decision.request->>'outcome' <> 'APPLIES')
                OR (row_data->>'disposition'='EXCLUDED'
                    AND decision.request->>'outcome' <> 'DOES_NOT_APPLY')
                OR (row_data->>'disposition' <> 'UNRESOLVED' AND (
                    row_data->'source_rule'->>'rule_id'
                        IS DISTINCT FROM decision.source_rule_candidate_id::text
                    OR encode(sha256(convert_to(
                        p9b_canonical_json(row_data->'source_rule'), 'UTF8')), 'hex')
                        IS DISTINCT FROM decision.context->>'source_rule_sha256'))
            THEN RAISE EXCEPTION 'ANNOUNCEMENT_SNAPSHOT_APPLICABILITY_INVALID'; END IF;
        END LOOP;
        RETURN NEW;
    END $$;
    CREATE TRIGGER investigation_announcement_snapshot_guard BEFORE INSERT OR UPDATE OR DELETE
        ON investigation_announcement_snapshots FOR EACH ROW
        EXECUTE FUNCTION investigation_guard_announcement_snapshot();
    """)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM investigation_announcement_snapshots)")
    ):
        raise RuntimeError("ANNOUNCEMENT_SNAPSHOT_HISTORY_DOWNGRADE_REFUSED")
    op.drop_table("investigation_announcement_snapshots")
    op.execute("DROP FUNCTION investigation_guard_announcement_snapshot()")
