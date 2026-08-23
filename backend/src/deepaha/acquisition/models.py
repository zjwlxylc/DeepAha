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


__all__ = ["AcquisitionEvaluation"]
