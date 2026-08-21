from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest

from deepaha.contracts.phase4 import EligibilityStatus, RuleOutcome, RuleSchemaV04
from deepaha.eligibility.engine import (
    ENGINE_VERSION,
    EligibilityDecision,
    EvaluationContext,
    evaluate_eligibility,
)
from deepaha.rules.compiler import compile_rule_set
from deepaha.rules.major import (
    ApprovedMajorMapping,
    MajorCatalog,
    load_approved_major_mapping,
    load_major_catalog,
)

FIXTURE_DIRECTORY = Path(__file__).parents[1] / "fixtures" / "evaluation"
NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
SCENARIO_CLOCK = date(2026, 8, 22)
RULE_ID = UUID("019b2000-0000-7000-8000-000000000001")
ROOT_ID = UUID("019b2000-0000-7000-8000-000000000002")
RULE_SET_ID = UUID("019b2000-0000-7000-8000-000000000003")
OPPORTUNITY_ID = UUID("019b2000-0000-7000-8000-000000000004")
DOCUMENT_ID = UUID("019b2000-0000-7000-8000-000000000005")
EVIDENCE_ID = UUID("019b2000-0000-7000-8000-000000000006")
SECOND_EVIDENCE_ID = UUID("019b2000-0000-7000-8000-000000000007")
MajorAssets = tuple[MajorCatalog, ApprovedMajorMapping]


@pytest.fixture(scope="module")
def major_assets() -> MajorAssets:
    catalog = load_major_catalog(FIXTURE_DIRECTORY / "phase4-major-catalog.json")
    mapping = load_approved_major_mapping(
        FIXTURE_DIRECTORY / "phase4-major-mapping.json",
        catalog,
    )
    return catalog, mapping


def evidence_values(
    *,
    evidence_id: UUID = EVIDENCE_ID,
    authority: str = "ORIGINAL_OFFICIAL_NOTICE",
    precedence: int = 400,
    relation: str = "SUPPORTS",
) -> dict[str, object]:
    return {
        "evidence_ref_id": evidence_id,
        "document_id": DOCUMENT_ID,
        "authority": authority,
        "precedence": precedence,
        "relation": relation,
        "effective_at": NOW,
        "assertion_sha256": str(evidence_id)[-1] * 64,
    }


def atomic_rule(
    *,
    field: str,
    operator: str,
    value_type: str,
    value: object,
    evidence: list[dict[str, object]] | None = None,
) -> RuleSchemaV04:
    return RuleSchemaV04.model_validate(
        {
            "rule_id": RULE_ID,
            "code": f"phase4-{field}",
            "operator": operator,
            "field": field,
            "value_type": value_type,
            "value": value,
            "operand_rule_ids": [],
            "required": True,
            "reason_template": f"Synthetic {field} requirement",
            "evidence": evidence or [evidence_values()],
        }
    )


def context_for(
    rule: RuleSchemaV04,
    profile_attributes: dict[str, object],
    major_assets: MajorAssets,
    *,
    semantic_major_candidate: bool = False,
    scenario_clock: date = SCENARIO_CLOCK,
) -> EvaluationContext:
    catalog, mapping = major_assets
    rule_set = {
        "rule_set_id": RULE_SET_ID,
        "version": 1,
        "opportunity_id": OPPORTUNITY_ID,
        "opportunity_version": 1,
        "rules": [rule],
        "root_rule_ids": [rule.rule_id],
        "review_status": "APPROVED",
        "rule_schema_version": "0.4.0",
        "created_at": NOW,
    }
    from deepaha.contracts.phase4 import RuleSetSchemaV04

    return EvaluationContext(
        rule_set=compile_rule_set(RuleSetSchemaV04.model_validate(rule_set)),
        profile_attributes=profile_attributes,
        major_catalog=catalog,
        major_mapping=mapping,
        scenario_clock=scenario_clock,
        semantic_major_candidate=semantic_major_candidate,
    )


def evaluate(
    rule: RuleSchemaV04,
    profile_attributes: dict[str, object],
    major_assets: MajorAssets,
    *,
    semantic_major_candidate: bool = False,
    scenario_clock: date = SCENARIO_CLOCK,
) -> EligibilityDecision:
    return evaluate_eligibility(
        context_for(
            rule,
            profile_attributes,
            major_assets,
            semantic_major_candidate=semantic_major_candidate,
            scenario_clock=scenario_clock,
        )
    )


def test_all_official_deterministic_rules_satisfied_is_eligible(
    major_assets: MajorAssets,
) -> None:
    decision = evaluate(
        atomic_rule(
            field="education_level",
            operator="GTE",
            value_type="STRING",
            value="BACHELOR",
        ),
        {"education_level": "MASTER"},
        major_assets,
    )
    assert decision.status is EligibilityStatus.ELIGIBLE
    assert decision.rule_evaluations[0].outcome is RuleOutcome.SATISFIED
    assert decision.engine_version == ENGINE_VERSION
    assert decision.review_reasons == ()


def test_approved_major_mapping_is_likely_eligible_not_eligible(
    major_assets: MajorAssets,
) -> None:
    decision = evaluate(
        atomic_rule(
            field="major_code",
            operator="IN",
            value_type="STRING",
            value=["080902"],
        ),
        {"major_code": "080903"},
        major_assets,
    )
    assert decision.status is EligibilityStatus.LIKELY_ELIGIBLE
    assert decision.rule_evaluations[0].outcome is RuleOutcome.SATISFIED
    assert decision.rule_evaluations[0].official_evidence is False
    assert "MAJOR_APPROVED_MAPPING_MATCH" in decision.review_reasons


@pytest.mark.parametrize(
    ("rule", "profile", "expected_missing"),
    [
        (
            atomic_rule(
                field="certificates",
                operator="CONTAINS_ALL",
                value_type="STRING_SET",
                value=["CET4"],
            ),
            {},
            "certificates",
        ),
        (
            atomic_rule(
                field="hukou_region",
                operator="IN",
                value_type="STRING",
                value=["Synthetic-Zhejiang"],
            ),
            {},
            "hukou_region",
        ),
    ],
)
def test_missing_required_profile_fields_are_uncertain(
    major_assets: MajorAssets,
    rule: RuleSchemaV04,
    profile: dict[str, object],
    expected_missing: str,
) -> None:
    decision = evaluate(rule, profile, major_assets)
    assert decision.status is EligibilityStatus.UNCERTAIN
    assert decision.rule_evaluations[0].outcome is RuleOutcome.UNKNOWN
    assert expected_missing in decision.missing_fields


def test_official_deterministic_degree_conflict_is_ineligible(
    major_assets: MajorAssets,
) -> None:
    decision = evaluate(
        atomic_rule(
            field="education_level",
            operator="IN",
            value_type="STRING",
            value=["DOCTORATE", "MASTER"],
        ),
        {"education_level": "BACHELOR"},
        major_assets,
    )
    assert decision.status is EligibilityStatus.INELIGIBLE
    conflict = decision.rule_evaluations[0]
    assert conflict.outcome is RuleOutcome.CONFLICT
    assert conflict.deterministic is True
    assert conflict.official_evidence is True
    assert conflict.evidence_ref_ids == (EVIDENCE_ID,)


def test_low_authority_conflict_cannot_be_ineligible(
    major_assets: MajorAssets,
) -> None:
    rule = atomic_rule(
        field="education_level",
        operator="IN",
        value_type="STRING",
        value=["MASTER"],
        evidence=[
            evidence_values(
                authority="HUMAN_APPROVED_MAPPING",
                precedence=200,
            )
        ],
    )
    decision = evaluate(rule, {"education_level": "BACHELOR"}, major_assets)
    assert decision.status is EligibilityStatus.UNCERTAIN
    assert decision.rule_evaluations[0].outcome is RuleOutcome.CONFLICT
    assert decision.rule_evaluations[0].official_evidence is False
    assert "LOW_AUTHORITY_CONFLICT" in decision.review_reasons


def test_equal_top_precedence_evidence_conflict_is_uncertain(
    major_assets: MajorAssets,
) -> None:
    rule = atomic_rule(
        field="education_level",
        operator="EQ",
        value_type="STRING",
        value="BACHELOR",
        evidence=[
            evidence_values(),
            evidence_values(
                evidence_id=SECOND_EVIDENCE_ID,
                relation="CONTRADICTS",
            ),
        ],
    )
    decision = evaluate(rule, {"education_level": "BACHELOR"}, major_assets)
    assert decision.status is EligibilityStatus.UNCERTAIN
    assert decision.rule_evaluations[0].outcome is RuleOutcome.UNKNOWN
    assert "EVIDENCE_CONFLICT" in decision.review_reasons


def test_semantic_major_candidate_is_never_a_qualification_conclusion(
    major_assets: MajorAssets,
) -> None:
    decision = evaluate(
        atomic_rule(
            field="major_code",
            operator="IN",
            value_type="STRING",
            value=["0809"],
        ),
        {"major_code": "030101"},
        major_assets,
        semantic_major_candidate=True,
    )
    assert decision.status is EligibilityStatus.UNCERTAIN
    assert decision.rule_evaluations[0].outcome is RuleOutcome.UNKNOWN
    assert decision.rule_evaluations[0].deterministic is False
    assert "MAJOR_SEMANTIC_CANDIDATE_ONLY" in decision.review_reasons


@pytest.mark.parametrize("birth_date", ["2000-08-22", "2008-08-22"])
def test_birth_date_boundaries_are_inclusive_and_use_explicit_scenario_clock(
    major_assets: MajorAssets,
    birth_date: str,
) -> None:
    decision = evaluate(
        atomic_rule(
            field="birth_date",
            operator="BETWEEN",
            value_type="DATE",
            value=["2000-08-22", "2008-08-22"],
        ),
        {"birth_date": birth_date},
        major_assets,
        scenario_clock=SCENARIO_CLOCK,
    )
    assert decision.status is EligibilityStatus.ELIGIBLE


def test_birth_date_after_scenario_clock_is_unknown_not_ineligible(
    major_assets: MajorAssets,
) -> None:
    decision = evaluate(
        atomic_rule(
            field="birth_date",
            operator="LTE",
            value_type="DATE",
            value="2008-08-22",
        ),
        {"birth_date": "2026-08-23"},
        major_assets,
        scenario_clock=SCENARIO_CLOCK,
    )
    assert decision.status is EligibilityStatus.UNCERTAIN
    assert decision.rule_evaluations[0].outcome is RuleOutcome.UNKNOWN
    assert "PROFILE_DATE_AFTER_SCENARIO_CLOCK" in decision.review_reasons


@pytest.mark.parametrize(
    ("field", "value_type", "allowed", "actual"),
    [
        ("graduation_year", "INTEGER", [2025, 2026], 2024),
        ("student_status", "STRING", ["GRADUATING", "RECENT_GRADUATE"], "EMPLOYED"),
        ("residence_region", "STRING", ["Synthetic-Hangzhou"], "Synthetic-Ningbo"),
        ("certificates", "STRING_SET", ["CET4"], ["CET6"]),
    ],
)
def test_official_domain_conflicts_are_deterministic_ineligible(
    major_assets: MajorAssets,
    field: str,
    value_type: str,
    allowed: list[object],
    actual: object,
) -> None:
    operator = "CONTAINS_ALL" if value_type == "STRING_SET" else "IN"
    decision = evaluate(
        atomic_rule(
            field=field,
            operator=operator,
            value_type=value_type,
            value=allowed,
        ),
        {field: actual},
        major_assets,
    )
    assert decision.status is EligibilityStatus.INELIGIBLE


def test_and_composition_prioritizes_official_conflict_over_other_missing_fields(
    major_assets: MajorAssets,
) -> None:
    education = atomic_rule(
        field="education_level",
        operator="IN",
        value_type="STRING",
        value=["MASTER"],
    )
    certificate = atomic_rule(
        field="certificates",
        operator="CONTAINS_ALL",
        value_type="STRING_SET",
        value=["CET4"],
    ).model_copy(update={"rule_id": ROOT_ID, "code": "phase4-certificates"})
    composite = RuleSchemaV04.model_validate(
        {
            "rule_id": UUID("019b2000-0000-7000-8000-000000000008"),
            "code": "phase4-root",
            "operator": "AND",
            "field": None,
            "value_type": None,
            "value": None,
            "operand_rule_ids": [education.rule_id, certificate.rule_id],
            "required": True,
            "reason_template": "Synthetic combined rule",
            "evidence": [],
        }
    )
    from deepaha.contracts.phase4 import RuleSetSchemaV04

    catalog, mapping = major_assets
    compiled = compile_rule_set(
        RuleSetSchemaV04.model_validate(
            {
                "rule_set_id": RULE_SET_ID,
                "version": 1,
                "opportunity_id": OPPORTUNITY_ID,
                "opportunity_version": 1,
                "rules": [education, certificate, composite],
                "root_rule_ids": [composite.rule_id],
                "review_status": "APPROVED",
                "rule_schema_version": "0.4.0",
                "created_at": NOW,
            }
        )
    )
    decision = evaluate_eligibility(
        EvaluationContext(
            rule_set=compiled,
            profile_attributes={"education_level": "BACHELOR"},
            major_catalog=catalog,
            major_mapping=mapping,
            scenario_clock=SCENARIO_CLOCK,
        )
    )
    assert decision.status is EligibilityStatus.INELIGIBLE
    assert set(decision.conflict_rule_ids) >= {education.rule_id, composite.rule_id}
    assert certificate.rule_id in decision.unknown_rule_ids
