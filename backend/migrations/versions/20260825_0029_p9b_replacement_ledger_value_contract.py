"""p9b_replacement_ledger_value_contract

Revision ID: 20260825_0029
Revises: 20260825_0028
Create Date: 2026-08-25 19:00:00
"""

# ruff: noqa: E501

from collections.abc import Sequence

from alembic import op

revision: str = "20260825_0029"
down_revision: str | None = "20260825_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _replace_credential_scanner()
    _create_value_function()
    _preflight_existing_values()
    _create_configuration_guard()
    _create_attempt_guard()


def downgrade() -> None:
    op.execute("DROP TRIGGER p9b_model_call_attempts_string_values ON p9b_model_call_attempts")
    for table_name in (
        "p9b_model_calls",
        "p9b_egress_decisions",
        "p9b_provider_egress_policy_snapshots",
        "p9b_source_egress_policy_snapshots",
        "p9b_egress_block_classifications",
        "p9b_model_task_specs",
    ):
        op.execute(f"DROP TRIGGER {table_name}_validate_strings ON {table_name}")
    op.execute("DROP FUNCTION p9b_guard_model_call_attempt_strings()")
    op.execute("DROP FUNCTION p9b_guard_gateway_configuration_strings()")
    op.execute("DROP FUNCTION p9b_gateway_string_value_allowed(text, text)")
    _restore_previous_credential_scanner()


def _replace_credential_scanner() -> None:
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION p9b_gateway_contains_credential_material(value text)
        RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
            SELECT value ~ '[[:cntrl:]]'
                OR value ~* '(^|[^a-z0-9_])(authorization|proxy-authorization|cookie|set-cookie)[[:space:]]*[:=]'
                OR value ~* '(^|[^a-z0-9_])(bearer|basic)[[:space:]]+[a-z0-9._~+/-]{8,}=*'
                OR value ~* '(^|[^a-z0-9_])(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|secret[_-]?key|password|credential)[[:space:]]*[:=]'
                OR value ~* '(^|[^a-z0-9_])sk-(proj-)?[a-z0-9_-]{20,}'
                OR value ~* '(^|[^a-z0-9_])xox[baprs]-[a-z0-9-]{20,}'
                OR value ~* '(^|[^a-z0-9_])gh[pousr]_[a-z0-9]{20,}'
                OR value ~* '(^|[^a-z0-9_])glpat-[a-z0-9_-]{20,}'
                OR value ~* '(^|[^a-z0-9_])akia[0-9a-z]{16}([^0-9a-z]|$)'
                OR value ~* '(^|[^a-z0-9_])aiza[0-9a-z_-]{30,}'
                OR value ~* '(^|[^a-z0-9_])(sk|rk)_(live|test)_[a-z0-9]{16,}'
                OR value ~* '(^|[^a-z0-9_])whsec_[a-z0-9]{16,}'
                OR value ~* '(^|[^a-z0-9_-])eyj[a-z0-9_-]{8,}[.]eyj[a-z0-9_-]{8,}[.][a-z0-9_-]{8,}'
                OR value ~* '-----begin [a-z0-9 ]*private key-----'
                OR value ~* '[?&](access_token|api[_-]?key|token|signature|x-amz-credential|x-amz-signature|sig|secret|password)='
                OR value ~* '[a-z][a-z0-9+.-]*://[^/?#[:space:]]+:[^@/?#[:space:]]+@'
        $$
        """
    )


def _create_value_function() -> None:
    op.execute(
        r"""
        CREATE FUNCTION p9b_gateway_string_value_allowed(value text, value_kind text)
        RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
            SELECT NOT p9b_gateway_contains_credential_material(value)
               AND CASE value_kind
                   WHEN 'IDENTIFIER' THEN
                       length(value) <= 128
                       AND value ~ '^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$'
                   WHEN 'PROVIDER_RESPONSE_ID' THEN
                       length(value) <= 256
                       AND value ~ '^[A-Za-z0-9][A-Za-z0-9._:/+-]*$'
                   WHEN 'STORAGE_BUCKET' THEN
                       length(value) <= 128
                       AND value ~ '^[A-Za-z0-9][A-Za-z0-9._-]*$'
                   WHEN 'OBJECT_KEY' THEN
                       length(value) <= 512
                       AND value = btrim(value)
                       AND value !~ '^[/\\]'
                       AND position(E'\\' in value) = 0
                       AND position('://' in value) = 0
                       AND position('?' in value) = 0
                       AND position('#' in value) = 0
                       AND NOT EXISTS (
                           SELECT 1 FROM regexp_split_to_table(value, '/') AS segment
                           WHERE segment IN ('', '.', '..')
                       )
                   WHEN 'ERROR_CODE' THEN
                       length(value) <= 64 AND value ~ '^[A-Z][A-Z0-9_]*$'
                   WHEN 'SHA256' THEN
                       value ~ '^[0-9a-f]{64}$'
                   ELSE false
               END
        $$
        """
    )


def _create_configuration_guard() -> None:
    op.execute(
        r"""
        CREATE FUNCTION p9b_guard_gateway_configuration_strings()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            valid boolean := false;
        BEGIN
            IF TG_TABLE_NAME = 'p9b_model_task_specs' THEN
                valid := p9b_gateway_string_value_allowed(NEW.task_name, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.task_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.route_class, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.output_schema_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.risk_class, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.egress_policy_id, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.fallback_policy, 'IDENTIFIER')
                    AND NOT EXISTS (SELECT 1 FROM unnest(NEW.allowed_input_block_types) value WHERE value IS NULL OR NOT p9b_gateway_string_value_allowed(value, 'IDENTIFIER'))
                    AND NOT EXISTS (SELECT 1 FROM unnest(NEW.provider_capabilities) value WHERE value IS NULL OR NOT p9b_gateway_string_value_allowed(value, 'IDENTIFIER'));
            ELSIF TG_TABLE_NAME = 'p9b_egress_block_classifications' THEN
                valid := p9b_gateway_string_value_allowed(NEW.classification_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.classifier_identity, 'IDENTIFIER')
                    AND NOT EXISTS (SELECT 1 FROM unnest(NEW.classifications) value WHERE value IS NULL OR NOT p9b_gateway_string_value_allowed(value, 'IDENTIFIER'));
            ELSIF TG_TABLE_NAME = 'p9b_source_egress_policy_snapshots' THEN
                valid := p9b_gateway_string_value_allowed(NEW.snapshot_id, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.recorded_by, 'IDENTIFIER');
            ELSIF TG_TABLE_NAME = 'p9b_provider_egress_policy_snapshots' THEN
                valid := p9b_gateway_string_value_allowed(NEW.snapshot_id, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.provider, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.region, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.retention_class, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.recorded_by, 'IDENTIFIER')
                    AND NOT EXISTS (SELECT 1 FROM unnest(NEW.allowed_classifications) value WHERE value IS NULL OR NOT p9b_gateway_string_value_allowed(value, 'IDENTIFIER'));
            ELSIF TG_TABLE_NAME = 'p9b_egress_decisions' THEN
                valid := p9b_gateway_string_value_allowed(NEW.task_spec_name, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.task_spec_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.target_scope, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.data_classification_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.minimizer_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.redactor_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.source_policy_snapshot_id, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.provider_policy_snapshot_id, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.provider, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.provider_region, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.decision, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.actor_type, 'IDENTIFIER')
                    AND (NEW.actor_identity IS NULL OR p9b_gateway_string_value_allowed(NEW.actor_identity, 'IDENTIFIER'))
                    AND NOT EXISTS (SELECT 1 FROM unnest(NEW.reason_codes) value WHERE value IS NULL OR NOT p9b_gateway_string_value_allowed(value, 'ERROR_CODE'));
            ELSIF TG_TABLE_NAME = 'p9b_model_calls' THEN
                valid := p9b_gateway_string_value_allowed(NEW.task_spec_name, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.task_spec_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.provider, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.model_id, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.model_snapshot, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.adapter_name, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.adapter_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.runtime_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.target_scope, 'IDENTIFIER')
                    AND (NEW.unit_segmentation_version IS NULL OR p9b_gateway_string_value_allowed(NEW.unit_segmentation_version, 'IDENTIFIER'))
                    AND p9b_gateway_string_value_allowed(NEW.prompt_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.output_schema_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.parser_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.contract_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.validation_pipeline_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(NEW.retention_class, 'IDENTIFIER');
            END IF;
            IF NOT coalesce(valid, false) THEN
                IF TG_TABLE_NAME = 'p9b_model_calls' THEN
                    RAISE EXCEPTION 'P9B_MODEL_CALL_STRING_INVALID';
                END IF;
                RAISE EXCEPTION 'P9B_GATEWAY_CONFIGURATION_STRING_INVALID';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for table_name in (
        "p9b_model_task_specs",
        "p9b_egress_block_classifications",
        "p9b_source_egress_policy_snapshots",
        "p9b_provider_egress_policy_snapshots",
        "p9b_egress_decisions",
        "p9b_model_calls",
    ):
        op.execute(
            f"CREATE TRIGGER {table_name}_validate_strings BEFORE INSERT ON {table_name} "
            "FOR EACH ROW EXECUTE FUNCTION p9b_guard_gateway_configuration_strings()"
        )


def _create_attempt_guard() -> None:
    op.execute(
        r"""
        CREATE FUNCTION p9b_guard_model_call_attempt_strings()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            unsafe_result boolean;
            credential_result boolean;
        BEGIN
            IF NOT p9b_gateway_string_value_allowed(NEW.source_policy_snapshot_id, 'IDENTIFIER')
               OR NOT p9b_gateway_string_value_allowed(NEW.provider_policy_snapshot_id, 'IDENTIFIER')
               OR NOT p9b_gateway_string_value_allowed(NEW.authorization_decision, 'IDENTIFIER')
               OR NOT p9b_gateway_string_value_allowed(NEW.authorization_reason_code, 'ERROR_CODE')
               OR (NEW.outcome IS NOT NULL AND NOT p9b_gateway_string_value_allowed(NEW.outcome, 'IDENTIFIER'))
               OR (NEW.raw_response_reference_kind IS NOT NULL AND NOT p9b_gateway_string_value_allowed(NEW.raw_response_reference_kind, 'IDENTIFIER'))
               OR (NEW.cost_status IS NOT NULL AND NOT p9b_gateway_string_value_allowed(NEW.cost_status, 'IDENTIFIER'))
            THEN
                RAISE EXCEPTION 'P9B_ATTEMPT_AUTHORITY_STRING_INVALID';
            END IF;
            unsafe_result :=
                (NEW.error_code IS NOT NULL AND NOT p9b_gateway_string_value_allowed(NEW.error_code, 'ERROR_CODE'))
                OR (NEW.provider_response_id IS NOT NULL AND NOT p9b_gateway_string_value_allowed(NEW.provider_response_id, 'PROVIDER_RESPONSE_ID'))
                OR (NEW.raw_response_storage_bucket IS NOT NULL AND NOT p9b_gateway_string_value_allowed(NEW.raw_response_storage_bucket, 'STORAGE_BUCKET'))
                OR (NEW.raw_response_object_key IS NOT NULL AND NOT p9b_gateway_string_value_allowed(NEW.raw_response_object_key, 'OBJECT_KEY'));
            unsafe_result := unsafe_result
                OR (NEW.raw_response_sha256 IS NOT NULL AND NOT p9b_gateway_string_value_allowed(NEW.raw_response_sha256, 'SHA256'));
            IF unsafe_result THEN
                credential_result :=
                    coalesce(p9b_gateway_contains_credential_material(NEW.error_code), false)
                    OR coalesce(p9b_gateway_contains_credential_material(NEW.provider_response_id), false)
                    OR coalesce(p9b_gateway_contains_credential_material(NEW.raw_response_storage_bucket), false)
                    OR coalesce(p9b_gateway_contains_credential_material(NEW.raw_response_object_key), false)
                    OR coalesce(p9b_gateway_contains_credential_material(NEW.raw_response_sha256), false);
                NEW.outcome := 'RESPONSE_METADATA_REJECTED';
                NEW.error_code := CASE WHEN credential_result
                    THEN 'CREDENTIAL_MATERIAL_REJECTED'
                    ELSE 'RESPONSE_METADATA_REJECTED' END;
                NEW.provider_response_id := NULL;
                NEW.raw_response_reference_kind := NULL;
                NEW.raw_response_storage_bucket := NULL;
                NEW.raw_response_object_key := NULL;
                NEW.raw_response_sha256 := NULL;
                NEW.response_hash := NULL;
                NEW.parsed_result_hash := NULL;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER p9b_model_call_attempts_string_values BEFORE INSERT OR UPDATE "
        "ON p9b_model_call_attempts FOR EACH ROW EXECUTE FUNCTION "
        "p9b_guard_model_call_attempt_strings()"
    )


def _preflight_existing_values() -> None:
    op.execute(
        r"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM p9b_model_task_specs row
                WHERE NOT (
                    p9b_gateway_string_value_allowed(row.task_name, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.task_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.route_class, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.output_schema_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.risk_class, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.egress_policy_id, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.fallback_policy, 'IDENTIFIER')
                ) OR EXISTS (SELECT 1 FROM unnest(row.allowed_input_block_types || row.provider_capabilities) value WHERE value IS NULL OR NOT p9b_gateway_string_value_allowed(value, 'IDENTIFIER'))
            ) OR EXISTS (
                SELECT 1 FROM p9b_egress_block_classifications row
                WHERE NOT p9b_gateway_string_value_allowed(row.classification_version, 'IDENTIFIER')
                   OR NOT p9b_gateway_string_value_allowed(row.classifier_identity, 'IDENTIFIER')
                   OR EXISTS (SELECT 1 FROM unnest(row.classifications) value WHERE value IS NULL OR NOT p9b_gateway_string_value_allowed(value, 'IDENTIFIER'))
            ) OR EXISTS (
                SELECT 1 FROM p9b_source_egress_policy_snapshots row
                WHERE NOT p9b_gateway_string_value_allowed(row.snapshot_id, 'IDENTIFIER')
                   OR NOT p9b_gateway_string_value_allowed(row.recorded_by, 'IDENTIFIER')
            ) OR EXISTS (
                SELECT 1 FROM p9b_provider_egress_policy_snapshots row
                WHERE NOT (p9b_gateway_string_value_allowed(row.snapshot_id, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.provider, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.region, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.retention_class, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.recorded_by, 'IDENTIFIER'))
                   OR EXISTS (SELECT 1 FROM unnest(row.allowed_classifications) value WHERE value IS NULL OR NOT p9b_gateway_string_value_allowed(value, 'IDENTIFIER'))
            ) OR EXISTS (
                SELECT 1 FROM p9b_egress_decisions row
                WHERE NOT (p9b_gateway_string_value_allowed(row.task_spec_name, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.task_spec_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.target_scope, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.data_classification_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.minimizer_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.redactor_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.source_policy_snapshot_id, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.provider_policy_snapshot_id, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.provider, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.provider_region, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.decision, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.actor_type, 'IDENTIFIER')
                    AND (row.actor_identity IS NULL OR p9b_gateway_string_value_allowed(row.actor_identity, 'IDENTIFIER')))
                   OR EXISTS (SELECT 1 FROM unnest(row.reason_codes) value WHERE value IS NULL OR NOT p9b_gateway_string_value_allowed(value, 'ERROR_CODE'))
            ) OR EXISTS (
                SELECT 1 FROM p9b_model_calls row
                WHERE NOT (p9b_gateway_string_value_allowed(row.task_spec_name, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.task_spec_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.provider, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.model_id, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.model_snapshot, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.adapter_name, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.adapter_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.runtime_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.target_scope, 'IDENTIFIER')
                    AND (row.unit_segmentation_version IS NULL OR p9b_gateway_string_value_allowed(row.unit_segmentation_version, 'IDENTIFIER'))
                    AND p9b_gateway_string_value_allowed(row.prompt_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.output_schema_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.parser_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.contract_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.validation_pipeline_version, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.retention_class, 'IDENTIFIER'))
            ) OR EXISTS (
                SELECT 1 FROM p9b_model_call_attempts row
                WHERE NOT (p9b_gateway_string_value_allowed(row.source_policy_snapshot_id, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.provider_policy_snapshot_id, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.authorization_decision, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.authorization_reason_code, 'ERROR_CODE')
                    AND (row.outcome IS NULL OR p9b_gateway_string_value_allowed(row.outcome, 'IDENTIFIER'))
                    AND (row.error_code IS NULL OR p9b_gateway_string_value_allowed(row.error_code, 'ERROR_CODE'))
                    AND (row.provider_response_id IS NULL OR p9b_gateway_string_value_allowed(row.provider_response_id, 'PROVIDER_RESPONSE_ID'))
                    AND (row.raw_response_reference_kind IS NULL OR p9b_gateway_string_value_allowed(row.raw_response_reference_kind, 'IDENTIFIER'))
                    AND (row.raw_response_storage_bucket IS NULL OR p9b_gateway_string_value_allowed(row.raw_response_storage_bucket, 'STORAGE_BUCKET'))
                    AND (row.raw_response_object_key IS NULL OR p9b_gateway_string_value_allowed(row.raw_response_object_key, 'OBJECT_KEY'))
                    AND (row.raw_response_sha256 IS NULL OR p9b_gateway_string_value_allowed(row.raw_response_sha256, 'SHA256'))
                    AND (row.cost_status IS NULL OR p9b_gateway_string_value_allowed(row.cost_status, 'IDENTIFIER')))
            ) OR EXISTS (
                SELECT 1 FROM p9b_model_call_finalizations row
                WHERE NOT (p9b_gateway_string_value_allowed(row.status, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.disposition, 'IDENTIFIER')
                    AND p9b_gateway_string_value_allowed(row.reason_code, 'ERROR_CODE'))
            ) THEN
                RAISE EXCEPTION 'P9B_GATEWAY_STRING_PREFLIGHT_FAILED';
            END IF;
        END;
        $$
        """
    )


def _restore_previous_credential_scanner() -> None:
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION p9b_gateway_contains_credential_material(value text)
        RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
            SELECT value ~ '[[:cntrl:]]'
                OR value ~* '(^|[^a-z0-9_])(authorization|proxy-authorization|cookie|set-cookie)[[:space:]]*[:=]'
                OR value ~* '(^|[^a-z0-9_])(bearer|basic)[[:space:]]+[a-z0-9._~+/-]{8,}=*'
                OR value ~* '(^|[^a-z0-9_])(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|secret[_-]?key|password|credential)[[:space:]]*[:=]'
                OR value ~* '(^|[^a-z0-9_])sk-(proj-)?[a-z0-9_-]{8,}'
        $$
        """
    )
