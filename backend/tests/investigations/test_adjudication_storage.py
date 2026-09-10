"""Exact frozen review bytes; numerical JSONB equality is not digest equality."""

from copy import deepcopy
from hashlib import sha256

import pytest

from deepaha.investigations.adjudication_storage import freeze_adjudication, thaw_adjudication
from deepaha.investigations.contracts import digest
from tests.investigations.test_cross_level_adjudication import package


@pytest.mark.parametrize("number", [0, 1, 1.0, -0.0, 1e-7, 1e20, 1e308, 9007199254740993])
def test_literal_roundtrip_and_existing_digest_are_preserved(number: int | float) -> None:
    value = package()
    value["decisions"] = []
    value["proposal"]["evidence"][0]["locator"]["synthetic_numeric_probe"] = number
    value["proposal"]["reason"] = "原文\t保留\n🎓（学历）e\u0301\u00a0"
    before = deepcopy(value)
    saved = freeze_adjudication(value)
    assert saved.payload_sha256 == digest(value)
    actual = thaw_adjudication(saved.model_dump(), expected_payload_sha256=digest(value))
    assert digest(actual) == digest(value) and value == before
    assert actual["proposal"]["source_review"] == value["proposal"]["source_review"]


@pytest.mark.parametrize("attack", ["hash", "rewrite", "whitespace", "duplicate", "nan", "version"])
def test_invalid_or_reencoded_storage_is_rejected(attack: str) -> None:
    value = package()
    saved = freeze_adjudication(value).model_dump()
    original = saved["payload_sha256"]
    if attack == "hash":
        saved["payload_sha256"] = "f" * 64
    elif attack == "rewrite":
        value["decisions"].pop()
        saved = freeze_adjudication(value).model_dump()
    elif attack == "whitespace":
        saved["payload_text"] = " " + saved["payload_text"]
    elif attack == "duplicate":
        saved["payload_text"] = '{"decisions":[],"decisions":[]}'
    elif attack == "nan":
        saved["payload_text"] = '{"probe":NaN}'
    else:
        saved["storage_version"] = "future/2"
    if attack in {"whitespace", "duplicate", "nan"}:
        saved["payload_sha256"] = sha256(saved["payload_text"].encode()).hexdigest()
        original = saved["payload_sha256"]  # invalid even with internally matching byte hash
    with pytest.raises(ValueError):
        thaw_adjudication(saved, expected_payload_sha256=original)


def test_canonical_storage_does_not_replace_domain_validation() -> None:
    value = package()
    value["decisions"][0]["reviewer_id"] = value["proposal"]["producer_id"]
    with pytest.raises(ValueError, match="independent"):
        freeze_adjudication(value)


def test_equal_numbers_with_different_frozen_representation_have_different_hashes() -> None:
    a = package()
    a["decisions"] = []
    b = deepcopy(a)
    a["proposal"]["evidence"][0]["locator"]["probe"] = 1
    b["proposal"]["evidence"][0]["locator"]["probe"] = 1.0
    assert a == b  # Python and JSONB numerical equality cannot protect exact evidence bytes.
    assert freeze_adjudication(a).payload_sha256 != freeze_adjudication(b).payload_sha256


def test_legacy_timestamp_spelling_is_not_normalized_on_storage() -> None:
    value = package()
    value["decisions"][0]["created_at"] = "2026-09-10T15:00:00+00:00"
    saved = freeze_adjudication(value)
    restored = thaw_adjudication(saved.model_dump(), expected_payload_sha256=digest(value))
    assert restored["decisions"][0]["created_at"] == "2026-09-10T15:00:00+00:00"
    assert saved.payload_sha256 == digest(value)


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_nested_numbers_cannot_be_frozen(number: float) -> None:
    value = package()
    value["decisions"] = []
    value["proposal"]["evidence"][0]["locator"]["probe"] = number
    with pytest.raises(ValueError):
        freeze_adjudication(value)
