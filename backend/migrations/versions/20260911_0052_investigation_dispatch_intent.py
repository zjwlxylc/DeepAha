"""Persistent operator dispatch intent for a queued investigation task."""

import sqlalchemy as sa
from alembic import op

revision = "20260911_0052"
down_revision = "20260910_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigation_tasks",
        sa.Column("dispatch_requested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("investigation_tasks", "dispatch_requested_at")
