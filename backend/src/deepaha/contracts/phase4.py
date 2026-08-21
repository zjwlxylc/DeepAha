from datetime import date
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, JsonValue, field_validator, model_validator

from deepaha.contracts.common import (
    EntityId,
    Instant,
    NonEmptyString,
    Sha256,
    VersionNumber,
)
from deepaha.contracts.phase1 import ContractModel


class EligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    LIKELY_ELIGIBLE = "LIKELY_ELIGIBLE"
    UNCERTAIN = "UNCERTAIN"
    INELIGIBLE = "INELIGIBLE"


class RuleOperator(StrEnum):
    EQ = "EQ"
    NE = "NE"
    IN = "IN"
    NOT_IN = "NOT_IN"
    GTE = "GTE"
    LTE = "LTE"
    BETWEEN = "BETWEEN"
    CONTAINS_ANY = "CONTAINS_ANY"
    CONTAINS_ALL = "CONTAINS_ALL"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class RuleValueType(StrEnum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    DATE = "DATE"
    STRING_SET = "STRING_SET"
    BOOLEAN = "BOOLEAN"


class RuleOutcome(StrEnum):
    SATISFIED = "SATISFIED"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


class RuleEvidenceAuthority(StrEnum):
    LATEST_OFFICIAL_CORRECTION = "LATEST_OFFICIAL_CORRECTION"
    FORMAL_OFFICIAL_ATTACHMENT = "FORMAL_OFFICIAL_ATTACHMENT"
    ORIGINAL_OFFICIAL_NOTICE = "ORIGINAL_OFFICIAL_NOTICE"
    OFFICIAL_FAQ_GUIDANCE = "OFFICIAL_FAQ_GUIDANCE"
    HUMAN_APPROVED_MAPPING = "HUMAN_APPROVED_MAPPING"
    LLM_SEMANTIC_INFERENCE = "LLM_SEMANTIC_INFERENCE"

    @property
    def precedence(self) -> int:
        return {
            self.LATEST_OFFICIAL_CORRECTION: 600,
            self.FORMAL_OFFICIAL_ATTACHMENT: 500,
            self.ORIGINAL_OFFICIAL_NOTICE: 400,
            self.OFFICIAL_FAQ_GUIDANCE: 300,
            self.HUMAN_APPROVED_MAPPING: 200,
            self.LLM_SEMANTIC_INFERENCE: 100,
        }[self]


class EvidenceRelation(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"


class EducationLevel(StrEnum):
    SECONDARY = "SECONDARY"
    ASSOCIATE = "ASSOCIATE"
    BACHELOR = "BACHELOR"
    MASTER = "MASTER"
    DOCTORATE = "DOCTORATE"


class StudentStatus(StrEnum):
    ENROLLED = "ENROLLED"
    GRADUATING = "GRADUATING"
    RECENT_GRADUATE = "RECENT_GRADUATE"
    EMPLOYED = "EMPLOYED"
    OTHER = "OTHER"


class EvaluationComponent(StrEnum):
    RULE_ENGINE = "RULE_ENGINE"
    ELIGIBILITY = "ELIGIBILITY"
    MATCH_REPLAY = "MATCH_REPLAY"


class EvaluationRunStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RuleField(StrEnum):
    EDUCATION_LEVEL = "education_level"
    MAJOR_CODE = "major_code"
    GRADUATION_YEAR = "graduation_year"
    STUDENT_STATUS = "student_status"
    BIRTH_DATE = "birth_date"
    HUKOU_REGION = "hukou_region"
    RESIDENCE_REGION = "residence_region"
    TARGET_REGIONS = "target_regions"
    CERTIFICATES = "certificates"


class RuleEvidenceSchemaV04(ContractModel):
    evidence_ref_id: EntityId
    document_id: EntityId
    authority: RuleEvidenceAuthority
    precedence: int = Field(ge=100, le=600)
    relation: EvidenceRelation
    effective_at: Instant
    assertion_sha256: Sha256

    @model_validator(mode="after")
    def require_authority_precedence(self) -> Self:
        if self.precedence != self.authority.precedence:
            raise ValueError("precedence must match authority")
        return self


_ATOMIC_OPERATORS = frozenset(
    {
        RuleOperator.EQ,
        RuleOperator.NE,
        RuleOperator.IN,
        RuleOperator.NOT_IN,
        RuleOperator.GTE,
        RuleOperator.LTE,
        RuleOperator.BETWEEN,
        RuleOperator.CONTAINS_ANY,
        RuleOperator.CONTAINS_ALL,
        RuleOperator.EXISTS,
        RuleOperator.NOT_EXISTS,
    }
)
_COMPOSITE_OPERATORS = frozenset({RuleOperator.AND, RuleOperator.OR, RuleOperator.NOT})
_SINGLE_VALUE_OPERATORS = frozenset(
    {RuleOperator.EQ, RuleOperator.NE, RuleOperator.GTE, RuleOperator.LTE}
)
_LIST_VALUE_OPERATORS = frozenset(
    {
        RuleOperator.IN,
        RuleOperator.NOT_IN,
        RuleOperator.CONTAINS_ANY,
        RuleOperator.CONTAINS_ALL,
    }
)


class RuleSchemaV04(ContractModel):
    rule_id: EntityId
    code: NonEmptyString
    operator: RuleOperator
    field: RuleField | None
    value_type: RuleValueType | None
    value: JsonValue | None
    operand_rule_ids: tuple[EntityId, ...]
    required: bool
    reason_template: NonEmptyString
    evidence: tuple[RuleEvidenceSchemaV04, ...]

    @field_validator("operand_rule_ids")
    @classmethod
    def require_unique_operands(cls, value: tuple[EntityId, ...]) -> tuple[EntityId, ...]:
        if len(value) != len(set(value)):
            raise ValueError("operand_rule_ids must not contain duplicates")
        return value

    @field_validator("evidence")
    @classmethod
    def require_unique_evidence(
        cls, value: tuple[RuleEvidenceSchemaV04, ...]
    ) -> tuple[RuleEvidenceSchemaV04, ...]:
        evidence_ids = [item.evidence_ref_id for item in value]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_ref_ids must not contain duplicates")
        return value

    @model_validator(mode="after")
    def require_operator_shape(self) -> Self:
        if self.operator in _ATOMIC_OPERATORS:
            self._require_atomic_shape()
        elif self.operator in _COMPOSITE_OPERATORS:
            self._require_composite_shape()
        else:  # pragma: no cover - enum validation rejects unknown values
            raise ValueError("unknown operator")
        return self

    def _require_atomic_shape(self) -> None:
        if self.field is None:
            raise ValueError("atomic rule requires field")
        if self.value_type is None:
            raise ValueError("atomic rule requires value_type")
        if self.operand_rule_ids:
            raise ValueError("atomic rule forbids operand_rule_ids")
        if self.required and not self.evidence:
            raise ValueError("required atomic rule requires evidence")
        if self.operator in {RuleOperator.EXISTS, RuleOperator.NOT_EXISTS}:
            if self.value is not None:
                raise ValueError("existence rule forbids value")
            return
        if self.value is None:
            raise ValueError("atomic rule requires value")
        if self.operator in _SINGLE_VALUE_OPERATORS:
            if isinstance(self.value, (list, dict)):
                raise ValueError("single-value operator requires a scalar value")
            return
        if self.operator is RuleOperator.BETWEEN:
            if not isinstance(self.value, list) or len(self.value) != 2:
                raise ValueError("BETWEEN requires exactly two values")
            left, right = self.value
            ordered = (
                isinstance(left, str)
                and isinstance(right, str)
                and left <= right
                or isinstance(left, int)
                and not isinstance(left, bool)
                and isinstance(right, int)
                and not isinstance(right, bool)
                and left <= right
                or isinstance(left, float)
                and isinstance(right, (int, float))
                and not isinstance(right, bool)
                and left <= right
            )
            if not ordered:
                raise ValueError("BETWEEN values must be sorted")
            return
        if self.operator in _LIST_VALUE_OPERATORS:
            if not isinstance(self.value, list) or not self.value:
                raise ValueError("set operator requires a non-empty value list")
            serialized = [str(item) for item in self.value]
            if len(serialized) != len(set(serialized)):
                raise ValueError("value list must not contain duplicates")
            if serialized != sorted(serialized):
                raise ValueError("value list must be sorted")

    def _require_composite_shape(self) -> None:
        if self.field is not None or self.value_type is not None or self.value is not None:
            raise ValueError("composite rule forbids field, value_type and value")
        if self.evidence:
            raise ValueError("composite rule forbids direct evidence")
        if self.operator is RuleOperator.NOT and len(self.operand_rule_ids) != 1:
            raise ValueError("NOT requires exactly one operand")
        if self.operator in {RuleOperator.AND, RuleOperator.OR} and len(self.operand_rule_ids) < 2:
            raise ValueError("AND and OR require at least two operands")


class RuleSetSchemaV04(ContractModel):
    rule_set_id: EntityId
    version: VersionNumber
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    rules: tuple[RuleSchemaV04, ...] = Field(min_length=1)
    root_rule_ids: tuple[EntityId, ...] = Field(min_length=1)
    review_status: Literal["APPROVED"]
    rule_schema_version: Literal["0.4.0"]
    created_at: Instant

    @model_validator(mode="after")
    def require_unique_rules_and_known_roots(self) -> Self:
        rule_ids = [rule.rule_id for rule in self.rules]
        codes = [rule.code for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("rule IDs must be unique")
        if len(codes) != len(set(codes)):
            raise ValueError("rule codes must be unique")
        if len(self.root_rule_ids) != len(set(self.root_rule_ids)):
            raise ValueError("root_rule_ids must be unique")
        unknown_roots = set(self.root_rule_ids) - set(rule_ids)
        if unknown_roots:
            raise ValueError("root_rule_ids must reference rules in this RuleSet")
        return self


class ProfileAttributesSchemaV04(ContractModel):
    education_level: EducationLevel | None
    major_name: NonEmptyString | None
    major_code: NonEmptyString | None
    graduation_year: int | None
    student_status: StudentStatus | None
    birth_date: date | None
    hukou_region: NonEmptyString | None
    residence_region: NonEmptyString | None
    target_regions: tuple[NonEmptyString, ...]
    certificates: tuple[NonEmptyString, ...]

    @field_validator("target_regions", "certificates", mode="before")
    @classmethod
    def normalize_unique_strings(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        normalized = tuple(sorted(str(item).strip() for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError("set-like profile fields must not contain duplicates")
        return normalized


class ProfileSnapshotSchemaV04(ContractModel):
    profile_snapshot_id: EntityId
    profile_id: EntityId
    version: VersionNumber
    synthetic: bool
    persona_family_id: EntityId | None
    attributes: ProfileAttributesSchemaV04
    scenario_clock: date
    profile_schema_version: Literal["0.4.0"]
    created_at: Instant
    created_by: NonEmptyString
    reviewed_by: NonEmptyString
    change_note: NonEmptyString


class RuleEvaluationSchemaV04(ContractModel):
    rule_id: EntityId
    outcome: RuleOutcome
    deterministic: bool
    official_evidence: bool
    reason_code: NonEmptyString
    evidence_ref_ids: tuple[EntityId, ...]
    missing_fields: tuple[RuleField, ...]

    @model_validator(mode="after")
    def require_unique_explanation_values(self) -> Self:
        if len(self.evidence_ref_ids) != len(set(self.evidence_ref_ids)):
            raise ValueError("evidence_ref_ids must be unique")
        if len(self.missing_fields) != len(set(self.missing_fields)):
            raise ValueError("missing_fields must be unique")
        return self


class EligibilityResultSchemaV04(ContractModel):
    result_id: EntityId
    status: EligibilityStatus
    rule_evaluations: tuple[RuleEvaluationSchemaV04, ...] = Field(min_length=1)
    satisfied_rule_ids: tuple[EntityId, ...]
    conflict_rule_ids: tuple[EntityId, ...]
    unknown_rule_ids: tuple[EntityId, ...]
    missing_fields: tuple[RuleField, ...]
    review_reasons: tuple[NonEmptyString, ...]
    evaluated_at: Instant
    engine_version: NonEmptyString

    @model_validator(mode="after")
    def require_consistent_outcomes_and_protected_ineligible(self) -> Self:
        evaluations_by_id = {item.rule_id: item for item in self.rule_evaluations}
        if len(evaluations_by_id) != len(self.rule_evaluations):
            raise ValueError("rule evaluations must use unique rule IDs")
        expected = {
            outcome: {
                item.rule_id for item in self.rule_evaluations if item.outcome is outcome
            }
            for outcome in RuleOutcome
        }
        provided = {
            RuleOutcome.SATISFIED: self._require_unique_ids(
                self.satisfied_rule_ids, "satisfied_rule_ids"
            ),
            RuleOutcome.CONFLICT: self._require_unique_ids(
                self.conflict_rule_ids, "conflict_rule_ids"
            ),
            RuleOutcome.UNKNOWN: self._require_unique_ids(
                self.unknown_rule_ids, "unknown_rule_ids"
            ),
        }
        if expected != provided:
            raise ValueError("outcome ID lists must match rule evaluation outcomes")
        if len(self.missing_fields) != len(set(self.missing_fields)):
            raise ValueError("missing_fields must be unique")
        if len(self.review_reasons) != len(set(self.review_reasons)):
            raise ValueError("review_reasons must be unique")
        if self.status is EligibilityStatus.INELIGIBLE:
            official_conflicts = [
                item
                for item in self.rule_evaluations
                if item.outcome is RuleOutcome.CONFLICT
                and item.deterministic
                and item.official_evidence
                and item.evidence_ref_ids
            ]
            if not official_conflicts:
                raise ValueError("INELIGIBLE requires an official deterministic conflict")
        return self

    @staticmethod
    def _require_unique_ids(value: tuple[EntityId, ...], name: str) -> set[EntityId]:
        if len(value) != len(set(value)):
            raise ValueError(f"{name} must be unique")
        return set(value)


class MatchSnapshotSchemaV04(ContractModel):
    snapshot_id: EntityId
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    rule_set_id: EntityId
    rule_set_version: VersionNumber
    profile_snapshot_id: EntityId
    profile_version: VersionNumber
    eligibility_result: EligibilityResultSchemaV04
    compiler_version: NonEmptyString
    engine_version: NonEmptyString
    major_catalog_version: NonEmptyString
    major_mapping_version: NonEmptyString
    scenario_clock: date
    input_sha256: Sha256
    created_at: Instant

    @model_validator(mode="after")
    def require_consistent_engine_version(self) -> Self:
        if self.engine_version != self.eligibility_result.engine_version:
            raise ValueError("engine_version must match eligibility_result")
        return self


class EvaluationCaseResultSchemaV04(ContractModel):
    case_id: NonEmptyString
    expected_status: EligibilityStatus
    actual_status: EligibilityStatus
    passed: bool
    match_snapshot_id: EntityId
    input_sha256: Sha256
    unexpected_ineligible: bool
    reason_codes: tuple[NonEmptyString, ...]

    @model_validator(mode="after")
    def require_consistent_pass_and_unique_reasons(self) -> Self:
        if self.passed != (self.expected_status is self.actual_status):
            raise ValueError("passed must match expected and actual status equality")
        expected_unexpected = (
            self.actual_status is EligibilityStatus.INELIGIBLE
            and self.expected_status is not EligibilityStatus.INELIGIBLE
        )
        if self.unexpected_ineligible != expected_unexpected:
            raise ValueError("unexpected_ineligible must match expected and actual status")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason_codes must be unique")
        return self


class EvaluationMetricsSchemaV04(ContractModel):
    total_cases: int = Field(ge=1)
    passed_cases: int = Field(ge=0)
    expected_ineligible_count: int = Field(ge=0)
    actual_ineligible_count: int = Field(ge=0)
    unexpected_ineligible_count: int = Field(ge=0)
    unexpected_ineligible_case_ids: tuple[NonEmptyString, ...]
    replay_mismatch_count: int = Field(ge=0)
    status_counts: dict[EligibilityStatus, int]

    @model_validator(mode="after")
    def require_bounded_counts(self) -> Self:
        if set(self.status_counts) != set(EligibilityStatus):
            raise ValueError("status_counts must contain every eligibility status")
        if any(count < 0 for count in self.status_counts.values()):
            raise ValueError("status_counts must be non-negative")
        if sum(self.status_counts.values()) != self.total_cases:
            raise ValueError("status_counts must sum to total_cases")
        if self.passed_cases > self.total_cases:
            raise ValueError("passed_cases must not exceed total_cases")
        if self.unexpected_ineligible_count > self.total_cases:
            raise ValueError("unexpected_ineligible_count must not exceed total_cases")
        if self.expected_ineligible_count > self.total_cases:
            raise ValueError("expected_ineligible_count must not exceed total_cases")
        if self.actual_ineligible_count > self.total_cases:
            raise ValueError("actual_ineligible_count must not exceed total_cases")
        if self.unexpected_ineligible_count != len(self.unexpected_ineligible_case_ids):
            raise ValueError("unexpected ineligible count must match case IDs")
        if len(self.unexpected_ineligible_case_ids) != len(
            set(self.unexpected_ineligible_case_ids)
        ):
            raise ValueError("unexpected ineligible case IDs must be unique")
        if self.replay_mismatch_count > self.total_cases:
            raise ValueError("replay_mismatch_count must not exceed total_cases")
        return self


class EvaluationComponentVersionsSchemaV04(ContractModel):
    contract: Literal["0.4.0"]
    compiler: NonEmptyString
    engine: NonEmptyString
    major_catalog: NonEmptyString
    major_mapping: NonEmptyString


class EvaluationRunSchemaV04(ContractModel):
    run_id: EntityId
    dataset_id: NonEmptyString
    dataset_version: NonEmptyString
    dataset_sha256: Sha256
    evidence_label: Literal["SYNTHETIC_EVALUATION_ONLY"]
    scenario_clock: Instant
    report_sha256: Sha256
    component: EvaluationComponent
    component_versions: EvaluationComponentVersionsSchemaV04
    synthetic: bool
    status: EvaluationRunStatus
    case_results: tuple[EvaluationCaseResultSchemaV04, ...]
    metrics: EvaluationMetricsSchemaV04 | None
    started_at: Instant
    completed_at: Instant | None
    error_summary: NonEmptyString | None

    @model_validator(mode="after")
    def require_status_shape_and_metrics(self) -> Self:
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must not be before started_at")
        if len({item.case_id for item in self.case_results}) != len(self.case_results):
            raise ValueError("case IDs must be unique")
        if self.status is EvaluationRunStatus.RUNNING:
            if (
                self.completed_at is not None
                or self.metrics is not None
                or self.error_summary is not None
            ):
                raise ValueError("RUNNING forbids completion fields")
        elif self.status is EvaluationRunStatus.COMPLETED:
            if self.completed_at is None or self.metrics is None or not self.case_results:
                raise ValueError("COMPLETED requires completed_at, case_results and metrics")
            if self.error_summary is not None:
                raise ValueError("COMPLETED forbids error_summary")
            self._require_metrics_match_results()
        elif self.completed_at is None or self.error_summary is None:
            raise ValueError("FAILED requires completed_at and error_summary")
        return self

    def _require_metrics_match_results(self) -> None:
        assert self.metrics is not None
        expected_counts = {status: 0 for status in EligibilityStatus}
        for result in self.case_results:
            expected_counts[result.actual_status] += 1
        unexpected_ineligible = sum(
            result.actual_status is EligibilityStatus.INELIGIBLE
            and result.expected_status is not EligibilityStatus.INELIGIBLE
            for result in self.case_results
        )
        replay_mismatches = sum(
            "REPLAY_MISMATCH" in result.reason_codes for result in self.case_results
        )
        unexpected_case_ids = tuple(
            result.case_id for result in self.case_results if result.unexpected_ineligible
        )
        expected_ineligible = sum(
            result.expected_status is EligibilityStatus.INELIGIBLE
            for result in self.case_results
        )
        actual_ineligible = expected_counts[EligibilityStatus.INELIGIBLE]
        if (
            self.metrics.total_cases != len(self.case_results)
            or self.metrics.passed_cases != sum(result.passed for result in self.case_results)
            or self.metrics.status_counts != expected_counts
            or self.metrics.unexpected_ineligible_count != unexpected_ineligible
            or self.metrics.expected_ineligible_count != expected_ineligible
            or self.metrics.actual_ineligible_count != actual_ineligible
            or self.metrics.unexpected_ineligible_case_ids != unexpected_case_ids
            or self.metrics.replay_mismatch_count != replay_mismatches
        ):
            raise ValueError("metrics must match case_results")


__all__ = [
    "EducationLevel",
    "EligibilityResultSchemaV04",
    "EligibilityStatus",
    "EvaluationCaseResultSchemaV04",
    "EvaluationComponent",
    "EvaluationComponentVersionsSchemaV04",
    "EvaluationMetricsSchemaV04",
    "EvaluationRunSchemaV04",
    "EvaluationRunStatus",
    "EvidenceRelation",
    "MatchSnapshotSchemaV04",
    "ProfileAttributesSchemaV04",
    "ProfileSnapshotSchemaV04",
    "RuleEvaluationSchemaV04",
    "RuleEvidenceAuthority",
    "RuleEvidenceSchemaV04",
    "RuleField",
    "RuleOperator",
    "RuleOutcome",
    "RuleSchemaV04",
    "RuleSetSchemaV04",
    "RuleValueType",
    "StudentStatus",
]
