from datetime import UTC, datetime
from uuid import UUID

import pytest

from deepaha.contracts.phase4 import (
    RuleEvidenceSchemaV04,
    RuleOperator,
    RuleSchemaV04,
    RuleSetSchemaV04,
)
from deepaha.rules.compiler import compile_rule_set
from deepaha.rules.types import FIELD_REGISTRY, RuleCompileError, RuleValueType

NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
RULE_SET_ID = UUID("019b1000-0000-7000-8000-000000000001")
OPPORTUNITY_ID = UUID("019b1000-0000-7000-8000-000000000002")
DOCUMENT_ID = UUID("019b1000-0000-7000-8000-000000000003")
EDUCATION_RULE_ID = UUID("019b1000-0000-7000-8000-000000000101")
CERTIFICATE_RULE_ID = UUID("019b1000-0000-7000-8000-000000000102")
AGE_RULE_ID = UUID("019b1000-0000-7000-8000-000000000103")
ROOT_RULE_ID = UUID("019b1000-0000-7000-8000-000000000104")
UNREACHABLE_RULE_ID = UUID("019b1000-0000-7000-8000-000000000105")
UNKNOWN_RULE_ID = UUID("019b1000-0000-7000-8000-000000000199")


def evidence(
    suffix: int,
    *,
    relation: str = "SUPPORTS",
    authority: str = "ORIGINAL_OFFICIAL_NOTICE",
    precedence: int = 400,
) -> RuleEvidenceSchemaV04:
    return RuleEvidenceSchemaV04.model_validate(
        {
            "evidence_ref_id": UUID(f"019b1000-0000-7000-8000-{suffix:012d}"),
            "document_id": DOCUMENT_ID,
            "authority": authority,
            "precedence": precedence,
            "relation": relation,
            "effective_at": NOW,
            "assertion_sha256": f"{suffix:x}"[-1] * 64,
        }
    )


def atomic_rule(
    rule_id: UUID,
    code: str,
    field: str,
    operator: str,
    value_type: str,
    value: object,
    *,
    rule_evidence: tuple[RuleEvidenceSchemaV04, ...] | None = None,
) -> RuleSchemaV04:
    return RuleSchemaV04.model_validate(
        {
            "rule_id": rule_id,
            "code": code,
            "operator": operator,
            "field": field,
            "value_type": value_type,
            "value": value,
            "operand_rule_ids": [],
            "required": True,
            "reason_template": f"Synthetic {code} rule",
            "evidence": rule_evidence or (evidence(int(str(rule_id)[-3:], 16) % 9 + 1),),
        }
    )


def composite_rule(
    rule_id: UUID,
    code: str,
    operator: str,
    operands: tuple[UUID, ...],
) -> RuleSchemaV04:
    return RuleSchemaV04.model_validate(
        {
            "rule_id": rule_id,
            "code": code,
            "operator": operator,
            "field": None,
            "value_type": None,
            "value": None,
            "operand_rule_ids": operands,
            "required": True,
            "reason_template": f"Synthetic {code} composition",
            "evidence": [],
        }
    )


def valid_rules() -> tuple[RuleSchemaV04, ...]:
    return (
        atomic_rule(
            EDUCATION_RULE_ID,
            "education",
            "education_level",
            "GTE",
            "STRING",
            "BACHELOR",
        ),
        atomic_rule(
            CERTIFICATE_RULE_ID,
            "certificate",
            "certificates",
            "CONTAINS_ALL",
            "STRING_SET",
            ["CET4"],
        ),
        atomic_rule(
            AGE_RULE_ID,
            "age",
            "birth_date",
            "BETWEEN",
            "DATE",
            ["2000-08-22", "2008-08-22"],
        ),
        composite_rule(
            ROOT_RULE_ID,
            "root",
            "AND",
            (EDUCATION_RULE_ID, CERTIFICATE_RULE_ID, AGE_RULE_ID),
        ),
    )


def rule_set(
    rules: tuple[RuleSchemaV04, ...] | None = None,
    roots: tuple[UUID, ...] = (ROOT_RULE_ID,),
) -> RuleSetSchemaV04:
    return RuleSetSchemaV04.model_validate(
        {
            "rule_set_id": RULE_SET_ID,
            "version": 1,
            "opportunity_id": OPPORTUNITY_ID,
            "opportunity_version": 1,
            "rules": rules or valid_rules(),
            "root_rule_ids": roots,
            "review_status": "APPROVED",
            "rule_schema_version": "0.4.0",
            "created_at": NOW,
        }
    )


def assert_compile_error(candidate: RuleSetSchemaV04, code: str) -> None:
    with pytest.raises(RuleCompileError) as captured:
        compile_rule_set(candidate)
    assert captured.value.code == code


def test_field_registry_is_closed_and_typed() -> None:
    assert set(FIELD_REGISTRY) == {
        "education_level",
        "major_code",
        "graduation_year",
        "student_status",
        "birth_date",
        "hukou_region",
        "residence_region",
        "target_regions",
        "certificates",
    }
    assert FIELD_REGISTRY["birth_date"].value_type is RuleValueType.DATE
    assert RuleOperator.BETWEEN in FIELD_REGISTRY["birth_date"].operators
    assert RuleOperator.CONTAINS_ALL in FIELD_REGISTRY["certificates"].operators


def test_compiler_emits_deterministic_topological_order_and_hash() -> None:
    first = compile_rule_set(rule_set())
    second = compile_rule_set(rule_set())
    assert tuple(item.code for item in first.rules) == (
        "education",
        "certificate",
        "age",
        "root",
    )
    assert first.compiled_sha256 == second.compiled_sha256
    assert first == second


def test_compiler_rejects_unknown_operator_even_if_contract_validation_is_bypassed() -> None:
    rules = valid_rules()
    invalid = rules[0].model_copy(update={"operator": "EXEC"})
    candidate = rule_set().model_copy(update={"rules": (invalid, *rules[1:])})
    assert_compile_error(candidate, "UNKNOWN_OPERATOR")


def test_compiler_rejects_unknown_field_even_if_contract_validation_is_bypassed() -> None:
    rules = valid_rules()
    invalid = rules[0].model_copy(update={"field": "profile.secret"})
    candidate = rule_set().model_copy(update={"rules": (invalid, *rules[1:])})
    assert_compile_error(candidate, "UNKNOWN_FIELD")


@pytest.mark.parametrize(
    "invalid_rule",
    [
        atomic_rule(
            EDUCATION_RULE_ID,
            "education",
            "education_level",
            "GTE",
            "INTEGER",
            1,
        ),
        atomic_rule(
            AGE_RULE_ID,
            "age",
            "birth_date",
            "BETWEEN",
            "DATE",
            ["not-a-date", "still-not-a-date"],
        ),
    ],
)
def test_compiler_rejects_declared_or_literal_type_mismatch(
    invalid_rule: RuleSchemaV04,
) -> None:
    rules = valid_rules()
    candidate_rules = tuple(
        invalid_rule if item.code == invalid_rule.code else item for item in rules
    )
    assert_compile_error(rule_set(candidate_rules), "TYPE_MISMATCH")


def test_compiler_rejects_operator_not_allowed_for_field() -> None:
    rules = valid_rules()
    invalid = rules[1].model_copy(update={"operator": RuleOperator.GTE, "value": "CET4"})
    candidate = rule_set().model_copy(update={"rules": (rules[0], invalid, *rules[2:])})
    assert_compile_error(candidate, "OPERATOR_NOT_ALLOWED")


def test_compiler_rejects_missing_operand_reference() -> None:
    rules = valid_rules()
    invalid_root = rules[-1].model_copy(
        update={"operand_rule_ids": (EDUCATION_RULE_ID, UNKNOWN_RULE_ID)}
    )
    candidate = rule_set().model_copy(update={"rules": (*rules[:-1], invalid_root)})
    assert_compile_error(candidate, "MISSING_OPERAND")


def test_compiler_rejects_invalid_composite_arity_after_bypassed_validation() -> None:
    rules = valid_rules()
    invalid_root = rules[-1].model_copy(update={"operand_rule_ids": (EDUCATION_RULE_ID,)})
    candidate = rule_set().model_copy(update={"rules": (*rules[:-1], invalid_root)})
    assert_compile_error(candidate, "INVALID_ARITY")


def test_compiler_rejects_cycles() -> None:
    first = composite_rule(ROOT_RULE_ID, "first", "NOT", (UNREACHABLE_RULE_ID,))
    second = composite_rule(UNREACHABLE_RULE_ID, "second", "NOT", (ROOT_RULE_ID,))
    assert_compile_error(rule_set((first, second)), "CYCLE")


def test_compiler_rejects_unreachable_rules() -> None:
    unreachable = atomic_rule(
        UNREACHABLE_RULE_ID,
        "unreachable",
        "hukou_region",
        "EQ",
        "STRING",
        "Synthetic-Zhejiang",
    )
    assert_compile_error(rule_set((*valid_rules(), unreachable)), "UNREACHABLE_RULE")


def test_equal_highest_precedence_evidence_conflict_is_compiled_as_uncertain_input() -> None:
    conflicting_rule = atomic_rule(
        EDUCATION_RULE_ID,
        "education",
        "education_level",
        "GTE",
        "STRING",
        "BACHELOR",
        rule_evidence=(evidence(7), evidence(8, relation="CONTRADICTS")),
    )
    rules = valid_rules()
    compiled = compile_rule_set(
        rule_set((conflicting_rule, rules[1], rules[2], rules[3]))
    )
    assert compiled.rules[0].evidence_conflicted is True
    assert compiled.rules[0].effective_precedence == 400
