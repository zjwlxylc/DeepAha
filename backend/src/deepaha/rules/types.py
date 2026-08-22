from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from pydantic import JsonValue

from deepaha.contracts.phase4 import (
    EvidenceRelation,
    RuleEvidenceAuthority,
    RuleField,
    RuleOperator,
    RuleValueType,
)


class RuleCompileError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class FieldSpec:
    value_type: RuleValueType
    operators: frozenset[RuleOperator]
    ordered: bool = False


_EXISTENCE = frozenset({RuleOperator.EXISTS, RuleOperator.NOT_EXISTS})
_SCALAR = frozenset(
    {
        RuleOperator.EQ,
        RuleOperator.NE,
        RuleOperator.IN,
        RuleOperator.NOT_IN,
        *_EXISTENCE,
    }
)
_ORDERED = frozenset(
    {
        RuleOperator.EQ,
        RuleOperator.NE,
        RuleOperator.IN,
        RuleOperator.NOT_IN,
        RuleOperator.GTE,
        RuleOperator.LTE,
        RuleOperator.BETWEEN,
        *_EXISTENCE,
    }
)
_SET = frozenset(
    {
        RuleOperator.CONTAINS_ANY,
        RuleOperator.CONTAINS_ALL,
        *_EXISTENCE,
    }
)

FIELD_REGISTRY: Mapping[str, FieldSpec] = MappingProxyType(
    {
        RuleField.EDUCATION_LEVEL.value: FieldSpec(
            RuleValueType.STRING,
            _ORDERED,
            ordered=True,
        ),
        RuleField.MAJOR_CODE.value: FieldSpec(RuleValueType.STRING, _SCALAR),
        RuleField.GRADUATION_YEAR.value: FieldSpec(
            RuleValueType.INTEGER,
            _ORDERED,
            ordered=True,
        ),
        RuleField.STUDENT_STATUS.value: FieldSpec(RuleValueType.STRING, _SCALAR),
        RuleField.BIRTH_DATE.value: FieldSpec(
            RuleValueType.DATE,
            _ORDERED,
            ordered=True,
        ),
        RuleField.HUKOU_REGION.value: FieldSpec(RuleValueType.STRING, _SCALAR),
        RuleField.RESIDENCE_REGION.value: FieldSpec(RuleValueType.STRING, _SCALAR),
        RuleField.TARGET_REGIONS.value: FieldSpec(RuleValueType.STRING_SET, _SET),
        RuleField.CERTIFICATES.value: FieldSpec(RuleValueType.STRING_SET, _SET),
    }
)


@dataclass(frozen=True, slots=True)
class CompiledEvidence:
    evidence_ref_id: UUID
    document_id: UUID
    authority: RuleEvidenceAuthority
    precedence: int
    relation: EvidenceRelation
    effective_at: datetime
    assertion_sha256: str


@dataclass(frozen=True, slots=True)
class CompiledRule:
    rule_id: UUID
    code: str
    operator: RuleOperator
    field: RuleField | None
    value_type: RuleValueType | None
    value: JsonValue | None
    operand_rule_ids: tuple[UUID, ...]
    required: bool
    reason_template: str
    evidence: tuple[CompiledEvidence, ...]
    effective_precedence: int | None
    evidence_conflicted: bool


@dataclass(frozen=True, slots=True)
class CompiledRuleSet:
    rule_set_id: UUID
    version: int
    opportunity_id: UUID
    opportunity_version: int
    root_rule_ids: tuple[UUID, ...]
    rules: tuple[CompiledRule, ...]
    compiled_sha256: str
    compiler_version: str


__all__ = [
    "CompiledEvidence",
    "CompiledRule",
    "CompiledRuleSet",
    "FIELD_REGISTRY",
    "FieldSpec",
    "RuleCompileError",
    "RuleValueType",
]
