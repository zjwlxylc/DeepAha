from uuid import UUID

import pytest

from deepaha.local_human_test.review import (
    FactDecisionCommand,
    HumanReviewError,
    RuleDecisionCommand,
    build_rule_payload,
    require_human_fact_reviewer,
)
from deepaha.review.auth import ReviewerPrincipal, ReviewerRole

REVIEWER_ID = UUID("019d0000-0000-7000-8000-000000000001")


def _principal(
    *roles: ReviewerRole,
    synthetic: bool = False,
    purposes: frozenset[str] = frozenset({"OPPORTUNITY_FACT_VALIDATION"}),
) -> ReviewerPrincipal:
    return ReviewerPrincipal(
        reviewer_id=REVIEWER_ID,
        roles=frozenset(roles),
        purposes=purposes,
        synthetic=synthetic,
    )


def test_human_fact_review_rejects_operator_only_synthetic_or_wrong_purpose() -> None:
    require_human_fact_reviewer(_principal(ReviewerRole.VALIDATION_REVIEWER))

    for principal in (
        _principal(ReviewerRole.LOCAL_TEST_OPERATOR),
        _principal(ReviewerRole.VALIDATION_REVIEWER, synthetic=True),
        _principal(ReviewerRole.VALIDATION_REVIEWER, purposes=frozenset()),
    ):
        with pytest.raises(HumanReviewError, match="HUMAN_VALIDATION_AUTHORITY_REQUIRED"):
            require_human_fact_reviewer(principal)


def test_fact_and_rule_commands_are_strict_and_bounded() -> None:
    fact = FactDecisionCommand(
        item_id=UUID("019d0000-0000-7000-8000-000000000002"),
        candidate_id=UUID("019d0000-0000-7000-8000-000000000003"),
        decision="APPROVE",
        reason="逐字核对官方原文。",
    )
    rule = RuleDecisionCommand(
        item_id=fact.item_id,
        rule_candidate_id=UUID("019d0000-0000-7000-8000-000000000004"),
        decision="REJECT",
        reason="规则表达扩大了原文范围。",
    )

    assert fact.decision == "APPROVE"
    assert rule.decision == "REJECT"
    with pytest.raises(ValueError):
        FactDecisionCommand.model_validate(fact.model_dump() | {"reason": " "})


@pytest.mark.parametrize(
    ("field_name", "value", "expected"),
    [
        (
            "education_requirements",
            {"minimum_level": "BACHELOR"},
            ("GTE", "education_level", "STRING", "BACHELOR"),
        ),
        (
            "major_requirements",
            {"allowed_codes": ["0809", "0810"]},
            ("IN", "major_code", "STRING", ["0809", "0810"]),
        ),
        (
            "credential_requirements",
            {"required_certificates": ["法律职业资格证"]},
            ("CONTAINS_ALL", "certificates", "STRING_SET", ["法律职业资格证"]),
        ),
    ],
)
def test_rules_are_deterministically_derived_only_from_verified_fact_shapes(
    field_name: str,
    value: object,
    expected: tuple[object, ...],
) -> None:
    payload = build_rule_payload(field_name=field_name, normalized_value=value)

    assert payload is not None
    assert (payload.operator, payload.field, payload.value_type, payload.value) == expected


def test_unrecognized_or_incomplete_fact_does_not_create_a_rule() -> None:
    assert build_rule_payload(field_name="canonical_title", normalized_value="公告") is None
    assert (
        build_rule_payload(
            field_name="education_requirements",
            normalized_value={"description": "本科及以上"},
        )
        is None
    )
