"""public_official_training_policy

Revision ID: 20260826_0032
Revises: 20260826_0031
Create Date: 2026-08-26 19:00:00
"""

# ruff: noqa: E501

from collections.abc import Sequence

from alembic import op

revision: str = "20260826_0032"
down_revision: str | None = "20260826_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    authority_condition = (
        "(NOT provider_policy.training_use OR "
        "provider_policy.allowed_classifications = "
        "ARRAY['PUBLIC_OFFICIAL_GENERAL']::text[])"
    )
    attempt_condition = (
        "(NOT policy.training_use OR policy.allowed_classifications = "
        "ARRAY['PUBLIC_OFFICIAL_GENERAL']::text[])"
    )
    _replace_authority_function(authority_condition)
    _replace_attempt_guard(attempt_condition)


def downgrade() -> None:
    _replace_authority_function("NOT provider_policy.training_use")
    _replace_attempt_guard("NOT policy.training_use")


def _replace_authority_function(training_condition: str) -> None:
    op.execute(
        rf"""
        CREATE OR REPLACE FUNCTION p9b_egress_decision_authorized_at(
            requested_decision_id uuid,
            authorization_time timestamptz
        ) RETURNS boolean LANGUAGE sql STABLE STRICT AS $$
            SELECT EXISTS (
                SELECT 1
                FROM p9b_egress_decisions AS decision
                JOIN source_bundle_revisions AS revision
                  ON revision.source_bundle_revision_id = decision.source_bundle_revision_id
                 AND revision.opportunity_id = decision.opportunity_id
                 AND revision.opportunity_version = decision.opportunity_version
                JOIN p9b_model_task_specs AS task
                  ON task.task_name = decision.task_spec_name
                 AND task.task_version = decision.task_spec_version
                JOIN p9b_source_egress_policy_snapshots AS source_policy
                  ON source_policy.snapshot_id = decision.source_policy_snapshot_id
                 AND source_policy.snapshot_hash = decision.source_policy_snapshot_hash
                 AND source_policy.source_bundle_revision_id = decision.source_bundle_revision_id
                JOIN p9b_provider_egress_policy_snapshots AS provider_policy
                  ON provider_policy.snapshot_id = decision.provider_policy_snapshot_id
                 AND provider_policy.snapshot_hash = decision.provider_policy_snapshot_hash
                 AND provider_policy.provider = decision.provider
                 AND provider_policy.region = decision.provider_region
                WHERE decision.egress_decision_id = requested_decision_id
                  AND decision.decision IN ('ALLOW', 'REDACT_AND_ALLOW')
                  AND decision.expires_at > authorization_time
                  AND (
                      revision.status = 'FROZEN'
                      OR (
                          revision.status = 'INVALIDATED'
                          AND authorization_time = decision.created_at
                          AND revision.frozen_at <= decision.created_at
                      )
                  )
                  AND source_policy.allows_egress
                  AND source_policy.valid_from <= authorization_time
                  AND source_policy.valid_until > authorization_time
                  AND source_policy.valid_until >= decision.expires_at
                  AND provider_policy.active
                  AND {training_condition}
                  AND (
                      NOT ('ZERO_RETENTION' = ANY(task.provider_capabilities))
                      OR provider_policy.zero_retention
                  )
                  AND provider_policy.valid_from <= authorization_time
                  AND provider_policy.valid_until > authorization_time
                  AND provider_policy.valid_until >= decision.expires_at
                  AND cardinality(decision.input_block_ids) > 0
                  AND cardinality(decision.input_block_ids) =
                      cardinality(decision.input_block_hashes)
                  AND cardinality(decision.input_block_ids) = (
                      SELECT count(DISTINCT input_id)
                      FROM unnest(decision.input_block_ids) AS input_id
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM unnest(decision.input_block_ids, decision.input_block_hashes)
                           AS requested(block_id, block_hash)
                      WHERE NOT EXISTS (
                          SELECT 1
                          FROM document_blocks AS block
                          JOIN source_bundle_members AS member
                            ON member.document_id = block.document_id
                           AND member.source_bundle_revision_id =
                               decision.source_bundle_revision_id
                          JOIN p9b_egress_block_classifications AS classification
                            ON classification.block_id = block.block_id
                           AND classification.block_hash = block.block_hash
                           AND classification.classification_version =
                               decision.data_classification_version
                          WHERE block.block_id = requested.block_id
                            AND block.block_hash = requested.block_hash
                            AND block.block_type = ANY(task.allowed_input_block_types)
                            AND NOT classification.contains_user_data
                            AND classification.classifications <@
                                provider_policy.allowed_classifications
                            AND NOT classification.classifications && ARRAY[
                                'PUBLIC_PERSON_LIST',
                                'RESTRICTED_BY_SOURCE_POLICY',
                                'UNSAFE_TO_EGRESS'
                            ]::text[]
                      )
                  )
            )
        $$
        """
    )


def _replace_attempt_guard(training_condition: str) -> None:
    op.execute(
        rf"""
        CREATE OR REPLACE FUNCTION p9b_guard_model_call_attempt()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            call_row p9b_model_calls%ROWTYPE;
            decision_row p9b_egress_decisions%ROWTYPE;
            task_row p9b_model_task_specs%ROWTYPE;
            revision_status text;
            authorization_time timestamptz := clock_timestamp();
            expected_attempt integer;
            authorized boolean := false;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'P9B_MODEL_CALL_ATTEMPT_HISTORY_IMMUTABLE';
            END IF;

            IF TG_OP = 'INSERT' THEN
                IF EXISTS (
                    SELECT 1 FROM p9b_model_call_finalizations
                    WHERE model_call_id = NEW.model_call_id
                ) THEN
                    RAISE EXCEPTION 'P9B_MODEL_CALL_ALREADY_FINALIZED';
                END IF;
                SELECT * INTO call_row FROM p9b_model_calls
                WHERE model_call_id = NEW.model_call_id;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'P9B_MODEL_CALL_NOT_FOUND';
                END IF;
                SELECT status INTO revision_status
                FROM source_bundle_revisions
                WHERE source_bundle_revision_id = call_row.source_bundle_revision_id
                FOR SHARE;
                PERFORM model_call_id FROM p9b_model_calls
                WHERE model_call_id = NEW.model_call_id FOR UPDATE;
                SELECT coalesce(max(attempt_number), 0) + 1 INTO expected_attempt
                FROM p9b_model_call_attempts WHERE model_call_id = NEW.model_call_id;
                IF NEW.attempt_number IS DISTINCT FROM expected_attempt THEN
                    RAISE EXCEPTION 'P9B_MODEL_CALL_ATTEMPT_SEQUENCE_MISMATCH';
                END IF;
                SELECT * INTO decision_row FROM p9b_egress_decisions
                WHERE egress_decision_id = call_row.egress_decision_id;
                SELECT * INTO task_row FROM p9b_model_task_specs
                WHERE task_name = call_row.task_spec_name
                  AND task_version = call_row.task_spec_version;
                IF expected_attempt > coalesce(task_row.max_attempts, 0) THEN
                    RAISE EXCEPTION 'P9B_MODEL_CALL_ATTEMPT_LIMIT_EXCEEDED';
                END IF;

                authorized := revision_status = 'FROZEN'
                    AND decision_row.decision IN ('ALLOW', 'REDACT_AND_ALLOW')
                    AND decision_row.expires_at > authorization_time
                    AND decision_row.source_bundle_revision_id = call_row.source_bundle_revision_id
                    AND decision_row.opportunity_id = call_row.opportunity_id
                    AND decision_row.opportunity_version = call_row.opportunity_version
                    AND decision_row.task_spec_name = call_row.task_spec_name
                    AND decision_row.task_spec_version = call_row.task_spec_version
                    AND decision_row.provider = call_row.provider
                    AND decision_row.input_block_ids = call_row.input_block_ids
                    AND decision_row.input_block_hashes = call_row.input_block_hashes
                    AND EXISTS (
                        SELECT 1 FROM p9b_source_egress_policy_snapshots AS policy
                        WHERE policy.snapshot_id = decision_row.source_policy_snapshot_id
                          AND policy.snapshot_hash = decision_row.source_policy_snapshot_hash
                          AND policy.source_bundle_revision_id = call_row.source_bundle_revision_id
                          AND policy.allows_egress
                          AND policy.valid_from <= authorization_time
                          AND policy.valid_until > authorization_time
                          AND policy.valid_until >= decision_row.expires_at
                    )
                    AND EXISTS (
                        SELECT 1 FROM p9b_provider_egress_policy_snapshots AS policy
                        WHERE policy.snapshot_id = decision_row.provider_policy_snapshot_id
                          AND policy.snapshot_hash = decision_row.provider_policy_snapshot_hash
                          AND policy.provider = call_row.provider
                          AND policy.region = decision_row.provider_region
                          AND policy.active
                          AND {training_condition}
                          AND policy.retention_class = call_row.retention_class
                          AND (
                              NOT ('ZERO_RETENTION' = ANY(task_row.provider_capabilities))
                              OR policy.zero_retention
                          )
                          AND policy.valid_from <= authorization_time
                          AND policy.valid_until > authorization_time
                          AND policy.valid_until >= decision_row.expires_at
                    );

                NEW.egress_decision_id := call_row.egress_decision_id;
                NEW.source_bundle_revision_id := call_row.source_bundle_revision_id;
                NEW.source_policy_snapshot_id := decision_row.source_policy_snapshot_id;
                NEW.source_policy_snapshot_hash := decision_row.source_policy_snapshot_hash;
                NEW.provider_policy_snapshot_id := decision_row.provider_policy_snapshot_id;
                NEW.provider_policy_snapshot_hash := decision_row.provider_policy_snapshot_hash;
                NEW.authorization_checked_at := authorization_time;
                NEW.created_at := authorization_time;
                NEW.provider_http_status := NULL;
                NEW.error_code := NULL;
                NEW.provider_response_id := NULL;
                NEW.raw_response_reference_kind := NULL;
                NEW.raw_response_storage_bucket := NULL;
                NEW.raw_response_object_key := NULL;
                NEW.raw_response_sha256 := NULL;
                NEW.response_hash := NULL;
                NEW.parsed_result_hash := NULL;
                NEW.input_tokens := NULL;
                NEW.output_tokens := NULL;
                NEW.cache_read_tokens := NULL;
                NEW.cache_write_tokens := NULL;
                NEW.cost_status := NULL;
                NEW.monetary_cost := NULL;
                NEW.latency_ms := NULL;
                IF authorized THEN
                    NEW.authorization_decision := 'AUTHORIZED';
                    NEW.authorization_reason_code := 'AUTHORIZED';
                    NEW.provider_invocation_allowed := true;
                    NEW.dispatch_deadline := authorization_time
                        + make_interval(secs => task_row.timeout_ms::double precision / 1000.0);
                    NEW.outcome := NULL;
                    NEW.completed_at := NULL;
                ELSE
                    NEW.authorization_decision := 'AUTHORITY_REJECTED';
                    NEW.authorization_reason_code := 'P9B_EGRESS_AUTHORITY_EXPIRED_OR_MISMATCH';
                    NEW.provider_invocation_allowed := false;
                    NEW.dispatch_deadline := NULL;
                    NEW.outcome := 'AUTHORITY_REJECTED';
                    NEW.completed_at := authorization_time;
                END IF;
                RETURN NEW;
            END IF;

            IF OLD.outcome IS NOT NULL THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_RESULT_ALREADY_TERMINAL';
            END IF;
            IF EXISTS (
                SELECT 1 FROM p9b_model_call_finalizations
                WHERE model_call_id = OLD.model_call_id
            ) THEN
                RAISE EXCEPTION 'P9B_MODEL_CALL_ALREADY_FINALIZED';
            END IF;
            IF OLD.authorization_decision <> 'AUTHORIZED' OR NOT OLD.provider_invocation_allowed THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_PROVIDER_INVOCATION_NOT_AUTHORIZED';
            END IF;
            IF ROW(
                NEW.model_call_id, NEW.attempt_number, NEW.attempt_id,
                NEW.egress_decision_id, NEW.source_bundle_revision_id,
                NEW.source_policy_snapshot_id, NEW.source_policy_snapshot_hash,
                NEW.provider_policy_snapshot_id, NEW.provider_policy_snapshot_hash,
                NEW.authorization_decision, NEW.authorization_reason_code,
                NEW.authorization_checked_at, NEW.dispatch_deadline,
                NEW.provider_invocation_allowed, NEW.created_at
            ) IS DISTINCT FROM ROW(
                OLD.model_call_id, OLD.attempt_number, OLD.attempt_id,
                OLD.egress_decision_id, OLD.source_bundle_revision_id,
                OLD.source_policy_snapshot_id, OLD.source_policy_snapshot_hash,
                OLD.provider_policy_snapshot_id, OLD.provider_policy_snapshot_hash,
                OLD.authorization_decision, OLD.authorization_reason_code,
                OLD.authorization_checked_at, OLD.dispatch_deadline,
                OLD.provider_invocation_allowed, OLD.created_at
            ) THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_AUTHORIZATION_IMMUTABLE';
            END IF;
            IF NEW.outcome IS NULL OR NEW.outcome = 'AUTHORITY_REJECTED' THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_RESULT_REQUIRED';
            END IF;

            NEW.completed_at := clock_timestamp();
            IF coalesce(p9b_gateway_contains_credential_material(NEW.provider_response_id), false)
               OR coalesce(p9b_gateway_contains_credential_material(NEW.raw_response_storage_bucket), false)
               OR coalesce(p9b_gateway_contains_credential_material(NEW.raw_response_object_key), false)
               OR coalesce(p9b_gateway_contains_credential_material(NEW.error_code), false)
            THEN
                NEW.outcome := 'RESPONSE_METADATA_REJECTED';
                NEW.error_code := 'CREDENTIAL_MATERIAL_REJECTED';
                NEW.provider_response_id := NULL;
                NEW.raw_response_reference_kind := NULL;
                NEW.raw_response_storage_bucket := NULL;
                NEW.raw_response_object_key := NULL;
                NEW.raw_response_sha256 := NULL;
                NEW.response_hash := NULL;
                NEW.parsed_result_hash := NULL;
            END IF;

            IF NEW.provider_http_status IS NOT NULL
               AND NEW.provider_http_status NOT BETWEEN 100 AND 599 THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_HTTP_STATUS_INVALID';
            END IF;
            IF NEW.raw_response_reference_kind IS NULL THEN
                IF NEW.provider_response_id IS NOT NULL
                   OR NEW.raw_response_storage_bucket IS NOT NULL
                   OR NEW.raw_response_object_key IS NOT NULL
                   OR NEW.raw_response_sha256 IS NOT NULL THEN
                    RAISE EXCEPTION 'P9B_ATTEMPT_RAW_RESPONSE_REFERENCE_INVALID';
                END IF;
            ELSIF NEW.raw_response_reference_kind = 'PROVIDER_RESPONSE_ID' THEN
                IF NEW.provider_response_id IS NULL
                   OR NEW.raw_response_storage_bucket IS NOT NULL
                   OR NEW.raw_response_object_key IS NOT NULL
                   OR NEW.raw_response_sha256 IS NOT NULL THEN
                    RAISE EXCEPTION 'P9B_ATTEMPT_RAW_RESPONSE_REFERENCE_INVALID';
                END IF;
            ELSIF NEW.raw_response_reference_kind = 'INTERNAL_OBJECT' THEN
                IF NEW.provider_response_id IS NOT NULL
                   OR NEW.raw_response_storage_bucket IS NULL
                   OR NEW.raw_response_object_key IS NULL
                   OR NEW.raw_response_sha256 IS NULL THEN
                    RAISE EXCEPTION 'P9B_ATTEMPT_RAW_RESPONSE_REFERENCE_INVALID';
                END IF;
            ELSE
                RAISE EXCEPTION 'P9B_ATTEMPT_RAW_RESPONSE_REFERENCE_INVALID';
            END IF;
            IF NEW.outcome = 'SUCCEEDED' THEN
                IF NEW.raw_response_reference_kind IS NULL
                   OR NEW.response_hash IS NULL
                   OR NEW.parsed_result_hash IS NULL
                   OR NEW.error_code IS NOT NULL THEN
                    RAISE EXCEPTION 'P9B_ATTEMPT_SUCCESS_SHAPE_INVALID';
                END IF;
            ELSIF NEW.parsed_result_hash IS NOT NULL THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_FAILURE_SHAPE_INVALID';
            END IF;
            IF NEW.input_tokens IS NULL OR NEW.input_tokens < 0
               OR NEW.output_tokens IS NULL OR NEW.output_tokens < 0
               OR NEW.cache_read_tokens IS NULL OR NEW.cache_read_tokens < 0
               OR NEW.cache_write_tokens IS NULL OR NEW.cache_write_tokens < 0
               OR NEW.latency_ms IS NULL OR NEW.latency_ms < 0 THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_USAGE_INVALID';
            END IF;
            IF (NEW.cost_status = 'REPORTED') IS DISTINCT FROM (NEW.monetary_cost IS NOT NULL)
               OR NEW.cost_status NOT IN ('REPORTED', 'COST_NOT_REPORTED')
               OR NEW.monetary_cost < 0 THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_COST_INVALID';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
