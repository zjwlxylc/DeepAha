from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from deepaha.db.base import Base


class RuleSetModel(Base):
    __tablename__ = "rule_sets"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(rule_set_id) = 7", name="rule_set_id_uuid7"),
        CheckConstraint("version >= 1", name="positive_version"),
        CheckConstraint("opportunity_version >= 1", name="positive_opportunity_version"),
        CheckConstraint(
            "jsonb_typeof(root_rule_ids) = 'array' and jsonb_array_length(root_rule_ids) >= 1",
            name="root_rule_ids_nonempty_array",
        ),
        CheckConstraint("review_status = 'APPROVED'", name="review_status_approved"),
        CheckConstraint("rule_schema_version = '0.4.0'", name="schema_version_v04"),
        ForeignKeyConstraint(
            ["opportunity_id", "opportunity_version"],
            ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
            ondelete="RESTRICT",
        ),
        PrimaryKeyConstraint("rule_set_id", "version"),
        UniqueConstraint(
            "opportunity_id",
            "opportunity_version",
            "version",
            name="uq_rule_sets_opportunity_version_rule_set_version",
        ),
    )

    rule_set_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_version: Mapped[int] = mapped_column(Integer)
    root_rule_ids: Mapped[list[str]] = mapped_column(JSONB)
    review_status: Mapped[str] = mapped_column(String(16))
    rule_schema_version: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RuleModel(Base):
    __tablename__ = "rules"
    __table_args__ = (
        CheckConstraint("uuid_extract_version(rule_id) = 7", name="rule_id_uuid7"),
        CheckConstraint("length(btrim(code)) >= 1", name="code_nonempty"),
        CheckConstraint(
            "operator in ('EQ', 'NE', 'IN', 'NOT_IN', 'GTE', 'LTE', 'BETWEEN', "
            "'CONTAINS_ANY', 'CONTAINS_ALL', 'EXISTS', 'NOT_EXISTS', 'AND', 'OR', 'NOT')",
            name="operator_values",
        ),
        CheckConstraint(
            "field is null or field in ('education_level', 'major_code', 'graduation_year', "
            "'student_status', 'birth_date', 'hukou_region', 'residence_region', "
            "'target_regions', 'certificates')",
            name="field_values",
        ),
        CheckConstraint(
            "value_type is null or value_type in "
            "('STRING', 'INTEGER', 'DATE', 'STRING_SET', 'BOOLEAN')",
            name="value_type_values",
        ),
        CheckConstraint(
            "jsonb_typeof(operand_rule_ids) = 'array'",
            name="operand_rule_ids_array",
        ),
        CheckConstraint("length(btrim(reason_template)) >= 1", name="reason_nonempty"),
        ForeignKeyConstraint(
            ["rule_set_id", "rule_set_version"],
            ["rule_sets.rule_set_id", "rule_sets.version"],
            ondelete="RESTRICT",
        ),
        PrimaryKeyConstraint("rule_set_id", "rule_set_version", "rule_id"),
        UniqueConstraint(
            "rule_set_id",
            "rule_set_version",
            "code",
            name="uq_rules_rule_set_code",
        ),
    )

    rule_set_id: Mapped[UUID] = mapped_column(Uuid)
    rule_set_version: Mapped[int] = mapped_column(Integer)
    rule_id: Mapped[UUID] = mapped_column(Uuid)
    code: Mapped[str] = mapped_column(String(128))
    operator: Mapped[str] = mapped_column(String(24))
    field: Mapped[str | None] = mapped_column(String(32))
    value_type: Mapped[str | None] = mapped_column(String(16))
    value: Mapped[object | None] = mapped_column(JSONB(none_as_null=True))
    operand_rule_ids: Mapped[list[str]] = mapped_column(JSONB)
    required: Mapped[bool] = mapped_column(Boolean)
    reason_template: Mapped[str] = mapped_column(Text)


class RuleEvidenceModel(Base):
    __tablename__ = "rule_evidence"
    __table_args__ = (
        CheckConstraint(
            "authority in ('LATEST_OFFICIAL_CORRECTION', 'FORMAL_OFFICIAL_ATTACHMENT', "
            "'ORIGINAL_OFFICIAL_NOTICE', 'OFFICIAL_FAQ_GUIDANCE', "
            "'HUMAN_APPROVED_MAPPING', 'LLM_SEMANTIC_INFERENCE')",
            name="authority_values",
        ),
        CheckConstraint(
            "(authority = 'LATEST_OFFICIAL_CORRECTION' and precedence = 600) or "
            "(authority = 'FORMAL_OFFICIAL_ATTACHMENT' and precedence = 500) or "
            "(authority = 'ORIGINAL_OFFICIAL_NOTICE' and precedence = 400) or "
            "(authority = 'OFFICIAL_FAQ_GUIDANCE' and precedence = 300) or "
            "(authority = 'HUMAN_APPROVED_MAPPING' and precedence = 200) or "
            "(authority = 'LLM_SEMANTIC_INFERENCE' and precedence = 100)",
            name="authority_precedence",
        ),
        CheckConstraint("relation in ('SUPPORTS', 'CONTRADICTS')", name="relation_values"),
        CheckConstraint(
            "assertion_sha256 ~ '^[0-9a-f]{64}$'",
            name="assertion_sha256_format",
        ),
        ForeignKeyConstraint(
            ["rule_set_id", "rule_set_version", "rule_id"],
            ["rules.rule_set_id", "rules.rule_set_version", "rules.rule_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["evidence_ref_id", "document_id"],
            ["evidence_refs.evidence_ref_id", "evidence_refs.document_id"],
            ondelete="RESTRICT",
        ),
        PrimaryKeyConstraint(
            "rule_set_id",
            "rule_set_version",
            "rule_id",
            "evidence_ref_id",
        ),
    )

    rule_set_id: Mapped[UUID] = mapped_column(Uuid)
    rule_set_version: Mapped[int] = mapped_column(Integer)
    rule_id: Mapped[UUID] = mapped_column(Uuid)
    evidence_ref_id: Mapped[UUID] = mapped_column(Uuid)
    document_id: Mapped[UUID] = mapped_column(Uuid)
    authority: Mapped[str] = mapped_column(String(40))
    precedence: Mapped[int] = mapped_column(Integer)
    relation: Mapped[str] = mapped_column(String(16))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    assertion_sha256: Mapped[str] = mapped_column(String(64))


__all__ = ["RuleEvidenceModel", "RuleModel", "RuleSetModel"]
