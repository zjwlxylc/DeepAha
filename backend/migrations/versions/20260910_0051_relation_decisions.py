"""Append-only independently reviewed relationship decisions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260910_0051"
down_revision = "20260910_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_relation_decisions",
        sa.Column("decision_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_relation_proposals.proposal_id"),
            nullable=False,
        ),
        sa.Column(
            "previous_decision_id",
            sa.Uuid(),
            sa.ForeignKey("investigation_relation_decisions.decision_id"),
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "reviewer_id", sa.Uuid(), sa.ForeignKey("reviewer_accounts.reviewer_id"), nullable=False
        ),
        sa.Column("request_key_hash", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("request", JSONB(), nullable=False),
        sa.Column("payload_text", sa.Text(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column(
            "projection",
            JSONB(),
            sa.Computed("payload_text::jsonb", persisted=True),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("proposal_id", "sequence", name="uq_relation_decision_sequence"),
        sa.UniqueConstraint(
            "proposal_id", "reviewer_id", "request_key_hash", name="uq_relation_decision_request"
        ),
        sa.CheckConstraint(
            "payload_sha256 = encode(sha256(convert_to(payload_text,'UTF8')),'hex')",
            name="payload_bytes",
        ),
    )
    op.execute("""
    CREATE FUNCTION investigation_guard_relation_decision() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE p investigation_relation_proposals; last_row investigation_relation_decisions; d jsonb;
    BEGIN
        IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'RELATION_DECISION_IMMUTABLE'; END IF;
        SELECT * INTO STRICT p FROM investigation_relation_proposals
            WHERE proposal_id=NEW.proposal_id;
        PERFORM 1 FROM investigation_tasks WHERE task_id=p.task_id FOR UPDATE;
        PERFORM 1 FROM reviewer_accounts WHERE reviewer_id=NEW.reviewer_id FOR SHARE;
        SELECT * INTO last_row FROM investigation_relation_decisions
            WHERE proposal_id=NEW.proposal_id ORDER BY sequence DESC LIMIT 1;
        d := NEW.payload_text::jsonb;
        IF NEW.reviewer_id = p.producer_id
            OR NOT EXISTS (SELECT 1 FROM reviewer_accounts WHERE reviewer_id=NEW.reviewer_id
                AND active AND NOT synthetic AND roles ? 'VALIDATION_REVIEWER'
                AND allowed_purposes ? 'OPPORTUNITY_FACT_VALIDATION')
            OR uuid_extract_version(NEW.decision_id) IS DISTINCT FROM 7
            OR NEW.sequence IS DISTINCT FROM coalesce(last_row.sequence,0)+1
            OR NEW.previous_decision_id IS DISTINCT FROM last_row.decision_id
            OR NOT isfinite(NEW.created_at) OR NEW.created_at < p.created_at
            OR NEW.created_at < last_row.created_at
            OR NEW.request_key_hash !~ '^[0-9a-f]{64}$'
            OR NEW.request_hash IS DISTINCT FROM
                encode(sha256(convert_to(p9b_canonical_json(NEW.request),'UTF8')),'hex')
            OR d->>'decision_id' IS DISTINCT FROM NEW.decision_id::text
            OR d->>'proposal_id' IS DISTINCT FROM NEW.proposal_id::text
            OR d->>'reviewer_id' IS DISTINCT FROM NEW.reviewer_id::text
            OR d->>'previous_decision_id' IS DISTINCT FROM NEW.previous_decision_id::text
            OR (d->>'sequence')::integer IS DISTINCT FROM NEW.sequence
            OR (d->>'created_at')::timestamptz IS DISTINCT FROM NEW.created_at
            OR coalesce(d->>'proposal_hash','') !~ '^[0-9a-f]{64}$'
            OR coalesce(d->>'decision','') NOT IN ('APPROVE','REJECT','NEEDS_ADJUDICATION')
            OR length(btrim(coalesce(d->>'reason',''))) NOT BETWEEN 1 AND 2000
            OR (d->>'decision'='APPROVE' AND p.projection#>>'{proposal,relation}'='UNRESOLVED')
            OR NEW.request->>'proposal_id' IS DISTINCT FROM NEW.proposal_id::text
            OR NEW.request->>'expected_proposal_payload_hash' IS DISTINCT FROM p.payload_sha256
            OR NEW.request->>'previous_decision_id' IS DISTINCT FROM NEW.previous_decision_id::text
            OR NEW.request->>'decision' IS DISTINCT FROM d->>'decision'
            OR NEW.request->>'reason' IS DISTINCT FROM d->>'reason'
            THEN RAISE EXCEPTION 'RELATION_DECISION_BINDING_INVALID'; END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER relation_decision_guard BEFORE INSERT OR UPDATE OR DELETE
        ON investigation_relation_decisions FOR EACH ROW
        EXECUTE FUNCTION investigation_guard_relation_decision();
    """)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM investigation_relation_decisions)")
    ):
        raise RuntimeError("RELATION_DECISION_HISTORY_DOWNGRADE_REFUSED")
    op.drop_table("investigation_relation_decisions")
    op.execute("DROP FUNCTION investigation_guard_relation_decision()")
