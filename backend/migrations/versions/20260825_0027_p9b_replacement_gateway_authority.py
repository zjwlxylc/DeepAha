"""p9b_replacement_gateway_authority

Revision ID: 20260825_0027
Revises: 20260825_0026
Create Date: 2026-08-25 17:00:00
"""

# ruff: noqa: E501

from collections.abc import Sequence

from alembic import op

revision: str = "20260825_0027"
down_revision: str | None = "20260825_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _create_complete_egress_authority_function()
    _create_egress_decision_guards()
    _create_model_call_insert_guard()
    _create_attempt_authority_guard()
    _preflight_existing_authority()


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER p9b_model_call_attempts_z_complete_authority "
        "ON p9b_model_call_attempts"
    )
    op.execute("DROP TRIGGER p9b_model_calls_guard_insert ON p9b_model_calls")
    op.execute(
        "DROP TRIGGER p9b_egress_decisions_validate_insert ON p9b_egress_decisions"
    )
    op.execute("DROP TRIGGER p9b_egress_decisions_stamp_insert ON p9b_egress_decisions")
    op.execute("DROP FUNCTION p9b_guard_complete_attempt_authority()")
    op.execute("DROP FUNCTION p9b_guard_model_call_insert()")
    op.execute("DROP FUNCTION p9b_validate_egress_decision_insert()")
    op.execute("DROP FUNCTION p9b_stamp_egress_decision_insert()")
    op.execute("DROP FUNCTION p9b_egress_decision_authorized_at(uuid, timestamptz)")


def _create_complete_egress_authority_function() -> None:
    op.execute(
        r"""
        CREATE FUNCTION p9b_egress_decision_authorized_at(
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
                  AND NOT provider_policy.training_use
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


def _create_egress_decision_guards() -> None:
    op.execute(
        r"""
        CREATE FUNCTION p9b_stamp_egress_decision_insert()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM source_bundle_revision_id
            FROM source_bundle_revisions
            WHERE source_bundle_revision_id = NEW.source_bundle_revision_id
            FOR SHARE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'P9B_EGRESS_DECISION_REVISION_NOT_FOUND';
            END IF;
            NEW.created_at := clock_timestamp();
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION p9b_validate_egress_decision_insert()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.actor_type NOT IN ('SYSTEM', 'HUMAN')
               OR (NEW.actor_type = 'HUMAN') IS DISTINCT FROM
                  (NEW.actor_identity IS NOT NULL)
               OR cardinality(NEW.reason_codes) = 0 THEN
                RAISE EXCEPTION 'P9B_EGRESS_DECISION_AUDIT_SHAPE_INVALID';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM source_bundle_revisions
                WHERE source_bundle_revision_id = NEW.source_bundle_revision_id
                  AND status = 'FROZEN'
            ) THEN
                RAISE EXCEPTION 'P9B_EGRESS_DECISION_REVISION_NOT_FROZEN';
            END IF;
            IF NEW.decision IN ('ALLOW', 'REDACT_AND_ALLOW')
               AND NOT p9b_egress_decision_authorized_at(
                   NEW.egress_decision_id,
                   NEW.created_at
               ) THEN
                RAISE EXCEPTION 'P9B_EGRESS_DECISION_AUTHORITY_INVALID';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER p9b_egress_decisions_stamp_insert BEFORE INSERT "
        "ON p9b_egress_decisions FOR EACH ROW EXECUTE FUNCTION "
        "p9b_stamp_egress_decision_insert()"
    )
    op.execute(
        "CREATE TRIGGER p9b_egress_decisions_validate_insert AFTER INSERT "
        "ON p9b_egress_decisions FOR EACH ROW EXECUTE FUNCTION "
        "p9b_validate_egress_decision_insert()"
    )


def _create_model_call_insert_guard() -> None:
    op.execute(
        r"""
        CREATE FUNCTION p9b_guard_model_call_insert()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            decision p9b_egress_decisions%ROWTYPE;
            provider_policy p9b_provider_egress_policy_snapshots%ROWTYPE;
        BEGIN
            SELECT * INTO decision FROM p9b_egress_decisions
            WHERE egress_decision_id = NEW.egress_decision_id;
            SELECT * INTO provider_policy FROM p9b_provider_egress_policy_snapshots
            WHERE snapshot_id = decision.provider_policy_snapshot_id
              AND snapshot_hash = decision.provider_policy_snapshot_hash;
            IF NOT FOUND
               OR decision.decision NOT IN ('ALLOW', 'REDACT_AND_ALLOW')
               OR decision.task_spec_name <> NEW.task_spec_name
               OR decision.task_spec_version <> NEW.task_spec_version
               OR decision.provider <> NEW.provider
               OR decision.source_bundle_revision_id <> NEW.source_bundle_revision_id
               OR decision.opportunity_id <> NEW.opportunity_id
               OR decision.opportunity_version <> NEW.opportunity_version
               OR decision.target_scope <> NEW.target_scope
               OR decision.opportunity_unit_id IS DISTINCT FROM NEW.opportunity_unit_id
               OR decision.opportunity_unit_version_id IS DISTINCT FROM
                  NEW.opportunity_unit_version_id
               OR decision.input_block_ids <> NEW.input_block_ids
               OR decision.input_block_hashes <> NEW.input_block_hashes
               OR provider_policy.retention_class <> NEW.retention_class
               OR cardinality(NEW.canonical_message_hashes) = 0
               OR cardinality(NEW.input_block_ids) = 0
               OR cardinality(NEW.input_block_ids) <>
                  cardinality(NEW.input_block_hashes)
               OR EXISTS (
                   SELECT 1 FROM unnest(NEW.canonical_message_hashes) AS value
                   WHERE value !~ '^[0-9a-f]{64}$'
               )
               OR EXISTS (
                   SELECT 1 FROM unnest(NEW.input_block_hashes) AS value
                   WHERE value !~ '^[0-9a-f]{64}$'
               ) THEN
                RAISE EXCEPTION 'P9B_MODEL_CALL_EGRESS_BINDING_MISMATCH';
            END IF;
            NEW.registered_at := clock_timestamp();
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER p9b_model_calls_guard_insert BEFORE INSERT ON p9b_model_calls "
        "FOR EACH ROW EXECUTE FUNCTION p9b_guard_model_call_insert()"
    )


def _create_attempt_authority_guard() -> None:
    op.execute(
        r"""
        CREATE FUNCTION p9b_guard_complete_attempt_authority()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            call_row p9b_model_calls%ROWTYPE;
        BEGIN
            IF NEW.authorization_decision = 'AUTHORIZED' THEN
                SELECT * INTO call_row FROM p9b_model_calls
                WHERE model_call_id = NEW.model_call_id;
                IF NEW.egress_decision_id <> call_row.egress_decision_id
                   OR NEW.source_bundle_revision_id <>
                      call_row.source_bundle_revision_id
                   OR NOT p9b_egress_decision_authorized_at(
                       NEW.egress_decision_id,
                       NEW.authorization_checked_at
                   ) THEN
                    NEW.authorization_decision := 'AUTHORITY_REJECTED';
                    NEW.authorization_reason_code :=
                        'P9B_EGRESS_AUTHORITY_EXPIRED_OR_MISMATCH';
                    NEW.provider_invocation_allowed := false;
                    NEW.dispatch_deadline := NULL;
                    NEW.outcome := 'AUTHORITY_REJECTED';
                    NEW.completed_at := NEW.authorization_checked_at;
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER p9b_model_call_attempts_z_complete_authority BEFORE INSERT "
        "ON p9b_model_call_attempts FOR EACH ROW EXECUTE FUNCTION "
        "p9b_guard_complete_attempt_authority()"
    )


def _preflight_existing_authority() -> None:
    op.execute(
        r"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM p9b_egress_decisions AS decision
                WHERE decision.decision IN ('ALLOW', 'REDACT_AND_ALLOW')
                  AND NOT p9b_egress_decision_authorized_at(
                      decision.egress_decision_id,
                      decision.created_at
                  )
            ) THEN
                RAISE EXCEPTION 'P9B_EXISTING_EGRESS_AUTHORITY_INVALID';
            END IF;
        END;
        $$
        """
    )
