"""Candidate values remain separate from source support and human approval."""

from dataclasses import asdict
from typing import Literal

import pytest

from deepaha.investigations.delivery import DeliveryEvidence, DeliveryFact
from deepaha.investigations.field_mapping import FieldTarget, map_field_candidate


def fact(value: str | None, *, field: str = "学历要求", status: str = "CONFIRMED") -> DeliveryFact:
    return DeliveryFact(
        "position",
        field,
        value,
        status,
        (DeliveryEvidence("notice", "学历、学位要求", {"selector": "th"}, "a" * 64, False),),
    )


def test_mapping_does_not_touch_quote_locator_or_claim_evidence() -> None:
    original = fact("硕士及以上")
    before = asdict(original)
    mapped = map_field_candidate(original, target=FieldTarget("position", "position"))
    assert mapped.normalized_value_candidate == {"minimum_level": "MASTER"}
    assert mapped.target_scope == "UNIT" and not mapped.abstained
    assert asdict(original) == before
    assert not hasattr(mapped, "ready_for_persistence")


@pytest.mark.parametrize(
    "value", ["本科", "本科或硕士", "硕士及以上（仅限应届）", "不限", "无要求", None]
)
def test_does_not_guess_or_drop_qualifiers(value: str | None) -> None:
    mapped = map_field_candidate(fact(value), target=FieldTarget("position", "position"))
    assert mapped.abstained and mapped.normalized_value_candidate is None


@pytest.mark.parametrize("status", ["UNKNOWN", "CONFLICT", "INSUFFICIENT", "UNPROCESSED"])
def test_retains_original_investigation_status(status: str) -> None:
    mapped = map_field_candidate(
        fact("硕士及以上", status=status), target=FieldTarget("position", "position")
    )
    assert mapped.original_status == status and mapped.abstained
    assert mapped.normalized_value_candidate is None


@pytest.mark.parametrize(
    "kind,scope", [("announcement", "OPPORTUNITY"), ("unit", None), ("position", "UNIT")]
)
def test_conditions_stay_on_their_declared_entity(
    kind: Literal["announcement", "unit", "position"], scope: str | None
) -> None:
    mapped = map_field_candidate(fact("硕士及以上"), target=FieldTarget("position", kind))
    assert mapped.target_scope == scope
    if scope is None:
        assert mapped.abstained
    other = map_field_candidate(fact("硕士及以上"), target=FieldTarget("other", kind))
    assert other.target_scope is None and other.abstained


@pytest.mark.parametrize(
    "field,value",
    [
        ("age", "35"),
        ("年龄要求", '{"birth_date_between":["2000-02-30","2001-01-01"]}'),
        ("年龄要求", '{"birth_date_between":["2001-01-01","2000-01-01"]}'),
        ("学历要求", '{"minimum_level":"MASTER","minimum_level":"BACHELOR"}'),
        ("专业要求", "计算机相关专业"),
        ("专业要求", "专业代码：0812、0812"),
        ("专业要求", '{"allowed_codes":[812]}'),
        ("户籍要求", '{"allowed_regions":[]}'),
    ],
)
def test_unsupported_or_ambiguous_value_abstains(field: str, value: str) -> None:
    mapped = map_field_candidate(
        fact(value, field=field), target=FieldTarget("position", "position")
    )
    assert mapped.abstained and mapped.raw_value == value
    assert mapped.normalized_value_candidate is None


def test_explicit_codes_keep_leading_zeros() -> None:
    mapped = map_field_candidate(
        fact("专业代码：0812、0809", field="专业要求"), target=FieldTarget("position", "position")
    )
    assert mapped.normalized_value_candidate == {"allowed_codes": ["0809", "0812"]}
