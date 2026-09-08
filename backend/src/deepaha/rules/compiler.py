import json
from datetime import date
from hashlib import sha256
from uuid import UUID

from deepaha.contracts.phase4 import (
    RuleEvidenceSchemaV04,
    RuleField,
    RuleOperator,
    RuleSchemaV04,
    RuleSetSchemaV04,
    RuleValueType,
)
from deepaha.rules.types import (
    FIELD_REGISTRY,
    CompiledEvidence,
    CompiledRule,
    CompiledRuleSet,
    RuleCompileError,
)

COMPILER_VERSION = "phase4-rule-compiler-v1"
_COMPOSITE_OPERATORS = frozenset({RuleOperator.AND, RuleOperator.OR, RuleOperator.NOT})
_LIST_OPERATORS = frozenset(
    {
        RuleOperator.IN,
        RuleOperator.NOT_IN,
        RuleOperator.BETWEEN,
        RuleOperator.CONTAINS_ANY,
        RuleOperator.CONTAINS_ALL,
    }
)


def compile_rule_set(rule_set: RuleSetSchemaV04) -> CompiledRuleSet:
    compiled_rules = compile_rule_graph(rule_set.rules, rule_set.root_rule_ids)
    compiled_sha256 = _compiled_hash(rule_set, compiled_rules)
    return CompiledRuleSet(
        rule_set_id=rule_set.rule_set_id,
        version=rule_set.version,
        opportunity_id=rule_set.opportunity_id,
        opportunity_version=rule_set.opportunity_version,
        root_rule_ids=rule_set.root_rule_ids,
        rules=compiled_rules,
        compiled_sha256=compiled_sha256,
        compiler_version=COMPILER_VERSION,
    )


def compile_rule_graph(
    rules: tuple[RuleSchemaV04, ...], root_rule_ids: tuple[UUID, ...]
) -> tuple[CompiledRule, ...]:
    """Validate graph semantics without manufacturing an opportunity identity."""
    rules_by_id = _index_rules(rules)
    _validate_roots(root_rule_ids, rules_by_id)
    for rule in rules:
        _validate_rule(rule, rules_by_id)
    ordered_rule_ids = _topological_order(root_rule_ids, rules_by_id)
    return tuple(_compile_rule(rules_by_id[rule_id]) for rule_id in ordered_rule_ids)


def _index_rules(rules: tuple[RuleSchemaV04, ...]) -> dict[UUID, RuleSchemaV04]:
    indexed: dict[UUID, RuleSchemaV04] = {}
    codes: set[str] = set()
    for rule in rules:
        if rule.rule_id in indexed:
            raise RuleCompileError("DUPLICATE_RULE_ID", f"duplicate rule {rule.rule_id}")
        if rule.code in codes:
            raise RuleCompileError("DUPLICATE_RULE_CODE", f"duplicate rule code {rule.code}")
        indexed[rule.rule_id] = rule
        codes.add(rule.code)
    if not indexed:
        raise RuleCompileError("EMPTY_RULE_SET", "RuleSet must contain at least one rule")
    return indexed


def _validate_roots(
    root_rule_ids: tuple[UUID, ...],
    rules_by_id: dict[UUID, RuleSchemaV04],
) -> None:
    if not root_rule_ids:
        raise RuleCompileError("MISSING_ROOT", "RuleSet requires a root rule")
    if len(root_rule_ids) != len(set(root_rule_ids)):
        raise RuleCompileError("DUPLICATE_ROOT", "root rule IDs must be unique")
    missing = [rule_id for rule_id in root_rule_ids if rule_id not in rules_by_id]
    if missing:
        raise RuleCompileError("MISSING_ROOT", f"unknown root rule {missing[0]}")


def _validate_rule(rule: RuleSchemaV04, rules_by_id: dict[UUID, RuleSchemaV04]) -> None:
    if not isinstance(rule.operator, RuleOperator):
        raise RuleCompileError("UNKNOWN_OPERATOR", f"unknown operator {rule.operator}")
    if rule.operator in _COMPOSITE_OPERATORS:
        _validate_composite_rule(rule, rules_by_id)
        return
    _validate_atomic_rule(rule)


def _validate_composite_rule(
    rule: RuleSchemaV04,
    rules_by_id: dict[UUID, RuleSchemaV04],
) -> None:
    operands = rule.operand_rule_ids
    if rule.operator is RuleOperator.NOT and len(operands) != 1:
        raise RuleCompileError("INVALID_ARITY", "NOT requires exactly one operand")
    if rule.operator in {RuleOperator.AND, RuleOperator.OR} and len(operands) < 2:
        raise RuleCompileError("INVALID_ARITY", "AND and OR require at least two operands")
    if len(operands) != len(set(operands)):
        raise RuleCompileError("DUPLICATE_OPERAND", f"duplicate operand in {rule.code}")
    missing = [rule_id for rule_id in operands if rule_id not in rules_by_id]
    if missing:
        raise RuleCompileError("MISSING_OPERAND", f"unknown operand rule {missing[0]}")
    if rule.field is not None or rule.value_type is not None or rule.value is not None:
        raise RuleCompileError("INVALID_COMPOSITE_SHAPE", f"composite rule {rule.code} has a value")
    if rule.evidence:
        raise RuleCompileError(
            "INVALID_COMPOSITE_SHAPE", f"composite rule {rule.code} has direct evidence"
        )


def _validate_atomic_rule(rule: RuleSchemaV04) -> None:
    if not isinstance(rule.field, RuleField):
        raise RuleCompileError("UNKNOWN_FIELD", f"unknown field {rule.field}")
    field_spec = FIELD_REGISTRY.get(rule.field.value)
    if field_spec is None:
        raise RuleCompileError("UNKNOWN_FIELD", f"unknown field {rule.field}")
    if (
        not isinstance(rule.value_type, RuleValueType)
        or rule.value_type is not field_spec.value_type
    ):
        raise RuleCompileError(
            "TYPE_MISMATCH",
            f"field {rule.field.value} requires {field_spec.value_type.value}",
        )
    if rule.operator not in field_spec.operators:
        raise RuleCompileError(
            "OPERATOR_NOT_ALLOWED",
            f"operator {rule.operator.value} is not allowed for {rule.field.value}",
        )
    if rule.operand_rule_ids:
        raise RuleCompileError("INVALID_ATOMIC_SHAPE", f"atomic rule {rule.code} has operands")
    if rule.required and not rule.evidence:
        raise RuleCompileError("MISSING_EVIDENCE", f"required rule {rule.code} has no evidence")
    _validate_literal(rule)


def _validate_literal(rule: RuleSchemaV04) -> None:
    if rule.operator in {RuleOperator.EXISTS, RuleOperator.NOT_EXISTS}:
        if rule.value is not None:
            raise RuleCompileError("TYPE_MISMATCH", "existence operators forbid values")
        return
    values = rule.value if rule.operator in _LIST_OPERATORS else [rule.value]
    if not isinstance(values, list) or not values:
        raise RuleCompileError("TYPE_MISMATCH", f"operator {rule.operator.value} requires values")
    if rule.operator is RuleOperator.BETWEEN and len(values) != 2:
        raise RuleCompileError("TYPE_MISMATCH", "BETWEEN requires two values")
    if rule.value_type is RuleValueType.STRING:
        valid = all(isinstance(value, str) and bool(value.strip()) for value in values)
    elif rule.value_type is RuleValueType.INTEGER:
        valid = all(isinstance(value, int) and not isinstance(value, bool) for value in values)
    elif rule.value_type is RuleValueType.DATE:
        valid = all(_is_iso_date(value) for value in values)
    elif rule.value_type is RuleValueType.STRING_SET:
        valid = all(isinstance(value, str) and bool(value.strip()) for value in values)
    elif rule.value_type is RuleValueType.BOOLEAN:
        valid = all(isinstance(value, bool) for value in values)
    else:
        valid = False
    if not valid:
        raise RuleCompileError("TYPE_MISMATCH", f"invalid value for {rule.value_type}")


def _is_iso_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _topological_order(
    root_rule_ids: tuple[UUID, ...],
    rules_by_id: dict[UUID, RuleSchemaV04],
) -> tuple[UUID, ...]:
    visiting: set[UUID] = set()
    visited: set[UUID] = set()
    ordered: list[UUID] = []

    def visit(rule_id: UUID) -> None:
        if rule_id in visiting:
            raise RuleCompileError("CYCLE", f"cycle reaches rule {rule_id}")
        if rule_id in visited:
            return
        visiting.add(rule_id)
        for operand_id in rules_by_id[rule_id].operand_rule_ids:
            visit(operand_id)
        visiting.remove(rule_id)
        visited.add(rule_id)
        ordered.append(rule_id)

    for root_rule_id in root_rule_ids:
        visit(root_rule_id)
    unreachable = set(rules_by_id) - visited
    if unreachable:
        first = min(unreachable, key=str)
        raise RuleCompileError("UNREACHABLE_RULE", f"rule {first} is unreachable")
    return tuple(ordered)


def _compile_rule(rule: RuleSchemaV04) -> CompiledRule:
    evidence = tuple(_compile_evidence(item) for item in _ordered_evidence(rule.evidence))
    effective_precedence = evidence[0].precedence if evidence else None
    highest_relations = {
        item.relation for item in evidence if item.precedence == effective_precedence
    }
    return CompiledRule(
        rule_id=rule.rule_id,
        code=rule.code,
        operator=rule.operator,
        field=rule.field,
        value_type=rule.value_type,
        value=rule.value,
        operand_rule_ids=rule.operand_rule_ids,
        required=rule.required,
        reason_template=rule.reason_template,
        evidence=evidence,
        effective_precedence=effective_precedence,
        evidence_conflicted=len(highest_relations) > 1,
    )


def _ordered_evidence(
    evidence: tuple[RuleEvidenceSchemaV04, ...],
) -> tuple[RuleEvidenceSchemaV04, ...]:
    return tuple(sorted(evidence, key=lambda item: (-item.precedence, str(item.evidence_ref_id))))


def _compile_evidence(evidence: RuleEvidenceSchemaV04) -> CompiledEvidence:
    return CompiledEvidence(
        evidence_ref_id=evidence.evidence_ref_id,
        document_id=evidence.document_id,
        authority=evidence.authority,
        precedence=evidence.precedence,
        relation=evidence.relation,
        effective_at=evidence.effective_at,
        assertion_sha256=evidence.assertion_sha256,
    )


def _compiled_hash(
    rule_set: RuleSetSchemaV04,
    compiled_rules: tuple[CompiledRule, ...],
) -> str:
    payload = {
        "compiler_version": COMPILER_VERSION,
        "rule_set_id": str(rule_set.rule_set_id),
        "version": rule_set.version,
        "opportunity_id": str(rule_set.opportunity_id),
        "opportunity_version": rule_set.opportunity_version,
        "root_rule_ids": [str(item) for item in rule_set.root_rule_ids],
        "rules": [_rule_payload(rule) for rule in compiled_rules],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _rule_payload(rule: CompiledRule) -> dict[str, object]:
    return {
        "rule_id": str(rule.rule_id),
        "code": rule.code,
        "operator": rule.operator.value,
        "field": rule.field.value if rule.field else None,
        "value_type": rule.value_type.value if rule.value_type else None,
        "value": rule.value,
        "operand_rule_ids": [str(item) for item in rule.operand_rule_ids],
        "required": rule.required,
        "reason_template": rule.reason_template,
        "evidence": [
            {
                "evidence_ref_id": str(item.evidence_ref_id),
                "document_id": str(item.document_id),
                "authority": item.authority.value,
                "precedence": item.precedence,
                "relation": item.relation.value,
                "effective_at": item.effective_at.isoformat(),
                "assertion_sha256": item.assertion_sha256,
            }
            for item in rule.evidence
        ],
        "effective_precedence": rule.effective_precedence,
        "evidence_conflicted": rule.evidence_conflicted,
    }


__all__ = ["COMPILER_VERSION", "compile_rule_graph", "compile_rule_set"]
