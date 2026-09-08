"""Synthetic offline plans; no authenticated database admission or human acceptance."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from deepaha.contracts.phase4 import (
    EligibilityStatus,
    EvidenceRelation,
    RuleEvidenceAuthority,
    RuleOutcome,
    RuleSchemaV04,
)
from deepaha.rules.major import load_approved_major_mapping, load_major_catalog
from deepaha.unit_qualification.compiler import compile_unit_qualification
from deepaha.unit_qualification.contracts import (
    ConditionDisposition,
    CoverageCondition,
    CoverageManifest,
    UnitIdentity,
    UnitQualificationPlan,
    UnitRuleAdmission,
    coverage_manifest_sha256,
    rule_sha256,
)
from deepaha.unit_qualification.evaluator import UnitEvaluationInput, evaluate_unit_qualification

NOW = datetime(2026, 9, 7, 9, tzinfo=UTC)
ASSETS = Path(__file__).parents[1] / "fixtures" / "evaluation"


def uid(n: int) -> UUID:
    return UUID(f"019b3000-0000-7000-8000-{n:012d}")


def target() -> UnitIdentity:
    return UnitIdentity(
        opportunity_id=uid(1),
        opportunity_version=2,
        unit_id=uid(2),
        unit_version=3,
        unit_version_id=uid(71),
    )


def rule(*, authority: str = "FORMAL_OFFICIAL_ATTACHMENT", at: datetime = NOW) -> RuleSchemaV04:
    return RuleSchemaV04.model_validate(
        {
            "rule_id": uid(3),
            "code": "minimum-education",
            "operator": "GTE",
            "field": "education_level",
            "value_type": "STRING",
            "value": "BACHELOR",
            "operand_rule_ids": [],
            "required": True,
            "reason_template": "Requires bachelor education",
            "evidence": [
                {
                    "evidence_ref_id": uid(4),
                    "document_id": uid(5),
                    "authority": authority,
                    "precedence": RuleEvidenceAuthority(authority).precedence,
                    "relation": "SUPPORTS",
                    "effective_at": at,
                    "assertion_sha256": "a" * 64,
                }
            ],
        }
    )


def condition(**updates: object) -> CoverageCondition:
    values: dict[str, object] = {
        "condition_id": "position-0/field-0",
        "scope": "UNIT",
        "source_entity_id": "position-0",
        "source_index": 0,
        "source_unit_id": uid(2),
        "source_unit_version": 3,
        "source_unit_version_id": uid(71),
        "field_name": "education",
        "source_sha256": "b" * 64,
        "state": "KNOWN",
        "fact_id": uid(6),
        "evidence_ref_ids": [uid(4)],
    }
    return CoverageCondition.model_validate(values | updates)


def plan(
    *,
    candidate: RuleSchemaV04 | None = None,
    conditions: tuple[CoverageCondition, ...] | None = None,
    dispositions: tuple[ConditionDisposition, ...] | None = None,
    admission_changes: dict[str, object] | None = None,
    empty: bool = False,
) -> UnitQualificationPlan:
    candidate = candidate or rule()
    manifest = CoverageManifest(
        coverage_policy_version="unit-condition-coverage/2.0.0",
        target=target(),
        preparation_id=uid(7),
        preparation_sha256="c" * 64,
        conditions=(condition(),) if conditions is None else conditions,
        upstream_blockers=(),
    )
    admission: dict[str, object] = {
        "rule_id": candidate.rule_id,
        "target": target(),
        "rule_sha256": rule_sha256(candidate),
        "condition_ids": ["position-0/field-0"],
        "candidate_id": uid(8),
        "approval_decision_id": uid(9),
        "producer_principal_id": "component:rule-candidate-v1",
        "reviewer_principal_id": "human:test-reviewer",
        "reviewed_at": NOW,
        "evidence_validity": [
            {
                "evidence_ref_id": item.evidence_ref_id,
                "valid_from": item.effective_at,
                "valid_until": None,
            }
            for item in candidate.evidence
        ],
    }
    default_disposition = ConditionDisposition(
        condition_id="position-0/field-0",
        kind="RULE",
        rule_ids=(candidate.rule_id,),
        decision_id=uid(10),
        reviewer_principal_id="human:test-reviewer",
        reason="Exact field",
    )
    return UnitQualificationPlan(
        contract_version="unit-qualification/2.0.0",
        qualification_plan_id=uid(11),
        version=1,
        target=target(),
        manifest=manifest,
        manifest_sha256=coverage_manifest_sha256(manifest),
        dispositions=(default_disposition,) if dispositions is None else dispositions,
        rules=() if empty else (candidate,),
        root_rule_ids=() if empty else (candidate.rule_id,),
        admissions=()
        if empty
        else (UnitRuleAdmission.model_validate(admission | (admission_changes or {})),),
    )


def request(
    candidate: UnitQualificationPlan | None = None,
    *,
    attributes: dict[str, object] | None = None,
) -> UnitEvaluationInput:
    catalog = load_major_catalog(ASSETS / "phase4-major-catalog.json")
    mapping = load_approved_major_mapping(ASSETS / "phase4-major-mapping.json", catalog)
    return UnitEvaluationInput(
        plan=candidate or plan(),
        expected_target=target(),
        profile_snapshot_id=uid(12),
        profile_version=2,
        profile_schema_version="unit-test-profile-v1",
        profile_attributes={"education_level": "MASTER"} if attributes is None else attributes,
        major_catalog=catalog,
        major_mapping=mapping,
        scenario_clock=date(2026, 9, 7),
        evidence_as_of=NOW,
    )


def codes(result: object) -> set[str]:
    from deepaha.unit_qualification.evaluator import UnitQualificationResult

    assert isinstance(result, UnitQualificationResult)
    return {item.code for item in result.coverage_blockers}


def test_no_rules_is_uncertain_without_fabricated_rule_ids() -> None:
    result = evaluate_unit_qualification(request(plan(empty=True, dispositions=())))
    assert result.status is EligibilityStatus.UNCERTAIN
    assert result.rule_evaluations == ()
    assert result.unknown_rule_ids == ()
    assert "NO_EXECUTABLE_RULES" in codes(result)


def test_all_supplied_fields_reviewed_does_not_prove_full_document_scope() -> None:
    result = evaluate_unit_qualification(request())
    assert result.engine_status is EligibilityStatus.ELIGIBLE
    assert result.status is EligibilityStatus.UNCERTAIN
    assert result.applied_status_cap is EligibilityStatus.UNCERTAIN
    assert "HUMAN_SCOPE_REVIEW_UNVERIFIED" in codes(result)
    assert result.target == target()
    assert not hasattr(result, "rule_set_id")


def test_caller_cannot_clear_scope_review_with_complete_boolean() -> None:
    payload = plan().manifest.model_dump() | {"complete": True}
    with pytest.raises(ValidationError, match="Extra inputs"):
        CoverageManifest.model_validate(payload)


def test_official_conflict_is_preserved_without_a_final_denial() -> None:
    result = evaluate_unit_qualification(request(attributes={"education_level": "ASSOCIATE"}))
    assert result.engine_status is EligibilityStatus.INELIGIBLE
    assert result.status is EligibilityStatus.UNCERTAIN
    assert result.applied_status_cap is EligibilityStatus.UNCERTAIN
    assert result.rule_evaluations[0].deterministic
    assert result.rule_evaluations[0].official_evidence


@pytest.mark.parametrize("at", [NOW + timedelta(seconds=1), NOW + timedelta(days=1)])
def test_future_evidence_cannot_deny(at: datetime) -> None:
    result = evaluate_unit_qualification(
        request(plan(candidate=rule(at=at)), attributes={"education_level": "ASSOCIATE"})
    )
    assert result.status is EligibilityStatus.UNCERTAIN
    assert result.rule_evaluations[0].outcome is RuleOutcome.UNKNOWN
    assert "NO_CURRENT_EVIDENCE" in codes(result)


def test_expired_evidence_cannot_deny_at_exclusive_end() -> None:
    candidate = plan(
        admission_changes={
            "evidence_validity": [
                {
                    "evidence_ref_id": uid(4),
                    "valid_from": NOW - timedelta(days=1),
                    "valid_until": NOW,
                }
            ]
        },
        candidate=rule(at=NOW - timedelta(days=1)),
    )
    result = evaluate_unit_qualification(
        request(candidate, attributes={"education_level": "ASSOCIATE"})
    )
    assert result.status is EligibilityStatus.UNCERTAIN


def test_low_authority_conflict_cannot_deny() -> None:
    result = evaluate_unit_qualification(
        request(
            plan(candidate=rule(authority="LLM_SEMANTIC_INFERENCE")),
            attributes={"education_level": "ASSOCIATE"},
        )
    )
    assert result.status is EligibilityStatus.UNCERTAIN
    assert not result.rule_evaluations[0].official_evidence


@pytest.mark.parametrize("scope", ["ANNOUNCEMENT", "EMPLOYER_GROUP"])
def test_parent_and_group_rules_do_not_implicitly_apply_to_unit(scope: str) -> None:
    candidate = plan(
        conditions=(
            condition(
                scope=scope,
                source_unit_id=None,
                source_unit_version=None,
                source_unit_version_id=None,
            ),
        )
    )
    result = evaluate_unit_qualification(
        request(candidate, attributes={"education_level": "ASSOCIATE"})
    )
    assert result.status is EligibilityStatus.UNCERTAIN
    assert "SCOPE_NOT_SUPPORTED" in codes(result)


@pytest.mark.parametrize(
    "state", ["UNKNOWN", "CONFLICT", "UNSUPPORTED", "REJECTED", "UNLOCATED", "UNPROCESSED"]
)
def test_unresolved_condition_cannot_be_promoted_to_rule(state: str) -> None:
    result = evaluate_unit_qualification(
        request(
            plan(conditions=(condition(state=state),)), attributes={"education_level": "ASSOCIATE"}
        )
    )
    assert result.status is EligibilityStatus.UNCERTAIN
    assert "CONDITION_UNRESOLVED" in codes(result)


def test_unknown_degree_remains_in_full_denominator() -> None:
    extra = condition(
        condition_id="position-0/field-1",
        source_index=1,
        field_name="degree",
        state="UNSUPPORTED",
        fact_id=None,
        evidence_ref_ids=[],
    )
    result = evaluate_unit_qualification(request(plan(conditions=(condition(), extra))))
    assert result.status is EligibilityStatus.UNCERTAIN
    assert any(item.condition_id == extra.condition_id for item in result.coverage_blockers)


def test_missing_profile_field_remains_visible() -> None:
    result = evaluate_unit_qualification(request(attributes={}))
    assert result.status is EligibilityStatus.UNCERTAIN
    assert tuple(item.value for item in result.missing_fields) == ("education_level",)


@pytest.mark.parametrize(
    "changes", [{"unit_version": 4}, {"unit_id": uid(44)}, {"opportunity_version": 3}]
)
def test_target_version_mismatch_is_rejected(changes: dict[str, object]) -> None:
    wrong = UnitIdentity.model_validate(target().model_dump() | changes)
    with pytest.raises(ValueError, match="target"):
        evaluate_unit_qualification(replace(request(), expected_target=wrong))


def test_sibling_fact_cannot_enter_unit_manifest() -> None:
    with pytest.raises(ValidationError, match="unit"):
        plan(conditions=(condition(source_unit_id=uid(44)),))


def test_manifest_tampering_is_rejected() -> None:
    candidate = plan()
    altered = candidate.model_copy(update={"manifest_sha256": "d" * 64})
    with pytest.raises(ValueError, match="manifest"):
        compile_unit_qualification(altered, evidence_as_of=NOW)


@pytest.mark.parametrize(
    "changes",
    [
        {"rule_sha256": "d" * 64},
        {
            "target": {
                "opportunity_id": uid(1),
                "opportunity_version": 2,
                "unit_id": uid(2),
                "unit_version": 4,
                "unit_version_id": uid(71),
            }
        },
        {"producer_principal_id": "human:test-reviewer"},
        {"condition_ids": ["omitted-condition"]},
    ],
)
def test_invalid_rule_admission_is_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        compile_unit_qualification(plan(admission_changes=changes), evidence_as_of=NOW)


def test_missing_approval_blocks_execution() -> None:
    candidate = plan().model_copy(update={"admissions": ()})
    result = evaluate_unit_qualification(
        request(candidate, attributes={"education_level": "ASSOCIATE"})
    )
    assert result.status is EligibilityStatus.UNCERTAIN
    assert "RULE_APPROVAL_MISSING" in codes(result)


def test_missing_or_unbound_fact_evidence_blocks_execution() -> None:
    result = evaluate_unit_qualification(
        request(
            plan(conditions=(condition(fact_id=None, evidence_ref_ids=[]),)),
            attributes={"education_level": "ASSOCIATE"},
        )
    )
    assert result.status is EligibilityStatus.UNCERTAIN
    assert "FACT_EVIDENCE_MISSING" in codes(result)


def test_replay_hash_binds_actual_profile_catalog_mapping_and_clocks() -> None:
    first_input = request()
    baseline = evaluate_unit_qualification(first_input)
    assert evaluate_unit_qualification(request()) == baseline
    variations = (
        replace(first_input, profile_version=3),
        replace(first_input, profile_attributes={"education_level": "BACHELOR"}),
        replace(first_input, scenario_clock=date(2026, 9, 8)),
        replace(first_input, evidence_as_of=NOW + timedelta(seconds=1)),
        replace(first_input, major_catalog=replace(first_input.major_catalog, entries={})),
        replace(
            first_input, major_mapping=replace(first_input.major_mapping, targets_by_source={})
        ),
    )
    assert all(
        evaluate_unit_qualification(item).input_sha256 != baseline.input_sha256
        for item in variations
    )


def test_future_mapping_cannot_support_hard_major_outcome() -> None:
    current = request()
    with pytest.raises(ValueError, match="mapping"):
        evaluate_unit_qualification(
            replace(
                current,
                major_mapping=replace(
                    current.major_mapping,
                    approved_at=NOW + timedelta(seconds=1),
                ),
            )
        )


def test_rejected_condition_cannot_disappear_through_nonqualification_disposition() -> None:
    disposition = ConditionDisposition(
        condition_id="position-0/field-0",
        kind="NON_QUALIFICATION",
        rule_ids=(),
        decision_id=uid(55),
        reviewer_principal_id="human:test-reviewer",
        reason="metadata",
    )
    result = evaluate_unit_qualification(
        request(
            plan(
                conditions=(condition(state="REJECTED"),),
                dispositions=(disposition,),
                empty=True,
            )
        )
    )
    assert "CONDITION_UNRESOLVED" in codes(result)


def test_nonqualification_disposition_does_not_authorize_execution_of_same_field() -> None:
    disposition = ConditionDisposition(
        condition_id="position-0/field-0",
        kind="NON_QUALIFICATION",
        rule_ids=(),
        decision_id=uid(55),
        reviewer_principal_id="human:test-reviewer",
        reason="metadata",
    )
    result = evaluate_unit_qualification(
        request(
            plan(dispositions=(disposition,)),
            attributes={"education_level": "ASSOCIATE"},
        )
    )
    assert result.status is EligibilityStatus.UNCERTAIN
    assert "RULE_DISPOSITION_MISMATCH" in codes(result)


def test_evidence_outside_frozen_fact_cannot_authorize_rule() -> None:
    result = evaluate_unit_qualification(
        request(
            plan(conditions=(condition(evidence_ref_ids=[uid(56)]),)),
            attributes={"education_level": "ASSOCIATE"},
        )
    )
    assert result.status is EligibilityStatus.UNCERTAIN
    assert "RULE_EVIDENCE_NOT_IN_FACTS" in codes(result)


def test_duplicate_denominator_rows_and_extra_dispositions_are_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        plan(conditions=(condition(), condition()))
    with pytest.raises(ValidationError, match="outside the manifest"):
        plan(
            dispositions=(
                ConditionDisposition(
                    condition_id="foreign-field",
                    kind="UNRESOLVED",
                    rule_ids=(),
                    decision_id=None,
                    reviewer_principal_id=None,
                    reason="not reviewed",
                ),
            )
        )


def test_upstream_blockers_are_preserved_in_result_and_replay_hash() -> None:
    candidate = plan()
    manifest = candidate.manifest.model_copy(update={"upstream_blockers": ("ATTACHMENT_UNREAD",)})
    candidate = candidate.model_copy(
        update={
            "manifest": manifest,
            "manifest_sha256": coverage_manifest_sha256(manifest),
        }
    )
    result = evaluate_unit_qualification(request(candidate))
    assert "ATTACHMENT_UNREAD" in codes(result)
    assert result.input_sha256 != evaluate_unit_qualification(request()).input_sha256


def test_future_higher_precedence_does_not_replace_current_official_evidence() -> None:
    current = rule(at=NOW - timedelta(days=1))
    future = current.evidence[0].model_copy(
        update={
            "evidence_ref_id": uid(57),
            "authority": RuleEvidenceAuthority.LATEST_OFFICIAL_CORRECTION,
            "precedence": 600,
            "effective_at": NOW + timedelta(days=1),
            "relation": EvidenceRelation.CONTRADICTS,
        }
    )
    candidate = RuleSchemaV04.model_validate(
        current.model_dump() | {"evidence": [*current.evidence, future]}
    )
    result = evaluate_unit_qualification(
        request(
            plan(
                candidate=candidate,
                conditions=(condition(evidence_ref_ids=[uid(4), uid(57)]),),
            ),
            attributes={"education_level": "ASSOCIATE"},
        )
    )
    assert result.engine_status is EligibilityStatus.INELIGIBLE
    assert result.status is EligibilityStatus.UNCERTAIN
    assert result.rule_evaluations[0].evidence_ref_ids == (uid(4),)


def test_current_higher_precedence_contradiction_prevents_hard_denial() -> None:
    current = rule()
    correction = current.evidence[0].model_copy(
        update={
            "evidence_ref_id": uid(57),
            "authority": RuleEvidenceAuthority.LATEST_OFFICIAL_CORRECTION,
            "precedence": 600,
            "relation": EvidenceRelation.CONTRADICTS,
        }
    )
    candidate = RuleSchemaV04.model_validate(
        current.model_dump() | {"evidence": [*current.evidence, correction]}
    )
    result = evaluate_unit_qualification(
        request(
            plan(
                candidate=candidate,
                conditions=(condition(evidence_ref_ids=[uid(4), uid(57)]),),
            ),
            attributes={"education_level": "ASSOCIATE"},
        )
    )
    assert result.status is EligibilityStatus.UNCERTAIN
    assert result.rule_evaluations[0].outcome is RuleOutcome.UNKNOWN


def composite_plan(operator: str, *, future_operand: bool = True) -> UnitQualificationPlan:
    first = plan()
    candidate = rule(at=NOW + timedelta(days=1) if future_operand else NOW)
    second = RuleSchemaV04.model_validate(
        candidate.model_dump()
        | {
            "rule_id": uid(61),
            "code": "second-rule",
            "field": "graduation_year",
            "operator": "GTE",
            "value_type": "INTEGER",
            "value": 2026,
            "evidence": [candidate.evidence[0].model_copy(update={"evidence_ref_id": uid(62)})],
        }
    )
    root = RuleSchemaV04.model_validate(
        {
            "rule_id": uid(63),
            "code": "composite-root",
            "operator": operator,
            "field": None,
            "value_type": None,
            "value": None,
            "operand_rule_ids": [uid(3), uid(61)],
            "required": True,
            "reason_template": "Approved composite",
            "evidence": [],
        }
    )
    second_condition = condition(
        condition_id="position-0/field-1",
        source_index=1,
        field_name="graduation_year",
        evidence_ref_ids=[uid(62)],
        fact_id=uid(64),
    )
    manifest = first.manifest.model_copy(update={"conditions": (condition(), second_condition)})
    base_admission = first.admissions[0].model_dump()
    second_admission = UnitRuleAdmission.model_validate(
        base_admission
        | {
            "rule_id": second.rule_id,
            "rule_sha256": rule_sha256(second),
            "condition_ids": [second_condition.condition_id],
            "evidence_validity": [
                {
                    "evidence_ref_id": uid(62),
                    "valid_from": candidate.evidence[0].effective_at,
                    "valid_until": None,
                }
            ],
        }
    )
    root_admission = UnitRuleAdmission.model_validate(
        base_admission
        | {
            "rule_id": root.rule_id,
            "rule_sha256": rule_sha256(root),
            "condition_ids": [],
            "evidence_validity": [],
        }
    )
    return UnitQualificationPlan.model_validate(
        first.model_dump()
        | {
            "manifest": manifest,
            "manifest_sha256": coverage_manifest_sha256(manifest),
            "rules": [*first.rules, second, root],
            "root_rule_ids": [root.rule_id],
            "dispositions": [
                *first.dispositions,
                first.dispositions[0].model_copy(
                    update={
                        "condition_id": second_condition.condition_id,
                        "rule_ids": (second.rule_id,),
                    }
                ),
            ],
            "admissions": [*first.admissions, second_admission, root_admission],
        }
    )


@pytest.mark.parametrize("operator", ["AND", "OR"])
def test_unexecutable_operand_does_not_get_removed_from_composite(operator: str) -> None:
    result = evaluate_unit_qualification(
        request(
            composite_plan(operator),
            attributes={"education_level": "ASSOCIATE", "graduation_year": 2020},
        )
    )
    assert result.status is EligibilityStatus.UNCERTAIN
    assert len(result.rule_evaluations) == 3
    by_id = {item.rule_id: item for item in result.rule_evaluations}
    assert by_id[uid(3)].outcome is RuleOutcome.CONFLICT
    assert by_id[uid(61)].outcome is RuleOutcome.UNKNOWN
    assert by_id[uid(63)].outcome is RuleOutcome.UNKNOWN
    assert result.engine_status is EligibilityStatus.UNCERTAIN
    assert result.diagnostic_rule_ids == (uid(3),)
    assert "DEPENDENCY_NOT_EXECUTABLE" in codes(result)


@pytest.mark.parametrize("operator,expected", [("AND", "INELIGIBLE"), ("OR", "ELIGIBLE")])
def test_executable_composite_retains_engine_semantics(operator: str, expected: str) -> None:
    result = evaluate_unit_qualification(
        request(
            composite_plan(operator, future_operand=False),
            attributes={"education_level": "ASSOCIATE", "graduation_year": 2026},
        )
    )
    assert result.engine_status.value == expected
    assert result.status is EligibilityStatus.UNCERTAIN
    assert len(result.rule_evaluations) == 3


def test_future_rule_approval_cannot_be_used_for_past_replay() -> None:
    result = evaluate_unit_qualification(
        request(
            plan(
                admission_changes={
                    "reviewed_at": NOW + timedelta(seconds=1),
                }
            ),
            attributes={"education_level": "ASSOCIATE"},
        )
    )
    assert result.status is EligibilityStatus.UNCERTAIN
    assert "RULE_APPROVAL_NOT_CURRENT" in codes(result)


@pytest.mark.parametrize("value", [None, [], {}, "", 1])
def test_missing_and_invalid_education_profile_do_not_deny(value: object) -> None:
    result = evaluate_unit_qualification(request(attributes={"education_level": value}))
    assert result.status is EligibilityStatus.UNCERTAIN


def test_clock_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone"):
        evaluate_unit_qualification(replace(request(), evidence_as_of=NOW.replace(tzinfo=None)))


def test_missing_field_is_not_confirmed_absence_under_not_composition() -> None:
    source = plan()
    absent = RuleSchemaV04.model_validate(
        source.rules[0].model_dump()
        | {
            "operator": "NOT_EXISTS",
            "value": None,
        }
    )
    root = RuleSchemaV04.model_validate(
        {
            "rule_id": uid(70),
            "code": "not-absence",
            "operator": "NOT",
            "field": None,
            "value_type": None,
            "value": None,
            "operand_rule_ids": [absent.rule_id],
            "required": True,
            "reason_template": "Explicit negation",
            "evidence": [],
        }
    )
    candidate = UnitQualificationPlan.model_validate(
        source.model_dump()
        | {
            "rules": [absent, root],
            "root_rule_ids": [root.rule_id],
            "admissions": [
                source.admissions[0].model_copy(update={"rule_sha256": rule_sha256(absent)}),
                source.admissions[0].model_copy(
                    update={
                        "rule_id": root.rule_id,
                        "rule_sha256": rule_sha256(root),
                        "condition_ids": (),
                        "evidence_validity": (),
                    }
                ),
            ],
        }
    )
    result = evaluate_unit_qualification(request(candidate, attributes={}))
    assert result.status is EligibilityStatus.UNCERTAIN
    assert "ABSENCE_NOT_PROVEN" in codes(result)
