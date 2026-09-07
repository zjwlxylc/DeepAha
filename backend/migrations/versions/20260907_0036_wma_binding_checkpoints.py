"""Persist partial WMA creation and freeze resolved execution/binding evidence."""

from alembic import op

revision = "20260907_0036"
down_revision = "20260907_0035"
branch_labels = None
depends_on = None


def _replace_guard(*, separate_checkpoints: bool) -> None:
    remote_guard = (
        """
          IF OLD.runtime_id IS NOT NULL AND OLD.runtime_id IS DISTINCT FROM NEW.runtime_id THEN
            RAISE EXCEPTION 'investigation runtime binding is immutable';
          END IF;
          IF OLD.remote_session_id IS NOT NULL AND
             OLD.remote_session_id IS DISTINCT FROM NEW.remote_session_id THEN
            RAISE EXCEPTION 'investigation session binding is immutable';
          END IF;
          IF NEW.remote_session_id IS NOT NULL AND NEW.runtime_id IS NULL THEN
            RAISE EXCEPTION 'investigation session requires a runtime';
          END IF;
          IF OLD.execution <> '{}'::jsonb AND
             (OLD.execution - 'recovery' - 'binding') IS DISTINCT FROM
             (NEW.execution - 'recovery' - 'binding') THEN
            RAISE EXCEPTION 'investigation execution is immutable';
          END IF;
          IF OLD.execution ? 'binding' AND
             (OLD.execution -> 'binding') IS DISTINCT FROM (NEW.execution -> 'binding') THEN
            RAISE EXCEPTION 'investigation binding evidence is immutable';
          END IF;
        """
        if separate_checkpoints
        else """
          IF OLD.runtime_id IS NOT NULL AND
             ROW(OLD.runtime_id, OLD.remote_session_id) IS DISTINCT FROM
             ROW(NEW.runtime_id, NEW.remote_session_id) THEN
            RAISE EXCEPTION 'investigation runtime binding is immutable';
          END IF;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION guard_investigation_task() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF ROW(OLD.task_id, OLD.source_id, OLD.endpoint_id, OLD.created_by,
                 OLD.request_key_hash, OLD.request_hash, OLD.request, OLD.source_snapshot,
                 OLD.contract, OLD.contract_hash, OLD.created_at) IS DISTINCT FROM
             ROW(NEW.task_id, NEW.source_id, NEW.endpoint_id, NEW.created_by,
                 NEW.request_key_hash, NEW.request_hash, NEW.request, NEW.source_snapshot,
                 NEW.contract, NEW.contract_hash, NEW.created_at) THEN
            RAISE EXCEPTION 'investigation request is immutable';
          END IF;
          IF OLD.result_objects <> '{}'::jsonb AND OLD.result_objects <> NEW.result_objects THEN
            RAISE EXCEPTION 'investigation manifest is immutable';
          END IF;
        """
        + remote_guard
        + """
          IF OLD.delivery_hash IS NOT NULL AND
             ROW(OLD.delivery_hash, OLD.delivery) IS DISTINCT FROM
             ROW(NEW.delivery_hash, NEW.delivery) THEN
            RAISE EXCEPTION 'investigation delivery is immutable';
          END IF;
          IF OLD.review IS NOT NULL AND
             ROW(OLD.review, OLD.reviewer_id, OLD.review_key_hash, OLD.review_hash, OLD.status)
             IS DISTINCT FROM
             ROW(NEW.review, NEW.reviewer_id, NEW.review_key_hash, NEW.review_hash, NEW.status) THEN
            RAISE EXCEPTION 'investigation review is immutable';
          END IF;
          RETURN NEW;
        END $$;
        """
    )


def upgrade() -> None:
    _replace_guard(separate_checkpoints=True)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM investigation_tasks
                     WHERE runtime_id IS NOT NULL AND remote_session_id IS NULL) THEN
            RAISE EXCEPTION 'resolve partial WMA bindings before downgrade';
          END IF;
        END $$;
    """)
    _replace_guard(separate_checkpoints=False)
