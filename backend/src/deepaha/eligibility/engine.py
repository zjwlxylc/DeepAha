from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from deepaha.contracts.phase4 import (
    EducationLevel,
    EligibilityStatus,
    RuleField,
    RuleOperator,
    RuleOutcome,
    RuleValueType,
)
from deepaha.rules.major import (
    ApprovedMajorMapping,
    MajorCatalog,
    MajorMatchKind,
    match_major,
)
from deepaha.rules.types import CompiledRule, CompiledRuleSet

ENGINE_VERSION = "phase4-eligibility-engine-v1"
_OFFICIAL_PRECEDENCE_FLOOR = 300
_EDUCATION_ORDER = {
    level.value: rank
    for rank, level in enumerate(
        (
            EducationLevel.SECONDARY,
            EducationLevel.ASSOCIATE,
            EducationLevel.BACHELOR,
            EducationLevel.MASTER,
            EducationLevel.DOCTORATE,
        )
    )
}


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    rule_set: CompiledRuleSet
    profile_attributes: Mapping[str, object]
    major_catalog: MajorCatalog
    major_mapping: ApprovedMajorMapping
    scenario_clock: date
    semantic_major_candidate: bool = False


@dataclass(frozen=True, slots=True)
class EvaluatedRule:
    rule_id: UUID
    outcome: RuleOutcome
    deterministic: bool
    official_evidence: bool
    reason_code: str
    evidence_ref_ids: tuple[UUID, ...]
    missing_fields: tuple[RuleField, ...]


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    status: EligibilityStatus
    rule_evaluations: tuple[EvaluatedRule, ...]
    satisfied_rule_ids: tuple[UUID, ...]
    conflict_rule_ids: tuple[UUID, ...]
    unknown_rule_ids: tuple[UUID, ...]
    missing_fields: tuple[RuleField, ...]
    review_reasons: tuple[str, ...]
    engine_version: str = ENGINE_VERSION


def evaluate_eligibility(context: EvaluationContext) -> EligibilityDecision:
    evaluations_by_id: dict[UUID, EvaluatedRule] = {}
    for rule in context.rule_set.rules:
        if rule.operator in {RuleOperator.AND, RuleOperator.OR, RuleOperator.NOT}:
            evaluation = _evaluate_composite(rule, evaluations_by_id)
        else:
            evaluation = _evaluate_atomic(rule, context)
        evaluations_by_id[rule.rule_id] = evaluation
    evaluations = tuple(evaluations_by_id[rule.rule_id] for rule in context.rule_set.rules)
    root_evaluations = tuple(
        evaluations_by_id[rule_id] for rule_id in context.rule_set.root_rule_ids
    )
    status = _aggregate_status(root_evaluations)
    review_reasons = _review_reasons(evaluations, status)
    return EligibilityDecision(
        status=status,
        rule_evaluations=evaluations,
        satisfied_rule_ids=tuple(
            item.rule_id for item in evaluations if item.outcome is RuleOutcome.SATISFIED
        ),
        conflict_rule_ids=tuple(
            item.rule_id for item in evaluations if item.outcome is RuleOutcome.CONFLICT
        ),
        unknown_rule_ids=tuple(
            item.rule_id for item in evaluations if item.outcome is RuleOutcome.UNKNOWN
        ),
        missing_fields=tuple(
            sorted({field for item in evaluations for field in item.missing_fields})
        ),
        review_reasons=review_reasons,
    )


def _evaluate_atomic(rule: CompiledRule, context: EvaluationContext) -> EvaluatedRule:
    evidence_ids = tuple(item.evidence_ref_id for item in rule.evidence)
    official = (
        rule.effective_precedence is not None
        and rule.effective_precedence >= _OFFICIAL_PRECEDENCE_FLOOR
    )
    if rule.evidence_conflicted:
        return _evaluation(
            rule,
            RuleOutcome.UNKNOWN,
            deterministic=False,
            official=False,
            reason="EVIDENCE_CONFLICT",
            evidence_ids=evidence_ids,
        )
    effective_evidence = tuple(
        item for item in rule.evidence if item.precedence == rule.effective_precedence
    )
    if effective_evidence and all(
        item.relation.value == "CONTRADICTS" for item in effective_evidence
    ):
        return _evaluation(
            rule,
            RuleOutcome.UNKNOWN,
            deterministic=False,
            official=False,
            reason="EVIDENCE_CONTRADICTS_RULE",
            evidence_ids=evidence_ids,
        )
    assert rule.field is not None
    field_name = rule.field.value
    raw_value = context.profile_attributes.get(field_name)
    if raw_value is None:
        if rule.operator is RuleOperator.NOT_EXISTS:
            return _evaluation(
                rule,
                RuleOutcome.SATISFIED,
                deterministic=True,
                official=official,
                reason="FIELD_CONFIRMED_ABSENT",
                evidence_ids=evidence_ids,
            )
        return _evaluation(
            rule,
            RuleOutcome.UNKNOWN,
            deterministic=False,
            official=False,
            reason="FIELD_MISSING",
            evidence_ids=evidence_ids,
            missing_fields=(rule.field,),
        )
    if rule.operator is RuleOperator.EXISTS:
        return _evaluation(
            rule,
            RuleOutcome.SATISFIED,
            deterministic=True,
            official=official,
            reason="FIELD_PRESENT",
            evidence_ids=evidence_ids,
        )
    if rule.operator is RuleOperator.NOT_EXISTS:
        return _evaluation(
            rule,
            RuleOutcome.CONFLICT,
            deterministic=True,
            official=official,
            reason="FIELD_PRESENT_WHEN_FORBIDDEN",
            evidence_ids=evidence_ids,
        )
    if rule.field is RuleField.MAJOR_CODE:
        return _evaluate_major(rule, str(raw_value), context, evidence_ids, official)
    normalized = _normalize_profile_value(rule, raw_value, context.scenario_clock)
    if normalized.reason_code is not None:
        return _evaluation(
            rule,
            RuleOutcome.UNKNOWN,
            deterministic=False,
            official=False,
            reason=normalized.reason_code,
            evidence_ids=evidence_ids,
        )
    matches = _compare(rule, normalized.value)
    return _evaluation(
        rule,
        RuleOutcome.SATISFIED if matches else RuleOutcome.CONFLICT,
        deterministic=True,
        official=official,
        reason="RULE_SATISFIED" if matches else "RULE_CONFLICT",
        evidence_ids=evidence_ids,
    )


def _evaluate_major(
    rule: CompiledRule,
    profile_code: str,
    context: EvaluationContext,
    evidence_ids: tuple[UUID, ...],
    official_rule_evidence: bool,
) -> EvaluatedRule:
    accepted_codes = tuple(str(item) for item in _list_value(rule.value))
    result = match_major(
        profile_code,
        accepted_codes,
        context.major_catalog,
        context.major_mapping,
        semantic_candidate=context.semantic_major_candidate,
    )
    if result.kind in {MajorMatchKind.EXACT, MajorMatchKind.CATALOG}:
        return _evaluation(
            rule,
            RuleOutcome.SATISFIED,
            deterministic=True,
            official=official_rule_evidence and result.official_conclusion,
            reason=result.reason_code,
            evidence_ids=evidence_ids,
        )
    if result.kind is MajorMatchKind.APPROVED_MAPPING:
        return _evaluation(
            rule,
            RuleOutcome.SATISFIED,
            deterministic=True,
            official=False,
            reason=result.reason_code,
            evidence_ids=evidence_ids,
        )
    if result.kind is MajorMatchKind.NO_MATCH:
        return _evaluation(
            rule,
            RuleOutcome.CONFLICT,
            deterministic=True,
            official=official_rule_evidence and result.official_conclusion,
            reason=result.reason_code,
            evidence_ids=evidence_ids,
        )
    missing = (RuleField.MAJOR_CODE,) if result.kind is MajorMatchKind.MISSING else ()
    return _evaluation(
        rule,
        RuleOutcome.UNKNOWN,
        deterministic=False,
        official=False,
        reason=result.reason_code,
        evidence_ids=evidence_ids,
        missing_fields=missing,
    )


@dataclass(frozen=True, slots=True)
class _NormalizedValue:
    value: object
    reason_code: str | None = None


def _normalize_profile_value(
    rule: CompiledRule,
    raw_value: object,
    scenario_clock: date,
) -> _NormalizedValue:
    if rule.value_type is RuleValueType.INTEGER:
        if not isinstance(raw_value, int) or isinstance(raw_value, bool):
            return _NormalizedValue(None, "PROFILE_FIELD_TYPE_MISMATCH")
        return _NormalizedValue(raw_value)
    if rule.value_type is RuleValueType.DATE:
        parsed = _as_date(raw_value)
        if parsed is None:
            return _NormalizedValue(None, "PROFILE_FIELD_TYPE_MISMATCH")
        if rule.field is RuleField.BIRTH_DATE and parsed > scenario_clock:
            return _NormalizedValue(None, "PROFILE_DATE_AFTER_SCENARIO_CLOCK")
        return _NormalizedValue(parsed)
    if rule.value_type is RuleValueType.STRING_SET:
        if not isinstance(raw_value, (list, tuple, set, frozenset)):
            return _NormalizedValue(None, "PROFILE_FIELD_TYPE_MISMATCH")
        if not all(isinstance(item, str) and item.strip() for item in raw_value):
            return _NormalizedValue(None, "PROFILE_FIELD_TYPE_MISMATCH")
        return _NormalizedValue(frozenset(str(item).strip() for item in raw_value))
    if rule.value_type is RuleValueType.BOOLEAN:
        if not isinstance(raw_value, bool):
            return _NormalizedValue(None, "PROFILE_FIELD_TYPE_MISMATCH")
        return _NormalizedValue(raw_value)
    if not isinstance(raw_value, str) or not raw_value.strip():
        return _NormalizedValue(None, "PROFILE_FIELD_TYPE_MISMATCH")
    if rule.field is RuleField.EDUCATION_LEVEL and raw_value not in _EDUCATION_ORDER:
        return _NormalizedValue(None, "PROFILE_FIELD_VALUE_UNKNOWN")
    return _NormalizedValue(raw_value.strip())


def _compare(rule: CompiledRule, actual: object) -> bool:
    expected = rule.value
    if rule.field is RuleField.EDUCATION_LEVEL:
        return _compare_ordered(rule.operator, _education_rank(actual), _education_values(expected))
    if rule.value_type is RuleValueType.DATE:
        return _compare_ordered(rule.operator, actual, _date_values(expected))
    if rule.operator is RuleOperator.EQ:
        return actual == expected
    if rule.operator is RuleOperator.NE:
        return actual != expected
    if rule.operator is RuleOperator.IN:
        return actual in _list_value(expected)
    if rule.operator is RuleOperator.NOT_IN:
        return actual not in _list_value(expected)
    if rule.operator is RuleOperator.GTE:
        return isinstance(actual, int) and isinstance(expected, int) and actual >= expected
    if rule.operator is RuleOperator.LTE:
        return isinstance(actual, int) and isinstance(expected, int) and actual <= expected
    if rule.operator is RuleOperator.BETWEEN:
        values = _list_value(expected)
        return (
            isinstance(actual, int)
            and len(values) == 2
            and isinstance(values[0], int)
            and isinstance(values[1], int)
            and values[0] <= actual <= values[1]
        )
    if rule.operator is RuleOperator.CONTAINS_ANY:
        return isinstance(actual, frozenset) and bool(actual & set(_list_value(expected)))
    if rule.operator is RuleOperator.CONTAINS_ALL:
        return isinstance(actual, frozenset) and set(_list_value(expected)) <= actual
    return False


def _education_rank(value: object) -> int:
    if not isinstance(value, str) or value not in _EDUCATION_ORDER:
        return -1
    return _EDUCATION_ORDER[value]


def _education_values(value: object) -> tuple[int, ...]:
    raw_values = _list_value(value) if isinstance(value, list) else (value,)
    return tuple(_education_rank(item) for item in raw_values)


def _date_values(value: object) -> tuple[date, ...]:
    raw_values = _list_value(value) if isinstance(value, list) else (value,)
    parsed = tuple(_as_date(item) for item in raw_values)
    return tuple(item for item in parsed if item is not None)


def _compare_ordered(operator: RuleOperator, actual: object, expected: tuple[object, ...]) -> bool:
    if not expected:
        return False
    if operator is RuleOperator.EQ:
        return actual == expected[0]
    if operator is RuleOperator.NE:
        return actual != expected[0]
    if operator is RuleOperator.IN:
        return actual in expected
    if operator is RuleOperator.NOT_IN:
        return actual not in expected
    if isinstance(actual, int):
        integer_values: list[int] = []
        for item in expected:
            if not isinstance(item, int):
                return False
            integer_values.append(item)
        if operator is RuleOperator.GTE:
            return actual >= integer_values[0]
        if operator is RuleOperator.LTE:
            return actual <= integer_values[0]
        if operator is RuleOperator.BETWEEN and len(integer_values) == 2:
            return integer_values[0] <= actual <= integer_values[1]
    if isinstance(actual, date):
        date_values: list[date] = []
        for item in expected:
            if not isinstance(item, date):
                return False
            date_values.append(item)
        if operator is RuleOperator.GTE:
            return actual >= date_values[0]
        if operator is RuleOperator.LTE:
            return actual <= date_values[0]
        if operator is RuleOperator.BETWEEN and len(date_values) == 2:
            return date_values[0] <= actual <= date_values[1]
    return False


def _as_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _list_value(value: object) -> tuple[object, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(value)


def _evaluate_composite(
    rule: CompiledRule,
    evaluations_by_id: Mapping[UUID, EvaluatedRule],
) -> EvaluatedRule:
    operands = tuple(evaluations_by_id[rule_id] for rule_id in rule.operand_rule_ids)
    if rule.operator is RuleOperator.NOT:
        source = operands[0]
        outcome = {
            RuleOutcome.SATISFIED: RuleOutcome.CONFLICT,
            RuleOutcome.CONFLICT: RuleOutcome.SATISFIED,
            RuleOutcome.UNKNOWN: RuleOutcome.UNKNOWN,
        }[source.outcome]
        return _evaluation(
            rule,
            outcome,
            deterministic=source.deterministic,
            official=source.official_evidence,
            reason=f"NOT_{source.reason_code}",
            evidence_ids=source.evidence_ref_ids,
            missing_fields=source.missing_fields,
        )
    if rule.operator is RuleOperator.AND:
        if any(item.outcome is RuleOutcome.CONFLICT for item in operands):
            selected = tuple(item for item in operands if item.outcome is RuleOutcome.CONFLICT)
            outcome = RuleOutcome.CONFLICT
        elif any(item.outcome is RuleOutcome.UNKNOWN for item in operands):
            selected = tuple(item for item in operands if item.outcome is RuleOutcome.UNKNOWN)
            outcome = RuleOutcome.UNKNOWN
        else:
            selected = operands
            outcome = RuleOutcome.SATISFIED
    elif any(item.outcome is RuleOutcome.SATISFIED for item in operands):
        selected = tuple(item for item in operands if item.outcome is RuleOutcome.SATISFIED)
        outcome = RuleOutcome.SATISFIED
    elif any(item.outcome is RuleOutcome.UNKNOWN for item in operands):
        selected = tuple(item for item in operands if item.outcome is RuleOutcome.UNKNOWN)
        outcome = RuleOutcome.UNKNOWN
    else:
        selected = operands
        outcome = RuleOutcome.CONFLICT
    if outcome is RuleOutcome.SATISFIED and rule.operator is RuleOperator.AND:
        official = all(item.official_evidence for item in selected)
    else:
        official = any(item.official_evidence and item.deterministic for item in selected)
    return _evaluation(
        rule,
        outcome,
        deterministic=all(item.deterministic for item in selected),
        official=official,
        reason=f"{rule.operator.value}_{outcome.value}",
        evidence_ids=_unique_ids(item.evidence_ref_ids for item in selected),
        missing_fields=tuple(sorted({field for item in selected for field in item.missing_fields})),
    )


def _aggregate_status(root_evaluations: tuple[EvaluatedRule, ...]) -> EligibilityStatus:
    if any(
        item.outcome is RuleOutcome.CONFLICT
        and item.deterministic
        and item.official_evidence
        and item.evidence_ref_ids
        for item in root_evaluations
    ):
        return EligibilityStatus.INELIGIBLE
    if any(item.outcome is not RuleOutcome.SATISFIED for item in root_evaluations):
        return EligibilityStatus.UNCERTAIN
    if any(not item.official_evidence for item in root_evaluations):
        return EligibilityStatus.LIKELY_ELIGIBLE
    return EligibilityStatus.ELIGIBLE


def _review_reasons(
    evaluations: tuple[EvaluatedRule, ...],
    status: EligibilityStatus,
) -> tuple[str, ...]:
    reasons: list[str] = []
    for item in evaluations:
        if item.outcome is RuleOutcome.UNKNOWN or not item.official_evidence:
            reasons.append(item.reason_code)
        if item.outcome is RuleOutcome.CONFLICT and not item.official_evidence:
            reasons.append("LOW_AUTHORITY_CONFLICT")
    if status is EligibilityStatus.LIKELY_ELIGIBLE and not reasons:
        reasons.append("NON_OFFICIAL_POSITIVE_SUPPORT")
    return tuple(dict.fromkeys(reasons))


def _evaluation(
    rule: CompiledRule,
    outcome: RuleOutcome,
    *,
    deterministic: bool,
    official: bool,
    reason: str,
    evidence_ids: tuple[UUID, ...],
    missing_fields: tuple[RuleField, ...] = (),
) -> EvaluatedRule:
    return EvaluatedRule(
        rule_id=rule.rule_id,
        outcome=outcome,
        deterministic=deterministic,
        official_evidence=official,
        reason_code=reason,
        evidence_ref_ids=evidence_ids,
        missing_fields=missing_fields,
    )


def _unique_ids(groups: Iterable[Iterable[UUID]]) -> tuple[UUID, ...]:
    ordered: dict[UUID, None] = {}
    for group in groups:
        for item in group:
            ordered[item] = None
    return tuple(ordered)


__all__ = [
    "ENGINE_VERSION",
    "EligibilityDecision",
    "EvaluatedRule",
    "EvaluationContext",
    "evaluate_eligibility",
]
