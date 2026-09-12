"""Record explicit, revocable exclusions of investigation materials without a parser.

A material whose media type no registered parser supports can never reach the
machine-evidence block the downstream gates require. Reviewers may exclude such a
material in writing instead: every exclusion is its own row so that who excluded
what, when and why stays auditable, and a later revocation is recorded instead of
deleting history. ``delivery_hash`` binds the decision to one delivery only.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260911_0053"
down_revision = "20260911_0052"
branch_labels = None
depends_on = None

TABLE = "investigation_document_exclusions"
ACTIVE_INDEX = "uq_investigation_document_exclusions_active"
DELIVERY_INDEX = "ix_investigation_document_exclusions_task_id_delivery_hash"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("exclusion_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.String(256), nullable=False),
        sa.Column("raw_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("media_type", sa.String(256), nullable=False),
        sa.Column("delivery_hash", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("excluded_by", sa.Uuid(), nullable=False),
        sa.Column("excluded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("exclusion_id"),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["investigation_tasks.task_id"],
            name="fk_investigation_document_exclusions_task",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "material_id"],
            ["investigation_materials.task_id", "investigation_materials.material_id"],
            name="fk_investigation_document_exclusions_material",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["excluded_by"],
            ["reviewer_accounts.reviewer_id"],
            name="fk_investigation_document_exclusions_excluded_by",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by"],
            ["reviewer_accounts.reviewer_id"],
            name="fk_investigation_document_exclusions_revoked_by",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("uuid_extract_version(exclusion_id) = 7", name="id_uuid7"),
        sa.CheckConstraint("delivery_hash ~ '^[0-9a-f]{64}$'", name="hash_format"),
        sa.CheckConstraint("length(btrim(reason)) between 8 and 2000", name="reason_length"),
        sa.CheckConstraint(
            "revoked_at is null or (revoked_reason is not null "
            "and length(btrim(revoked_reason)) between 8 and 2000)",
            name="revoked_reason",
        ),
    )
    # Only one exclusion may be effective at a time; revoked rows stay as history.
    op.create_index(
        ACTIVE_INDEX,
        TABLE,
        ["task_id", "material_id", "delivery_hash"],
        unique=True,
        postgresql_where=sa.text("revoked_at is null"),
    )
    op.create_index(DELIVERY_INDEX, TABLE, ["task_id", "delivery_hash"])


def downgrade() -> None:
    if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {TABLE})")):
        raise RuntimeError("Cannot discard investigation document exclusion history")
    op.drop_index(DELIVERY_INDEX, table_name=TABLE)
    op.drop_index(ACTIVE_INDEX, table_name=TABLE)
    op.drop_table(TABLE)
