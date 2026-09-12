"""Keep local dispatch authorization separate from immutable execution evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260912_0055"
down_revision = "20260911_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigation_tasks",
        sa.Column(
            "dispatch_context",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("investigation_tasks", "dispatch_context")
