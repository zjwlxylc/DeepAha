"""Immutable frozen relationship proposals; no approval or qualification activation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260910_0050"
down_revision = "20260910_0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_relation_proposals",
        sa.Column("proposal_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("investigation_tasks.task_id"), nullable=False
        ),
        sa.Column(
            "target_plan_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_unit_plans.plan_id"),
            nullable=False,
        ),
        sa.Column(
            "producer_id", sa.Uuid(), sa.ForeignKey("reviewer_accounts.reviewer_id"), nullable=False
        ),
        sa.Column("request_key_hash", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("request", JSONB(), nullable=False),
        sa.Column("storage_version", sa.String(64), nullable=False),
        sa.Column("payload_text", sa.Text(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column(
            "projection",
            JSONB(),
            sa.Computed("payload_text::jsonb", persisted=True),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "target_plan_id", "producer_id", "request_key_hash", name="uq_relation_proposal_request"
        ),
        sa.CheckConstraint(
            "storage_version = 'adjudication-frozen-json/1.0.0'",
            name="storage_version",
        ),
        sa.CheckConstraint(
            "payload_sha256 = encode(sha256(convert_to(payload_text,'UTF8')),'hex')",
            name="payload_bytes",
        ),
    )
    op.execute("""
    CREATE FUNCTION investigation_guard_relation_proposal() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE p jsonb; base investigation_unit_plans; actual_task uuid;
    BEGIN
        IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'RELATION_PROPOSAL_IMMUTABLE'; END IF;
        p := NEW.payload_text::jsonb->'proposal';
        PERFORM 1 FROM investigation_tasks WHERE task_id=NEW.task_id FOR UPDATE;
        SELECT * INTO STRICT base FROM investigation_unit_plans WHERE plan_id=NEW.target_plan_id;
        SELECT f.task_id INTO STRICT actual_task FROM investigation_rule_preparations r
            JOIN investigation_fact_preparations f ON f.preparation_id=r.fact_preparation_id
            WHERE r.rule_preparation_id=base.rule_preparation_id;
        PERFORM 1 FROM reviewer_accounts WHERE reviewer_id=NEW.producer_id FOR SHARE;
        IF actual_task IS DISTINCT FROM NEW.task_id
            OR uuid_extract_version(NEW.proposal_id) IS DISTINCT FROM 7
            OR NEW.request_key_hash !~ '^[0-9a-f]{64}$'
            OR NEW.request_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.request),'UTF8')),'hex')
            OR NOT isfinite(NEW.created_at) OR NEW.created_at < base.created_at
            OR NOT EXISTS (SELECT 1 FROM reviewer_accounts WHERE reviewer_id=NEW.producer_id
                AND active AND NOT synthetic AND roles ? 'VALIDATION_REVIEWER'
                AND allowed_purposes ? 'OPPORTUNITY_FACT_VALIDATION')
            OR NEW.payload_text::jsonb->'decisions' IS DISTINCT FROM '[]'::jsonb
            OR p->>'proposal_id' IS DISTINCT FROM NEW.proposal_id::text
            OR p->>'producer_id' IS DISTINCT FROM NEW.producer_id::text
            OR (p->>'created_at')::timestamptz IS DISTINCT FROM NEW.created_at
            OR p->>'contract_version' IS DISTINCT FROM 'cross-level-adjudication/1.0.0'
            OR p->>'scope' IS DISTINCT FROM 'CROSS_LEVEL_ADJUDICATION_REVIEW_ONLY'
            OR p#>>'{source_review,dependencies,group,snapshot,base_v2,plan_id}'
                IS DISTINCT FROM NEW.target_plan_id::text
            OR p#>>'{source_review,dependencies,group,dependencies,group_source,source,task_id}'
                IS DISTINCT FROM NEW.task_id::text
            OR p#>'{source_review,dependencies,group,snapshot,base_v2,plan}'
                IS DISTINCT FROM base.plan
            OR p#>'{source_review,dependencies,group,snapshot,base_v2,context}'
                IS DISTINCT FROM base.context
            OR NEW.request->>'target_plan_id' IS DISTINCT FROM NEW.target_plan_id::text
            OR NEW.request->>'expected_review_hash' IS DISTINCT FROM p->>'source_review_hash'
            OR NEW.request->'condition_ids' IS DISTINCT FROM p->'condition_ids'
            OR NEW.request->'relation' IS DISTINCT FROM p->'relation'
            OR NEW.request->'displaced_condition_ids' IS DISTINCT FROM p->'displaced_condition_ids'
            OR NEW.request->'reason' IS DISTINCT FROM p->'reason'
            THEN RAISE EXCEPTION 'RELATION_PROPOSAL_BINDING_INVALID'; END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER relation_proposal_guard BEFORE INSERT OR UPDATE OR DELETE
        ON investigation_relation_proposals FOR EACH ROW
        EXECUTE FUNCTION investigation_guard_relation_proposal();
    """)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM investigation_relation_proposals)")
    ):
        raise RuntimeError("RELATION_PROPOSAL_HISTORY_DOWNGRADE_REFUSED")
    op.drop_table("investigation_relation_proposals")
    op.execute("DROP FUNCTION investigation_guard_relation_proposal()")
