"""Candidate payloads must compile and preserve deterministic qualification semantics."""

import pytest

from deepaha.contracts.phase4 import EligibilityStatus, RuleSchemaV04
from deepaha.local_human_test.review import build_rule_payload
from tests.eligibility.test_engine import (
    RULE_ID,
    MajorAssets,
    evaluate,
    evidence_values,
    major_assets,
)

__all__ = ["major_assets"]


@pytest.mark.parametrize(
    ("field", "normalized", "allowed", "denied"),
    [
        (
            "education_requirements",
            {"minimum_level": "BACHELOR"},
            {"education_level": "MASTER"},
            {"education_level": "ASSOCIATE"},
        ),
        (
            "major_requirements",
            {"allowed_codes": ["080901"]},
            {"major_code": "080901"},
            {"major_code": "030101"},
        ),
        (
            "household_registration_requirements",
            {"allowed_regions": ["330100"]},
            {"hukou_region": "330100"},
            {"hukou_region": "310100"},
        ),
        (
            "applicant_scope",
            {"student_statuses": ["GRADUATING", "RECENT_GRADUATE"]},
            {"student_status": "GRADUATING"},
            {"student_status": "EMPLOYED"},
        ),
        (
            "credential_requirements",
            {"required_certificates": ["合成证书"]},
            {"certificates": ["合成证书"]},
            {"certificates": []},
        ),
        (
            "age_requirements",
            {"birth_date_between": ["1990-01-01", "2005-12-31"]},
            {"birth_date": "1998-01-01"},
            {"birth_date": "1970-01-01"},
        ),
    ],
)
def test_candidate_can_compile_and_distinguish_allowed_denied_and_missing(
    field: str,
    normalized: object,
    allowed: dict[str, object],
    denied: dict[str, object],
    major_assets: MajorAssets,
) -> None:
    payload = build_rule_payload(field_name=field, normalized_value=normalized)
    assert payload is not None
    rule = RuleSchemaV04.model_validate(
        payload.model_dump()
        | {
            "rule_id": RULE_ID,
            "operand_rule_ids": [],
            "evidence": [evidence_values()],
        }
    )
    for profile, expected in [
        (allowed, EligibilityStatus.ELIGIBLE),
        (denied, EligibilityStatus.INELIGIBLE),
        ({}, EligibilityStatus.UNCERTAIN),
    ]:
        result = evaluate(rule, profile, major_assets)
        assert result.status is expected
        assert result.rule_evaluations[0].evidence_ref_ids == (rule.evidence[0].evidence_ref_id,)
