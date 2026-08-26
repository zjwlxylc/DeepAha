"""local_human_test_run_idempotency_compat

Revision ID: 20260826_0031
Revises: 20260826_0030
Create Date: 2026-08-26 18:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260826_0031"
down_revision: str | None = "20260826_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Early local-only 0030 databases predated these two run idempotency columns.
    # Fresh 0030 databases already contain them, so every statement is conditional.
    op.execute(
        "ALTER TABLE local_human_test_runs "
        "ADD COLUMN IF NOT EXISTS idempotency_key varchar(128)"
    )
    op.execute(
        "ALTER TABLE local_human_test_runs "
        "ADD COLUMN IF NOT EXISTS request_hash varchar(64)"
    )
    op.execute(
        "UPDATE local_human_test_runs SET "
        "idempotency_key = coalesce(idempotency_key, 'legacy-' || run_id::text), "
        "request_hash = coalesce(request_hash, encode(digest(" 
        "convert_to('legacy:' || run_id::text, 'UTF8'), 'sha256'), 'hex')) "
        "WHERE idempotency_key IS NULL OR request_hash IS NULL"
    )
    op.execute(
        "ALTER TABLE local_human_test_runs "
        "ALTER COLUMN idempotency_key SET NOT NULL, "
        "ALTER COLUMN request_hash SET NOT NULL"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'local_human_test_runs'::regclass
                  AND conname = 'ck_local_human_test_runs_idempotency_key_nonempty'
            ) THEN
                ALTER TABLE local_human_test_runs ADD CONSTRAINT
                    ck_local_human_test_runs_idempotency_key_nonempty
                    CHECK (length(btrim(idempotency_key)) >= 1);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'local_human_test_runs'::regclass
                  AND conname = 'ck_local_human_test_runs_request_hash_format'
            ) THEN
                ALTER TABLE local_human_test_runs ADD CONSTRAINT
                    ck_local_human_test_runs_request_hash_format
                    CHECK (request_hash ~ '^[0-9a-f]{64}$');
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'local_human_test_runs'::regclass
                  AND conname = 'uq_local_human_test_runs_creator_idempotency'
            ) THEN
                ALTER TABLE local_human_test_runs ADD CONSTRAINT
                    uq_local_human_test_runs_creator_idempotency
                    UNIQUE (created_by_reviewer_id, idempotency_key);
            END IF;
        END;
        $$
        """
    )


def downgrade() -> None:
    # These columns are part of the canonical 0030 schema. Downgrading to 0030
    # therefore preserves them and only removes the compatibility revision marker.
    pass
