"""Keep condition-level time coverage and leaf diagnostics separate from root decisions."""

from datetime import timedelta

import pytest

from deepaha.contracts.phase4 import EligibilityStatus, RuleOutcome, RuleSchemaV04
from deepaha.unit_qualification.contracts import (
    UnitQualificationPlan,
    coverage_manifest_sha256,
    rule_sha256,
)
from deepaha.unit_qualification.evaluator import evaluate_unit_qualification
from tests.unit_qualification.test_evaluator import (
    NOW,
    composite_plan,
    condition,
    plan,
    request,
    rule,
    uid,
)


def test_each_condition_needs_current_evidence_not_just_the_rule_as_a_whole() -> None:
    first = rule(at=NOW - timedelta(days=2))
    second_evidence = first.evidence[0].model_copy(update={"evidence_ref_id": uid(99)})
    candidate = RuleSchemaV04.model_validate(
        first.model_dump() | {"evidence": [*first.evidence, second_evidence]}
    )
    second_condition = condition(
        condition_id="position-0/field-1",
        source_index=1,
        fact_id=uid(98),
        evidence_ref_ids=[uid(99)],
    )
    base = plan(
        candidate=candidate,
        conditions=(condition(), second_condition),
        admission_changes={
            "condition_ids": ["position-0/field-0", "position-0/field-1"],
            "evidence_validity": [
                {
                    "evidence_ref_id": uid(4),
                    "valid_from": first.evidence[0].effective_at,
                    "valid_until": None,
                },
                {
                    "evidence_ref_id": uid(99),
                    "valid_from": second_evidence.effective_at,
                    "valid_until": NOW,
                },
            ],
        },
    )
    saved = UnitQualificationPlan.model_validate(
        base.model_dump()
        | {
            "dispositions": [
                *base.dispositions,
                base.dispositions[0].model_copy(
                    update={"condition_id": second_condition.condition_id}
                ),
            ]
        }
    )
    result = evaluate_unit_qualification(
        request(saved, attributes={"education_level": "ASSOCIATE"})
    )
    assert result.engine_status is EligibilityStatus.UNCERTAIN
    assert result.rule_evaluations[0].outcome is RuleOutcome.UNKNOWN
    assert any(
        b.code == "CONDITION_EVIDENCE_NOT_CURRENT"
        and b.condition_id == second_condition.condition_id
        for b in result.coverage_blockers
    )


@pytest.mark.parametrize(
    "attributes,outcome", [({"education_level": "ASSOCIATE"}, "CONFLICT"), ({}, "UNKNOWN")]
)
def test_current_leaf_diagnostics_survive_an_unexecutable_composite(
    attributes: dict[str, object], outcome: str
) -> None:
    result = evaluate_unit_qualification(request(composite_plan("AND"), attributes=attributes))
    rows = {row.rule_id: row for row in result.rule_evaluations}
    assert result.status is EligibilityStatus.UNCERTAIN
    assert result.engine_status is EligibilityStatus.UNCERTAIN
    assert rows[uid(63)].outcome is RuleOutcome.UNKNOWN
    assert rows[uid(3)].outcome.value == outcome
    assert rows[uid(3)].evidence_ref_ids == (uid(4),)
    assert result.diagnostic_rule_ids == (uid(3),)
    if outcome == "CONFLICT":
        assert result.conflict_rule_ids == (uid(3),)
    else:
        assert tuple(field.value for field in result.missing_fields) == ("education_level",)


def test_diagnostic_conflict_does_not_override_an_independent_executable_root() -> None:
    base = composite_plan("AND")
    root = RuleSchemaV04.model_validate(
        rule().model_dump()
        | {
            "rule_id": uid(80),
            "code": "current-graduation-root",
            "field": "graduation_year",
            "operator": "GTE",
            "value_type": "INTEGER",
            "value": 2026,
            "evidence": [rule().evidence[0].model_copy(update={"evidence_ref_id": uid(81)})],
        }
    )
    added = condition(
        condition_id="position-0/field-2",
        source_index=2,
        fact_id=uid(82),
        field_name="graduation_year",
        evidence_ref_ids=[uid(81)],
    )
    manifest = base.manifest.model_copy(update={"conditions": (*base.manifest.conditions, added)})
    candidate = UnitQualificationPlan.model_validate(
        base.model_dump()
        | {
            "manifest": manifest,
            "manifest_sha256": coverage_manifest_sha256(manifest),
            "rules": [*base.rules, root],
            "root_rule_ids": [*base.root_rule_ids, root.rule_id],
            "dispositions": [
                *base.dispositions,
                base.dispositions[0].model_copy(
                    update={
                        "condition_id": added.condition_id,
                        "rule_ids": (root.rule_id,),
                        "decision_id": uid(85),
                    }
                ),
            ],
            "admissions": [
                *base.admissions,
                base.admissions[0].model_copy(
                    update={
                        "rule_id": root.rule_id,
                        "rule_sha256": rule_sha256(root),
                        "candidate_id": uid(83),
                        "approval_decision_id": uid(84),
                        "condition_ids": (added.condition_id,),
                        "evidence_validity": (
                            base.admissions[0]
                            .evidence_validity[0]
                            .model_copy(update={"evidence_ref_id": uid(81)}),
                        ),
                    }
                ),
            ],
        }
    )
    result = evaluate_unit_qualification(
        request(candidate, attributes={"education_level": "ASSOCIATE", "graduation_year": 2026})
    )
    assert result.engine_status is EligibilityStatus.ELIGIBLE
    assert result.status is EligibilityStatus.UNCERTAIN
    assert result.conflict_rule_ids == result.diagnostic_rule_ids == (uid(3),)
