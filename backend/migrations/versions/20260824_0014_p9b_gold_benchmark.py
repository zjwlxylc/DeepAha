"""p9b_gold_benchmark

Revision ID: 20260824_0014
Revises: 20260824_0013
Create Date: 2026-08-24 20:10:00
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260824_0014"
down_revision: str | None = "20260824_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gold_annotation_tasks",
        sa.Column("gold_annotation_task_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_manifest_id", sa.Uuid(), nullable=False),
        sa.Column("entry_id", sa.String(length=128), nullable=False),
        sa.Column("partition", sa.String(length=32), nullable=False),
        sa.Column("answer_access_class", sa.String(length=32), nullable=False),
        sa.Column("annotator_identity", sa.Text(), nullable=False),
        sa.Column("verifier_identity", sa.Text(), nullable=False),
        sa.Column("adjudicator_identity", sa.Text(), nullable=False),
        sa.Column("curator_identity", sa.Text(), nullable=False),
        sa.Column(
            "role_attestation_references",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("blind_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blind_ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("split_seed_reference", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(gold_annotation_task_id) = 7",
            name=op.f("ck_gold_annotation_tasks_task_id_uuid7"),
        ),
        sa.CheckConstraint(
            "partition in ('CALIBRATION', 'DEVELOPMENT', 'VALIDATION', 'LOCKED_ACCEPTANCE')",
            name=op.f("ck_gold_annotation_tasks_partition_values"),
        ),
        sa.CheckConstraint(
            "status in ('BLIND_REVIEW', 'READY_FOR_ADJUDICATION', 'FROZEN', 'INVALIDATED')",
            name=op.f("ck_gold_annotation_tasks_status_values"),
        ),
        sa.CheckConstraint(
            "annotator_identity like 'human:%' and verifier_identity like 'human:%' and adjudicator_identity like 'human:%' and curator_identity like 'human:%'",
            name=op.f("ck_gold_annotation_tasks_human_responsibility_identities"),
        ),
        sa.CheckConstraint(
            "annotator_identity <> verifier_identity and annotator_identity <> adjudicator_identity and annotator_identity <> curator_identity and verifier_identity <> adjudicator_identity and verifier_identity <> curator_identity and adjudicator_identity <> curator_identity",
            name=op.f("ck_gold_annotation_tasks_role_identity_separation"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(role_attestation_references) = 'object' and role_attestation_references ?& array['ANNOTATOR', 'VERIFIER', 'ADJUDICATOR', 'CURATOR']",
            name=op.f("ck_gold_annotation_tasks_role_attestations_complete"),
        ),
        sa.CheckConstraint(
            "(status = 'BLIND_REVIEW' and blind_ended_at is null) or (status <> 'BLIND_REVIEW' and blind_ended_at is not null)",
            name=op.f("ck_gold_annotation_tasks_blind_state"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_manifest_id", "entry_id"],
            ["dataset_manifest_entries.dataset_manifest_id", "dataset_manifest_entries.entry_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_manifest_id", "partition", "answer_access_class"],
            [
                "dataset_manifests.dataset_manifest_id",
                "dataset_manifests.partition",
                "dataset_manifests.answer_access_class",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("gold_annotation_task_id", name=op.f("pk_gold_annotation_tasks")),
        sa.UniqueConstraint(
            "dataset_manifest_id",
            "entry_id",
            name=op.f("uq_gold_annotation_tasks_dataset_manifest_id"),
        ),
    )
    op.create_table(
        "gold_annotation_submissions",
        sa.Column("gold_annotation_submission_id", sa.Uuid(), nullable=False),
        sa.Column("gold_annotation_task_id", sa.Uuid(), nullable=False),
        sa.Column("review_role", sa.String(length=16), nullable=False),
        sa.Column("actor_identity", sa.Text(), nullable=False),
        sa.Column("assisted_calibration", sa.Boolean(), nullable=False),
        sa.Column("judgments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(gold_annotation_submission_id) = 7",
            name=op.f("ck_gold_annotation_submissions_submission_id_uuid7"),
        ),
        sa.CheckConstraint(
            "review_role in ('ANNOTATOR', 'VERIFIER')",
            name=op.f("ck_gold_annotation_submissions_review_role_values"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(judgments) = 'array' and jsonb_array_length(judgments) >= 1",
            name=op.f("ck_gold_annotation_submissions_judgments_nonempty"),
        ),
        sa.ForeignKeyConstraint(
            ["gold_annotation_task_id"],
            ["gold_annotation_tasks.gold_annotation_task_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "gold_annotation_submission_id", name=op.f("pk_gold_annotation_submissions")
        ),
        sa.UniqueConstraint(
            "gold_annotation_task_id",
            "review_role",
            name=op.f("uq_gold_annotation_submissions_gold_annotation_task_id"),
        ),
        sa.UniqueConstraint(
            "gold_annotation_submission_id",
            "gold_annotation_task_id",
            name="uq_gold_submissions_task_binding",
        ),
    )
    op.create_table(
        "gold_adjudication_decisions",
        sa.Column("gold_adjudication_decision_id", sa.Uuid(), nullable=False),
        sa.Column("gold_annotation_task_id", sa.Uuid(), nullable=False),
        sa.Column("annotation_submission_id", sa.Uuid(), nullable=False),
        sa.Column("verification_submission_id", sa.Uuid(), nullable=False),
        sa.Column("adjudicator_identity", sa.Text(), nullable=False),
        sa.Column("judgments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(gold_adjudication_decision_id) = 7",
            name=op.f("ck_gold_adjudication_decisions_decision_id_uuid7"),
        ),
        sa.CheckConstraint(
            "annotation_submission_id <> verification_submission_id",
            name=op.f("ck_gold_adjudication_decisions_distinct_submissions"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(judgments) = 'array' and jsonb_array_length(judgments) >= 1",
            name=op.f("ck_gold_adjudication_decisions_judgments_nonempty"),
        ),
        sa.ForeignKeyConstraint(
            ["gold_annotation_task_id"],
            ["gold_annotation_tasks.gold_annotation_task_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["annotation_submission_id", "gold_annotation_task_id"],
            [
                "gold_annotation_submissions.gold_annotation_submission_id",
                "gold_annotation_submissions.gold_annotation_task_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["verification_submission_id", "gold_annotation_task_id"],
            [
                "gold_annotation_submissions.gold_annotation_submission_id",
                "gold_annotation_submissions.gold_annotation_task_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "gold_adjudication_decision_id", name=op.f("pk_gold_adjudication_decisions")
        ),
        sa.UniqueConstraint(
            "gold_annotation_task_id",
            name=op.f("uq_gold_adjudication_decisions_gold_annotation_task_id"),
        ),
        sa.UniqueConstraint(
            "gold_adjudication_decision_id",
            "gold_annotation_task_id",
            name="uq_gold_adjudication_task_binding",
        ),
    )
    op.create_table(
        "gold_truth_versions",
        sa.Column("gold_truth_version_id", sa.Uuid(), nullable=False),
        sa.Column("gold_annotation_task_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("supersedes_truth_version_id", sa.Uuid(), nullable=True),
        sa.Column("revision_reason_code", sa.String(length=128), nullable=False),
        sa.Column("annotation_submission_id", sa.Uuid(), nullable=False),
        sa.Column("verification_submission_id", sa.Uuid(), nullable=False),
        sa.Column("adjudication_decision_id", sa.Uuid(), nullable=True),
        sa.Column("curator_identity", sa.Text(), nullable=False),
        sa.Column("judgments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("truth_hash", sa.String(length=64), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(gold_truth_version_id) = 7",
            name=op.f("ck_gold_truth_versions_truth_version_id_uuid7"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_gold_truth_versions_positive_version")),
        sa.CheckConstraint(
            "(version = 1 and supersedes_truth_version_id is null) or (version > 1 and supersedes_truth_version_id is not null)",
            name=op.f("ck_gold_truth_versions_version_chain_shape"),
        ),
        sa.CheckConstraint(
            "annotation_submission_id <> verification_submission_id",
            name=op.f("ck_gold_truth_versions_distinct_submissions"),
        ),
        sa.CheckConstraint(
            "truth_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_gold_truth_versions_truth_hash_format"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(judgments) = 'array' and jsonb_array_length(judgments) >= 1",
            name=op.f("ck_gold_truth_versions_judgments_nonempty"),
        ),
        sa.ForeignKeyConstraint(
            ["gold_annotation_task_id"],
            ["gold_annotation_tasks.gold_annotation_task_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["annotation_submission_id", "gold_annotation_task_id"],
            [
                "gold_annotation_submissions.gold_annotation_submission_id",
                "gold_annotation_submissions.gold_annotation_task_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["verification_submission_id", "gold_annotation_task_id"],
            [
                "gold_annotation_submissions.gold_annotation_submission_id",
                "gold_annotation_submissions.gold_annotation_task_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["adjudication_decision_id", "gold_annotation_task_id"],
            [
                "gold_adjudication_decisions.gold_adjudication_decision_id",
                "gold_adjudication_decisions.gold_annotation_task_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_truth_version_id"],
            ["gold_truth_versions.gold_truth_version_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("gold_truth_version_id", name=op.f("pk_gold_truth_versions")),
        sa.UniqueConstraint(
            "gold_annotation_task_id",
            name=op.f("uq_gold_truth_versions_gold_annotation_task_id"),
        ),
        sa.UniqueConstraint("truth_hash", name=op.f("uq_gold_truth_versions_truth_hash")),
    )
    op.create_table(
        "gold_answer_access_events",
        sa.Column("gold_answer_access_event_id", sa.Uuid(), nullable=False),
        sa.Column("gold_annotation_task_id", sa.Uuid(), nullable=False),
        sa.Column("requester_identity", sa.Text(), nullable=False),
        sa.Column("requester_role", sa.String(length=24), nullable=False),
        sa.Column("access_kind", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(gold_answer_access_event_id) = 7",
            name=op.f("ck_gold_answer_access_events_access_event_id_uuid7"),
        ),
        sa.CheckConstraint(
            "requester_role in ('ANNOTATOR', 'VERIFIER', 'ADJUDICATOR', 'CURATOR', 'AI_ENGINEER', 'EVALUATOR')",
            name=op.f("ck_gold_answer_access_events_requester_role_values"),
        ),
        sa.CheckConstraint(
            "access_kind in ('GOLD_ANSWER', 'ADJUDICATION_REASON', 'MODEL_COMPARISON')",
            name=op.f("ck_gold_answer_access_events_access_kind_values"),
        ),
        sa.CheckConstraint(
            "decision in ('GRANTED', 'DENIED')",
            name=op.f("ck_gold_answer_access_events_decision_values"),
        ),
        sa.ForeignKeyConstraint(
            ["gold_annotation_task_id"],
            ["gold_annotation_tasks.gold_annotation_task_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "gold_answer_access_event_id", name=op.f("pk_gold_answer_access_events")
        ),
    )
    _create_guards()


def downgrade() -> None:
    connection = op.get_bind()
    populated = connection.execute(
        sa.text(
            "select exists(select 1 from gold_annotation_tasks) or "
            "exists(select 1 from gold_annotation_submissions) or "
            "exists(select 1 from gold_adjudication_decisions) or "
            "exists(select 1 from gold_truth_versions) or "
            "exists(select 1 from gold_answer_access_events)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("cannot downgrade P9-B Gold history after governed records exist")
    _drop_guards()
    op.drop_table("gold_answer_access_events")
    op.drop_table("gold_truth_versions")
    op.drop_table("gold_adjudication_decisions")
    op.drop_table("gold_annotation_submissions")
    op.drop_table("gold_annotation_tasks")


def _create_guards() -> None:
    for table in (
        "gold_annotation_tasks",
        "gold_annotation_submissions",
        "gold_adjudication_decisions",
        "gold_truth_versions",
        "gold_answer_access_events",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_immutable_guard BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION p9b_insert_only_guard()"
        )
    op.execute(
        """
        CREATE FUNCTION p9b_gold_task_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.status <> 'BLIND_REVIEW' OR NEW.blind_ended_at IS NOT NULL OR NOT EXISTS (
                SELECT 1 FROM dataset_manifests manifest
                WHERE manifest.dataset_manifest_id = NEW.dataset_manifest_id
                  AND manifest.status = 'FROZEN'
            ) THEN
                RAISE EXCEPTION 'GOLD_TASK_REQUIRES_FROZEN_MANIFEST_AND_BLIND_START';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER gold_annotation_tasks_insert_guard BEFORE INSERT ON gold_annotation_tasks "
        "FOR EACH ROW EXECUTE FUNCTION p9b_gold_task_insert_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION p9b_gold_submission_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE task gold_annotation_tasks%ROWTYPE;
        BEGIN
            SELECT * INTO task FROM gold_annotation_tasks
            WHERE gold_annotation_task_id = NEW.gold_annotation_task_id;
            IF NOT FOUND OR
               (NEW.review_role = 'ANNOTATOR' AND NEW.actor_identity <> task.annotator_identity) OR
               (NEW.review_role = 'VERIFIER' AND NEW.actor_identity <> task.verifier_identity) OR
               (NEW.assisted_calibration AND task.partition <> 'CALIBRATION') THEN
                RAISE EXCEPTION 'GOLD_SUBMISSION_ROLE_OR_ASSISTANCE_MISMATCH';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER gold_annotation_submissions_insert_guard BEFORE INSERT ON "
        "gold_annotation_submissions FOR EACH ROW EXECUTE FUNCTION "
        "p9b_gold_submission_insert_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION p9b_gold_adjudication_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE task gold_annotation_tasks%ROWTYPE;
        DECLARE annotation gold_annotation_submissions%ROWTYPE;
        DECLARE verification gold_annotation_submissions%ROWTYPE;
        BEGIN
            SELECT * INTO task FROM gold_annotation_tasks
            WHERE gold_annotation_task_id = NEW.gold_annotation_task_id;
            SELECT * INTO annotation FROM gold_annotation_submissions
            WHERE gold_annotation_submission_id = NEW.annotation_submission_id;
            SELECT * INTO verification FROM gold_annotation_submissions
            WHERE gold_annotation_submission_id = NEW.verification_submission_id;
            IF NOT FOUND OR NEW.adjudicator_identity <> task.adjudicator_identity OR
               annotation.review_role <> 'ANNOTATOR' OR verification.review_role <> 'VERIFIER' OR
               annotation.gold_annotation_task_id <> task.gold_annotation_task_id OR
               verification.gold_annotation_task_id <> task.gold_annotation_task_id THEN
                RAISE EXCEPTION 'GOLD_ADJUDICATION_INDEPENDENCE_OR_BINDING_MISMATCH';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER gold_adjudication_decisions_insert_guard BEFORE INSERT ON "
        "gold_adjudication_decisions FOR EACH ROW EXECUTE FUNCTION "
        "p9b_gold_adjudication_insert_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION p9b_gold_truth_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE task gold_annotation_tasks%ROWTYPE;
        DECLARE annotation gold_annotation_submissions%ROWTYPE;
        DECLARE verification gold_annotation_submissions%ROWTYPE;
        DECLARE adjudication gold_adjudication_decisions%ROWTYPE;
        DECLARE predecessor gold_truth_versions%ROWTYPE;
        BEGIN
            SELECT * INTO task FROM gold_annotation_tasks
            WHERE gold_annotation_task_id = NEW.gold_annotation_task_id;
            SELECT * INTO annotation FROM gold_annotation_submissions
            WHERE gold_annotation_submission_id = NEW.annotation_submission_id;
            SELECT * INTO verification FROM gold_annotation_submissions
            WHERE gold_annotation_submission_id = NEW.verification_submission_id;
            IF NOT FOUND OR NEW.curator_identity <> task.curator_identity OR
               annotation.review_role <> 'ANNOTATOR' OR verification.review_role <> 'VERIFIER' THEN
                RAISE EXCEPTION 'GOLD_TRUTH_INDEPENDENCE_OR_BINDING_MISMATCH';
            END IF;
            IF annotation.judgments <> verification.judgments THEN
                SELECT * INTO adjudication FROM gold_adjudication_decisions
                WHERE gold_adjudication_decision_id = NEW.adjudication_decision_id;
                IF NOT FOUND OR adjudication.gold_annotation_task_id <> NEW.gold_annotation_task_id OR
                   adjudication.annotation_submission_id <> NEW.annotation_submission_id OR
                   adjudication.verification_submission_id <> NEW.verification_submission_id OR
                   adjudication.judgments <> NEW.judgments THEN
                    RAISE EXCEPTION 'CONFLICTING_GOLD_REQUIRES_BOUND_ADJUDICATION';
                END IF;
            ELSIF NEW.adjudication_decision_id IS NULL AND NEW.judgments <> annotation.judgments THEN
                RAISE EXCEPTION 'AGREED_GOLD_TRUTH_MUST_MATCH_SUBMISSIONS';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM gold_answer_access_events access_event
                WHERE access_event.gold_annotation_task_id = NEW.gold_annotation_task_id
                  AND access_event.requester_identity = NEW.curator_identity
                  AND access_event.requester_role = 'CURATOR'
                  AND access_event.access_kind = 'GOLD_ANSWER'
                  AND access_event.decision = 'GRANTED'
                  AND access_event.reason_code =
                      'BLIND_REVIEW_COMPLETED_AFTER_TWO_SUBMISSIONS'
                  AND access_event.occurred_at = NEW.frozen_at
            ) THEN
                RAISE EXCEPTION 'GOLD_TRUTH_REQUIRES_BLIND_END_AUDIT';
            END IF;
            IF NEW.version > 1 THEN
                SELECT * INTO predecessor FROM gold_truth_versions
                WHERE gold_truth_version_id = NEW.supersedes_truth_version_id;
                IF NOT FOUND OR predecessor.gold_annotation_task_id = NEW.gold_annotation_task_id OR
                   predecessor.version + 1 <> NEW.version THEN
                    RAISE EXCEPTION 'GOLD_TRUTH_VERSION_CHAIN_MISMATCH';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER gold_truth_versions_insert_guard BEFORE INSERT ON gold_truth_versions "
        "FOR EACH ROW EXECUTE FUNCTION p9b_gold_truth_insert_guard()"
    )


def _drop_guards() -> None:
    for trigger, table in (
        ("gold_annotation_tasks_insert_guard", "gold_annotation_tasks"),
        ("gold_annotation_submissions_insert_guard", "gold_annotation_submissions"),
        ("gold_adjudication_decisions_insert_guard", "gold_adjudication_decisions"),
        ("gold_truth_versions_insert_guard", "gold_truth_versions"),
    ):
        op.execute(f"DROP TRIGGER {trigger} ON {table}")
    for table in (
        "gold_annotation_tasks",
        "gold_annotation_submissions",
        "gold_adjudication_decisions",
        "gold_truth_versions",
        "gold_answer_access_events",
    ):
        op.execute(f"DROP TRIGGER {table}_immutable_guard ON {table}")
    for function in (
        "p9b_gold_truth_insert_guard",
        "p9b_gold_adjudication_insert_guard",
        "p9b_gold_submission_insert_guard",
        "p9b_gold_task_insert_guard",
    ):
        op.execute(f"DROP FUNCTION {function}()")
