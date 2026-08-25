"""p9b_replacement_gold_attestation_integrity

Revision ID: 20260825_0024
Revises: 20260825_0023
Create Date: 2026-08-24 23:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0024"
down_revision: str | None = "20260825_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gold_role_attestations",
        sa.Column("gold_role_attestation_id", sa.Uuid(), nullable=False),
        sa.Column("review_role", sa.String(length=16), nullable=False),
        sa.Column("subject_identity", sa.Text(), nullable=False),
        sa.Column("attestation_authority_identity", sa.Text(), nullable=False),
        sa.Column("verification_method", sa.String(length=40), nullable=False),
        sa.Column("external_evidence_reference", sa.Text(), nullable=False),
        sa.Column("external_evidence_sha256", sa.String(length=64), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "uuid_extract_version(gold_role_attestation_id) = 7",
            name=op.f("ck_gold_role_attestations_attestation_id_uuid7"),
        ),
        sa.CheckConstraint(
            "review_role in ('ANNOTATOR', 'VERIFIER', 'ADJUDICATOR', 'CURATOR')",
            name=op.f("ck_gold_role_attestations_review_role_values"),
        ),
        sa.CheckConstraint(
            "subject_identity like 'human:%' and "
            "attestation_authority_identity <> subject_identity",
            name=op.f("ck_gold_role_attestations_independent_human_subject"),
        ),
        sa.CheckConstraint(
            "verification_method in ('EXTERNAL_HUMAN_DIRECTORY', "
            "'SIGNED_ACCOUNT_ASSERTION', 'IN_PERSON_ACCOUNTABILITY_RECORD')",
            name=op.f("ck_gold_role_attestations_verification_method_values"),
        ),
        sa.CheckConstraint(
            "external_evidence_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_gold_role_attestations_evidence_hash_format"),
        ),
        sa.CheckConstraint(
            "external_evidence_reference not like 'synthetic:%' and "
            "external_evidence_reference not like 'synthetic-fixture:%' and "
            "external_evidence_reference not like 'claimed-human:%'",
            name=op.f("ck_gold_role_attestations_external_evidence_required"),
        ),
        sa.CheckConstraint(
            "expires_at is null or expires_at > verified_at",
            name=op.f("ck_gold_role_attestations_attestation_window"),
        ),
        sa.PrimaryKeyConstraint(
            "gold_role_attestation_id",
            name=op.f("pk_gold_role_attestations"),
        ),
        sa.UniqueConstraint(
            "review_role",
            "subject_identity",
            "external_evidence_sha256",
            name=op.f("uq_gold_role_attestations_review_role"),
        ),
    )
    op.execute(
        "CREATE TRIGGER gold_role_attestations_immutable_guard BEFORE UPDATE OR DELETE "
        "ON gold_role_attestations FOR EACH ROW EXECUTE FUNCTION p9b_insert_only_guard()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text("select exists(select 1 from gold_role_attestations limit 1)")
    ).scalar_one():
        raise RuntimeError("cannot downgrade P9-B Gold attestations after evidence exists")
    op.execute("DROP TRIGGER gold_role_attestations_immutable_guard ON gold_role_attestations")
    op.drop_table("gold_role_attestations")
