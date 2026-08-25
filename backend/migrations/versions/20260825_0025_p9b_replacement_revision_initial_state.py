"""p9b_replacement_revision_initial_state

Revision ID: 20260825_0025
Revises: 20260825_0024
Create Date: 2026-08-25 15:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260825_0025"
down_revision: str | None = "20260825_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE FUNCTION p9b_guard_bundle_revision_initial_state()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.status IS DISTINCT FROM 'DRAFT' OR NEW.frozen_at IS NOT NULL THEN
                RAISE EXCEPTION 'P9B_BUNDLE_INITIAL_STATE_MISMATCH';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER source_bundle_revisions_guard_insert BEFORE INSERT ON "
        "source_bundle_revisions FOR EACH ROW EXECUTE FUNCTION "
        "p9b_guard_bundle_revision_initial_state()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER source_bundle_revisions_guard_insert ON source_bundle_revisions")
    op.execute("DROP FUNCTION p9b_guard_bundle_revision_initial_state()")
