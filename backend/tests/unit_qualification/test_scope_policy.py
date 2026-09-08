"""No legacy policy or caller-supplied scope declaration may unlock hard outcomes."""

from dataclasses import replace
from datetime import timedelta

import pytest
from pydantic import ValidationError

from deepaha.contracts.phase4 import (
    EligibilityStatus,
    EvidenceRelation,
    RuleEvidenceAuthority,
    RuleOutcome,
    RuleSchemaV04,
)
from deepaha.unit_qualification.contracts import (
    CoverageCondition,
    UnitQualificationPlan,
    content_sha256,
)
from deepaha.unit_qualification.evaluator import evaluate_unit_qualification
from tests.unit_qualification.test_evaluator import (
    NOW,
    codes,
    condition,
    plan,
    request,
    rule,
    target,
    uid,
)


@pytest.mark.parametrize("scope", [None, "ANNOUNCEMENT", "EMPLOYER_GROUP"])
@pytest.mark.parametrize("education,engine", [("MASTER", "ELIGIBLE"), ("ASSOCIATE", "INELIGIBLE")])
def test_unreviewed_scope_caps_both_directions(
    scope: str | None, education: str, engine: str
) -> None:
    conditions: tuple[CoverageCondition, ...] = (condition(),)
    if scope:
        conditions += (
            condition(
                condition_id="parent/exception",
                source_index=1,
                scope=scope,
                source_entity_id="parent",
                source_unit_id=None,
                source_unit_version=None,
                source_unit_version_id=None,
                field_name="exception",
                state="UNPROCESSED",
                fact_id=None,
                evidence_ref_ids=[],
            ),
        )
    result = evaluate_unit_qualification(
        request(plan(conditions=conditions), attributes={"education_level": education})
    )
    assert result.engine_status.value == engine
    assert result.status is EligibilityStatus.UNCERTAIN
    assert result.status_cap is EligibilityStatus.UNCERTAIN
    assert "HUMAN_SCOPE_REVIEW_UNVERIFIED" in result.review_reasons
    assert result.contract_version == "unit-qualification/2.0.0"
    if engine == "INELIGIBLE":
        assert (
            result.conflict_rule_ids and result.rule_evaluations[0].outcome is RuleOutcome.CONFLICT
        )
        assert "NEGATIVE_CONCLUSION_REQUIRES_SCOPE_REVIEW" in result.review_reasons


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0", "1.4.0"])
def test_legacy_policy_cannot_enter_new_core_even_using_unvalidated_copy(version: str) -> None:
    candidate = plan().model_copy(update={"contract_version": f"unit-qualification/{version}"})
    with pytest.raises(ValidationError):
        evaluate_unit_qualification(request(candidate))


def test_coverage_policy_cannot_be_downgraded_even_with_recomputed_hash() -> None:
    candidate = plan()
    payload = candidate.model_dump(mode="json")
    payload["manifest"]["coverage_policy_version"] = "unit-condition-coverage/1.0.0"
    payload["manifest_sha256"] = content_sha256(payload["manifest"])
    with pytest.raises(ValidationError):
        UnitQualificationPlan.model_validate(payload)


def test_exact_unit_version_uuid_is_required_and_bound() -> None:
    wrong = target().model_copy(update={"unit_version_id": uid(999)})
    with pytest.raises(ValueError, match="target"):
        evaluate_unit_qualification(replace(request(), expected_target=wrong))
    with pytest.raises(ValidationError, match="unit version"):
        plan(conditions=(condition(source_unit_version_id=uid(999)),))
    payload = target().model_dump()
    payload.pop("unit_version_id")
    with pytest.raises(ValidationError, match="unit_version_id"):
        type(target()).model_validate(payload)


def test_lower_precedence_is_recomputed_after_correction_expires() -> None:
    current = rule(at=NOW - timedelta(days=2))
    expired = current.evidence[0].model_copy(
        update={
            "evidence_ref_id": uid(57),
            "authority": RuleEvidenceAuthority.LATEST_OFFICIAL_CORRECTION,
            "precedence": 600,
            "relation": EvidenceRelation.CONTRADICTS,
        }
    )
    candidate = RuleSchemaV04.model_validate(
        current.model_dump() | {"evidence": [*current.evidence, expired]}
    )
    saved = plan(
        candidate=candidate,
        conditions=(condition(evidence_ref_ids=[uid(4), uid(57)]),),
        admission_changes={
            "evidence_validity": [
                {
                    "evidence_ref_id": uid(4),
                    "valid_from": current.evidence[0].effective_at,
                    "valid_until": None,
                },
                {
                    "evidence_ref_id": uid(57),
                    "valid_from": expired.effective_at,
                    "valid_until": NOW,
                },
            ]
        },
    )
    result = evaluate_unit_qualification(
        request(saved, attributes={"education_level": "ASSOCIATE"})
    )
    assert result.engine_status is EligibilityStatus.INELIGIBLE
    assert result.status is EligibilityStatus.UNCERTAIN
    assert result.rule_evaluations[0].evidence_ref_ids == (uid(4),)


def test_evidence_begins_at_inclusive_start() -> None:
    result = evaluate_unit_qualification(request())
    assert result.rule_evaluations[0].evidence_ref_ids == (uid(4),)
    assert "NO_CURRENT_EVIDENCE" not in codes(result)


@pytest.mark.parametrize("version", [True, 0, -1])
def test_invalid_profile_versions_are_not_replayed(version: int) -> None:
    with pytest.raises(ValueError, match="positive version"):
        evaluate_unit_qualification(replace(request(), profile_version=version))
