"""phase5_public_catalog

Revision ID: 20260822_0005
Revises: 20260822_0004
Create Date: 2026-08-22 10:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_0005"
down_revision: str | None = "20260822_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the version-bound public catalog governance allowlist."""
    op.create_table(
        "public_catalog_entries",
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("collection_kind", sa.String(length=24), nullable=False),
        sa.Column("dataset_id", sa.String(length=128), nullable=False),
        sa.Column("dataset_version", sa.String(length=64), nullable=False),
        sa.Column("content_use_basis", sa.String(length=32), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "opportunity_version >= 1",
            name=op.f("ck_public_catalog_entries_positive_opportunity_version"),
        ),
        sa.CheckConstraint(
            "collection_kind in ('REAL_GOLD', 'LICENSE_SAFE_FIXTURE')",
            name=op.f("ck_public_catalog_entries_collection_kind_values"),
        ),
        sa.CheckConstraint(
            "content_use_basis in ('OPEN_LICENSE', 'OFFICIAL_PUBLIC_ACCESS', 'LINK_ONLY')",
            name=op.f("ck_public_catalog_entries_content_use_basis_values"),
        ),
        sa.CheckConstraint(
            "length(btrim(dataset_id)) >= 1",
            name=op.f("ck_public_catalog_entries_dataset_id_nonempty"),
        ),
        sa.CheckConstraint(
            "length(btrim(dataset_version)) >= 1",
            name=op.f("ck_public_catalog_entries_dataset_version_nonempty"),
        ),
        sa.CheckConstraint(
            "length(btrim(reviewed_by)) >= 1",
            name=op.f("ck_public_catalog_entries_reviewed_by_nonempty"),
        ),
        sa.CheckConstraint(
            "last_verified_at >= approved_at",
            name=op.f("ck_public_catalog_entries_verification_timestamp_order"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            name=op.f("fk_public_catalog_entries_opportunity_id_opportunity_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "opportunity_id",
            name=op.f("pk_public_catalog_entries"),
        ),
    )


def downgrade() -> None:
    """Refuse to discard publication governance evidence."""
    connection = op.get_bind()
    contains_rows = connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM public_catalog_entries LIMIT 1)")
    ).scalar_one()
    if contains_rows:
        raise RuntimeError("cannot downgrade Phase 5 while publication governance rows exist")
    op.drop_table("public_catalog_entries")
