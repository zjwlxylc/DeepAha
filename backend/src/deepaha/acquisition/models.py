from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class AcquisitionEvaluation(Base):
    __tablename__ = "acquisition_evaluations"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(acquisition_evaluation_id) = 7",
            name="acquisition_evaluation_id_uuid7",
        ),
        CheckConstraint(
            "strategy_used in ('STRUCTURED', 'STATIC_HTTP', 'BROWSER', "
            "'OFFICIAL_ALTERNATIVE', 'MANUAL')",
            name="strategy_used_values",
        ),
        CheckConstraint(
            "validation_status in ('VALID', 'CONTENT_CHALLENGE', 'CAPTCHA_REQUIRED', "
            "'AUTH_REQUIRED', 'ACCESS_DENIED', 'UNEXPECTED_CONTENT', "
            "'ZERO_DISCOVERY_SUSPECT', 'SELECTOR_DRIFT')",
            name="validation_status_values",
        ),
        CheckConstraint(
            "challenge_type is null or challenge_type in "
            "('JAVASCRIPT_COOKIE', 'CAPTCHA', 'AUTHENTICATION', 'ACCESS_CONTROL')",
            name="challenge_type_values",
        ),
        CheckConstraint(
            "(validation_status = 'CONTENT_CHALLENGE' and challenge_type is not null and "
            "challenge_type = 'JAVASCRIPT_COOKIE') or "
            "(validation_status = 'CAPTCHA_REQUIRED' and challenge_type is not null and "
            "challenge_type = 'CAPTCHA') or "
            "(validation_status = 'AUTH_REQUIRED' and challenge_type is not null and "
            "challenge_type = 'AUTHENTICATION') or "
            "(validation_status = 'ACCESS_DENIED' and challenge_type is not null and "
            "challenge_type = 'ACCESS_CONTROL') or "
            "(validation_status in ('VALID', 'UNEXPECTED_CONTENT', "
            "'ZERO_DISCOVERY_SUSPECT', 'SELECTOR_DRIFT') and challenge_type is null)",
            name="challenge_state",
        ),
        CheckConstraint(
            "jsonb_typeof(redirect_chain) = 'array' and "
            "jsonb_array_length(redirect_chain) between 1 and 11",
            name="redirect_chain_shape",
        ),
        CheckConstraint(
            "discovered_count is null or discovered_count between 0 and 10000",
            name="discovered_count_range",
        ),
        CheckConstraint(
            "(strategy_used = 'MANUAL') = manual_intervention",
            name="manual_intervention_state",
        ),
        CheckConstraint(
            "jsonb_typeof(diagnostic_codes) = 'array' and "
            "jsonb_array_length(diagnostic_codes) <= 32",
            name="diagnostic_codes_shape",
        ),
        CheckConstraint(
            "jsonb_typeof(validation_metrics) = 'object' and "
            "octet_length(validation_metrics::text) <= 4096",
            name="validation_metrics_shape",
        ),
        CheckConstraint("contract_version = '1.0.0'", name="contract_version_value"),
        ForeignKeyConstraint(
            ["observation_id", "endpoint_id", "source_id", "artifact_id"],
            [
                "capture_observations.observation_id",
                "capture_observations.endpoint_id",
                "capture_observations.source_id",
                "capture_observations.artifact_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["endpoint_id", "source_id"],
            ["source_endpoints.endpoint_id", "source_endpoints.source_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["artifact_id", "source_id"],
            ["raw_artifacts.artifact_id", "raw_artifacts.source_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("observation_id"),
        UniqueConstraint(
            "acquisition_evaluation_id",
            "observation_id",
            "endpoint_id",
            "source_id",
            "artifact_id",
            "strategy_used",
            "validation_status",
            "validator_name",
            "validator_version",
            name="uq_acquisition_evaluations_p9b_provenance_binding",
        ),
        Index(
            "ix_acquisition_evaluations_endpoint_evaluated",
            "endpoint_id",
            text("evaluated_at DESC"),
            text("acquisition_evaluation_id DESC"),
        ),
    )

    acquisition_evaluation_id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    observation_id: Mapped[UUID] = mapped_column(Uuid)
    endpoint_id: Mapped[UUID] = mapped_column(Uuid)
    source_id: Mapped[UUID] = mapped_column(Uuid)
    artifact_id: Mapped[UUID] = mapped_column(Uuid)
    strategy_used: Mapped[str] = mapped_column(String(32))
    validation_status: Mapped[str] = mapped_column(String(32))
    challenge_type: Mapped[str | None] = mapped_column(String(32))
    redirect_chain: Mapped[list[str]] = mapped_column(JSONB)
    discovered_count: Mapped[int | None] = mapped_column(Integer)
    manual_intervention: Mapped[bool] = mapped_column(Boolean)
    diagnostic_codes: Mapped[list[str]] = mapped_column(JSONB)
    validator_name: Mapped[str] = mapped_column(String(128))
    validator_version: Mapped[str] = mapped_column(String(64))
    metrics_schema_version: Mapped[str] = mapped_column(String(64))
    validation_metrics: Mapped[dict[str, object]] = mapped_column(JSONB)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    contract_version: Mapped[str] = mapped_column(String(16))


class AcquisitionRun(Base):
    __tablename__ = "acquisition_runs"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(acquisition_run_id) = 7", name="run_id_uuid7"),
        CheckConstraint("uuid_extract_version(recipe_id) = 7", name="recipe_id_uuid7"),
        CheckConstraint("completed_at >= started_at", name="timestamp_order"),
        CheckConstraint("request_count between 0 and 25", name="request_count_range"),
        CheckConstraint(
            "jsonb_typeof(strategy_attempts) = 'array' and "
            "jsonb_array_length(strategy_attempts) = request_count",
            name="strategy_attempts_shape",
        ),
        CheckConstraint(
            "discovered_count between 0 and 10000 and "
            "validated_count between 0 and request_count and "
            "parsed_count between 0 and validated_count and "
            "attachment_count between 0 and discovered_count and "
            "evidence_count between 0 and 10000",
            name="count_coherence",
        ),
        CheckConstraint(
            "terminal_code ~ '^[A-Z][A-Z0-9_]{0,127}$' and "
            "(stable_stop_reason is null or stable_stop_reason ~ '^[A-Z][A-Z0-9_]{0,127}$')",
            name="terminal_code_shape",
        ),
        CheckConstraint(
            "(terminal_code = 'COMPLETE') = (stable_stop_reason is null)",
            name="stable_stop_reason_state",
        ),
        CheckConstraint("contract_version = '1.0.0'", name="contract_version_value"),
        ForeignKeyConstraint(
            ["endpoint_id", "source_id"],
            ["source_endpoints.endpoint_id", "source_endpoints.source_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "acquisition_run_id",
            "recipe_id",
            "source_id",
            "endpoint_id",
            "endpoint_policy_version",
            "recipe_version",
            name="uq_acquisition_runs_p9b_provenance_binding",
        ),
        Index(
            "ix_acquisition_runs_endpoint_completed",
            "endpoint_id",
            text("completed_at DESC"),
            text("acquisition_run_id DESC"),
        ),
    )

    acquisition_run_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    recipe_id: Mapped[UUID] = mapped_column(Uuid)
    source_id: Mapped[UUID] = mapped_column(Uuid)
    endpoint_id: Mapped[UUID] = mapped_column(Uuid)
    endpoint_policy_version: Mapped[str] = mapped_column(String(64))
    recipe_version: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    terminal_code: Mapped[str] = mapped_column(String(128))
    request_count: Mapped[int] = mapped_column(Integer)
    strategy_attempts: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    discovered_count: Mapped[int] = mapped_column(Integer)
    validated_count: Mapped[int] = mapped_column(Integer)
    parsed_count: Mapped[int] = mapped_column(Integer)
    attachment_count: Mapped[int] = mapped_column(Integer)
    evidence_count: Mapped[int] = mapped_column(Integer)
    zero_discovery_flag: Mapped[bool] = mapped_column(Boolean)
    selector_drift_flag: Mapped[bool] = mapped_column(Boolean)
    manual_intervention: Mapped[bool] = mapped_column(Boolean)
    stable_stop_reason: Mapped[str | None] = mapped_column(String(128))
    contract_version: Mapped[str] = mapped_column(String(16))


class SourceIntegrationEvidence(Base):
    __tablename__ = "source_integration_evidence"
    __table_args__ = (
        CheckConstraint(
            "uuid_extract_version(source_integration_evidence_id) = 7",
            name="evidence_id_uuid7",
        ),
        CheckConstraint("uuid_extract_version(recipe_id) = 7", name="recipe_id_uuid7"),
        CheckConstraint(
            "onboarding_mode in "
            "('RECIPE_ONLY', 'THIN_PLUGIN', 'GENERIC_CAPABILITY', 'NEW_FETCHER')",
            name="onboarding_mode_values",
        ),
        CheckConstraint(
            "recipe_line_count between 1 and 10000 and "
            "source_specific_production_loc between 0 and 100000 and "
            "generic_capability_changes between 0 and 100 and "
            "onboarding_minutes between 0 and 100000 and "
            "total_request_count between 0 and 100000 and "
            "browser_request_count between 0 and total_request_count and "
            "manual_request_count between 0 and total_request_count and "
            "run_failure_count between 0 and total_request_count and "
            "maintenance_minutes between 0 and 100000",
            name="cost_count_coherence",
        ),
        CheckConstraint(
            "onboarding_mode <> 'RECIPE_ONLY' or "
            "(source_specific_production_loc = 0 and generic_capability_changes = 0)",
            name="recipe_only_shape",
        ),
        CheckConstraint(
            "onboarding_mode <> 'THIN_PLUGIN' or source_specific_production_loc > 0",
            name="thin_plugin_shape",
        ),
        CheckConstraint(
            "onboarding_mode <> 'NEW_FETCHER' or not reused_existing_fetcher",
            name="new_fetcher_shape",
        ),
        CheckConstraint("contract_version = '1.0.0'", name="contract_version_value"),
        ForeignKeyConstraint(
            ["endpoint_id", "source_id"],
            ["source_endpoints.endpoint_id", "source_endpoints.source_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("source_id", "endpoint_id", "recipe_version"),
    )

    source_integration_evidence_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    recipe_id: Mapped[UUID] = mapped_column(Uuid)
    source_id: Mapped[UUID] = mapped_column(Uuid)
    endpoint_id: Mapped[UUID] = mapped_column(Uuid)
    recipe_version: Mapped[str] = mapped_column(String(64))
    primary_fetcher: Mapped[str] = mapped_column(String(128))
    onboarding_mode: Mapped[str] = mapped_column(String(32))
    reused_existing_fetcher: Mapped[bool] = mapped_column(Boolean)
    recipe_line_count: Mapped[int] = mapped_column(Integer)
    source_specific_production_loc: Mapped[int] = mapped_column(Integer)
    generic_capability_changes: Mapped[int] = mapped_column(Integer)
    core_schema_changed: Mapped[bool] = mapped_column(Boolean)
    onboarding_minutes: Mapped[int] = mapped_column(Integer)
    total_request_count: Mapped[int] = mapped_column(Integer)
    browser_request_count: Mapped[int] = mapped_column(Integer)
    manual_request_count: Mapped[int] = mapped_column(Integer)
    run_failure_count: Mapped[int] = mapped_column(Integer)
    maintenance_minutes: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    contract_version: Mapped[str] = mapped_column(String(16))


__all__ = ["AcquisitionEvaluation", "AcquisitionRun", "SourceIntegrationEvidence"]
