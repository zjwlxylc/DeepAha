"""p9b_replacement_unknown_reconciliation

Revision ID: 20260825_0028
Revises: 20260825_0027
Create Date: 2026-08-25 18:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260825_0028"
down_revision: str | None = "20260825_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE FUNCTION p9b_reconcile_stale_model_call_attempts(
            requested_model_call_id uuid DEFAULT NULL
        ) RETURNS TABLE(model_call_id uuid) LANGUAGE plpgsql AS $$
        DECLARE
            stale record;
        BEGIN
            FOR stale IN
                SELECT attempt.model_call_id, attempt.attempt_number
                FROM p9b_model_call_attempts AS attempt
                LEFT JOIN p9b_model_call_finalizations AS finalization
                  ON finalization.model_call_id = attempt.model_call_id
                WHERE attempt.outcome IS NULL
                  AND attempt.authorization_decision = 'AUTHORIZED'
                  AND attempt.provider_invocation_allowed
                  AND attempt.dispatch_deadline <= clock_timestamp()
                  AND finalization.model_call_id IS NULL
                  AND (
                      requested_model_call_id IS NULL
                      OR attempt.model_call_id = requested_model_call_id
                  )
                ORDER BY attempt.model_call_id, attempt.attempt_number
                FOR UPDATE OF attempt SKIP LOCKED
            LOOP
                UPDATE p9b_model_call_attempts
                SET outcome = 'PROVIDER_OUTCOME_UNKNOWN',
                    provider_http_status = NULL,
                    error_code = 'DISPATCH_DEADLINE_EXCEEDED',
                    provider_response_id = NULL,
                    raw_response_reference_kind = NULL,
                    raw_response_storage_bucket = NULL,
                    raw_response_object_key = NULL,
                    raw_response_sha256 = NULL,
                    response_hash = NULL,
                    parsed_result_hash = NULL,
                    input_tokens = 0,
                    output_tokens = 0,
                    cache_read_tokens = 0,
                    cache_write_tokens = 0,
                    cost_status = 'COST_NOT_REPORTED',
                    monetary_cost = NULL,
                    latency_ms = least(
                        2147483647,
                        greatest(
                            0,
                            floor(extract(epoch FROM (clock_timestamp() - created_at)) * 1000)
                        )
                    )::integer,
                    completed_at = clock_timestamp()
                WHERE p9b_model_call_attempts.model_call_id = stale.model_call_id
                  AND attempt_number = stale.attempt_number;

                INSERT INTO p9b_model_call_finalizations (model_call_id)
                VALUES (stale.model_call_id);
                model_call_id := stale.model_call_id;
                RETURN NEXT;
            END LOOP;
        END;
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION p9b_reconcile_stale_model_call_attempts(uuid)")
